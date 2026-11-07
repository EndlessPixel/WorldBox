#!/usr/bin/env python3
"""准备 Briefcase 源目录并构建 Linux AppImage。

    python build_appimage.py --prepare     # 生成 briefcase_src/ 与图标
    python build_appimage.py --build       # create/build/package AppImage
    python build_appimage.py               # 两步都做

Briefcase 要求 sources 里有一个与 app 同名的启动模块（worldbox/__main__.py），
这里用 runpy 以 __main__ 身份运行 app.py，Ursina 才能找到 update/input。
"""

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'briefcase_src'
DIST = ROOT / 'dist'

ENTRY = '''"""Briefcase AppImage 入口：以 __main__ 身份运行 app.py。"""
import os
import runpy
from pathlib import Path

os.environ.setdefault('WORLDBOX_BRIEFCASE', '1')
os.environ.setdefault(
    'WORLDBOX_DATA_DIR',
    str(Path.home() / '.local' / 'share' / 'WorldBox'))

runpy.run_module('app', run_name='__main__', alter_sys=True)
'''


def version():
    with (ROOT / 'pyproject.toml').open('rb') as f:
        return tomllib.load(f)['tool']['briefcase']['version']


def prepare():
    if SRC.exists():
        shutil.rmtree(SRC)
    (SRC / 'worldbox').mkdir(parents=True)
    (SRC / 'worldbox' / '__init__.py').write_text('"""Briefcase launcher package."""\n',
                                                  encoding='utf-8')
    (SRC / 'worldbox' / '__main__.py').write_text(ENTRY, encoding='utf-8')

    for name in ('app.py', 'cdn_download.py'):
        shutil.copy2(ROOT / name, SRC / name)
    shutil.copytree(ROOT / 'world', SRC / 'world',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    (SRC / 'config' / 'resource_packs').mkdir(parents=True)
    shutil.copy2(ROOT / 'config' / 'blocks.json', SRC / 'config' / 'blocks.json')
    for pack in (ROOT / 'config' / 'resource_packs').glob('*.json'):
        shutil.copy2(pack, SRC / 'config' / 'resource_packs' / pack.name)

    (SRC / 'assets' / 'fonts').mkdir(parents=True)
    fonts = [p for p in (ROOT / 'assets' / 'fonts').glob('*')
             if p.is_file() and p.suffix.lower() in ('.ttc', '.otf', '.ttf', '.txt')]
    for font in fonts:
        shutil.copy2(font, SRC / 'assets' / 'fonts' / font.name)
    if not fonts:
        print('[!] No CJK font found; Chinese text will fall back to ASCII.')

    # 生成简单的应用图标（不入库，CI/本地构建时生成）
    (ROOT / 'resources').mkdir(exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (512, 512), (24, 28, 36, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((96, 160, 416, 416), fill=(134, 96, 67, 255))
        draw.rectangle((96, 96, 416, 176), fill=(92, 172, 78, 255))
        image.save(ROOT / 'resources' / 'icon.png')
    except ImportError:
        print('[!] Pillow missing; Briefcase may need resources/icon.png')
    print('[OK] briefcase_src prepared')


def run(*args):
    print('>', ' '.join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def build():
    for command in ('create', 'build', 'package'):
        if run(sys.executable, '-m', 'briefcase', command,
               'linux', 'appimage', '--no-input') != 0:
            print('[X] briefcase', command, 'failed')
            return 1
    target = DIST / f'WorldBox-{version()}-linux-x86_64.AppImage'
    images = []
    for base in (DIST, ROOT / 'linux', ROOT / 'build'):
        if base.is_dir():
            images.extend(base.rglob('*.AppImage'))
    images = [p for p in images if p.resolve() != target.resolve()]
    if not images:
        print('[X] No .AppImage produced')
        return 1
    DIST.mkdir(exist_ok=True)
    shutil.copy2(max(images, key=lambda p: p.stat().st_mtime), target)
    print('[OK]', target)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prepare', action='store_true')
    ap.add_argument('--build', action='store_true')
    args = ap.parse_args()
    do_all = not (args.prepare or args.build)
    if args.prepare or do_all:
        prepare()
    if args.build or do_all:
        return build()
    return 0


if __name__ == '__main__':
    sys.exit(main())
