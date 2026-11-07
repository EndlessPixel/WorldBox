#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cdn-assets.json 资源下载器

读取当前目录下的 cdn-assets.json，按其定义的 URL -> 相对路径 映射下载文件。

用法：
    python download_cdn_assets.py
    python download_cdn_assets.py -F                  # 强制覆盖
    python download_cdn_assets.py -f my.json -r dist  # 指定文件与根目录
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_FILE = "config/cdn-assets.json"
USER_AGENT = "Mozilla/5.0 (compatible; cdn-assets-downloader/1.0)"


# ---------- 解析配置 ----------

def parse_entry(url, dest):
    """标准化一条映射。"""
    if not isinstance(url, str) or not isinstance(dest, str):
        return None
    url, dest = url.strip(), dest.strip()
    if not url or not dest:
        return None
    return url, dest


def extract_from_list(items):
    mapping = {}
    for item in items:
        if isinstance(item, dict):
            url = item.get("url") or item.get("src") or item.get("from")
            dest = item.get("path") or item.get("dest") or item.get("to") or item.get("file")
            pair = parse_entry(url, dest)
            if pair:
                mapping[pair[0]] = pair[1]
        elif isinstance(item, str) and "->" in item:
            url, dest = item.split("->", 1)
            pair = parse_entry(url, dest)
            if pair:
                mapping[pair[0]] = pair[1]
    return mapping


def extract_from_dict(obj):
    mapping = {}
    for k, v in obj.items():
        if isinstance(v, str):
            pair = parse_entry(k, v)
            if pair:
                mapping[pair[0]] = pair[1]
        elif isinstance(v, dict):
            url = v.get("url") or v.get("src") or k
            dest = v.get("path") or v.get("dest") or v.get("to") or v.get("file")
            pair = parse_entry(url, dest)
            if pair:
                mapping[pair[0]] = pair[1]
    return mapping


def load_mapping(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 解包一层常见包装
    if isinstance(data, dict):
        for key in ("assets", "files", "entries", "items"):
            if key in data and isinstance(data[key], (dict, list)):
                data = data[key]
                break

    if isinstance(data, list):
        mapping = extract_from_list(data)
    elif isinstance(data, dict):
        mapping = extract_from_dict(data)
    else:
        raise ValueError("无法识别的 JSON 结构")

    if not mapping:
        raise ValueError("没有解析出任何 URL -> 路径 映射")
    return mapping


# ---------- 下载 ----------

def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def normalize_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((
        p.scheme, p.netloc,
        urllib.parse.quote(p.path, safe="/%:@&=+$,~"),
        p.params, p.query, p.fragment,
    ))


def download_one(url: str, dest: str, root: Path, force: bool,
                 timeout: int, retries: int) -> bool:
    target = (root / dest).resolve()
    root_resolved = root.resolve()

    # 安全校验：不允许跳出 root
    try:
        target.relative_to(root_resolved)
    except ValueError:
        print(f"  ✗ 拒绝越界路径: {dest}")
        return False

    if target.exists() and not force:
        print(f"  ↷ 已存在，跳过 ({fmt_size(target.stat().st_size)})")
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    real_url = normalize_url(url)

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(real_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done * 100 // total
                            sys.stdout.write(
                                f"\r  ↓ {pct:3d}%  {fmt_size(done)}/{fmt_size(total)}"
                            )
                            sys.stdout.flush()
                        else:
                            sys.stdout.write(f"\r  ↓ {fmt_size(done)}")
                            sys.stdout.flush()
            sys.stdout.write("\r" + " " * 60 + "\r")
            tmp.replace(target)
            print(f"  ✓ 完成 → {dest}  ({fmt_size(target.stat().st_size)})")
            return True
        except urllib.error.HTTPError as e:
            print(f"  ✗ HTTP {e.code}: {e.reason}  (第 {attempt}/{retries} 次)")
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {e}  (第 {attempt}/{retries} 次)")

        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        if attempt < retries:
            time.sleep(min(2 ** attempt, 10))

    print(f"  ✗ 放弃: {url}")
    return False


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="按 cdn-assets.json 下载 CDN 资源")
    ap.add_argument("-f", "--file", default=CONFIG_FILE, help="配置文件（默认 %(default)s）")
    ap.add_argument("-r", "--root", default=".", help="下载根目录（默认当前目录）")
    ap.add_argument("-F", "--force", action="store_true", help="已存在也强制重新下载")
    ap.add_argument("-t", "--timeout", type=int, default=30, help="单次请求超时秒数")
    ap.add_argument("--retries", type=int, default=3, help="失败重试次数")
    args = ap.parse_args()

    cfg_path = Path(args.file)
    if not cfg_path.is_file():
        print(f"✗ 找不到配置文件: {cfg_path.resolve()}")
        sys.exit(1)

    try:
        mapping = load_mapping(cfg_path)
    except Exception as e:
        print(f"✗ 解析 {cfg_path} 失败: {e}")
        sys.exit(1)

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    print(f"共 {len(mapping)} 个资源待处理，根目录: {root.resolve()}\n")

    ok = fail = 0
    for i, (url, dest) in enumerate(mapping.items(), 1):
        print(f"[{i}/{len(mapping)}] {url}")
        if download_one(url, dest, root, args.force, args.timeout, args.retries):
            ok += 1
        else:
            fail += 1
        print()

    print(f"结束：成功 {ok}，失败 {fail}")
    sys.exit(0 if fail == 0 else 2)


if __name__ == "__main__":
    main()