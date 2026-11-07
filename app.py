"""
3D 世界 - Python + Ursina
=========================
- 128x128 米体素世界（每方块 1 米），按 16x16 区块合并网格渲染，
  避免给 16384 个方块各建一个实体
- 左键挖掘 / 右键放置 / 中键选取方块 / 滚轮切换快捷栏
- 方块 ID 形如 worldbox:grass.block，定义在同目录 blocks.json（id / name / color）
- E 背包（3x9）/ 数字键 1-9 快捷栏 / 准心 / 方块选中线框
- 天空盒 + 昼夜更替（日出日落偏橙，夜晚整体变暗）
- WASD 移动 / Ctrl 疾跑 / 空格跳跃 / Shift 蹲下 / C 放大 / 鼠标转视角
- ESC 暂停菜单（继续 / 存档 / 保存并退出）；F5 存档
- 同目录 setting.json 可配置：自动跳跃/高度、视距、FOV、视角晃动、亮度
- 存档：同目录 world_save.json（玩家状态、方块改动、快捷栏）

安装：pip install ursina
"""

from ursina import *
from pathlib import Path
import atexit
import ctypes
import json
import math

# ---------- 用户设置（同目录 setting.json） ----------
SETTINGS_FILE = Path(__file__).resolve().with_name('setting.json')
DEFAULT_SETTINGS = {
    'auto_jump': True,          # 是否自动跳上台阶
    'auto_jump_height': 1.0,    # 自动跳跃能跨过的高度（格）
    'view_distance': 96,        # 视距（米）
    'fov': 40,                  # 基础视场角
    'view_bob': 0.03,           # 移动时视角晃动幅度（米）
    'brightness': 1.0,          # 画面亮度（0.3 ~ 2.0）
}


def _cfg_number(value, default, low, high):
    """配置数值校验：拒绝非法值并钳制范围。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with SETTINGS_FILE.open(encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError, TypeError):
        print('[设置] 没有可用的 setting.json，使用默认设置')
        return settings
    if not isinstance(raw, dict):
        print('[设置] setting.json 格式不正确，使用默认设置')
        return settings
    if isinstance(raw.get('auto_jump'), bool):
        settings['auto_jump'] = raw['auto_jump']
    settings['auto_jump_height'] = _cfg_number(raw.get('auto_jump_height'), 1.0, 0.5, 2.0)
    settings['view_distance'] = _cfg_number(raw.get('view_distance'), 96, 16, 256)
    settings['fov'] = _cfg_number(raw.get('fov'), 40, 20, 120)
    settings['view_bob'] = _cfg_number(raw.get('view_bob'), 0.03, 0.0, 0.2)
    settings['brightness'] = _cfg_number(raw.get('brightness'), 1.0, 0.3, 2.0)
    print('[设置] ' + ', '.join(f'{k}={v}' for k, v in settings.items()))
    return settings


SETTINGS = load_settings()

# ================= 可调参数 =================
WORLD_SIZE        = 128     # 世界边长（米）
CHUNK_SIZE        = 16      # 每个区块边长（米）
VIEW_DISTANCE     = SETTINGS['view_distance']     # 区块可见距离（米）
AUTO_JUMP         = SETTINGS['auto_jump']         # 自动跳上台阶
AUTO_JUMP_HEIGHT  = SETTINGS['auto_jump_height']  # 自动跳跃能跨过的高度（格）
BASE_FOV          = SETTINGS['fov']               # 基础视场角
VIEW_BOB          = SETTINGS['view_bob']          # 移动时视角晃动幅度（米）
BRIGHTNESS        = SETTINGS['brightness']        # 画面亮度

# 世界分层（从最底层往上）：基岩 1 层、石头 3 层、泥土 2 层、草 1 层
WORLD_LAYERS      = (
    ('worldbox:bedrock.block', 1),
    ('worldbox:stone.block', 3),
    ('worldbox:dirt.block', 2),
    ('worldbox:grass.block', 1),
)
WORLD_DEPTH       = sum(count for _, count in WORLD_LAYERS)
MIN_BLOCK_Y       = -WORLD_DEPTH   # 最底层 y=-7，顶层草方块顶面仍在 y=0
MAX_BLOCK_Y       = 16      # 可放置高度上限（不含）
FALL_LIMIT_Y      = MIN_BLOCK_Y - 10   # 掉到这个高度以下传送回出生点
REACH_DISTANCE    = 6.0     # 挖掘/放置距离（米）

EYE_HEIGHT        = 1.75    # 站立眼高（米）
CROUCH_EYE_HEIGHT = 1.00    # 蹲下眼高（米）
WALK_SPEED        = 6.0     # 走路速度 m/s
SPRINT_SPEED      = 9.5     # 疾跑速度 m/s（按住 Ctrl）
CROUCH_SPEED      = 2.5     # 蹲行速度 m/s
ZOOM_FOV          = min(15, BASE_FOV * 0.6)   # C 键放大时的视场角
FOV_LERP_SPEED    = 10      # 变焦过渡速度
GRAVITY           = 25.0    # 重力 m/s^2
JUMP_SPEED        = 8.0     # 起跳速度 m/s
MOUSE_SENSITIVITY = 40      # 鼠标灵敏度
EYE_LERP_SPEED    = 12      # 眼高过渡速度
PLAYER_RADIUS     = 0.4     # 玩家半径（用于边界限制）
HUD_INTERVAL      = 0.1     # HUD 刷新间隔（秒）
AUTOSAVE_INTERVAL = 30.0    # 自动存档间隔（秒）
DAY_LENGTH        = 180.0   # 一昼夜时长（秒）
START_DAY_TIME    = 0.35    # 0=午夜, 0.25=日出, 0.5=正午, 0.75=日落

HOTBAR_SLOTS      = 9       # 快捷栏格数
INVENTORY_COLS    = 9       # 背包列数
INVENTORY_ROWS    = 3       # 背包行数（3x9）
SLOT_SIZE         = 0.052   # UI 格子边长（屏幕比例）
SLOT_GAP          = 0.006   # 格子间距

SAVE_FILE         = Path(__file__).resolve().with_name('world_save.json')
BLOCKS_FILE       = Path(__file__).resolve().with_name('blocks.json')
DEFAULT_BLOCK_ID  = 'worldbox:grass.block'
# ===========================================

# ---------- 方块定义（blocks.json） ----------
DEFAULT_BLOCKS = (
    {'id': 'worldbox:grass.block', 'name': 'Grass', 'color': (92, 172, 78)},
    {'id': 'worldbox:dirt.block',  'name': 'Dirt',  'color': (134, 96, 67)},
    {'id': 'worldbox:stone.block', 'name': 'Stone', 'color': (128, 128, 128)},
)


def load_blocks():
    """读取 blocks.json；逐条校验，坏条目跳过，文件不可用时退回内置定义。"""
    blocks = {}
    try:
        with BLOCKS_FILE.open(encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, list):
            for item in raw[:256]:   # 限制条目数，避免异常大文件
                if not isinstance(item, dict):
                    continue
                block_id = item.get('id')
                if not isinstance(block_id, str) or not block_id.strip():
                    continue
                rgb = item.get('color')
                if not isinstance(rgb, (list, tuple)) or len(rgb) < 3:
                    continue
                try:
                    r, g, b = (max(0, min(255, int(c))) for c in rgb[:3])
                except (TypeError, ValueError):
                    continue
                name = item.get('name')
                blocks[block_id] = {
                    'name': str(name) if name else block_id,
                    'color': (r, g, b),
                }
    except (OSError, ValueError, TypeError):
        blocks = {}
    if not blocks:
        blocks = {b['id']: {'name': b['name'], 'color': b['color']} for b in DEFAULT_BLOCKS}
    return blocks


BLOCKS = load_blocks()
BLOCK_IDS = list(BLOCKS)
BLOCK_NAMES = {block_id: data['name'] for block_id, data in BLOCKS.items()}
print(f'[方块] 已加载 {len(BLOCKS)} 种：' + ', '.join(BLOCK_IDS))


# ---------- 存档 ----------
def load_save():
    """读取存档；文件损坏或版本不兼容时返回 None。"""
    try:
        with SAVE_FILE.open(encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get('version') not in (1, 2):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def _save_number(value, default, low, high):
    """把存档中的数值安全地钳制到合法范围，拒绝 NaN/inf/非数字。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(low, min(high, number))


