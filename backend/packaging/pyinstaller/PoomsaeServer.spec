# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller executes spec files without guaranteeing __file__.
# Prefer current working directory (Makefile runs from project root),
# with a fallback based on SPECPATH.
PROJECT_ROOT = Path.cwd().resolve()
if not (PROJECT_ROOT / "src" / "tkd_scorer").exists():
    spec_dir = Path(globals().get("SPECPATH", ".")).resolve()
    PROJECT_ROOT = spec_dir.parents[1]
SRC_DIR = PROJECT_ROOT / "src"

block_cipher = None

entry_script = SRC_DIR / "tkd_scorer" / "entry_points" / "runtime_server.py"

# Bundle package resources needed by the FastAPI admin frontend
# (templates, static assets and UI translation catalogs).
datas = collect_data_files(
    "tkd_scorer",
    includes=[
        "infra/templates/**/*.html",
        "infra/static/**/*",
        "infra/i18n/locales/*.json",
    ],
)

hiddenimports = []
hiddenimports += collect_submodules("tkd_scorer")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("passlib.handlers")


a = Analysis(
    [str(entry_script)],
    pathex=[str(PROJECT_ROOT), str(SRC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PoomsaeServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PoomsaeServer",
)
