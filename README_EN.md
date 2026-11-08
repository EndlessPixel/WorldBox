<div align="center">

# WorldBox

**A small voxel sandbox written in Python with Ursina — an editable block world, resource packs, a fullscreen map and fully remappable controls.**

English · [简体中文](README.md)

[![Build](https://github.com/EndlessPixel/WorldBox/actions/workflows/build.yml/badge.svg)](https://github.com/EndlessPixel/WorldBox/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/EndlessPixel/WorldBox?label=Release)](https://github.com/EndlessPixel/WorldBox/releases/latest)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

[⬇️ Download for Windows](https://github.com/EndlessPixel/WorldBox/releases/latest) · [⬇️ Download AppImage](https://github.com/EndlessPixel/WorldBox/releases/latest)

</div>

---

## 📖 Table of Contents

- [✨ Features](#-features)
- [🕹️ Controls](#️controls)
- [🚀 Getting Started](#-getting-started)
- [📦 Build Artifacts](#-build-artifacts)
- [🧩 Project Layout](#-project-layout)
- [⚙️ Configuration](#️configuration)
- [🎨 Resource Packs](#-resource-packs)
- [💾 Saves & Data](#-saves--data)
- [🔄 Release Pipeline](#-release-pipeline)
- [❓ FAQ](#-faq)
- [🤝 Contributing](#-contributing)
- [📄 License & Credits](#-license--credits)

---

## ✨ Features

- **A real voxel world** — 128×128 m, rendered as merged 16×16 chunks with only exposed faces; digging and placing rebuilds just the affected chunks.
- **Proper player volume** — AABB collision with separate foot and head checks; you keep standing while any corner of your body still rests on a block. Horizontal motion is split into ≤0.05 m substeps, so frame hitches can no longer tunnel you through walls.
- **Sneak-safe edges** — holding `Shift` keeps you from walking off a ledge, and digging the floor from under you will not drop you either; releasing it restores gravity immediately.
- **11 block types, including slabs** — grass, dirt, stone, cobblestone, obsidian, bricks, end stone, bedrock, plus **stone / cobblestone / bricks slabs** (0.5 m tall, stackable into steps), each with configurable colour and textures.
- **Resource pack system** — describe textures in a JSON manifest, let the game download them into their own namespace at runtime; browse, download and switch packs from inside the game.
- **Fullscreen map (`M`)** — a 128×128 colour-block top-down view drawn from block colours, with a red marker for the player.
- **Inventory & hotbar** — a 3×9 inventory plus a 9-slot hotbar: left click picks up or swaps, right click copies or replaces, hovering shows the name, ID and colour of an item.
- **Remappable controls** — all 12 actions can be rebound; conflicts swap automatically and the layout persists to `config/keys.json`.
- **Settings panel** — language, resource pack, auto-jump and its height, view distance, FOV, view bob and brightness — all applied instantly.
- **Bilingual UI** — full i18n with a runtime language switch.
- **Day/night & culling** — a 180-second day cycle, distance culling and a subtle view bob while moving.
- **Cross-platform input** — physical polling through X11 on Linux and Win32 on Windows, sidestepping the dropped key events of the Ursina event layer.

---

## 🕹️ Controls

| Key | Action | Key | Action |
| --- | --- | --- | --- |
| `W` `A` `S` `D` | Move | `Ctrl` | Sprint |
| `Space` | Jump | `Shift` | Crouch / sneak (edge-safe) |
| `C` | Zoom | `M` | Fullscreen map |
| Left click | Dig block | Right click | Place block |
| Middle click | Pick block to hotbar | Wheel | Cycle hotbar |
| `1` ~ `9` | Select hotbar slot | `E` | Toggle inventory |
| `ESC` | Pause menu / back | `F5` | Save immediately |

> Every key can be reassigned in **ESC → Key Bindings**.

---

## 🚀 Getting Started

### Run from source

```bash
git clone https://github.com/EndlessPixel/WorldBox.git
cd WorldBox

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

Requires Python 3.12+, an X11 session on Linux/macOS or a desktop session on Windows.

### Just download it

Grab a build from [Releases](https://github.com/EndlessPixel/WorldBox/releases/latest):

| Platform | File | Notes |
| --- | --- | --- |
| Windows | `WorldBox-<version>-windows-x86_64.zip` | Unzip and run `WorldBox.exe`; keep the whole folder |
| Linux | `WorldBox-<version>-linux-x86_64.AppImage` | `chmod +x` and run; requires FUSE (or `--appimage-extract-and-run`) |

---

## 📦 Build Artifacts

Two packagers, each covering one platform, and CI builds both:

- **PyInstaller → Windows `.exe`** — `build_exe.py` bundles the Ursina/Panda3D runtime, block table, resource pack manifests and the CJK font into a single-folder exe, plus a distributable zip.
- **Briefcase → Linux `.AppImage`** — `build_appimage.py` builds an AppDir with Briefcase and wraps it into a single-file AppImage via linuxdeploy.

```bash
# Windows (can only be built on Windows)
pip install -r requirements-build.txt
python build_exe.py                 # dist/WorldBox/ and dist/WorldBox-<version>-windows-x86_64.zip

# Linux
pip install -r requirements-build.txt
python build_appimage.py             # dist/WorldBox-<version>-linux-x86_64.AppImage
```

The build scripts also prepare the Briefcase source tree, render an application icon and patch the missing `host_arch` variable into the upstream AppImage template.

---

## 🧩 Project Layout

```
WorldBox/
├── app.py                  # Entry point: window + Game bootstrap
├── world/                  # Game modules
│   ├── game.py             # Orchestration: input, digging/placing, day cycle, saving
│   ├── player.py           # Movement, jumping, AABB collision, sneaking
│   ├── voxel.py            # Voxel data, chunk meshes, DDA raycast
│   ├── blocks.py           # Block table (reads config/blocks.json)
│   ├── materials.py        # Texture atlas and isometric 3D item icons
│   ├── mapview.py          # Fullscreen map (vertex-coloured blocks)
│   ├── ui.py               # HUD / inventory / menus / settings / packs / keybinds
│   ├── keybinds.py         # Key bindings and translation
│   ├── inputs.py           # X11 / Win32 physical input polling
│   ├── i18n.py             # Chinese & English strings
│   ├── packs.py            # Resource pack discovery and downloads
│   ├── storage.py          # Save file IO (atomic replace)
│   └── config.py           # Constants and setting.json handling
├── config/
│   ├── blocks.json         # Block definitions (id / name / color)
│   └── resource_packs/     # Resource pack manifests
├── assets/                 # Runtime assets (textures, fonts; not in git)
├── build_exe.py            # PyInstaller packaging
├── build_appimage.py       # Briefcase packaging
├── make_release_notes.py   # Release notes generator
└── .github/workflows/      # CI: build + release
```

---

## ⚙️ Configuration

### Settings

`config/setting.json` (created on first run):

| Key | Description | Default |
| --- | --- | --- |
| `language` | UI language `zh` / `en` | `zh` |
| `resource_pack` | Resource pack id, empty for the built-in one | `""` |
| `auto_jump` | Automatically jump up 1-block steps | `true` |
| `auto_jump_height` | Maximum height auto-jump can clear | `1.0` |
| `view_distance` | Chunk visibility distance (metres) | `96` |
| `fov` | Field of view | `40` |
| `view_bob` | View bob amplitude while moving | `0.03` |
| `brightness` | Screen brightness | `1.0` |

Everything is editable in-game under **ESC → Settings**; changes take effect immediately and are written back atomically.

### Key bindings

`config/keys.json` maps 12 actions to physical key names:

```json
{
  "forward": "w", "back": "s", "left": "a", "right": "d",
  "jump": "space", "crouch": "shift", "sprint": "ctrl",
  "zoom": "c", "inventory": "e", "menu": "escape",
  "save": "f5", "map": "m"
}
```

Use ↑↓ to pick an action, press Enter and then any key to rebind it, `R` to restore defaults. Rebinding an already used key swaps the two actions. The engine always evaluates the canonical key names internally, so custom bindings never break other logic.

---

## 🎨 Resource Packs

A resource pack is a `cdn-assets.json` manifest: an `id` naming the namespace, plus `URL -> relative path` mappings.

```json
{
  "id": "minecraft",
  "https://assets.mcasset.cloud/26.3/assets/minecraft/textures/block/stone.png": "assets/worldbox/blocks/stone.png"
}
```

- Download targets are rewritten to `assets/<id>/blocks/`, so packs never overwrite each other.
- Any manifest dropped into `config/resource_packs/` shows up automatically in the in-game **Resource Packs** page.
- On that page: ↑↓ to select, **Enter** to apply, **R** to download, **ESC** to go back. Applying rebuilds the texture atlas, all chunk meshes and every item icon without a restart.
- Blocks without an explicit mapping fall back to a same-named texture derived from their ID (e.g. `worldbox:obsidian.block` → `obsidian.png`).

---

## 💾 Saves & Data

| Data | Windows | Linux AppImage |
| --- | --- | --- |
| Save `world_save.json` | Next to the exe | `~/.local/share/WorldBox/` |
| Settings `config/setting.json` | Next to the exe | `~/.local/share/WorldBox/` |
| Key bindings `config/keys.json` | Next to the exe | `~/.local/share/WorldBox/` |
| Resource pack textures | `assets/<id>/` | `~/.local/share/WorldBox/assets/<id>/` |

Saves are written to a temporary file and atomically replaced; only blocks the player actually changed are stored, and corrupt entries are skipped on load.

---

## 🔄 Release Pipeline

`.github/workflows/build.yml` runs three jobs:

1. **windows** — PyInstaller build → startup self-check (`WorldBox.exe --smoke`) → upload zip.
2. **linux** — Briefcase build → upload AppImage.
3. **release** — collect artifacts, compute SHA-256 checksums, render the release notes and publish.

Release strategy:

- Pushing to `main` **overwrites** the rolling `latest` release (old assets are removed, notes and artifacts refreshed).
- For a versioned release, type a version into the Actions page or run:
  ```bash
  gh workflow run build.yml -f version=1.0.0
  ```
  which syncs the version in `pyproject.toml` and creates a `v1.0.0` release without touching `latest`.

Release notes follow a fixed template: commit message, build details (version, commit hash, build time), SHA-256 verification hashes.

---

## ❓ FAQ

**Q: The Chinese UI shows boxes or garbage.**
The CJK font is missing. Drop any Chinese font (e.g. the SIL OFL licensed Noto Sans CJK) into `assets/fonts/`, or let the CI download it; `.ttc`, `.otf` and `.ttf` are all supported.

**Q: Blocks look like coloured noise instead of textures.**
No textures ship with the game; blocks fall back to a noise material generated from the colour in `blocks.json`. Open **ESC → Resource Packs** to download a pack.

**Q: The Windows build complains about missing files.**
Distribute the whole `WorldBox/` folder — the runtime lives in `_internal/`.

**Q: The AppImage does nothing when double-clicked.**
It needs FUSE (`libfuse2`); without it run `./WorldBox-x.y.z-x86_64.AppImage --appimage-extract-and-run`.

**Q: How do I enlarge the world or add blocks?**
World size lives in `world/config.py` as `WORLD_SIZE`; new blocks only need `id` / `name` / `color` in `config/blocks.json` and they show up in the inventory and hotbar automatically.

---

## 🤝 Contributing

1. Fork the repository and create a branch: `git checkout -b feature/your-feature`
2. Get it running locally: `pip install -r requirements.txt && python app.py`
3. Make sure your change still starts on both Windows and Linux
4. Push and open a pull request — CI builds both platform artifacts automatically

Match the existing style: Chinese docstrings, type hints, and a module-level docstring explaining the module's responsibility.

---

## 📄 License & Credits

- **Code** — Apache License 2.0, see [LICENSE](LICENSE).
- **Font** — CI fetches Noto Sans CJK under the SIL Open Font License 1.1; the licence text ships with the artifacts (`assets/fonts/OFL.txt`).
- **Minecraft textures** — downloaded at runtime by the user from `assets.mcasset.cloud`; they are **not redistributed in this repository** and remain the property of Mojang Studios / Microsoft.

<div align="center">
  <sub>A tiny world built with Python + Ursina + Panda3D 🚀</sub>
</div>
