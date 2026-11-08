"""方块表：从 blocks.json 读取 id / name / color。"""

import json

from . import config

DEFAULT_BLOCK_ID = 'worldbox:grass.block'
SLAB_HEIGHT = 0.5      # 半砖高度（米）


def is_slab(block_id):
    """判断是否半砖：ID 以 _slab 结尾，例如 worldbox:stone_slab.block。"""
    return isinstance(block_id, str) and block_id.endswith('_slab.block')


DEFAULT_BLOCKS = (
    {'id': 'worldbox:grass.block',      'name': 'Grass',      'color': (92, 172, 78)  },
    {'id': 'worldbox:dirt.block',       'name': 'Dirt',       'color': (134, 96, 67)  },
    {'id': 'worldbox:stone.block',      'name': 'Stone',      'color': (128, 128, 128)},
    {'id': 'worldbox:stone_slab.block', 'name': 'Stone Slab', 'color': (128, 128, 128)},
    {'id': 'worldbox:cobblestone.block','name': 'Cobblestone','color': [100, 100, 100]},
    {'id': 'worldbox:cobblestone_slab.block', 'name': 'Cobblestone Slab',
     'color': [100, 100, 100]},
    {'id': 'worldbox:bricks.block',     'name': 'Bricks',     'color': (156, 83, 62)  },
    {'id': 'worldbox:bricks_slab.block','name': 'Bricks Slab','color': (156, 83, 62)  },
    {'id': 'worldbox:obsidian.block',   'name': 'Obsidian',   'color': (26, 22, 38)   },
    {'id': 'worldbox:bedrock.block',    'name': 'Bedrock',    'color': (90, 90, 90)   },
    {'id': 'worldbox:end_stone.block',  'name': 'End Stone',  'color': (219, 213, 161)},
    {'id': 'worldbox:clay.block',       'name': 'Clay',       'color': (160, 166, 179)},
    {'id': 'worldbox:stone_bricks.block','name': 'Stone Bricks','color': (122, 122, 122)},
    {'id': 'worldbox:stone_bricks_slab.block', 'name': 'Stone Bricks Slab',
     'color': (122, 122, 122)},
    {'id': 'worldbox:mossy_cobblestone.block', 'name': 'Mossy Cobblestone',
     'color': (100, 102, 90)},
    {'id': 'worldbox:mossy_cobblestone_slab.block', 'name': 'Mossy Cobblestone Slab',
     'color': (100, 102, 90)},
    {'id': 'worldbox:mossy_stone_bricks.block', 'name': 'Mossy Stone Bricks',
     'color': (120, 122, 110)},
    {'id': 'worldbox:mossy_stone_bricks_slab.block', 'name': 'Mossy Stone Bricks Slab',
     'color': (120, 122, 110)},
    {'id': 'worldbox:cracked_stone_bricks.block', 'name': 'Cracked Stone Bricks',
     'color': (122, 122, 122)},
    {'id': 'worldbox:cracked_stone_bricks_slab.block', 'name': 'Cracked Stone Bricks Slab',
     'color': (122, 122, 122)},
    {'id': 'worldbox:podzol.block', 'name': 'Podzol', 'color': (120, 85, 55)},
    {'id': 'worldbox:mycelium.block', 'name': 'Mycelium', 'color': (140, 130, 145)},
    {'id': 'worldbox:netherrack.block', 'name': 'Netherrack', 'color': (112, 52, 44)},
    {'id': 'worldbox:chiseled_stone_bricks.block', 'name': 'Chiseled Stone Bricks',
     'color': (122, 122, 122)},
)


def load_blocks():
    """读取 blocks.json；逐条校验，坏条目跳过，文件不可用时退回内置定义。"""
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
                    r, g, b = (max(0, min(255, int(c))) for c in rgb[:3])
                except (TypeError, ValueError):
                    continue
                name = item.get('name')
                blocks[block_id] = {
                    'name': str(name) if name else block_id,
                    'color': (r, g, b),
                }
    except (OSError, ValueError, TypeError):
        blocks = {}
    if not blocks:
        blocks = {b['id']: {'name': b['name'], 'color': b['color']} for b in DEFAULT_BLOCKS}
    return blocks


BLOCKS = load_blocks()
BLOCK_IDS = list(BLOCKS)
BLOCK_NAMES = {block_id: data['name'] for block_id, data in BLOCKS.items()}
print(f'[方块] 已加载 {len(BLOCKS)} 种：' + ', '.join(BLOCK_IDS))
