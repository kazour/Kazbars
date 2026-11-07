"""
KazBars — In-game stopwatch dialog.

Extras-menu settings for the in-game stopwatch panel (KazBarsStopwatch stub):
the build gate, the baked default position, its Size (a percent of the
profile's overlay size, hinted in pt) and the start-collapsed flag.
Reads/writes the profile document's `stopwatch` section (data layer:
`stopwatch.py`; the store autosaves). Positions are stored as fractions of the
game resolution; the X/Y fields display projected px at the current resolution
(the grid editor convention). The build bakes the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

Layout follows the Damage Numbers panel conventions: tip bar under the header,
a master gate row above titled cards, and every control + static label greying
with the gate so a disabled dialog reads fully-off, not half-on.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import get_game_resolution_or_default, project_px, unproject_px
from .overlay_size import panel_fs
from .stopwatch import validate_config
from .ui_forms import create_card, labeled_spinbox, size_slider
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import center_on_parent

_WIDTH = 470
_HEIGHT = 380


def open_stopwatch_dialog(app):
    """Open or focus the stopwatch settings dialog (modal). On apply, persist
    the config — it takes effect in-game on the next Build & Install."""
    existing = app.stopwatch_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.profile_store.get_section('stopwatch'))
    game_w, game_h = get_game_resolution_or_default()

    dialog = tk.Toplevel(app)
    app.stopwatch_dialog = dialog
    dialog.withdraw()
    dialog.title("Stopwatch")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Stopwatch",
                         MODULE_COLORS['grids'], width=_WIDTH)
    create_tip_bar(dialog, "A Start / Pause / Reset stopwatch in-game. "
                           "Apply, then Build & Install to see it.")

    # Master gate row above the cards; everything below greys when it's off.
    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the stopwatch in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb,
                "Adds a Start / Pause / Reset stopwatch panel to the in-game "
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
        text="Where the panel first appears in-game. Drag its title bar\n"
             "to move it — the game remembers, across relogs and restarts.\n"
             "X/Y here only seed a first-ever session.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
    pos_blurb.pack(anchor='w', pady=(0, PAD_XS))
    _register_dim(pos_blurb)

    # Fractions display as projected px at the current game resolution.
    x_var = tk.IntVar(value=project_px(cfg['fx'], game_w))
    y_var = tk.IntVar(value=project_px(cfg['fy'], game_h))
    pos_row = ttk.Frame(pos_card)
    pos_row.pack(anchor='w')
    gated.append(labeled_spinbox(pos_row, "X ", x_var, from_=0, to=game_w,
                                 width=6, padx=(0, PAD_SMALL * 2), label_sink=sink))
    gated.append(labeled_spinbox(pos_row, "Y ", y_var, from_=0, to=game_h,
                                 width=6, label_sink=sink))

    size_card = create_card(content, "Size")
    size_card.pack(fill='x', pady=(0, PAD_ROW))
    base = app.profile_store.get_section('overlay')['size']
    size_row = ttk.Frame(size_card)
    size_row.pack(anchor='w')
    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(base, p)} pt text",
        tooltip="A percent of the overlay size (Overlay, top of the Grids tab). "
                "The whole panel scales with it, collapsed bar included.",
        label_sink=sink)
    gated.append(size_scale)

    behavior_card = create_card(content, "Behavior")
    behavior_card.pack(fill='x', pady=(0, PAD_ROW))
    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(behavior_card, text="Start collapsed (title bar only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w')
    add_tooltip(collapsed_cb,
                "The panel loads as just its title bar — click its + button "
                "in-game to expand.")
    gated.append(collapsed_cb)

    _register_dim(*sink)

    def _sync_enabled(*_):
        on = enabled_var.get()
        for widget in gated:
            widget.configure(state='normal' if on else 'disabled')
        for lbl, normal_fg in dim_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])

    enable_cb.configure(command=_sync_enabled)
    _sync_enabled()

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
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'fx': _read_frac(x_var, cfg['fx'], game_w),
            'fy': _read_frac(y_var, cfg['fy'], game_h),
            'scale': size_var.get(),
            'startCollapsed': collapsed_var.get(),
        })
        app.profile_store.set_section('stopwatch', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg['enabled']:
            app_toast(app, "Stopwatch saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "Stopwatch off — next build removes it", 'info')
        dialog.destroy()

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

    center_on_parent(dialog, app, _WIDTH, _HEIGHT)
    dialog.deiconify()

    dialog.bind("<Return>", lambda e: _apply())
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    # The global one-shot dark-titlebar patch can miss a Toplevel built this
    # late, so re-assert it on the dialog's own map (as damageinfo_colors_panel).
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
