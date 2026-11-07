"""按键绑定：action -> 物理键名，持久化到 config/keys.json。

游戏内部始终使用默认键名（w/space/escape...）判断动作；这里负责把
玩家自定义的绑定键「翻译」成内部键名，这样 player/ui/game 都不用改。
"""

import json

from . import config
from .inputs import PhysicalKeys

# 动作 -> 默认键名。顺序就是配置页里的显示顺序。
DEFAULT_BINDINGS = {
    'forward': 'w',
    'back': 's',
    'left': 'a',
    'right': 'd',
    'jump': 'space',
    'crouch': 'shift',
    'sprint': 'ctrl',
    'zoom': 'c',
    'inventory': 'e',
    'menu': 'escape',
    'save': 'f5',
    'map': 'm',
}

VALID_KEYS = (set(PhysicalKeys.KEYSYMS) | set(PhysicalKeys.ALIASES.values())
              | set(DEFAULT_BINDINGS.values()))
INTERNAL_KEYS = set(DEFAULT_BINDINGS.values())

BINDINGS = dict(DEFAULT_BINDINGS)


def load():
    """读取并校验 keys.json；坏值、重复绑定一律回退默认。"""
    global BINDINGS
    BINDINGS = dict(DEFAULT_BINDINGS)
    try:
        with config.KEYS_FILE.open(encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError, TypeError):
        return
    if not isinstance(raw, dict):
        return
    used = set()
    for action, key in raw.items():
        if (action not in DEFAULT_BINDINGS or not isinstance(key, str)
                or key not in VALID_KEYS or key in used):
            continue
        used.add(key)
        BINDINGS[action] = key
    # 上面按顺序覆盖可能留下重复（默认值被别的动作占用），再清理一次
    for action, key in list(BINDINGS.items()):
        others = [a for a, k in BINDINGS.items() if a != action and k == key]
        if others:
            BINDINGS[action] = DEFAULT_BINDINGS[action]


def save():
    """原子写回 keys.json。"""
    try:
        config.KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.KEYS_FILE.with_name(config.KEYS_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(BINDINGS, f, ensure_ascii=False, indent=2)
        tmp.replace(config.KEYS_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False


def set_binding(action, key):
    """绑定一个动作；若该键已被其他动作占用，则两者互换。"""
    if action not in DEFAULT_BINDINGS or key not in VALID_KEYS:
        return False
    old = BINDINGS[action]
    for other, bound in list(BINDINGS.items()):
        if other != action and bound == key:
            BINDINGS[other] = old
    BINDINGS[action] = key
    return save()


def reset():
    global BINDINGS
    BINDINGS = dict(DEFAULT_BINDINGS)
    return save()


def canonicalize(keys):
    """把物理按键集合翻译成游戏内部键名集合。"""
    result = {key for key in keys if key not in INTERNAL_KEYS}
    for action, bound in BINDINGS.items():
        if bound in keys:
            result.add(DEFAULT_BINDINGS[action])
    return result


def display(key):
    """配置页里显示的按键名。"""
    names = {
        'space': 'SPACE', 'escape': 'ESC', 'shift': 'SHIFT', 'ctrl': 'CTRL',
        'alt': 'ALT', 'enter': 'ENTER', 'tab': 'TAB',
        'up': 'UP', 'down': 'DOWN', 'left': 'LEFT', 'right': 'RIGHT',
        'backspace': 'BACKSPACE', 'delete': 'DEL',
    }
    return names.get(key, key.upper())


load()
