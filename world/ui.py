"""游戏 UI：HUD、准心、快捷栏、背包、暂停菜单、设置面板与选中指示器。"""

from ursina import Button, Entity, Mesh, Text, camera, color, destroy, mouse, window

from . import config, i18n, keybinds, packs
from .blocks import BLOCK_IDS, BLOCK_NAMES, BLOCKS
from .storage import _save_number

if config.CJK_FONT:
    Text.default_font = config.CJK_FONT

# 菜单/设置按钮统一用较亮的颜色，默认按钮色太暗看不清
BUTTON_COLOR = color.rgba(.58, .62, .68, 1)
# 半透明遮罩在 z=-10，页面文字/按钮必须更靠前（UI 相机朝 +Z，z 越小越靠前）
UI_FRONT_Z = -20

SETTING_KEYS = (
    'language', 'resource_pack', 'auto_jump', 'auto_jump_height',
    'view_distance', 'fov', 'view_bob', 'brightness',
)
# key -> (最小值, 最大值, 步进, 小数位)
SETTING_SPECS = {
    'auto_jump_height': (0.5, 2.0, 0.1, 1),
    'view_distance': (16, 256, 8, 0),
    'fov': (20, 120, 5, 0),
    'view_bob': (0.0, 0.2, 0.01, 2),
    'brightness': (0.3, 2.0, 0.1, 1),
}


