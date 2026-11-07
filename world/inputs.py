"""X11 物理输入轮询。

本机 Ursina/Panda3D 的键盘事件层会丢失 key-up（held_keys 只增不减），
space/shift/escape 也没有事件；鼠标按键事件同样不可靠。这里直接读
X11 的物理状态，非 X11 平台回退到 held_keys / mouse.left/right。
"""

import ctypes

from ursina import application


class PhysicalKeys:
    KEYSYMS = {
        'w': 0x77, 'a': 0x61, 's': 0x73, 'd': 0x64,
        'c': 0x63, 'e': 0x65,
        'space': 0x20, 'escape': 0xff1b, 'f5': 0xffc2,
        'shift_l': 0xffe1, 'shift_r': 0xffe2,
        'lcontrol': 0xffe3, 'rcontrol': 0xffe4,
        'up': 0xff52, 'down': 0xff54, 'left': 0xff51, 'right': 0xff53,
        'enter': 0xff0d, 'kp_enter': 0xff8d,
        '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
        '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    }
    ALIASES = {
        'shift_l': 'shift', 'shift_r': 'shift',
        'lcontrol': 'ctrl', 'rcontrol': 'ctrl',
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