save_data = load_save()
print(f'[存档] {"已读取 " + SAVE_FILE.name if save_data else "无存档，使用默认世界"}')


def save_world():
    """先写临时文件再原子替换，避免中途退出留下半截存档。"""
    try:
        payload = {
            'version': 2,
            'x': round(player_pos.x, 4),
            'z': round(player_pos.z, 4),
            'yaw': round(yaw % 360, 4),
            'pitch': round(pitch, 4),
            'blocks': {f'{x},{y},{z}': block_id for (x, y, z), block_id in world_edits.items()},
            'hotbar': hotbar,
            'selected_slot': selected_slot,
            'day_time': round(day_time, 5),
        }
        tmp = SAVE_FILE.with_name(SAVE_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(SAVE_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False


# ---------- 体素世界数据 ----------
world_blocks = {}      # (x, y, z) -> block_id
world_edits = {}       # 玩家改动：(x, y, z) -> block_id，或 None 表示被挖掉
chunk_blocks = {}      # (cx, cz) -> {(x, y, z), ...}
chunk_meshes = {}      # (cx, cz) -> Entity
chunks_per_axis = math.ceil(WORLD_SIZE / CHUNK_SIZE)
block_tint = color.white   # 昼夜变化时统一乘到所有区块上


def chunk_coord(x, z):
    return (x // CHUNK_SIZE, z // CHUNK_SIZE)


def add_block(x, y, z, block_id):
    world_blocks[(x, y, z)] = block_id
    chunk_blocks.setdefault(chunk_coord(x, z), set()).add((x, y, z))


def remove_block(x, y, z):
    if world_blocks.pop((x, y, z), None) is None:
        return False
    chunk_blocks.get(chunk_coord(x, z), set()).discard((x, y, z))
    return True


# 初始世界分层填充（顶层草方块顶面正好落在 y=0）
_layer_block_ids = []
for _layer_id, _layer_count in WORLD_LAYERS:
    _layer_block_ids.extend(
        [_layer_id if _layer_id in BLOCKS else DEFAULT_BLOCK_ID] * _layer_count)

for _x in range(WORLD_SIZE):
    for _z in range(WORLD_SIZE):
        for _offset, _layer_id in enumerate(_layer_block_ids):
            add_block(_x, MIN_BLOCK_Y + _offset, _z, _layer_id)

# 应用存档里的方块改动（坐标与 ID 都校验，损坏条目直接跳过）
if save_data:
    _saved_edits = save_data.get('blocks')
    if isinstance(_saved_edits, dict):
        for _key, _block_id in list(_saved_edits.items())[:30000]:
            try:
                _x, _y, _z = (int(part) for part in str(_key).split(','))
            except (TypeError, ValueError):
                continue
            if not (0 <= _x < WORLD_SIZE and 0 <= _z < WORLD_SIZE
                    and MIN_BLOCK_Y <= _y < MAX_BLOCK_Y):
                continue
            if _block_id is not None and _block_id not in BLOCKS:
                continue
            if _block_id is None:
                remove_block(_x, _y, _z)
            else:
                add_block(_x, _y, _z, _block_id)
            world_edits[(_x, _y, _z)] = _block_id


# ---------- 键盘 / 鼠标状态 ----------
class PhysicalKeys:
    """优先轮询 X11 的真实输入状态。

    本机 Ursina/Panda3D 的键盘事件层会丢失 key-up（held_keys 只增不减），
    space/shift/escape 也没有事件；鼠标按键事件同样不可靠。物理状态
    不受事件队列影响；非 X11 平台回退到 held_keys / mouse.left/right。
    """
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


app = Ursina()
window.title = '3D World  |  128 x 128'
window.color = color.rgb(145, 200, 240)
window.exit_button.enabled = False   # 右上角开发模式的 X 按钮用不上，隐藏
keyboard = PhysicalKeys()

# ---------- 天空盒（跟随相机，昼夜通过 color 乘色实现） ----------
sky = Sky()

# ---------- 体素区块网格 ----------
# 六个面：邻接方向、4 个顶点偏移、明暗系数
FACES = (
    (( 0,  1,  0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)), 1.00),  # 顶
    (( 0, -1,  0), ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)), 0.45),  # 底
    (( 1,  0,  0), ((1, 0, 1), (1, 1, 1), (1, 1, 0), (1, 0, 0)), 0.80),  # +X
    ((-1,  0,  0), ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), 0.80),  # -X
    (( 0,  0,  1), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)), 0.70),  # +Z
    (( 0,  0, -1), ((1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 0)), 0.70),  # -Z
)


