"""游戏编排：输入分发、每帧更新、挖掘/放置、昼夜、视距剔除与存档。"""

import atexit
import math

from ursina import Sky, application, camera, color, held_keys, mouse, time, window

from . import blocks, config, i18n, keybinds, packs, storage
from .inputs import PhysicalKeys
from .mapview import WorldMap
from .materials import BlockMaterials
from .player import Player
from .ui import GameUI
from .voxel import VoxelWorld


class Game:
    def __init__(self):
        self.save_data = storage.load_save()
        print(f'[存档] {"已读取 " + config.SAVE_FILE.name if self.save_data else "无存档，使用默认世界"}')

        # 加载资源包（默认包 + 设置里选中的包），缺纹理时从 CDN 下载
        packs.ensure_active()
        self._pack = config.SETTINGS.get('resource_pack') or ''

        self.world = VoxelWorld(self.save_data)
        self.player = Player(self.world, self.save_data)
        self.ui = GameUI(self.save_data, self.world.materials,
                         on_save=self.save, on_quit=self.quit)
        self.keyboard = PhysicalKeys()
        self.mapview = WorldMap(self.world, self.player)
        self.sky = Sky()

        self.day_time = config.START_DAY_TIME
        if self.save_data:
            self.day_time = storage._save_number(
                self.save_data.get('day_time'), self.day_time, 0.0, 1.0) % 1.0
        self.last_solar = -2.0
        self.hud_timer = 0.0
        self.hud_frames = 0
        self.prev_keys = set()
        self.prev_raw_keys = set()
        self.prev_left = False
        self.prev_middle = False
        self.prev_right = False
        self.pending_scroll = 0
        self.notice = i18n.t('notice.help')
        self.notice_timer = 10.0
        self.autosave_timer = 0.0
        self._language = i18n.get_language()

        mouse.locked = True
        atexit.register(self.save)   # 覆盖窗口关闭 / alt+F4 等退出路径

    # ---------- 存档 ----------
    def save(self):
        payload = {
            'version': 2,
            'x': round(self.player.pos.x, 4),
            'z': round(self.player.pos.z, 4),
            'yaw': round(self.player.yaw % 360, 4),
            'pitch': round(self.player.pitch, 4),
            'blocks': {f'{x},{y},{z}': block_id
                       for (x, y, z), block_id in self.world.world_edits.items()},
            'hotbar': self.ui.hotbar,
            'selected_slot': self.ui.selected_slot,
            'day_time': round(self.day_time, 5),
        }
        return storage.save_payload(payload)

    def quit(self):
        self.save()
        application.quit()

    def _apply_resource_pack(self, pack_id):
        """切换资源包：确保纹理已下载，重建材质、区块网格与物品图标。"""
        self._pack = pack_id
        if pack_id:
            packs.ensure_pack(pack_id)
        self.world.materials = BlockMaterials()
        self.world.build_all()
        self.ui.apply_materials(self.world.materials)
        self.notice = i18n.t('notice.pack_switched')
        self.notice_timer = 2.0

    @staticmethod
    def _placement_target(hx, hy, hz, normal, hit_y):
        """根据命中面算出放置位置 (tx, ty, tz, layer)。

        半砖顶面命中 → 放在同一格的上层；整块顶面 → 放在上一格的下层；
        底面 → 放在下方格的上层；侧面 → 相邻格，命中上半部分时放上层。
        """
        if normal == (0, 1, 0):                     # 顶面
            if abs(hit_y - (hy + 0.5)) < 1e-6:
                return hx, hy, hz, 1
            return hx, hy + 1, hz, 0
        if normal == (0, -1, 0):                    # 底面
            return hx, hy - 1, hz, 1
        tx, tz = hx + normal[0], hz + normal[2]     # 侧面
        layer = 1 if abs(hit_y - (hy + 0.5)) < 1e-6 else 0
        return tx, hy, tz, layer

    def _drop_item(self):
        """丢弃：先丢手上的物品，否则清空当前快捷栏格。"""
        if self.ui.held_item is not None:
            self.ui.clear_held()
        elif self.ui.hotbar[self.ui.selected_slot] is not None:
            self.ui.hotbar[self.ui.selected_slot] = None
            self.ui.refresh_hotbar()
        else:
            return
        self.notice = i18n.t('notice.dropped')
        self.notice_timer = 1.5

    # ---------- 输入 ----------
    def input(self, key):
        if key == 'scroll up':
            self.pending_scroll += 1
        elif key == 'scroll down':
            self.pending_scroll -= 1
        if (key == 'left mouse down' and not self.ui.menu_state['open']
                and not self.ui.inventory_open and not mouse.locked):
            mouse.locked = True

    # ---------- 每帧更新 ----------
    def update(self):
        raw_dt = time.dt
        if raw_dt <= 0:
            return
        dt = min(raw_dt, 0.05)

        # --- 窗口最小化时不要继续锁定/抢占鼠标指针 ---
        panda_window = application.base.win if application.base else None
        if panda_window is not None:
            minimized = bool(panda_window.getProperties().getMinimized())
            if minimized and mouse.locked:
                mouse.locked = False
            elif (not minimized and not mouse.locked
                  and not self.ui.menu_state['open']
                  and not self.ui.inventory_open
                  and not self.ui.settings_open):
                mouse.locked = True

        # --- 语言切换后刷新常驻提示 ---
        if i18n.get_language() != self._language:
            self._language = i18n.get_language()
            self.notice = i18n.t('notice.help')
            self.notice_timer = 3.0
            self.mapview.retranslate()

        # --- 资源包切换：下载纹理并热重载材质 ---
        active_pack = config.SETTINGS.get('resource_pack') or ''
        if active_pack != self._pack:
            self._apply_resource_pack(active_pack)

        # --- 物理按键状态（X11）；非 X11 平台回退到 Ursina 事件层 ---
        raw_keys = self.keyboard.snapshot()
        if raw_keys is None:
            raw_keys = {k for k in keybinds.VALID_KEYS if held_keys[k]}
            if held_keys['left shift'] or held_keys['right shift']:
                raw_keys.add('shift')
            if held_keys['left control'] or held_keys['right control']:
                raw_keys.add('ctrl')
            for ursina_name, name in (('up arrow', 'up'), ('down arrow', 'down'),
                                      ('left arrow', 'left'), ('right arrow', 'right'),
                                      ('space', 'space'), ('escape', 'escape')):
                if held_keys[ursina_name]:
                    raw_keys.add(name)
        # 自定义按键绑定：物理键名 -> 游戏内部键名
        raw_just = raw_keys - self.prev_raw_keys
        self.prev_raw_keys = raw_keys.copy()
        keys = keybinds.canonicalize(raw_keys)
        just_pressed = keys - self.prev_keys
        self.prev_keys = keys.copy()

        # --- 鼠标按键（物理轮询，上升沿触发一次操作） ---
        buttons = self.keyboard.mouse_buttons()
        if buttons is None:
            left_down, middle_down, right_down = (bool(mouse.left), bool(mouse.middle),
                                                  bool(mouse.right))
        else:
            left_down, middle_down, right_down = buttons
        left_click = left_down and not self.prev_left
        middle_click = middle_down and not self.prev_middle
        right_click = right_down and not self.prev_right
        self.prev_left, self.prev_middle, self.prev_right = left_down, middle_down, right_down

        # --- M 全屏地图 / ESC 逐层返回 ---
        if 'm' in just_pressed and self.mapview.is_open:
            self.mapview.close()
        elif self.mapview.is_open and 'escape' in just_pressed:
            self.mapview.close()
        elif ('m' in just_pressed and not self.ui.menu_state['open']
              and not self.ui.inventory_open):
            self.mapview.toggle()
        elif 'escape' in just_pressed:
            if self.ui.rebind_action:
                self.ui.cancel_rebind()
            elif self.ui.keys_open:
                self.ui.close_keybinds()
            elif self.ui.packs_open:
                self.ui.close_packs()
            elif self.ui.settings_open:
                self.ui.close_settings()
            elif self.ui.menu_state['open']:
                self.ui.close_menu()
            elif self.ui.inventory_open:
                self.ui.close_inventory()
            else:
                self.ui.open_menu()

        # --- E：背包开关（菜单/地图打开时不响应） ---
        if ('e' in just_pressed and not self.ui.menu_state['open']
                and not self.mapview.is_open):
            if self.ui.inventory_open:
                self.ui.close_inventory()
            else:
                self.ui.open_inventory()

        if 'f5' in just_pressed:
            saved = self.save()
            self.notice = i18n.t('notice.saved' if saved else 'notice.save_failed')
            self.notice_timer = 1.5

        # --- G：丢弃当前手持 / 快捷栏方块 ---
        if 'g' in just_pressed and not self.ui.menu_state['open']:
            self._drop_item()

        # --- 定时自动存档 ---
        self.autosave_timer += raw_dt
        if self.autosave_timer >= config.AUTOSAVE_INTERVAL:
            self.autosave_timer = 0.0
            self.save()

        # --- 菜单 / 设置 / 资源包 / 按键绑定：暂停游戏 ---
        if self.ui.menu_state['open']:
            if self.ui.rebind_action:
                # 捕获任意新按下的物理键；ESC 取消
                for key in sorted(raw_just):
                    if key == 'escape':
                        self.ui.cancel_rebind()
                    else:
                        self.ui.finish_rebind(key)
                    break
            elif self.ui.keys_open:
                actions = list(keybinds.DEFAULT_BINDINGS)
                if 'up' in just_pressed:
                    self.ui.keys_index = (self.ui.keys_index - 1) % len(actions)
                    self.ui.refresh_keybinds()
                if 'down' in just_pressed:
                    self.ui.keys_index = (self.ui.keys_index + 1) % len(actions)
                    self.ui.refresh_keybinds()
                if 'enter' in just_pressed:
                    self.ui.start_rebind()
                if 'r' in raw_just:
                    self.ui.reset_keybinds()
            elif self.ui.packs_open:
                options = self.ui.pack_options()
                if options:
                    if 'up' in just_pressed:
                        self.ui.packs_index = (self.ui.packs_index - 1) % len(options)
                        self.ui.refresh_packs()
                    if 'down' in just_pressed:
                        self.ui.packs_index = (self.ui.packs_index + 1) % len(options)
                        self.ui.refresh_packs()
                    if 'enter' in just_pressed:
                        self.ui.apply_pack_selection()
                    if 'r' in raw_just:
                        self.ui.download_selected_pack()
            elif self.ui.settings_open:
                if 'up' in just_pressed:
                    self.ui.settings_index = (
                        self.ui.settings_index - 1) % len(self.ui.settings_rows)
                    self.ui.refresh_settings()
                if 'down' in just_pressed:
                    self.ui.settings_index = (
                        self.ui.settings_index + 1) % len(self.ui.settings_rows)
                    self.ui.refresh_settings()
                current_key = self.ui.settings_rows[self.ui.settings_index][0]
                if 'left' in just_pressed:
                    self.ui.adjust_setting(current_key, -1)
                if 'right' in just_pressed:
                    self.ui.adjust_setting(current_key, 1)
                if 'enter' in just_pressed:
                    self.ui.adjust_setting(current_key, 1)
            else:
                if 'up' in just_pressed:
                    self.ui.menu_state['index'] = (
                        self.ui.menu_state['index'] - 1) % len(self.ui.menu_buttons)
                    self.ui.refresh_menu_highlight()
                if 'down' in just_pressed:
                    self.ui.menu_state['index'] = (
                        self.ui.menu_state['index'] + 1) % len(self.ui.menu_buttons)
                    self.ui.refresh_menu_highlight()
                if 'enter' in just_pressed:
                    self.ui.menu_buttons[self.ui.menu_state['index']].on_click()
            keys = set()
            just_pressed = set()

        # --- 全屏地图打开：冻结移动与交互，刷新玩家标记 ---
        if self.mapview.is_open:
            self.ui.hide_tooltip()
            self.ui.hud.enabled = False
            keys = set()
            just_pressed = set()
            self.mapview.update_marker()
        else:
            self.ui.hud.enabled = True
            if not self.ui.inventory_open:
                self.ui.hide_tooltip()

        # --- 背包打开：暂停移动，方向键选择、回车放入快捷栏 ---
        if self.ui.inventory_open:
            page_size = config.INVENTORY_PAGE_SIZE
            page_items = self.ui.inventory_page_items()
            moved = False
            if 'left' in just_pressed:
                self.ui.inv_selected = (self.ui.inv_selected - 1) % max(1, len(page_items))
                moved = True
            if 'right' in just_pressed:
                self.ui.inv_selected = (self.ui.inv_selected + 1) % max(1, len(page_items))
                moved = True
            if 'up' in just_pressed:
                self.ui.inv_selected = (
                    self.ui.inv_selected - config.INVENTORY_COLS) % max(1, len(page_items))
                moved = True
            if 'down' in just_pressed:
                self.ui.inv_selected = (
                    self.ui.inv_selected + config.INVENTORY_COLS) % max(1, len(page_items))
                moved = True
            if 'page_up' in just_pressed or 'page_down' in just_pressed:
                self.ui.turn_inventory_page(-1 if 'page_up' in just_pressed else 1)
                moved = True
            if moved:
                self.ui.refresh_inventory()
            if 'enter' in just_pressed:
                # 手上有物品时优先用它替换当前快捷栏格，否则取高亮的创造背包格
                picked = (self.ui.held_item
                          or (page_items[self.ui.inv_selected]
                              if self.ui.inv_selected < len(page_items) else None))
                if picked is not None:
                    old = self.ui.hotbar[self.ui.selected_slot]
                    self.ui.hotbar[self.ui.selected_slot] = picked
                    if self.ui.held_item is not None:
                        # 交换：手上换成被替换掉的物品，避免丢失
                        self.ui.held_item = old
                        self.ui.held_from = (self.ui.selected_slot
                                             if old is not None else None)
                    self.ui.refresh_hotbar()
            for i in range(config.HOTBAR_SLOTS):
                if str(i + 1) in just_pressed:
                    self.ui.selected_slot = i
                    self.ui.refresh_hotbar()

            # 鼠标拖拽：点背包格拿起/放下，点快捷栏格放入
            point = self.keyboard.pointer_ui_position()
            if point is None:
                point = (mouse.x, mouse.y)
            self.ui.handle_inventory_click(point, left_click, right_click)
            self.ui.update_tooltip(point)
            keys = set()
            just_pressed = set()

        # --- 数字键 / 滚轮切换快捷栏 ---
        if not self.ui.menu_state['open'] and not self.ui.inventory_open:
            for i in range(config.HOTBAR_SLOTS):
                if str(i + 1) in just_pressed and self.ui.selected_slot != i:
                    self.ui.selected_slot = i
                    self.ui.refresh_hotbar()
            scroll_steps = self.pending_scroll
            self.pending_scroll = 0
            if scroll_steps:
                self.ui.selected_slot = (
                    self.ui.selected_slot - scroll_steps) % config.HOTBAR_SLOTS
                self.ui.refresh_hotbar()
        else:
            self.pending_scroll = 0   # 菜单/背包里滚轮不生效，丢弃

        # --- 玩家：视角、移动、跳跃、重力、相机 ---
        self.player.update(keys, just_pressed, dt)
        if self.player.notice:
            self.notice = self.player.notice
            self.notice_timer = 3.0
            self.player.notice = None

        # --- 准星射线 / 选中框 / 挖掘 / 放置 ---
        active = (not self.ui.menu_state['open'] and not self.ui.inventory_open
                  and not self.mapview.is_open)
        hit = (self.world.raycast(camera.world_position, camera.forward,
                                  config.REACH_DISTANCE) if active else None)

        show_selector = hit is not None
        if self.ui.selector.enabled != show_selector:
            self.ui.selector.enabled = show_selector

        if hit is not None:
            (hx, hy, hz), normal, hit_y = hit
            segment = self.world.segment_at_height(hx, hy, hz, hit_y)
            # 选择框：按命中方块的实际高度显示（半砖只有半格高）
            if segment is not None:
                seg_y0, seg_y1, _ = segment
                self.ui.selector.position = (hx + .5, (seg_y0 + seg_y1) / 2, hz + .5)
                self.ui.selector.scale = (1.004, max(0.004, seg_y1 - seg_y0), 1.004)

            if middle_click and segment is not None:   # 中键取方块
                picked = segment[2]
                if picked in self.ui.hotbar:
                    self.ui.selected_slot = self.ui.hotbar.index(picked)
                else:
                    self.ui.hotbar[self.ui.selected_slot] = picked
                self.ui.refresh_hotbar()
            if left_click and segment is not None:
                layer = 0 if segment[0] == hy else 1
                # 只有世界最底层的基岩不可破坏；玩家自己放置的基岩可以挖掉
                if layer == 0 and hy == config.MIN_BLOCK_Y:
                    self.notice, self.notice_timer = i18n.t('notice.bedrock'), 1.5
                elif self.world.remove_block(hx, hy, hz, layer=layer):
                    self.world.record_edit(hx, hy, hz)
                    self.world.rebuild_around(hx, hz)
            if right_click and normal != (0, 0, 0):
                tx, ty, tz, layer = self._placement_target(hx, hy, hz, normal, hit_y)
                block_id = self.ui.hotbar[self.ui.selected_slot]
                if (block_id is not None
                        and 0 <= tx < config.WORLD_SIZE and 0 <= tz < config.WORLD_SIZE
                        and config.MIN_BLOCK_Y <= ty < config.MAX_BLOCK_Y
                        and self.world.can_place(tx, ty, tz, layer, block_id)
                        and not self.player.overlaps(tx, ty, tz, block_id, layer)):
                    self.world.add_block(tx, ty, tz, block_id, layer=layer)
                    self.world.record_edit(tx, ty, tz)
                    self.world.rebuild_around(tx, tz)

        if self.ui.crosshair.enabled != active:
            self.ui.crosshair.enabled = active
        show_hotbar = not self.ui.menu_state['open'] and not self.mapview.is_open
        if self.ui.hotbar_root.enabled != show_hotbar:
            self.ui.hotbar_root.enabled = show_hotbar

        # --- 区域化视距剔除 ---
        view_sq = config.VIEW_DISTANCE * config.VIEW_DISTANCE
        for (cx, cz), entity in self.world.chunk_meshes.items():
            center_x = cx * config.CHUNK_SIZE + config.CHUNK_SIZE / 2
            center_z = cz * config.CHUNK_SIZE + config.CHUNK_SIZE / 2
            dx = max(abs(center_x - self.player.pos.x) - config.CHUNK_SIZE / 2, 0)
            dz = max(abs(center_z - self.player.pos.z) - config.CHUNK_SIZE / 2, 0)
            visible = (dx * dx + dz * dz) <= view_sq
            if entity.enabled != visible:
                entity.enabled = visible

        # --- 昼夜更替：0=午夜, 0.25=日出, 0.5=正午, 0.75=日落 ---
        self.day_time = (self.day_time + raw_dt / config.DAY_LENGTH) % 1.0
        solar = math.sin((self.day_time - 0.25) * math.tau)
        daylight = max(0.0, solar)
        if abs(solar - self.last_solar) > 0.005:
            self.last_solar = solar
            # 注意：Entity.color 直接作为 color scale 使用，必须是 0~1 的 rgba
            block_tint = color.rgba(
                min(1.0, (0.35 + 0.65 * daylight) * config.BRIGHTNESS),
                min(1.0, (0.38 + 0.62 * daylight) * config.BRIGHTNESS),
                min(1.0, (0.55 + 0.45 * daylight) * config.BRIGHTNESS), 1)
            self.world.set_tint(block_tint)
            if solar >= 0:      # 日出 → 白天
                _t = min(1.0, solar * 2.5)
                _sr, _sg, _sb = 1.0, 0.55 + 0.45 * _t, 0.40 + 0.60 * _t
            else:               # 日落 → 夜晚
                _t = min(1.0, -solar * 2.5)
                _sr = 1.0 + (0.12 - 1.0) * _t
                _sg = 0.55 + (0.16 - 0.55) * _t
                _sb = 0.40 + (0.32 - 0.40) * _t
            _sr = min(1.0, _sr * config.BRIGHTNESS)
            _sg = min(1.0, _sg * config.BRIGHTNESS)
            _sb = min(1.0, _sb * config.BRIGHTNESS)
            self.sky.color = color.rgba(_sr, _sg, _sb, 1)
            window.color = color.rgba(_sr, _sg, _sb, 1)

        # --- HUD：按间隔刷新，Text setter 每次都会重建文本节点 ---
        self.hud_timer += raw_dt
        self.hud_frames += 1
        if self.notice_timer > 0:
            self.notice_timer -= raw_dt
            if self.notice_timer <= 0:
                self.notice = ''
        if self.hud_timer >= config.HUD_INTERVAL:
            if self.ui.menu_state['open']:
                self.ui.hud.text = i18n.t('hud.menu')
            elif self.ui.inventory_open:
                self.ui.hud.text = i18n.t('hud.inventory')
            else:
                flags = [i18n.t(key) for key, on in
                         (('hud.crouch', self.player.crouching),
                          ('hud.sprint', self.player.sprinting),
                          ('hud.zoom', self.player.zooming)) if on]
                flags_text = ('  [' + ' '.join(flags) + ']') if flags else ''
                block_id = self.ui.hotbar[self.ui.selected_slot]
                block_name = (i18n.block_name(block_id,
                                              blocks.BLOCK_NAMES.get(block_id, 'Air'))
                              if block_id else 'Air')
                clock = int(self.day_time * 24 * 60) % (24 * 60)
                self.ui.hud.text = (
                    f'FPS {int(self.hud_frames / self.hud_timer):3d}   '
                    f'X {self.player.pos.x:6.1f}  Y {self.player.pos.y:5.2f}  Z {self.player.pos.z:6.1f}   '
                    f'{i18n.t("hud.eye")} {self.player.current_eye:.2f} m   '
                    f'{clock // 60:02d}:{clock % 60:02d}{flags_text}   {block_name}'
                    f'{"  [" + self.notice + "]" if self.notice else ""}'
                )
            self.hud_timer = 0.0
            self.hud_frames = 0
