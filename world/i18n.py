"""中英双语文本。语言由 config/setting.json 的 language 字段决定。"""

from . import config

TEXTS = {
    'zh': {
        'language.name': '中文',
        'menu.paused': '已暂停',
        'menu.resume': '继续',
        'menu.settings': '设置',
        'menu.save': '保存',
        'menu.save_quit': '保存并退出',
        'menu.hint': 'WASD 移动 / 空格跳跃 / Shift 蹲下 / Ctrl 疾跑 / C 放大 / 左键挖 / 右键放',
        'inventory.title': '背包',
        'inventory.hint': '点击物品拾取 / 点击快捷栏放入 / E 关闭',
        'settings.title': '设置',
        'settings.hint': '方向键选择 / 左右调整 / 点击 - + 修改 / ESC 返回',
        'settings.back': '返回',
        'settings.language': '语言',
        'settings.auto_jump': '自动跳跃',
        'settings.auto_jump_height': '跳跃高度',
        'settings.view_distance': '视距',
        'settings.fov': '视场角',
        'settings.view_bob': '视角晃动',
        'settings.brightness': '亮度',
        'settings.resource_pack': '资源包',
        'pack.worldbox': '默认',
        'pack.minecraft': 'Minecraft 26.3',
        'settings.on': '开',
        'settings.off': '关',
        'notice.help': '左键挖 / 右键放 / 中键取方块 / 滚轮切快捷栏 / E 背包',
        'notice.saved': '已保存',
        'notice.save_failed': '保存失败',
        'notice.bedrock': '基岩 - 无法破坏',
        'notice.fell': '掉出世界 - 已传送回出生点',
        'notice.pack_switched': '资源包已切换',
        'hud.menu': '菜单',
        'hud.inventory': '背包',
        'hud.eye': '眼高',
        'hud.crouch': '蹲',
        'hud.sprint': '疾跑',
        'hud.zoom': '放大',
        'block.grass': '草方块',
        'block.dirt': '泥土',
        'block.stone': '石头',
        'block.bedrock': '基岩',
    },
    'en': {
        'language.name': 'English',
        'menu.paused': 'PAUSED',
        'menu.resume': 'Resume',
        'menu.settings': 'Settings',
        'menu.save': 'Save',
        'menu.save_quit': 'Save & Quit',
        'menu.hint': 'WASD move / SPACE jump / SHIFT crouch / CTRL sprint / C zoom / LMB dig / RMB place',
        'inventory.title': 'INVENTORY',
        'inventory.hint': 'CLICK item to pick up / CLICK hotbar slot to place / E close',
        'settings.title': 'SETTINGS',
        'settings.hint': 'UP/DOWN select / LEFT/RIGHT adjust / click - + / ESC back',
        'settings.back': 'Back',
        'settings.language': 'Language',
        'settings.auto_jump': 'Auto Jump',
        'settings.auto_jump_height': 'Jump Height',
        'settings.view_distance': 'View Distance',
        'settings.fov': 'FOV',
        'settings.view_bob': 'View Bob',
        'settings.brightness': 'Brightness',
        'settings.resource_pack': 'Resource Pack',
        'pack.worldbox': 'Default',
        'settings.on': 'ON',
        'settings.off': 'OFF',
        'notice.help': 'LMB dig / RMB place / MMB pick / wheel hotbar / E inventory',
        'notice.saved': 'SAVED',
        'notice.save_failed': 'SAVE FAILED',
        'notice.bedrock': 'BEDROCK - unbreakable',
        'notice.fell': 'FELL OUT OF WORLD - TELEPORTED TO SPAWN',
        'notice.pack_switched': 'RESOURCE PACK SWITCHED',
        'hud.menu': 'MENU',
        'hud.inventory': 'INVENTORY',
        'hud.eye': 'EYE',
        'hud.crouch': 'CROUCH',
        'hud.sprint': 'SPRINT',
        'hud.zoom': 'ZOOM',
        'block.grass': 'Grass',
        'block.dirt': 'Dirt',
        'block.stone': 'Stone',
        'block.bedrock': 'Bedrock',
    },
}

_language = config.SETTINGS.get('language', 'zh')
if _language not in TEXTS:
    _language = 'zh'


def get_language():
    return _language


def set_language(language):
    """切换语言；返回是否成功。"""
    global _language
    if language in TEXTS:
        _language = language
        return True
    return False


def t(key, **kwargs):
    """取当前语言的文本；缺失时回退英文，再回退 key。"""
    text = TEXTS.get(_language, {}).get(key)
    if text is None:
        text = TEXTS['en'].get(key, key)
    return text.format(**kwargs) if kwargs else text


def block_name(block_id, default):
    """按方块 ID 后缀查翻译（grass/dirt/stone/bedrock），未收录时用 default。"""
    suffix = str(block_id).split(':')[-1].split('.')[0]
    return TEXTS.get(_language, {}).get(f'block.{suffix}', default)


def pack_name(pack_id):
    """资源包显示名：有翻译用翻译，否则直接显示 id。"""
    return TEXTS.get(_language, {}).get(f'pack.{pack_id}') or pack_id
