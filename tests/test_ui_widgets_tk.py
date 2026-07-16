"""Tk-level regression tests for ui_widgets binding hygiene.

Two pinned behaviors (both verified against a live Tk before fixing):

  1. `add_tooltip` is idempotent per widget — a repeat call updates the
     existing tooltip's text instead of stacking another live instance.
     Refresh paths (the game-path label re-adds its tooltip on every folder
     change) would otherwise accumulate <Enter> bindings and show overlapping
     stale tooltips on a single hover.
  2. `bind_label_hover_colors` appends (add="+") rather than overwriting, so
     a tooltip bound to the same widget first keeps working.

Windows-gated like test_panels_construct (Tk UI smoke matches CI). Animation
and real hover timing stay manual QA; these assert the binding/instance
mechanics deterministically.

Run: `pytest tests/test_ui_widgets_tk.py` (from repo root).
"""

import sys
import tkinter as tk

import pytest

from kazbars.ui_widgets import add_tooltip, bind_label_hover_colors

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32',
    reason='Tk UI smoke is Windows-only (matches CI)',
)


@pytest.fixture(scope='module')
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def _handler_count(widget, sequence):
    script = widget.bind(sequence) or ''
    return len([ln for ln in script.splitlines() if ln.strip()])


def test_add_tooltip_is_idempotent_per_widget(root):
    lbl = tk.Label(root, text='x')
    add_tooltip(lbl, 'first')
    first_instance = lbl._kz_tooltip
    assert _handler_count(lbl, '<Enter>') == 1

    add_tooltip(lbl, 'second')
    # Same instance, updated text, no stacked bindings.
    assert lbl._kz_tooltip is first_instance
    assert lbl._kz_tooltip.text == 'second'
    assert _handler_count(lbl, '<Enter>') == 1


def test_add_tooltip_accepts_callable_text_on_update(root):
    lbl = tk.Label(root, text='x')
    add_tooltip(lbl, 'static')
    add_tooltip(lbl, lambda: 'dynamic')
    assert lbl._kz_tooltip.text() == 'dynamic'


def test_hover_colors_preserves_existing_enter_bindings(root):
    lbl = tk.Label(root, text='x')
    add_tooltip(lbl, 'tip')
    assert _handler_count(lbl, '<Enter>') == 1
    bind_label_hover_colors(lbl, '#888888', '#ffffff')
    # Appended, not replaced — the tooltip's handler survives.
    assert _handler_count(lbl, '<Enter>') == 2
    assert _handler_count(lbl, '<Leave>') == 2