class GameUI:
    def __init__(self, save_data=None, materials=None, on_save=None, on_quit=None):
        self.on_save = on_save
        self.on_quit = on_quit
        self.materials = materials
        self.inventory_open = False
        self.held_item = None
        self.menu_state = {'open': False, 'index': 0}
        self.settings_open = False
        self.settings_index = 0
        self.packs_open = False
        self.packs_index = 0
        self.keys_open = False
        self.keys_index = 0
        self.rebind_action = None

        # 快捷栏 / 背包（创造模式：方块无限，只选择类型）
        self.hotbar = [BLOCK_IDS[i] if i < len(BLOCK_IDS) else None
                       for i in range(config.HOTBAR_SLOTS)]
        self.inventory = [BLOCK_IDS[i] if i < len(BLOCK_IDS) else None
                          for i in range(config.INVENTORY_COLS * config.INVENTORY_ROWS)]
        self.selected_slot = 0
        self.inv_selected = 0

        if save_data:
            saved_hotbar = save_data.get('hotbar')
            if isinstance(saved_hotbar, list):
                for i in range(config.HOTBAR_SLOTS):
                    if i < len(saved_hotbar):
                        item = saved_hotbar[i]
                        self.hotbar[i] = (item if isinstance(item, str) and item in BLOCKS
                                          else None)
                self.selected_slot = int(_save_number(
                    save_data.get('selected_slot'), 0, 0, config.HOTBAR_SLOTS - 1))

        self._build_hud()
        self._build_crosshair()
        self._build_hotbar()
        self._build_inventory()
        self._build_tooltip()
        self._build_menu()
        self._build_settings()
        self._build_packs()
        self._build_keybinds()
        self.selector = Entity(model='wireframe_cube', color=color.white,
                               scale=1.004, enabled=False)

        self.refresh_hotbar()
        self.refresh_inventory()
        self.refresh_settings()
        self.refresh_packs()
        self.refresh_keybinds()

    # ---------- 构建 ----------
    @staticmethod
    def _bring_to_front(root):
        """把页面里的文字/按钮（除第一块背景遮罩）放到遮罩前面。"""
        for child in list(root.children)[1:]:
            child.z = UI_FRONT_Z

    def _build_hud(self):
        self.hud = Text(text='', position=(-0.86, 0.47), origin=(-0.5, 0.5),
                        scale=0.75, background=True, z=-2)

    def _build_crosshair(self):
        self.crosshair = Entity(parent=camera.ui)
        Entity(parent=self.crosshair, model='quad', color=color.rgba(0, 0, 0, .6),
               scale=(.010, .030), z=-1)
        Entity(parent=self.crosshair, model='quad', color=color.white,
               scale=(.003, .024), z=-1.01)
        Entity(parent=self.crosshair, model='quad', color=color.white,
               scale=(.024, .003), z=-1.01)

    def _build_hotbar(self):
        self.hotbar_root = Entity(parent=camera.ui)
        self.hotbar_ui = []
        step = config.SLOT_SIZE + config.SLOT_GAP
        for i in range(config.HOTBAR_SLOTS):
            x = (i - (config.HOTBAR_SLOTS - 1) / 2) * step
            bg = Entity(parent=self.hotbar_root, model='quad', color=color.black66,
                        scale=(config.SLOT_SIZE, config.SLOT_SIZE), x=x, y=-.44, z=-1)
            items = self._make_slot_items(bg)
            Text(parent=bg, text=str(i + 1), origin=(-.5, -.5),
                 position=(-.44, -.44), scale=.45, z=-.2)
            self.hotbar_ui.append((bg, items))

    def _build_inventory(self):
        self.inventory_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.inventory_root, model='quad', color=color.black66,
               scale=(3, 2), z=-10)
        self.inventory_title = Text(parent=self.inventory_root, text=i18n.t('inventory.title'),
                                    origin=(0, 0), y=.34, scale=1.5, z=UI_FRONT_Z)
        self.inventory_hint = Text(parent=self.inventory_root, text=i18n.t('inventory.hint'),
                                   origin=(0, 0), y=-.35, scale=.6,
                                   color=color.gray, z=UI_FRONT_Z)

        self.inventory_ui = []
        step = config.SLOT_SIZE + config.SLOT_GAP
        for row in range(config.INVENTORY_ROWS):
            for col in range(config.INVENTORY_COLS):
                x = (col - (config.INVENTORY_COLS - 1) / 2) * step
                y = .12 - row * step
                bg = Entity(parent=self.inventory_root, model='quad',
                            color=color.black90, scale=(config.SLOT_SIZE, config.SLOT_SIZE),
                            x=x, y=y, z=-1)
                items = self._make_slot_items(bg)
                self.inventory_ui.append((bg, items))

        self.held_icons = self._make_held_icons()

    def _build_tooltip(self):
        """悬停物品信息提示：固定尺寸的深色底板 + 三行文字。"""
        self.tooltip_width = .42
        self.tooltip_height = .105
        # 必须比背包全屏遮罩（z=-10）更靠前，否则会被深度测试挡住
        self.tooltip_root = Entity(parent=camera.ui, enabled=False, z=-20)
        # UI 相机朝 +Z，z 越小越靠前：底板在后、文字在前
        Entity(parent=self.tooltip_root, model='quad',
               color=color.rgba(.05, .06, .08, .96),
               scale=(self.tooltip_width, self.tooltip_height),
               origin=(-.5, .5), z=.02)
        self.tooltip_text = Text(parent=self.tooltip_root, text='',
                                 origin=(-.5, .5), scale=.72,
                                 color=color.white, z=-.01)

    def _build_menu(self):
        self.menu_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.menu_root, model='quad', color=color.black66,
               scale=(3, 2), z=-10)
        self.menu_title = Text(parent=self.menu_root, text=i18n.t('menu.paused'),
                               origin=(0, 0), y=.32, scale=2)
        self.menu_status = Text(parent=self.menu_root, text='', origin=(0, 0),
                                y=-.34, scale=.8)
        self.menu_hint = Text(parent=self.menu_root, text=i18n.t('menu.hint'),
                              origin=(0, 0), y=-.44, scale=.5, color=color.gray)

        self.menu_labels = (i18n.t('menu.resume'), i18n.t('menu.settings'),
                            i18n.t('menu.packs'), i18n.t('menu.keybinds'),
                            i18n.t('menu.save'), i18n.t('menu.save_quit'))
        self.menu_buttons = [
            Button(parent=self.menu_root, text=label, scale=(.5, .065),
                   color=BUTTON_COLOR,
                   y=.13 - i * .085, on_click=action)
            for i, (label, action) in enumerate(zip(
                self.menu_labels,
                (self.close_menu, self.open_settings, self.open_packs,
                 self.open_keybinds, self._menu_save, self._menu_quit)))
        ]
        self.refresh_menu_highlight()
        self._bring_to_front(self.menu_root)

    def _build_settings(self):
        self.settings_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.settings_root, model='quad', color=color.black66,
               scale=(3, 2), z=-10)
        self.settings_title = Text(parent=self.settings_root, text=i18n.t('settings.title'),
                                   origin=(0, 0), y=.42, scale=1.5)

        self.settings_rows = []
        for i, key in enumerate(SETTING_KEYS):
            y = .28 - i * .07
            label = Text(parent=self.settings_root, text=i18n.t(f'settings.{key}'),
                         origin=(-.5, 0), x=-.7, y=y, scale=.75)
            Button(parent=self.settings_root, text='-', scale=(.055, .055),
                   x=.26, y=y, on_click=(lambda k=key: self.adjust_setting(k, -1)))
            value = Text(parent=self.settings_root, text='', origin=(0, 0),
                         x=.42, y=y, scale=.75)
            Button(parent=self.settings_root, text='+', scale=(.055, .055),
                   x=.60, y=y, on_click=(lambda k=key: self.adjust_setting(k, 1)))
            self.settings_rows.append((key, label, value))

        self.settings_hint = Text(parent=self.settings_root, text=i18n.t('settings.hint'),
                                  origin=(0, 0), y=-.3, scale=.5, color=color.gray)
        self.settings_back = Button(parent=self.settings_root, text=i18n.t('settings.back'),
                                    scale=(.5, .065), color=BUTTON_COLOR,
                                    y=-.42, on_click=self.close_settings)
        self._bring_to_front(self.settings_root)

    def _build_packs(self):
        """资源包配置页：列表、状态、应用/下载。"""
        self.packs_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.packs_root, model='quad', color=color.black66,
               scale=(3, 2), z=-10)
        self.packs_title = Text(parent=self.packs_root, text=i18n.t('packs.title'),
                                origin=(0, 0), y=.42, scale=1.5)
        self.packs_rows = []
        for i in range(8):
            y = .28 - i * .07
            label = Text(parent=self.packs_root, text='', origin=(-.5, 0),
                         x=-.7, y=y, scale=.75)
            value = Text(parent=self.packs_root, text='', origin=(0, 0),
                         x=.52, y=y, scale=.65)
            self.packs_rows.append((label, value))
        self.packs_status = Text(parent=self.packs_root, text='', origin=(0, 0),
                                 y=-.27, scale=.65, color=color.azure)
        self.packs_hint = Text(parent=self.packs_root, text=i18n.t('packs.hint'),
                               origin=(0, 0), y=-.33, scale=.5, color=color.gray)
        Button(parent=self.packs_root, text=i18n.t('packs.apply'),
               scale=(.28, .065), color=BUTTON_COLOR, x=-.35, y=-.42,
               on_click=self.apply_pack_selection)
        Button(parent=self.packs_root, text=i18n.t('packs.download'),
               scale=(.28, .065), color=BUTTON_COLOR, x=0, y=-.42,
               on_click=self.download_selected_pack)
        self.packs_back = Button(parent=self.packs_root, text=i18n.t('packs.back'),
                                 scale=(.28, .065), color=BUTTON_COLOR,
                                 x=.35, y=-.42, on_click=self.close_packs)
        self._bring_to_front(self.packs_root)

    def _build_keybinds(self):
        """按键绑定页：动作列表 + 重绑定/恢复默认。"""
        self.keys_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.keys_root, model='quad', color=color.black66,
               scale=(3, 2), z=-10)
        self.keys_title = Text(parent=self.keys_root, text=i18n.t('keybinds.title'),
                               origin=(0, 0), y=.42, scale=1.5)
        self.keys_rows = []
        for i, action in enumerate(keybinds.DEFAULT_BINDINGS):
            y = .30 - i * .045
            label = Text(parent=self.keys_root, text='', origin=(-.5, 0),
                         x=-.7, y=y, scale=.7)
            value = Text(parent=self.keys_root, text='', origin=(0, 0),
                         x=.5, y=y, scale=.7)
            self.keys_rows.append((action, label, value))
        self.keys_status = Text(parent=self.keys_root, text='', origin=(0, 0),
                                y=-.27, scale=.65, color=color.azure)
        self.keys_hint = Text(parent=self.keys_root, text=i18n.t('keybinds.hint'),
                              origin=(0, 0), y=-.33, scale=.5, color=color.gray)
        Button(parent=self.keys_root, text=i18n.t('keybinds.rebind'),
               scale=(.28, .065), color=BUTTON_COLOR, x=-.35, y=-.42,
               on_click=self.start_rebind)
        Button(parent=self.keys_root, text=i18n.t('keybinds.reset'),
               scale=(.28, .065), color=BUTTON_COLOR, x=0, y=-.42,
               on_click=self.reset_keybinds)
        self.keys_back = Button(parent=self.keys_root, text=i18n.t('keybinds.back'),
                                scale=(.28, .065), color=BUTTON_COLOR,
                                x=.35, y=-.42, on_click=self.close_keybinds)
        self._bring_to_front(self.keys_root)

    # ---------- 刷新 ----------
    @staticmethod
    def _clone_mesh(mesh):
        """Ursina 的 Mesh 是 NodePath：多个 Entity 共用同一实例会被反复
        reparentTo，最后只有最后创建的那个图标真正挂住网格。每个图标克隆一份。"""
        return Mesh(vertices=mesh.vertices, triangles=mesh.triangles,
                    uvs=mesh.uvs, colors=mesh.colors, mode=mesh.mode)

    def _make_slot_items(self, bg):
        """在一个格子里生成所有方块的 3D 图标（按 block_id 索引，默认隐藏）。"""
        items = {}
        if self.materials:
            for block_id, mesh in self.materials.item_meshes.items():
                icon = Entity(
                    parent=bg, model=self._clone_mesh(mesh),
                    texture=self.materials.texture,
                    scale=(.85, .85, .85), z=-.1, enabled=False)
                icon.set_two_sided(True)   # 顶/左面绕序相反，避免被背面剔除
                items[block_id] = icon
        return items

    def _make_held_icons(self):
        """背包里跟随鼠标的手持图标。"""
        icons = {}
        if self.materials:
            for block_id, mesh in self.materials.item_meshes.items():
                icon = Entity(
                    parent=camera.ui, model=self._clone_mesh(mesh),
                    texture=self.materials.texture,
                    scale=(config.SLOT_SIZE * .85, config.SLOT_SIZE * .85,
                           config.SLOT_SIZE * .85),
                    enabled=False, z=-18)
                icon.set_two_sided(True)
                icons[block_id] = icon
        return icons

    def apply_materials(self, materials):
        """资源包切换后：重建快捷栏/背包/手持图标并刷新显示。"""
        self.materials = materials
        for slots in (self.hotbar_ui, self.inventory_ui):
            for bg, items in slots:
                for icon in items.values():
                    destroy(icon)
                items.clear()
                items.update(self._make_slot_items(bg))
        for icon in self.held_icons.values():
            destroy(icon)
        self.held_icons = self._make_held_icons()
        self.refresh_hotbar()
        self.refresh_inventory()

    def slot_color(self, block_id):
        r, g, b = BLOCKS[block_id]['color']
        return color.rgba(r / 255, g / 255, b / 255, 1)

    def refresh_hotbar(self):
        for i, (bg, items) in enumerate(self.hotbar_ui):
            block_id = self.hotbar[i]
            for item_id, icon in items.items():
                icon.enabled = (item_id == block_id)
            bg.color = (color.rgba(1, 1, 1, .35) if i == self.selected_slot
                        else color.black66)

    def refresh_inventory(self):
        for i, (bg, items) in enumerate(self.inventory_ui):
            block_id = self.inventory[i]
            for item_id, icon in items.items():
                icon.enabled = (item_id == block_id)
            bg.color = (color.rgba(1, 1, 1, .35) if i == self.inv_selected
                        else color.black90)

    def refresh_menu_highlight(self):
        for i, button in enumerate(self.menu_buttons):
            button.text = (f'> {self.menu_labels[i]} <'
                           if i == self.menu_state['index']
                           else f'  {self.menu_labels[i]}  ')

    def refresh_settings(self):
        for i, (key, label, value) in enumerate(self.settings_rows):
            label.text = i18n.t(f'settings.{key}')
            value.text = self.setting_display(key)
            highlighted = (i == self.settings_index)
            label.color = color.azure if highlighted else color.white
            value.color = label.color

    # ---------- 资源包配置页 ----------
    @staticmethod
    def pack_options():
        """[(id, 显示名)]；'' 表示默认世界（噪声材质）。"""
        return ([('', i18n.pack_name(packs.DEFAULT_PACK_ID))]
                + [(pid, i18n.pack_name(pid))
                   for pid, _ in packs.available_packs() if pid])

    @staticmethod
    def pack_status(pack_id):
        if not pack_id:
            return i18n.t('packs.builtin')
        folder = config.ROOT_DIR / 'assets' / pack_id / 'blocks'
        count = len(tuple(folder.glob('*.png'))) if folder.is_dir() else 0
        return (i18n.t('packs.ready').format(count=count)
                if count else i18n.t('packs.missing'))

    def refresh_packs(self):
        options = self.pack_options()
        self.packs_index = min(self.packs_index, max(0, len(options) - 1))
        active = config.SETTINGS.get('resource_pack') or ''
        for i, (label, value) in enumerate(self.packs_rows):
            if i < len(options):
                pack_id, name = options[i]
                label.text = f'> {name} <' if i == self.packs_index else f'  {name}  '
                label.enabled = True
                value.enabled = True
                marker = i18n.t('packs.active') if pack_id == active else ''
                value.text = f'{self.pack_status(pack_id)}  {marker}'.strip()
            else:
                label.enabled = False
                value.enabled = False
            label.color = color.azure if i == self.packs_index else color.white
            value.color = label.color

    def apply_pack_selection(self):
        options = self.pack_options()
        if not options:
            return
        pack_id = options[self.packs_index][0]
        config.apply_settings({'resource_pack': pack_id})
        self.packs_status.text = i18n.t('packs.applied')
        self.refresh_packs()

    def download_selected_pack(self):
        options = self.pack_options()
        if not options:
            return
        pack_id = options[self.packs_index][0]
        if not pack_id:
            self.packs_status.text = i18n.t('packs.ready').format(count=0)
            return
        ok = packs.ensure_pack(pack_id)
        self.packs_status.text = i18n.t('packs.downloaded' if ok else 'packs.failed')
        self.refresh_packs()

    # ---------- 按键绑定页 ----------
    def refresh_keybinds(self):
        actions = list(keybinds.DEFAULT_BINDINGS)
        self.keys_index %= len(actions)
        for i, (action, label, value) in enumerate(self.keys_rows):
            name = i18n.t(f'key.{action}')
            label.text = f'> {name} <' if i == self.keys_index else f'  {name}  '
            value.text = (i18n.t('keybinds.press') if action == self.rebind_action
                          else keybinds.display(keybinds.BINDINGS[action]))
            tint = color.azure if i == self.keys_index else color.white
            label.color = tint
            value.color = tint

    def start_rebind(self):
        self.rebind_action = list(keybinds.DEFAULT_BINDINGS)[self.keys_index]
        self.keys_status.text = i18n.t('keybinds.press')
        self.refresh_keybinds()

    def finish_rebind(self, key):
        if not self.rebind_action:
            return
        action = self.rebind_action
        self.rebind_action = None
        if keybinds.set_binding(action, key):
            self.keys_status.text = i18n.t('keybinds.done').format(
                key=keybinds.display(key))
        else:
            self.keys_status.text = i18n.t('keybinds.failed')
        self.refresh_keybinds()

    def cancel_rebind(self):
        self.rebind_action = None
        self.keys_status.text = i18n.t('keybinds.cancel')
        self.refresh_keybinds()

    def reset_keybinds(self):
        keybinds.reset()
        self.rebind_action = None
        self.keys_status.text = i18n.t('keybinds.reset_done')
        self.refresh_keybinds()

    def setting_display(self, key):
        value = config.SETTINGS.get(key)
        if key == 'language':
            return i18n.t('language.name')
        if key == 'resource_pack':
            return i18n.pack_name(value or packs.DEFAULT_PACK_ID)
        if key == 'auto_jump':
            return i18n.t('settings.on' if value else 'settings.off')
        if key == 'auto_jump_height':
            return f'{value:.1f}'
        if key == 'view_bob':
            return f'{value:.2f}'
        if key == 'brightness':
            return f'{value:.1f}'
        return f'{value:g}'

    def adjust_setting(self, key, delta):
        """调整一项设置并立即生效、写回 setting.json。"""
        if key == 'language':
            languages = ('zh', 'en')
            current = config.SETTINGS.get('language', 'zh')
            index = (languages.index(current) + delta) % len(languages)
            self.set_language(languages[index])
            return
        if key == 'resource_pack':
            options = [''] + [pid for pid, _ in packs.available_packs() if pid]
            current = config.SETTINGS.get('resource_pack', '')
            index = options.index(current) if current in options else 0
            config.apply_settings(
                {'resource_pack': options[(index + delta) % len(options)]})
            self.refresh_settings()
            return
        if key == 'auto_jump':
            config.apply_settings(
                {'auto_jump': not config.SETTINGS.get('auto_jump', True)})
        else:
            low, high, step, decimals = SETTING_SPECS[key]
            value = config.SETTINGS.get(key, low) + delta * step
            value = round(max(low, min(high, value)), decimals)
            if decimals == 0:
                value = int(value)
            config.apply_settings({key: value})
        self.refresh_settings()

    def set_language(self, language):
        i18n.set_language(language)
        config.apply_settings({'language': language})
        self.retranslate()

    def retranslate(self):
        """语言切换后刷新所有静态文本。"""
        self.menu_title.text = i18n.t('menu.paused')
        self.menu_hint.text = i18n.t('menu.hint')
        self.menu_labels = (i18n.t('menu.resume'), i18n.t('menu.settings'),
                            i18n.t('menu.packs'), i18n.t('menu.keybinds'),
                            i18n.t('menu.save'), i18n.t('menu.save_quit'))
        for button, label in zip(self.menu_buttons, self.menu_labels):
            button.text = label
        self.refresh_menu_highlight()
        self.menu_status.text = ''

        self.packs_title.text = i18n.t('packs.title')
        self.packs_hint.text = i18n.t('packs.hint')
        self.packs_back.text = i18n.t('packs.back')
        self.packs_status.text = ''
        self.refresh_packs()

        self.keys_title.text = i18n.t('keybinds.title')
        self.keys_hint.text = i18n.t('keybinds.hint')
        self.keys_back.text = i18n.t('keybinds.back')
        self.keys_status.text = ''
        self.refresh_keybinds()

        self.inventory_title.text = i18n.t('inventory.title')
        self.inventory_hint.text = i18n.t('inventory.hint')

        self.settings_title.text = i18n.t('settings.title')
        self.settings_hint.text = i18n.t('settings.hint')
        self.settings_back.text = i18n.t('settings.back')
        self.refresh_settings()

    # ---------- 格子命中 ----------
    @staticmethod
    def slot_index_at(px, py, cols, rows, center_y):
        """判断 UI 坐标落在哪个格子上；返回格子索引，未命中返回 None。"""
        step = config.SLOT_SIZE + config.SLOT_GAP
        half = config.SLOT_SIZE / 2
        col = round(px / step + (cols - 1) / 2)
        row = round((center_y - py) / step)
        if not (0 <= col < cols and 0 <= row < rows):
            return None
        slot_x = (col - (cols - 1) / 2) * step
        slot_y = center_y - row * step
        if abs(px - slot_x) <= half and abs(py - slot_y) <= half:
            return row * cols + col
        return None

    def hovered_slot(self, point):
        """返回鼠标悬停的 ('inventory'|'hotbar', 索引)；没命中返回 None。"""
        if point is None:
            return None
        px, py = point
        inv_idx = self.slot_index_at(px, py, config.INVENTORY_COLS,
                                     config.INVENTORY_ROWS, .12)
        if inv_idx is not None:
            return ('inventory', inv_idx)
        hot_idx = self.slot_index_at(px, py, config.HOTBAR_SLOTS, 1, -.44)
        if hot_idx is not None:
            return ('hotbar', hot_idx)
        return None

    @staticmethod
    def item_info(block_id):
        """物品悬浮信息：名称 / ID / 颜色。"""
        if block_id is None:
            return ''
        name = i18n.block_name(block_id, BLOCK_NAMES.get(block_id, str(block_id)))
        r, g, b = BLOCKS.get(block_id, {}).get('color', (0, 0, 0))
        return f'{name}\n{block_id}\n{i18n.t("tooltip.color")} {r},{g},{b}'

    def update_tooltip(self, point):
        """背包打开时按鼠标位置刷新悬浮提示。"""
        if not self.inventory_open or point is None:
            self.hide_tooltip()
            return
        slot = self.hovered_slot(point)
        items = (self.inventory if slot and slot[0] == 'inventory' else self.hotbar)
        block_id = items[slot[1]] if slot else None
        if block_id is None and self.held_item is not None:
            block_id = self.held_item
        if block_id is None:
            self.hide_tooltip()
            return
        text = self.item_info(block_id)
        if self.tooltip_text.text != text:
            self.tooltip_text.text = text
        half_w = window.aspect_ratio / 2
        px = max(-half_w + .01,
                 min(half_w - self.tooltip_width - .01, point[0] + .032))
        py = max(-.5 + self.tooltip_height + .01,
                 min(.5 - .01, point[1] - .032))
        self.tooltip_root.position = (px, py, -20)
        self.tooltip_root.enabled = True

    def hide_tooltip(self):
        self.tooltip_root.enabled = False

    # ---------- 开关 ----------
    def open_inventory(self):
        self.inventory_open = True
        self.inventory_root.enabled = True
        self.refresh_inventory()
        mouse.locked = False

    def close_inventory(self):
        if self.held_item is not None:      # 关背包时把手上物品放回空位，避免丢失
            for i in range(len(self.inventory)):
                if self.inventory[i] is None:
                    self.inventory[i] = self.held_item
                    break
            self.held_item = None
            for icon in self.held_icons.values():
                icon.enabled = False
        self.inventory_open = False
        self.inventory_root.enabled = False
        self.hide_tooltip()
        self.refresh_inventory()
        mouse.locked = True

    def open_menu(self):
        if self.inventory_open:             # 菜单优先，先收起背包（顺手回收手上物品）
            self.close_inventory()
        self.settings_open = False
        self.settings_root.enabled = False
        self.packs_open = False
        self.packs_root.enabled = False
        self.keys_open = False
        self.keys_root.enabled = False
        self.rebind_action = None
        self.menu_state['open'] = True
        self.menu_state['index'] = 0
        self.menu_status.text = ''
        self.menu_root.enabled = True
        self.refresh_menu_highlight()
        mouse.locked = False

    def close_menu(self):
        self.settings_open = False
        self.settings_root.enabled = False
        self.packs_open = False
        self.packs_root.enabled = False
        self.keys_open = False
        self.keys_root.enabled = False
        self.rebind_action = None
        self.menu_state['open'] = False
        self.menu_root.enabled = False
        mouse.locked = True

    def open_settings(self):
        self.settings_open = True
        self.settings_index = 0
        self.menu_root.enabled = False
        self.settings_root.enabled = True
        self.refresh_settings()
        mouse.locked = False

    def close_settings(self):
        self.settings_open = False
        self.settings_root.enabled = False
        self.menu_root.enabled = True
        self.refresh_menu_highlight()
        mouse.locked = False

    def open_packs(self):
        self.packs_open = True
        self.packs_root.enabled = True
        self.settings_root.enabled = False
        self.menu_root.enabled = False
        self.settings_open = False
        self.packs_status.text = ''
        self.refresh_packs()
        mouse.locked = False

    def close_packs(self):
        self.packs_open = False
        self.packs_root.enabled = False
        self.menu_root.enabled = True
        self.refresh_menu_highlight()
        mouse.locked = False

    def open_keybinds(self):
        self.keys_open = True
        self.keys_root.enabled = True
        self.packs_root.enabled = False
        self.menu_root.enabled = False
        self.packs_open = False
        self.rebind_action = None
        self.keys_status.text = ''
        self.refresh_keybinds()
        mouse.locked = False

    def close_keybinds(self):
        self.keys_open = False
        self.keys_root.enabled = False
        self.menu_root.enabled = True
        self.rebind_action = None
        self.refresh_menu_highlight()
        mouse.locked = False

    def _menu_save(self):
        saved = bool(self.on_save and self.on_save())
        self.menu_status.text = i18n.t('notice.saved' if saved else 'notice.save_failed')

    def _menu_quit(self):
        if self.on_quit:
            self.on_quit()

    # ---------- 背包鼠标拖拽 / 替换 ----------
    def handle_inventory_click(self, point, left_click, right_click=False):
        slot = self.hovered_slot(point)
        if slot and (left_click or right_click):
            which, idx = slot
            items = self.inventory if which == 'inventory' else self.hotbar
            item = items[idx]
            if left_click:
                if self.held_item is None:
                    if item is not None:
                        self.held_item = item
                        items[idx] = None
                else:
                    items[idx] = self.held_item
                    self.held_item = item
                if which == 'hotbar':
                    self.selected_slot = idx
            else:
                # 右键：空手时复制该格物品；手上有物品时替换该格（手上保留，可连续替换）
                if self.held_item is None:
                    if item is not None:
                        self.held_item = item
                else:
                    items[idx] = self.held_item
                    if which == 'hotbar':
                        self.selected_slot = idx
            if which == 'inventory':
                self.refresh_inventory()
            else:
                self.refresh_hotbar()

        # 手上的方块跟随鼠标
        for block_id, icon in self.held_icons.items():
            icon.enabled = (block_id == self.held_item and point is not None)
            if icon.enabled:
                icon.position = (point[0], point[1], -18)
