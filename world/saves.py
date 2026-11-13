"""多存档与玩家档案：saves/ 目录管理、旧存档迁移。

存档结构（version 3，按 16x16 区块分文件）：
    saves/<存档名>/world.json          # 玩家/快捷栏/时间等元数据
    saves/<存档名>/chunks/c<cx>_<cz>.json  # 该区块内被改动过的格子
玩家档案：
    config/player.json                 # {'name': 玩家名}
旧的 version 1/2 单文件存档仍可读，首次保存时自动迁移成分区块格式。
"""

import json
import re
import shutil
from pathlib import Path

from . import config

SAVES_DIR = config.ROOT_DIR / 'saves'
PLAYER_FILE = config.CONFIG_DIR / 'player.json'
SAVE_FILE_NAME = 'world.json'
CHUNKS_DIR_NAME = 'chunks'
SAVE_FORMAT = 'chunks'
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


def chunks_dir(path):
    return Path(path).parent / CHUNKS_DIR_NAME


def chunk_file(path, cx, cz):
    return chunks_dir(path) / f'c{cx}_{cz}.json'


def _chunk_coords(filename):
    """从 c<cx>_<cz>.json 反解区块坐标；名字不合法返回 None。"""
    try:
        cx, cz = filename[1:].split('_')
        return int(cx), int(cz)
    except (ValueError, IndexError):
        return None


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
            if isinstance(data, dict):
                if isinstance(data.get('blocks'), dict):
                    info['blocks'] = len(data['blocks'])
                else:
                    info['blocks'] = max(0, int(data.get('block_count') or 0))
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
    """读取存档；损坏或不兼容时返回 None。

    version 3 的方块数据分散在 chunks/ 里，这里合并回 blocks 字段，
    上层（VoxelWorld、存档列表）看到的仍然只是一份 dict。
    单个区块文件损坏只跳过该文件，不会让整个存档打不开。
    """
    path = Path(path)
    try:
        with path.open(encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get('version') not in (1, 2, 3):
        return None
    if data.get('format') == SAVE_FORMAT:
        blocks = {}
        cdir = chunks_dir(path)
        if cdir.is_dir():
            for item in sorted(cdir.glob('c*_*.json')):
                if _chunk_coords(item.stem) is None:
                    continue
                try:
                    with item.open(encoding='utf-8') as f:
                        part = json.load(f)
                except (OSError, ValueError, TypeError):
                    continue
                if isinstance(part, dict):
                    blocks.update(part)
        data['blocks'] = blocks
    return data


def save_payload(path, payload, dirty_chunks=None):
    """原子写回存档：方块按区块分文件，元数据单独放 world.json。

    dirty_chunks 是 {(cx, cz), ...}，只重写变动过的区块，世界再大也不会
    每次保存都重写全部数据。首次保存（还没有 chunks 目录）会全量迁移，
    并清掉已经没有任何改动的旧区块文件。
    """
    path = Path(path)
    blocks = payload.get('blocks')
    if not isinstance(blocks, dict):
        blocks = {}
    meta = {key: value for key, value in payload.items() if key != 'blocks'}
    meta['version'] = 3
    meta['format'] = SAVE_FORMAT
    meta['block_count'] = len(blocks)

    grouped = {}
    for key, value in blocks.items():
        try:
            parts = str(key).split(',')
            x, z = int(parts[0]), int(parts[2])
        except (TypeError, ValueError, IndexError):
            continue
        cx, cz = x // config.CHUNK_SIZE, z // config.CHUNK_SIZE
        grouped.setdefault((cx, cz), {})[key] = value

    cdir = chunks_dir(path)
    force_all = dirty_chunks is None or not cdir.is_dir()
    if force_all:
        targets = set(grouped)
        if cdir.is_dir():
            for item in cdir.glob('c*_*.json'):
                coord = _chunk_coords(item.stem)
                if coord is not None:
                    targets.add(coord)
    else:
        targets = set(dirty_chunks)

    try:
        cdir.mkdir(parents=True, exist_ok=True)
        for cx, cz in targets:
            data = grouped.get((cx, cz), {})
            target = chunk_file(path, cx, cz)
            if not data:
                if target.exists():
                    target.unlink()
                continue
            tmp = target.with_name(target.name + '.tmp')
            with tmp.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            tmp.replace(target)
        tmp = path.with_name(path.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
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
