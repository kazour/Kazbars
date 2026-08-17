"""
KazBars — Cast timer dialog.

Extras-menu settings for the cast-timer overlay (the timer-only Flash overlay
showing player/target cast time): the build gate, the two baked positions, and
the shared text style. Reads/writes the profile document's `cast_timer`
section (data layer: `cast_timer.py`; the store autosaves). Positions are
stored as fractions of the game resolution; the X/Y fields display projected
px at the current resolution (the grid editor convention) so the
drag-in-game → copy-the-coordinates workflow keeps working. The build bakes
the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

Font is fixed to Arial — the only face embedded in base.swf (see cast_timer.py) —
so the dialog offers Bold rather than a family picker, and the sample preview
draws in Arial to match what the overlay will render.

Layout follows the Damage Numbers panel conventions: tip bar under the header,
a master gate row above titled cards, and every control + static label greying
with the gate (the preview sample dims too) so a disabled dialog reads
fully-off, not half-on.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .cast_timer import validate_config
from .grid_model import get_game_resolution_or_default, project_px, unproject_px
from .ui_forms import ColorSwatch, create_card, labeled_spinbox
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    CAST_TIMER_ACCENT,
    FONT_BODY,
    FONT_SMALL,
    GRID_PREVIEW_PX,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

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

    cfg = validate_config(app.profile_store.get_section('cast_timer'))
    game_w, game_h = get_game_resolution_or_default()

    dialog = tk.Toplevel(app)
    app.cast_timer_dialog = dialog
    dialog.withdraw()
    dialog.title("Cast Timer")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Cast Timer", CAST_TIMER_ACCENT, width=_WIDTH)
    create_tip_bar(dialog, "A cast-time readout for you and your target. "
                           "Apply, then Build & Install to see it.")

    # Master gate row above the cards; everything below greys when it's off.
    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the cast timer in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb,
                "Adds a cast-time readout for you and your target to the in-game "
                "overlay.")

    # Footer first so it reserves height before the cards claim the rest.
    footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
    footer.pack(fill='x', side='bottom')

    content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
    content.pack(fill='both', expand=True)

    # Everything registered here greys in step with the master gate — controls
    # by ttk state, static text by foreground — so a disabled dialog reads
    # fully-off, not half-on (the Damage Numbers convention).
    gated: list = []
    dim_labels: list[tuple[ttk.Label, str]] = []
    sink: list = []  # descriptor labels collected from labeled_spinbox rows

    def _register_dim(*labels):
        for lbl in labels:
            dim_labels.append((lbl, str(lbl.cget('foreground'))))

    pos_card = create_card(content, "Position")
    pos_card.pack(fill='x', pady=(0, PAD_ROW))
    pos_blurb = ttk.Label(
        pos_card,
        text="Where each timer first appears in-game. Shift+Ctrl+Alt\n"
             "toggles preview mode: drag a timer and the game remembers.\n"
             "X/Y here only seed a first-ever session.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
    pos_blurb.pack(anchor='w', pady=(0, PAD_XS))
    _register_dim(pos_blurb)

    # Fractions display as projected px at the current game resolution.
    px_var = tk.IntVar(value=project_px(cfg['playerFx'], game_w))
    py_var = tk.IntVar(value=project_px(cfg['playerFy'], game_h))
    tx_var = tk.IntVar(value=project_px(cfg['targetFx'], game_w))
    ty_var = tk.IntVar(value=project_px(cfg['targetFy'], game_h))
    for title, x_var, y_var in (("Player", px_var, py_var),
                                ("Target", tx_var, ty_var)):
        row = ttk.Frame(pos_card)
        row.pack(anchor='w', pady=(0, PAD_XS))
        row_lbl = ttk.Label(row, text=title, font=FONT_BODY,
                            foreground=THEME_COLORS['body'],
                            width=_POS_LABEL_W, anchor='w')
        row_lbl.pack(side='left')
        sink.append(row_lbl)
        gated.append(labeled_spinbox(row, "X ", x_var, from_=0, to=game_w,
                                     width=6, padx=(0, PAD_SMALL * 2),
                                     label_sink=sink))
        gated.append(labeled_spinbox(row, "Y ", y_var, from_=0, to=game_h,
                                     width=6, label_sink=sink))

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
    size_var = tk.IntVar(value=cfg['fontSize'])
    display_var = tk.StringVar(value=_DISPLAY_TO_LABEL.get(cfg['display'], "Both"))
    color = [cfg['color']]  # boxed so the swatch callback can rebind it

    def _redraw_preview(*_args):
        """Draw the timer text as the overlay will render it — Arial, chosen
        colour/size/weight — shrinking to fit the square so a 48px sample still
        reads as one line. Dims with the master gate so the sample never looks
        live on a disabled dialog."""
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
        fill = f"#{color[0]}" if enabled_var.get() else TK_COLORS['dim_text']
        preview.create_text(GRID_PREVIEW_PX // 2, GRID_PREVIEW_PX // 2, text=sample,
                            fill=fill, font=font, anchor="center", tags="sample")

    bold_cb = ttk.Checkbutton(style_col, text="Bold", variable=bold_var,
                              command=_redraw_preview)
    bold_cb.pack(anchor='w', pady=(0, PAD_XS))
    gated.append(bold_cb)

    size_row = ttk.Frame(style_col)
    size_row.pack(anchor='w', pady=(0, PAD_XS))
    gated.append(labeled_spinbox(
        size_row, "Font size ", size_var, from_=8, to=48, width=6,
        tooltip="Timer text size in pixels.",
        on_change=_redraw_preview, label_sink=sink))

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

    _register_dim(*sink)

    def _sync_enabled(*_):
        on = enabled_var.get()
        for widget in gated:
            widget.configure(state='normal' if on else 'disabled')
        # The combobox's live state is readonly, not normal — normal would
        # make it editable.
        show_cb.configure(state='readonly' if on else 'disabled')
        swatch.set_enabled(on)
        for lbl, normal_fg in dim_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])
        _redraw_preview()

    enable_cb.configure(command=_sync_enabled)
    _sync_enabled()

    def _read(var, default):
        # An emptied spinbox makes IntVar.get() raise before validate_config
        # can clamp it — fall back to the loaded value.
        try:
            return var.get()
        except tk.TclError:
            return default

    def _read_frac(var, frac, extent):
        # Position fields carry projected px; typed overshoot clamps to the
        # screen edge (the grid editor convention), then unprojects back to
        # the stored fraction. An emptied spinbox keeps the loaded fraction.
        try:
            px = max(0, min(int(var.get()), extent))
        except (ValueError, tk.TclError):
            return frac
        return unproject_px(px, extent)

    def _apply():
        # One master gate drives both sides: enableP/enableT stay in the schema
        # for the generator contract, but the dialog has never split them.
        enabled = enabled_var.get()
        new_cfg = validate_config({
            'enabled': enabled,
            'enableP': enabled,
            'enableT': enabled,
            'playerFx': _read_frac(px_var, cfg['playerFx'], game_w),
            'playerFy': _read_frac(py_var, cfg['playerFy'], game_h),
            'targetFx': _read_frac(tx_var, cfg['targetFx'], game_w),
            'targetFy': _read_frac(ty_var, cfg['targetFy'], game_h),
            'bold': bold_var.get(),
            'fontSize': _read(size_var, cfg['fontSize']),
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

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

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
