#!/usr/bin/env python3
"""准备 Briefcase 源目录并构建 Linux AppImage。

    python build_appimage.py --prepare     # 生成 briefcase_src/ 与图标
    python build_appimage.py --build       # create/build/package AppImage
    python build_appimage.py               # 两步都做

Briefcase 要求 sources 里有一个与 app 同名的启动模块（worldbox/__main__.py），
这里用 runpy 以 __main__ 身份运行 app.py，Ursina 才能找到 update/input。
"""

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'briefcase_src'
DIST = ROOT / 'dist'
TEMPLATE = ROOT / 'build' / 'appimage-template'
TEMPLATE_URL = 'https://github.com/beeware/briefcase-linux-appimage-template.git'
TEMPLATE_BRANCH = 'v0.4.7'

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


def prepare_template():
    """克隆官方 AppImage 模板，补上漏声明的 host_arch 变量。

    Briefcase 0.4.7 的模板在 briefcase.toml 里用了 cookiecutter.host_arch，
    但 cookiecutter.json 没有声明它；cookiecutter 会忽略未声明的 extra_context
    变量，导致 "OrderedDict object has no attribute 'host_arch'"。
    """
    if not TEMPLATE.exists():
        TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
        print('>', 'git clone', TEMPLATE_BRANCH, TEMPLATE_URL, flush=True)
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', TEMPLATE_BRANCH,
                        TEMPLATE_URL, str(TEMPLATE)], check=True, cwd=ROOT)
    context_file = TEMPLATE / 'cookiecutter.json'
    data = json.loads(context_file.read_text(encoding='utf-8'))
    if 'host_arch' not in data:
        data['host_arch'] = 'x86_64'
        context_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n',
                                encoding='utf-8')
        print('[OK] patched cookiecutter.json: host_arch')


def prepare():
    prepare_template()
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
        # --no-docker：CI 本身就是 Linux，用宿主机 Python 装依赖，
        # 避免官方 Docker 镜像里缺少 /usr/bin/python3.12 的问题
        if run(sys.executable, '-m', 'briefcase', command,
               'linux', 'appimage', '--no-input', '--no-docker') != 0:
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
