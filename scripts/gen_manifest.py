#!/usr/bin/env python3
"""Generate ota/manifest.json and stamp CONTENT_BASELINE_VERSION.

Repo tooling — NOT shipped. Run by .github/workflows/ota-manifest.yml on a
push-to-main that touches the stock buff files (or manually:
``python scripts/gen_manifest.py "release notes"``).

It reads the two shipped stock files, computes their sha256, pins each payload
URL to the current commit SHA (so a payload can't shift under a published
manifest), bumps ``content_version`` only when the content actually changed,
fills ``min_app_version`` from ``__version__``, writes ``ota/manifest.json``, and
stamps the same version into ``src/kazbars/__init__.py`` as
``CONTENT_BASELINE_VERSION``. ``tests/test_manifest.py`` guards that the two stay
in lockstep and that the manifest sha256 matches the committed stock files.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STOCK = REPO / "src" / "kazbars" / "assets" / "kazbars"
INIT = REPO / "src" / "kazbars" / "__init__.py"
MANIFEST = REPO / "ota" / "manifest.json"
FILES = ("Database.json", "Default.json")
RAW_URL = "https://raw.githubusercontent.com/kazour/Kazbars/{sha}/src/kazbars/assets/kazbars/{name}"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _app_version():
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', INIT.read_text(encoding="utf-8"))
    return m.group(1) if m else "0.0.0"


def _git_head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()


def _stamp_baseline(version):
    text = INIT.read_text(encoding="utf-8")
    new, n = re.subn(r"(CONTENT_BASELINE_VERSION\s*=\s*)\d+", rf"\g<1>{version}", text, count=1)
    if n != 1:
        raise SystemExit("CONTENT_BASELINE_VERSION assignment not found in __init__.py")
    INIT.write_text(new, encoding="utf-8")


def main(notes=""):
    shas = {name: _sha256(STOCK / name) for name in FILES}
    existing = _read_json(MANIFEST)
    if existing is None:
        version = 1
    elif all(existing.get("files", {}).get(n, {}).get("sha256") == shas[n] for n in FILES):
        version = existing["content_version"]          # no content change — keep version
    else:
        version = int(existing["content_version"]) + 1  # content moved — bump
    sha = _git_head()
    manifest = {
        "schema": 1,
        "content_version": version,
        "min_app_version": _app_version(),
        "source_commit": sha,
        "notes": notes,
        "files": {
            name: {"url": RAW_URL.format(sha=sha, name=name), "sha256": shas[name]}
            for name in FILES
        },
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _stamp_baseline(version)
    print(
        f"Wrote {MANIFEST.relative_to(REPO).as_posix()} "
        f"content_version={version} (min_app {manifest['min_app_version']}, commit {sha[:8]})"
    )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
