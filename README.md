<div align="center">

# WorldBox

**一个用 Python + Ursina 写的小型体素沙盒 —— 可编辑方块世界、资源包、全屏地图与可自定义按键。**

[English](README_EN.md) · 简体中文

[![Build](https://github.com/EndlessPixel/WorldBox/actions/workflows/build.yml/badge.svg)](https://github.com/EndlessPixel/WorldBox/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/EndlessPixel/WorldBox?label=Release)](https://github.com/EndlessPixel/WorldBox/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

[⬇️ 下载 Windows 版](https://github.com/EndlessPixel/WorldBox/releases/latest) · [⬇️ 下载 Linux AppImage](https://github.com/EndlessPixel/WorldBox/releases/latest)

</div>

---

## 📖 目录

- [✨ 特性](#-特性)
- [🕹️ 操作](#️操作)
- [🚀 快速开始](#-快速开始)
- [📦 构建产物](#-构建产物)
- [🧩 项目结构](#-项目结构)
- [⚙️ 配置](#️配置)
- [🎨 资源包](#-资源包)
- [💾 存档与数据](#-存档与数据)
- [🔄 发布流程](#-发布流程)
- [❓ 常见问题](#-常见问题)
- [🤝 参与贡献](#-参与贡献)
- [📄 许可与致谢](#-许可与致谢)

---

## ✨ 特性

- **真正的体素世界** —— 128×128 米、按 16×16 分块合并渲染，只生成暴露面，挖掘/放置只重建受影响的区块。
- **完整的玩家体积** —— AABB 碰撞体积，脚部/头部分别判定；身体任意一角仍压在方块上就不会掉下去；水平移动拆成 ≤0.05m 子步，杜绝掉帧穿墙。
- **潜行防坠** —— 按住 `Shift` 不会走下悬崖，脚下被挖空也不会坠落，松开立即恢复重力。
- **11 种方块，含半砖** —— 草方块、泥土、石头、原石、黑曜石、红砖、末地石、基岩，以及石头 / 原石 / 红砖三种**半砖**（高 0.5 米，可叠成台阶），颜色与纹理都可自定义。
- **资源包系统** —— 用一份 JSON 描述纹理来源，运行时下载到自己的命名空间；支持在游戏内切换、下载、查看状态。
- **全屏地图（`M`）** —— 128×128 色块俯视图，用方块颜色绘制地形，红色标记玩家位置。
- **背包与物品栏** —— 3×9 背包 + 9 格快捷栏，左键拾取/交换、右键复制或替换，悬停显示名称、ID 与颜色。
- **按键绑定** —— 12 个动作全部可重绑定，冲突自动互换，配置持久化到 `config/keys.json`。
- **设置面板** —— 语言、资源包、自动跳跃与高度、视距、FOV、视角晃动、亮度，修改即时生效。
- **中英双语** —— 完整 i18n，界面语言可随时切换。
- **昼夜与视野** —— 180 秒一昼夜的太阳光照、视距剔除、移动视角晃动。
- **跨平台输入** —— Linux 走 X11、Windows 走 Win32 物理轮询，绕开 Ursina 事件层丢按键的问题。

---

## 🕹️ 操作

| 按键 | 功能 | 按键 | 功能 |
| --- | --- | --- | --- |
| `W` `A` `S` `D` | 移动 | `Ctrl` | 疾跑 |
| `Space` | 跳跃 | `Shift` | 蹲下 / 潜行防坠 |
| `C` | 放大视角 | `M` | 全屏地图 |
| 左键 | 挖掘方块 | 右键 | 放置方块 |
| 中键 | 取样方块到快捷栏 | 滚轮 | 切换快捷栏 |
| `1` ~ `9` | 选择快捷栏 | `E` | 打开背包 |
| `ESC` | 暂停菜单 / 返回 | `F5` | 立即存档 |

> 所有按键都可以在 **ESC → 按键绑定** 里重新指定。

---

## 🚀 快速开始

### 从源码运行

```bash
git clone https://github.com/EndlessPixel/WorldBox.git
cd WorldBox

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

需要 Python 3.12 或更高版本、Linux/macOS 上的 X11 或 Windows 桌面环境。

### 直接下载玩

从 [Releases](https://github.com/EndlessPixel/WorldBox/releases/latest) 下载：

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| Windows | `WorldBox-<版本>-windows-x86_64.zip` | 解压后运行 `WorldBox.exe`，请保留整个目录 |
| Linux | `WorldBox-<版本>-linux-x86_64.AppImage` | `chmod +x` 后直接运行，需要 FUSE（或 `--appimage-extract-and-run`） |

---

## 📦 构建产物

两个打包器各司其职，CI 会同时产出：

- **PyInstaller → Windows `.exe`**：`build_exe.py` 把 Ursina/Panda3D 运行时、方块表、资源包定义和中文字体一起打进单目录 exe 包，并额外生成 zip 便于分发。
- **Briefcase → Linux `.AppImage`**：`build_appimage.py` 用 Briefcase 生成 AppDir，再由 linuxdeploy 封装成单文件 AppImage。

```bash
# Windows（只能在 Windows 上构建）
pip install -r requirements-build.txt
python build_exe.py                 # 产物：dist/WorldBox/ 与 dist/WorldBox-<版本>-windows-x86_64.zip

# Linux
pip install -r requirements-build.txt
python build_appimage.py             # 产物：dist/WorldBox-<版本>-linux-x86_64.AppImage
```

构建脚本会顺带准备 Briefcase 所需的源目录、生成应用图标，并把官方 AppImage 模板补上缺失的 `host_arch` 变量。

---

## 🧩 项目结构

```
WorldBox/
├── app.py                  # 入口：创建窗口、装配 Game
├── world/                  # 游戏主体
│   ├── game.py             # 编排：输入分发、挖掘/放置、昼夜、存档
│   ├── player.py           # 移动、跳跃、AABB 碰撞、潜行防坠
│   ├── voxel.py            # 体素数据、区块网格、DDA 射线
│   ├── blocks.py           # 方块表（读 config/blocks.json）
│   ├── materials.py        # 纹理图集与等距 3D 物品图标
│   ├── mapview.py          # M 键全屏地图（顶点色色块）
│   ├── ui.py               # HUD / 背包 / 菜单 / 设置 / 资源包 / 按键绑定
│   ├── keybinds.py         # 按键绑定与翻译
│   ├── inputs.py           # X11 / Win32 物理输入轮询
│   ├── i18n.py             # 中英文案
│   ├── packs.py            # 资源包扫描与下载
│   ├── storage.py          # 存档读写（原子替换）
│   └── config.py           # 常量与 setting.json 读写
├── config/
│   ├── blocks.json         # 方块定义（id / name / color）
│   └── resource_packs/     # 资源包定义
├── assets/                 # 运行时资源（纹理、字体；不入库）
├── build_exe.py            # PyInstaller 打包
├── build_appimage.py       # Briefcase 打包
├── make_release_notes.py   # 生成发布说明
└── .github/workflows/      # CI：构建 + 发布
```

---

## ⚙️ 配置

### 设置项

`config/setting.json`（首次运行自动生成）：

| 键 | 说明 | 默认 |
| --- | --- | --- |
| `language` | 界面语言 `zh` / `en` | `zh` |
| `resource_pack` | 资源包 id，空字符串表示默认 | `""` |
| `auto_jump` | 自动跳上 1 格台阶 | `true` |
| `auto_jump_height` | 自动跳跃可跨越的高度 | `1.0` |
| `view_distance` | 区块可见距离（米） | `96` |
| `fov` | 视场角 | `40` |
| `view_bob` | 移动视角晃动幅度 | `0.03` |
| `brightness` | 画面亮度 | `1.0` |

游戏内 **ESC → 设置** 可直接调整，改动即时生效并原子写回文件。

### 按键绑定

`config/keys.json` 保存 12 个动作对应的物理键名：

```json
{
  "forward": "w", "back": "s", "left": "a", "right": "d",
  "jump": "space", "crouch": "shift", "sprint": "ctrl",
  "zoom": "c", "inventory": "e", "menu": "escape",
  "save": "f5", "map": "m"
}
```

在 **ESC → 按键绑定** 中用 ↑↓ 选择、回车后按任意新键完成重绑定、`R` 恢复默认；重复绑定会自动与原动作互换。游戏内部始终使用默认键名判定动作，因此自定义键位不会影响其它逻辑。

---

## 🎨 资源包

资源包就是一份 `cdn-assets.json`：顶层 `id` 是命名空间，其余是 `URL -> 相对路径` 的映射。

```json
{
  "id": "minecraft",
  "https://assets.mcasset.cloud/26.3/assets/minecraft/textures/block/stone.png": "assets/worldbox/blocks/stone.png"
}
```

- 下载位置会被重写到 `assets/<id>/blocks/`，因此不同资源包互不覆盖。
- 放在 `config/resource_packs/` 下的文件会自动出现在游戏内的 **资源包** 页面。
- 页面里 ↑↓ 选择、**回车**应用、**R**下载、**ESC** 返回；应用后会重建纹理图集、区块网格与所有物品图标，无需重启。
- 未收录的方块会按 ID 后缀自动查找同名纹理（如 `worldbox:obsidian.block` → `obsidian.png`）。

---

## 💾 存档与数据

| 数据 | Windows | Linux AppImage |
| --- | --- | --- |
| 存档 `world_save.json` | exe 同目录 | `~/.local/share/WorldBox/` |
| 设置 `config/setting.json` | exe 同目录 | `~/.local/share/WorldBox/` |
| 按键 `config/keys.json` | exe 同目录 | `~/.local/share/WorldBox/` |
| 资源包纹理 | `assets/<id>/` | `~/.local/share/WorldBox/assets/<id>/` |

存档采用「写临时文件再原子替换」，只记录玩家改动过的方块，损坏条目会被跳过。

---

## 🔄 发布流程

`.github/workflows/build.yml` 三个 job：

1. **windows** —— PyInstaller 打包 → 启动自检（`WorldBox.exe --smoke`）→ 上传 zip。
2. **linux** —— Briefcase 打包 → 上传 AppImage。
3. **release** —— 汇总产物、计算 SHA-256、生成发布说明并发布。

发布策略：

- 推送到 `main` → **覆盖**固定的 `latest` 发布（先清理旧资产，再更新说明与产物）。
- 手动发版 → 在 Actions 页面填入版本号，或：
  ```bash
  gh workflow run build.yml -f version=1.0.0
  ```
  会同步 `pyproject.toml` 版本号并创建 `v1.0.0` 发布，不影响 `latest`。

发布说明按统一模板生成，包含提交信息、构建详情（版本号 / 提交哈希 / 构建时间）、SHA-256 校验哈希。

---

## ❓ 常见问题

**Q：界面中文显示成方块或乱码？**
缺少中文字体。把任意中文字体（例如 SIL OFL 授权的 Noto Sans CJK）放到 `assets/fonts/`，或在 CI 构建时自动下载；文件名支持 `.ttc` / `.otf` / `.ttf`。

**Q：方块看起来是彩色噪点，不是纹理？**
默认不附带任何纹理，方块用 `blocks.json` 里的颜色生成噪点材质。到 **ESC → 资源包** 下载一个资源包即可。

**Q：Windows 上传完 zip 后运行exe 提示缺少文件？**
请分发整个 `WorldBox/` 目录，运行时依赖在 `_internal/` 里。

**Q：AppImage 双击没反应？**
需要 FUSE（`libfuse2`）；无 FUSE 时用 `./WorldBox-x.y.z-x86_64.AppImage --appimage-extract-and-run`。

**Q：想让世界更大 / 加新方块？**
世界尺寸在 `world/config.py` 的 `WORLD_SIZE`，新方块加到 `config/blocks.json`（`id` / `name` / `color`）即可，背包与快捷栏会自动收录。

---

## 🤝 参与贡献

1. Fork 仓库并新建分支：`git checkout -b feature/your-feature`
2. 本地跑通：`pip install -r requirements.txt && python app.py`
3. 提交前确保改动在 Windows 与 Linux 上都能启动
4. 推送并发起 Pull Request，CI 会自动构建两个平台的产物

代码风格保持与现有模块一致：中文注释、类型提示、模块顶部 docstring。

---

## 📄 许可与致谢

- **代码**：Apache License 2.0，见 [LICENSE](LICENSE)。
- **字体**：CI 使用 SIL Open Font License 1.1 的 Noto Sans CJK，许可文本随产物分发（`assets/fonts/OFL.txt`）。
- **Minecraft 纹理**：仅在运行时由用户自行从 `assets.mcasset.cloud` 下载，**不随本仓库分发**，版权归 Mojang Studios / Microsoft 所有。

<div align="center">
  <sub>用 Python + Ursina + Panda3D 造的小世界 🚀</sub>
</div>
