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
        'menu.packs': '资源包',
        'menu.keybinds': '按键绑定',
        'packs.title': '资源包',
        'packs.hint': '方向键选择 / 回车应用 / R 下载 / ESC 返回',
        'packs.apply': '应用',
        'packs.download': '下载',
        'packs.back': '返回',
        'packs.builtin': '内置（噪声材质）',
        'packs.ready': '已就绪 {count} 个纹理',
        'packs.missing': '需下载',
        'packs.active': '使用中',
        'packs.applied': '已应用，正在加载…',
        'packs.downloaded': '下载完成',
        'packs.failed': '下载失败',
        'keybinds.title': '按键绑定',
        'keybinds.hint': '方向键选择 / 回车重绑定 / R 恢复默认 / ESC 返回',
        'keybinds.rebind': '重绑定',
        'keybinds.reset': '恢复默认',
        'keybinds.back': '返回',
        'keybinds.press': '按下新按键…',
        'keybinds.done': '已绑定 {key}',
        'keybinds.failed': '该按键不可绑定',
        'keybinds.cancel': '已取消',
        'keybinds.reset_done': '已恢复默认按键',
        'key.forward': '前进',
        'key.back': '后退',
        'key.left': '左移',
        'key.right': '右移',
        'key.jump': '跳跃',
        'key.crouch': '蹲下',
        'key.sprint': '疾跑',
        'key.zoom': '放大',
        'key.inventory': '背包',
        'key.menu': '暂停菜单',
        'key.save': '保存',
        'key.map': '全屏地图',
        'key.drop': '丢弃方块',
        'map.title': '地图',
        'map.hint': 'M 或 ESC 关闭',
        'menu.hint': 'WASD 移动 / 空格跳跃 / Shift 蹲下 / Ctrl 疾跑 / C 放大 / 左键挖 / 右键放',
        'inventory.title': '背包',
        'inventory.hint': '创造背包只读 / 方向键选择 / 回车放入快捷栏 / PageUp PageDown 翻页 / E 关闭',
        'inventory.prev': '上一页',
        'inventory.next': '下一页',
        'inventory.page': '第 {page}/{total} 页',
        'tooltip.color': '颜色',
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
        'notice.help': '左键挖 / 右键放 / 中键取方块 / 滚轮切快捷栏 / E 背包 / M 地图',
        'notice.saved': '已保存',
        'notice.save_failed': '保存失败',
        'notice.bedrock': '基岩 - 无法破坏',
        'notice.fell': '掉出世界 - 已传送回出生点',
        'notice.dropped': '已丢弃',
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
        'block.cobblestone': '原石',
        'block.stone_slab': '石头半砖',
        'block.cobblestone_slab': '原石半砖',
        'block.bricks_slab': '红砖半砖',
        'block.clay': '黏土',
        'block.stone_bricks': '石砖',
        'block.stone_bricks_slab': '石砖半砖',
        'block.bedrock': '基岩',
        'block.obsidian': '黑曜石',
        'block.bricks': '红砖',
        'block.end_stone': '末地石',
    },
    'en': {
        'language.name': 'English',
        'menu.paused': 'PAUSED',
        'menu.resume': 'Resume',
        'menu.settings': 'Settings',
        'menu.save': 'Save',
        'menu.save_quit': 'Save & Quit',
        'menu.packs': 'Resource Packs',
        'menu.keybinds': 'Key Bindings',
        'packs.title': 'RESOURCE PACKS',
        'packs.hint': 'UP/DOWN select / ENTER apply / R download / ESC back',
        'packs.apply': 'Apply',
        'packs.download': 'Download',
        'packs.back': 'Back',
        'packs.builtin': 'Built-in (noise)',
        'packs.ready': '{count} textures ready',
        'packs.missing': 'Needs download',
        'packs.active': 'ACTIVE',
        'packs.applied': 'Applied, loading…',
        'packs.downloaded': 'Download complete',
        'packs.failed': 'Download failed',
        'keybinds.title': 'KEY BINDINGS',
        'keybinds.hint': 'UP/DOWN select / ENTER rebind / R reset / ESC back',
        'keybinds.rebind': 'Rebind',
        'keybinds.reset': 'Reset',
        'keybinds.back': 'Back',
        'keybinds.press': 'Press a key…',
        'keybinds.done': 'Bound {key}',
        'keybinds.failed': 'Key not bindable',
        'keybinds.cancel': 'Cancelled',
        'keybinds.reset_done': 'Defaults restored',
        'key.forward': 'Forward',
        'key.back': 'Back',
        'key.left': 'Strafe Left',
        'key.right': 'Strafe Right',
        'key.jump': 'Jump',
        'key.crouch': 'Crouch',
        'key.sprint': 'Sprint',
        'key.zoom': 'Zoom',
        'key.inventory': 'Inventory',
        'key.menu': 'Pause Menu',
        'key.save': 'Save',
        'key.map': 'Fullscreen Map',
        'key.drop': 'Drop Block',
        'map.title': 'MAP',
        'map.hint': 'M or ESC to close',
        'menu.hint': 'WASD move / SPACE jump / SHIFT crouch / CTRL sprint / C zoom / LMB dig / RMB place',
        'inventory.title': 'INVENTORY',
        'inventory.hint': 'Creative bag is read-only / arrows select / ENTER to hotbar / PageUp PageDown page / E close',
        'inventory.prev': 'Prev',
        'inventory.next': 'Next',
        'inventory.page': 'Page {page}/{total}',
        'tooltip.color': 'Color',
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
        'pack.minecraft': 'Minecraft 26.3',
        'settings.on': 'ON',
        'settings.off': 'OFF',
        'notice.help': 'LMB dig / RMB place / MMB pick / wheel hotbar / E inv / M map',
        'notice.saved': 'SAVED',
        'notice.save_failed': 'SAVE FAILED',
        'notice.bedrock': 'BEDROCK - unbreakable',
        'notice.fell': 'FELL OUT OF WORLD - TELEPORTED TO SPAWN',
        'notice.dropped': 'DROPPED',
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
        'block.cobblestone': 'Cobblestone',
        'block.stone_slab': 'Stone Slab',
        'block.cobblestone_slab': 'Cobblestone Slab',
        'block.bricks_slab': 'Bricks Slab',
        'block.clay': 'Clay',
        'block.stone_bricks': 'Stone Bricks',
        'block.stone_bricks_slab': 'Stone Bricks Slab',
        'block.bedrock': 'Bedrock',
        'block.obsidian': 'Obsidian',
        'block.bricks': 'Bricks',
        'block.end_stone': 'End Stone',
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
    """按方块 ID 后缀查翻译：当前语言 → 英文 → blocks.json 的 name。"""
    suffix = str(block_id).split(':')[-1].split('.')[0]
    key = f'block.{suffix}'
    return (TEXTS.get(_language, {}).get(key)
            or TEXTS['en'].get(key)
            or default)


def pack_name(pack_id):
    """资源包显示名：有翻译用翻译，否则直接显示 id。"""
    return TEXTS.get(_language, {}).get(f'pack.{pack_id}') or pack_id
