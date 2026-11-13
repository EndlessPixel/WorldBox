"""服务器列表持久化：config/servers.json。

每一项 {name, address}，按名称排序；增删都原子写回。联机功能尚未实现，
这里只负责把"服务器列表"这个 UI 数据持久化下来（新增/删除可用）。
"""

import json

from . import config
from .saves import sanitize_name

SERVERS_FILE = config.CONFIG_DIR / 'servers.json'
ADDRESS_MAX_LEN = 64


def sanitize_address(address):
    """地址只做去空白与长度限制（端口号、冒号都保留）。"""
    return str(address or '').strip()[:ADDRESS_MAX_LEN]


def _load():
    try:
        with SERVERS_FILE.open(encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, dict) and item.get('name'):
            out.append({'name': str(item['name'])[:24],
                        'address': str(item.get('address', ''))[:ADDRESS_MAX_LEN]})
    return out


def _save(servers):
    """原子写回：先写临时文件再替换，避免中途退出留下半截文件。"""
    try:
        SERVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SERVERS_FILE.with_name(SERVERS_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(servers, f, ensure_ascii=False, indent=2)
        tmp.replace(SERVERS_FILE)
        return True
    except OSError:
        return False


def list_servers():
    """[{name, address}]，按名称排序。"""
    return sorted(_load(), key=lambda s: s['name'])


def add_server(name, address):
    """新增服务器；重名或非法名返回 False。"""
    name = sanitize_name(name)
    if not name:
        return False
    servers = _load()
    if any(s['name'] == name for s in servers):
        return False
    servers.append({'name': name, 'address': sanitize_address(address)})
    return _save(servers)


def delete_server(name):
    """删除服务器；不存在返回 False。"""
    name = sanitize_name(name)
    if not name:
        return False
    current = _load()
    servers = [s for s in current if s['name'] != name]
    if len(servers) == len(current):
        return False          # 列表里本就没有这个服务器
    return _save(servers)
