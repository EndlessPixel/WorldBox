"""体素世界：方块数据、区块网格、射线与地面查询。

每格被分成上下两个 0.5 米的半层：
- 整块方块占满一格（下层，高度 1.0）
- 半砖只占半格（下层或上层，高度 0.5），ID 以 _slab 结尾
因此半砖可以叠成整格高度，也可以放在整块之上只露半格。
渲染、碰撞与支撑高度都按方块的实际高度计算。
"""

import math

from ursina import Entity, Mesh, color, destroy

from . import config
from .blocks import BLOCKS, DEFAULT_BLOCK_ID, SLAB_HEIGHT, is_slab
from .materials import BlockMaterials

SUPPORT_TOLERANCE = 0.05   # 脚部允许与支撑面相差的高度（米）
HALF = 0.5                  # 半层高度

# 侧面方向：(dx, dz, 明暗系数)
SIDE_DIRECTIONS = (
    (1, 0, 0.80),
    (-1, 0, 0.80),
    (0, 1, 0.70),
    (0, -1, 0.70),
)


class VoxelWorld:
    def __init__(self, save_data=None):
        self.world_blocks = {}     # (x, y, z) -> 下层方块 id
        self.world_uppers = {}     # (x, y, z) -> 上层方块 id（半砖）
        self.world_edits = {}      # 玩家改动：(x, y, z) -> {'b': id|None, 't': id|None}
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

    def add_block(self, x, y, z, block_id, layer=0):
        """放置方块：layer 0 = 下层，layer 1 = 上层（只放半砖）。"""
        key = (x, y, z)
        if layer == 1:
            if not is_slab(block_id):
                return False
            self.world_uppers[key] = block_id
        else:
            self.world_blocks[key] = block_id
            if not is_slab(block_id):
                self.world_uppers.pop(key, None)   # 整块占满整格
        self.chunk_blocks.setdefault(self.chunk_coord(x, z), set()).add(key)
        return True

    def remove_block(self, x, y, z, layer=None):
        """移除方块；layer 为 None 时清空整格。"""
        key = (x, y, z)
        changed = False
        if layer is None:
            changed = self.world_blocks.pop(key, None) is not None
            changed = self.world_uppers.pop(key, None) is not None or changed
        elif layer == 1:
            changed = self.world_uppers.pop(key, None) is not None
        else:
            changed = self.world_blocks.pop(key, None) is not None
        return changed

    def can_place(self, x, y, z, layer, block_id):
        """目标位置能否放置：上层要求下层不是整块，下层要求整格为空。"""
        key = (x, y, z)
        if layer == 1:
            lower = self.world_blocks.get(key)
            if lower is not None and not is_slab(lower):
                return False
            return self.world_uppers.get(key) is None
        return (self.world_blocks.get(key) is None
                and self.world_uppers.get(key) is None)

    def record_edit(self, x, y, z):
        """记录玩家改动（存档用）。"""
        key = (x, y, z)
        self.world_edits[key] = {
            'b': self.world_blocks.get(key),
            't': self.world_uppers.get(key),
        }

    def segments(self, x, y, z):
        """该格的实体段 [(y0, y1, block_id)]，按高度从低到高。"""
        out = []
        lower = self.world_blocks.get((x, y, z))
        if lower is not None:
            out.append((y, y + (HALF if is_slab(lower) else 1.0), lower))
        upper = self.world_uppers.get((x, y, z))
        if upper is not None:
            out.append((y + HALF, y + 1.0, upper))
        return out

    def segment_at_height(self, x, y, z, hit_y):
        """命中高度落在哪一段实体上，返回 (y0, y1, block_id)；没有则 None。"""
        for segment in self.segments(x, y, z):
            if segment[0] - 1e-6 <= hit_y <= segment[1] + 1e-6:
                return segment
        return None

    def solid_run(self, x, y, z, hit_y):
        """命中高度所在的连续实体区间 (low, high)；没有则 None。

        两半砖组成整格时返回整格 [y, y+1]，供选择框按实际占据范围显示。
        """
        segments = self.segments(x, y, z)
        index = None
        for i, (y0, y1, _bid) in enumerate(segments):
            if y0 - 1e-6 <= hit_y <= y1 + 1e-6:
                index = i
                break
        if index is None:
            return None
        low, high = segments[index][0], segments[index][1]
        i = index - 1
        while i >= 0 and abs(segments[i][1] - low) < 1e-6:
            low = segments[i][0]
            i -= 1
        i = index + 1
        while i < len(segments) and abs(segments[i][0] - high) < 1e-6:
            high = segments[i][1]
            i += 1
        return low, high

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
        for key, value in list(edits.items())[:30000]:
            try:
                x, y, z = (int(part) for part in str(key).split(','))
            except (TypeError, ValueError):
                continue
            if not (0 <= x < config.WORLD_SIZE and 0 <= z < config.WORLD_SIZE
                    and config.MIN_BLOCK_Y <= y < config.MAX_BLOCK_Y):
                continue
            if isinstance(value, dict):
                lower = value.get('b')
                upper = value.get('t')
            elif value is None:
                lower = upper = None
            else:                      # 旧格式：只有下层
                lower, upper = value, None
            for block_id in (lower, upper):
                if block_id is not None and block_id not in BLOCKS:
                    lower = upper = None
                    break
            self.remove_block(x, y, z)
            if lower is not None:
                self.add_block(x, y, z, lower, layer=0)
            if upper is not None and is_slab(upper):
                self.add_block(x, y, z, upper, layer=1)
            self.record_edit(x, y, z)

    # ---------- 网格 ----------
    def block_top(self, x, y, z):
        """该格最高的实体顶面；没有方块返回 None。"""
        segments = self.segments(x, y, z)
        return segments[-1][1] if segments else None

    def top_block_at(self, x, z):
        """该列最高的方块 (y, block_id)；空列返回 (None, None)。"""
        for y in range(config.MAX_BLOCK_Y - 1, config.MIN_BLOCK_Y - 1, -1):
            segments = self.segments(x, y, z)
            if segments:
                return y, segments[-1][2]
        return None, None

    def _covers_plane(self, x, y, z, plane):
        """该格是否有实体覆盖给定水平面。"""
        for (y0, y1, _) in self.segments(x, y, z):
            if y0 - 1e-6 <= plane <= y1 + 1e-6:
                return True
        return False

    def _segment_blocked(self, x, y, z, low, high):
        """邻居是否完全遮住 [low, high] 这段竖直区间。"""
        for (c, d, _) in self.segments(x, y, z):
            if c <= low + 1e-6 and d >= high - 1e-6:
                return True
        return False

    def build_chunk_mesh(self, cx, cz):
        """把一个区块里所有暴露面合并成一个 Mesh（顶点颜色 + 方块表颜色）。

        按 0.5 米的粒度切分：整块是 1.0 的一段，半砖是 0.5 的一段；
        邻居完全遮住的段不画，只被遮住一半的段只画没被遮住的那一半。
        """
        vertices, triangles, colors, uvs = [], [], [], []
        for (x, y, z) in self.chunk_blocks.get((cx, cz), ()):
            segments = self.segments(x, y, z)
            if not segments:
                continue
            checker = 1.0 if (x + z) % 2 == 0 else 0.94   # 棋盘微调，方便看出 1 米格

            for (y0, y1, block_id) in segments:
                uv_set = self.materials.uvs.get(block_id,
                                                self.materials.uvs[DEFAULT_BLOCK_ID])

                def add_face(corners, shade, face_key, v_range=None):
                    start = len(vertices)
                    factor = shade * checker
                    u0, v0, u1, v1 = uv_set[face_key]
                    if v_range is not None:
                        # 竖直方向裁剪（半砖取贴图下半、整块上半段取上半），
                        # 而不是把整张贴图压扁
                        v0, v1 = v_range
                    face_uv = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))
                    for (vx, vy, vz), (uu, vv) in zip(corners, face_uv):
                        vertices.append((vx, vy, vz))
                        colors.append((factor, factor, factor, 1.0))
                        uvs.append((uu, vv))
                    triangles.extend(((start, start + 1, start + 2),
                                      (start, start + 2, start + 3)))

                # 顶面：被上方方块覆盖时不可见
                if not self._covers_plane(x, y + 1, z, y1):
                    add_face(((x, y1, z), (x, y1, z + 1),
                              (x + 1, y1, z + 1), (x + 1, y1, z)), 1.00, 'top')

                # 底面：下方方块顶面高于本格底部时不可见
                if y0 > config.MIN_BLOCK_Y and not self._covers_plane(x, y - 1, z, y0):
                    add_face(((x, y0, z + 1), (x + 1, y0, z + 1),
                              (x + 1, y0, z), (x, y0, z)), 0.45, 'bottom')

                # 侧面：按 0.5 细分，邻居完全遮住的段不画
                side_u0, side_v0, side_u1, side_v1 = uv_set['side']
                side_dv = side_v1 - side_v0
                for (dx, dz, shade) in SIDE_DIRECTIONS:
                    low = y0
                    while low < y1 - 1e-6:
                        high = min(low + HALF, y1)
                        if not self._segment_blocked(x + dx, y, z + dz, low, high):
                            if dx == 1:
                                corners = ((x + 1, low, z + 1), (x + 1, high, z + 1),
                                           (x + 1, high, z), (x + 1, low, z))
                            elif dx == -1:
                                corners = ((x, low, z), (x, high, z),
                                           (x, high, z + 1), (x, low, z + 1))
                            elif dz == 1:
                                corners = ((x, low, z + 1), (x, high, z + 1),
                                           (x + 1, high, z + 1), (x + 1, low, z + 1))
                            else:
                                corners = ((x + 1, low, z), (x + 1, high, z),
                                           (x, high, z), (x, low, z))
                            # 贴图按整格高度裁剪：段占格内 [a, b] → 取对应纵向区间
                            v_low = side_v0 + side_dv * (low - y)
                            v_high = side_v0 + side_dv * (high - y)
                            add_face(corners, shade, 'side',
                                     v_range=(v_low, v_high))
                        low = high

        return Mesh(vertices=vertices, triangles=triangles, colors=colors, uvs=uvs,
                    mode='triangle')

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
        print(f'[世界] 已生成 {len(self.chunk_meshes)} 个区块，'
              f'{len(self.world_blocks) + len(self.world_uppers)} 个方块')

    def set_tint(self, tint):
        """昼夜变化时统一乘到所有区块上。"""
        self.block_tint = tint
        for entity in self.chunk_meshes.values():
            entity.color = tint

    def destroy(self):
        """退出到主页面时销毁所有区块实体。"""
        for entity in self.chunk_meshes.values():
            destroy(entity)
        self.chunk_meshes.clear()
        self.chunk_blocks.clear()
        self.world_blocks.clear()
        self.world_uppers.clear()
        self.world_edits.clear()

    # ---------- 查询 ----------
    @staticmethod
    def _segment_hit(oy, dy, y0, y1, t_enter, t_exit):
        """射线与竖直段 [y0, y1] 的交点。

        返回 (进入时间, 命中高度)；这段没被射线穿过则返回 (None, None)。
        命中高度取"射线先碰到的那一面"：向下射线碰到段顶，向上射线碰到段底。
        """
        if dy > 1e-9:
            t_in, t_out = (y0 - oy) / dy, (y1 - oy) / dy
            hit_y = y0
        elif dy < -1e-9:
            t_in, t_out = (y1 - oy) / dy, (y0 - oy) / dy
            hit_y = y1
        else:
            if y0 - 1e-6 <= oy <= y1 + 1e-6:
                return t_exit, oy          # 水平射线穿过该段（命中侧面）
            return None, None
        if t_out < t_enter - 1e-6 or t_in > t_exit + 1e-6:
            return None, None
        if t_in < t_enter - 1e-6:
            # 进入该格时已经在段内部：命中迎面那一面
            return t_enter, (y1 if dy < 0 else y0)
        return t_in, hit_y

    def raycast(self, origin, direction, max_distance):
        """体素 DDA：返回 (命中方块坐标, 命中面法线, 命中高度)，未命中返回 None。

        命中高度是实体真实表面（半砖顶面在 y+0.5），用于判断放置到哪一层。
        """
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
        t_enter = 0.0
        t_exit = min(t_max_x, t_max_y, t_max_z)
        for _ in range(128):
            if t_enter > max_distance:
                break
            # 从侧面进入该格时的高度：射线此时已在该段的竖直区间内，
            # 命中的是这一格的侧面，不能误判成顶面/底面
            entry_y = origin[1] + dy * t_enter
            # 竖直射线按方向取最近的段：向下先撞最高段，向上先撞最低段
            segments = self.segments(x, y, z)
            if dy < -1e-9:
                segments = list(reversed(segments))
            for (y0, y1, _bid) in segments:
                if (normal != (0, 0, 0) and normal[1] == 0
                        and y0 - 1e-6 <= entry_y <= y1 + 1e-6):
                    return (x, y, z), normal, entry_y
                t_in, hit_y = self._segment_hit(origin[1], dy, y0, y1,
                                               t_enter, t_exit)
                if t_in is None:
                    continue
                if dy < -1e-9:
                    face_normal = (0, 1, 0)      # 向下射线：命中顶面
                elif dy > 1e-9:
                    face_normal = (0, -1, 0)     # 向上射线：命中底面
                else:
                    face_normal = normal        # 水平射线：命中侧面
                return (x, y, z), face_normal, hit_y
            if t_max_x < t_max_y and t_max_x < t_max_z:
                x += step_x
                t_enter, t_exit = t_max_x, t_max_x + t_delta_x
                t_max_x += t_delta_x
                normal = (-step_x, 0, 0)
            elif t_max_y < t_max_z:
                y += step_y
                t_enter, t_exit = t_max_y, t_max_y + t_delta_y
                t_max_y += t_delta_y
                normal = (0, -step_y, 0)
            else:
                z += step_z
                t_enter, t_exit = t_max_z, t_max_z + t_delta_z
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

        传 feet_y 时只返回脚部附近（+SUPPORT_TOLERANCE）的实体顶面，
        这样站在悬空方块（如 2 格高的洞顶）下面时不会被吸附到洞顶上；
        不传时返回整列最高顶面，供地图/出生点使用。
        """
        ix, iz = math.floor(x), math.floor(z)
        if feet_y is None:
            for y in range(config.MAX_BLOCK_Y - 1, config.MIN_BLOCK_Y - 1, -1):
                segments = self.segments(ix, y, iz)
                if segments:
                    return segments[-1][1]
            return config.FALL_LIMIT_Y
        top = min(config.MAX_BLOCK_Y - 1,
                  math.floor(feet_y + SUPPORT_TOLERANCE))
        for y in range(top, config.MIN_BLOCK_Y - 1, -1):
            for (_y0, y1, _) in reversed(self.segments(ix, y, iz)):
                if y1 <= feet_y + SUPPORT_TOLERANCE:
                    return y1
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
        """AABB 范围内与身体竖直区间重叠的实体里最高的顶面；没有则返回 None。

        脚下的方块（顶面不高于脚部）不算重叠，因此站在半砖上不会被自己挡住。
        """
        bottom_limit = math.floor(feet_y + 0.001)
        top_limit = math.ceil(feet_y + height - 0.001)
        highest = None
        for cx, cz in self.columns(x, z, radius):
            for cy in range(bottom_limit, top_limit + 1):
                for (block_bottom, block_top, _) in self.segments(cx, cy, cz):
                    if block_top <= feet_y + SUPPORT_TOLERANCE:
                        continue                   # 已经踩在脚下的方块
                    if block_bottom >= feet_y + height - SUPPORT_TOLERANCE:
                        continue                   # 高过头顶，不算撞到
                    if highest is None or block_top > highest:
                        highest = block_top
        return highest
