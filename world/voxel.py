"""体素世界：方块数据、区块网格、射线与地面查询。"""

import math

from ursina import Entity, Mesh, color, destroy

from . import config
from .blocks import BLOCKS, DEFAULT_BLOCK_ID
from .materials import BlockMaterials

SUPPORT_TOLERANCE = 0.05   # 脚部允许与支撑面相差的高度（米）

# 六个面：邻接方向、4 个顶点偏移、明暗系数
FACES = (
    (( 0,  1,  0), ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)), 1.00),  # 顶
    (( 0, -1,  0), ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)), 0.45),  # 底
    (( 1,  0,  0), ((1, 0, 1), (1, 1, 1), (1, 1, 0), (1, 0, 0)), 0.80),  # +X
    ((-1,  0,  0), ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)), 0.80),  # -X
    (( 0,  0,  1), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)), 0.70),  # +Z
    (( 0,  0, -1), ((1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 0)), 0.70),  # -Z
)


class VoxelWorld:
    def __init__(self, save_data=None):
        self.world_blocks = {}     # (x, y, z) -> block_id
        self.world_edits = {}      # 玩家改动：(x, y, z) -> block_id 或 None
        self.chunk_blocks = {}     # (cx, cz) -> {(x, y, z), ...}
        self.chunk_meshes = {}     # (cx, cz) -> Entity
        self.chunks_per_axis = math.ceil(config.WORLD_SIZE / config.CHUNK_SIZE)
        self.block_tint = color.white
        self.materials = BlockMaterials()

        self._fill_layers()
        self._apply_saved_edits(save_data)
        self.build_all()

    # ---------- 数据 ----------
    def chunk_coord(self, x, z):
        return (x // config.CHUNK_SIZE, z // config.CHUNK_SIZE)

    def add_block(self, x, y, z, block_id):
        self.world_blocks[(x, y, z)] = block_id
        self.chunk_blocks.setdefault(self.chunk_coord(x, z), set()).add((x, y, z))

    def remove_block(self, x, y, z):
        if self.world_blocks.pop((x, y, z), None) is None:
            return False
        self.chunk_blocks.get(self.chunk_coord(x, z), set()).discard((x, y, z))
        return True

    def _fill_layers(self):
        """初始世界分层填充（顶层草方块顶面正好落在 y=0）。"""
        layer_ids = []
        for block_id, count in config.WORLD_LAYERS:
            layer_ids.extend([block_id if block_id in BLOCKS else DEFAULT_BLOCK_ID] * count)
        for x in range(config.WORLD_SIZE):
            for z in range(config.WORLD_SIZE):
                for offset, block_id in enumerate(layer_ids):
                    self.add_block(x, config.MIN_BLOCK_Y + offset, z, block_id)

    def _apply_saved_edits(self, save_data):
        """应用存档里的方块改动（坐标与 ID 都校验，损坏条目直接跳过）。"""
        if not save_data:
            return
        edits = save_data.get('blocks')
        if not isinstance(edits, dict):
            return
        for key, block_id in list(edits.items())[:30000]:
            try:
                x, y, z = (int(part) for part in str(key).split(','))
            except (TypeError, ValueError):
                continue
            if not (0 <= x < config.WORLD_SIZE and 0 <= z < config.WORLD_SIZE
                    and config.MIN_BLOCK_Y <= y < config.MAX_BLOCK_Y):
                continue
            if block_id is not None and block_id not in BLOCKS:
                continue
            if block_id is None:
                self.remove_block(x, y, z)
            else:
                self.add_block(x, y, z, block_id)
            self.world_edits[(x, y, z)] = block_id

    # ---------- 网格 ----------
    def build_chunk_mesh(self, cx, cz):
        """把一个区块里所有暴露面合并成一个 Mesh（顶点颜色 + 方块表颜色）。"""
        vertices, triangles, colors, uvs = [], [], [], []
        for (x, y, z) in self.chunk_blocks.get((cx, cz), ()):
            block_id = self.world_blocks.get((x, y, z))
            if block_id is None:
                continue
            uv_set = self.materials.uvs.get(block_id, self.materials.uvs[DEFAULT_BLOCK_ID])
            checker = 1.0 if (x + z) % 2 == 0 else 0.94   # 棋盘微调，方便看出 1 米格
            for (nx, ny, nz), corners, shade in FACES:
                if ny == -1 and y == config.MIN_BLOCK_Y:
                    continue                               # 世界最底层不生成底面
                if (x + nx, y + ny, z + nz) in self.world_blocks:
                    continue                               # 相邻方块遮挡，跳过该面
                start = len(vertices)
                factor = shade * checker
                face = 'top' if ny == 1 else ('bottom' if ny == -1 else 'side')
                u0, v0, u1, v1 = uv_set[face]
                face_uv = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))
                for (ox, oy, oz), (uu, vv) in zip(corners, face_uv):
                    vertices.append((x + ox, y + oy, z + oz))
                    colors.append((factor, factor, factor, 1.0))
                    uvs.append((uu, vv))
                triangles.extend(((start, start + 1, start + 2), (start, start + 2, start + 3)))
        return Mesh(vertices=vertices, triangles=triangles, colors=colors, uvs=uvs, mode='triangle')

    def rebuild_chunk(self, cx, cz):
        old = self.chunk_meshes.pop((cx, cz), None)
        if old is not None:
            destroy(old)
        mesh = self.build_chunk_mesh(cx, cz)
        if mesh.vertices:
            entity = Entity(model=mesh, texture=self.materials.texture)
            entity.set_two_sided(True)   # 兜底：即使绕序偏差也不会出现空洞
            entity.color = self.block_tint
            self.chunk_meshes[(cx, cz)] = entity

    def rebuild_around(self, x, z):
        """方块变化后重建所在区块；在区块边缘时连带重建相邻区块。"""
        cx, cz = self.chunk_coord(x, z)
        affected = {(cx, cz)}
        if x % config.CHUNK_SIZE == 0 and cx > 0:
            affected.add((cx - 1, cz))
        if x % config.CHUNK_SIZE == config.CHUNK_SIZE - 1 and cx < self.chunks_per_axis - 1:
            affected.add((cx + 1, cz))
        if z % config.CHUNK_SIZE == 0 and cz > 0:
            affected.add((cx, cz - 1))
        if z % config.CHUNK_SIZE == config.CHUNK_SIZE - 1 and cz < self.chunks_per_axis - 1:
            affected.add((cx, cz + 1))
        for _cx, _cz in affected:
            self.rebuild_chunk(_cx, _cz)

    def build_all(self):
        for cx in range(self.chunks_per_axis):
            for cz in range(self.chunks_per_axis):
                self.rebuild_chunk(cx, cz)
        print(f'[世界] 已生成 {len(self.chunk_meshes)} 个区块，{len(self.world_blocks)} 个方块')

    def set_tint(self, tint):
        """昼夜变化时统一乘到所有区块上。"""
        self.block_tint = tint
        for entity in self.chunk_meshes.values():
            entity.color = tint

    # ---------- 查询 ----------
    def raycast(self, origin, direction, max_distance):
        """体素 DDA：返回 (命中方块坐标, 进入面法线)，未命中返回 None。"""
        length = math.sqrt(direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2)
        if length == 0:
            return None
        dx, dy, dz = direction[0] / length, direction[1] / length, direction[2] / length

        x, y, z = math.floor(origin[0]), math.floor(origin[1]), math.floor(origin[2])
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        step_z = 1 if dz > 0 else -1

        inf = float('inf')
        t_delta_x = abs(1.0 / dx) if dx else inf
        t_delta_y = abs(1.0 / dy) if dy else inf
        t_delta_z = abs(1.0 / dz) if dz else inf
        t_max_x = ((x + 1 - origin[0]) / dx) if dx > 0 else (((x - origin[0]) / dx) if dx < 0 else inf)
        t_max_y = ((y + 1 - origin[1]) / dy) if dy > 0 else (((y - origin[1]) / dy) if dy < 0 else inf)
        t_max_z = ((z + 1 - origin[2]) / dz) if dz > 0 else (((z - origin[2]) / dz) if dz < 0 else inf)

        normal = (0, 0, 0)
        distance = 0.0
        for _ in range(128):
            if distance > max_distance:
                break
            if (x, y, z) in self.world_blocks:
                return (x, y, z), normal
            if t_max_x < t_max_y and t_max_x < t_max_z:
                x += step_x
                distance = t_max_x
                t_max_x += t_delta_x
                normal = (-step_x, 0, 0)
            elif t_max_y < t_max_z:
                y += step_y
                distance = t_max_y
                t_max_y += t_delta_y
                normal = (0, -step_y, 0)
            else:
                z += step_z
                distance = t_max_z
                t_max_z += t_delta_z
                normal = (0, 0, -step_z)
        return None

    @staticmethod
    def columns(x, z, radius):
        """玩家 AABB 覆盖到的所有方块列。"""
        for cx in range(math.floor(x - radius), math.floor(x + radius) + 1):
            for cz in range(math.floor(z - radius), math.floor(z + radius) + 1):
                yield cx, cz

    def ground_height_at(self, x, z, feet_y=None):
        """单列的支撑面高度。

        传 feet_y 时只返回脚部附近（+SUPPORT_TOLERANCE）的方块顶面，
        这样站在悬空方块（如 2 格高的洞顶）下面时不会被吸附到洞顶上；
        不传时保持旧行为（整列最高方块顶面），供地图/出生点使用。
        """
        ix, iz = math.floor(x), math.floor(z)
        if feet_y is None:
            for y in range(config.MAX_BLOCK_Y - 1, config.MIN_BLOCK_Y - 1, -1):
                if (ix, y, iz) in self.world_blocks:
                    return y + 1
            return config.FALL_LIMIT_Y
        top = min(config.MAX_BLOCK_Y - 1,
                  math.floor(feet_y + SUPPORT_TOLERANCE))
        for y in range(top, config.MIN_BLOCK_Y - 1, -1):
            if (ix, y, iz) in self.world_blocks and y + 1 <= feet_y + SUPPORT_TOLERANCE:
                return y + 1
        return config.FALL_LIMIT_Y

    def support_height_at(self, x, z, feet_y, radius):
        """玩家碰撞体积（AABB）覆盖的所有列里的最高支撑面。

        任意一角还压在方块上就算有支撑，避免中心点刚离开方块就穿模下坠。
        """
        if radius <= 0:
            return self.ground_height_at(x, z, feet_y)
        best = config.FALL_LIMIT_Y
        for cx, cz in self.columns(x, z, radius):
            height = self.ground_height_at(cx + .5, cz + .5, feet_y)
            if height > best:
                best = height
        return best

    def body_clearance(self, x, z, feet_cell, radius):
        """AABB 范围内脚部/头部两格是否被方块占据，返回 (脚, 头)。"""
        foot = head = False
        for cx, cz in self.columns(x, z, radius):
            foot = foot or (cx, feet_cell, cz) in self.world_blocks
            head = head or (cx, feet_cell + 1, cz) in self.world_blocks
            if foot and head:
                break
        return foot, head
