"""方块材质：加载 MC 16x16 纹理，生成共享图集与 3D 物品网格。

- 世界网格和快捷栏/背包共用一张图集纹理，避免每种方块一个材质。
- 每个「方块状态变体」占图集一列，列内按 FACE_SLOTS 逐槽放贴图；
  贴图与变体全部来自 config/blocks.json 的声明（见 world/blocks.py）。
- 草方块顶面/侧面草边是灰度图，这里乘绿色滤镜。
"""

from PIL import Image
from ursina import Mesh, Texture

from . import config
from .blocks import (BLOCK_IDS, BLOCKS, DEFAULT_BLOCK_ID, FACE_SLOTS,
                     all_variants, is_slab, textures_for)

TILE = 16
GRASS_TINT = (0.62, 1.10, 0.48)


class BlockMaterials:
    def __init__(self):
        # 当前资源包命名空间：'' = 自带默认包 worldbox
        namespace = config.SETTINGS.get('resource_pack') or 'worldbox'
        texture_dir = config.ROOT_DIR / 'assets' / namespace / 'blocks'
        if not texture_dir.is_dir():
            texture_dir = config.ROOT_DIR / 'assets' / 'worldbox' / 'blocks'
        self.texture_dir = texture_dir
        self.block_ids = list(BLOCK_IDS)

        # 收集所有需要生成贴图的变体（基础方块 + 声明的状态变体）
        self.variant_textures = {}
        self.variant_keys = []
        for key, block_id, states in all_variants():
            if key in self.variant_textures:
                continue
            self.variant_textures[key] = (block_id,
                                          textures_for(block_id, states))
            self.variant_keys.append(key)

        width = max(1, len(self.variant_keys)) * TILE
        self.atlas = Image.new('RGBA',
                               (width, TILE * len(FACE_SLOTS)),
                               (0, 0, 0, 0))
        self.uvs = {}
        for col, key in enumerate(self.variant_keys):
            self.uvs[key] = {}
            for row, slot in enumerate(FACE_SLOTS):
                tile = self._load_tile(key, slot)
                self.atlas.paste(tile, (col * TILE, row * TILE))
                self.uvs[key][slot] = self._uv(col, row)

        self.texture = Texture(self.atlas, filtering='nearest')
        self.item_meshes = {}
        for block_id in self.block_ids:
            self.item_meshes[block_id] = self._make_item_mesh(block_id)

    # ---------- 纹理加载 ----------
    def _load_tile(self, variant_key, slot):
        block_id, textures = self.variant_textures[variant_key]
        filename = textures.get(slot) or textures.get('side')
        if filename:
            path = self.texture_dir / filename
            if path.exists():
                try:
                    image = Image.open(path).convert('RGBA')
                    if image.size != (TILE, TILE):
                        image = image.resize((TILE, TILE), Image.NEAREST)
                    if block_id == 'worldbox:grass.block':
                        face = ('top' if slot == 'top'
                                else 'bottom' if slot == 'bottom' else 'side')
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
        uv_set = self.uvs[block_id]
        top_uv = uv_set['top']
        side_uv = uv_set['side']
        coordinates = (
            (-0.5, 0.25), (0.0, 0.5), (0.5, 0.25), (0.0, 0.0),      # 顶面
            (-0.5, 0.25), (0.0, 0.0), (0.0, -0.5), (-0.5, -0.25),   # 左面
            (0.5, 0.25), (0.0, 0.0), (0.0, -0.5), (0.5, -0.25),     # 右面
        )
        vertices = [(x, y, 0) for x, y in coordinates]
        if is_slab(block_id):
            # 半砖图标压扁一半高度
            vertices = [(x, y * 0.5, z) for x, y, z in vertices]
        triangles = (
            (0, 1, 2), (0, 2, 3),
            (4, 5, 6), (4, 6, 7),
            (8, 9, 10), (8, 10, 11),
        )
        u0, v0, u1, v1 = side_uv
        if is_slab(block_id):
            # 半砖只占下半格：侧面裁剪贴图下半，不是把整张贴图压扁
            v1 = v0 + (v1 - v0) * 0.5
        # 侧面是竖直平行四边形：两条竖直边对应贴图上下（v），
        # 两条斜边对应贴图左右（u），草边等才会水平位于侧面顶部
        left_uv = ((u0, v1), (u1, v1), (u1, v0), (u0, v0))
        # 右面从另一侧看，u 方向相反（前棱为 u0、后棱为 u1）
        right_uv = ((u1, v1), (u0, v1), (u0, v0), (u1, v0))
        uvs = self._quad_uv(top_uv) + list(left_uv) + list(right_uv)
        colors = []
        for factor in (1.0, 0.78, 0.6):   # 顶亮、左中、右暗
            colors.extend([(factor, factor, factor, 1.0)] * 4)
        return Mesh(vertices=vertices, triangles=triangles, uvs=uvs,
                    colors=colors, mode='triangle')

    @staticmethod
    def _quad_uv(uv):
        u0, v0, u1, v1 = uv
        return [(u0, v0), (u0, v1), (u1, v1), (u1, v0)]
