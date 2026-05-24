# Documentation

This folder holds the docs that go deeper than the [README](../README.md). Skim this index first; each doc says what it's for and when to update it.

## What's here

| Doc | Audience | Update cadence | Update when… |
|---|---|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Everyone | Per release | A version is cut. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The release routine in [`.github/release.md`](../.github/release.md) prepends entries automatically; manual edits to the `[Unreleased]` section are fine in between. |
| [`architecture.md`](architecture.md) | Maintainers / Claude | With the code | A module moves, an import changes, a file is added or retired, a dependency cluster rearranges. The line counts and module list at the bottom are the load-bearing part — keep them honest. |
| [`flows.md`](flows.md) | Maintainers / Claude | With the code | A documented function is renamed/moved, a flow's UI trigger changes (menu, button, shortcut), or a step is added/removed in a flow's call chain. The `file:line` refs are best-effort and drift; the function names + paths + step ordering are what matters. |
| [`database-changelog.md`](database-changelog.md) | Maintainers / Claude | On every DB edit | A buff is added, renamed, reclassified, or has its spell ID corrected in `Database.json`. One dated bullet per change (buff name + spell ID + action); applies however the edit was made. |

## What used to be here, and where it went

- `requirements.txt` → **deleted.** Deps live in [`pyproject.toml`](../pyproject.toml). Run `pip install -e ".[dev]"` or `uv sync --extra dev`.
- `architecture-notes.md` → **deleted.** It was a 2026-04-25 audit-cycle artifact whose three findings were all marked resolved (refactored in code, status notes added to flows.md). Historical clutter. The convention it surfaced — *"name dispatchers explicitly across boundaries"* — lives in [`flows.md`](flows.md)'s preamble.

## Documents elsewhere in the repo

| Doc | Audience | Purpose |
|---|---|---|
| [`README.md`](../README.md) | Users + new contributors | First impression, install, quick start, build-from-source |
| [`PRODUCT.md`](../PRODUCT.md) | Maintainers | Brand brief: register, users, voice, anti-references, design principles. Read before changing user-facing copy or product direction. |
| [`DESIGN.md`](../DESIGN.md) | Maintainers | Visual system: tokens, colors, typography, components, do's and don'ts. Read before changing visible UI. |
| [`DESIGN.json`](../DESIGN.json) | Tooling | Machine-readable companion to DESIGN.md (color tonal ramps, role classifications). Useful for design-system tooling, theme generation, or audit scripts. |
| [`CLAUDE.md`](../CLAUDE.md) | Claude Code | Working agreement: code-quality rules, architecture context, key files, style. Updated when conventions change. |
| [`.github/release.md`](../.github/release.md) | Claude Code | Release routine. Run via "prepare a release". Updated when the release workflow or version-source moves. |
| [`.github/release-notes.md`](../.github/release-notes.md) | End users (rendered in GitHub Releases) | Evergreen install/highlights body + per-release "What's New" preamble prepended by the release routine. |

## Doc strategy

Three audiences, kept distinct:

1. **Users** (download the .exe) — get [`README.md`](../README.md) and the GitHub Releases page. Nothing else should leak to them.
2. **Contributors** (clone and hack) — get the README's "Building from source" section, [`PRODUCT.md`](../PRODUCT.md), [`DESIGN.md`](../DESIGN.md), and the `docs/` folder.
3. **Claude / tooling** — gets [`CLAUDE.md`](../CLAUDE.md), [`.github/release.md`](../.github/release.md), and `.claude/commands/`.

Every doc opens with one line stating its purpose and refresh trigger. If you can't write that line, the doc probably shouldn't exist as its own file.
