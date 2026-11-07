"""
3D 世界 - Python + Ursina
=========================
- 128x128 米绿色方块平地（每方块 1 米）
- 区域化构建：每 16x16 米合并成 1 个区块（共 64 个区块），
  用纹理平铺表现方块，避免创建 16384 个实体导致的性能问题
- 第一人称：WASD 移动 / Ctrl 疾跑 / 空格跳跃 / Shift 蹲下 / C 放大 / 鼠标转视角
- 摄像机眼高 1.75 m（蹲下平滑过渡到 1.0 m）
- ESC 打开暂停菜单（继续 / 存档 / 保存并退出），支持鼠标点击与方向键+回车
- 存档：同目录 world_save.json，启动时读取，退出时自动保存

安装：pip install ursina
"""

from ursina import *
from panda3d.core import SamplerState
from PIL import Image, ImageDraw
from pathlib import Path
import atexit
import ctypes
import json
import math
import random

# ================= 可调参数 =================
WORLD_SIZE        = 128     # 世界边长（米）
CHUNK_SIZE        = 16      # 每个区块边长（米），128/16 = 8x8 = 64 个区块
VIEW_DISTANCE     = 96      # 区块可见距离（米）

EYE_HEIGHT        = 1.75    # 站立眼高（米）
CROUCH_EYE_HEIGHT = 1.00    # 蹲下眼高（米）
WALK_SPEED        = 6.0     # 走路速度 m/s
SPRINT_SPEED      = 9.5     # 疾跑速度 m/s（按住 Ctrl）
CROUCH_SPEED      = 2.5     # 蹲行速度 m/s
ZOOM_FOV          = 15      # C 键放大时的视场角（Ursina 默认 40，越小放大越多）
FOV_LERP_SPEED    = 10      # 变焦过渡速度
GRAVITY           = 25.0    # 重力 m/s^2
JUMP_SPEED        = 8.0     # 起跳速度 m/s
MOUSE_SENSITIVITY = 40      # 鼠标灵敏度
EYE_LERP_SPEED    = 12      # 眼高过渡速度
PLAYER_RADIUS     = 0.4     # 玩家半径（用于边界限制）
HUD_INTERVAL      = 0.1     # HUD 刷新间隔（秒），避免每帧重建文本网格
AUTOSAVE_INTERVAL = 30.0    # 自动存档间隔（秒）
WORLD_SEED        = 20261107  # 地面噪点种子，随存档一起持久化
SAVE_FILE         = Path(__file__).resolve().with_name('world_save.json')
# ===========================================

