"""
KazBars — Target inspect panel dialog.

Extras-menu settings for the in-game target inspect panel (KazBarsInspect
stub): the build gate, the baked default position, the baked font size, and
the start-collapsed flag. It also hosts two settings that are not the inspect
panel's own, for the same "these belong together" reason: the buff-discovery
console's build gate (flat prefs key `build_console`), and the text size the
four in-game panels share (flat prefs key `panel_font_size`) — the console and
the preview control panel have no dialog of their own to host either.
The panel's own settings read/write the profile document's `inspect` section
(data layer: `inspect.py`; the store autosaves); the two ride-along settings
stay machine-local prefs keys, so Apply is a two-store write. Positions are
stored as fractions of the game resolution; the X/Y fields display projected
px at the current resolution (the grid editor convention) so the
drag-in-game → copy-the-coordinates workflow keeps working. The build bakes
the values into the generated SWF.
Functions take the KazBarsApp instance as first arg.

Layout follows the Damage Numbers panel conventions: tip bar under the header,
a master gate row above titled cards, and the inspect panel's own controls
greying with the gate. The shared text size and the console gate stay live —
they are independent settings that only ride along on this dialog's Apply.
"""

import tkinter as tk
from tkinter import ttk

from .grid_model import get_game_resolution_or_default, project_px, unproject_px
from .inspect import validate_config
from .ui_forms import create_card, labeled_spinbox
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
from .window_position import bind_window_position_save, restore_window_position

_WIDTH = 470
_HEIGHT = 640


