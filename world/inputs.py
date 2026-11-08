"""跨平台物理输入轮询。

Ursina/Panda3D 的键盘事件层会丢失 key-up（held_keys 只增不减），
space/shift/escape 也没有事件；鼠标按键事件同样不可靠。
Linux 用 XQueryKeymap / XQueryPointer，Windows 用 GetAsyncKeyState /
GetCursorPos，其它平台回退到 held_keys / mouse.left/right。
"""

import ctypes
import sys

from ursina import application


class PhysicalKeys:
    # 按键绑定需要覆盖常见键；XKeysymToKeycode 会把 keysym 映射到当前布局的 keycode
    KEYSYMS = {chr(code): code for code in range(ord('a'), ord('z') + 1)}
    KEYSYMS.update({str(i): 0x30 + i for i in range(10)})
    KEYSYMS.update({
        'space': 0x20, 'escape': 0xff1b, 'tab': 0xff09,
        'enter': 0xff0d, 'kp_enter': 0xff8d,
        'backspace': 0xff08, 'delete': 0xffff,
        'up': 0xff52, 'down': 0xff54, 'left': 0xff51, 'right': 0xff53,
        'home': 0xff50, 'end': 0xff57, 'page_up': 0xff55, 'page_down': 0xff56,
        'shift_l': 0xffe1, 'shift_r': 0xffe2,
        'lcontrol': 0xffe3, 'rcontrol': 0xffe4,
        'alt_l': 0xffe9, 'alt_r': 0xffea,
        'super_l': 0xffeb, 'super_r': 0xffec,
        'minus': 0x2d, 'equal': 0x3d, 'bracket_left': 0x5b,
        'bracket_right': 0x5d, 'semicolon': 0x3b, 'quote': 0x27,
        'comma': 0x2c, 'period': 0x2e, 'slash': 0x2f,
        'backslash': 0x5c, 'grave': 0x60,
    })
    KEYSYMS.update({f'f{i}': 0xffbd + i for i in range(1, 13)})
    ALIASES = {
        'shift_l': 'shift', 'shift_r': 'shift',
        'lcontrol': 'ctrl', 'rcontrol': 'ctrl',
        'alt_l': 'alt', 'alt_r': 'alt',
        'super_l': 'super', 'super_r': 'super',
        'kp_enter': 'enter',
    }
    BUTTON1_MASK = 1 << 8      # 鼠标左键
    BUTTON2_MASK = 1 << 9      # 鼠标中键
    BUTTON3_MASK = 1 << 10     # 鼠标右键

    # 可打印字符：键名 -> (无 Shift, 有 Shift)，供聊天输入使用
    CHAR_MAP = {name: (name, name.upper()) for name in
                'abcdefghijklmnopqrstuvwxyz'}
    CHAR_MAP.update({
        'space': (' ', ' '),
        '0': ('0', ')'), '1': ('1', '!'), '2': ('2', '@'), '3': ('3', '#'),
        '4': ('4', '$'), '5': ('5', '%'), '6': ('6', '^'), '7': ('7', '&'),
        '8': ('8', '*'), '9': ('9', '('),
        'minus': ('-', '_'), 'equal': ('=', '+'),
        'bracket_left': ('[', '{'), 'bracket_right': (']', '}'),
        'semicolon': (';', ':'), 'quote': ("'", '"'),
        'comma': (',', '<'), 'period': ('.', '>'), 'slash': ('/', '?'),
        'backslash': ('\\', '|'), 'grave': ('`', '~'),
    })
    # Windows 虚拟键码 -> (无 Shift, 有 Shift)
    WIN_CHAR_MAP = {code: (chr(code), chr(code).upper())
                    for code in range(0x41, 0x5B)}
    WIN_CHAR_MAP.update({
        0x30: ('0', ')'), 0x31: ('1', '!'), 0x32: ('2', '@'), 0x33: ('3', '#'),
        0x34: ('4', '$'), 0x35: ('5', '%'), 0x36: ('6', '^'), 0x37: ('7', '&'),
        0x38: ('8', '*'), 0x39: ('9', '('),
        0x20: (' ', ' '), 0xBA: (';', ':'), 0xBB: ('=', '+'),
        0xBC: (',', '<'), 0xBD: ('-', '_'), 0xBE: ('.', '>'),
        0xBF: ('/', '?'), 0xC0: ('`', '~'), 0xDB: ('[', '{'),
        0xDD: (']', '}'), 0xDC: ('\\', '|'), 0xDE: ("'", '"'),
    })

    # Windows 虚拟键码（键名与 X11 分支输出的别名一致）
    VK_CODES = {c: 0x41 + i for i, c in enumerate('abcdefghijklmnopqrstuvwxyz')}
    VK_CODES.update({str(i): 0x30 + i for i in range(10)})
    VK_CODES.update({f'f{i}': 0x6F + i for i in range(1, 13)})
    VK_CODES.update({
        'space': 0x20, 'escape': 0x1b, 'tab': 0x09, 'enter': 0x0d,
        'backspace': 0x08, 'delete': 0x2e,
        'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
        'home': 0x24, 'end': 0x23, 'page_up': 0x21, 'page_down': 0x22,
        'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12, 'super': 0x5b,
        'minus': 0xbd, 'equal': 0xbb, 'bracket_left': 0xdb,
        'bracket_right': 0xdd, 'semicolon': 0xba, 'quote': 0xde,
        'comma': 0xbc, 'period': 0xbe, 'slash': 0xbf,
        'backslash': 0xdc, 'grave': 0xc0,
    })
    VK_LBUTTON, VK_RBUTTON, VK_MBUTTON = 0x01, 0x02, 0x04

    def __init__(self):
        self._x11 = None
        self._win32 = None
        self._wintypes = None
        self._root = 0
        self._window_id = 0
        self._hwnd = 0
        self._keycodes = {}
        if sys.platform == 'win32':
            self._init_win32()
            return
        x11 = None
        for name in ('libX11.so.6', 'libX11.so'):
            try:
                x11 = ctypes.CDLL(name)
                break
            except OSError:
                continue
        if x11 is None:
            return

        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XKeysymToKeycode.restype = ctypes.c_uint
        x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XQueryKeymap.restype = ctypes.c_int
        x11.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XQueryPointer.restype = ctypes.c_int
        x11.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        display = x11.XOpenDisplay(None)
        if not display:
            return

        self._x11 = x11
        self._display = display
        self._root = x11.XDefaultRootWindow(display)
        try:
            self._window_id = application.base.win.get_window_handle().get_int_handle()
        except Exception:
            self._window_id = self._root
        self._keymap = (ctypes.c_ubyte * 32)()
        self._keymap_ptr = ctypes.cast(self._keymap, ctypes.POINTER(ctypes.c_ubyte))
        self._keycodes = {
            name: x11.XKeysymToKeycode(display, keysym)
            for name, keysym in self.KEYSYMS.items()
        }
        # keycode -> 键名（取第一个，避免不同布局的别名互相覆盖）
        self._keycode_names = {}
        for name, code in self._keycodes.items():
            if code and code not in self._keycode_names:
                self._keycode_names[code] = name
        self._prev_pressed = set()

    # ---------- Windows ----------
    def _init_win32(self):
        try:
            from ctypes import wintypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = ctypes.c_short
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            user32.GetCursorPos.restype = wintypes.BOOL
            user32.ScreenToClient.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
            user32.ScreenToClient.restype = wintypes.BOOL
            self._win32 = user32
            self._wintypes = wintypes
        except Exception as e:
            print(f'[输入] Win32 初始化失败，回退 Ursina 事件层: {e}')
            self._win32 = None
            return
        self._resolve_hwnd()

    def _resolve_hwnd(self):
        try:
            self._hwnd = application.base.win.get_window_handle().get_int_handle()
        except Exception:
            self._hwnd = 0

    def snapshot(self):
        """返回当前按下的键名集合；无物理输入后端时返回 None 以启用回退。"""
        if self._win32 is not None:
            user32 = self._win32
            return {name for name, vk in self.VK_CODES.items()
                    if user32.GetAsyncKeyState(vk) & 0x8000}
        if self._x11 is None or not self._x11.XQueryKeymap(self._display, self._keymap_ptr):
            return None
        pressed = set()
        for name, code in self._keycodes.items():
            if not 8 <= code < 256:
                continue
            if self._keymap[code // 8] & (1 << (code % 8)):
                pressed.add(self.ALIASES.get(name, name))
        return pressed

    def char_events(self):
        """自上次调用以来新按下的可打印字符列表；无物理后端时返回 None。

        聊天输入用：不依赖 Ursina 事件层（本机 key-up 丢失、space 无事件）。
        """
        if self._win32 is not None:
            return self._char_events_win32()
        if self._x11 is None or not self._x11.XQueryKeymap(
                self._display, self._keymap_ptr):
            return None
        pressed = {code for name, code in self._keycodes.items()
                   if 8 <= code < 256
                   and self._keymap[code // 8] & (1 << (code % 8))}
        fresh = pressed - self._prev_pressed
        self._prev_pressed = pressed
        if not fresh:
            return []
        shift = any(name in pressed for name in ('shift_l', 'shift_r'))
        chars = []
        for code in sorted(fresh):
            pair = self.CHAR_MAP.get(self._keycode_names.get(code))
            if pair:
                chars.append(pair[1] if shift else pair[0])
        return chars

    def _char_events_win32(self):
        user32 = self._win32
        pressed = {code for code in self.WIN_CHAR_MAP
                   if user32.GetAsyncKeyState(code) & 0x8000}
        fresh = pressed - self._prev_pressed
        self._prev_pressed = pressed
        if not fresh:
            return []
        shift = bool(user32.GetAsyncKeyState(0x10) & 0x8000)
        return [pair[1] if shift else pair[0]
                for code in sorted(fresh)
                if (pair := self.WIN_CHAR_MAP.get(code))]

    def drain_chars(self):
        """丢弃挂起的字符输入（打开聊天时调用，避免把打开前的按键算进来）。"""
        self.char_events()

    def mouse_buttons(self):
        """返回 (左键, 中键, 右键) 的按住状态；无物理后端时返回 None。"""
        if self._win32 is not None:
            user32 = self._win32
            return (bool(user32.GetAsyncKeyState(self.VK_LBUTTON) & 0x8000),
                    bool(user32.GetAsyncKeyState(self.VK_MBUTTON) & 0x8000),
                    bool(user32.GetAsyncKeyState(self.VK_RBUTTON) & 0x8000))
        if self._x11 is None or not self._root:
            return None
        root_return = ctypes.c_ulong()
        child_return = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        win_x = ctypes.c_int()
        win_y = ctypes.c_int()
        mask = ctypes.c_uint()
        ok = self._x11.XQueryPointer(
            self._display, self._root,
            ctypes.byref(root_return), ctypes.byref(child_return),
            ctypes.byref(root_x), ctypes.byref(root_y),
            ctypes.byref(win_x), ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        if not ok:
            return None
        return (bool(mask.value & self.BUTTON1_MASK),
                bool(mask.value & self.BUTTON2_MASK),
                bool(mask.value & self.BUTTON3_MASK))

    def pointer_ui_position(self):
        """返回鼠标在 UI 坐标里的位置（x ∈ ±aspect/2，y ∈ ±0.5）；不可用时返回 None。"""
        if self._win32 is not None:
            if not self._hwnd:
                self._resolve_hwnd()
            if not self._hwnd:
                return None
            point = self._wintypes.POINT()
            if not self._win32.GetCursorPos(ctypes.byref(point)):
                return None
            if not self._win32.ScreenToClient(
                    self._wintypes.HWND(self._hwnd), ctypes.byref(point)):
                return None
            window = application.base.win
            width, height = window.get_x_size(), window.get_y_size()
            if width <= 0 or height <= 0:
                return None
            return ((point.x / width - 0.5) * (width / height),
                    0.5 - point.y / height)
        if self._x11 is None or not self._window_id:
            return None
        root_return = ctypes.c_ulong()
        child_return = ctypes.c_ulong()
        root_x = ctypes.c_int()
        root_y = ctypes.c_int()
        win_x = ctypes.c_int()
        win_y = ctypes.c_int()
        mask = ctypes.c_uint()
        ok = self._x11.XQueryPointer(
            self._display, self._window_id,
            ctypes.byref(root_return), ctypes.byref(child_return),
            ctypes.byref(root_x), ctypes.byref(root_y),
            ctypes.byref(win_x), ctypes.byref(win_y),
            ctypes.byref(mask),
        )
        if not ok:
            return None
        window = application.base.win
        width, height = window.get_x_size(), window.get_y_size()
        if width <= 0 or height <= 0:
            return None
        aspect = width / height
        return ((win_x.value / width - 0.5) * aspect,
                0.5 - win_y.value / height)
