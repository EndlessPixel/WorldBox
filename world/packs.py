"""资源包管理：扫描 config/resource_packs/ 里的资源包定义，按需下载纹理。

- 默认世界不下载任何纹理：缺失文件由 BlockMaterials 按方块颜色生成噪声材质。
- 资源包：config/resource_packs/*.json，顶层 "id" 字段就是命名空间，
  纹理下载到 assets/<id>/blocks/ 下；选中后覆盖默认的噪声材质。
"""

import sys

from . import config

DEFAULT_PACK_ID = 'worldbox'

# 延迟导入顶层 cdn_download（app.py 从项目根启动，root 一定在 sys.path）
_cdn = None


def _downloader():
    global _cdn
    if _cdn is None:
        # 打包模式下 cdn_download 已随应用分发，由打包器的导入器提供
        if not config.IS_PACKAGED and str(config.ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(config.ROOT_DIR))
        import cdn_download
        _cdn = cdn_download
    return _cdn


def available_packs():
    """返回 [(pack_id, config_path), ...]；只扫描 config/resource_packs/*.json。"""
    downloader = _downloader()
    packs = []
    seen = set()
    if config.RESOURCE_PACK_DIR.is_dir():
        for path in sorted(config.RESOURCE_PACK_DIR.glob('*.json')):
            pack_id = downloader.read_pack_id(path)
            if not pack_id or pack_id in seen:
                continue
            seen.add(pack_id)
            packs.append((pack_id, path))
    return packs


def pack_exists(pack_id):
    return any(pid == pack_id for pid, _ in available_packs())


def ensure_pack(pack_id, log=True):
    """确保某个资源包的纹理都已下载；找不到该 id 时静默跳过。"""
    for pid, path in available_packs():
        if pid == pack_id:
            ok, fail = _downloader().ensure_pack(path, root=config.ROOT_DIR, log=log)
            if log and fail:
                print(f'[资源包] {pack_id} 有 {fail} 个文件下载失败，缺失处用颜色噪声兜底')
            return fail == 0
    if log:
        print(f'[资源包] 没有找到 id 为 {pack_id} 的资源包定义')
    return False


def ensure_active(log=True):
    """启动时调用：当前设置选择了资源包时补齐它的缺失纹理。"""
    active = config.SETTINGS.get('resource_pack')
    if active and active != DEFAULT_PACK_ID:
        ensure_pack(active, log=log)
