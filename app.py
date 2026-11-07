"""
3D 世界 - Python + Ursina
=========================
入口文件。游戏主体拆分在 world/ 包里：

- world/config.py   配置与 setting.json
- world/blocks.py   方块表（blocks.json）
- world/storage.py  存档读写（world_save.json）
- world/inputs.py   X11 物理键鼠轮询
- world/voxel.py    体素数据、区块网格、射线
- world/player.py   玩家移动/视角/跳跃/重力
- world/ui.py       HUD、快捷栏、背包、菜单、准心
- world/game.py     输入分发、每帧更新、挖掘/放置、昼夜

操作：WASD 移动 / Ctrl 疾跑 / Space 跳 / Shift 蹲 / C 放大
      左键挖 / 右键放 / 中键取方块 / 滚轮切快捷栏 / 1-9 选格
      E 背包（点击拾取、再点快捷栏放入）/ ESC 菜单 / F5 存档

安装：pip install ursina
"""

from ursina import Ursina, color, window

from world.game import Game

app = Ursina()
window.title = 'WorldBox'
window.color = color.rgb(145, 200, 240)
window.exit_button.enabled = False   # 右上角开发模式的 X 按钮用不上，隐藏

game = Game()


def update():
    game.update()


def input(key):
    game.input(key)


app.run()
