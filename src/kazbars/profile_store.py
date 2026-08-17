"""KazBars — runtime profile store: the in-memory document + debounced autosave.

One `ProfileStore` per open profile. Panels are views: they read sections via
`get_section` (treat as read-only) and write through `set_section` /
`update_section`, which arm a debounced atomic write — there is no dirty flag,
no Save prompt, and no gather-at-save step, so section data exists independent
of any panel's lifetime. `flush()` forces the pending write (Build & Install
and app exit call it, guaranteeing built == saved).

Scheduling is injected (`schedule(ms, fn) -> token` / `cancel(token)`; app.py
passes `after`/`after_cancel`) so the debounce is deterministic under test.
On the first mutation of a session the pre-mutation document is handed to
`write_bak` once — the snapshot behind `revert_to_session_start` and the
corrupt-load fallback. A failed write keeps the document dirty, sets
`last_write_failed` (the exit path shows a rescue offer while it's set), and
retries on a slower cadence until a write lands.
"""

import copy
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DEBOUNCE_MS = 1000
RETRY_MS = 5000


class ProfileStore:
    def __init__(
        self,
        document: dict,
        writer: Callable[[dict], Any],
        schedule: Callable[[int, Callable[[], None]], Any],
        cancel: Callable[[Any], None],
        write_bak: Callable[[dict], None] | None = None,
    ) -> None:
        self._doc = document
        self._writer = writer
        self._schedule = schedule
        self._cancel = cancel
        self._write_bak = write_bak
        self._session_start = copy.deepcopy(document)
        self._bak_written = False
        self._pending: Any = None
        self._dirty = False
        self.last_write_failed = False

    # ------------------------------------------------------------------ #
    # READ
    # ------------------------------------------------------------------ #

    @property
    def document(self) -> dict:
        return self._doc

    @property
    def dirty(self) -> bool:
        return self._dirty

    def get_section(self, key: str) -> dict:
        """The live section dict — read-only by contract; mutate via
        `set_section`/`update_section` so the autosaver arms."""
        return self._doc['modules'].setdefault(key, {})

    # ------------------------------------------------------------------ #
    # MUTATE (every path arms the autosaver)
    # ------------------------------------------------------------------ #

    def set_section(self, key: str, data: dict) -> None:
        self._doc['modules'][key] = data
        self._touch()

    def update_section(self, key: str, patch: dict) -> None:
        self._doc['modules'].setdefault(key, {}).update(patch)
        self._touch()

    def set_name(self, name: str) -> None:
        self._doc['name'] = str(name).strip() or self._doc['name']
        self._touch()

    def set_authored_at(self, resolution) -> None:
        """Re-anchor the document's provenance resolution (after a load-time
        rescale or a game-resolution change re-bases the coordinates)."""
        self._doc['authored_at'] = [int(resolution[0]), int(resolution[1])]
        self._touch()

    def revert_to_session_start(self) -> None:
        """Restore the session-start snapshot. The revert is itself a mutation,
        so the restored state autosaves like any other edit."""
        self._doc = copy.deepcopy(self._session_start)
        self._touch()

    def _touch(self) -> None:
        if not self._bak_written and self._write_bak is not None:
            self._bak_written = True
            self._write_bak(copy.deepcopy(self._session_start))
        self._dirty = True
        self._arm(DEBOUNCE_MS)

    def _arm(self, delay_ms: int) -> None:
        if self._pending is not None:
            self._cancel(self._pending)
        self._pending = self._schedule(delay_ms, self._fire)

    def _fire(self) -> None:
        self._pending = None
        self._write_now()

    # ------------------------------------------------------------------ #
    # PERSIST
    # ------------------------------------------------------------------ #

    def _write_now(self) -> None:
        try:
            result = self._writer(self._doc)
        except OSError as e:
            logger.warning('Profile autosave failed: %s', e)
            result = None
        if result:
            self._dirty = False
            self.last_write_failed = False
        else:
            self.last_write_failed = True
            self._arm(RETRY_MS)

    def flush(self) -> bool:
        """Cancel any pending debounce and write now if dirty. True when the
        document is safely on disk."""
        if self._pending is not None:
            self._cancel(self._pending)
            self._pending = None
        if self._dirty:
            self._write_now()
        return not self._dirty
