"""KazBars — profile document model (pure: no Tk, no file I/O).

One profile = one JSON document: a small envelope plus a `modules` map holding
one section per participating module. Sections are declared as `SectionSpec`s
(a `settings_core` Schema slice plus its apply lane) and collected into a
`SectionRegistry` by app.py at startup — modules never import each other for
this, and cluster modules may import this module (it is on the isolation
test's infrastructure list) to export their own `PROFILE_SECTION`.

`validate_document` is the single boundary: library load, envelope import, and
the migration ladder all pass through it, so an unvalidated document can reach
neither disk nor the running app. Old-format profiles (pre-revamp
`profile_schema` / root-level `grids`) are rejected, not migrated — clean
start, no legacy rungs. Documents stamped by a newer app (`schema` above
current) are refused untouched, never truncated down.

Envelope: `schema` (int, this module's ladder key), `id` (stable 8-hex,
minted at creation/import, survives rename), `name` (display name; filename
slugs derive from it but identity is the id), `authored_at` ([w, h],
display-only provenance), `modules` (sections). Unknown `modules` keys are
preserved verbatim so a document that visited a newer build round-trips
without loss; inside known sections the usual strict coerce/clamp/drop
applies (`validate_all`, or `validate_patch` for sparse override sections
whose absent keys mean "defer to a baseline held elsewhere").
"""

import copy
import re
import secrets
from collections.abc import Callable, Iterable
from typing import Any

from .settings_core import Migration, Schema, get_defaults, validate_all, validate_patch

DOC_SCHEMA_VERSION = 1

# Apply lanes — how a section's settings reach the game. BUILD is baked into
# the SWF by Build & Install; PATCH writes game XML only on an explicit Apply
# (never on profile switch); LIVE retunes desktop overlays immediately.
LANE_BUILD = 'build'
LANE_PATCH = 'patch'
LANE_LIVE = 'live'
LANES = (LANE_BUILD, LANE_PATCH, LANE_LIVE)

# Display-only fallback when a document carries no usable authored_at. Kept
# local (mirrors grid_model.DEFAULT_GAME_RESOLUTION) so this module imports
# only settings_core and stays safely importable from cluster modules.
_DEFAULT_AUTHORED_AT = [1920, 1080]

_ID_RE = re.compile(r'^[0-9a-f]{8}$')


class DocumentError(ValueError):
    """A document failed the boundary check. The message is user-presentable:
    the library skips files that raise it; import surfaces it verbatim."""


# =========================================================================== #
# SECTION CONTRACT                                                            #
# =========================================================================== #

class SectionSpec:
    """One module's slice of the profile document.

    `schema` is a settings_core Schema declared with `filename=''` (sections
    own no file). `sparse` sections validate via `validate_patch` — absent
    keys stay absent ("no opinion") and the empty dict is the default.
    `harvest_refs(section) -> iterable` lists the buff ids/names the section
    references, for self-contained export (None = section carries no refs).
    """

    def __init__(
        self,
        key: str,
        schema: Schema,
        lane: str,
        *,
        sparse: bool = False,
        harvest_refs: Callable[[dict], Iterable[Any]] | None = None,
    ) -> None:
        if lane not in LANES:
            raise ValueError(f'unknown lane: {lane!r}')
        self.key = key
        self.schema = schema
        self.lane = lane
        self.sparse = sparse
        self.harvest_refs = harvest_refs

    def defaults(self) -> dict[str, Any]:
        return {} if self.sparse else get_defaults(self.schema)

    def validate(self, raw: Any) -> dict[str, Any]:
        if self.sparse:
            return validate_patch(self.schema, raw)
        return validate_all(self.schema, raw)


