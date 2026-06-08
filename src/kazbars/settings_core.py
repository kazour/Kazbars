"""KazBars — schema-driven settings core (pure, no Tk).

One engine behind every settings file. A `Schema` is an ordered set of typed
`Field`s plus a migration ladder; the functional API loads/validates/fills/saves
a settings dict against it, atomically. Each settings module (`deeps_settings`,
`live_tracker_settings`, `damageinfo_settings`, and `prefs` in Phase 2) declares
a `Schema` and routes its load/save/validate through here, so validation,
drop-unknown, fill-missing, atomic writes, and forward migrations all live in one
place instead of being hand-rolled per file.

**Strict by default.** `validate_all(..., mode='strict')` keeps only declared
fields — any persisted key that is not a `Field` is erased on the next save. A
dynamic key namespace (e.g. per-window positions) must therefore be modelled as a
single structured-dict `Field` with a custom `validate=`, not as N top-level keys.

Imports only stdlib + `settings_manager.safe_save_json` — safe on the mypy gate
and importable from CI without the UI extra.
"""

import copy
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .settings_manager import safe_save_json

logger = logging.getLogger(__name__)

SCHEMA_VERSION_KEY = 'schema_version'


# =========================================================================== #
# SCHEMA PRIMITIVES                                                            #
# =========================================================================== #

class Field:
    """One declared setting: its default plus how to coerce a stored value.

    Coercion strategy, in order of precedence:
      - `validate(value) -> value` — full override for bespoke fields
        (structured dicts, list filters); when given, `kind`/`min`/`max`/`choices`
        are ignored.
      - `kind='bool'` — `bool(value)`.
      - `choices` — membership test; with `kind='int'` the value is `int()`-coerced
        first (off-list or unparsable → default), otherwise matched as given.
      - `kind in ('int', 'float')` — `float()`-coerce, clamp to `[min, max]`, then
        return an `int` (rounded) or `float`. Unparsable → default.
      - no spec — value passes through unchanged.

    `**ui_metadata` (unit/description/tooltip/step/type/options/invert/relative …)
    is stashed on `.ui` for panels that read field metadata; it never affects
    persistence.
    """

    def __init__(
        self,
        default: Any,
        *,
        validate: Callable[[Any], Any] | None = None,
        min: Any = None,
        max: Any = None,
        kind: str | None = None,
        choices: tuple | None = None,
        **ui_metadata: Any,
    ) -> None:
        self.default = default
        self.validate = validate
        self.min = min
        self.max = max
        self.kind = kind
        self.choices = choices
        self.ui = ui_metadata


class Migration:
    """One ladder rung: `upgrade(data) -> data` lifts a settings dict to
    `to_version`. Rungs are applied in ascending `to_version` order for any file
    whose stored `schema_version` is below them. The ladder ships empty (clean
    start) but the machinery is live for the first post-publish schema bump."""

    def __init__(self, to_version: int, upgrade: Callable[[dict], dict]) -> None:
        self.to_version = to_version
        self.upgrade = upgrade


class Schema:
    """A settings file's full contract: filename, current integer version, the
    declared fields, and the (ordered) migration ladder."""

    def __init__(
        self,
        filename: str,
        version: int,
        fields: dict[str, Field],
        migrations: tuple[Migration, ...] = (),
    ) -> None:
        self.filename = filename
        self.version = version
        self.fields = dict(fields)
        self.migrations = tuple(sorted(migrations, key=lambda m: m.to_version))


# =========================================================================== #
# VALIDATION / COERCION                                                       #
# =========================================================================== #

def _coerce_field(f: Field, value: Any) -> Any:
    """Coerce one raw value against a single field's rules."""
    if f.validate is not None:
        return f.validate(value)
    if f.kind == 'bool':
        return bool(value)
    if f.choices is not None:
        if f.kind == 'int':
            try:
                coerced = int(value)
            except (TypeError, ValueError):
                return f.default
            return coerced if coerced in f.choices else f.default
        return value if value in f.choices else f.default
    if f.kind in ('int', 'float'):
        try:
            num = float(value)
        except (TypeError, ValueError):
            return f.default
        if f.min is not None:
            num = max(f.min, num)
        if f.max is not None:
            num = min(f.max, num)
        return round(num) if f.kind == 'int' else float(num)
    return value


