"""M 键全屏地图：用 blocks.json 的 color 为每列最高方块画色块。

不依赖纹理/资源包，所有色块合并成若干带顶点色的 Mesh（分组避免
Panda3D 的 16 位索引上限），红点表示玩家位置。
"""

from ursina import Entity, Mesh, Text, camera, color, destroy, window

from . import config, i18n
from .blocks import BLOCKS

ROW_GROUPS = 8          # 每组 16 行，单个 Mesh 顶点数 < 65536


class WorldMap:
    def __init__(self, world, player):
        self.world = world
        self.player = player
        self.is_open = False
        self.half_x = (window.aspect_ratio / 2) * .94
        self.half_y = .47

        self.root = Entity(parent=camera.ui, enabled=False, z=-15)
        Entity(parent=self.root, model='quad', color=color.rgba(.04, .05, .07, 1),
               scale=(2, 2), z=1)
        self.cell_entities = [Entity(parent=self.root, color=color.white)
                              for _ in range(ROW_GROUPS)]
        self.marker = Entity(parent=self.root, model='quad',
                             color=color.rgba(1, .18, .18, 1), scale=.012, z=-1)
        self.title = Text(parent=self.root, text=i18n.t('map.title'),
                          origin=(0, 0), y=.485, scale=1.2, color=color.white, z=-2)
        self.hint = Text(parent=self.root, text=i18n.t('map.hint'),
                         origin=(0, 0), y=-.485, scale=.6, color=color.white, z=-2)

    # ---------- 色块网格 ----------
    def _cell_color(self, x, z):
        top, block_id = self.world.top_block_at(x, z)
        rgb = BLOCKS.get(block_id, {}).get('color', (60, 60, 60))
        # 棋盘微调 + 高度明暗：挖低的列更暗、堆高的列更亮，纯用 color 表现地形
        shade = .94 if (x + z) % 2 else 1.0
        if top is not None:
            if top < 0:
                shade *= max(.45, 1 + top * .08)
            elif top > 0:
                shade *= min(1.2, 1 + top * .03)
        return (min(1.0, rgb[0] / 255 * shade),
                min(1.0, rgb[1] / 255 * shade),
                min(1.0, rgb[2] / 255 * shade), 1)

    def rebuild(self):
        """世界方块变化后重建色块（128x128 个色块，按行分组）。"""
        n = config.WORLD_SIZE
        rows_per_group = n // ROW_GROUPS
        dx = 2 * self.half_x / n
        dy = 2 * self.half_y / n
        for group, entity in enumerate(self.cell_entities):
            vertices, triangles, colors = [], [], []
            for z in range(group * rows_per_group, (group + 1) * rows_per_group):
                y1 = self.half_y - z * dy
                y0 = y1 - dy
                for x in range(n):
                    x0 = -self.half_x + x * dx
                    x1 = x0 + dx
                    rgba = self._cell_color(x, z)
                    start = len(vertices)
                    vertices.extend(((x0, y0, 0), (x1, y0, 0),
                                     (x1, y1, 0), (x0, y1, 0)))
                    colors.extend((rgba,) * 4)
                    triangles.extend(((start, start + 1, start + 2),
                                      (start, start + 2, start + 3)))
            entity.model = Mesh(vertices=vertices, triangles=triangles,
                                colors=colors, mode='triangle')
            entity.set_two_sided(True)
        self.update_marker()

    def update_marker(self):
        n = config.WORLD_SIZE
        self.marker.position = (
            -self.half_x + (self.player.pos.x / n) * 2 * self.half_x,
            self.half_y - (self.player.pos.z / n) * 2 * self.half_y,
            -1,
        )

    # ---------- 开关 ----------
    def toggle(self):
        self.is_open = not self.is_open
        if self.is_open:
            self.rebuild()
        self.root.enabled = self.is_open
        return self.is_open

    def close(self):
        self.is_open = False
        self.root.enabled = False

    def retranslate(self):
        self.title.text = i18n.t('map.title')
        self.hint.text = i18n.t('map.hint')

    def destroy(self):
        """退出到主页面时销毁地图实体。"""
        destroy(self.root)
        self.cell_entities = []
