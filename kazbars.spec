# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH)
ASSETS = ROOT / "src" / "kazbars" / "assets"

a = Analysis(
    ["src/kazbars/__main__.py"],
    pathex=["src"],
    binaries=[],
    # Bundle assets INSIDE the kazbars package so frozen runs use the same
    # `Path(__file__).parent / "assets"` resolution as dev runs. PyInstaller
    # 6.x puts datas under `_internal/`, so a destination of `kazbars/assets/X`
    # ends up at `<exe>/_internal/kazbars/assets/X` — mirroring `src/kazbars/assets/X`.
    datas=[
        (str(ASSETS / "kazbars"), "kazbars/assets/kazbars"),
        (str(ASSETS / "compiler"), "kazbars/assets/compiler"),
        (str(ASSETS / "common_stubs"), "kazbars/assets/common_stubs"),
        # Deeps cluster: bundled pet-name registry consumed lazily by
        # `kazbars.deeps_parsers._pet_names()` on first call.
        (str(ASSETS / "deeps"), "kazbars/assets/deeps"),
        # Damage Numbers: the pristine game SWF + the lean AS2 source tree the
        # generator bakes + MTASC-injects on each build (see damageinfo_generator).
        (str(ASSETS / "damageinfo"), "kazbars/assets/damageinfo"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Strip dev-only files. PyInstaller normalizes destinations to OS-native
# separators, so check both forms.
_DEV_ONLY = {
    "kazbars/assets/compiler/changes.txt",
    "kazbars/assets/compiler/future.txt",
    "kazbars/assets/compiler/readme.txt",
    "kazbars/assets/kazbars/base.fla",
}
DEV_ONLY = _DEV_ONLY | {p.replace("/", "\\") for p in _DEV_ONLY}
a.datas = [d for d in a.datas if d[0] not in DEV_ONLY]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KazBars",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KazBars",
)
