"""Tests for `profile_store` — the in-memory document + debounced autosave.

The scheduler is injected, so the debounce is exercised deterministically: a
fake records scheduled callbacks and fires them by hand. Pins the debounce
collapse (N mutations → one write), flush-before-build semantics, the lazy
once-only session .bak, revert-then-autosave, and the failed-write retry loop
with `last_write_failed` for the exit rescue path.

Run: `pytest tests/test_profile_store.py` (from repo root).
"""

from kazbars.profile_store import DEBOUNCE_MS, RETRY_MS, ProfileStore


class FakeScheduler:
    def __init__(self):
        self.pending = {}
        self._n = 0

    def schedule(self, ms, fn):
        self._n += 1
        self.pending[self._n] = (ms, fn)
        return self._n

    def cancel(self, token):
        self.pending.pop(token, None)

    def fire(self):
        """Run every pending callback (as if its delay elapsed)."""
        for token in list(self.pending):
            ms, fn = self.pending.pop(token)
            fn()


class SpyWriter:
    def __init__(self):
        self.calls = []
        self.fail = False

    def __call__(self, doc):
        self.calls.append({"name": doc["name"], "alpha": dict(doc["modules"]["alpha"])})
        return None if self.fail else object()


def _doc():
    return {
        "schema": 1,
        "id": "a3f81c2e",
        "name": "Setup",
        "authored_at": [2560, 1440],
        "modules": {"alpha": {"count": 10}},
    }


def _store(write_bak=None):
    sched = FakeScheduler()
    writer = SpyWriter()
    store = ProfileStore(_doc(), writer, sched.schedule, sched.cancel, write_bak=write_bak)
    return store, sched, writer


def test_mutations_collapse_into_one_debounced_write():
    store, sched, writer = _store()
    store.update_section("alpha", {"count": 1})
    store.update_section("alpha", {"count": 2})
    store.set_name("Renamed")
    assert writer.calls == []  # nothing until the debounce fires
    assert len(sched.pending) == 1  # re-armed, not stacked
    (ms, _fn), = sched.pending.values()
    assert ms == DEBOUNCE_MS
    sched.fire()
    assert len(writer.calls) == 1
    assert writer.calls[0] == {"name": "Renamed", "alpha": {"count": 2}}
    assert not store.dirty


def test_flush_writes_now_and_cancels_pending():
    store, sched, writer = _store()
    store.update_section("alpha", {"count": 5})
    assert store.flush() is True
    assert len(writer.calls) == 1
    assert sched.pending == {}  # debounce cancelled, not left to double-write
    sched.fire()
    assert len(writer.calls) == 1


def test_clean_flush_writes_nothing():
    store, sched, writer = _store()
    assert store.flush() is True
    assert writer.calls == []


def test_session_bak_written_lazily_and_once():
    baks = []
    store, sched, writer = _store(write_bak=baks.append)
    assert baks == []  # read-only session: no snapshot
    store.update_section("alpha", {"count": 1})
    store.update_section("alpha", {"count": 2})
    assert len(baks) == 1
    assert baks[0]["modules"]["alpha"] == {"count": 10}  # pre-mutation state


def test_revert_restores_snapshot_and_autosaves():
    store, sched, writer = _store()
    store.update_section("alpha", {"count": 99})
    sched.fire()
    store.revert_to_session_start()
    assert store.get_section("alpha") == {"count": 10}
    sched.fire()
    assert writer.calls[-1]["alpha"] == {"count": 10}  # reverted state persisted


def test_failed_write_sets_flag_and_retries_slower():
    store, sched, writer = _store()
    writer.fail = True
    store.update_section("alpha", {"count": 1})
    sched.fire()
    assert store.last_write_failed is True
    assert store.dirty is True
    (ms, _fn), = sched.pending.values()
    assert ms == RETRY_MS
    writer.fail = False
    sched.fire()  # retry lands
    assert store.last_write_failed is False
    assert not store.dirty
    assert len(writer.calls) == 2


def test_writer_oserror_is_a_failure_not_a_crash():
    def exploding_writer(doc):
        raise OSError("disk full")

    sched = FakeScheduler()
    store = ProfileStore(_doc(), exploding_writer, sched.schedule, sched.cancel)
    store.update_section("alpha", {"count": 1})
    sched.fire()
    assert store.last_write_failed is True
    assert store.flush() is False  # still not on disk — exit path shows rescue
