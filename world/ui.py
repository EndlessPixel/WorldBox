"""游戏 UI：HUD、准心、快捷栏、背包、暂停菜单、设置面板与选中指示器。"""

from ursina import Button, Entity, Text, camera, color, mouse

from . import config, i18n
from .blocks import BLOCK_IDS, BLOCKS
from .storage import _save_number

if config.CJK_FONT:
    Text.default_font = config.CJK_FONT

SETTING_KEYS = (
    'language', 'auto_jump', 'auto_jump_height',
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
    def __init__(self, save_data=None, on_save=None, on_quit=None):
        self.on_save = on_save
        self.on_quit = on_quit
        self.inventory_open = False
        self.held_item = None
        self.menu_state = {'open': False, 'index': 0}
        self.settings_open = False
        self.settings_index = 0

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
        self._build_menu()
        self._build_settings()
        self.selector = Entity(model='wireframe_cube', color=color.white,
                               scale=1.004, enabled=False)

        self.refresh_hotbar()
        self.refresh_inventory()
        self.refresh_settings()

    # ---------- 构建 ----------
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
            item = Entity(parent=bg, model='quad', color=color.white,
                          scale=(.72, .72), z=-.01)
            Text(parent=bg, text=str(i + 1), origin=(-.5, -.5),
                 position=(-.44, -.44), scale=.45, z=-.02)
            self.hotbar_ui.append((bg, item))

    def _build_inventory(self):
        self.inventory_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.inventory_root, model='quad', color=color.black66,
               scale=(3, 2), z=0)
        self.inventory_title = Text(parent=self.inventory_root, text=i18n.t('inventory.title'),
                                    origin=(0, 0), y=.34, scale=1.5, z=-.02)
        self.inventory_hint = Text(parent=self.inventory_root, text=i18n.t('inventory.hint'),
                                   origin=(0, 0), y=-.35, scale=.6,
                                   color=color.gray, z=-.02)

        self.inventory_ui = []
        step = config.SLOT_SIZE + config.SLOT_GAP
        for row in range(config.INVENTORY_ROWS):
            for col in range(config.INVENTORY_COLS):
                x = (col - (config.INVENTORY_COLS - 1) / 2) * step
                y = .12 - row * step
                bg = Entity(parent=self.inventory_root, model='quad',
                            color=color.black90, scale=(config.SLOT_SIZE, config.SLOT_SIZE),
                            x=x, y=y, z=-1)
                item = Entity(parent=bg, model='quad', color=color.white,
                              scale=(.72, .72), z=-.01)
                self.inventory_ui.append((bg, item))

        self.held_icon = Entity(parent=camera.ui, model='quad', color=color.white,
                                scale=(config.SLOT_SIZE * .72, config.SLOT_SIZE * .72),
                                enabled=False, z=-3)

    def _build_menu(self):
        self.menu_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.menu_root, model='quad', color=color.black66, scale=(3, 2))
        self.menu_title = Text(parent=self.menu_root, text=i18n.t('menu.paused'),
                               origin=(0, 0), y=.32, scale=2)
        self.menu_status = Text(parent=self.menu_root, text='', origin=(0, 0),
                                y=-.34, scale=.8)
        self.menu_hint = Text(parent=self.menu_root, text=i18n.t('menu.hint'),
                              origin=(0, 0), y=-.44, scale=.5, color=color.gray)

        self.menu_labels = (i18n.t('menu.resume'), i18n.t('menu.settings'),
                            i18n.t('menu.save'), i18n.t('menu.save_quit'))
        self.menu_buttons = [
            Button(parent=self.menu_root, text=label, scale=(.5, .065),
                   y=.10 - i * .1, on_click=action)
            for i, (label, action) in enumerate(zip(
                self.menu_labels,
                (self.close_menu, self.open_settings, self._menu_save, self._menu_quit)))
        ]
        self.refresh_menu_highlight()

    def _build_settings(self):
        self.settings_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.settings_root, model='quad', color=color.black66, scale=(3, 2))
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
                                    scale=(.5, .065), y=-.42, on_click=self.close_settings)

    # ---------- 刷新 ----------
    def slot_color(self, block_id):
        r, g, b = BLOCKS[block_id]['color']
        return color.rgba(r / 255, g / 255, b / 255, 1)

    def refresh_hotbar(self):
        for i, (bg, item) in enumerate(self.hotbar_ui):
            block_id = self.hotbar[i]
            item.enabled = block_id is not None
            if block_id is not None:
                item.color = self.slot_color(block_id)
            bg.color = color.white if i == self.selected_slot else color.black66

    def refresh_inventory(self):
        for i, (bg, item) in enumerate(self.inventory_ui):
            block_id = self.inventory[i]
            item.enabled = block_id is not None
            if block_id is not None:
                item.color = self.slot_color(block_id)
            bg.color = color.white if i == self.inv_selected else color.black90

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

    def setting_display(self, key):
        value = config.SETTINGS.get(key)
        if key == 'language':
            return i18n.t('language.name')
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
                            i18n.t('menu.save'), i18n.t('menu.save_quit'))
        for button, label in zip(self.menu_buttons, self.menu_labels):
            button.text = label
        self.refresh_menu_highlight()
        self.menu_status.text = ''

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
            self.held_icon.enabled = False
        self.inventory_open = False
        self.inventory_root.enabled = False
        self.refresh_inventory()
        mouse.locked = True

    def open_menu(self):
        if self.inventory_open:             # 菜单优先，先收起背包（顺手回收手上物品）
            self.close_inventory()
        self.settings_open = False
        self.settings_root.enabled = False
        self.menu_state['open'] = True
        self.menu_state['index'] = 0
        self.menu_status.text = ''
        self.menu_root.enabled = True
        self.refresh_menu_highlight()
        mouse.locked = False

    def close_menu(self):
        self.settings_open = False
        self.settings_root.enabled = False
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

    def _menu_save(self):
        saved = bool(self.on_save and self.on_save())
        self.menu_status.text = i18n.t('notice.saved' if saved else 'notice.save_failed')

    def _menu_quit(self):
        if self.on_quit:
            self.on_quit()

    # ---------- 背包鼠标拖拽 ----------
    def handle_inventory_click(self, point, left_click):
        if left_click and point is not None:
            px, py = point
            inv_idx = self.slot_index_at(px, py, config.INVENTORY_COLS,
                                         config.INVENTORY_ROWS, .12)
            hot_idx = self.slot_index_at(px, py, config.HOTBAR_SLOTS, 1, -.44)
            if inv_idx is not None:
                item = self.inventory[inv_idx]
                if self.held_item is None:
                    if item is not None:
                        self.held_item = item
                        self.inventory[inv_idx] = None
                else:
                    self.inventory[inv_idx] = self.held_item
                    self.held_item = item
                self.refresh_inventory()
            elif hot_idx is not None:
                item = self.hotbar[hot_idx]
                if self.held_item is not None:
                    self.hotbar[hot_idx] = self.held_item
                    self.held_item = item
                    self.selected_slot = hot_idx
                else:
                    self.selected_slot = hot_idx
                self.refresh_hotbar()

        # 手上的方块跟随鼠标
        if self.held_item is not None and point is not None:
            self.held_icon.position = (point[0], point[1], -3)
            self.held_icon.color = self.slot_color(self.held_item)
            self.held_icon.enabled = True
        else:
            self.held_icon.enabled = False
