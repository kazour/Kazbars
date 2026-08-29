"""KazBars — managed profile library (file I/O, no Tk).

The only code that reads or writes ``userdata/profiles/``. Every byte passes
`profile_document.validate_document` on the way in AND on the way out — the
single-writer contract: an unvalidated document cannot land on disk, and a
file that fails the gate (corrupt, hand-mangled, old-format) is silently
skipped by listings and left untouched on disk, never migrated or deleted.

Identity is the in-document ``id``; filenames are readable slugs of the
display name and purely cosmetic. Rename re-slugs the file but the id — and
therefore the ``active_profile`` pointer — survives even if the filesystem
half fails (listings dedupe by id, newest file wins). Deletes move to
``profiles/trash/`` (pruned to the newest 10). Session ``.bak`` snapshots
(``<slug>.json.bak``) back File ▸ Revert and the corrupt-load fallback.

Templates are instantiate-only: `ensure_nonempty` copies the first template
on the chain that passes the gate into the library under a fresh id — a
template file itself can never become a library entry.
"""

import copy
import json
import logging
import re
from pathlib import Path

from .grid_model import apply_seed_sizes
from .profile_document import (
    DocumentError,
    SectionRegistry,
    mint_id,
    new_document,
    validate_document,
)
from .settings_manager import safe_save_json

logger = logging.getLogger(__name__)

TRASH_KEEP = 10
SEED_NAME = 'My Setup'

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slugify(name: str) -> str:
    """A Windows-safe filename stem from a display name. Keeps case and spaces
    (tool-honest, browsable in Explorer); strips illegal chars and trailing
    dots/spaces; never empty."""
    slug = _ILLEGAL_FILENAME_CHARS.sub('', str(name))
    slug = ' '.join(slug.split()).rstrip('. ')
    return slug or 'Profile'


