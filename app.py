"""
3D 世界 - Python + Ursina
=========================
入口文件。游戏主体拆分在 world/ 包里

操作：WASD 移动 / Ctrl 疾跑 / Space 跳 / Shift 蹲 / C 放大
      左键挖 / 右键放 / 中键取方块 / 滚轮切快捷栏 / 1-9 选格
      E 背包（点击拾取、再点快捷栏放入）/ ESC 菜单 / F5 存档

安装：pip install ursina
"""

import os
import sys

# 打包成 exe 后可能是 cp1252 控制台或无 stdout，中文日志会让 print 抛编码错误
if getattr(sys, 'frozen', False):
    for _stream_name in ('stdout', 'stderr'):
        _stream = getattr(sys, _stream_name, None)
        if _stream is None:
            setattr(sys, _stream_name, open(os.devnull, 'w', encoding='utf-8'))
        elif hasattr(_stream, 'reconfigure'):
            try:
                _stream.reconfigure(encoding='utf-8', errors='replace')
            except (OSError, ValueError, AttributeError):
                pass

from ursina import Ursina, application, color, window

from world import config
from world.game import Game

# 打包成 exe 后 sys.argv[0] 不一定指向数据目录；显式指向可写的根目录，
# Ursina 才能递归找到 assets/fonts 里的中文字体
application.asset_folder = config.ROOT_DIR

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
