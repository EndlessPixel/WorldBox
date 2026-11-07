"""X11 物理输入轮询。

本机 Ursina/Panda3D 的键盘事件层会丢失 key-up（held_keys 只增不减），
space/shift/escape 也没有事件；鼠标按键事件同样不可靠。这里直接读
X11 的物理状态，非 X11 平台回退到 held_keys / mouse.left/right。
"""

import ctypes

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

    def __init__(self):
        self._x11 = None
        self._root = 0
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

    def snapshot(self):
        """返回当前按下的键名集合；X11 不可用时返回 None 以启用回退。"""
        if self._x11 is None or not self._x11.XQueryKeymap(self._display, self._keymap_ptr):
            return None
        pressed = set()
        for name, code in self._keycodes.items():
            if not 8 <= code < 256:
                continue
            if self._keymap[code // 8] & (1 << (code % 8)):
                pressed.add(self.ALIASES.get(name, name))
        return pressed

    def mouse_buttons(self):
        """返回 (左键, 中键, 右键) 的按住状态；X11 不可用时返回 None。"""
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