class SectionRegistry:
    """The full section roster, populated once by app.py at startup. Order of
    registration is preserved (it fixes section order in written documents)."""

    def __init__(self) -> None:
        self._specs: dict[str, SectionSpec] = {}

    def register(self, spec: SectionSpec) -> None:
        if spec.key in self._specs:
            raise ValueError(f'section already registered: {spec.key!r}')
        self._specs[spec.key] = spec

    def get(self, key: str) -> SectionSpec | None:
        return self._specs.get(key)

    def specs(self) -> tuple[SectionSpec, ...]:
        return tuple(self._specs.values())

    def for_lane(self, lane: str) -> tuple[SectionSpec, ...]:
        return tuple(s for s in self._specs.values() if s.lane == lane)


# =========================================================================== #
# DOCUMENT CREATION                                                           #
# =========================================================================== #

def mint_id() -> str:
    """A fresh stable profile id: 8 lowercase hex chars. Minted at creation,
    duplication, and import; never regenerated by rename or edit."""
    return secrets.token_hex(4)


def new_document(registry: SectionRegistry, name: str, authored_at: Iterable[int]) -> dict:
    """A complete document at the current schema: fresh id, every registered
    section at its defaults (sparse sections empty)."""
    return {
        'schema': DOC_SCHEMA_VERSION,
        'id': mint_id(),
        'name': str(name).strip() or 'Profile',
        'authored_at': _coerce_authored_at(list(authored_at)),
        'modules': {spec.key: spec.defaults() for spec in registry.specs()},
    }


# =========================================================================== #
# MIGRATION LADDER                                                            #
# =========================================================================== #

# Document-level rungs, keyed off the envelope `schema` int. Ships empty; the
# machinery is live for the first format bump (rungs run inside
# validate_document, before section validation, so load and import migrate
# identically and never leave a stale document behind).
MIGRATIONS: tuple[Migration, ...] = ()


def _migrate(raw: dict) -> dict:
    current = raw.get('schema', 0)
    data = raw
    for m in MIGRATIONS:
        if current < m.to_version:
            data = m.upgrade(dict(data))
            current = m.to_version
    return data


# =========================================================================== #
# THE BOUNDARY                                                                #
# =========================================================================== #

def _coerce_authored_at(value: Any) -> list[int]:
    if (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
    ):
        return list(value)
    return list(_DEFAULT_AUTHORED_AT)


def validate_document(registry: SectionRegistry, raw: Any) -> dict:
    """Validate `raw` into a current-schema document, or raise `DocumentError`.

    Never mutates `raw`; the result is a fresh dict. Rejections: non-dict,
    old-format profile, missing/invalid envelope fields, schema above current.
    Known sections are strictly validated; unknown sections are deep-copied
    through verbatim.
    """
    if not isinstance(raw, dict):
        raise DocumentError('Not a KazBars profile.')
    if 'profile_schema' in raw or 'grids' in raw:
        raise DocumentError('This profile is from an older KazBars.')
    schema = raw.get('schema')
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        raise DocumentError('Not a KazBars profile.')
    if schema > DOC_SCHEMA_VERSION:
        raise DocumentError('This profile needs a newer KazBars — update the app first.')

    data = _migrate(raw)

    doc_id = data.get('id')
    if not isinstance(doc_id, str) or not _ID_RE.match(doc_id):
        raise DocumentError('This profile file is damaged (bad id).')

    raw_modules = data.get('modules')
    if not isinstance(raw_modules, dict):
        raw_modules = {}
    modules: dict[str, Any] = {}
    for spec in registry.specs():
        if spec.key in raw_modules:
            modules[spec.key] = spec.validate(raw_modules[spec.key])
        else:
            modules[spec.key] = spec.defaults()
    for key, value in raw_modules.items():
        if registry.get(key) is None:
            modules[key] = copy.deepcopy(value)

    return {
        'schema': DOC_SCHEMA_VERSION,
        'id': doc_id,
        'name': str(data.get('name', '')).strip() or 'Profile',
        'authored_at': _coerce_authored_at(data.get('authored_at')),
        'modules': modules,
    }
