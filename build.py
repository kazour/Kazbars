"""
Kaz Grids Build Script
Compiles the application to an executable and bundles it with assets into a zip file.

Usage:
    python build.py
"""

import subprocess
import shutil
import sys
from pathlib import Path
from datetime import datetime

# Configuration
APP_NAME = "Kaz Grids"
MAIN_SCRIPT = "kzgrids.py"
VERSION = "1.1.0"

# Directories
ROOT_DIR = Path(__file__).parent
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
BUNDLE_DIR = DIST_DIR / APP_NAME
ASSETS_DIR = ROOT_DIR / "assets"

# Asset folders to include in bundle
ASSETS_TO_COPY = [
    "compiler",
    "common_stubs",
    "kzgrids",
]

# Files/folders to strip from the distribution bundle (dev-only artifacts)
BUNDLE_EXCLUDES = [
    "compiler/changes.txt",
    "compiler/future.txt",
    "compiler/readme.txt",
    "kzgrids/base.fla",
]

# Folders to create (empty)
FOLDERS_TO_CREATE = [
    "settings",
    "profiles",
]


def clean_build():
    """Remove previous build artifacts."""
    print("Cleaning previous build...")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    spec_file = ROOT_DIR / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()

    zip_file = ROOT_DIR / f"{APP_NAME}.zip"
    if zip_file.exists():
        zip_file.unlink()

    print("  Done.")


def build_executable():
    """Build the executable using PyInstaller."""
    print("Building executable with PyInstaller...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--name", APP_NAME,
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--specpath", str(ROOT_DIR),
        "--hidden-import", "Modules",
        "--hidden-import", "Modules.database_editor",
        "--hidden-import", "Modules.build_utils",
        "--hidden-import", "Modules.grids_panel",
        "--hidden-import", "Modules.grids_generator",
        "--hidden-import", "Modules.build_loading",
        "--hidden-import", "Modules.boss_timer",
        "--hidden-import", "Modules.timer_overlay",
        "--hidden-import", "Modules.combat_monitor",
        "--hidden-import", "Modules.live_tracker_panel",
        "--hidden-import", "Modules.live_tracker_settings",
        "--hidden-import", "Modules.ui_helpers",
        "--hidden-import", "Modules.settings_manager",
        "--hidden-import", "Modules.window_position",
        "--hidden-import", "Modules.ui_tk_style",
        "--hidden-import", "Modules.ui_widgets",
        "--hidden-import", "Modules.grid_dialogs",
        "--hidden-import", "Modules.grid_model",
        "--hidden-import", "Modules.first_launch",
        "--hidden-import", "Modules.build_executor",
        MAIN_SCRIPT
    ]

    result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)

    if result.returncode != 0:
        print("  ERROR: PyInstaller failed!")
        print(result.stderr)
        return False

    exe_path = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print("  ERROR: Executable not created!")
        return False

    print(f"  Created: {exe_path}")
    return True


def create_bundle():
    """Create the distribution bundle with all required files."""
    print("Creating distribution bundle...")

    if not BUNDLE_DIR.exists():
        print(f"  ERROR: PyInstaller output directory not found: {BUNDLE_DIR}")
        return False
    print(f"  Found: {APP_NAME}.exe (from --onedir build)")

    # Create assets folder
    bundle_assets = BUNDLE_DIR / "assets"
    bundle_assets.mkdir(exist_ok=True)

    # Copy assets
    for asset in ASSETS_TO_COPY:
        src = ASSETS_DIR / asset
        dst = bundle_assets / asset

        if src.is_dir():
            shutil.copytree(src, dst)
            print(f"  Copied folder: assets/{asset}")
        elif src.is_file():
            shutil.copy2(src, dst)
            print(f"  Copied file: assets/{asset}")
        else:
            print(f"  WARNING: Asset not found: {asset}")

    # Strip dev-only files from bundle
    for exclude in BUNDLE_EXCLUDES:
        target = bundle_assets / Path(exclude)
        if target.is_dir():
            shutil.rmtree(target)
            print(f"  Removed (dev-only): assets/{exclude}")
        elif target.is_file():
            target.unlink()
            print(f"  Removed (dev-only): assets/{exclude}")

    # Create empty folders
    for folder in FOLDERS_TO_CREATE:
        folder_path = BUNDLE_DIR / folder
        folder_path.mkdir(exist_ok=True)
        print(f"  Created folder: {folder}")

    print("  Done.")
    return True


def create_zip():
    """Create the final zip file."""
    print("Creating zip file...")

    zip_name = f"{APP_NAME}"
    zip_path = ROOT_DIR / f"{zip_name}.zip"

    shutil.make_archive(
        str(ROOT_DIR / zip_name),
        'zip',
        DIST_DIR,
        APP_NAME
    )

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  Created: {zip_path.name} ({size_mb:.1f} MB)")

    return True


def cleanup_build_artifacts():
    """Remove intermediate build files, keep only zip."""
    print("Cleaning up build artifacts...")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    spec_file = ROOT_DIR / f"{APP_NAME}.spec"
    if spec_file.exists():
        spec_file.unlink()

    print("  Done.")


def main():
    """Main build process."""
    print("=" * 60)
    print(f"  {APP_NAME} Build Script v{VERSION}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("ERROR: PyInstaller not installed!")
        print("Run: pip install pyinstaller")
        return 1

    clean_build()
    print()

    if not build_executable():
        return 1
    print()

    if not create_bundle():
        return 1
    print()

    if not create_zip():
        return 1
    print()

    cleanup_build_artifacts()
    print()

    print("=" * 60)
    print("  BUILD COMPLETE!")
    print(f"  Output: {ROOT_DIR / f'{APP_NAME}.zip'}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
