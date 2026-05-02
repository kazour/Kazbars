# KazBars — Release Routine

Instructions for Claude Code. Run this routine when Kaz says "prepare a release" or "ship v1.x".

---

## Prerequisites (verify once, then never again)

Before this routine can work, these must be true. Check them on first run; if any fails, fix it and commit **before** starting a release.

1. **`.github/workflows/release.yml` matches the fixed version** shipped alongside this doc. Key requirements:
   - `workflow_dispatch:` trigger present (for manual test runs)
   - `fetch-depth: 0` on checkout (for full history)
   - `cache: 'pip'` on setup-python
   - `if: startsWith(github.ref, 'refs/tags/')` guard on the gh-release step so manual dispatches don't create releases
2. **`.github/release-notes.md` exists** and holds evergreen install/highlights content. The workflow reads release notes from this file. The routine below **prepends** a "What's New" section each release — the evergreen body stays intact. If the file doesn't exist, bootstrap it with Highlights / Install / Requirements content before running the routine.
3. **`docs/CHANGELOG.md` exists.** The routine prepends to it. If missing, create with a single header line.

---

## Rules for the routine

1. **Stop and wait at every approval gate.** The gates exist because release mistakes are hard to undo.
2. **Never force-push.** Never delete a remote tag. If something goes wrong after the tag is pushed, create a new version.
3. **One command per step.** Do not chain git operations. Kaz needs to see each outcome.
4. **If a check fails, stop and report.** Do not try alternative approaches.

---

## Step 0 — Pre-flight checks

Run all of these before touching anything. If any fails, report and stop.

```bash
# Clean working tree
git status --porcelain
# Expected: empty output

# On main
git branch --show-current
# Expected: main

# Synced with origin
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
# Expected: identical SHAs

# Workflow file exists and is syntactically valid
test -f .github/workflows/release.yml && echo OK
# Expected: OK
# Optional parse: python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"

# Release notes stub exists
test -f .github/release-notes.md && echo OK
# Expected: OK
```

If anything is off, print what failed and stop. Do not attempt to fix pre-flight issues silently.

---

## Step 1 — Determine the version bump

