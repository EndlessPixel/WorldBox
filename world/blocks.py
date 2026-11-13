"""方块表：config/blocks.json 是唯一数据源（颜色、贴图、状态、形状）。

以前每加一种方块要同步改 4 处（blocks.json、materials.SURFACE_FILES、
本文件的 DEFAULT_BLOCKS、资源包 URL），现在只需在 blocks.json 加条目：
- 贴图按 id 推导；半砖自动去掉 _slab 指向基方块贴图
- 多面方块用 textures 声明 top / bottom / side / ±x / ±z
- 有状态的方块用 states 声明状态键与允许值，texture_variants 声明贴图变体
有外部贴图时再往资源包 JSON 补一条 URL 即可。
"""

import json

from . import config

DEFAULT_BLOCK_ID = 'worldbox:grass.block'
SLAB_HEIGHT = 0.5      # 半砖高度（米）

# 图集为每个变体预留的贴图槽。top/bottom/side 是基础槽，
# ±x/±z 是方向槽（声明后覆盖 side，用于原木、朝向方块等）。
FACE_SLOTS = ('top', 'bottom', 'side', '+x', '-x', '+z', '-z')


def is_slab(block_id):
    """半砖判定：优先查声明的 shape，回退到历史 _slab.block 后缀。"""
    if isinstance(block_id, str) and BLOCKS.get(block_id, {}).get('shape') == 'slab':
        return True
    return isinstance(block_id, str) and block_id.endswith('_slab.block')


def shape_of(block_id):
    if isinstance(block_id, str):
        return BLOCKS.get(block_id, {}).get('shape', 'full')
    return 'full'


# blocks.json 完全不可用时才启用的最小回退，只保证游戏能启动
DEFAULT_BLOCKS = (
    {'id': 'worldbox:grass.block', 'name': 'Grass', 'color': (92, 172, 78),
     'textures': {'top': 'grass_block_top.png',
                  'side': 'grass_block_side.png',
                  'bottom': 'coarse_dirt.png'}},
    {'id': 'worldbox:dirt.block', 'name': 'Dirt', 'color': (134, 96, 67),
     'textures': {'top': 'coarse_dirt.png', 'side': 'coarse_dirt.png',
                  'bottom': 'coarse_dirt.png'}},
    {'id': 'worldbox:stone.block', 'name': 'Stone', 'color': (128, 128, 128)},
)


def _stem(block_id):
    """方块 id → 贴图基名；半砖去掉 _slab，指向基方块的贴图。"""
    stem = str(block_id).split(':')[-1].split('.')[0]
    return stem[:-5] if stem.endswith('_slab') else stem


def _default_textures(block_id):
    name = f'{_stem(block_id)}.png'
    return {'top': name, 'bottom': name, 'side': name}


def _parse_textures(raw, base):
    """声明的贴图覆盖到基础表上；未声明的方向槽留空，运行时回退 side。"""
    result = dict(base)
    if isinstance(raw, dict):
        for slot in FACE_SLOTS:
            value = raw.get(slot)
            if isinstance(value, str) and value.strip():
                result[slot] = value.strip()
    return result


def _parse_states(raw):
    """states: {状态键: [允许值...]}，第一个值是默认值。"""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(values, (list, tuple)) or not values:
            continue
        clean = tuple(str(value) for value in values
                      if isinstance(value, (str, int, float)))
        if clean:
            result[key] = clean
    return result


def _parse_variants(raw, base, schema):
    """texture_variants: {"axis=x": {槽: 贴图}} → {(键, 值): 贴图表}。"""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for key, overlay in raw.items():
        if not isinstance(key, str) or '=' not in key:
            continue
        state_key, value = key.split('=', 1)
        if state_key not in schema or value not in schema[state_key]:
            continue
        result[(state_key, value)] = _parse_textures(overlay, base)
    return result