# ---------- 存档：保存玩家状态与地面种子 ----------
def load_save():
    """读取存档；文件损坏或版本不兼容时返回 None。"""
    try:
        with SAVE_FILE.open(encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get('version') != 1:
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
world_seed = WORLD_SEED
if save_data:
    try:
        world_seed = int(save_data.get('seed', WORLD_SEED))
    except (TypeError, ValueError):
        world_seed = WORLD_SEED
print(f'[存档] {"已读取 " + SAVE_FILE.name if save_data else "无存档，使用默认世界"}')


def save_world():
    """先写临时文件再原子替换，避免中途退出留下半截存档。"""
    try:
        payload = {
            'version': 1,
            'seed': world_seed,
            'x': round(player_pos.x, 4),
            'z': round(player_pos.z, 4),
            'yaw': round(yaw % 360, 4),
            'pitch': round(pitch, 4),
        }
        tmp = SAVE_FILE.with_name(SAVE_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(SAVE_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False


# ---------- 键盘状态 ----------
class PhysicalKeys:
    """优先用 XQueryKeymap 轮询物理按键。

    本机 Ursina/Panda3D 的键盘事件层会丢失 key-up（held_keys 只增不减，
    WASD 停不下来），且空格/Shift/ESC 收不到事件（跳跃、蹲下、退出失效）。
    物理状态不受事件队列影响；非 X11 平台回退到 held_keys。
    """
    KEYSYMS = {
        'w': 0x77, 'a': 0x61, 's': 0x73, 'd': 0x64, 'c': 0x63,
        'space': 0x20, 'escape': 0xff1b, 'f5': 0xffc2,
        'shift_l': 0xffe1, 'shift_r': 0xffe2,
        'lcontrol': 0xffe3, 'rcontrol': 0xffe4,
        'up': 0xff52, 'down': 0xff54, 'enter': 0xff0d, 'kp_enter': 0xff8d,
    }
    # 左右修饰键与小键盘回车统一成逻辑键名
    ALIASES = {
        'shift_l': 'shift', 'shift_r': 'shift',
        'lcontrol': 'ctrl', 'rcontrol': 'ctrl',
        'kp_enter': 'enter',
    }

    def __init__(self):
        self._x11 = None
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
        display = x11.XOpenDisplay(None)
        if not display:
            return

        self._x11 = x11
        self._display = display
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


app = Ursina()
window.title = '3D World  |  128 x 128'
window.color = color.rgb(145, 200, 240)
keyboard = PhysicalKeys()

# ---------- 生成绿色方块地面纹理 ----------
def make_ground_texture(seed):
    rng = random.Random(seed)  # 固定种子，保证读档前后地面外观一致
    px = 64
    img = Image.new('RGB', (px, px), (92, 172, 78))
    draw = ImageDraw.Draw(img)

    # 噪点，让方块看起来不那么呆板
    for _ in range(500):
        x, y = rng.randrange(px), rng.randrange(px)
        r, g, b = img.getpixel((x, y))
        d = rng.randint(-15, 15)
        draw.point((x, y), fill=(
            max(0, min(255, r + d)),
            max(0, min(255, g + d)),
            max(0, min(255, b + d)),
        ))

    # 1 米方块描边
    draw.rectangle([0, 0, px - 1, px - 1], outline=(52, 108, 42), width=4)

    # 直接由内存图像创建纹理：省去磁盘 I/O，也避免临时文件的竞态与残留。
    # Texture 构造器不接受 wrap_u/wrap_v，平铺需通过 repeat 属性设置。
    texture = Texture(img)
    texture.repeat = SamplerState.WM_repeat  # 与 texture_scale 配合实现 1 米方格平铺
    return texture

ground_texture = make_ground_texture(world_seed)

# ---------- 区域化构建地面 ----------
chunks = []
# 向上取整，保证 WORLD_SIZE 不能被 CHUNK_SIZE 整除时边缘条带也被覆盖
chunks_per_axis = math.ceil(WORLD_SIZE / CHUNK_SIZE)

for cx in range(chunks_per_axis):
    for cz in range(chunks_per_axis):
        # 最后一个区块按剩余尺寸裁剪，不越出世界边界
        size_x = min(CHUNK_SIZE, WORLD_SIZE - cx * CHUNK_SIZE)
        size_z = min(CHUNK_SIZE, WORLD_SIZE - cz * CHUNK_SIZE)
        chunk = Entity(
            model='plane',
            texture=ground_texture,
            texture_scale=(size_x, size_z),  # 纹理平铺 size 次 → 每格 1 米
            scale=(size_x, 1, size_z),
            position=(
                cx * CHUNK_SIZE + size_x / 2,
                0,
                cz * CHUNK_SIZE + size_z / 2,
            ),
        )
        chunks.append(chunk)

print(f'[世界] 已生成 {len(chunks)} 个区块，覆盖 {WORLD_SIZE} x {WORLD_SIZE} 米')

# ---------- 玩家状态 ----------
player_pos  = Vec3(WORLD_SIZE / 2, 0, WORLD_SIZE / 2)
velocity_y  = 0.0
grounded    = True
current_eye = EYE_HEIGHT
yaw         = 45.0
pitch       = 0.0
hud_timer   = 0.0   # HUD 计时（使用未钳制的真实帧时长）
hud_frames  = 0     # 统计周期内帧数，用于计算平均 FPS
prev_keys   = set()  # 上一帧按下的键，用于检测"刚按下"
menu_state  = {'open': False, 'index': 0}  # ESC 暂停菜单状态
notice      = 'WASD move | CTRL sprint | C zoom | ESC menu'
notice_timer = 8.0
autosave_timer = 0.0
current_fov = camera.fov   # C 键放大用；默认视场角直接取自 Ursina
default_fov = camera.fov

# 恢复存档：坐标与角度都做钳制，防止损坏的存档把玩家送出世界
if save_data:
    player_pos.x = _save_number(save_data.get('x'), player_pos.x, PLAYER_RADIUS, WORLD_SIZE - PLAYER_RADIUS)
    player_pos.z = _save_number(save_data.get('z'), player_pos.z, PLAYER_RADIUS, WORLD_SIZE - PLAYER_RADIUS)
    yaw   = _save_number(save_data.get('yaw'), yaw, -360000, 360000) % 360
    pitch = _save_number(save_data.get('pitch'), pitch, -89.0, 89.0)

camera.position   = player_pos + Vec3(0, current_eye, 0)
camera.rotation_x = pitch
camera.rotation_y = yaw

mouse.locked = True
atexit.register(save_world)  # 覆盖窗口关闭 / alt+F4 等退出路径

# ---------- HUD ----------
hud = Text(
    text='',
    position=(-0.86, 0.47),
    origin=(-0.5, 0.5),
    scale=0.75,
    background=True,
)

# ---------- ESC 暂停菜单 ----------
menu_root = Entity(parent=camera.ui, enabled=False)
Entity(parent=menu_root, model='quad', color=color.black66, scale=(3, 2))
Text(parent=menu_root, text='PAUSED', origin=(0, 0), y=.32, scale=2)
menu_status = Text(parent=menu_root, text='', origin=(0, 0), y=-.28, scale=.8)
Text(parent=menu_root, text='WASD move / SPACE jump / SHIFT crouch / CTRL sprint / C zoom',
     origin=(0, 0), y=-.4, scale=.6, color=color.gray)

menu_labels = ('Resume', 'Save', 'Save & Quit')


def open_menu():
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


# ---------- 输入：菜单打开时左键点按钮，其余情况点击窗口重新锁定鼠标 ----------
def input(key):
    if key == 'left mouse down' and not menu_state['open'] and not mouse.locked:
        mouse.locked = True

# ---------- 每帧更新 ----------
def update():
    global velocity_y, grounded, current_eye, yaw, pitch
    global hud_timer, hud_frames, prev_keys, notice, notice_timer, autosave_timer, current_fov

    raw_dt = time.dt
    if raw_dt <= 0:
        return
    dt = min(raw_dt, 0.05)  # 限制最大步长，防止卡顿时穿模/跳跃异常；raw_dt 仅用于 FPS 统计

    # --- 物理按键状态（X11）；非 X11 平台回退到 Ursina 事件层 ---
    keys = keyboard.snapshot()
    if keys is None:
        keys = {k for k in ('w', 'a', 's', 'd', 'space', 'escape', 'f5', 'c') if held_keys[k]}
        if held_keys['left shift'] or held_keys['right shift'] or held_keys['shift']:
            keys.add('shift')
        if held_keys['left control'] or held_keys['right control'] or held_keys['control']:
            keys.add('ctrl')
        if held_keys['up arrow']:
            keys.add('up')
        if held_keys['down arrow']:
            keys.add('down')
        if held_keys['enter']:
            keys.add('enter')
    just_pressed = keys - prev_keys
    prev_keys = keys.copy()

    # --- ESC 开关菜单；F5 手动存档 ---
    if 'escape' in just_pressed:
        if menu_state['open']:
            close_menu()
        else:
            open_menu()
    if 'f5' in just_pressed:
        notice, notice_timer = ('SAVED' if save_world() else 'SAVE FAILED'), 1.5

    # --- 定时自动存档，防止意外退出丢失进度 ---
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

    # --- 鼠标视角 ---
    if mouse.locked:
        yaw   += mouse.velocity[0] * MOUSE_SENSITIVITY
        pitch -= mouse.velocity[1] * MOUSE_SENSITIVITY
        pitch = max(-89.0, min(89.0, pitch))

    camera.rotation_y = yaw
    camera.rotation_x = pitch

    # --- 蹲下 / 疾跑（Ctrl） / 跳跃（跳跃取上升沿，按住空格不会连跳） ---
    crouching = 'shift' in keys
    sprinting = 'ctrl' in keys and not crouching
    if 'space' in just_pressed and grounded:
        velocity_y = JUMP_SPEED
        grounded = False

    # --- C 键放大：平滑改变视场角，松开自动恢复 ---
    zooming = 'c' in keys
    target_fov = ZOOM_FOV if zooming else default_fov
    current_fov += (target_fov - current_fov) * min(1.0, dt * FOV_LERP_SPEED)
    if abs(camera.fov - current_fov) > 0.01:   # 仅在变化时更新 lens，避免每帧重建投影矩阵
        camera.fov = current_fov

    # --- 水平移动（基于朝向） ---
    fwd  = int('w' in keys) - int('s' in keys)
    side = int('d' in keys) - int('a' in keys)

    if fwd or side:
        yr      = math.radians(yaw)
        forward = Vec3(math.sin(yr), 0, math.cos(yr))
        right   = Vec3(math.cos(yr), 0, -math.sin(yr))
        move    = (forward * fwd + right * side).normalized()

        # 蹲行优先于疾跑，避免同时按住 Shift+Ctrl 时互相打架
        speed = CROUCH_SPEED if crouching else (SPRINT_SPEED if sprinting else WALK_SPEED)
        player_pos.x += move.x * speed * dt
        player_pos.z += move.z * speed * dt

        # 世界边界
        player_pos.x = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS, player_pos.x))
        player_pos.z = max(PLAYER_RADIUS, min(WORLD_SIZE - PLAYER_RADIUS, player_pos.z))

    # --- 重力与落地 ---
    velocity_y   -= GRAVITY * dt
    player_pos.y += velocity_y * dt
    if player_pos.y <= 0:
        player_pos.y = 0
        velocity_y   = 0
        grounded     = True

    # --- 眼高平滑过渡（蹲下/站起） ---
    target_eye = CROUCH_EYE_HEIGHT if crouching else EYE_HEIGHT
    current_eye += (target_eye - current_eye) * min(1.0, dt * EYE_LERP_SPEED)

    camera.position = player_pos + Vec3(0, current_eye, 0)

    # --- 区域化视距剔除 ---
    view_sq = VIEW_DISTANCE * VIEW_DISTANCE
    for c in chunks:
        # 用区块 AABB 到玩家的最近距离判断，避免按中心点判断把脚下/近处区块误隐藏
        dx = max(abs(c.x - player_pos.x) - c.scale_x / 2, 0)
        dz = max(abs(c.z - player_pos.z) - c.scale_z / 2, 0)
        visible = (dx * dx + dz * dz) <= view_sq
        if c.enabled != visible:  # enabled setter 会 stash/unstash，仅在状态变化时写入
            c.enabled = visible

    # --- HUD：Text 的 setter 每次都重建文本节点，按间隔刷新并统计平均 FPS ---
    # 标签用 ASCII，避免 Ursina 默认字体缺中文字形而不断打印警告
    hud_timer += raw_dt
    hud_frames += 1
    if notice_timer > 0:
        notice_timer -= raw_dt
        if notice_timer <= 0:
            notice = ''
    if hud_timer >= HUD_INTERVAL:
        if menu_state['open']:
            hud.text = 'MENU'
        else:
            flags = [name for name, active in
                     (('CROUCH', crouching), ('SPRINT', sprinting), ('ZOOM', zooming)) if active]
            flags_text = ('  [' + ' '.join(flags) + ']') if flags else ''
            hud.text = (
                f'FPS {int(hud_frames / hud_timer):3d}   '
                f'X {player_pos.x:6.1f}  Y {player_pos.y:5.2f}  Z {player_pos.z:6.1f}   '
                f'EYE {current_eye:.2f} m{flags_text}'
                f'{"  [" + notice + "]" if notice else ""}'
            )
        hud_timer = 0.0
        hud_frames = 0

app.run()