Read the current version from `src/kazbars/__init__.py` (single source of truth — `pyproject.toml`'s hatchling reads from here):

```bash
grep -E '^__version__\s*=' src/kazbars/__init__.py
# Expect one line like: __version__ = "2.0.0"
```

Get commits since the last tag:

```bash
git describe --tags --abbrev=0 2>/dev/null || echo "NO_PREVIOUS_TAG"
# Capture output as $PREV_TAG

git log --pretty=format:'%s' $PREV_TAG..HEAD
# Or if no previous tag: git log --pretty=format:'%s'
```

Classify each commit subject by its prefix:

| Prefix | Bucket | Bump signal |
|---|---|---|
| `Feature:` / `Feat:` | Added | minor |
| `Fix:` / `Bugfix:` | Fixed | patch |
| `Refactor:` | Changed | **minor** (semantics may shift) |
| `Polish:` / `Chore:` / `Docs:` | Changed | patch |
| `Validate:` | Fixed | patch |
| `BREAKING:` anywhere in subject or body | Changed | **major** |
| Anything else | Changed | patch (safe default) |

**Version bump rule:** use the highest signal across all commits.

Report the proposed bump to Kaz in this shape:

```
Current: v1.0.0
Commits since v1.0.0: 6
  Fix: save database changes on close, not just profile
  Validate: block build when enabled grids have no tracked buffs
  Refactor: grids reference buffs by primary spell ID
  Polish: mode button label, ID-input validation, GitHub link, copy fixes
  Feature: non-modal GitHub release check on launch
  Feature: File > Uninstall from game client

Proposed: v1.1.0 (minor — new features + refactor)

Approve? (y/n, or type a different version like 1.2.0)
```

**APPROVAL GATE #1.** Do not proceed until Kaz approves explicitly.

---

## Step 2 — Draft release notes and changelog

Write `/mnt/user-data/outputs/CHANGELOG_DRAFT.md` grouping the commits:

```markdown
## v1.1.0 — <YYYY-MM-DD>

### Added
- Background check for new releases on launch. Click the toast to open release notes.
- File → Uninstall from game client. Cleanly removes KazBars files from the selected install.

### Changed
- Grids now reference buffs by spell ID instead of name. Renaming a buff in the database no longer breaks grids that use it. Existing profiles migrate automatically on load; any buffs that can't be resolved are listed in a dialog so you can re-add them.
- Mode button on each grid card reads "Slot Assignments..." when the grid is in static mode.
- About dialog now links to the GitHub repo.

### Fixed
- Database changes are now saved when you close the app and click "Yes" on the unsaved-changes prompt. Previously only the profile was saved.
- Build now refuses to run if an enabled grid has no tracked buffs, instead of installing a silent grid.
- Invalid entries in the Add Buff ID field show a warning before saving instead of being dropped silently.
- Welcome popup no longer references a non-existent "Edit → Clear All Grids" menu path.

---
```

**Translation rule:** commit messages are for developers; release notes are for users. Do not paste commit subjects verbatim — rewrite each into something a non-technical user can act on. Preserve every bullet that mentions user-visible behavior. Drop bullets that are purely internal (none apply this release, but this rule stands for future ones).

**APPROVAL GATE #2.** Present the draft to Kaz. Wait for edits or approval. Do not proceed.

Once approved, the routine must also **prepend** the approved notes to `.github/release-notes.md` as a `## What's New in vX.Y.Z` section, followed by a `---` separator, then the existing Highlights / Install / Requirements body. Do not overwrite — the evergreen install content carries forward every release. The workflow uses this file as the release body. The `---` separator in `docs/CHANGELOG.md` separates versions there; in release-notes.md it separates "What's New" from the evergreen body.

---

## Step 3 — Apply version bump and commit

Update `__version__` in `src/kazbars/__init__.py`:

```bash
# Replace only the version string, nothing else
sed -i 's/^__version__ = "2.0.0"/__version__ = "2.1.0"/' src/kazbars/__init__.py
grep -E '^__version__\s*=' src/kazbars/__init__.py
# Verify
```

(One source: `pyproject.toml` reads this via hatchling's dynamic version. Don't bump anywhere else.)

Prepend the approved changelog entry to `docs/CHANGELOG.md`. Keep the existing file header (if any) at the top:

```bash
# Read existing CHANGELOG, prepend new entry after any top-level header
# Simplest approach: use a temp file
cat CHANGELOG_DRAFT.md docs/CHANGELOG.md > docs/CHANGELOG.new
mv docs/CHANGELOG.new docs/CHANGELOG.md
```

If `docs/CHANGELOG.md` has a `# Changelog` header that should stay at the top, adjust — handle this case by reading the file first and inserting the draft after line 1.

Prepend the approved notes to `.github/release-notes.md` as a `## What's New in vX.Y.Z` section followed by a `---` separator — do not touch the evergreen Highlights / Install / Requirements body below (see Step 2 above).

Stage and commit:

```bash
git add src/kazbars/__init__.py docs/CHANGELOG.md .github/release-notes.md
git status
# Confirm only these 3 files are staged. If anything else shows up, stop.

git commit -m "Release v2.1.0"
```

**APPROVAL GATE #3.** Show Kaz the commit and `git log -1 --stat` output. Wait for approval before pushing.

---

## Step 4 — Tag and push

Two pushes, in this order. Do not combine them.

```bash
# Push the release commit first so origin/main is ahead of the tag
git push origin main
```

Wait for confirmation it succeeded. Then:

```bash
# Annotated tag (annotated, not lightweight — release workflows expect this)
git tag -a v1.1.0 -m "KazBars v1.1.0"
git push origin v1.1.0
```

Report both pushes completed.

---

## Step 5 — Watch CI

Tell Kaz to open the GitHub Actions sidebar in VS Code (the GitHub Actions extension is installed — confirmed). The `Release` workflow should appear with a running indicator.

Do **not** poll the API from the routine. The Actions sidebar is faster to read and doesn't need a token.

While the build runs, prepare the post-release checklist (Step 6) so it's ready when CI finishes.

**If CI fails:**
- Report the failing step.
- Do not delete the tag. Do not retry automatically.
- The fix is a new commit + new patch-version tag (e.g., v1.1.1), not force-rewriting v1.1.0.

**If CI succeeds:**
- Confirm the release appears at `https://github.com/kazour/Kazbars/releases/tag/vX.Y.Z`.
- Confirm `KazBars.zip` and `KazBars.zip.sha256` are attached as assets.

---

## Step 6 — Post-release reminders

Print this checklist for Kaz:

```
Release v1.1.0 shipped. Don't forget:

[ ] Download the zip and sanity-check: extract, run KazBars.exe,
    confirm the version in the About dialog reads 1.1.0
[ ] Submit the exe to Microsoft Defender for reputation:
    https://www.microsoft.com/en-us/wdsi/filesubmission
    (Select "Software developer", upload the zip, takes 1-3 days)
[ ] Post in Discord with a link to the release notes
[ ] First-time check: confirm v1.0.0 users get the update toast on
    their next launch (someone in Discord will report if they don't)
```

Delete `CHANGELOG_DRAFT.md` from `/mnt/user-data/outputs/` — it's been applied to the real CHANGELOG.

---

## Invocation

When Kaz says one of:
- "prepare a release"
- "ship v1.x" / "release v1.x"
- "cut a release"

Claude Code runs this routine from Step 0. If Kaz specifies a version explicitly ("ship v1.1.0"), use that and skip the version-proposal part of Step 1 but still show the commit list for review.

---

## Things NOT in scope for the routine

- Do not touch `kazbars.spec` during a release (the spec is checked-in; changes are committed separately)
- Do not touch `release.yml` during a release (one-time fixes, committed separately)
- Do not create draft releases — this routine goes straight to published
- Do not handle pre-releases / RCs — if Kaz wants one, add that to this doc first
- Do not auto-generate changelog from commits without the approval gate. The gate exists because commit messages are internal and notes are external.

---

*End of release routine.*
