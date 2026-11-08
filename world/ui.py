"""游戏 UI：HUD、准心、快捷栏、背包、暂停菜单、设置面板与选中指示器。"""

import time as py_time

from ursina import (Button, Entity, Mesh, Text, application, camera, color,
                    destroy, mouse, window)

from . import config, i18n, keybinds, packs, saves
from .blocks import BLOCK_IDS, BLOCK_NAMES, BLOCKS
from .storage import _save_number

if config.CJK_FONT:
    Text.default_font = config.CJK_FONT

# 菜单/设置按钮统一用较亮的颜色，默认按钮色太暗看不清
BUTTON_COLOR = color.rgba(.58, .62, .68, 1)
# 半透明遮罩在 z=-10，页面文字/按钮必须更靠前（UI 相机朝 +Z，z 越小越靠前）
UI_FRONT_Z = -20
# 存档列表最多显示几行
SAVES_MAX_ROWS = 8
# 聊天框布局（UI 坐标：x∈±0.8, y∈±0.5）
CHAT_X = -.78            # 左侧起点
CHAT_WIDTH = 1.2         # 蒙版宽度
CHAT_INPUT_Y = .375      # 输入行距屏幕底部的偏移
CHAT_LINE_STEP = .042    # 每条消息的行距
CHAT_MAX_LINES = 8       # 最多保留几条
CHAT_LIFE = 10.0         # 消息存活秒数（最后 1.5 秒淡出）
CHAT_MAX_INPUT = 100     # 输入长度上限


class TextInput:
    """单行文本输入框：聊天、创建玩家、新存档名共用。

    字符来自 PhysicalKeys 物理轮询（不依赖 Ursina 事件层），
    回车提交、Esc 取消，光标每 0.5 秒闪烁。
    """

    def __init__(self):
        self.root = Entity(parent=camera.ui, enabled=False)
        self.bg = Entity(parent=self.root, model='quad',
                         color=color.rgba(0, 0, 0, .55),
                         scale=(CHAT_WIDTH, .042), origin=(-.5, .5),
                         x=CHAT_X, y=-CHAT_INPUT_Y, z=-1)
        self.label = Text(parent=self.root, text='', origin=(-.5, .5),
                          x=CHAT_X + .008, y=-CHAT_INPUT_Y + .007,
                          scale=.55, z=-2)
        self.text = ''
        self.prompt = ''
        self.max_len = CHAT_MAX_INPUT
        self.on_submit = None
        self.on_cancel = None
        self.cursor_on = True
        self.cursor_timer = 0.0

    @property
    def is_open(self):
        return self.root.enabled

    def open(self, prompt='', on_submit=None, position=None, width=None,
             max_len=CHAT_MAX_INPUT, text='', on_cancel=None):
        """打开输入框；position=(y, x) 指定输入行位置。"""
        self.prompt = prompt
        self.on_submit = on_submit
        self.on_cancel = on_cancel
        self.text = text[:max_len]
        self.max_len = max_len
        if position is not None:
            y, x = position
            self.bg.y = -y
            self.bg.x = x
            self.label.y = -y + .007
            self.label.x = x + .008
        if width is not None:
            self.bg.scale = (width, .042)
        self.cursor_on = True
        self.cursor_timer = 0.0
        self.root.enabled = True
        self._refresh()

    def close(self):
        self.root.enabled = False
        self.on_submit = None
        self.on_cancel = None

    def type(self, chars):
        """输入字符（有长度上限）。"""
        if not self.is_open or not chars:
            return
        self.text = (self.text + chars)[:self.max_len]
        self.cursor_on = True
        self.cursor_timer = 0.0
        self._refresh()

    def backspace(self):
        if self.is_open and self.text:
            self.text = self.text[:-1]
            self._refresh()

    def submit(self):
        """回车：回调并关闭；没有回调时仅关闭。"""
        callback, text = self.on_submit, self.text.strip()
        self.close()
        if callback:
            callback(text)

    def cancel(self):
        """Esc：取消回调并关闭。"""
        callback = self.on_cancel
        self.close()
        if callback:
            callback()

    def update(self, dt):
        """光标闪烁。"""
        if not self.is_open:
            return
        self.cursor_timer += dt
        if self.cursor_timer >= .5:
            self.cursor_timer = 0.0
            self.cursor_on = not self.cursor_on
            self._refresh()

    def _refresh(self):
        self.label.text = f'{self.prompt}{self.text}' + (
            '|' if self.cursor_on else ' ')

