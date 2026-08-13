"""
KazBars — Cast timer dialog.

Extras-menu settings for the cast-timer overlay (the timer-only Flash overlay
showing player/target cast time): the build gate, the two baked positions, and
the shared text style. Persists machine-local in prefs.json under `cast_timer`
(data layer: `cast_timer.py`); the build bakes the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

Font is fixed to Arial — the only face embedded in base.swf (see cast_timer.py) —
so the dialog offers Bold rather than a family picker, and the sample preview
draws in Arial to match what the overlay will render.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .cast_timer import validate_config
from .grid_model import SCREEN_MAX_X, SCREEN_MAX_Y
from .ui_forms import ColorSwatch, labeled_spinbox
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_SMALL,
    CAST_TIMER_ACCENT,
    FONT_SECTION,
    FONT_SMALL,
    GRID_PREVIEW_PX,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

_WIDTH = 400
_HEIGHT = 560

_DISPLAY_LABELS = (("Elapsed", "elapsed"), ("Total", "total"), ("Both", "both"))
_DISPLAY_TO_LABEL = {v: k for k, v in _DISPLAY_LABELS}
_LABEL_TO_DISPLAY = dict(_DISPLAY_LABELS)
_SAMPLES = {"elapsed": "1.2", "total": "2.5", "both": "1.2 / 2.5"}


def open_cast_timer_dialog(app):
    """Open or focus the cast-timer settings dialog (modal). On apply, persist
    the config — it takes effect in-game on the next Build & Install."""
    existing = app.cast_timer_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.settings.get('cast_timer'))

    dialog = tk.Toplevel(app)
    app.cast_timer_dialog = dialog
    dialog.withdraw()
    dialog.title("Cast Timer")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Cast Timer", CAST_TIMER_ACCENT, width=_WIDTH)

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    enable_cb = ttk.Checkbutton(content, text="Include the cast timer in builds",
                                variable=enabled_var)
    enable_cb.pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
    add_tooltip(enable_cb,
                "Adds a cast-time readout for you and your target to the in-game "
                "overlay. Takes effect on the next Build & Install.")

    ttk.Label(content,
              text="Where each timer first appears in-game. Shift+Ctrl+Alt\n"
                   "toggles preview mode: drag a timer and the game remembers.\n"
                   "X/Y here only seed a first-ever session.",
              font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left'
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))

    px_var = tk.IntVar(value=cfg['playerX'])
    py_var = tk.IntVar(value=cfg['playerY'])
    tx_var = tk.IntVar(value=cfg['targetX'])
    ty_var = tk.IntVar(value=cfg['targetY'])
    for title, x_var, y_var in (("Player position", px_var, py_var),
                                ("Target position", tx_var, ty_var)):
        ttk.Label(content, text=title,
                  font=FONT_SECTION, foreground=THEME_COLORS['heading']
                  ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
        row = ttk.Frame(content)
        row.pack(anchor='w', pady=(0, PAD_SMALL))
        labeled_spinbox(row, "X ", x_var, from_=0, to=SCREEN_MAX_X,
                        width=6, padx=(0, PAD_SMALL * 2))
        labeled_spinbox(row, "Y ", y_var, from_=0, to=SCREEN_MAX_Y, width=6)

    ttk.Label(content, text="Text",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))

    # Style controls on the left, a live sample of what they produce on the right.
    text_row = ttk.Frame(content)
    text_row.pack(fill='x', pady=(0, PAD_SMALL))
    style_col = ttk.Frame(text_row)
    style_col.pack(side='left', fill='x', expand=True)
    preview = tk.Canvas(text_row, width=GRID_PREVIEW_PX, height=GRID_PREVIEW_PX,
                        bg=TK_COLORS['bg'], highlightthickness=0)
    preview.pack(side='right', padx=(PAD_XS, 0))

    bold_var = tk.BooleanVar(value=cfg['bold'])
    size_var = tk.IntVar(value=cfg['fontSize'])
    display_var = tk.StringVar(value=_DISPLAY_TO_LABEL.get(cfg['display'], "Both"))
    color = [cfg['color']]  # boxed so the swatch callback can rebind it

    def _redraw_preview(*_args):
        """Draw the timer text as the overlay will render it — Arial, chosen
        colour/size/weight — shrinking to fit the square so a 48px sample still
        reads as one line."""
        preview.delete("sample")
        sample = _SAMPLES.get(_LABEL_TO_DISPLAY.get(display_var.get(), "both"), "1.2 / 2.5")
        try:
            size = int(size_var.get())
        except (ValueError, tk.TclError):
            size = cfg['fontSize']
        font = tkfont.Font(family="Arial", size=size,
                           weight="bold" if bold_var.get() else "normal")
        while size > 7 and font.measure(sample) > GRID_PREVIEW_PX - 8:
            size -= 1
            font.configure(size=size)
        preview.create_text(GRID_PREVIEW_PX // 2, GRID_PREVIEW_PX // 2, text=sample,
                            fill=f"#{color[0]}", font=font, anchor="center", tags="sample")

    ttk.Checkbutton(style_col, text="Bold", variable=bold_var,
                    command=_redraw_preview).pack(anchor='w', pady=(0, PAD_XS))

    size_row = ttk.Frame(style_col)
    size_row.pack(anchor='w', pady=(0, PAD_XS))
    labeled_spinbox(size_row, "Font size ", size_var, from_=8, to=48, width=6,
                    tooltip="Timer text size in pixels, baked in at build time.",
                    on_change=_redraw_preview)

    show_row = ttk.Frame(style_col)
    show_row.pack(anchor='w', pady=(0, PAD_XS))
    ttk.Label(show_row, text="Show ", font=FONT_SMALL).pack(side='left')
    show_cb = ttk.Combobox(show_row, textvariable=display_var,
                           values=[lbl for lbl, _ in _DISPLAY_LABELS],
                           state="readonly", width=8)
    show_cb.pack(side='left')
    show_cb.bind("<<ComboboxSelected>>", _redraw_preview)
    add_tooltip(show_cb,
                "Elapsed = count up (1.2). Total = estimated cast length (2.5). "
                "Both = 1.2 / 2.5.")

    color_row = ttk.Frame(style_col)
    color_row.pack(anchor='w')
    ttk.Label(color_row, text="Color ", font=FONT_SMALL).pack(side='left')

    def _on_color(hex_str):
        color[0] = hex_str.lstrip("#").upper()
        _redraw_preview()

    swatch = ColorSwatch(color_row, initial_color=f"#{color[0]}", on_change=_on_color)
    swatch.pack(side='left')
    add_tooltip(swatch, "Timer text color — the player and target timers share it.")

    _redraw_preview()

    btns = ttk.Frame(content)
    btns.pack(fill='x', side='bottom', pady=(PAD_SMALL, 0))

    def _read(var, default):
        # An emptied spinbox makes IntVar.get() raise before validate_config
        # can clamp it — fall back to the loaded value.
        try:
            return var.get()
        except tk.TclError:
            return default

    def _apply():
        # One master gate drives both sides: enableP/enableT stay in the schema
        # for the generator contract, but the dialog has never split them.
        enabled = enabled_var.get()
        new_cfg = validate_config({
            'enabled': enabled,
            'enableP': enabled,
            'enableT': enabled,
            'playerX': _read(px_var, cfg['playerX']),
            'playerY': _read(py_var, cfg['playerY']),
            'targetX': _read(tx_var, cfg['targetX']),
            'targetY': _read(ty_var, cfg['targetY']),
            'bold': bold_var.get(),
            'fontSize': _read(size_var, cfg['fontSize']),
            'display': _LABEL_TO_DISPLAY.get(display_var.get(), "both"),
            'color': color[0],
        })
        app.settings.set('cast_timer', new_cfg)
        app.settings.save()
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg['enabled']:
            app_toast(app, "Cast timer saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Cast timer off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(btns, text="Apply", bootstyle="success",
               command=_apply, width=BTN_SMALL).pack(side='right')
    ttk.Button(btns, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_SMALL
               ).pack(side='right', padx=(0, PAD_XS))

    # withdraw → build → restore → deiconify, then keep the drag: the dialog
    # reopens where the user left it (clamped to a live monitor), like its two
    # siblings. Staggered past both of them on a first-launch centre.
    restore_window_position(dialog, 'cast_timer_settings', _WIDTH, _HEIGHT, app,
                            resizable=False, offset=(60, 60))
    bind_window_position_save(dialog, 'cast_timer_settings', save_size=False)
    dialog.deiconify()

    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    # The global one-shot dark-titlebar patch can miss a Toplevel built this
    # late, so re-assert it on the dialog's own map (as damageinfo_colors_panel).
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
