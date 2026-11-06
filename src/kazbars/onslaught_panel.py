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
reason shows as a hint while typing; each name has a delete with an Undo
toast. Reads/writes the profile document's `onslaught` section (data layer:
`onslaught.py`; the store autosaves). No position fields: the board and the
alerts are placed in game, in preview mode. The build bakes the values.
Functions take the KazBarsApp instance as first arg.
"""

import tkinter as tk
from tkinter import ttk

from . import onslaught
from .overlay_size import panel_fs
from .ui_forms import create_card, create_slider_row, size_slider
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    BTN_SMALL,
    FONT_BODY,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_MICRO,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast, debounced_callback
from .window_position import center_on_parent, fit_window_height

_WIDTH = 720
_HEIGHT = 500
# The roster's first wrap, before the card has a width to read: about the
# Watched mobs card's inner width at the stock font (the roster's <Configure>
# then sets the real one).
_ROSTER_WRAP = 360

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
    existing = app.onslaught_dialog
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    cfg = onslaught.validate_config(app.profile_store.get_section('onslaught'))

    dialog = tk.Toplevel(app)
    app.onslaught_dialog = dialog
    dialog.withdraw()
    dialog.title("Onslaught Tracker")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    create_dialog_header(dialog, "Onslaught Tracker", MODULE_COLORS['grids'], width=_WIDTH)
    create_tip_bar(dialog, "Bosses, waves and spawn alerts in Skull Gate and Kuthchemes. "
                           "Apply, then Build & Install to see it.")

    enabled_var = tk.BooleanVar(value=cfg['enabled'])
    master = ttk.Frame(dialog)
    master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
    enable_cb = ttk.Checkbutton(master, text="Include the onslaught tracker in builds",
                                variable=enabled_var)
    enable_cb.pack(side='left')
    add_tooltip(enable_cb, "Adds the tracker to the in-game overlay; it shows itself in the "
                           "Onslaught instances only. Place the board and the alerts in "
                           "preview mode (Shift+Ctrl+Alt).")

    footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
    footer.pack(fill='x', side='bottom')
    content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
    content.pack(fill='both', expand=True)

    # (widget, rule) pairs: the rule says whether the widget is live on top of
    # the master gate, so the whole dialog greys from one place.
    controls: list = []
    labels: list = []

    display = create_card(content, "Display")
    display.pack(side='left', fill='both', expand=True, padx=(0, PAD_SMALL), pady=(0, PAD_ROW))
    watched = create_card(content, "Watched mobs")
    watched.pack(side='left', fill='both', expand=True, pady=(0, PAD_ROW))

    base = app.profile_store.get_section('overlay')['size']
    size_row = ttk.Frame(display)
    size_row.pack(anchor='w', pady=(0, PAD_XS))
    size_sink: list = []
    size_scale, size_var, _ = size_slider(
        size_row, cfg['scale'], lambda p: f"{panel_fs(base, p)} pt text",
        tooltip="The board's text, a percent of the overlay size (Overlay, top of the "
                "Grids tab); the alerts draw 1.6 times as large.",
        label_sink=size_sink)
    controls.append((size_scale, None))
    labels.extend((lbl, None) for lbl in size_sink)

    show_vars = {}
    for title, items in (("Board:", _BOARD), ("Alerts:", _ALERTS)):
        row = ttk.Frame(display)
        row.pack(anchor='w', pady=PAD_MICRO)
        lbl = ttk.Label(row, text=title, font=FONT_BODY, foreground=THEME_COLORS['body'], width=7)
        lbl.pack(side='left')
        labels.append((lbl, None))
        for key, text, tip in items:
            var = tk.BooleanVar(value=cfg[key])
            cb = ttk.Checkbutton(row, text=text, variable=var, command=lambda: _sync())
            cb.pack(side='left', padx=(0, PAD_SMALL))
            add_tooltip(cb, tip)
            show_vars[key] = var
            controls.append((cb, None))

    alert_sink: list = []
    alert_scale, alert_label = create_slider_row(
        display, "Alert time:", 3, 15, cfg['alertSeconds'], " s",
        on_drag=lambda v: alert_label.configure(text=f"{round(float(v))} s"),
        value_width=5, label_sink=alert_sink)

    def _alerts_on():
        return show_vars['showAlerts'].get() or show_vars['showAlly'].get()

    def _list_or_alerts():
        return show_vars['showList'].get() or show_vars['showAlerts'].get()

    add_tooltip(alert_scale, "How long a banner stays: a spawn alert, or Hylda's 50 % and 25 % alerts")
    controls.append((alert_scale, _alerts_on))
    labels.extend((lbl, _alerts_on) for lbl in alert_sink)

    # ---- Watched mobs --------------------------------------------------------
    always_n = sum(1 for r in onslaught.ROWS if r.kind != onslaught.CAMP)
    always = ttk.Label(watched, text=f"{always_n} always", font=FONT_SMALL,
                       foreground=THEME_COLORS['muted'])
    always.pack(anchor='w')
    labels.append((always, _list_or_alerts))
    hint = ttk.Label(watched, text="Mob list or Spawn alerts reads these.", font=FONT_SMALL,
                     foreground=THEME_COLORS['muted'])
    # The names themselves, one wrapped line per group in catalog order; the
    # camps' line only while they are included.
    roster = ttk.Frame(watched)
    roster.pack(fill='x')
    roster_lines = []
    camp_line = None
    for group in onslaught.GROUPS:
        rows = [r for r in onslaught.ROWS if r.group == group]
        line = ttk.Label(roster, text=f"{group}: {', '.join(r.name for r in rows)}",
                         font=FONT_SMALL, foreground=THEME_COLORS['muted'],
                         wraplength=_ROSTER_WRAP, justify='left')
        roster_lines.append(line)
        if rows[0].kind == onslaught.CAMP:
            camp_line = line
            labels.append((line, lambda: show_vars['showList'].get()))
        else:
            line.pack(anchor='w')
            labels.append((line, _list_or_alerts))

    def _refit():
        # The card grows with its lines (and the user's names); _HEIGHT stays
        # the floor so a short list keeps its room.
        if dialog.winfo_ismapped():
            fit_window_height(dialog, _WIDTH, _HEIGHT)

    def _wrap():
        if not roster.winfo_exists():  # closed while the debounce waited
            return
        width = roster.winfo_width()
        if width > 1 and width != int(roster_lines[0].cget('wraplength')):
            for line in roster_lines:
                line.configure(wraplength=width)
            _refit()

    roster.bind('<Configure>', debounced_callback(dialog, 30, lambda *_: _wrap()))

    camps_var = tk.BooleanVar(value=cfg['camps'])

    def _show_camps():
        if camps_var.get():
            camp_line.pack(anchor='w')
        else:
            camp_line.pack_forget()
        _refit()

    camps_cb = ttk.Checkbutton(watched, text="Include Kuthchemes camps", variable=camps_var,
                               command=_show_camps)
    camps_cb.pack(anchor='w', pady=(PAD_XS, PAD_XS))
    _show_camps()
    add_tooltip(camps_cb, "Listed on the board, never alerted: " + ", ".join(
        r.name for r in onslaught.ROWS if r.kind == onslaught.CAMP))
    controls.append((camps_cb, lambda: show_vars['showList'].get()))

    own_row = ttk.Frame(watched)
    own_row.pack(fill='x')
    own_lbl = ttk.Label(own_row, text="Your own names:", font=FONT_BODY,
                        foreground=THEME_COLORS['body'])
    own_lbl.pack(side='left')
    labels.append((own_lbl, _list_or_alerts))
    name_var = tk.StringVar()
    name_entry = ttk.Entry(own_row, textvariable=name_var, width=24)
    name_entry.pack(side='left', padx=PAD_XS)
    add_tooltip(name_entry, "A mob's exact in-game name, watched as a mini")
    controls.append((name_entry, _list_or_alerts))
    add_btn = ttk.Button(own_row, text="Add", width=BTN_SMALL, command=lambda: _add())
    add_btn.pack(side='left')
    reason_var = tk.StringVar()
    reason = ttk.Label(watched, textvariable=reason_var, font=FONT_SMALL,
                       foreground=THEME_COLORS['muted'])
    reason.pack(anchor='w')
    names_frame = ttk.Frame(watched)
    names_frame.pack(fill='both', expand=True, pady=(PAD_XS, 0))
    custom = list(cfg['custom'])

    def _refusal():
        return onslaught.custom_refusal(name_var.get().strip(), custom)

    def _draw_names():
        for w in names_frame.winfo_children():
            w.destroy()
        live = enabled_var.get() and _list_or_alerts()
        for name in custom:
            row = ttk.Frame(names_frame)
            row.pack(fill='x', pady=PAD_MICRO)
            ttk.Label(row, text=name, font=FONT_BODY,
                      foreground=THEME_COLORS['body'] if live else TK_COLORS['dim_text']
                      ).pack(side='left')
            btn = ttk.Button(row, text="×", width=2, bootstyle='secondary',  # type: ignore[call-arg]
                             command=lambda n=name: _delete(n), state='normal' if live else 'disabled')
            btn.pack(side='right')
            add_tooltip(btn, f"Stop watching {name}")
        _refit()

    def _add(_e=None):
        if _refusal() is None:
            custom.append(name_var.get().strip())
            name_var.set("")
            _draw_names()
        return 'break'

    def _delete(name):
        before = list(custom)
        custom.remove(name)
        _draw_names()

        def _undo():
            if dialog.winfo_exists():
                custom[:] = before
                _draw_names()
        app_toast(dialog, f"Removed {name} — click to undo", 'info', 8,
                  key='onslaught-custom-undo', on_click=_undo)

    def _on_name_typed(*_):
        text = name_var.get().strip()
        reason_var.set((_refusal() or "") if text else "")
        add_btn.configure(state='normal' if (enabled_var.get() and _list_or_alerts()
                                             and _refusal() is None) else 'disabled')

    name_var.trace_add('write', _on_name_typed)
    name_entry.bind('<Return>', _add)

    resting = [(lbl, rule, str(lbl.cget('foreground'))) for lbl, rule in labels]

    def _sync(*_):
        on = enabled_var.get()
        for widget, rule in controls:
            widget.configure(state='normal' if on and (rule is None or rule()) else 'disabled')
        for lbl, rule, fg in resting:
            live = on and (rule is None or rule())
            lbl.configure(foreground=fg if live else TK_COLORS['dim_text'])
        if on and not _list_or_alerts():
            hint.pack(anchor='w', after=always)
        else:
            hint.pack_forget()
        _on_name_typed()
        _draw_names()

    enable_cb.configure(command=_sync)
    _sync()

    def _apply():
        new_cfg = onslaught.validate_config({
            'enabled': enabled_var.get(),
            'scale': size_var.get(),
            **{key: var.get() for key, var in show_vars.items()},
            'alertSeconds': round(float(alert_scale.get())),
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

    ttk.Button(footer, text="Apply", bootstyle="success",
               command=_apply, width=BTN_DIALOG).pack(side='right')
    ttk.Button(footer, text="Cancel", bootstyle="secondary",
               command=dialog.destroy, width=BTN_DIALOG
               ).pack(side='right', padx=(0, PAD_SMALL))

    dialog.update_idletasks()
    center_on_parent(dialog, app, _WIDTH, max(_HEIGHT, dialog.winfo_reqheight()))
    dialog.deiconify()

    dialog.bind("<Return>", lambda e: _apply() if e.widget is not name_entry else None)
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.bind("<Map>",
                lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                add="+")
    dialog.after(0, enable_cb.focus_set)
    return dialog
