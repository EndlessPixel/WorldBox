"""游戏编排：输入分发、每帧更新、挖掘/放置、昼夜、视距剔除与存档。

启动流程：没有玩家档案 → 创建玩家；否则进入主页面（单人游戏/设置）。
进入存档后才创建世界；退出到主页面会卸载世界。
"""

import atexit
import math
import time as py_time
from pathlib import Path

from ursina import Sky, application, camera, color, held_keys, mouse, time, window

from . import blocks, config, i18n, keybinds, packs, saves, storage
from .inputs import PhysicalKeys
from .mapview import WorldMap
from .materials import BlockMaterials
from .player import Player
from .ui import GameUI
from .voxel import VoxelWorld


class Game:
    def __init__(self):
        # 迁移旧存档（根目录 world_save.json → saves/ 下第一个存档）
        saves.migrate_legacy()

        # 加载资源包（默认包 + 设置里选中的包），缺纹理时从 CDN 下载
        packs.ensure_active()
        self._pack = config.SETTINGS.get('resource_pack') or ''

        # 玩家档案：没有就要先创建
        profile = saves.load_player()
        self.player_name = profile['name'] if profile else ''

        self.world = None
        self.player = None
        self.mapview = None
        self.save_path = None
        self.save_data = None
        self.state = 'menu' if profile else 'create_player'

        self.ui = GameUI(save_data=None, materials=None,
                         on_save=self.save, on_quit=self.quit)
        self.ui.notice_callback = self._show_notice
        self.ui.player_name = self.player_name or 'Player'
        self.ui.on_play_save = self.start_save
        self.ui.on_player_created = self._player_created
        self.ui.on_quit_to_title = self.quit_to_title
        self.ui.on_rename_player = self._rename_player
        self.keyboard = PhysicalKeys()
        self.sky = Sky()

        self.day_time = config.START_DAY_TIME
        self.last_solar = -2.0
        self.hud_timer = 0.0
        self.hud_frames = 0
        self.prev_keys = set()
        self.prev_raw_keys = set()
        self.prev_left = False
        self.prev_middle = False
        self.prev_right = False
        self.pending_scroll = 0
        self._pending_chars = ''       # 无物理输入后端时累积的聊天字符
        self.notice = ''
        self.notice_timer = 0.0
        self.autosave_timer = 0.0
        self._language = i18n.get_language()
        self._last_frame_time = py_time.perf_counter()

        if self.state == 'create_player':
            self.ui.show_player_creation()
        else:
            self.ui.show_title()
        mouse.locked = False
        atexit.register(self.save)   # 覆盖窗口关闭 / alt+F4 等退出路径

    # ---------- 启动流程 ----------
    def _player_created(self):
        """玩家创建完成：进入主页面。"""
        self.state = 'menu'
        self.ui.show_title()

    def start_save(self, path):
        """加载存档并进入世界。"""
        path = Path(path)
        save_data = saves.load_save(path) or {}
        self.save_path = path
        self.save_data = save_data

        self.world = VoxelWorld(save_data)
        self.player = Player(self.world, save_data)
        self.mapview = WorldMap(self.world, self.player)
        self.ui.apply_materials(self.world.materials)
        self.ui.load_hotbar(save_data)
        self.ui.refresh_hotbar()

        self.day_time = config.START_DAY_TIME
        if save_data:
            self.day_time = storage._save_number(
                save_data.get('day_time'), self.day_time, 0.0, 1.0) % 1.0
        self.autosave_timer = 0.0
        self.ui.hide_all_screens()
        self.state = 'playing'
        mouse.locked = True
        self.notice = i18n.t('notice.help')
        self.notice_timer = 10.0
        print(f'[存档] 已进入 {path}')

    def quit_to_title(self):
        """保存并卸载世界，返回主页面。"""
        self.save()
        if self.world is not None:
            self.world.destroy()
        if self.mapview is not None:
            self.mapview.destroy()
        self.world = None
        self.player = None
        self.mapview = None
        self.save_path = None
        self.save_data = None
        self.state = 'title'
        self.ui.show_title()
        mouse.locked = False

    # ---------- 存档 ----------
    def save(self):
        if self.world is None or self.save_path is None:
            return False
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
        ok = saves.save_payload(self.save_path, payload,
                                dirty_chunks=self.world.dirty_chunks)
        if ok:
            self.world.dirty_chunks.clear()
        return ok

    def quit(self):
        self.save()
        application.quit()

    # ---------- 主页面/存档页输入 ----------
    def _update_menus(self, just_pressed):
        """非游戏状态下的键盘导航（可选）；鼠标点击统一由 _dispatch_click 处理。"""
        ui = self.ui
        if ui.settings_open:
            if 'up' in just_pressed:
                ui.settings_index = (ui.settings_index - 1) % len(ui.settings_rows)
                ui.refresh_settings()
            if 'down' in just_pressed:
                ui.settings_index = (ui.settings_index + 1) % len(ui.settings_rows)
                ui.refresh_settings()
            current_key = ui.settings_rows[ui.settings_index][0]
            if 'left' in just_pressed:
                ui.adjust_setting(current_key, -1)
            if 'right' in just_pressed:
                ui.adjust_setting(current_key, 1)
            if 'enter' in just_pressed:
                ui.adjust_setting(current_key, 1)
            if 'escape' in just_pressed:
                ui.close_settings()
            return
        if ui.screen == 'title':
            if 'up' in just_pressed:
                ui.title_select(-1)
            if 'down' in just_pressed:
                ui.title_select(1)
            if 'enter' in just_pressed:
                ui.title_activate()
            if 'escape' in just_pressed:
                ui.title_quit()
            return
        if ui.screen == 'saves':
            if 'up' in just_pressed:
                ui.saves_select(-1)
            if 'down' in just_pressed:
                ui.saves_select(1)
            if 'enter' in just_pressed:
                ui.saves_play()
            if 'n' in just_pressed:
                ui.saves_new()
            if 'd' in just_pressed:
                ui.saves_delete()
            if 'escape' in just_pressed:
                ui.saves_back()
            return
        if ui.screen in ('new_save', 'player'):
            return

    # ---------- 统一鼠标分发 ----------
    def _dispatch_click(self, point, left_click, right_click):
        """所有 UI 页面走同一套物理鼠标命中；返回是否吞掉这次点击。

        吞掉后 Game 会把本帧的鼠标/键盘状态清空，避免点击切页后
        后续分支又按旧页面处理，或菜单里的点击穿透到世界挖掘逻辑。
        """
        ui = self.ui
        if self.state != 'playing':
            if ui.settings_open:
                if left_click:
                    ui.settings_click(point)
            elif ui.screen == 'title':
                if left_click:
                    ui.title_click(point)
            elif ui.screen == 'saves':
                if left_click:
                    ui.saves_click(point)
            elif ui.screen == 'new_save':
                if left_click:
                    ui.new_save_click(point)
            elif ui.screen == 'player':
                if left_click:
                    ui.player_click(point)
            return True
        if ui.rename_open:
            if left_click:
                ui.rename_click(point)
            return True
        if ui.rebind_action:
            return True                      # 等待按键重绑定，点击不生效
        if ui.keys_open:
            if left_click:
                ui.keybinds_click(point)
            return True
        if ui.packs_open:
            if left_click:
                ui.packs_click(point)
            return True
        if ui.settings_open:
            if left_click:
                ui.settings_click(point)
            return True
        if ui.menu_state['open']:
            if left_click:
                ui.menu_click(point)
            return True
        if self.mapview.is_open:
            if left_click:
                self.mapview.click(point)
            return True
        if ui.inventory_open:
            ui.inventory_click(point, left_click, right_click)
            return True
        if ui.text_input.is_open:
            return True                      # 聊天输入时点击不挖方块
        return False

    def _show_notice(self, key):
        """UI 回调：显示一次性提示（i18n 键）。"""
        self.notice = i18n.t(key)
        self.notice_timer = 2.5

    def _rename_player(self, name):
        """游戏内改名：写回玩家档案，同步聊天前缀与标题页欢迎语。"""
        if not saves.save_player(name):
            return False
        self.player_name = name
        self.ui.player_name = name
        self.ui.refresh_title()
        self.notice = i18n.t('notice.renamed')
        self.notice_timer = 2.0
        return True

    def _apply_resource_pack(self, pack_id):
        """切换资源包：确保纹理已下载，重建材质、区块网格与物品图标。"""
        self._pack = pack_id
        if pack_id:
            packs.ensure_pack(pack_id)
        if self.world is None:      # 主页面：没有世界可重建
            return
        self.world.materials = BlockMaterials()
        self.world.build_all()
        self.ui.apply_materials(self.world.materials)
        self.notice = i18n.t('notice.pack_switched')
        self.notice_timer = 2.0

    @staticmethod
    def _placement_target(hx, hy, hz, normal, hit_y, segment=None,
                          block_id=None):
        """根据命中面算出放置位置 (tx, ty, tz, layer)。

        下半砖顶面 → 同格上层；上半砖底面 → 同格下层（补全整格）；
        整格/下半砖底面 → 下方一格：整块放下层、半砖放上层贴住底面；
        整格顶面 → 上一格下层；侧面 → 相邻格，命中段是上半砖时放上层。
        """
        if segment is not None:
            seg_y0, seg_y1 = segment[0], segment[1]
        else:                      # 没有段信息时按整格处理
            seg_y0, seg_y1 = hy, hy + 1.0
        if normal == (0, 1, 0):                     # 顶面
            if abs(seg_y1 - (hy + 0.5)) < 1e-6:
                return hx, hy, hz, 1
            return hx, hy + 1, hz, 0
        if normal == (0, -1, 0):                    # 底面
            if abs(seg_y0 - (hy + 0.5)) < 1e-6:
                return hx, hy, hz, 0            # 上半砖下面补下半砖
            return hx, hy - 1, hz, (1 if blocks.is_slab(block_id) else 0)
        tx, tz = hx + normal[0], hz + normal[2]     # 侧面
        layer = 1 if abs(seg_y0 - (hy + 0.5)) < 1e-6 else 0
        return tx, hy, tz, layer

    @staticmethod
    def _placement_states(block_id, normal):
        """按放置面自动决定方块状态：目前支持 axis（原木沿法线方向倒下）。

        以后加朝向类方块，只要在新方块的 states 里声明并在这里补规则即可。
        """
        if not block_id or 'axis' not in blocks.BLOCK_STATES.get(block_id, {}):
            return None
        if normal[0]:
            return {'axis': 'x'}
        if normal[2]:
            return {'axis': 'z'}
        return {'axis': 'y'}

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
        # 无物理输入后端时的文本输入回退（Ursina 事件层）
        if self.ui.text_input.is_open:
            if key == 'space':
                self._pending_chars += ' '
            elif len(key) == 1 and key.isprintable():
                self._pending_chars += key
        if (key == 'left mouse down' and self.state == 'playing'
                and not self.ui.menu_state['open']
                and not self.ui.inventory_open
                and not self.ui.settings_open
                and not self.ui.packs_open
                and not self.ui.keys_open
                and not self.ui.text_input.is_open
                and not self.mapview.is_open
                and not mouse.locked):
            mouse.locked = True

    # ---------- 每帧更新 ----------
    def update(self):
        raw_dt = time.dt
        if raw_dt <= 0:
            return
        dt = min(raw_dt, 0.05)

        # --- 最大帧率限制（软件限帧：Panda3D 运行时不限帧时跑满） ---
        if config.MAX_FPS > 0:
            wait = (1.0 / config.MAX_FPS
                    - (py_time.perf_counter() - self._last_frame_time))
            if wait > 0:
                py_time.sleep(wait)
        self._last_frame_time = py_time.perf_counter()

        # --- 远裁剪面跟随视距：Ursina 默认 far=1000 对体素世界过远，会让深度
        # 缓冲精度不足，远处方块面互相 z-fighting 而闪烁。收紧到"视距 + 余量"
        # 即可；天空穹顶会按 far 自动缩放，不会被裁掉。 ---
        need_far = config.VIEW_DISTANCE + 48
        if getattr(self, '_cam_far', None) != need_far:
            camera.far = need_far
            self._cam_far = need_far

        # --- 任何 UI 页面打开或窗口最小化时都释放鼠标，否则锁回游戏 ---
        panda_window = application.base.win if application.base else None
        if panda_window is not None:
            minimized = bool(panda_window.getProperties().getMinimized())
            map_open = self.mapview is not None and self.mapview.is_open
            if minimized or self.ui.any_screen_open() or map_open:
                if mouse.locked:
                    mouse.locked = False
            elif (not mouse.locked and not minimized
                  and self.state == 'playing'):
                mouse.locked = True

        # --- 语言切换后刷新静态文本 ---
        if i18n.get_language() != self._language:
            self._language = i18n.get_language()
            if self.state == 'playing':
                self.notice = i18n.t('notice.help')
                self.notice_timer = 3.0
                self.mapview.retranslate()
            self.ui.retranslate()

        # --- 资源包切换：下载纹理并热重载材质（仅游戏内） ---
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

        # --- 鼠标 UI 坐标：所有页面共用一次 ---
        point = self.keyboard.pointer_ui_position()
        if point is None:
            point = (mouse.x, mouse.y)

        # --- 统一鼠标分发：点击被 UI 消费后，本帧不再处理其它输入 ---
        clicked = left_click or middle_click or right_click
        if clicked and self._dispatch_click(point, left_click, right_click):
            left_click = middle_click = right_click = False
            keys = set()
            just_pressed = set()

        # --- 聊天框/文本输入：回车提交，Esc 取消，打字时屏蔽游戏按键 ---
        if self.ui.text_input.is_open:
            if 'enter' in just_pressed:
                self.ui.text_input.submit()
            elif 'escape' in just_pressed:
                self.ui.text_input.cancel()
            else:
                if 'backspace' in just_pressed:
                    self.ui.text_input.backspace()
                chars = self.keyboard.char_events()
                if chars is None:              # 无物理后端：用事件层累积的字符
                    chars, self._pending_chars = self._pending_chars, ''
                if chars:
                    self.ui.text_input.type(''.join(chars))
            keys = set()
            just_pressed = set()
        elif (self.state == 'playing' and 'enter' in just_pressed
              and not self.ui.any_screen_open()
              and not self.mapview.is_open):
            self.ui.open_chat()
            self.keyboard.drain_chars()
            keys = set()
            just_pressed = set()
        self.ui.update_chat(raw_dt)

        # --- 非游戏状态：主页面/存档/创建玩家/设置 ---
        if self.state != 'playing':
            self._update_menus(just_pressed)
            return

        # --- F3：切换调试信息面板 ---
        if 'f3' in just_pressed:
            self.ui.toggle_debug()

        # --- M 全屏地图 / ESC 逐层返回 ---
        if 'm' in just_pressed and self.mapview.is_open:
            self.mapview.close()
        elif self.mapview.is_open and 'escape' in just_pressed:
            self.mapview.close()
        elif ('m' in just_pressed and not self.ui.menu_state['open']
              and not self.ui.inventory_open):
            self.mapview.toggle()
        elif 'escape' in just_pressed:
            if self.ui.rename_open:
                self.ui.cancel_rename()
            elif self.ui.rebind_action:
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
            if not self.ui.inventory_open:
                self.ui.hide_tooltip()

        # --- 背包打开：暂停移动；鼠标为主，键盘只做翻页与快捷栏选格 ---
        if self.ui.inventory_open:
            if 'page_up' in just_pressed or 'page_down' in just_pressed:
                self.ui.turn_inventory_page(
                    -1 if 'page_up' in just_pressed else 1)
            for i in range(config.HOTBAR_SLOTS):
                if str(i + 1) in just_pressed:
                    self.ui.selected_slot = i
                    self.ui.refresh_hotbar()
            # 鼠标点击已由 _dispatch_click 统一处理，这里只刷新光标状态
            self.ui.update_inventory_cursor(point)
            keys = set()
            just_pressed = set()

        # --- 数字键 / 滚轮切换快捷栏 ---
        if not self.ui.any_screen_open():
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
            # 选择框：按连续实体区间显示（两半砖组成整格时框住整格）
            run = self.world.solid_run(hx, hy, hz, hit_y)
            if run is not None:
                run_y0, run_y1 = run
                self.ui.selector.position = (hx + .5, (run_y0 + run_y1) / 2, hz + .5)
                self.ui.selector.scale = (1.004, max(0.004, run_y1 - run_y0), 1.004)

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
                block_id = self.ui.hotbar[self.ui.selected_slot]
                tx, ty, tz, layer = self._placement_target(
                    hx, hy, hz, normal, hit_y, segment, block_id)
                if (block_id is not None
                        and 0 <= tx < config.WORLD_SIZE and 0 <= tz < config.WORLD_SIZE
                        and config.MIN_BLOCK_Y <= ty < config.MAX_BLOCK_Y
                        and self.world.can_place(tx, ty, tz, layer, block_id)
                        and not self.player.overlaps(tx, ty, tz, block_id, layer)):
                    self.world.add_block(
                        tx, ty, tz, block_id, layer=layer,
                        states=self._placement_states(block_id, normal))
                    self.world.record_edit(tx, ty, tz)
                    self.world.rebuild_around(tx, tz)

        if self.ui.crosshair.enabled != active:
            self.ui.crosshair.enabled = active
        show_hotbar = (not self.ui.menu_state['open']
                       and not self.ui.inventory_open
                       and not self.mapview.is_open)
        if self.ui.hotbar_root.enabled != show_hotbar:
            self.ui.hotbar_root.enabled = show_hotbar
        # 地图打开时隐藏聊天记录
        if self.ui.chat_root.enabled == self.mapview.is_open:
            self.ui.chat_root.enabled = not self.mapview.is_open

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
            fps = int(self.hud_frames / self.hud_timer)
            # 左上角按窗口宽高比定位：小窗口时左半截也不会被裁到屏幕外
            self.ui.debug_root.x = -window.aspect_ratio / 2 + .02
            self.ui.debug_root.y = .47
            if self.ui.debug_open:
                flags = [i18n.t(key) for key, on in
                         (('hud.crouch', self.player.crouching),
                          ('hud.sprint', self.player.sprinting),
                          ('hud.zoom', self.player.zooming)) if on]
                block_id = self.ui.hotbar[self.ui.selected_slot]
                block_name = (i18n.block_name(
                    block_id, blocks.BLOCK_NAMES.get(block_id, 'Air'))
                    if block_id else 'Air')
                clock = int(self.day_time * 24 * 60) % (24 * 60)
                visible = sum(1 for entity in self.world.chunk_meshes.values()
                              if entity.enabled)
                save_name = (self.save_path.parent.name
                             if self.save_path else '-')
                self.ui.debug_text.text = '\n'.join((
                    i18n.t('debug.title'),
                    f'{i18n.t("debug.fps")}   {fps}',
                    f'{i18n.t("debug.pos")}   {self.player.pos.x:.1f} / '
                    f'{self.player.pos.y:.2f} / {self.player.pos.z:.1f}',
                    f'{i18n.t("debug.eye")}   {self.player.current_eye:.2f} m'
                    f'     {i18n.t("debug.time")}   {clock // 60:02d}:{clock % 60:02d}',
                    f'{i18n.t("debug.block")}   {block_name}',
                    f'{i18n.t("debug.state")}   '
                    f'{" ".join(flags) or i18n.t("debug.none")}',
                    f'{i18n.t("debug.chunks")}   {visible}/'
                    f'{len(self.world.chunk_meshes)}'
                    f'     {i18n.t("debug.edits")}   {len(self.world.world_edits)}',
                    f'{i18n.t("debug.save")}   {save_name}',
                ))
            # 常驻 HUD 只显示临时提示，不再堆一长串调试信息
            show_notice = (bool(self.notice) and not self.ui.any_screen_open()
                           and not self.mapview.is_open)
            self.ui.hud.enabled = show_notice
            if show_notice:
                self.ui.hud.text = self.notice
            self.hud_timer = 0.0
            self.hud_frames = 0
