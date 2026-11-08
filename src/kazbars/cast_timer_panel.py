"""
KazBars — Cast timer dialog.

Extras-menu settings for the cast-timer overlay (the timer-only Flash overlay
showing player/target cast time): the build gate, the two baked positions, and
the shared text style. Reads/writes the profile document's `cast_timer`
section (data layer: `cast_timer.py`; the store autosaves). Positions are
stored as fractions of the game resolution; the X/Y fields display projected
px at the current resolution (the grid editor convention). The build bakes
the values into the generated SWF. The shell is `extras_dialog.ExtrasShell`.
Functions take the KazBarsApp instance as first arg.

The face is the profile's overlay font (Grids tab), so the dialog offers Bold
and a Size (a percent of the overlay size, hinted in pt) rather than a family
picker; the sample preview draws in Arial at the baked size, and dims with
the gate so it never looks live on a disabled dialog.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .cast_timer import validate_config
from .extras_dialog import ExtrasShell, raise_if_open
from .grid_model import get_game_resolution_or_default
from .overlay_size import panel_fs
from .ui_forms import ColorSwatch, create_card, position_fields, size_slider
from .ui_helpers import (
    FONT_BODY,
    FONT_SMALL,
    GRID_PREVIEW_PX,
    PAD_ROW,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip, app_toast

_WIDTH = 470
_HEIGHT = 450

_DISPLAY_LABELS = (("Elapsed", "elapsed"), ("Total", "total"), ("Both", "both"))
_DISPLAY_TO_LABEL = {v: k for k, v in _DISPLAY_LABELS}
_LABEL_TO_DISPLAY = dict(_DISPLAY_LABELS)
_SAMPLES = {"elapsed": "1.2", "total": "2.5", "both": "1.2 / 2.5"}

# Fixed width (chars) of the Player/Target row descriptors so both position
# rows start their spinboxes at the same x.
_POS_LABEL_W = 7


def open_cast_timer_dialog(app):
    """Open or focus the cast-timer settings dialog (modal). On apply, persist
    the config — it takes effect in-game on the next Build & Install."""
    if raise_if_open(app.cast_timer_dialog):
        return app.cast_timer_dialog

    cfg = validate_config(app.profile_store.get_section('cast_timer'))
    game_w, game_h = get_game_resolution_or_default()
    shell = ExtrasShell(
        app, 'cast_timer_dialog', title="Cast Timer",
        tip="A cast-time readout for you and your target. Apply, then Build & Install to see it.",
        gate_text="Include the cast timer in builds",
        gate_tip="Adds a cast-time readout for you and your target to the in-game overlay.",
        enabled=cfg['enabled'], width=_WIDTH)
    dialog, content, enabled_var = shell.dialog, shell.content, shell.enabled_var
    sink: list = []  # descriptor labels collected from the gated rows

    pos_card = create_card(content, "Position")
    pos_card.pack(fill='x', pady=(0, PAD_ROW))
    pos_blurb = ttk.Label(
        pos_card,
        text="Where each timer first appears in-game. Shift+Ctrl+Alt\n"
             "toggles preview mode: drag a timer and the game remembers.\n"
             "X/Y here only seed a first-ever session.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
    pos_blurb.pack(anchor='w', pady=(0, PAD_XS))
    shell.dim(pos_blurb)

    readers = {}
    for title, side in (("Player", 'player'), ("Target", 'target')):
        row = ttk.Frame(pos_card)
        row.pack(anchor='w', pady=(0, PAD_XS))
        row_lbl = ttk.Label(row, text=title, font=FONT_BODY,
                            foreground=THEME_COLORS['body'],
                            width=_POS_LABEL_W, anchor='w')
        row_lbl.pack(side='left')
        sink.append(row_lbl)
        x_spin, y_spin, readers[side] = position_fields(
            row, cfg[f'{side}Fx'], cfg[f'{side}Fy'], game_w, game_h, label_sink=sink)
        shell.gate(x_spin, y_spin)

    text_card = create_card(content, "Text")
    text_card.pack(fill='x', pady=(0, PAD_ROW))

    # Style controls on the left, a live sample of what they produce on the right.
    text_row = ttk.Frame(text_card)
    text_row.pack(fill='x')
    style_col = ttk.Frame(text_row)
    style_col.pack(side='left', fill='x', expand=True)
    preview = tk.Canvas(text_row, width=GRID_PREVIEW_PX, height=GRID_PREVIEW_PX,
                        bg=TK_COLORS['bg'], highlightthickness=0)
    preview.pack(side='right', padx=(PAD_XS, 0))

    bold_var = tk.BooleanVar(value=cfg['bold'])
    display_var = tk.StringVar(value=_DISPLAY_TO_LABEL.get(cfg['display'], "Both"))
    color = [cfg['color']]  # boxed so the swatch callback can rebind it

    def _redraw_preview(*_args):
        """Draw the timer text as the overlay will render it — the baked size,
        chosen colour/weight — shrinking to fit the square so a large sample
        still reads as one line."""
        preview.delete("sample")
        sample = _SAMPLES.get(_LABEL_TO_DISPLAY.get(display_var.get(), "both"), "1.2 / 2.5")
        size = panel_fs(shell.base, size_var.get())
        font = tkfont.Font(family="Arial", size=size,
                           weight="bold" if bold_var.get() else "normal")
        while size > 7 and font.measure(sample) > GRID_PREVIEW_PX - 8:
            size -= 1
            font.configure(size=size)
        fill = f"#{color[0]}" if enabled_var.get() else TK_COLORS['dim_text']
        preview.create_text(GRID_PREVIEW_PX // 2, GRID_PREVIEW_PX // 2, text=sample,
                            fill=fill, font=font, anchor="center", tags="sample")

    bold_cb = ttk.Checkbutton(style_col, text="Bold", variable=bold_var,
                              command=_redraw_preview)
    bold_cb.pack(anchor='w', pady=(0, PAD_XS))
    shell.gate(bold_cb)

    size_row = ttk.Frame(style_col)
    size_row.pack(anchor='w', pady=(0, PAD_XS))
    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(shell.base, p)} pt",
        on_move=_redraw_preview, length=100,
        tooltip="Timer text size, a percent of the overlay size (Overlay, top "
                "of the Grids tab).",
        label_sink=sink)
    shell.gate(size_scale)

    show_row = ttk.Frame(style_col)
    show_row.pack(anchor='w', pady=(0, PAD_XS))
    show_lbl = ttk.Label(show_row, text="Show ", font=FONT_SMALL)
    show_lbl.pack(side='left')
    sink.append(show_lbl)
    show_cb = ttk.Combobox(show_row, textvariable=display_var,
                           values=[lbl for lbl, _ in _DISPLAY_LABELS],
                           state="readonly", width=8)
    show_cb.pack(side='left')
    show_cb.bind("<<ComboboxSelected>>", _redraw_preview)
    shell.gate(show_cb, live='readonly')
    add_tooltip(show_cb,
                "Elapsed = count up (1.2). Total = estimated cast length (2.5). "
                "Both = 1.2 / 2.5.")

    color_row = ttk.Frame(style_col)
    color_row.pack(anchor='w')
    color_lbl = ttk.Label(color_row, text="Color ", font=FONT_SMALL)
    color_lbl.pack(side='left')
    sink.append(color_lbl)

    def _on_color(hex_str):
        color[0] = hex_str.lstrip("#").upper()
        _redraw_preview()

    swatch = ColorSwatch(color_row, initial_color=f"#{color[0]}", on_change=_on_color)
    swatch.pack(side='left')
    add_tooltip(swatch, "Timer text color — the player and target timers share it.")

    shell.dim(*sink)

    def _after_sync(on):
        swatch.set_enabled(on)
        _redraw_preview()

    shell.on_sync = _after_sync
    shell.sync()

    def _apply():
        # One master gate drives both sides: enableP/enableT stay in the schema
        # for the generator contract, but the dialog has never split them.
        enabled = enabled_var.get()
        (pfx, pfy), (tfx, tfy) = readers['player'](), readers['target']()
        new_cfg = validate_config({
            'enabled': enabled,
            'enableP': enabled,
            'enableT': enabled,
            'playerFx': pfx,
            'playerFy': pfy,
            'targetFx': tfx,
            'targetFy': tfy,
            'bold': bold_var.get(),
            'scale': size_var.get(),
            'display': _LABEL_TO_DISPLAY.get(display_var.get(), "both"),
            'color': color[0],
        })
        app.profile_store.set_section('cast_timer', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg['enabled']:
            app_toast(app, "Cast timer saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Cast timer off — next build removes it", 'info')
        dialog.destroy()

    shell.finish(_apply, _HEIGHT)
    return dialog