def build_chunk_mesh(cx, cz):
    """把一个区块里所有暴露面合并成一个 Mesh（顶点颜色 + 方块表颜色）。"""
    vertices, triangles, colors, uvs = [], [], [], []
    for (x, y, z) in chunk_blocks.get((cx, cz), ()):
        block_id = world_blocks.get((x, y, z))
        if block_id is None:
            continue
        r, g, b = BLOCKS.get(block_id, BLOCKS[DEFAULT_BLOCK_ID])['color']
        checker = 1.0 if (x + z) % 2 == 0 else 0.94   # 棋盘微调，方便看出 1 米格
        for (nx, ny, nz), corners, shade in FACES:
            if ny == -1 and y == MIN_BLOCK_Y:
                continue                               # 世界最底层不生成底面
            if (x + nx, y + ny, z + nz) in world_blocks:
                continue                               # 相邻方块遮挡，跳过该面
            start = len(vertices)
            factor = shade * checker
            for ox, oy, oz in corners:
                vertices.append((x + ox, y + oy, z + oz))
                colors.append((r / 255 * factor, g / 255 * factor, b / 255 * factor, 1.0))
                uvs.append((0.0, 0.0))
            triangles.extend(((start, start + 1, start + 2), (start, start + 2, start + 3)))
    return Mesh(vertices=vertices, triangles=triangles, colors=colors, uvs=uvs, mode='triangle')


def rebuild_chunk(cx, cz):
    old = chunk_meshes.pop((cx, cz), None)
    if old is not None:
        destroy(old)
    mesh = build_chunk_mesh(cx, cz)
    if mesh.vertices:
        entity = Entity(model=mesh, texture='white_cube')
        entity.set_two_sided(True)   # 兜底：即使绕序偏差也不会出现空洞
        entity.color = block_tint    # 夜间重建的区块也要跟随当前亮度
        chunk_meshes[(cx, cz)] = entity


def rebuild_around(x, z):
    """方块变化后重建所在区块；在区块边缘时连带重建相邻区块。"""
    cx, cz = chunk_coord(x, z)
    affected = {(cx, cz)}
    if x % CHUNK_SIZE == 0 and cx > 0:
        affected.add((cx - 1, cz))
    if x % CHUNK_SIZE == CHUNK_SIZE - 1 and cx < chunks_per_axis - 1:
        affected.add((cx + 1, cz))
    if z % CHUNK_SIZE == 0 and cz > 0:
        affected.add((cx, cz - 1))
    if z % CHUNK_SIZE == CHUNK_SIZE - 1 and cz < chunks_per_axis - 1:
        affected.add((cx, cz + 1))
    for _cx, _cz in affected:
        rebuild_chunk(_cx, _cz)


for _cx in range(chunks_per_axis):
    for _cz in range(chunks_per_axis):
        rebuild_chunk(_cx, _cz)
print(f'[世界] 已生成 {len(chunk_meshes)} 个区块，{len(world_blocks)} 个方块')


