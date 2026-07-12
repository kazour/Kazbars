# Documentation

This folder holds the docs that go deeper than the [README](../README.md). Skim this index first; each doc says what it's for and when to update it.

## What's here

| Doc | Audience | Update cadence | Update when… |
|---|---|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Everyone | Per release | A version is cut. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are prepended at release time; manual edits to the `[Unreleased]` section are fine in between. |
| [`architecture.md`](architecture.md) | Maintainers | With the code | A module moves, an import changes, a file is added or retired, a dependency cluster rearranges. The line counts and module list at the bottom are the load-bearing part — keep them honest. |
| [`flows.md`](flows.md) | Maintainers | With the code | A documented function is renamed/moved, a flow's UI trigger changes (menu, button, shortcut), or a step is added/removed in a flow's call chain. Refs are function-anchored (a backticked `callable()` + its file path, never `file:line`) and machine-checked by `tests/test_docs_in_sync.py`; the function names, paths, and step ordering are load-bearing. |
| [`database-changelog.md`](database-changelog.md) | Maintainers | On every DB edit | A buff is added, renamed, reclassified, or has its spell ID corrected in `Database.json`. One dated bullet per change (buff name + spell ID + action); applies however the edit was made. |

## What used to be here, and where it went

- `requirements.txt` → **deleted.** Deps live in [`pyproject.toml`](../pyproject.toml). Run `pip install -e ".[dev]"` or `uv sync --extra dev`.
- `architecture-notes.md` → **deleted.** It was a 2026-04-25 audit-cycle artifact whose three findings were all marked resolved (refactored in code, status notes added to flows.md). Historical clutter. The convention it surfaced — *"name dispatchers explicitly across boundaries"* — lives in [`flows.md`](flows.md)'s preamble.

## Documents elsewhere in the repo

| Doc | Audience | Purpose |
|---|---|---|
| [`README.md`](../README.md) | Users + new contributors | First impression, install, quick start, build-from-source |
| [`.github/release-notes.md`](../.github/release-notes.md) | End users (rendered in GitHub Releases) | Evergreen install/highlights body + per-release "What's New" preamble prepended at release time. |

## Doc strategy

Two audiences, kept distinct:

1. **Users** (download the .exe) — get [`README.md`](../README.md) and the GitHub Releases page. Nothing else should leak to them.
2. **Contributors** (clone and hack) — get the README's "Building from source" section and the `docs/` folder.

Every doc opens with one line stating its purpose and refresh trigger. If you can't write that line, the doc probably shouldn't exist as its own file.