class ProfileLibrary:
    """CRUD over one profiles directory. Pure file layer — no Tk, no app."""

    def __init__(
        self,
        profiles_dir: str | Path,
        registry: SectionRegistry,
        template_paths: tuple[Path, ...] = (),
    ) -> None:
        self.profiles_dir = Path(profiles_dir)
        self.trash_dir = self.profiles_dir / 'trash'
        self.registry = registry
        self.template_paths = tuple(Path(p) for p in template_paths)

    # ------------------------------------------------------------------ #
    # READING
    # ------------------------------------------------------------------ #

    def _read_doc(self, path: Path) -> dict | None:
        """One file through the gate, or None (corrupt/old/foreign → skip)."""
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            logger.debug('Skipping unreadable profile %s: %s', path.name, e)
            return None
        try:
            return validate_document(self.registry, raw)
        except DocumentError as e:
            logger.debug('Skipping non-library file %s: %s', path.name, e)
            return None

    def list_profiles(self) -> list[tuple[Path, dict]]:
        """All valid library entries, deduped by id (newest file wins — heals a
        rename whose old-file cleanup failed), sorted by display name."""
        by_id: dict[str, tuple[Path, dict]] = {}
        for path in self.profiles_dir.glob('*.json'):
            if not path.is_file():
                continue
            doc = self._read_doc(path)
            if doc is None:
                continue
            held = by_id.get(doc['id'])
            if held is None or path.stat().st_mtime > held[0].stat().st_mtime:
                by_id[doc['id']] = (path, doc)
        return sorted(by_id.values(), key=lambda e: str(e[1]['name']).casefold())

    def load(self, profile_id: str) -> tuple[Path, dict] | None:
        for path, doc in self.list_profiles():
            if doc['id'] == profile_id:
                return path, doc
        return None

    # ------------------------------------------------------------------ #
    # WRITING (the single writer)
    # ------------------------------------------------------------------ #

    def write(self, doc: dict) -> Path | None:
        """Validate and persist `doc`. An existing entry with the same id keeps
        its file; a new id gets a collision-free slug path. Returns the written
        path, or None on OSError (callers treat None as a failed autosave)."""
        validated = validate_document(self.registry, doc)
        held = self.load(validated['id'])
        path = held[0] if held else self._new_path(validated['name'])
        try:
            safe_save_json(path, validated)
            return path
        except OSError as e:
            logger.warning('Could not write profile %s: %s', path.name, e)
            return None

    def _new_path(self, name: str) -> Path:
        base = slugify(name)
        path = self.profiles_dir / f'{base}.json'
        n = 2
        while path.exists():
            path = self.profiles_dir / f'{base} ({n}).json'
            n += 1
        return path

    # ------------------------------------------------------------------ #
    # LIFECYCLE OPERATIONS
    # ------------------------------------------------------------------ #

    def create_blank(self, name: str, authored_at: tuple[int, int]) -> dict | None:
        doc = new_document(self.registry, name, authored_at)
        return doc if self.write(doc) else None

    def create_from_template(self, name: str, authored_at: tuple[int, int]) -> dict | None:
        """Instantiate the first template on the chain that passes the gate:
        fresh id, given name, the template's own authored_at (its coordinates
        were authored at that resolution). None if no template validates.

        Grid positions are fractions and land proportionally on any screen, but
        sizes are px — so the grids get `authored_at`'s tier sizes stamped on
        instantiation, which is the one moment no user edit can be lost."""
        template = self._load_template()
        if template is None:
            return None
        doc = copy.deepcopy(template)
        doc['id'] = mint_id()
        doc['name'] = str(name).strip() or SEED_NAME
        grids = doc['modules'].get('grids', {}).get('grids')
        if grids:
            apply_seed_sizes(grids, authored_at[1])
        return doc if self.write(doc) else None

    def _load_template(self) -> dict | None:
        for path in self.template_paths:
            if path.is_file():
                doc = self._read_doc(path)
                if doc is not None:
                    return doc
        return None

    def has_template(self) -> bool:
        """Whether any template on the chain passes the gate (drives whether
        first-launch offers the 'Use Defaults' card)."""
        return self._load_template() is not None

    def duplicate(self, profile_id: str) -> dict | None:
        held = self.load(profile_id)
        if held is None:
            return None
        doc = copy.deepcopy(held[1])
        doc['id'] = mint_id()
        doc['name'] = self.unique_name(f"{doc['name']} (copy)")
        return doc if self.write(doc) else None

    def unique_name(self, wanted: str) -> str:
        """`wanted`, suffixed ' 2', ' 3', … until no listed profile carries it."""
        taken = {str(d['name']).casefold() for _, d in self.list_profiles()}
        if wanted.casefold() not in taken:
            return wanted
        n = 2
        while f'{wanted} {n}'.casefold() in taken:
            n += 1
        return f'{wanted} {n}'

    def rename(self, profile_id: str, new_name: str) -> Path | None:
        """Update the display name and re-slug the file. The id never changes,
        so pointers survive; if old-file cleanup fails, listing dedupe heals it
        (newest wins). Returns the new path, or None (unknown id/empty name/IO)."""
        new_name = str(new_name).strip()
        held = self.load(profile_id)
        if held is None or not new_name:
            return None
        old_path, doc = held
        doc['name'] = new_name
        target = old_path if slugify(new_name) == old_path.stem else self._new_path(new_name)
        try:
            safe_save_json(target, validate_document(self.registry, doc))
        except OSError as e:
            logger.warning('Could not rename profile to %s: %s', target.name, e)
            return None
        if target != old_path:
            self._remove_quietly(old_path)
            self._remove_quietly(self._bak_path(old_path))
        return target

    def delete(self, profile_id: str) -> bool:
        """Move the entry into trash/ (collision-suffixed) and prune trash to
        the newest TRASH_KEEP files. The session .bak dies with it."""
        held = self.load(profile_id)
        if held is None:
            return False
        path = held[0]
        try:
            self.trash_dir.mkdir(parents=True, exist_ok=True)
            target = self.trash_dir / path.name
            n = 2
            while target.exists():
                target = self.trash_dir / f'{path.stem} ({n}){path.suffix}'
                n += 1
            path.replace(target)
        except OSError as e:
            logger.warning('Could not trash profile %s: %s', path.name, e)
            return False
        self._remove_quietly(self._bak_path(path))
        self._prune_trash()
        return True

    def _prune_trash(self) -> None:
        try:
            entries = sorted(
                (p for p in self.trash_dir.glob('*.json') if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for stale in entries[TRASH_KEEP:]:
                self._remove_quietly(stale)
        except OSError as e:
            logger.debug('Trash prune skipped: %s', e)

    def ensure_nonempty(self, authored_at: tuple[int, int]) -> dict | None:
        """The library-never-empty invariant: when no entry exists, seed
        SEED_NAME from the template chain (blank fallback if none validates).
        Returns the seeded document, or None when the library was not empty."""
        if self.list_profiles():
            return None
        doc = self.create_from_template(SEED_NAME, authored_at)
        if doc is None:
            doc = self.create_blank(SEED_NAME, authored_at)
        return doc

    # ------------------------------------------------------------------ #
    # SESSION SNAPSHOTS
    # ------------------------------------------------------------------ #

    @staticmethod
    def _bak_path(path: Path) -> Path:
        return path.with_name(path.name + '.bak')

    def write_session_bak(self, doc: dict) -> None:
        """Persist the session-start snapshot beside the entry's file. Crash
        insurance behind File ▸ Revert; best-effort, never raises."""
        held = self.load(doc.get('id', ''))
        if held is None:
            return
        try:
            safe_save_json(self._bak_path(held[0]), doc)
        except OSError as e:
            logger.debug('Session snapshot skipped: %s', e)

    def read_session_bak(self, profile_id: str) -> dict | None:
        """The entry's session-start snapshot through the gate, or None."""
        held = self.load(profile_id)
        if held is None:
            return None
        bak = self._bak_path(held[0])
        return self._read_doc(bak) if bak.is_file() else None

    @staticmethod
    def _remove_quietly(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.debug('Could not remove %s: %s', path.name, e)
