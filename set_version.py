#!/usr/bin/env python3
"""CI 手动发版时同步 pyproject.toml 里的版本号。"""

import os
import re
from pathlib import Path

value = os.environ.get('RELEASE_VERSION', '').strip().lstrip('v')
if value:
    path = Path('pyproject.toml')
    text = path.read_text(encoding='utf-8')
    path.write_text(
        re.sub(r'^version = "[^"]+"', f'version = "{value}"', text, flags=re.M),
        encoding='utf-8')
    print(f'version set to {value}')
