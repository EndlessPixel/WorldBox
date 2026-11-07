"""方块表：从 blocks.json 读取 id / name / color。"""

import json

from . import config

DEFAULT_BLOCK_ID = 'worldbox:grass.block'

DEFAULT_BLOCKS = (
    {'id': 'worldbox:grass.block',      'name': 'Grass',      'color': (92, 172, 78)  },
    {'id': 'worldbox:dirt.block',       'name': 'Dirt',       'color': (134, 96, 67)  },
    {'id': 'worldbox:stone.block',      'name': 'Stone',      'color': (128, 128, 128)},
    {'id': 'worldbox:cobblestone.block','name': 'Cobblestone','color': [100, 100, 100]},
    {"id": 'worldbox:bedrock.block',    'name': 'Bedrock',    'color': [90, 90, 90]   },
    {'id': 'worldbox:obsidian.block',   'name': 'Obsidian',   'color': (26, 22, 38)   },
    {'id': 'worldbox:bricks.block',     'name': 'Bricks',     'color': (156, 83, 62)  }
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
