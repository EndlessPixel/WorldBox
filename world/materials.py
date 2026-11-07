"""方块材质：加载 MC 16x16 纹理，生成共享图集与 3D 物品网格。

- 世界网格和快捷栏/背包共用一张图集纹理，避免每种方块一个材质。
- 草方块顶面/侧面草边是灰度图，这里乘绿色滤镜。
- 物品图标用等距三面（顶/左/右）Mesh，呈现 3D 方块效果。
"""

from PIL import Image
from ursina import Mesh, Texture

from . import config
from .blocks import BLOCK_IDS, BLOCKS, DEFAULT_BLOCK_ID

TILE = 16
GRASS_TINT = (0.62, 1.10, 0.48)

SURFACE_FILES = {
    'worldbox:grass.block': {
        'top': 'grass_block_top.png',
        'side': 'grass_block_side.png',
        'bottom': 'coarse_dirt.png',
    },
    'worldbox:dirt.block': {
        'top': 'coarse_dirt.png',
        'side': 'coarse_dirt.png',
        'bottom': 'coarse_dirt.png',
    },
    'worldbox:stone.block': {
        'top': 'stone.png',
        'side': 'stone.png',
        'bottom': 'stone.png',
    },
    'worldbox:bedrock.block': {
        'top': 'bedrock.png',
        'side': 'bedrock.png',
        'bottom': 'bedrock.png',
    },
}


class BlockMaterials:
    def __init__(self):
        # 当前资源包命名空间：'' = 自带默认包 worldbox
        namespace = config.SETTINGS.get('resource_pack') or 'worldbox'
        texture_dir = config.ROOT_DIR / 'assets' / namespace / 'blocks'
        if not texture_dir.is_dir():
            texture_dir = config.ROOT_DIR / 'assets' / 'worldbox' / 'blocks'
        self.texture_dir = texture_dir
        self.block_ids = list(BLOCK_IDS)
        width = max(1, len(self.block_ids)) * TILE
        self.atlas = Image.new('RGBA', (width, TILE * 3), (0, 0, 0, 0))
        self.uvs = {}
        self.item_meshes = {}

        for col, block_id in enumerate(self.block_ids):
            self.uvs[block_id] = {}
            for row, face in enumerate(('top', 'side', 'bottom')):
                tile = self._load_tile(block_id, face)
                self.atlas.paste(tile, (col * TILE, row * TILE))
                self.uvs[block_id][face] = self._uv(col, row)

        self.texture = Texture(self.atlas, filtering='nearest')
        for block_id in self.block_ids:
            self.item_meshes[block_id] = self._make_item_mesh(block_id)

    # ---------- 纹理加载 ----------
    def _load_tile(self, block_id, face):
        filename = SURFACE_FILES.get(block_id, {}).get(face)
        if filename:
            path = self.texture_dir / filename
            if path.exists():
                try:
                    image = Image.open(path).convert('RGBA')
                    if image.size != (TILE, TILE):
                        image = image.resize((TILE, TILE), Image.NEAREST)
                    if block_id == 'worldbox:grass.block':
                        self._tint_grass(image, face)
                    return image
                except OSError:
                    pass
        return self._fallback_tile(block_id)

    @staticmethod
    def _tint_grass(image, face):
        """顶面整张染绿；侧面只染顶部草边（排除棕色泥土）。"""
        pixels = image.load()
        for y in range(TILE):
            for x in range(TILE):
                r, g, b, a = pixels[x, y]
                if a == 0:
                    continue
                if face == 'top' or (face == 'side' and y < 5 and g >= r - 10):
                    pixels[x, y] = (
                        min(255, int(r * GRASS_TINT[0])),
                        min(255, int(g * GRASS_TINT[1])),
                        min(255, int(b * GRASS_TINT[2])),
                        a,
                    )

    @staticmethod
    def _fallback_tile(block_id):
        """材质文件缺失时，按 blocks.json 的颜色生成 16x16 噪声。"""
        base = BLOCKS.get(block_id, BLOCKS[DEFAULT_BLOCK_ID])['color']
        seed = sum(ord(char) for char in block_id)
        image = Image.new('RGBA', (TILE, TILE), (*base, 255))
        pixels = image.load()
        for y in range(TILE):
            for x in range(TILE):
                delta = ((x * 7 + y * 13 + seed) % 25) - 12
                pixels[x, y] = (
                    max(0, min(255, base[0] + delta)),
                    max(0, min(255, base[1] + delta)),
                    max(0, min(255, base[2] + delta)),
                    255,
                )
        return image

    def _uv(self, col, row):
        """图集里一格 tile 的 UV（内缩半像素，避免采样到相邻格）。"""
        width, height = self.atlas.size
        pad = 0.5
        return (
            (col * TILE + pad) / width,
            1 - ((row + 1) * TILE - pad) / height,
            ((col + 1) * TILE - pad) / width,
            1 - (row * TILE + pad) / height,
        )

    # ---------- 3D 物品图标 ----------
    def _make_item_mesh(self, block_id):
        top_uv = self.uvs[block_id]['top']
        side_uv = self.uvs[block_id]['side']
        coordinates = (
            (-0.5, 0.25), (0.0, 0.5), (0.5, 0.25), (0.0, 0.0),      # 顶面
            (-0.5, 0.25), (0.0, 0.0), (0.0, -0.5), (-0.5, -0.25),   # 左面
            (0.5, 0.25), (0.0, 0.0), (0.0, -0.5), (0.5, -0.25),     # 右面
        )
        vertices = [(x, y, 0) for x, y in coordinates]
        triangles = (
            (0, 1, 2), (0, 2, 3),
            (4, 5, 6), (4, 6, 7),
            (8, 9, 10), (8, 10, 11),
        )
        uvs = self._quad_uv(top_uv) + self._quad_uv(side_uv) + self._quad_uv(side_uv)
        colors = []
        for factor in (1.0, 0.78, 0.6):   # 顶亮、左中、右暗
            colors.extend([(factor, factor, factor, 1.0)] * 4)
        return Mesh(vertices=vertices, triangles=triangles, uvs=uvs,
                    colors=colors, mode='triangle')

    @staticmethod
    def _quad_uv(uv):
        u0, v0, u1, v1 = uv
        return [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]