# ---------- 射线 / 碰撞辅助 ----------
def voxel_raycast(origin, direction, max_distance):
    """体素 DDA：返回 (命中方块坐标, 进入面法线)，未命中返回 None。"""
    length = math.sqrt(direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2)
    if length == 0:
        return None
    dx, dy, dz = direction[0] / length, direction[1] / length, direction[2] / length

    x, y, z = math.floor(origin[0]), math.floor(origin[1]), math.floor(origin[2])
    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy > 0 else -1
    step_z = 1 if dz > 0 else -1

    inf = float('inf')
    t_delta_x = abs(1.0 / dx) if dx else inf
    t_delta_y = abs(1.0 / dy) if dy else inf
    t_delta_z = abs(1.0 / dz) if dz else inf
    t_max_x = ((x + 1 - origin[0]) / dx) if dx > 0 else (((x - origin[0]) / dx) if dx < 0 else inf)
    t_max_y = ((y + 1 - origin[1]) / dy) if dy > 0 else (((y - origin[1]) / dy) if dy < 0 else inf)
    t_max_z = ((z + 1 - origin[2]) / dz) if dz > 0 else (((z - origin[2]) / dz) if dz < 0 else inf)

    normal = (0, 0, 0)
    distance = 0.0
    for _ in range(128):
        if distance > max_distance:
            break
        if (x, y, z) in world_blocks:
            return (x, y, z), normal
        if t_max_x < t_max_y and t_max_x < t_max_z:
            x += step_x
            distance = t_max_x
            t_max_x += t_delta_x
            normal = (-step_x, 0, 0)
        elif t_max_y < t_max_z:
            y += step_y
            distance = t_max_y
            t_max_y += t_delta_y
            normal = (0, -step_y, 0)
        else:
            z += step_z
            distance = t_max_z
            t_max_z += t_delta_z
            normal = (0, 0, -step_z)
    return None


def ground_height_at(x, z):
    """玩家所在列最高的方块顶面；该列被挖空时返回世界底限，让玩家继续下落。"""
    ix, iz = math.floor(x), math.floor(z)
    for y in range(MAX_BLOCK_Y - 1, MIN_BLOCK_Y - 1, -1):
        if (ix, y, iz) in world_blocks:
            return y + 1
    return FALL_LIMIT_Y


def player_overlaps(x, y, z):
    """判断方块是否与玩家身体重叠，避免把自己封进方块里。"""
    if x != math.floor(player_pos.x) or z != math.floor(player_pos.z):
        return False
    feet = math.floor(player_pos.y + 0.001)
    head = math.floor(player_pos.y + EYE_HEIGHT - 0.001)
    return feet <= y <= head


# ---------- 玩家状态 ----------
player_pos  = Vec3(WORLD_SIZE / 2, 0, WORLD_SIZE / 2)
velocity_y  = 0.0
grounded    = True
current_eye = EYE_HEIGHT
yaw         = 45.0
pitch       = 0.0
hud_timer   = 0.0
hud_frames  = 0
prev_keys   = set()
prev_left   = False
prev_middle = False
prev_right  = False
pending_scroll = 0
notice      = 'LMB dig / RMB place / MMB pick / wheel hotbar / E inventory'
notice_timer = 10.0
autosave_timer = 0.0
default_fov = BASE_FOV
current_fov = BASE_FOV
camera.fov = BASE_FOV
bob_phase = 0.0     # 视角晃动相位
bob_amount = 0.0    # 视角晃动强度（0~1）
menu_state  = {'open': False, 'index': 0}
day_time     = START_DAY_TIME
last_solar   = -2.0   # 用太阳高度角判断是否需要刷新天色（daylight 在黄昏和夜晚都为 0）

# 快捷栏 / 背包物品（当前为创造模式：方块无限，只选择类型）
hotbar = [BLOCK_IDS[i] if i < len(BLOCK_IDS) else None for i in range(HOTBAR_SLOTS)]
inventory = [BLOCK_IDS[i] if i < len(BLOCK_IDS) else None
             for i in range(INVENTORY_COLS * INVENTORY_ROWS)]
selected_slot = 0
inv_selected = 0
inventory_open = False
held_item = None   # 背包里被"拿在鼠标上"的方块 ID

if save_data:
    player_pos.x = _save_number(save_data.get('x'), player_pos.x, PLAYER_RADIUS, WORLD_SIZE - PLAYER_RADIUS)
    player_pos.z = _save_number(save_data.get('z'), player_pos.z, PLAYER_RADIUS, WORLD_SIZE - PLAYER_RADIUS)
    yaw   = _save_number(save_data.get('yaw'), yaw, -360000, 360000) % 360
    pitch = _save_number(save_data.get('pitch'), pitch, -89.0, 89.0)
    day_time = _save_number(save_data.get('day_time'), day_time, 0.0, 1.0) % 1.0
    _saved_hotbar = save_data.get('hotbar')
    if isinstance(_saved_hotbar, list):
        for _i in range(HOTBAR_SLOTS):
            if _i < len(_saved_hotbar):
                _item = _saved_hotbar[_i]
                hotbar[_i] = _item if isinstance(_item, str) and _item in BLOCKS else None
        selected_slot = int(_save_number(save_data.get('selected_slot'), 0, 0, HOTBAR_SLOTS - 1))

camera.position   = player_pos + Vec3(0, current_eye, 0)
camera.rotation_x = pitch
camera.rotation_y = yaw

mouse.locked = True
atexit.register(save_world)   # 覆盖窗口关闭 / alt+F4 等退出路径


# ---------- HUD ----------
hud = Text(
    text='',
    position=(-0.86, 0.47),
    origin=(-0.5, 0.5),
    scale=0.75,
    background=True,
    z=-2,
)

# ---------- 准心 ----------
crosshair = Entity(parent=camera.ui)
Entity(parent=crosshair, model='quad', color=color.rgba(0, 0, 0, .6), scale=(.010, .030), z=-1)
Entity(parent=crosshair, model='quad', color=color.white, scale=(.003, .024), z=-1.01)
Entity(parent=crosshair, model='quad', color=color.white, scale=(.024, .003), z=-1.01)

