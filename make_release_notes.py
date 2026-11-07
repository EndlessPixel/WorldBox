#!/usr/bin/env python3
"""生成 GitHub Release 说明（项目约定的日志格式）。

用法：
    python make_release_notes.py --version 0.1.0 --files dist/*.zip dist/*.AppImage
"""

import argparse
import hashlib
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = 'https://github.com/EndlessPixel/WorldBox'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args):
    try:
        return subprocess.check_output(('git',) + args, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--files', nargs='+', required=True)
    ap.add_argument('--output', default='RELEASE_NOTES.md')
    args = ap.parse_args()

    sha = os.environ.get('GITHUB_SHA') or git_output('rev-parse', 'HEAD')
    message = git_output('log', '-1', '--pretty=%B') or '(no commit message)'
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y年%m月%d日 %H时%M分%S秒')

    lines = [
        '## 📝 提交信息',
        '```',
        message,
        '```',
        '',
        '## 🔧 构建详情',
        '- 项目名称: WorldBox',
        f'- 版本号: {args.version}',
        f'- 提交哈希: [{sha}]({REPO}/commit/{sha})',
        f'- 构建时间: {now}',
        '',
        '## 🔍 文件校验',
        '- 校验算法: SHA-256',
        '',
        '## 📦 文件校验哈希',
        '```',
    ]
    for path in args.files:
        lines.append(f'{Path(path).name}: {sha256(path)}')
    lines += ['```', '', '> 本发布由 GitHub Actions 自动生成', '']

    Path(args.output).write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