SETTING_KEYS = (
    'language', 'resource_pack', 'auto_jump', 'auto_jump_height',
    'view_distance', 'fov', 'view_bob', 'brightness', 'max_fps', 'vsync',
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
        self.on_play_save = lambda path: None      # 由 Game 设置：进入存档
        self.on_player_created = lambda: None      # 由 Game 设置：玩家创建完成
        self.on_quit_to_title = lambda: None       # 由 Game 设置：退出到主页面
        self.notice_callback = None   # 由 Game 设置：显示一次性提示
        self.materials = materials
        self.inventory_open = False
        self.held_item = None
        self.held_from = None      # 手上物品来自哪个快捷栏格（关闭时放回）
        self.menu_state = {'open': False, 'index': 0}
        self.settings_open = False
        self.settings_index = 0
        self.packs_open = False
        self.packs_index = 0
        self.keys_open = False
        self.keys_index = 0
        self.rebind_action = None

        # 快捷栏：玩家可改动；创造背包：固定展示全部方块，只读
        self.hotbar = [BLOCK_IDS[i] if i < len(BLOCK_IDS) else None
                       for i in range(config.HOTBAR_SLOTS)]
        self.inventory = list(BLOCK_IDS)
        self.inv_page = 0
        self.selected_slot = 0
        self.inv_selected = 0
        self.load_hotbar(save_data)

        self._build_hud()
        self._build_crosshair()
        self._build_chat()
        self._build_hotbar()
        self._build_inventory()
        self._build_tooltip()
        self._build_menu()
        self._build_settings()
        self._build_packs()
        self._build_keybinds()
        self._build_title()
        self._build_saves()
        self._build_new_save()
        self._build_player()
        self.selector = Entity(model='wireframe_cube', color=color.white,
                               scale=1.004, enabled=False)

        # 主页面 / 存档列表状态
        self.title_index = 0
        self.saves_index = 0
        self.save_entries = []          # saves.list_saves() 的结果
        self.settings_from_title = False
        self.screen = 'title'           # 当前页面：title/saves/new_save/player

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

    # ---------- 聊天 ----------
    def _build_chat(self):
        """聊天框：左下角消息记录（半透明黑底）+ 复用 TextInput 输入行。"""
        self.player_name = 'Player'
        self.chat_messages = []          # [(root, text, 创建时间)]
        self.chat_root = Entity(parent=camera.ui)
        self.text_input = TextInput()

    def add_chat_message(self, text):
        """在左下角添加一条聊天消息（自动堆叠、超时淡出）。"""
        if not text:
            return
        root = Entity(parent=self.chat_root)
        Entity(parent=root, model='quad', color=color.rgba(0, 0, 0, .5),
               scale=(CHAT_WIDTH, .038), origin=(-.5, .5),
               x=CHAT_X, y=0, z=-1)
        label = Text(parent=root, text=text, origin=(-.5, .5),
                     x=CHAT_X + .008, y=-.008, scale=.52, z=-2)
        self.chat_messages.append((root, label, py_time.perf_counter()))
        while len(self.chat_messages) > CHAT_MAX_LINES:
            old_root, _old_label, _ = self.chat_messages.pop(0)
            destroy(old_root)
        self._restack_chat()

    def _restack_chat(self):
        """把消息从输入行上方依次往上排。"""
        for i, (root, label, _born) in enumerate(self.chat_messages):
            root.y = -.33 + (len(self.chat_messages) - 1 - i) * CHAT_LINE_STEP
            label.y = -.008

    def update_chat(self, dt):
        """输入框光标闪烁 + 消息超时淡出移除。"""
        self.text_input.update(dt)
        if not self.chat_messages:
            return
        now = py_time.perf_counter()
        expired = False
        for message in list(self.chat_messages):
            age = now - message[2]
            if age > CHAT_LIFE:
                destroy(message[0])
                self.chat_messages.remove(message)
                expired = True
            elif age > CHAT_LIFE - 1.5:
                # 最后 1.5 秒淡出
                fade = max(0.0, (CHAT_LIFE - age) / 1.5)
                message[1].color = color.rgba(1, 1, 1, fade)
                message[0].children[0].color = color.rgba(0, 0, 0, .5 * fade)
        if expired:
            self._restack_chat()

    def open_chat(self):
        self.text_input.open(prompt='> ', on_submit=self.submit_chat,
                             position=(-CHAT_INPUT_Y, CHAT_X),
                             width=CHAT_WIDTH, max_len=CHAT_MAX_INPUT)

    def submit_chat(self, text=''):
        """发送消息（TextInput 的回调）。

        注意：Ursina 的 Text 把以 < 开头的字符串当富文本标签，
        所以前缀用方括号，不能用 <名字>。
        """
        text = (text if text is not None else self.text_input.text).strip()
        if text:
            self.add_chat_message(f'[{self.player_name}] {text}')

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

        # 翻页控件
        self.inv_page_text = Text(parent=self.inventory_root, text='',
                                  origin=(0, 0), y=-.30, scale=.62,
                                  color=color.gray, z=UI_FRONT_Z)
        Button(parent=self.inventory_root, text=i18n.t('inventory.prev'),
               scale=(.22, .055), color=BUTTON_COLOR,
               x=-.42, y=-.38, on_click=lambda: self.turn_inventory_page(-1))
        Button(parent=self.inventory_root, text=i18n.t('inventory.next'),
               scale=(.22, .055), color=BUTTON_COLOR,
               x=.42, y=-.38, on_click=lambda: self.turn_inventory_page(1))

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
                            i18n.t('menu.save'), i18n.t('menu.save_quit'),
                            i18n.t('menu.quit_to_title'))
        self.menu_buttons = [
            Button(parent=self.menu_root, text=label, scale=(.5, .062),
                   color=BUTTON_COLOR,
                   y=.16 - i * .072, on_click=action)
            for i, (label, action) in enumerate(zip(
                self.menu_labels,
                (self.close_menu, self.open_settings, self.open_packs,
                 self.open_keybinds, self._menu_save, self._menu_quit,
                 self._menu_quit_to_title)))
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
        # 行数增加后自动压缩行距，避免超出面板
        row_step = min(0.07, 0.60 / max(1, len(SETTING_KEYS) - 1))
        for i, key in enumerate(SETTING_KEYS):
            y = .29 - i * row_step
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

    # ---------- 主页面 ----------
    def _build_title(self):
        """标题页：玩家信息 + 单人游戏 / 设置 / 退出。"""
        self.title_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.title_root, model='quad', color=color.rgba(0, 0, 0, .85),
               scale=(3, 2), z=-10)
        Text(parent=self.title_root, text=i18n.t('title.game'),
             origin=(0, 0), y=.30, scale=2.4, z=UI_FRONT_Z)
        self.title_player = Text(parent=self.title_root, text='',
                                 origin=(0, 0), y=.185, scale=.8,
                                 color=color.azure, z=UI_FRONT_Z)
        labels = (i18n.t('title.singleplayer'), i18n.t('title.settings'),
                  i18n.t('title.quit'))
        self.title_buttons = [
            Button(parent=self.title_root, text=label, scale=(.5, .065),
                   color=BUTTON_COLOR, y=.02 - i * .08, on_click=action)
            for i, (label, action) in enumerate(zip(
                labels, (self.title_play, self.title_settings,
                         self.title_quit)))
        ]
        self.title_hint = Text(parent=self.title_root, text=i18n.t('title.hint'),
                               origin=(0, 0), y=-.32, scale=.55,
                               color=color.gray, z=UI_FRONT_Z)
        self._bring_to_front(self.title_root)

    # ---------- 存档列表 ----------
    def _build_saves(self):
        """存档列表：选择 / 进入 / 新建 / 删除。"""
        self.saves_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.saves_root, model='quad', color=color.rgba(0, 0, 0, .85),
               scale=(3, 2), z=-10)
        self.saves_title = Text(parent=self.saves_root, text=i18n.t('saves.title'),
                                origin=(0, 0), y=.42, scale=1.6, z=UI_FRONT_Z)
        self.saves_rows = []
        for i in range(SAVES_MAX_ROWS):
            y = .30 - i * .055
            label = Text(parent=self.saves_root, text='', origin=(-.5, 0),
                         x=-.72, y=y, scale=.62, z=UI_FRONT_Z)
            self.saves_rows.append(label)
        self.saves_empty = Text(parent=self.saves_root,
                                text=i18n.t('saves.empty'), origin=(0, 0),
                                y=.05, scale=.7, color=color.gray, z=UI_FRONT_Z)
        self.saves_status = Text(parent=self.saves_root, text='', origin=(0, 0),
                                 y=-.27, scale=.65, color=color.azure, z=UI_FRONT_Z)
        self.saves_hint = Text(parent=self.saves_root, text=i18n.t('saves.hint'),
                               origin=(0, 0), y=-.33, scale=.5,
                               color=color.gray, z=UI_FRONT_Z)
        buttons = (
            (i18n.t('saves.play'), -.42, self.saves_play),
            (i18n.t('saves.new'), -.14, self.saves_new),
            (i18n.t('saves.delete'), .14, self.saves_delete),
            (i18n.t('saves.back'), .42, self.saves_back),
        )
        self.saves_buttons = [
            Button(parent=self.saves_root, text=label, scale=(.28, .06),
                   color=BUTTON_COLOR, x=x, y=-.42, on_click=action)
            for label, x, action in buttons
        ]
        self._bring_to_front(self.saves_root)

    # ---------- 创建新世界 ----------
    def _build_new_save(self):
        self.new_save_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.new_save_root, model='quad', color=color.rgba(0, 0, 0, .85),
               scale=(3, 2), z=-10)
        self.new_save_title = Text(parent=self.new_save_root,
                                   text=i18n.t('newSave.title'),
                                   origin=(0, 0), y=.30, scale=1.6, z=UI_FRONT_Z)
        self.new_save_label = Text(parent=self.new_save_root,
                                   text=i18n.t('newSave.name'),
                                   origin=(0, 0), y=.12, scale=.8,
                                   color=color.gray, z=UI_FRONT_Z)
        self.new_save_status = Text(parent=self.new_save_root, text='',
                                    origin=(0, 0), y=-.22, scale=.65,
                                    color=color.azure, z=UI_FRONT_Z)
        self.new_save_buttons = [
            Button(parent=self.new_save_root, text=i18n.t('newSave.create'),
                   scale=(.28, .06), color=BUTTON_COLOR, x=-.35, y=-.34,
                   on_click=self.new_save_create),
            Button(parent=self.new_save_root, text=i18n.t('newSave.cancel'),
                   scale=(.28, .06), color=BUTTON_COLOR, x=.35, y=-.34,
                   on_click=self.new_save_cancel),
        ]
        self._bring_to_front(self.new_save_root)

    # ---------- 创建玩家 ----------
    def _build_player(self):
        self.player_root = Entity(parent=camera.ui, enabled=False)
        Entity(parent=self.player_root, model='quad', color=color.rgba(0, 0, 0, .85),
               scale=(3, 2), z=-10)
        self.player_title = Text(parent=self.player_root, text=i18n.t('player.title'),
                                 origin=(0, 0), y=.30, scale=1.8, z=UI_FRONT_Z)
        self.player_hint = Text(parent=self.player_root, text=i18n.t('player.hint'),
                                origin=(0, 0), y=.18, scale=.65,
                                color=color.gray, z=UI_FRONT_Z)
        self.player_button = Button(parent=self.player_root,
                                    text=i18n.t('player.confirm'),
                                    scale=(.3, .06), color=BUTTON_COLOR, y=-.28,
                                    on_click=self.player_confirm)
        self._bring_to_front(self.player_root)

    # ---------- 页面切换 ----------
    def _enter_menu_ui(self):
        """进入非游戏页面：收起 HUD/快捷栏/准星等游戏内 UI。"""
        self.hotbar_root.enabled = False
        self.hud.enabled = False
        self.crosshair.enabled = False
        self.selector.enabled = False
        self.chat_root.enabled = False

    def show_title(self):
        self._hide_screens()
        self._enter_menu_ui()
        self.screen = 'title'
        self.title_root.enabled = True
        self.refresh_title()

    def show_saves(self):
        self._hide_screens()
        self._enter_menu_ui()
        self.screen = 'saves'
        self.saves_root.enabled = True
        self.refresh_saves()

    def show_new_save(self):
        self._hide_screens()
        self._enter_menu_ui()
        self.screen = 'new_save'
        self.new_save_root.enabled = True
        self.new_save_status.text = ''
        self._open_name_input(self.new_save_create, self.new_save_cancel)

    def show_player_creation(self):
        self._hide_screens()
        self._enter_menu_ui()
        self.screen = 'player'
        self.player_root.enabled = True
        self._open_name_input(self.player_confirm, None)

    def _open_name_input(self, on_submit, on_cancel):
        """打开居中的名称输入框（创建玩家/新存档共用）。"""
        self.text_input.open(prompt='', on_submit=on_submit,
                             on_cancel=on_cancel,
                             position=(.0, -.30), width=.8,
                             max_len=saves.NAME_MAX_LEN)

    def _hide_screens(self):
        for root in (self.title_root, self.saves_root, self.new_save_root,
                     self.player_root, self.settings_root, self.packs_root,
                     self.keys_root, self.menu_root):
            root.enabled = False
        self.settings_open = self.packs_open = self.keys_open = False
        self.menu_state['open'] = False
        if self.text_input.is_open:
            self.text_input.close()

    def hide_all_screens(self):
        """进入世界：收起所有页面 UI，恢复游戏内 HUD。"""
        self._hide_screens()
        self.inventory_open = False
        self.inventory_root.enabled = False
        self.hide_tooltip()
        if self.held_item is not None:
            self.clear_held()
        self.hotbar_root.enabled = True
        self.hud.enabled = True
        self.crosshair.enabled = True
        self.chat_root.enabled = True

    # ---------- 刷新 ----------
    def refresh_title(self):
        self.title_player.text = i18n.t('title.welcome').format(
            name=self.player_name)
        for i, button in enumerate(self.title_buttons):
            button.text = (f'> {i18n.t(["title.singleplayer", "title.settings", "title.quit"][i])} <'
                           if i == self.title_index
                           else f'  {i18n.t(["title.singleplayer", "title.settings", "title.quit"][i])}  ')

    def refresh_saves(self):
        self.save_entries = saves.list_saves()
        if self.save_entries:
            self.saves_index = min(self.saves_index, len(self.save_entries) - 1)
        else:
            self.saves_index = 0
        self.saves_empty.enabled = not self.save_entries
        for i, label in enumerate(self.saves_rows):
            if i < len(self.save_entries):
                entry = self.save_entries[i]
                stamp = py_time.strftime('%Y-%m-%d %H:%M',
                                         py_time.localtime(entry['mtime']))
                label.text = i18n.t('saves.row').format(
                    name=entry['name'], blocks=entry['blocks'], time=stamp)
                label.enabled = True
            else:
                label.text = ''
                label.enabled = False
            label.color = color.azure if i == self.saves_index else color.white

    # ---------- 主页面动作 ----------
    def title_select(self, delta):
        self.title_index = (self.title_index + delta) % len(self.title_buttons)
        self.refresh_title()

    def title_activate(self):
        (self.title_play, self.title_settings, self.title_quit)[self.title_index]()

    def title_play(self):
        self.show_saves()

    def title_settings(self):
        self.settings_from_title = True
        self.settings_open = True
        self.settings_index = 0
        self.title_root.enabled = False
        self.settings_root.enabled = True
        self.refresh_settings()

    def title_quit(self):
        if self.on_quit:
            self.on_quit()
        else:
            application.quit()

    # ---------- 存档列表动作 ----------
    def saves_select(self, delta):
        if not self.save_entries:
            return
        self.saves_index = (self.saves_index + delta) % len(self.save_entries)
        self.refresh_saves()

    def saves_play(self):
        """进入选中的存档（由 Game 真正加载世界）。"""
        if self.save_entries:
            self.saves_status.text = ''
            self.on_play_save(self.save_entries[self.saves_index]['path'])

    def saves_new(self):
        self.show_new_save()

    def saves_delete(self):
        if not self.save_entries:
            return
        name = self.save_entries[self.saves_index]['name']
        if saves.delete_save(name):
            self.saves_status.text = i18n.t('saves.deleted')
            self.saves_index = 0
        else:
            self.saves_status.text = i18n.t('saves.save_failed')
        self.refresh_saves()

    def saves_back(self):
        self.show_title()

    # ---------- 创建新世界 ----------
    def new_save_create(self, name):
        name = saves.sanitize_name(name)
        if not name or saves.save_file(name).exists():
            self.new_save_status.text = i18n.t('saves.exists')
            self._open_name_input(self.new_save_create, self.new_save_cancel)
            return
        if saves.create_save(name) is None:
            self.new_save_status.text = i18n.t('notice.save_failed')
            self._open_name_input(self.new_save_create, self.new_save_cancel)
            return
        self.on_play_save(saves.save_file(name))

    def new_save_cancel(self):
        self.show_saves()

    # ---------- 创建玩家 ----------
    def player_confirm(self, name):
        name = saves.sanitize_name(name)
        if not name:
            self._open_name_input(self.player_confirm, None)
            return
        saves.save_player(name)
        self.player_name = name
        self.on_player_created()

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

    def inventory_page_items(self):
        """当前页显示的方块（创造背包只读，内容固定）。"""
        start = self.inv_page * config.INVENTORY_PAGE_SIZE
        return self.inventory[start:start + config.INVENTORY_PAGE_SIZE]

    def inventory_page_count(self):
        total = max(1, -(-len(self.inventory) // config.INVENTORY_PAGE_SIZE))
        return total

    def turn_inventory_page(self, delta):
        """翻页：← → 或点击按钮。"""
        self.inv_page = (self.inv_page + delta) % self.inventory_page_count()
        self.inv_selected = 0
        self.refresh_inventory()

    def refresh_inventory(self):
        page = self.inventory_page_items()
        for i, (bg, items) in enumerate(self.inventory_ui):
            block_id = page[i] if i < len(page) else None
            for item_id, icon in items.items():
                icon.enabled = (item_id == block_id)
            bg.color = (color.rgba(1, 1, 1, .35) if i == self.inv_selected
                        else color.black90)
        self.inv_page_text.text = i18n.t('inventory.page').format(
            page=self.inv_page + 1, total=self.inventory_page_count())

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
        if key in ('auto_jump', 'vsync'):
            return i18n.t('settings.on' if value else 'settings.off')
        if key == 'max_fps':
            return i18n.t('settings.unlimited' if not value else str(int(value)))
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
        elif key == 'vsync':
            # Panda3D 运行时不支持切换垂直同步：保存设置，重启后生效
            config.apply_settings(
                {'vsync': not config.SETTINGS.get('vsync', True)})
            if self.notice_callback:
                self.notice_callback('notice.restart_required')
        elif key == 'max_fps':
            choices = list(config.FPS_CHOICES)
            current = int(config.SETTINGS.get('max_fps', 0) or 0)
            index = choices.index(current) if current in choices else 0
            config.apply_settings(
                {'max_fps': choices[(index + delta) % len(choices)]})
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
                            i18n.t('menu.save'), i18n.t('menu.save_quit'),
                            i18n.t('menu.quit_to_title'))
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

        # 主页面 / 存档 / 创建玩家
        self.title_hint.text = i18n.t('title.hint')
        self.saves_title.text = i18n.t('saves.title')
        self.saves_hint.text = i18n.t('saves.hint')
        self.saves_empty.text = i18n.t('saves.empty')
        self.new_save_title.text = i18n.t('newSave.title')
        self.new_save_label.text = i18n.t('newSave.name')
        self.player_title.text = i18n.t('player.title')
        self.player_hint.text = i18n.t('player.hint')
        for button, key in zip(self.saves_buttons,
                               ('saves.play', 'saves.new', 'saves.delete',
                                'saves.back')):
            button.text = i18n.t(key)
        self.new_save_buttons[0].text = i18n.t('newSave.create')
        self.new_save_buttons[1].text = i18n.t('newSave.cancel')
        self.player_button.text = i18n.t('player.confirm')
        self.refresh_title()      # 最后刷新，保留高亮标记
        self.saves_title.text = i18n.t('saves.title')
        self.saves_hint.text = i18n.t('saves.hint')
        self.saves_empty.text = i18n.t('saves.empty')
        for button, key in zip(self.saves_buttons,
                               ('saves.play', 'saves.new', 'saves.delete',
                                'saves.back')):
            button.text = i18n.t(key)
        self.new_save_title.text = i18n.t('newSave.title')
        self.new_save_label.text = i18n.t('newSave.name')
        self.new_save_buttons[0].text = i18n.t('newSave.create')
        self.new_save_buttons[1].text = i18n.t('newSave.cancel')
        self.player_title.text = i18n.t('player.title')
        self.player_hint.text = i18n.t('player.hint')
        self.player_button.text = i18n.t('player.confirm')

    def load_hotbar(self, save_data):
        """从存档恢复快捷栏与选中格（无效条目置空）。"""
        if not save_data:
            return
        saved_hotbar = save_data.get('hotbar')
        if isinstance(saved_hotbar, list):
            for i in range(config.HOTBAR_SLOTS):
                if i < len(saved_hotbar):
                    item = saved_hotbar[i]
                    self.hotbar[i] = (item if isinstance(item, str) and item in BLOCKS
                                      else None)
            self.selected_slot = int(_save_number(
                save_data.get('selected_slot'), 0, 0, config.HOTBAR_SLOTS - 1))

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

    # ---------- 页面鼠标命中（不依赖 Ursina 鼠标事件层） ----------
    @staticmethod
    def _hit_button(point, button):
        """UI 坐标是否落在按钮矩形内。"""
        if point is None:
            return False
        px, py = point
        return (abs(px - button.x) <= button.scale_x / 2 + .012
                and abs(py - button.y) <= button.scale_y / 2 + .012)

    def title_click(self, point):
        for i, button in enumerate(self.title_buttons):
            if self._hit_button(point, button):
                self.title_index = i
                self.refresh_title()
                button.on_click()
                return

    def saves_click(self, point):
        if point is None:
            return
        # 行点击：选中该存档
        for i in range(min(len(self.save_entries), SAVES_MAX_ROWS)):
            y = .30 - i * .055
            if abs(point[1] - y) <= .028 and -.72 <= point[0] <= .72:
                if self.saves_index != i:
                    self.saves_index = i
                    self.refresh_saves()
                return
        for button in self.saves_buttons:
            if self._hit_button(point, button):
                button.on_click()
                return

    def new_save_click(self, point):
        for button in self.new_save_buttons:
            if self._hit_button(point, button):
                button.on_click()
                return

    def player_click(self, point):
        if self._hit_button(point, self.player_button):
            self.player_button.on_click()

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
        if slot and slot[0] == 'inventory':
            # 创造背包：页内索引换算成全局索引
            index = self.inv_page * config.INVENTORY_PAGE_SIZE + slot[1]
            block_id = self.inventory[index] if index < len(self.inventory) else None
        else:
            block_id = self.hotbar[slot[1]] if slot else None
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
        if self.held_item is not None:
            # 手上的物品来自快捷栏：放回原来的格子，避免关闭背包时丢失
            if (self.held_from is not None
                    and self.hotbar[self.held_from] is None):
                self.hotbar[self.held_from] = self.held_item
                self.refresh_hotbar()
            self.clear_held()
        self.inventory_open = False
        self.inventory_root.enabled = False
        self.hide_tooltip()
        self.refresh_inventory()
        mouse.locked = True

    def clear_held(self):
        """清空手上的物品（不等放回格子）。"""
        self.held_item = None
        self.held_from = None
        for icon in self.held_icons.values():
            icon.enabled = False

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
        self.settings_from_title = False
        self.settings_open = True
        self.settings_index = 0
        self.menu_root.enabled = False
        self.settings_root.enabled = True
        self.refresh_settings()
        mouse.locked = False

    def close_settings(self):
        self.settings_open = False
        self.settings_root.enabled = False
        if self.settings_from_title:
            # 从主页面打开的设置：返回主页面
            self.settings_from_title = False
            self.title_root.enabled = True
            self.refresh_title()
        else:
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

    def _menu_quit_to_title(self):
        """保存并退出到主页面（由 Game 真正卸载世界）。"""
        if self.on_quit_to_title:
            self.on_quit_to_title()

    # ---------- 背包鼠标拖拽 / 替换 ----------
    def handle_inventory_click(self, point, left_click, right_click=False):
        slot = self.hovered_slot(point)
        if slot and (left_click or right_click):
            which, idx = slot
            if which == 'inventory':
                # 创造背包是只读的：只允许选中查看，不能拿取/替换
                self.inv_selected = idx
                self.refresh_inventory()
            else:
                item = self.hotbar[idx]
                if left_click:
                    if self.held_item is None:
                        if item is not None:
                            self.held_item = item
                            self.held_from = idx
                            self.hotbar[idx] = None
                    else:
                        self.hotbar[idx] = self.held_item
                        self.held_item = item
                        self.held_from = idx if item is not None else None
                    self.selected_slot = idx
                else:
                    # 右键：空手时复制该格物品；手上有物品时替换该格（手上保留）
                    if self.held_item is None:
                        if item is not None:
                            self.held_item = item
                            self.held_from = idx
                    else:
                        self.hotbar[idx] = self.held_item
                        self.held_from = idx
                    self.selected_slot = idx
                self.refresh_hotbar()

        # 手上的方块跟随鼠标
        for block_id, icon in self.held_icons.items():
            icon.enabled = (block_id == self.held_item and point is not None)
            if icon.enabled:
                icon.position = (point[0], point[1], -18)