def coerce(schema: Schema, key: str, value: Any) -> Any:
    """Coerce one value for `key`. Unknown keys pass through unchanged — the
    drop-unknown step lives in `validate_all`, not here (mirrors the per-file
    `validate_setting` contract callers rely on)."""
    f = schema.fields.get(key)
    if f is None:
        return value
    return _coerce_field(f, value)


def get_defaults(schema: Schema) -> dict[str, Any]:
    """A fresh defaults dict — each mutable default is deep-copied so callers can
    mutate the result without touching the schema."""
    return {key: copy.deepcopy(f.default) for key, f in schema.fields.items()}


def validate_all(schema: Schema, raw: Any, *, mode: str = 'strict') -> dict[str, Any]:
    """Start from defaults, coerce every declared key present in `raw`, and fill
    the rest. In `'strict'` mode (the default and only one used in-app) any
    undeclared key is dropped; any other mode keeps undeclared keys verbatim."""
    result = get_defaults(schema)
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        if key in schema.fields:
            result[key] = _coerce_field(schema.fields[key], value)
        elif mode != 'strict':
            result[key] = value
    return result


# =========================================================================== #
# MIGRATION LADDER                                                            #
# =========================================================================== #

def _migrate(schema: Schema, raw: dict) -> dict:
    """Run ordered ladder rungs from the stored `schema_version` up to the
    schema's current version. Empty ladder → returns `raw` unchanged. Idempotent:
    a dict already at the current version triggers no rung."""
    if not schema.migrations:
        return raw
    current = raw.get(SCHEMA_VERSION_KEY, 0)
    data = dict(raw)
    for m in schema.migrations:
        if current < m.to_version:
            data = m.upgrade(data)
            current = m.to_version
    return data


# =========================================================================== #
# FILE I/O                                                                    #
# =========================================================================== #

def _read_json(path: Path) -> dict | None:
    """Read a JSON object, or None on missing/corrupt/non-dict (logged at
    debug; never raises)."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.debug('Could not read %s: %s', path.name, e)
    return None


def load(schema: Schema, folder: str | Path) -> dict[str, Any]:
    """Read `<folder>/<schema.filename>`, run the migration ladder, then validate
    + fill. A missing or corrupt file yields defaults — load never raises."""
    raw = _read_json(Path(folder) / schema.filename)
    if raw is None:
        return get_defaults(schema)
    return validate_all(schema, _migrate(schema, raw), mode='strict')


def save(schema: Schema, folder: str | Path, data: dict) -> bool:
    """Validate `data`, stamp `schema_version`, and write atomically (temp +
    rename via `safe_save_json`). Creates the folder if missing. Returns success."""
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        validated = validate_all(schema, data, mode='strict')
        validated[SCHEMA_VERSION_KEY] = schema.version
        safe_save_json(Path(folder) / schema.filename, validated)
        return True
    except OSError as e:
        logger.warning('Could not save %s: %s', schema.filename, e)
        return False


# =========================================================================== #
# STATEFUL STORE (load-once, get/set, save) — used by the prefs facade         #
# =========================================================================== #

class Store:
    """A loaded settings file held in memory: `get`/`set` against `.data`, then
    `save()` atomically. The three typed settings modules use the functional API
    above (folder varies per call); `prefs` (Phase 2) wraps a `Store`."""

    def __init__(self, schema: Schema, folder: str | Path) -> None:
        self.schema = schema
        self.folder = Path(folder)
        self.data = load(schema, folder)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self, data: dict | None = None) -> bool:
        if data is not None:
            self.data = data
        return save(self.schema, self.folder, self.data)

    def reload(self) -> None:
        """Re-read from disk, replacing in-memory state (used after a restore
        overwrites the file underneath the running app)."""
        self.data = load(self.schema, self.folder)