def _make_entry(item):
    block_id = item['id']
    base = _default_textures(block_id)
    textures = _parse_textures(item.get('textures'), base)
    states = _parse_states(item.get('states'))
    declared = item.get('shape')
    shape = (declared if declared in ('full', 'slab')
             else 'slab' if block_id.endswith('_slab.block') else 'full')
    return {
        'name': item['name'],
        'color': item['color'],
        'textures': textures,
        'states': states,
        'variants': _parse_variants(item.get('texture_variants'),
                                    textures, states),
        'shape': shape,
    }


def load_blocks():
    """读取 blocks.json；逐条校验，坏条目跳过，文件不可用时退回最小定义。"""
    blocks = {}
    try:
        with config.BLOCKS_FILE.open(encoding='utf-8') as f:
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
                    color = tuple(max(0, min(255, int(c))) for c in rgb[:3])
                except (TypeError, ValueError):
                    continue
                name = item.get('name')
                block_id = block_id.strip()
                blocks[block_id] = _make_entry({
                    'id': block_id,
                    'name': str(name) if name else block_id,
                    'color': color,
                    'textures': item.get('textures'),
                    'states': item.get('states'),
                    'texture_variants': item.get('texture_variants'),
                    'shape': item.get('shape'),   # 未声明时由 _make_entry 按后缀推断
                })
    except (OSError, ValueError, TypeError):
        blocks = {}
    if not blocks:
        for item in DEFAULT_BLOCKS:
            blocks[item['id']] = _make_entry(item)
    return blocks


BLOCKS = load_blocks()
BLOCK_IDS = list(BLOCKS)
BLOCK_NAMES = {block_id: data['name'] for block_id, data in BLOCKS.items()}
BLOCK_TEXTURES = {block_id: data['textures'] for block_id, data in BLOCKS.items()}
BLOCK_STATES = {block_id: data['states'] for block_id, data in BLOCKS.items()}
BLOCK_VARIANTS = {block_id: data['variants'] for block_id, data in BLOCKS.items()}
print(f'[方块] 已加载 {len(BLOCKS)} 种：' + ', '.join(BLOCK_IDS))


# ---------- 方块状态 ----------
def default_states(block_id):
    """方块声明的所有状态键取默认值。"""
    return {key: values[0]
            for key, values in BLOCK_STATES.get(block_id, {}).items()}


def normalize_states(block_id, states):
    """过滤非法值，并去掉等于默认值的项（世界/存档里只存差异）。"""
    schema = BLOCK_STATES.get(block_id)
    if not schema or not isinstance(states, dict):
        return {}
    result = {}
    for key, values in schema.items():
        value = states.get(key)
        if value in values and value != values[0]:
            result[key] = value
    return result


def states_for(block_id, states):
    """默认值 + 已存差异 = 完整状态。"""
    result = default_states(block_id)
    result.update(normalize_states(block_id, states))
    return result


def variant_key(block_id, states):
    """渲染用的图集键：无差异用基础 id，有差异追加 |key=value。"""
    diff = normalize_states(block_id, states)
    if not diff:
        return block_id
    return block_id + '|' + ','.join(f'{k}={diff[k]}' for k in sorted(diff))


def textures_for(block_id, states):
    """按状态解析最终的面贴图表（基础表 + 命中的状态变体覆盖）。"""
    result = dict(BLOCK_TEXTURES.get(block_id, _default_textures(block_id)))
    full = states_for(block_id, states)
    for (key, value), overlay in BLOCK_VARIANTS.get(block_id, {}).items():
        if full.get(key) == value:
            result.update(overlay)
    return result


def all_variants():
    """图集需要生成的所有 (变体键, 基础 id, 状态差异)。"""
    for block_id in BLOCK_IDS:
        yield block_id, block_id, {}
        for (key, value) in BLOCK_VARIANTS.get(block_id, {}):
            states = {key: value}
            yield variant_key(block_id, states), block_id, states
