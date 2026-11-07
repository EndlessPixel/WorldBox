"""全局配置：setting.json 加载与所有可调参数。"""

import json
import math
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / 'config'

# 配置文件优先放 config/ 目录，同时兼容放在项目根目录的旧布局
SETTINGS_FILE = CONFIG_DIR / 'setting.json'
BLOCKS_FILE = CONFIG_DIR / 'blocks.json'
# 资源包定义目录（默认世界不下载纹理，用程序生成的噪声材质）
RESOURCE_PACK_DIR = CONFIG_DIR / 'resource_packs'
if not SETTINGS_FILE.exists() and (ROOT_DIR / 'setting.json').exists():
    SETTINGS_FILE = ROOT_DIR / 'setting.json'
if not BLOCKS_FILE.exists() and (ROOT_DIR / 'blocks.json').exists():
    BLOCKS_FILE = ROOT_DIR / 'blocks.json'
SAVE_FILE = ROOT_DIR / 'world_save.json'

# 中文字体：放进 assets/ 才能被 Ursina 的字体查找器找到
CJK_FONT = None
if (ROOT_DIR / 'assets' / 'fonts' / 'NotoSansCJK-Regular.ttc').exists():
    CJK_FONT = 'fonts/NotoSansCJK-Regular.ttc'

DEFAULT_SETTINGS = {
    'auto_jump': True,          # 是否自动跳上台阶
    'auto_jump_height': 1.0,    # 自动跳跃能跨过的高度（格）
    'view_distance': 96,        # 视距（米）
    'fov': 40,                  # 基础视场角
    'view_bob': 0.03,           # 移动时视角晃动幅度（米）
    'brightness': 1.0,          # 画面亮度（0.3 ~ 2.0）
    'language': 'zh',           # 界面语言：zh / en
    'resource_pack': '',        # 资源包 id（'' = 自带默认包 worldbox）
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
    if raw.get('language') in ('zh', 'en'):
        settings['language'] = raw['language']
    pack = raw.get('resource_pack')
    if isinstance(pack, str):
        settings['resource_pack'] = pack.strip()
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
# ===========================================


def save_settings():
    """原子写回 setting.json。"""
    try:
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, ensure_ascii=False, indent=2)
        tmp.replace(SETTINGS_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False


def apply_settings(updates):
    """运行时应用设置（同步模块级常量）并写回文件。"""
    global VIEW_DISTANCE, AUTO_JUMP, AUTO_JUMP_HEIGHT, BASE_FOV, VIEW_BOB, BRIGHTNESS, ZOOM_FOV

    if isinstance(updates.get('auto_jump'), bool):
        SETTINGS['auto_jump'] = updates['auto_jump']
    for key, low, high in (('auto_jump_height', 0.5, 2.0),
                           ('view_distance', 16, 256),
                           ('fov', 20, 120),
                           ('view_bob', 0.0, 0.2),
                           ('brightness', 0.3, 2.0)):
        if key in updates:
            SETTINGS[key] = _cfg_number(updates[key], SETTINGS[key], low, high)
    if updates.get('language') in ('zh', 'en'):
        SETTINGS['language'] = updates['language']
    if isinstance(updates.get('resource_pack'), str):
        SETTINGS['resource_pack'] = updates['resource_pack'].strip()

    AUTO_JUMP = SETTINGS['auto_jump']
    AUTO_JUMP_HEIGHT = SETTINGS['auto_jump_height']
    VIEW_DISTANCE = SETTINGS['view_distance']
    BASE_FOV = SETTINGS['fov']
    VIEW_BOB = SETTINGS['view_bob']
    BRIGHTNESS = SETTINGS['brightness']
    ZOOM_FOV = min(15, BASE_FOV * 0.6)
    return save_settings()
