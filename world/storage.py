"""存档：读取、数值校验与原子写入。"""

import json
import math

from . import config


def load_save():
    """读取存档；文件损坏或版本不兼容时返回 None。"""
    try:
        with config.SAVE_FILE.open(encoding='utf-8') as f:
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


def save_payload(payload):
    """先写临时文件再原子替换，避免中途退出留下半截存档。"""
    try:
        tmp = config.SAVE_FILE.with_name(config.SAVE_FILE.name + '.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(config.SAVE_FILE)
        return True
    except (OSError, TypeError, ValueError):
        return False
