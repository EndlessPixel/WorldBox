"""体素世界：方块数据、区块网格、射线与地面查询。

方块可以是整块（高 1 米）或半砖（高 0.5 米，ID 以 _slab 结尾）：
渲染、碰撞与支撑高度都按方块的实际高度计算。
"""

import math

from ursina import Entity, Mesh, color, destroy

from . import config
from .blocks import BLOCKS, DEFAULT_BLOCK_ID, SLAB_HEIGHT, is_slab
from .materials import BlockMaterials

SUPPORT_TOLERANCE = 0.05   # 脚部允许与支撑面相差的高度（米）

# 侧面方向：(dx, dz, 明暗系数)
SIDE_DIRECTIONS = (
    (1, 0, 0.80),
    (-1, 0, 0.80),
    (0, 1, 0.70),
    (0, -1, 0.70),
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
    def block_top(self, x, y, z):
        """该格方块的顶面高度（半砖 0.5 / 整块 1.0）；没有方块返回 None。"""
        block_id = self.world_blocks.get((x, y, z))
        if block_id is None:
            return None
        return y + (SLAB_HEIGHT if is_slab(block_id) else 1.0)

    def top_block_at(self, x, z):
        """该列最高的方块 (y, block_id)；空列返回 (None, None)。"""
        for y in range(config.MAX_BLOCK_Y - 1, config.MIN_BLOCK_Y - 1, -1):
            block_id = self.world_blocks.get((x, y, z))
            if block_id is not None:
                return y, block_id
        return None, None

    def build_chunk_mesh(self, cx, cz):
        """把一个区块里所有暴露面合并成一个 Mesh（顶点颜色 + 方块表颜色）。

        半砖只占格子下半部分：顶面在 y+0.5，侧面按邻居高度决定画哪一段。
        """
        vertices, triangles, colors, uvs = [], [], [], []
        for (x, y, z) in self.chunk_blocks.get((cx, cz), ()):
            block_id = self.world_blocks.get((x, y, z))
            if block_id is None:
                continue
            uv_set = self.materials.uvs.get(block_id, self.materials.uvs[DEFAULT_BLOCK_ID])
            checker = 1.0 if (x + z) % 2 == 0 else 0.94   # 棋盘微调，方便看出 1 米格
            y_bottom = y
            y_top = y + (SLAB_HEIGHT if is_slab(block_id) else 1.0)

            def add_face(corners, shade, face_key):
                start = len(vertices)
                factor = shade * checker
                u0, v0, u1, v1 = uv_set[face_key]
                face_uv = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))
                for (vx, vy, vz), (uu, vv) in zip(corners, face_uv):
                    vertices.append((vx, vy, vz))
                    colors.append((factor, factor, factor, 1.0))
                    uvs.append((uu, vv))
                triangles.extend(((start, start + 1, start + 2), (start, start + 2, start + 3)))

            # 顶面：被上方方块覆盖时不可见
            above = self.world_blocks.get((x, y + 1, z))
            covered = False
            if above is not None:
                above_bottom = y + 1
                above_top = above_bottom + (SLAB_HEIGHT if is_slab(above) else 1.0)
                covered = (above_bottom - 1e-6 <= y_top <= above_top + 1e-6)
            if not covered:
                add_face(((x, y_top, z), (x, y_top, z + 1),
                          (x + 1, y_top, z + 1), (x + 1, y_top, z)), 1.00, 'top')

            # 底面：下方方块顶面高于本格底部时不可见
            if y > config.MIN_BLOCK_Y:
                below_top = self.block_top(x, y - 1, z)
                if below_top is None or below_top < y_bottom - 1e-6:
                    add_face(((x, y_bottom, z + 1), (x + 1, y_bottom, z + 1),
                              (x + 1, y_bottom, z), (x, y_bottom, z)), 0.45, 'bottom')

            # 四个侧面：邻居整块挡住全侧，邻居半砖只挡住下半段
            for (dx, dz, shade) in SIDE_DIRECTIONS:
                neighbour = self.world_blocks.get((x + dx, y, z + dz))
                if neighbour is None:
                    seg_bottom, seg_top = y_bottom, y_top
                else:
                    neighbour_top = y + (SLAB_HEIGHT if is_slab(neighbour) else 1.0)
                    if neighbour_top >= y_top - 1e-6:
                        continue        # 完全被遮挡
                    seg_bottom, seg_top = max(y_bottom, neighbour_top), y_top
                if seg_top - seg_bottom <= 1e-6:
                    continue
                if dx == 1:
                    corners = ((x + 1, seg_bottom, z + 1), (x + 1, seg_top, z + 1),
                               (x + 1, seg_top, z), (x + 1, seg_bottom, z))
                elif dx == -1:
                    corners = ((x, seg_bottom, z), (x, seg_top, z),
                               (x, seg_top, z + 1), (x, seg_bottom, z + 1))
                elif dz == 1:
                    corners = ((x, seg_bottom, z + 1), (x, seg_top, z + 1),
                               (x + 1, seg_top, z + 1), (x + 1, seg_bottom, z + 1))
                else:
                    corners = ((x + 1, seg_bottom, z), (x + 1, seg_top, z),
                               (x, seg_top, z), (x, seg_bottom, z))
                add_face(corners, shade, 'side')

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
        """单列的支撑面高度（半砖顶面为 y+0.5）。

        传 feet_y 时只返回脚部附近（+SUPPORT_TOLERANCE）的方块顶面，
        这样站在悬空方块（如 2 格高的洞顶）下面时不会被吸附到洞顶上；
        不传时返回整列最高方块顶面，供地图/出生点使用。
        """
        ix, iz = math.floor(x), math.floor(z)
        if feet_y is None:
            for y in range(config.MAX_BLOCK_Y - 1, config.MIN_BLOCK_Y - 1, -1):
                block_id = self.world_blocks.get((ix, y, iz))
                if block_id is not None:
                    return y + (SLAB_HEIGHT if is_slab(block_id) else 1.0)
            return config.FALL_LIMIT_Y
        top = min(config.MAX_BLOCK_Y - 1,
                  math.floor(feet_y + SUPPORT_TOLERANCE))
        for y in range(top, config.MIN_BLOCK_Y - 1, -1):
            block_id = self.world_blocks.get((ix, y, iz))
            if block_id is None:
                continue
            block_top = y + (SLAB_HEIGHT if is_slab(block_id) else 1.0)
            if block_top <= feet_y + SUPPORT_TOLERANCE:
                return block_top
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

    def body_overlap_top(self, x, z, feet_y, height, radius):
        """AABB 范围内与身体竖直区间重叠的方块里最高的顶面；没有则返回 None。

        脚下的方块（顶面不高于脚部）不算重叠，因此站在半砖上不会被自己挡住。
        """
        bottom_limit = math.floor(feet_y + 0.001)
        top_limit = math.ceil(feet_y + height - 0.001)
        highest = None
        for cx, cz in self.columns(x, z, radius):
            for cy in range(bottom_limit, top_limit + 1):
                block_id = self.world_blocks.get((cx, cy, cz))
                if block_id is None:
                    continue
                block_bottom = cy
                block_top = cy + (SLAB_HEIGHT if is_slab(block_id) else 1.0)
                if block_top <= feet_y + SUPPORT_TOLERANCE:
                    continue                       # 已经踩在脚下的方块
                if block_bottom >= feet_y + height - SUPPORT_TOLERANCE:
                    continue                       # 高过头顶，不算撞到
                if highest is None or block_top > highest:
                    highest = block_top
        return highest
