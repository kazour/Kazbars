"""Tests for kazbars.ui_components.ToastModel — the pure state core of the
toast system: per-severity duration defaults, coalesce-by-key, the visible
cap + overflow queue, two-tier priority, and bottom-anchored slot offsets
(the overlap regression). The Tk renderer (ToastManager) stays /smoke
territory — animations and real geometry aren't unit-testable headlessly.

Run: `pytest tests/test_toast_model.py` (from repo root).
"""

from kazbars.ui_components import ToastManager, ToastModel


def _dismiss(model, toast):
    """Dismiss a visible toast the way the renderer does: exit, then remove."""
    model.start_exit(toast)
    return model.remove(toast)


def test_default_durations_by_severity():
    m = ToastModel()
    assert m.show('a', 'info')[1].duration == 4
    assert m.show('b', 'success')[1].duration == 4
    assert m.show('c', 'warning')[1].duration == 6
    assert m.show('d', 'danger')[1].duration == 8
    assert m.show('e', 'error')[1].duration == 8


def test_explicit_duration_wins():
    _, t = ToastModel().show('build failed', 'error', duration=10)
    assert t.duration == 10


def test_visible_capped_then_queued():
    m = ToastModel()
    states = [m.show(f'm{i}', 'info')[0] for i in range(5)]
    assert states == ['visible', 'visible', 'visible', 'queued', 'queued']
    assert len(m.visible) == ToastModel.MAX_VISIBLE
    assert len(m.queued) == 2


def test_removal_promotes_fifo():
    m = ToastModel()
    toasts = [m.show(f'm{i}', 'info')[1] for i in range(5)]
    promoted = _dismiss(m, toasts[0])
    assert promoted == [toasts[3]]
    assert toasts[3] in m.visible
    assert m.queued == [toasts[4]]


def test_high_priority_jumps_queued_low():
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')
    _, low1 = m.show('low1', 'info')
    _, low2 = m.show('low2', 'success')
    _, high1 = m.show('high1', 'warning')
    _, high2 = m.show('high2', 'danger')
    # highs jump queued lows, stay FIFO among themselves
    assert m.queued == [high1, high2, low1, low2]


def test_high_priority_never_displaces_visible():
    m = ToastModel()
    visible = [m.show(f'fill{i}', 'info')[1] for i in range(3)]
    state, _ = m.show('urgent', 'danger')
    assert state == 'queued'
    assert m.visible == visible


def test_coalesce_updates_visible_in_place():
    m = ToastModel()
    _, first = m.show('Unassigned 1 buff', 'warning', key='grid_resize')
    state, second = m.show('Unassigned 2 buffs', 'warning', key='grid_resize')
    assert state == 'coalesced'
    assert second is first
    assert first.message == 'Unassigned 2 buffs'
    assert len(m.visible) == 1


def test_coalesce_skips_exiting_toast():
    m = ToastModel()
    _, first = m.show('old', 'warning', key='k')
    m.start_exit(first)
    state, second = m.show('new', 'warning', key='k')
    assert state == 'visible'
    assert second is not first


def test_coalesce_updates_queued_record():
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')
    _, queued = m.show('v1', 'info', key='k')
    state, again = m.show('v2', 'info', key='k')
    assert state == 'queued'
    assert again is queued
    assert queued.message == 'v2'
    assert len(m.queued) == 1


def test_exiting_toast_holds_its_slot_until_removed():
    m = ToastModel()
    toasts = [m.show(f'm{i}', 'info')[1] for i in range(3)]
    m.start_exit(toasts[0])
    state, fourth = m.show('m3', 'info')
    assert state == 'queued'  # a fading toast still occupies a slot
    assert m.remove(toasts[0]) == [fourth]


def test_slot_offsets_never_overlap():
    # The Bug-1 regression: stacked toasts must each clear the one below,
    # whatever their (real, measured) heights are.
    heights = [30, 44, 28]  # oldest → newest
    base, gap = 12, 4
    offsets = ToastModel.slot_offsets(heights, base, gap)
    assert offsets[-1] == base  # newest sits at the bottom margin
    for i in range(len(heights) - 1):
        assert offsets[i] >= offsets[i + 1] + heights[i + 1] + gap


def test_slot_offsets_empty():
    assert ToastModel.slot_offsets([], 12, 4) == []


def test_every_severity_has_a_color_and_danger_is_red():
    # Pins the old silent fallback: 'danger' wasn't in STYLES and rendered
    # accent-colored instead of red.
    for style in ToastModel.DEFAULT_DURATIONS:
        assert style in ToastManager.STYLES
    assert ToastManager.STYLES['danger'] == 'danger'
    assert ToastManager.STYLES['error'] == 'danger'
