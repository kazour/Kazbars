"""
KazBars — Onslaught Tracker dialog.

Extras-menu settings for the in-game Onslaught Tracker (KazBarsOnslaught
stub): the build gate, then two columns. **Display**: Size (the board's text;
the alerts draw 1.6 times as large), the five displays by the anchor they
appear on — Board (Mob list, Wave timer, Hylda HP) and Alerts (Spawn alerts,
AoE warnings) — and Alert time (how long a banner stays; greyed unless Spawn
alerts or Hylda HP is on). **Watched mobs** (greyed unless Mob list or Spawn
alerts is on): the 27 catalog mobs watched in every run, named by group
under their count, Include Kuthchemes camps (greyed unless Mob list is on;
the camps' own line shows while it is ticked), and the user's own names — Add (or
Enter) only when `onslaught.custom_refusal` accepts the trimmed text, whose
reason shows as a hint while typing; each name has a delete (Cancel drops
every unapplied change). Reads/writes the profile document's `onslaught`
section (data layer: `onslaught.py`; the store autosaves). No position
fields: the board and the alerts are placed in game, in preview mode. The
build bakes the values. The shell is `extras_dialog.ExtrasShell`.
Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from . import onslaught
from .extras_dialog import ExtrasShell, raise_if_open
from .overlay_size import panel_fs
from .ui_forms import create_card, create_slider_row, size_slider
from .ui_helpers import (
    BTN_SMALL,
    FONT_BODY,
    FONT_SMALL,
    PAD_INNER,
    PAD_MICRO,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip, app_toast, debounced_callback
from .window_position import fit_window_height

_WIDTH = 720
_HEIGHT = 500

# (section key, label, what it draws) per display, by the anchor it appears on.
_BOARD = (
    ('showList', "Mob list", "The bosses, skulls and minis in view, with their health"),
    ('showWave', "Wave timer", "The wave line and the time to the next spawn"),
    ('showAlly', "Hylda HP", "The health of Valkyrie Hylda, the ally you defend in Skull Gate, "
                             "with alerts at 50 % and 25 %"),
)
_ALERTS = (
    ('showAlerts', "Spawn alerts", "A banner when a watched boss, skull or mini spawns"),
    ('showAoe', "AoE warnings", "A banner when Thugra Khotan's AoE helpers spawn in Kuthchemes"),
)


def open_onslaught_dialog(app):
    """Open or focus the Onslaught Tracker settings dialog (modal). On apply,
    persist the config — it takes effect in-game on the next Build & Install."""
    if raise_if_open(app.onslaught_dialog):
        return app.onslaught_dialog

    cfg = onslaught.validate_config(app.profile_store.get_section('onslaught'))
    shell = ExtrasShell(
        app, 'onslaught_dialog', title="Onslaught Tracker",
        tip="Bosses, waves and spawn alerts in Skull Gate and Kuthchemes. "
            "Apply, then Build & Install to see it.",
        gate_text="Include the onslaught tracker in builds",
        gate_tip="Adds the tracker to the in-game overlay; it shows itself in the "
                 "Onslaught instances only. Place the board and the alerts in "
                 "preview mode (Shift+Ctrl+Alt).",
        enabled=cfg['enabled'], width=_WIDTH)
    dialog, content, enabled_var = shell.dialog, shell.content, shell.enabled_var

    display = create_card(content, "Display")
    # Display takes its own width, Watched mobs the rest: the roster's wrap
    # (read off its width) never feeds back into the split.
    display.pack(side='left', fill='y', padx=(0, PAD_SMALL), pady=(0, PAD_ROW))
    watched = create_card(content, "Watched mobs")
    watched.pack(side='left', fill='both', expand=True, pady=(0, PAD_ROW))

    size_row = ttk.Frame(display)
    size_row.pack(anchor='w', pady=(0, PAD_XS))
    size_sink: list = []
    size_scale, size_var = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(shell.base, p)} pt text",
        tooltip="The board's text, a percent of the overlay size (Overlay, top of the "
                "Grids tab); the alerts draw 1.6 times as large.",
        label_sink=size_sink)
    shell.gate(size_scale)
    shell.dim(*size_sink)

    show_vars = {}
    for title, items in (("Board:", _BOARD), ("Alerts:", _ALERTS)):
        row = ttk.Frame(display)
        row.pack(anchor='w', pady=PAD_MICRO)
        lbl = ttk.Label(row, text=title, font=FONT_BODY, foreground=THEME_COLORS['body'], width=7)
        lbl.pack(side='left')
        shell.dim(lbl)
        for key, text, tip in items:
            var = tk.BooleanVar(value=cfg[key])
            cb = ttk.Checkbutton(row, text=text, variable=var, command=shell.sync)
            cb.pack(side='left', padx=(0, PAD_SMALL))
            add_tooltip(cb, tip)
            show_vars[key] = var
            shell.gate(cb)

    def _alerts_on():
        return show_vars['showAlerts'].get() or show_vars['showAlly'].get()

    def _list_or_alerts():
        return show_vars['showList'].get() or show_vars['showAlerts'].get()

    list_on = show_vars['showList'].get

    alert_sink: list = []
    alert_scale, alert_label = create_slider_row(
        display, "Alert time:", *onslaught.ALERT_SECONDS, cfg['alertSeconds'], " s",
        on_drag=lambda v: alert_label.configure(text=f"{round(float(v))} s"),
        label_sink=alert_sink)
    add_tooltip(alert_scale, "How long a banner stays: a spawn alert, or Hylda's 50 % and 25 % alerts")
    shell.gate(alert_scale, rule=_alerts_on)
    shell.dim(*alert_sink, rule=_alerts_on)

    # ---- Watched mobs --------------------------------------------------------
    always_n = sum(1 for r in onslaught.ROWS if r.kind != onslaught.CAMP)
    always = ttk.Label(watched, text=f"{always_n} always", font=FONT_SMALL,
                       foreground=THEME_COLORS['muted'])
    always.pack(anchor='w')
    shell.dim(always, rule=_list_or_alerts)
    hint = ttk.Label(watched, text="Mob list or Spawn alerts reads these.", font=FONT_SMALL,
                     foreground=THEME_COLORS['muted'])
    # The names themselves, one wrapped line per group in catalog order; the
    # camps' line (the last group) only while they are included.
    roster = ttk.Frame(watched)
    roster.pack(fill='x')
    roster_lines = []
    for group in onslaught.GROUPS:
        rows = [r for r in onslaught.ROWS if r.group == group]
        line = ttk.Label(roster, text=f"{group}: {', '.join(r.name for r in rows)}",
                         font=FONT_SMALL, foreground=THEME_COLORS['muted'], justify='left')
        roster_lines.append(line)
        if rows[0].kind == onslaught.CAMP:
            camp_line = line
            shell.dim(line, rule=list_on)
        else:
            line.pack(anchor='w')
            shell.dim(line, rule=_list_or_alerts)

    def _refit():
        # The dialog follows its content (the roster's lines, the user's
        # names) about its own centre; _HEIGHT stays the floor so a short
        # list keeps its room.
        if dialog.winfo_ismapped():
            fit_window_height(dialog, _WIDTH, _HEIGHT, about_centre=True)

    def _wrap_to(width):
        for line in roster_lines:
            line.configure(wraplength=width)

    def _wrap():
        if not roster.winfo_exists():  # closed while the debounce waited
            return
        width = roster.winfo_width()
        if width > 1 and width != int(roster_lines[0].cget('wraplength')):
            _wrap_to(width)
            _refit()

    roster.bind('<Configure>', debounced_callback(dialog, 30, lambda *_: _wrap()))

    camps_var = tk.BooleanVar(value=cfg['camps'])

    def _show_camps():
        if camps_var.get():
            camp_line.pack(anchor='w')  # the last group: appended is in catalog order
        else:
            camp_line.pack_forget()
        _refit()

    camps_cb = ttk.Checkbutton(watched, text="Include Kuthchemes camps", variable=camps_var,
                               command=_show_camps)
    camps_cb.pack(anchor='w', pady=(PAD_XS, PAD_XS))
    _show_camps()
    add_tooltip(camps_cb, "Listed on the board, never alerted: " + ", ".join(
        r.name for r in onslaught.ROWS if r.kind == onslaught.CAMP))
    shell.gate(camps_cb, rule=list_on)

    own_row = ttk.Frame(watched)
    own_row.pack(fill='x')
    own_lbl = ttk.Label(own_row, text="Your own names:", font=FONT_BODY,
                        foreground=THEME_COLORS['body'])
    own_lbl.pack(side='left')
    shell.dim(own_lbl, rule=_list_or_alerts)
    name_var = tk.StringVar()
    name_entry = ttk.Entry(own_row, textvariable=name_var, width=24)
    name_entry.pack(side='left', padx=PAD_XS)
    add_tooltip(name_entry, "A mob's exact in-game name, watched as a mini")
    shell.gate(name_entry, rule=_list_or_alerts)
    add_btn = ttk.Button(own_row, text="Add", width=BTN_SMALL, command=lambda: _add())
    add_btn.pack(side='left')
    reason = ttk.Label(watched, font=FONT_SMALL, foreground=THEME_COLORS['muted'])
    reason.pack(anchor='w')
    names_frame = ttk.Frame(watched)
    names_frame.pack(fill='both', expand=True, pady=(PAD_XS, 0))
    custom = list(cfg['custom'])
    name_rows: list = []  # (label, delete button) per custom name

    def _refusal():
        return onslaught.custom_refusal(name_var.get().strip(), custom)

    def _paint_names():
        """The names' rows follow the gate and the displays that read them."""
        live = enabled_var.get() and _list_or_alerts()
        for lbl, btn in name_rows:
            lbl.configure(foreground=THEME_COLORS['body'] if live else TK_COLORS['dim_text'])
            btn.configure(state='normal' if live else 'disabled')

    def _draw_names():
        for w in names_frame.winfo_children():
            w.destroy()
        name_rows.clear()
        for name in custom:
            row = ttk.Frame(names_frame)
            row.pack(fill='x', pady=PAD_MICRO)
            lbl = ttk.Label(row, text=name, font=FONT_BODY)
            lbl.pack(side='left')
            btn = ttk.Button(row, text="×", width=2, bootstyle='secondary',  # type: ignore[call-arg]
                             command=lambda n=name: _delete(n))
            btn.pack(side='right')
            add_tooltip(btn, f"Stop watching {name}")
            name_rows.append((lbl, btn))
        _paint_names()

    def _names_changed():
        # A name added or removed: the list's rows, then the height.
        _draw_names()
        _refit()

    def _add(_e=None):
        if _refusal() is None:
            custom.append(name_var.get().strip())
            name_var.set("")
            _names_changed()
        return 'break'

    def _delete(name):
        custom.remove(name)
        _names_changed()

    def _on_name_typed(*_):
        refusal = _refusal()
        reason.configure(text=(refusal or "") if name_var.get().strip() else "")
        live = enabled_var.get() and _list_or_alerts() and refusal is None
        add_btn.configure(state='normal' if live else 'disabled')

    name_var.trace_add('write', _on_name_typed)
    name_entry.bind('<Return>', _add)

    def _after_sync(on):
        hinted = bool(hint.winfo_manager())
        if on and not _list_or_alerts():
            hint.pack(anchor='w', after=always)
        else:
            hint.pack_forget()
        _on_name_typed()
        _paint_names()
        if bool(hint.winfo_manager()) != hinted:  # a line came or went; a recolour never re-fits
            _refit()

    shell.on_sync = _after_sync
    _draw_names()
    shell.sync()

    def _apply():
        new_cfg = onslaught.validate_config({
            'enabled': enabled_var.get(),
            'scale': size_var.get(),
            **{key: var.get() for key, var in show_vars.items()},
            'alertSeconds': round(alert_scale.get()),
            'camps': camps_var.get(),
            'custom': custom,
        })
        app.profile_store.set_section('onslaught', new_cfg)
        app.grids_panel.refresh_extras_shortcuts()
        if new_cfg == cfg:
            app_toast(app, "No changes to apply", 'info')
        elif onslaught.ships(new_cfg):
            app_toast(app, "Onslaught tracker saved — Build & Install to apply", 'success')
        elif new_cfg['enabled']:
            app_toast(app, "Onslaught tracker shows nothing — the next build leaves it out", 'warning')
        else:
            app_toast(app, "Onslaught tracker off — next build removes it", 'info')
        dialog.destroy()

    # The roster's first wrap, before the card has a width to read: what
    # Display leaves, less the paddings around it — content's sides (PAD_TAB
    # each), the gap after Display (PAD_SMALL), the card's own (PAD_INNER
    # each). Its <Configure> then re-wraps to the width the card really got.
    dialog.update_idletasks()
    _wrap_to(_WIDTH - 2 * PAD_TAB - PAD_SMALL - display.winfo_reqwidth() - 2 * PAD_INNER)
    shell.finish(_apply, enter_except=name_entry, min_height=_HEIGHT)
    return dialog