# ---------- 快捷栏 ----------
hotbar_root = Entity(parent=camera.ui)
hotbar_ui = []
for _i in range(HOTBAR_SLOTS):
    _x = (_i - (HOTBAR_SLOTS - 1) / 2) * (SLOT_SIZE + SLOT_GAP)
    _bg = Entity(parent=hotbar_root, model='quad', color=color.black66,
                 scale=(SLOT_SIZE, SLOT_SIZE), x=_x, y=-.44, z=-1)
    _item = Entity(parent=_bg, model='quad', color=color.white, scale=(.72, .72), z=-.01)
    _label = Text(parent=_bg, text=str(_i + 1), origin=(-.5, -.5),
                  position=(-.44, -.44), scale=.45, z=-.02)
    hotbar_ui.append((_bg, _item, _label))


def slot_color(block_id):
    r, g, b = BLOCKS[block_id]['color']
    return color.rgba(r / 255, g / 255, b / 255, 1)


def refresh_hotbar():
    for i, (bg, item, _label) in enumerate(hotbar_ui):
        block_id = hotbar[i]
        item.enabled = block_id is not None
        if block_id is not None:
            item.color = slot_color(block_id)
        bg.color = color.white if i == selected_slot else color.black66


refresh_hotbar()   # 启动时按 hotbar 数据填充格子颜色

# ---------- 背包（3x9） ----------
inventory_root = Entity(parent=camera.ui, enabled=False)
Entity(parent=inventory_root, model='quad', color=color.black66, scale=(3, 2), z=0)
Text(parent=inventory_root, text='INVENTORY', origin=(0, 0), y=.34, scale=1.5, z=-.02)
Text(parent=inventory_root,
     text='CLICK item to pick up / CLICK hotbar slot to place / E close',
     origin=(0, 0), y=-.35, scale=.6, color=color.gray, z=-.02)

inventory_ui = []
for _row in range(INVENTORY_ROWS):
    for _col in range(INVENTORY_COLS):
        _x = (_col - (INVENTORY_COLS - 1) / 2) * (SLOT_SIZE + SLOT_GAP)
        _y = .12 - _row * (SLOT_SIZE + SLOT_GAP)
        _bg = Entity(parent=inventory_root, model='quad', color=color.black90,
                     scale=(SLOT_SIZE, SLOT_SIZE), x=_x, y=_y, z=-1)
        _item = Entity(parent=_bg, model='quad', color=color.white, scale=(.72, .72), z=-.01)
        inventory_ui.append((_bg, _item))


def refresh_inventory():
    for i, (bg, item) in enumerate(inventory_ui):
        block_id = inventory[i]
        item.enabled = block_id is not None
        if block_id is not None:
            item.color = slot_color(block_id)
        bg.color = color.white if i == inv_selected else color.black90


# 跟随鼠标的"拿在手上"方块图标
held_icon = Entity(parent=camera.ui, model='quad', color=color.white,
                   scale=(SLOT_SIZE * .72, SLOT_SIZE * .72), enabled=False, z=-3)


def slot_index_at(px, py, cols, rows, center_y):
    """判断 UI 坐标落在哪个格子上；返回格子索引，未命中返回 None。"""
    step = SLOT_SIZE + SLOT_GAP
    half = SLOT_SIZE / 2
    col = round(px / step + (cols - 1) / 2)
    row = round((center_y - py) / step)
    if not (0 <= col < cols and 0 <= row < rows):
        return None
    slot_x = (col - (cols - 1) / 2) * step
    slot_y = center_y - row * step
    if abs(px - slot_x) <= half and abs(py - slot_y) <= half:
        return row * cols + col
    return None


def open_inventory():
    global inventory_open
    inventory_open = True
    inventory_root.enabled = True
    refresh_inventory()
    mouse.locked = False


def close_inventory():
    global inventory_open, held_item
    if held_item is not None:      # 关背包时把手上物品放回空位，避免丢失
        for i in range(len(inventory)):
            if inventory[i] is None:
                inventory[i] = held_item
                break
        held_item = None
        held_icon.enabled = False
    inventory_open = False
    inventory_root.enabled = False
    refresh_inventory()
    mouse.locked = True


# ---------- ESC 暂停菜单 ----------
menu_root = Entity(parent=camera.ui, enabled=False)
Entity(parent=menu_root, model='quad', color=color.black66, scale=(3, 2))
Text(parent=menu_root, text='PAUSED', origin=(0, 0), y=.32, scale=2)
menu_status = Text(parent=menu_root, text='', origin=(0, 0), y=-.28, scale=.8)
Text(parent=menu_root,
     text='WASD move / SPACE jump / SHIFT crouch / CTRL sprint / C zoom / LMB dig / RMB place',
     origin=(0, 0), y=-.4, scale=.55, color=color.gray)

menu_labels = ('Resume', 'Save', 'Save & Quit')


def open_menu():
    if inventory_open:            # 菜单优先，先收起背包（顺手回收手上物品）
        close_inventory()
    menu_state['open'] = True
    menu_state['index'] = 0
    menu_status.text = ''
    menu_root.enabled = True
    refresh_menu_highlight()
    mouse.locked = False


def close_menu():
    menu_state['open'] = False
    menu_root.enabled = False
    mouse.locked = True


def menu_save():
    menu_status.text = 'SAVED' if save_world() else 'SAVE FAILED'


def menu_quit():
    save_world()
    application.quit()


menu_buttons = [
    Button(parent=menu_root, text=label, scale=(.5, .07), y=.08 - i * .12, on_click=action)
    for i, (label, action) in enumerate(zip(menu_labels, (close_menu, menu_save, menu_quit)))
]


def refresh_menu_highlight():
    for i, button in enumerate(menu_buttons):
        button.text = f'> {menu_labels[i]} <' if i == menu_state['index'] else f'  {menu_labels[i]}  '


