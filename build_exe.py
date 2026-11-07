#!/usr/bin/env python3
"""在 Windows 上把 WorldBox 打包成 dist/WorldBox/WorldBox.exe。

PyInstaller 不支持跨平台交叉编译，Windows exe 必须在 Windows 机器上构建：

    pip install -r requirements.txt -r requirements-build.txt
    python build_exe.py              # 无控制台窗口
    python build_exe.py --console    # 保留控制台，方便排查启动错误

在 Linux/macOS 上直接运行本脚本只会提示改用 GitHub Actions 的
"Build Windows EXE" 工作流。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# PyInstaller 的 --add-data 分隔符：Windows 是 ';'，POSIX 是 ':'
SEP = os.pathsep


def version():
    with (ROOT / 'pyproject.toml').open('rb') as f:
        return tomllib.load(f)['tool']['briefcase']['version']


def main():
    ap = argparse.ArgumentParser(description='构建 WorldBox Windows exe')
    ap.add_argument('--console', action='store_true', help='保留控制台窗口')
    ap.add_argument('--onefile', action='store_true', help='打成单个 exe（启动较慢）')
    args = ap.parse_args()

    if sys.platform != 'win32':
        print('[X] Windows exe must be built on Windows (PyInstaller has no cross-compile).')
        print('    Push to GitHub and use the "Build Windows EXE" workflow.')
        return 2
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print('[X] Missing PyInstaller: pip install -r requirements-build.txt')
        return 2

    fonts = [p for p in (ROOT / 'assets' / 'fonts').glob('Noto*.*')
             if p.suffix.lower() in ('.ttc', '.otf', '.ttf')]
    if not fonts:
        print('[!] CJK font not found; Chinese text will fall back to ASCII.')
        print('    CI downloads the OFL-licensed Noto Sans SC automatically.')

    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
           '--onefile' if args.onefile else '--onedir',
           '--name', 'WorldBox']
    if not args.console:
        cmd.append('--windowed')
    for package in ('ursina', 'panda3d', 'direct'):
        cmd += ['--collect-all', package]
    for module in ('world.game', 'world.inputs', 'world.keybinds',
                   'world.mapview', 'world.packs', 'cdn_download'):
        cmd += ['--hidden-import', module]

    # 只读的默认数据打进包里；config.py 首次启动会复制到 exe 目录（可写）
    for src, dst in (('config/blocks.json', 'config'),
                     ('config/resource_packs', 'config/resource_packs'),
                     ('assets/fonts', 'assets/fonts')):
        if (ROOT / src).exists():
            cmd += ['--add-data', f'{src}{SEP}{dst}']
    cmd.append('app.py')

    print('>', ' '.join(cmd))
    result = subprocess.call(cmd, cwd=ROOT)
    if result == 0:
        print('\n[OK] Build complete: dist/WorldBox/WorldBox.exe')
        archive = ROOT / 'dist' / f'WorldBox-{version()}-windows-x86_64.zip'
        shutil.make_archive(str(archive.with_suffix('')), 'zip',
                            root_dir=ROOT / 'dist', base_dir='WorldBox')
        print('[OK] Release archive:', archive)
    return result


if __name__ == '__main__':
    sys.exit(main())