def open_inspect_dialog(app):
    """Open or focus the inspect-panel settings dialog (modal). On apply,
    persist the config — it takes effect in-game on the next Build & Install."""
    existing = app.inspect_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = validate_config(app.profile_store.get_section('inspect'))
    game_w, game_h = get_game_resolution_or_default()

    dialog = tk.Toplevel(app)
    app.inspect_dialog = dialog
    dialog.withdraw()
    dialog.title("Inspect Panel")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Inspect Panel",
                         MODULE_COLORS['grids'], width=_WIDTH)
    create_tip_bar(dialog, "Your target's combat sheet, in-game. "
                           "Apply, then Build & Install to see it.")

    # Master gate row above the cards; the inspect panel's own controls grey
    # when it's off (the shared size + console are independent and stay live).
    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the inspect panel in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb,
                "Adds a target inspect panel to the in-game overlay: target "
                "something and see its combat sheet — armor, protections, "
                "crit, critigation and more.")

    # Footer first so it reserves height before the cards claim the rest.
    footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
    footer.pack(fill='x', side='bottom')

    content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
    content.pack(fill='both', expand=True)

    # Everything registered here greys in step with the master gate — controls
    # by ttk state, static text by foreground — so a disabled panel reads
    # fully-off, not half-on (the Damage Numbers convention).
    gated: list = []
    dim_labels: list[tuple[ttk.Label, str]] = []
    sink: list = []  # descriptor labels collected from gated labeled_spinbox rows

    def _register_dim(*labels):
        for lbl in labels:
            dim_labels.append((lbl, str(lbl.cget('foreground'))))

    pos_card = create_card(content, "Position")
    pos_card.pack(fill='x', pady=(0, PAD_ROW))
    pos_blurb = ttk.Label(
        pos_card,
        text="Where the panel first appears in-game. Drag its name strip\n"
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

    size_card = create_card(content, "Text size")
    size_card.pack(fill='x', pady=(0, PAD_ROW))
    ttk.Label(
        size_card,
        text="One size for all four in-game panels — stopwatch, inspect panel,\n"
             "buff console and control panel. It's set here because the last two\n"
             "have no dialog of their own.",
        font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left'
    ).pack(anchor='w', pady=(0, PAD_XS))

    shared_before = app.settings.get('panel_font_size')
    shared_var = tk.IntVar(value=shared_before)
    shared_row = ttk.Frame(size_card)
    shared_row.pack(anchor='w', pady=(0, PAD_XS))
    shared_spin = labeled_spinbox(shared_row, "All panels ", shared_var,
                                  from_=8, to=48, width=6)
    add_tooltip(shared_spin,
                "Each panel scales as one piece, collapsed bars included, so they "
                "keep matching at any size.")

    # fontSize is None when the panel follows the shared size. The spinbox still
    # shows a number so unticking the box has somewhere to start from.
    follow_var = tk.BooleanVar(value=cfg['fontSize'] is None)
    follow_cb = ttk.Checkbutton(size_card, text="Use the shared size for this panel",
                                variable=follow_var)
    follow_cb.pack(anchor='w', pady=(0, PAD_XS))
    add_tooltip(follow_cb,
                "Untick to make the inspect panel bigger or smaller than the rest.")
    gated.append(follow_cb)

    size_var = tk.IntVar(value=shared_before if cfg['fontSize'] is None else cfg['fontSize'])
    size_row = ttk.Frame(size_card)
    size_row.pack(anchor='w')
    size_spin = labeled_spinbox(size_row, "Inspect panel only ", size_var,
                                from_=8, to=48, width=6, label_sink=sink)
    add_tooltip(size_spin,
                "This panel's own size, used instead of the shared one.")

    def _sync_size_override(*_):
        on = enabled_var.get() and not follow_var.get()
        size_spin.configure(state='normal' if on else 'disabled')

    follow_var.trace_add('write', _sync_size_override)

    behavior_card = create_card(content, "Behavior")
    behavior_card.pack(fill='x', pady=(0, PAD_ROW))
    collapsed_var = tk.BooleanVar(value=cfg['startCollapsed'])
    collapsed_cb = ttk.Checkbutton(behavior_card, text="Start collapsed (name strip only)",
                                   variable=collapsed_var)
    collapsed_cb.pack(anchor='w')
    add_tooltip(collapsed_cb,
                "The panel loads folded to just its name strip — click its "
                "+ button in-game to expand.")
    gated.append(collapsed_cb)

    sections_card = create_card(content, "Sections")
    sections_card.pack(fill='x', pady=(0, PAD_ROW))
    pvp_var = tk.BooleanVar(value=cfg['showPvp'])
    pvp_cb = ttk.Checkbutton(sections_card, text="Show the PvP section",
                             variable=pvp_var)
    pvp_cb.pack(anchor='w', pady=(0, PAD_XS))
    add_tooltip(pvp_cb,
                "PvP armor, protections, spell damage, combat rating and "
                "kills / deaths — shown on player targets only.")
    gated.append(pvp_cb)
    perks_var = tk.BooleanVar(value=cfg['showPerks'])
    perks_cb = ttk.Checkbutton(sections_card, text="Track slotted perks",
                               variable=perks_var)
    perks_cb.pack(anchor='w')
    add_tooltip(perks_cb,
                "Adds a row of buff icons at the bottom of the panel showing "
                "the AA perks detected on a player target — each player can "
                "slot up to six.")
    gated.append(perks_cb)

    console_card = create_card(content, "Console")
    console_card.pack(fill='x', pady=(0, PAD_ROW))
    console_before = bool(app.settings.get('build_console', False))
    console_var = tk.BooleanVar(value=console_before)
    console_cb = ttk.Checkbutton(console_card,
                                 text="Include the buff-discovery console in builds",
                                 variable=console_var)
    console_cb.pack(anchor='w')
    add_tooltip(console_cb,
                "Adds an in-game window that logs every buff and debuff on you "
                "and your target with its buff ID — the ID you need to track "
                "something the database doesn't carry. Opens in preview mode "
                "(Shift+Ctrl+Alt).")

    _register_dim(*sink)

    def _sync_enabled(*_):
        on = enabled_var.get()
        for widget in gated:
            widget.configure(state='normal' if on else 'disabled')
        for lbl, normal_fg in dim_labels:
            lbl.configure(foreground=normal_fg if on else TK_COLORS['dim_text'])
        # The follow gate re-applies on top of the master (as the exemplar's
        # shadow gate), covering the size spinbox in both directions.
        _sync_size_override()

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
        shared = _read(shared_var, shared_before)
        new_cfg = validate_config({
            'enabled': enabled_var.get(),
            'fx': _read_frac(x_var, cfg['fx'], game_w),
            'fy': _read_frac(y_var, cfg['fy'], game_h),
            # Checked means "no opinion" — never the number left in the disabled
            # spinbox, or unticking once would freeze the panel off the shared value.
            'fontSize': None if follow_var.get() else _read(size_var, shared),
            'startCollapsed': collapsed_var.get(),
            'showPvp': pvp_var.get(),
            'showPerks': perks_var.get(),
        })
        # Two stores on one Apply: the ride-along settings are machine-local
        # prefs, the panel's own config is a profile section (autosaved).
        app.settings.set('panel_font_size', shared)
        app.settings.set('build_console', console_var.get())
        app.settings.save()
        app.profile_store.set_section('inspect', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        # Three separate settings live in this dialog, so name whichever moved
        # rather than reporting an inspect save that isn't one — and a bare
        # Apply with nothing moved says so instead of claiming a console save.
        if new_cfg != cfg:
            if new_cfg['enabled']:
                app_toast(app, "Inspect panel saved — Build & Install to apply", 'success')
            else:
                app_toast(app, "Inspect panel off — next build removes it", 'info')
        elif shared != shared_before:
            app_toast(app, "Panel text size saved — Build & Install to apply", 'success')
        elif console_var.get() != console_before:
            app_toast(app, "Console saved — Build & Install to apply", 'success')
        else:
            app_toast(app, "No changes to apply", 'info')
        dialog.destroy()

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

    # withdraw → build → restore → deiconify, then keep the drag: the dialog
    # reopens where the user left it (clamped to a live monitor), like the
    # panels it configures. Staggered off the stopwatch dialog's first-launch
    # centre so opening both doesn't stack them exactly.
    restore_window_position(dialog, 'inspect_settings', _WIDTH, _HEIGHT, app,
                            resizable=False, offset=(30, 30))
    bind_window_position_save(dialog, 'inspect_settings', save_size=False)
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
