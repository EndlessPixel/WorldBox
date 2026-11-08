"""多存档与玩家档案：saves/ 目录管理、旧存档迁移。

存档结构：
    saves/<存档名>/world.json      # 与旧 world_save.json 相同的内容
玩家档案：
    config/player.json             # {'name': 玩家名}
首次运行会把根目录旧 world_save.json 迁移为第一个存档（不删除原文件）。
"""

import json
import re
import shutil
from pathlib import Path

from . import config

SAVES_DIR = config.ROOT_DIR / 'saves'
PLAYER_FILE = config.CONFIG_DIR / 'player.json'
SAVE_FILE_NAME = 'world.json'
NAME_MAX_LEN = 24
# 存档名不允许出现的字符（路径安全）
_NAME_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_name(name):
    """过滤存档/玩家名：去首尾空白与非法字符，限制长度。"""
    text = _NAME_BAD.sub('', str(name or '')).strip()
    text = text.replace('..', '')          # 防目录穿越
    return text[:NAME_MAX_LEN]


def save_dir(name):
    return SAVES_DIR / name


def save_file(name):
    return save_dir(name) / SAVE_FILE_NAME


# ---------- 玩家档案 ----------
def load_player():
    """读取玩家档案；没有或损坏时返回 None。"""
    try:
        with PLAYER_FILE.open(encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    name = sanitize_name(data.get('name'))
    if not name:
        return None
    return {'name': name}


def save_player(name):
    """写入玩家档案（原子替换）。"""
    name = sanitize_name(name)
    if not name:
        return False
    try:
        PLAYER_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PLAYER_FILE.with_name(PLAYER_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump({'name': name}, f, ensure_ascii=False, indent=2)
        tmp.replace(PLAYER_FILE)
        return True
    except OSError:
        return False


# ---------- 存档列表 ----------
def list_saves():
    """[{name, path, mtime, blocks}]，按修改时间从新到旧。"""
    saves = []
    if not SAVES_DIR.is_dir():
        return saves
    for entry in SAVES_DIR.iterdir():
        if not entry.is_dir():
            continue
        path = entry / SAVE_FILE_NAME
        if not path.is_file():
            continue
        info = {'name': entry.name, 'path': path,
                'mtime': path.stat().st_mtime, 'blocks': 0}
        try:
            with path.open(encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get('blocks'), dict):
                info['blocks'] = len(data['blocks'])
        except (OSError, ValueError, TypeError):
            pass
        saves.append(info)
    saves.sort(key=lambda item: item['mtime'], reverse=True)
    return saves


def create_save(name):
    """新建存档目录；重名或非法名返回 None。"""
    name = sanitize_name(name)
    if not name or save_file(name).exists():
        return None
    try:
        save_dir(name).mkdir(parents=True, exist_ok=True)
        return save_dir(name)
    except OSError:
        return None


def delete_save(name):
    """删除存档目录。"""
    name = sanitize_name(name)
    if not name:
        return False
    directory = save_dir(name)
    if not directory.is_dir():
        return False
    try:
        shutil.rmtree(directory)
        return True
    except OSError:
        return False


def rename_save(old_name, new_name):
    """重命名存档目录。"""
    old_name, new_name = sanitize_name(old_name), sanitize_name(new_name)
    if not old_name or not new_name or old_name == new_name:
        return False
    if save_file(new_name).exists():
        return False
    try:
        save_dir(old_name).rename(save_dir(new_name))
        return True
    except OSError:
        return False


# ---------- 读写 ----------
def load_save(path):
    """读取存档；损坏或不兼容时返回 None。"""
    try:
        with Path(path).open(encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('version') not in (1, 2):
        return None
    return data


def save_payload(path, payload):
    """原子写回存档。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
        return True
    except (OSError, TypeError, ValueError):
        return False


def migrate_legacy():
    """把根目录旧 world_save.json 迁移为 saves/ 下第一个存档。"""
    legacy = config.ROOT_DIR / 'world_save.json'
    if not legacy.is_file() or list_saves():
        return None
    data = load_save(legacy)
    if data is None:
        return None
    from . import i18n
    name = i18n.t('save.default_name')
    if create_save(name) is None:
        # 默认名被占用：追加序号
        for i in range(2, 100):
            name = f"{i18n.t('save.default_name')} {i}"
            if create_save(name) is not None:
                break
        else:
            return None
    try:
        shutil.copy2(legacy, save_file(name))
    except OSError:
        return None
    print(f'[存档] 已迁移旧存档到 saves/{name}/')
    return name
