"""Tests for kazbars.ui_components.ToastModel — the pure state core of the
toast system: per-severity duration defaults, coalesce-by-key, the visible
cap + overflow queue, two-tier priority, and bottom-anchored slot offsets
(the overlap regression). The Tk renderer (ToastManager) stays manual-QA
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


def test_coalesce_carries_on_click_and_style_visible():
    # Consecutive grid deletes share one undo key: clicking the coalesced
    # toast must undo the LATEST delete, so on_click (and severity) has to
    # replace the earlier record's, not just the text.
    m = ToastModel()
    undo_a, undo_b = object(), object()
    _, first = m.show('Deleted A', 'info', key='undo', on_click=undo_a)
    state, second = m.show('Deleted B', 'warning', key='undo', on_click=undo_b)
    assert state == 'coalesced'
    assert second is first
    assert first.message == 'Deleted B'
    assert first.on_click is undo_b
    assert first.style == 'warning'


def test_coalesce_carries_on_click_and_style_queued():
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')
    cb1, cb2 = object(), object()
    _, queued = m.show('q1', 'warning', key='k', on_click=cb1)
    state, again = m.show('q2', 'success', key='k', on_click=cb2)
    assert state == 'queued'
    assert again is queued
    assert queued.on_click is cb2
    assert queued.style == 'success'


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


def test_coalesce_escalation_resorts_queued_ahead_of_lows():
    # A queued keyed toast that coalesces low→high (info→warning, the grid_resize
    # case) must jump ahead of low-priority toasts already queued in front of it.
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')          # fill the visible cap
    _, low0 = m.show('low0', 'info')        # plain low, queued first
    _, keyed = m.show('resize', 'info', key='grid_resize')
    assert m.queued == [low0, keyed]
    m.show('unassigned', 'warning', key='grid_resize')   # escalate
    assert m.queued == [keyed, low0]        # keyed jumped the low band
    assert keyed.style == 'warning'


def test_coalesce_deescalation_moves_queued_behind_highs():
    # The reverse: a queued high-priority keyed toast coalescing high→low
    # (warning→success) drops behind genuine high-priority toasts.
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')
    _, keyed = m.show('unassigned', 'warning', key='grid_resize')
    _, high1 = m.show('urgent', 'danger')
    assert m.queued == [keyed, high1]
    m.show('restored', 'success', key='grid_resize')     # de-escalate
    assert m.queued == [high1, keyed]       # keyed fell behind the danger
    assert keyed.style == 'success'


def test_coalesce_within_band_keeps_queue_position():
    # Same-band coalesce (info→success, both low) must NOT re-sort.
    m = ToastModel()
    for i in range(3):
        m.show(f'fill{i}', 'info')
    _, first = m.show('a', 'info')
    _, keyed = m.show('resize', 'info', key='grid_resize')
    assert m.queued == [first, keyed]
    m.show('resize2', 'success', key='grid_resize')
    assert m.queued == [first, keyed]       # position preserved
    assert keyed.message == 'resize2'


def test_manager_coalesce_onto_unmounted_toast_does_not_raise():
    # A just-promoted toast lives in `visible` with widget=None until _mount()
    # assigns it (tail of _finish_remove). A same-key coalesce landing in that
    # window must not deref None; the model update still lands for _mount to
    # render. ToastManager touches no Tk on this path, so it runs headless.
    mgr = ToastManager(object())
    _, promoted = mgr._model.show('first', 'info', key='k')  # 'visible', unmounted
    assert promoted.widget is None
    mgr.show('second', 'warning', key='k')  # must not raise
    assert promoted.message == 'second'
    assert promoted.style == 'warning'


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
