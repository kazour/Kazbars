#!/usr/bin/env python3
"""Cut a release from docs/CHANGELOG.md's [Unreleased] section.

Repo tooling — NOT shipped. The release train (.github/workflows/release-train.yml)
runs it unattended on ``main``; a manual release runs it by hand, usually with
``--version``. It does, in order:

  1. read the ``## [Unreleased]`` body — empty ⇒ exit 3, nothing to release;
  2. pick the bump: a ``### Added`` heading ⇒ minor, else patch. ``--version X.Y.Z``
     overrides — the only way to a major;
  3. rename the heading to ``## [X.Y.Z] — YYYY-MM-DD`` and insert a fresh, empty
     ``## [Unreleased]`` above it (the form tests/test_docs_in_sync.py expects);
  4. bump ``__version__`` in src/kazbars/__init__.py (the single source — pyproject
     reads it through hatchling);
  5. replace everything above the first ``---`` in .github/release-notes.md with a
     ``## What's New in vX.Y.Z`` block: a one-line lead plus the [Unreleased] body
     verbatim. CHANGELOG entries are written for players, so they ship as-is; a
     manual release polishes the block before pushing.

``--dry-run`` prints the plan and writes nothing. Exit codes: 0 cut, 3 nothing to
do, 1 error. Never touches git — the caller commits, tags and pushes.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHANGELOG = REPO / "docs" / "CHANGELOG.md"
INIT = REPO / "src" / "kazbars" / "__init__.py"
NOTES = REPO / ".github" / "release-notes.md"

UNRELEASED = "## [Unreleased]"
NOTHING_TO_DO = 3
_VERSION_LINE = re.compile(r'^__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"', re.M)


def unreleased_body(text):
    """The text between ``## [Unreleased]`` and the next ``## `` heading, stripped."""
    start = text.find(UNRELEASED)
    if start < 0:
        raise SystemExit("docs/CHANGELOG.md has no ## [Unreleased] section")
    rest = text[start + len(UNRELEASED):]
    nxt = re.search(r"^## ", rest, re.M)
    return (rest[:nxt.start()] if nxt else rest).strip()


def current_version(init_text):
    m = _VERSION_LINE.search(init_text)
    if not m:
        raise SystemExit("__version__ not found in src/kazbars/__init__.py")
    return tuple(int(x) for x in m.groups())


def next_version(current, body):
    """(version, reason): minor when the body carries a ### Added heading, else patch."""
    major, minor, patch = current
    if re.search(r"^### Added\b", body, re.M):
        return (major, minor + 1, 0), "minor — ### Added present"
    return (major, minor, patch + 1), "patch"


def lead_line(body):
    """`A small update: 2 fixed, 1 changed.` from the bullet counts per section."""
    counts = []
    section = None
    for line in body.splitlines():
        head = re.match(r"^### (\w+)", line)
        if head:
            section = head.group(1).lower()
            counts.append([section, 0])
        elif line.startswith("- ") and counts:
            counts[-1][1] += 1
    parts = [f"{n} {name}" for name, n in counts if n]
    return f"A small update: {', '.join(parts)}." if parts else "A small update."


def whats_new(version, body):
    return f"## What's New in v{version}\n\n{lead_line(body)}\n\n{body}\n"


def cut(version, date, *, dry_run=False):
    """Apply the three edits (or, dry-run, return them). Returns the What's New block."""
    changelog = CHANGELOG.read_text(encoding="utf-8")
    init = INIT.read_text(encoding="utf-8")
    notes = NOTES.read_text(encoding="utf-8")

    body = unreleased_body(changelog)
    block = whats_new(version, body)
    divider = notes.find("\n---\n")
    if divider < 0:
        raise SystemExit(".github/release-notes.md has no --- divider above the evergreen body")

    if not dry_run:
        CHANGELOG.write_text(
            changelog.replace(UNRELEASED, f"{UNRELEASED}\n\n## [{version}] — {date}", 1),
            encoding="utf-8")
        INIT.write_text(_VERSION_LINE.sub(f'__version__ = "{version}"', init, count=1),
                        encoding="utf-8")
        NOTES.write_text(block + notes[divider:], encoding="utf-8")
    return block


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cut a release from docs/CHANGELOG.md [Unreleased].")
    ap.add_argument("--version", metavar="X.Y.Z", help="force this version (the only way to a major)")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        # The What's New block carries ▸, — and friends; a cp1252 console (the
        # Windows default) would otherwise crash the final print — after the
        # files were already written.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    body = unreleased_body(CHANGELOG.read_text(encoding="utf-8"))
    if not body:
        print("Nothing to release: docs/CHANGELOG.md [Unreleased] is empty.")
        return NOTHING_TO_DO
    current = current_version(INIT.read_text(encoding="utf-8"))
    if args.version:
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", args.version)
        if not m:
            raise SystemExit(f"--version must be X.Y.Z, got {args.version!r}")
        target, reason = tuple(int(x) for x in m.groups()), "forced"
        if target <= current:
            raise SystemExit(f"--version {args.version} is not above the current "
                             f"{'.'.join(map(str, current))}")
    else:
        target, reason = next_version(current, body)
    version = ".".join(map(str, target))

    block = cut(version, args.date, dry_run=args.dry_run)
    print(f"{'Would cut' if args.dry_run else 'Cut'} v{version} ({reason}) from "
          f"v{'.'.join(map(str, current))}, dated {args.date}\n")
    print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
