"""
KazBars — First Launch Dialog
Modal setup dialog shown when no game folder is configured.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ttkbootstrap.dialogs import Messagebox

from . import game_folder, profile_io, update_orchestrator
from .app_popups import show_welcome_popup
from .game_resolution import COMMON_RESOLUTIONS
from .grid_model import parse_resolution
from .overlay import size_for_height
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_SMALL,
    FONT_BODY,
    FONT_SECTION,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_TINY,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import bind_label_press_effect
from .window_position import fit_window_height, restore_window_position

FIRST_LAUNCH_SIZE = (640, 480)

COMMON_INSTALL_PATHS = [
    r"C:\Funcom\Age of Conan",
    r"D:\Games\Age of Conan",
    r"C:\Program Files (x86)\Funcom\Age of Conan",
    r"C:\Program Files (x86)\Steam\steamapps\common\Age of Conan - Unchained",
    r"C:\Steam\steamapps\common\Age of Conan - Unchained",
    r"D:\Steam\steamapps\common\Age of Conan - Unchained",
    r"D:\SteamLibrary\steamapps\common\Age of Conan - Unchained",
]


def show_first_launch_dialog(parent, app_name, on_game_set, on_load_default,
                             on_resolution_set=None, default_profile_exists=True,
                             on_dialog_closed=None, on_start_empty=None,
                             on_import_profile=None):
    """Modal first-launch setup. Returns when dialog closes.

    Callbacks:
      on_game_set(path)           — user picked a game folder
      on_load_default(res_str)    — user chose "Load Defaults" (after on_game_set)
      on_resolution_set(res_str)  — the resolution, saved on every path
      on_import_profile(dialog)   — user chose "Import Profile" (after on_game_set);
                                    truthy once a profile landed, falsy on a
                                    cancel or a refused file (the dialog stays)
      on_start_empty()            — user chose "Start Empty" (after on_game_set)
      on_dialog_closed()          — dialog destroyed
    """
    dialog = tk.Toplevel(parent)
    dialog.title(f"Welcome to {app_name}")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    restore_window_position(dialog, 'first_launch', *FIRST_LAUNCH_SIZE, parent,
                            resizable=False)

    # Header
    create_dialog_header(dialog, f"Welcome to {app_name}",
                         MODULE_COLORS['grids'], width=FIRST_LAUNCH_SIZE[0])

    content = ttk.Frame(dialog)
    content.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

    # --- Section 1: Game path ---
    ttk.Label(content, text="Game Folder",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))

    ttk.Label(content, text="Where is Age of Conan installed?",
              font=FONT_SMALL, foreground=THEME_COLORS['muted']
              ).pack(anchor='w', pady=(0, PAD_XS))

    path_frame = ttk.Frame(content)
    path_frame.pack(fill='x', pady=(0, PAD_TINY))

    path_var = tk.StringVar()
    path_entry = ttk.Entry(path_frame, textvariable=path_var, font=FONT_BODY)
    path_entry.pack(side='left', fill='x', expand=True, padx=(0, PAD_SMALL))

    def browse():
        p = filedialog.askdirectory(title="Select Age of Conan Folder",
                                     parent=dialog)
        if p:
            path_var.set(p)

    ttk.Button(path_frame, text="Browse", width=BTN_SMALL,
               command=browse).pack(side='right')

    warn_label = ttk.Label(content, text="", font=FONT_SMALL,
                           foreground=THEME_COLORS['warning'])
    warn_label.pack(anchor='w')

    def _validate_path_hint():
        p = path_var.get().strip()
        if p and not game_folder.is_game_folder(p):
            warn_label.configure(
                text="This doesn't look like an AoC install — missing Data/Gui/Default/",
                foreground=THEME_COLORS['warning'])
        else:
            warn_label.configure(text="")

    # Common locations (only show paths that exist). Its own frame, not packed
    # straight on content, so it can hide once the entry already holds one of
    # these paths — repeating a path the user just typed or clicked is noise,
    # not help.
    existing_paths = [cp for cp in COMMON_INSTALL_PATHS if Path(cp).exists()]
    found_frame = ttk.Frame(content)
    if existing_paths:
        ttk.Label(found_frame, text="Found on this PC:", font=FONT_SMALL,
                  foreground=THEME_COLORS['muted']).pack(anchor='w', pady=(PAD_XS, PAD_TINY))
        for cp in existing_paths:
            lbl = ttk.Label(found_frame, text=f"  {cp}", font=FONT_SMALL,
                            foreground=THEME_COLORS['body'], cursor='hand2',
                            takefocus=True)
            lbl.pack(anchor='w')
            lbl.bind('<Button-1>', lambda e, p=cp: path_var.set(p))
            lbl.bind('<Return>', lambda e, p=cp: path_var.set(p))
            lbl.bind('<space>', lambda e, p=cp: path_var.set(p))
            lbl.bind('<FocusIn>', lambda e, l=lbl: l.config(
                foreground=THEME_COLORS['accent']))
            lbl.bind('<FocusOut>', lambda e, l=lbl: l.config(
                foreground=THEME_COLORS['body']))
            bind_label_press_effect(lbl)
        found_frame.pack(fill='x')

    # Separator
    sep = ttk.Separator(content, orient='horizontal')
    sep.pack(fill='x', pady=(PAD_TAB, PAD_SMALL))

    # --- Section 2: How to start ---
    ttk.Label(content, text="How do you want to start?",
              font=FONT_SECTION, foreground=THEME_COLORS['heading']
              ).pack(anchor='w', pady=(0, PAD_XS))

    # Resolution detection
    screen_w = parent.winfo_screenwidth()
    screen_h = parent.winfo_screenheight()
    detected = f"{screen_w}x{screen_h}"

    common_resolutions = list(COMMON_RESOLUTIONS)
    if detected not in common_resolutions:
        common_resolutions.insert(0, detected)

    res_var = tk.StringVar(value=detected)

    # Above the cards, not in one: every path builds, and builds place things
    # at this resolution.
    res_frame = ttk.Frame(content)
    res_frame.pack(fill='x', pady=(0, PAD_SMALL))
    ttk.Label(res_frame, text="Game resolution:", font=FONT_SMALL,
              foreground=THEME_COLORS['muted']).pack(side='left', padx=(0, PAD_SMALL))
    ttk.Combobox(res_frame, textvariable=res_var, values=common_resolutions,
                 width=12, font=FONT_SMALL).pack(side='left', padx=(0, PAD_SMALL))
    ttk.Label(res_frame, text="match your in-game setting", font=FONT_SMALL,
              foreground=THEME_COLORS['muted']).pack(side='left')

    # --- Shared actions ---
    def _set_game_if_provided(unless=None):
        p = path_var.get().strip()
        if p and p != unless:
            on_game_set(str(Path(p).resolve()))
        if on_resolution_set:
            on_resolution_set(res_var.get())

    def _close():
        dialog.destroy()
        if on_dialog_closed:
            on_dialog_closed()

    def _commit_setup():
        """Every start button's prologue: the resolution must read, then the
        folder and the resolution persist. False (warning shown) stops the
        action; the dialog stays."""
        if not parse_resolution(res_var.get()):
            Messagebox.show_warning(
                f"\"{res_var.get()}\" isn't a valid resolution.\n\n"
                "Use WIDTHxHEIGHT, like 1920x1080.",
                title="Invalid Resolution", parent=dialog)
            return False
        _set_game_if_provided()
        return True

    def load_default():
        if _commit_setup():
            on_load_default(res_var.get())
            _close()

    def import_profile():
        # Persisted before the picker opens: the click confirmed the folder
        # and the resolution, whatever the picker then returns.
        if not _commit_setup():
            return
        if on_import_profile and on_import_profile(dialog):
            _close()
        else:
            buttons["Import Profile"].focus_set()

    def start_empty():
        if _commit_setup():
            if on_start_empty:
                on_start_empty()
            _close()

    def skip():
        # Keep a typed game path even on "Set up later" / X — losing it because
        # the user closed the dialog is worse than skipping the re-arm. The
        # path filled in for them is not kept here: they never confirmed it
        # (an Import Profile click did, and already saved it).
        _set_game_if_provided(unless=auto_path)
        _close()

    # --- Equal-weight option cards: equal columns, buttons on one baseline ---
    _card_bg = TK_COLORS['status_bg']
    _border = TK_COLORS['border']
    cards = [("Use Defaults", "Pre-configured grids for\ncommon raid buffs and debuffs.",
              "Load Defaults", "success", load_default)] if default_profile_exists else []
    cards += [("Import Profile", "Open a profile file\nyou or a friend saved.",
               "Import Profile", "info-outline", import_profile),
              ("Start Empty", "Build your own grids\nfrom scratch.",
               "Start Empty", "info-outline", start_empty)]

    cards_frame = ttk.Frame(content)
    cards_frame.pack(fill='x', pady=(0, PAD_SMALL))
    buttons = {}   # by button label
    for col, (title, blurb, label, style, command) in enumerate(cards):
        cards_frame.columnconfigure(col, weight=1, uniform='card')
        card = tk.Frame(cards_frame, bg=_card_bg, highlightthickness=1,
                        highlightbackground=_border, highlightcolor=_border)
        card.grid(row=0, column=col, sticky='nsew',
                  padx=(0 if col == 0 else PAD_XS, 0 if col == len(cards) - 1 else PAD_XS))
        inner = tk.Frame(card, bg=_card_bg)
        inner.pack(fill='both', expand=True, padx=PAD_LF, pady=PAD_LF)
        ttk.Label(inner, text=title, font=FONT_SECTION,
                  foreground=THEME_COLORS['heading']).pack(anchor='w')
        ttk.Label(inner, text=blurb, font=FONT_SMALL, foreground=THEME_COLORS['muted']
                  ).pack(anchor='w', pady=(PAD_TINY, PAD_SMALL))
        ttk.Frame(inner).pack(expand=True)   # pushes the button to the card's foot
        btn = ttk.Button(inner, text=label, bootstyle=style, command=command,
                         state='disabled')
        btn.pack(anchor='w')
        buttons[label] = btn

    # Says why the buttons are off. Always packed (empty when a path is set) so
    # the cards don't shift as the user types.
    gate_label = ttk.Label(content, text="", font=FONT_SMALL,
                           foreground=THEME_COLORS['muted'])
    gate_label.pack(anchor='w', pady=(0, PAD_TINY))

    # Enable/disable action buttons based on game path
    def _on_path_changed(*_):
        p = path_var.get().strip()
        has_path = bool(p)
        state = 'normal' if has_path else 'disabled'
        for btn in buttons.values():
            btn.configure(state=state)
        gate_label.configure(
            text="" if has_path else "Set your game folder above to start.")
        _validate_path_hint()
        # The entry already shows one of these paths verbatim — repeating it
        # in the list below is noise, not help. Clearing or editing it away
        # from every listed path brings the list back.
        if existing_paths:
            if p in existing_paths:
                found_frame.pack_forget()
            else:
                found_frame.pack(fill='x', before=sep)

    path_var.trace_add('write', _on_path_changed)
    _on_path_changed()

    # One unambiguous install → fill it in and arm the buttons, so Enter starts
    # the app. Two candidates is a choice only the user can make; zero leaves
    # the entry as the one thing to do. Set after the trace so it wires through
    # the same enable path as typing.
    _detected = [cp for cp in existing_paths if game_folder.is_game_folder(cp)]
    auto_path = _detected[0] if len(_detected) == 1 else None
    if auto_path:
        path_var.set(auto_path)
        # Enter then starts the app: Use Defaults, or Start Empty with no template.
        (buttons.get("Load Defaults") or buttons["Start Empty"]).focus_set()
    else:
        path_entry.focus_set()

    # Skip at the bottom
    ttk.Separator(content, orient='horizontal').pack(fill='x', side='bottom')
    skip_frame = ttk.Frame(content)
    skip_frame.pack(fill='x', side='bottom', pady=(PAD_SMALL, 0))
    skip_lbl = ttk.Label(skip_frame, text="Set up later",
                         font=FONT_BODY, foreground=THEME_COLORS['accent'],
                         cursor='hand2', takefocus=True)
    skip_lbl.pack(side='right')
    skip_lbl.bind('<Button-1>', lambda e: skip())
    skip_lbl.bind('<Return>', lambda e: skip())
    skip_lbl.bind('<space>', lambda e: skip())
    skip_lbl.bind('<Enter>', lambda e: skip_lbl.config(
        foreground=THEME_COLORS['heading']))
    skip_lbl.bind('<Leave>', lambda e: skip_lbl.config(
        foreground=THEME_COLORS['accent']))
    bind_label_press_effect(skip_lbl)

    dialog.protocol("WM_DELETE_WINDOW", skip)
    dialog.bind('<Escape>', lambda e: skip())

    # "Found on this PC" is as long as the PC makes it; grow rather than clip
    # the bottom-packed "Set up later" row. Never shrinks below the design size,
    # and re-clamps — restore_window_position only placed the design height, so
    # growing without this can push that same row off the bottom of the screen.
    fit_window_height(dialog, *FIRST_LAUNCH_SIZE)


def run_first_launch(app, app_name):
    """Coordinate first-launch flow: show the dialog, then handle the chosen
    path. Startup already seeded the profile ('My Setup' from the template),
    so "Use Defaults" re-anchors that seed to the chosen resolution, "Import
    Profile" replaces it with a picked file (no confirm — the seed is nothing
    the user made), and "Start Empty" empties it. Owns the callbacks the
    dialog dispatches to."""
    welcome_data = {}

    def _save_resolution(resolution_str):
        parsed = parse_resolution(resolution_str)
        if parsed:
            app.settings.set('game_resolution', list(parsed))
            app.settings.save()

    def on_game_set(path):
        app.game_path = path
        game_folder.save_game_path(app)
        game_folder.refresh_game_path_label(app)

    def _seed_overlay_size(resolution_str):
        """Set the seed's overlay size for the resolution the user just
        picked. Startup seeded the profile before this dialog opened, so its
        size came from the pre-dialog default — positions need nothing
        (fractions), the base size every in-game size derives from does. Only
        ever the pristine seed."""
        parsed = parse_resolution(resolution_str)
        if parsed:
            app.profile_store.update_section('overlay', {'size': size_for_height(parsed[1])})
            app.grids_panel.load_overlay()

    def _note_welcome(imported=False, notes=()):
        """The welcome popup's kwargs, from the profile now in place."""
        grids = app.grids_panel.grids
        welcome_data.update(
            grid_count=len(grids),
            enabled_count=sum(1 for g in grids if g.get('enabled', True)),
            profile_name=app.profile_store.document['name'],
            imported=imported, notes=notes)

    def on_load_default(resolution_str):
        # The resolution is already saved (on_resolution_set); positions are
        # fractions and fit any resolution as-is, the overlay size is set for
        # the chosen one.
        _seed_overlay_size(resolution_str)
        _note_welcome()

    def on_import_profile(dialog):
        # The file's own overlay size stands: it was set for its author's game.
        picked = profile_io.pick_profile_file(app, parent=dialog)
        if picked is None:
            return False
        doc, embedded = picked
        # No toast: the welcome popup is the one confirmation, buffs included.
        _note_welcome(imported=True, notes=profile_io.install_imported(app, doc, embedded))
        return True

    def on_start_empty():
        # The user asked for a clean slate — empty the seeded profile's grids
        # (autosaves through the store like any edit).
        app.grids_panel.load_profile_data([])
        app._on_grids_edited()

    def on_dialog_closed():
        if welcome_data:
            app.after(100, lambda: show_welcome_popup(app, **welcome_data))
        # First launch is complete — now safe to check for updates (app release,
        # then OTA buff-content; deferred so it never races the welcome popup).
        update_orchestrator.check_on_launch(app)
        game_folder.check_install_health(app)

    show_first_launch_dialog(
        app, app_name, on_game_set, on_load_default, _save_resolution,
        profile_io.template_doc(app) is not None, on_dialog_closed, on_start_empty,
        on_import_profile,
    )
