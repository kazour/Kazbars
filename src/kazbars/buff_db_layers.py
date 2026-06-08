"""KazBars — three-layer buff DB merge (pure, no Tk).

Effective DB = stock floor (``assets/``) ← OTA override (``content/``) ← user
deltas (``database_user.json``), and **user always wins**. Buffs merge by their
primary spell ID (``ids[0]`` — the AoC-canonical identity; ``name`` is
display-only, and whitelist refs already normalise to ``ids[0]`` on load).

Each layer is a v2 buff file (``{version, buffs: [...]}``). The user delta file
additionally carries a ``deleted`` tombstone list of floor ``ids[0]`` the user
has hidden — a tombstone removes a stock/content buff from the effective set but
is overridden by a user buff that re-adds the same ``ids[0]``.

``provenance`` maps each effective buff's ``ids[0]`` to the layer it came from
(``stock`` | ``content`` | ``user``) so the editor can badge it (Built-in /
Updated / Yours) and pick the right delete copy. The editor writes only
``database_user.json`` (via ``DeltaStore``); ``assets/`` is never written.
"""

import json
import logging
from pathlib import Path
from typing import Any

from .settings_manager import safe_save_json

logger = logging.getLogger(__name__)

USER_DB_VERSION = 2

STOCK = 'stock'
CONTENT = 'content'
USER = 'user'

# Optional buff keys whose absence == this value; normalised away before two
# buffs are compared for equality, so an edit that doesn't actually change a
# stock buff isn't recorded as a spurious user override.
_OPTIONAL_DEFAULTS = {'stacking': False, 'partialList': False, 'stackStart': 1, 'stackEnd': 0}


def _identity(buff: dict) -> Any:
    """A buff's merge key: its primary spell ID (``ids[0]``), or None if it has none."""
    ids = buff.get('ids')
    return ids[0] if ids else None


def _canonical(buff: dict) -> dict:
    """Drop optional keys left at their default so equality ignores cosmetic
    differences (e.g. an explicit ``stackEnd: 0`` vs the key being absent)."""
    return {k: v for k, v in buff.items() if not (k in _OPTIONAL_DEFAULTS and v == _OPTIONAL_DEFAULTS[k])}


def _buffs_equal(a: dict, b: dict) -> bool:
    return _canonical(a) == _canonical(b)


def _read_buffs(path) -> list:
    """Read a v2 buff file's ``buffs`` list, or ``[]`` on missing/corrupt."""
    if not path:
        return []
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                buffs = data.get('buffs', [])
                if isinstance(buffs, list):
                    return buffs
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning('Could not read buff layer %s: %s', Path(path).name, e)
    return []


def _read_user_delta(path) -> tuple[list, set]:
    """Read ``database_user.json`` → (buffs, deleted-id set). Missing/corrupt →
    ``([], set())``. Never raises."""
    buffs: list = []
    deleted: set = set()
    if not path:
        return buffs, deleted
    try:
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                b = data.get('buffs', [])
                if isinstance(b, list):
                    buffs = b
                d = data.get('deleted', [])
                if isinstance(d, list):
                    deleted = set(d)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning('Could not read user buff deltas: %s', e)
    return buffs, deleted


def merge_layers(stock_buffs: list, content_buffs: list, user_buffs: list,
                 deleted: set) -> tuple[list, dict]:
    """Merge three buff lists by ``ids[0]`` (user wins), then apply tombstones.
    Returns ``(effective_buffs, provenance)`` where provenance maps ``ids[0]`` →
    layer. First-seen order (stock → content → user) is preserved for stable
    output; an override keeps the buff in its first-seen position."""
    merged: dict = {}
    provenance: dict = {}
    order: list = []

    for layer, buffs in ((STOCK, stock_buffs), (CONTENT, content_buffs), (USER, user_buffs)):
        for buff in buffs:
            key = _identity(buff)
            if key is None:
                continue
            if key not in merged:
                order.append(key)
            merged[key] = buff
            provenance[key] = layer

    # Tombstones hide floor (stock/content) buffs the user deleted — but a user
    # buff re-adding the same ids[0] wins over its own tombstone.
    for key in deleted:
        if key in merged and provenance.get(key) != USER:
            merged.pop(key, None)
            provenance.pop(key, None)

    effective = [merged[k] for k in order if k in merged]
    return effective, provenance


def load_effective(stock_path, content_path=None, user_delta_path=None) -> tuple[list, dict]:
    """Load + merge the three layers from disk. Missing layers are treated as
    empty. Returns ``(effective_buffs, provenance)``."""
    stock = _read_buffs(stock_path)
    content = _read_buffs(content_path)
    user_buffs, deleted = _read_user_delta(user_delta_path)
    return merge_layers(stock, content, user_buffs, deleted)


def load_floor(stock_path, content_path=None, stock_fallback_path=None) -> tuple[list, dict]:
    """The merge floor — stock ← content override, **no user deltas**. Returns
    ``(floor_buffs, floor_provenance)`` (provenance is ``stock`` | ``content``).
    Mirrors the effective load's corrupt-stock fallback so the editor diffs
    against the same floor the app booted from. The editor uses this to compute
    deltas and badge each row."""
    stock = _read_buffs(stock_path)
    if not stock and stock_fallback_path:
        stock = _read_buffs(stock_fallback_path)
    content = _read_buffs(content_path)
    return merge_layers(stock, content, [], set())


def compute_delta(floor_buffs: list, edited_buffs: list) -> dict:
    """Diff the edited effective list against the floor (stock ← content).

    Returns ``{version, buffs, deleted}``:
      - ``buffs`` — user adds + overrides: every edited buff that is new (no
        floor entry for its ``ids[0]``) or differs from the floor buff.
      - ``deleted`` — sorted ``ids[0]`` of floor buffs the user removed
        (tombstones). A user buff whose ``ids[0]`` isn't in the floor and was
        removed simply drops out — no tombstone needed.

    Keyed on ``ids[0]``; changing a buff's *primary* ID reads as a new user buff
    plus a tombstone of the old ID (the old floor entry is now absent from edited).
    """
    floor_by_id: dict = {}
    for b in floor_buffs:
        key = _identity(b)
        if key is not None:
            floor_by_id[key] = b

    edited_keys: set = set()
    delta_buffs: list = []
    for b in edited_buffs:
        key = _identity(b)
        if key is None:
            continue
        edited_keys.add(key)
        floor_b = floor_by_id.get(key)
        if floor_b is None or not _buffs_equal(floor_b, b):
            delta_buffs.append(b)

    deleted = sorted(k for k in floor_by_id if k not in edited_keys)
    return {'version': USER_DB_VERSION, 'buffs': delta_buffs, 'deleted': deleted}


class DeltaStore:
    """Load/save ``database_user.json`` as ``{version:2, buffs:[...],
    deleted:[...]}``, atomic via ``safe_save_json``."""

    def __init__(self, path) -> None:
        self.path = Path(path)

    def load(self) -> dict:
        buffs, deleted = _read_user_delta(self.path)
        return {'version': USER_DB_VERSION, 'buffs': buffs, 'deleted': sorted(deleted)}

    def save(self, delta: dict) -> None:
        data = {
            'version': USER_DB_VERSION,
            'buffs': delta.get('buffs', []),
            'deleted': sorted(delta.get('deleted', [])),
        }
        safe_save_json(self.path, data)