# ---------- 方块选中指示器 ----------
selector = Entity(model='wireframe_cube', color=color.white, scale=1.004, enabled=False)

# ---------- 输入：滚轮 / 窗口点击重新锁定鼠标 ----------
def input(key):
    global pending_scroll
    if key == 'scroll up':
        pending_scroll += 1
    elif key == 'scroll down':
        pending_scroll -= 1
    if key == 'left mouse down' and not menu_state['open'] and not inventory_open and not mouse.locked:
        mouse.locked = True


# ---------- 每帧更新 ----------
def update():
    global velocity_y, grounded, current_eye, yaw, pitch
    global hud_timer, hud_frames, prev_keys, notice, notice_timer, autosave_timer, current_fov
    global prev_left, prev_middle, prev_right, selected_slot, inv_selected, held_item
    global pending_scroll, day_time, last_solar, block_tint, bob_phase, bob_amount

    raw_dt = time.dt
    if raw_dt <= 0:
        return
    dt = min(raw_dt, 0.05)

    # --- 物理按键状态（X11）；非 X11 平台回退到 Ursina 事件层 ---
    keys = keyboard.snapshot()
    if keys is None:
        keys = {k for k in ('w', 'a', 's', 'd', 'space', 'escape', 'f5', 'c', 'e',
                            '1', '2', '3', '4', '5', '6', '7', '8', '9') if held_keys[k]}
        if held_keys['left shift'] or held_keys['right shift'] or held_keys['shift']:
            keys.add('shift')
        if held_keys['left control'] or held_keys['right control'] or held_keys['control']:
            keys.add('ctrl')
        if held_keys['up arrow']:
            keys.add('up')
        if held_keys['down arrow']:
            keys.add('down')
        if held_keys['left arrow']:
            keys.add('left')
        if held_keys['right arrow']:
            keys.add('right')
        if held_keys['enter']:
            keys.add('enter')
    just_pressed = keys - prev_keys
    prev_keys = keys.copy()

    # --- 鼠标按键（物理轮询，上升沿触发一次操作） ---
    buttons = keyboard.mouse_buttons()
    if buttons is None:
        left_down, middle_down, right_down = bool(mouse.left), bool(mouse.middle), bool(mouse.right)
    else:
        left_down, middle_down, right_down = buttons
    left_click = left_down and not prev_left
    middle_click = middle_down and not prev_middle
    right_click = right_down and not prev_right
    prev_left, prev_middle, prev_right = left_down, middle_down, right_down

    # --- ESC：菜单 / 背包 / 打开菜单 ---
    if 'escape' in just_pressed:
        if menu_state['open']:
            close_menu()
        elif inventory_open:
            close_inventory()
        else:
            open_menu()

    # --- E：背包开关（菜单打开时不响应） ---
    if 'e' in just_pressed and not menu_state['open']:
        if inventory_open:
            close_inventory()
        else:
            open_inventory()

    if 'f5' in just_pressed:
        notice, notice_timer = ('SAVED' if save_world() else 'SAVE FAILED'), 1.5

    # --- 定时自动存档 ---
    autosave_timer += raw_dt
    if autosave_timer >= AUTOSAVE_INTERVAL:
        autosave_timer = 0.0
        save_world()

    # --- 菜单打开：暂停游戏，方向键选择、回车确认 ---
    if menu_state['open']:
        if 'up' in just_pressed:
            menu_state['index'] = (menu_state['index'] - 1) % len(menu_buttons)
            refresh_menu_highlight()
        if 'down' in just_pressed:
            menu_state['index'] = (menu_state['index'] + 1) % len(menu_buttons)
            refresh_menu_highlight()
        if 'enter' in just_pressed:
            menu_buttons[menu_state['index']].on_click()
        keys = set()
        just_pressed = set()

    # --- 背包打开：暂停移动，方向键选择、回车放入快捷栏 ---
    if inventory_open:
        moved = False
        if 'left' in just_pressed:
            inv_selected = (inv_selected - 1) % len(inventory)
            moved = True
        if 'right' in just_pressed:
            inv_selected = (inv_selected + 1) % len(inventory)
            moved = True
        if 'up' in just_pressed:
            inv_selected = (inv_selected - INVENTORY_COLS) % len(inventory)
            moved = True
        if 'down' in just_pressed:
            inv_selected = (inv_selected + INVENTORY_COLS) % len(inventory)
            moved = True
        if moved:
            refresh_inventory()
        if 'enter' in just_pressed:
            block_id = inventory[inv_selected]
            if block_id is not None:
                hotbar[selected_slot] = block_id
                refresh_hotbar()
        for _i in range(HOTBAR_SLOTS):
            if str(_i + 1) in just_pressed:
                selected_slot = _i
                refresh_hotbar()

        # 鼠标拖拽：点背包格拿起/放下，点快捷栏格放入
        point = keyboard.pointer_ui_position()
        if point is None:
            point = (mouse.x, mouse.y)
        if left_click and point is not None:
            px, py = point
            inv_idx = slot_index_at(px, py, INVENTORY_COLS, INVENTORY_ROWS, .12)
            hot_idx = slot_index_at(px, py, HOTBAR_SLOTS, 1, -.44)
            if inv_idx is not None:
                item = inventory[inv_idx]
                if held_item is None:
                    if item is not None:
                        held_item = item
                        inventory[inv_idx] = None
                else:
                    inventory[inv_idx] = held_item
                    held_item = item
                refresh_inventory()
            elif hot_idx is not None:
                item = hotbar[hot_idx]
                if held_item is not None:
                    hotbar[hot_idx] = held_item
                    held_item = item
                    selected_slot = hot_idx
                else:
                    selected_slot = hot_idx
                refresh_hotbar()

        # 手上的方块跟随鼠标
        if held_item is not None and point is not None:
            held_icon.position = (point[0], point[1], -3)
            held_icon.color = slot_color(held_item)
            held_icon.enabled = True
        else:
            held_icon.enabled = False

        keys = set()
        just_pressed = set()

    # --- 数字键 / 滚轮切换快捷栏 ---
    if not menu_state['open'] and not inventory_open:
        for _i in range(HOTBAR_SLOTS):
            if str(_i + 1) in just_pressed and selected_slot != _i:
                selected_slot = _i
                refresh_hotbar()
        scroll_steps = pending_scroll
        pending_scroll = 0
        if scroll_steps:
            selected_slot = (selected_slot - scroll_steps) % HOTBAR_SLOTS
            refresh_hotbar()
    else:
        pending_scroll = 0   # 菜单/背包里滚轮不生效，丢弃

    # --- 鼠标视角 ---
    if mouse.locked:
        yaw   += mouse.velocity[0] * MOUSE_SENSITIVITY
        pitch -= mouse.velocity[1] * MOUSE_SENSITIVITY
        pitch = max(-89.0, min(89.0, pitch))

    camera.rotation_y = yaw
    camera.rotation_x = pitch

    # --- 蹲下 / 疾跑（Ctrl） / 跳跃（上升沿） ---
    crouching = 'shift' in keys
    sprinting = 'ctrl' in keys and not crouching
    if 'space' in just_pressed and grounded:
        velocity_y = JUMP_SPEED
        grounded = False

    # --- C 键放大：平滑改变视场角，松开自动恢复 ---
    zooming = 'c' in keys
    target_fov = ZOOM_FOV if zooming else default_fov
    current_fov += (target_fov - current_fov) * min(1.0, dt * FOV_LERP_SPEED)
    if abs(camera.fov - current_fov) > 0.01:
        camera.fov = current_fov

    # --- 水平移动（基于朝向） ---
    fwd  = int('w' in keys) - int('s' in keys)
    side = int('d' in keys) - int('a' in keys)
    current_speed = 0.0

    if fwd or side:
        yr      = math.radians(yaw)
        forward = Vec3(math.sin(yr), 0, math.cos(yr))
        right   = Vec3(math.cos(yr), 0, -math.sin(yr))
        move    = (forward * fwd + right * side).normalized()

        # 蹲行优先于疾跑，避免同时按住 Shift+Ctrl 时互相打架
        speed = CROUCH_SPEED if crouching else (SPRINT_SPEED if sprinting else WALK_SPEED)
        current_speed = speed
        next_x = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS,
                                        player_pos.x + move.x * speed * dt))
        next_z = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS,
                                        player_pos.z + move.z * speed * dt))

        # 台阶检测：1 格台阶自动跳上去，超过配置高度的方块直接挡住（不再瞬移）
        step_up = ground_height_at(next_x, next_z) - player_pos.y
        if step_up <= 0.01:
            player_pos.x, player_pos.z = next_x, next_z
        elif grounded and step_up <= AUTO_JUMP_HEIGHT + 0.01 and AUTO_JUMP:
            # 按台阶高度给足起跳速度，让玩家沿抛物线跳上去，有完整的跳跃过程
            velocity_y = max(JUMP_SPEED, math.sqrt(2 * GRAVITY * (step_up + 0.25)))
            grounded = False
            player_pos.x, player_pos.z = next_x, next_z

    # 世界边界：每帧钳制，任何方式都不会走出世界
    player_pos.x = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS, player_pos.x))
    player_pos.z = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS, player_pos.z))

    # --- 重力与方块支撑（站到放置的方块上） ---
    ground_y = ground_height_at(player_pos.x, player_pos.z)
    velocity_y   -= GRAVITY * dt
    player_pos.y += velocity_y * dt
    if player_pos.y <= ground_y:
        player_pos.y = ground_y
        velocity_y   = 0
        grounded     = True

    # 掉出世界：低于底限就传送回出生点
    if player_pos.y <= FALL_LIMIT_Y:
        player_pos.x = WORLD_SIZE / 2
        player_pos.z = WORLD_SIZE / 2
        spawn_ground = ground_height_at(player_pos.x, player_pos.z)
        player_pos.y = max(0.0, spawn_ground) + 0.05
        velocity_y = 0
        grounded = True
        notice, notice_timer = 'FELL OUT OF WORLD - TELEPORTED TO SPAWN', 3.0

    # --- 眼高平滑过渡 ---
    target_eye = CROUCH_EYE_HEIGHT if crouching else EYE_HEIGHT
    current_eye += (target_eye - current_eye) * min(1.0, dt * EYE_LERP_SPEED)

    # --- 移动时的视角晃动（view_bob 可配置，0 关闭） ---
    moving = bool(fwd or side) and grounded
    bob_amount += ((1.0 if moving else 0.0) - bob_amount) * min(1.0, dt * 8)
    if moving and current_speed > 0:
        bob_phase += dt * 9.0 * (current_speed / WALK_SPEED)
    bob_y = math.sin(bob_phase) * VIEW_BOB * bob_amount
    bob_x = math.sin(bob_phase * 0.5) * VIEW_BOB * 0.4 * bob_amount
    yr = math.radians(yaw)
    camera.position = player_pos + Vec3(
        math.cos(yr) * bob_x,
        current_eye + bob_y,
        -math.sin(yr) * bob_x,
    )

    # --- 准星射线 / 选中框 / 挖掘 / 放置 ---
    active = not menu_state['open'] and not inventory_open
    hit = voxel_raycast(camera.world_position, camera.forward, REACH_DISTANCE) if active else None

    show_selector = hit is not None
    if selector.enabled != show_selector:
        selector.enabled = show_selector
    if hit is not None:
        hx, hy, hz = hit[0]
        selector.position = (hx + .5, hy + .5, hz + .5)

    if hit is not None:
        (hx, hy, hz), normal = hit
        if middle_click:   # 中键取方块：快捷栏已有就切过去，没有就放进当前格
            picked = world_blocks.get((hx, hy, hz))
            if picked is not None:
                if picked in hotbar:
                    selected_slot = hotbar.index(picked)
                else:
                    hotbar[selected_slot] = picked
                refresh_hotbar()
        if left_click:
            if world_blocks.get((hx, hy, hz)) == 'worldbox:bedrock.block':
                notice, notice_timer = 'BEDROCK - unbreakable', 1.5
            elif remove_block(hx, hy, hz):
                world_edits[(hx, hy, hz)] = None
                rebuild_around(hx, hz)
        if right_click and normal != (0, 0, 0):
            tx, ty, tz = hx + normal[0], hy + normal[1], hz + normal[2]
            block_id = hotbar[selected_slot]
            if (block_id is not None
                    and 0 <= tx < WORLD_SIZE and 0 <= tz < WORLD_SIZE
                    and MIN_BLOCK_Y <= ty < MAX_BLOCK_Y
                    and (tx, ty, tz) not in world_blocks
                    and not player_overlaps(tx, ty, tz)):
                add_block(tx, ty, tz, block_id)
                world_edits[(tx, ty, tz)] = block_id
                rebuild_around(tx, tz)

    if crosshair.enabled != active:
        crosshair.enabled = active
    if hotbar_root.enabled == menu_state['open']:
        hotbar_root.enabled = not menu_state['open']

    # --- 区域化视距剔除 ---
    view_sq = VIEW_DISTANCE * VIEW_DISTANCE
    for (cx, cz), entity in chunk_meshes.items():
        center_x = cx * CHUNK_SIZE + CHUNK_SIZE / 2
        center_z = cz * CHUNK_SIZE + CHUNK_SIZE / 2
        dx = max(abs(center_x - player_pos.x) - CHUNK_SIZE / 2, 0)
        dz = max(abs(center_z - player_pos.z) - CHUNK_SIZE / 2, 0)
        visible = (dx * dx + dz * dz) <= view_sq
        if entity.enabled != visible:
            entity.enabled = visible

    # --- 昼夜更替：0=午夜, 0.25=日出, 0.5=正午, 0.75=日落 ---
    day_time = (day_time + raw_dt / DAY_LENGTH) % 1.0
    solar = math.sin((day_time - 0.25) * math.tau)
    daylight = max(0.0, solar)
    if abs(solar - last_solar) > 0.005:
        last_solar = solar
        # 注意：Entity.color 直接作为 color scale 使用，必须是 0~1 的 rgba
        block_tint = color.rgba(
            min(1.0, (0.35 + 0.65 * daylight) * BRIGHTNESS),
            min(1.0, (0.38 + 0.62 * daylight) * BRIGHTNESS),
            min(1.0, (0.55 + 0.45 * daylight) * BRIGHTNESS), 1)
        for _entity in chunk_meshes.values():
            _entity.color = block_tint
        if solar >= 0:      # 日出 → 白天
            _t = min(1.0, solar * 2.5)
            _sr, _sg, _sb = 1.0, 0.55 + 0.45 * _t, 0.40 + 0.60 * _t
        else:               # 日落 → 夜晚
            _t = min(1.0, -solar * 2.5)
            _sr = 1.0 + (0.12 - 1.0) * _t
            _sg = 0.55 + (0.16 - 0.55) * _t
            _sb = 0.40 + (0.32 - 0.40) * _t
        _sr = min(1.0, _sr * BRIGHTNESS)
        _sg = min(1.0, _sg * BRIGHTNESS)
        _sb = min(1.0, _sb * BRIGHTNESS)
        sky.color = color.rgba(_sr, _sg, _sb, 1)
        window.color = color.rgba(_sr, _sg, _sb, 1)

    # --- HUD：按间隔刷新，Text setter 每次都会重建文本节点 ---
    hud_timer += raw_dt
    hud_frames += 1
    if notice_timer > 0:
        notice_timer -= raw_dt
        if notice_timer <= 0:
            notice = ''
    if hud_timer >= HUD_INTERVAL:
        if menu_state['open']:
            hud.text = 'MENU'
        elif inventory_open:
            hud.text = 'INVENTORY'
        else:
            flags = [name for name, on in
                     (('CROUCH', crouching), ('SPRINT', sprinting), ('ZOOM', zooming)) if on]
            flags_text = ('  [' + ' '.join(flags) + ']') if flags else ''
            block_id = hotbar[selected_slot]
            block_name = BLOCK_NAMES.get(block_id, 'Air') if block_id else 'Air'
            clock = int(day_time * 24 * 60) % (24 * 60)
            hud.text = (
                f'FPS {int(hud_frames / hud_timer):3d}   '
                f'X {player_pos.x:6.1f}  Y {player_pos.y:5.2f}  Z {player_pos.z:6.1f}   '
                f'EYE {current_eye:.2f} m   {clock // 60:02d}:{clock % 60:02d}{flags_text}   {block_name}'
                f'{"  [" + notice + "]" if notice else ""}'
            )
        hud_timer = 0.0
        hud_frames = 0


app.run()
