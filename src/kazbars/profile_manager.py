"""KazBars — Profile Manager dialog.

A richer alternative to the raw OS file pickers: list / load / rename /
duplicate / delete / set-default over ``userdata/profiles/*.json``, plus portable
``KZBARS1:`` export (to clipboard) and import. The codec + the self-contained
buff embedding live in the pure ``profile_share``; this module is the Tk shell.

Export bundles any user-DB buffs the profile references (so it survives a paste
into a fresh install); import is one confirmation — "this profile includes N
custom buffs" — then writes the profile and merges the embedded buffs into
``database_user.json`` (skip-on-collision), with a single summary toast.
"""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ttkbootstrap.dialogs import Messagebox, Querybox

from . import profile_io, profile_share
from .buff_db_layers import DeltaStore
from .ui_headers import create_dialog_header
from .ui_helpers import (
    BTN_DIALOG,
    FONT_BODY,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
    style_treeview_heading,
)
from .ui_widgets import app_toast, confirm
from .userdata import database_user_path
from .window_position import bind_window_position_save, restore_window_position

logger = logging.getLogger(__name__)


def open_profile_manager(app):
    """Open (or focus) the Profile Manager dialog."""
    existing = getattr(app, '_profile_manager', None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return
    app._profile_manager = ProfileManagerDialog(app)


class ProfileManagerDialog(tk.Toplevel):
    WIDTH = 460
    MIN_HEIGHT = 320

    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self.app = app
        self.title("Manage Profiles")
        self.transient(app)
        self.resizable(False, True)

        create_dialog_header(self, "Manage Profiles", MODULE_COLORS['grids'], width=self.WIDTH)

        body = ttk.Frame(self)
        body.pack(fill='both', expand=True, padx=PAD_TAB * 2, pady=(PAD_TAB, PAD_LF))

        ttk.Label(body, text="Your profiles live in userdata/profiles. ★ marks your default.",
                  font=FONT_SMALL, foreground=THEME_COLORS['muted'],
                  wraplength=self.WIDTH - PAD_TAB * 4, justify='left').pack(anchor='w', pady=(0, PAD_SMALL))

        list_frame = ttk.Frame(body)
        list_frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(list_frame, columns=('name',), show='headings',
                                 selectmode='browse', height=10)
        style_treeview_heading()
        self.tree.heading('name', text='Profile', anchor='w')
        self.tree.column('name', width=self.WIDTH - PAD_TAB * 5, anchor='w')
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', lambda e: self._load())
        self.tree.bind('<Return>', lambda e: self._load())
        field_bg = ttk.Style().lookup('Treeview', 'fieldbackground') or TK_COLORS['bg']
        self._empty_hint = ttk.Label(
            self.tree,
            text="No profiles yet. Save your setup with File ▸ Save profile as…, "
                 "or import one below.",
            font=FONT_BODY, foreground=THEME_COLORS['muted'], background=field_bg,
            justify='center', wraplength=self.WIDTH - PAD_TAB * 8)

        manage = ttk.Frame(body)
        manage.pack(fill='x', pady=(PAD_SMALL, 0))
        for text, cmd in (("Load", self._load), ("Rename", self._rename),
                          ("Duplicate", self._duplicate), ("Delete", self._delete),
                          ("Set Default", self._set_default)):
            ttk.Button(manage, text=text, command=cmd,
                       bootstyle="secondary").pack(side='left', padx=PAD_XS)  # type: ignore[call-arg]

        share = ttk.Frame(body)
        share.pack(fill='x', pady=(PAD_SMALL, 0))
        ttk.Label(share, text="Share a profile (custom buffs travel with it):",
                  font=FONT_BODY, foreground=THEME_COLORS['body']).pack(anchor='w', pady=(PAD_SMALL, PAD_XS))
        share_btns = ttk.Frame(share)
        share_btns.pack(fill='x')
        ttk.Button(share_btns, text="Export to clipboard",
                   command=self._export, bootstyle="success").pack(side='left', padx=(0, PAD_XS))  # type: ignore[call-arg]
        ttk.Button(share_btns, text="Import from string…",
                   command=self._import, bootstyle="info-outline").pack(side='left')  # type: ignore[call-arg]
        ttk.Button(share_btns, text="Close", width=BTN_DIALOG, command=self._close,
                   bootstyle="secondary").pack(side='right')  # type: ignore[call-arg]

        self._refresh(select=self._initial_iid())
        self.minsize(self.WIDTH, self.MIN_HEIGHT)
        restore_window_position(self, "profile_manager", self.WIDTH, 420, app, resizable=True)
        bind_window_position_save(self, "profile_manager")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind('<Escape>', lambda e: self._close())
        self.deiconify()
        self.tree.focus_set()

    # -- helpers ---------------------------------------------------------- #
    def _profiles(self):
        return sorted(self.app.profiles_path.glob("*.json"), key=lambda p: p.stem.lower())

    def _default_path(self):
        pref = self.app.settings.get('default_profile')
        return Path(pref).resolve() if pref else None

    def _initial_iid(self):
        """Row to preselect on open: the default profile if set, else the first."""
        default = self._default_path()
        profiles = self._profiles()
        if default:
            for path in profiles:
                if path.resolve() == default:
                    return path.name
        return profiles[0].name if profiles else None

    def _refresh(self, select=None):
        self.tree.delete(*self.tree.get_children())
        default = self._default_path()
        for path in self._profiles():
            mark = "  ★" if default and path.resolve() == default else ""
            self.tree.insert('', 'end', iid=path.name, values=(path.stem + mark,))
        if self.tree.get_children():
            self._empty_hint.place_forget()
        else:
            self._empty_hint.place(relx=0.5, rely=0.4, anchor='center')
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
            self.tree.focus(select)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            app_toast(self, "Select a profile first", 'warning')
            return None
        return self.app.profiles_path / sel[0]

    def _unique_path(self, stem):
        candidate = self.app.profiles_path / f"{stem}.json"
        n = 2
        while candidate.exists():
            candidate = self.app.profiles_path / f"{stem} ({n}).json"
            n += 1
        return candidate

    # -- actions ---------------------------------------------------------- #
    def _load(self):
        path = self._selected()
        if not path:
            return
        if not self.app._check_unsaved_changes():
            return
        data, corrupt = profile_io.read_profile_file(path)
        profile_io.apply_profile_data(self.app, path, data, corrupt=corrupt)
        self._close()

    def _rename(self):
        path = self._selected()
        if not path:
            return
        new = Querybox.get_string(prompt=f"Rename '{path.stem}' to:",
                                  title="Rename Profile", parent=self)
        if not new or not new.strip():
            return
        target = self.app.profiles_path / f"{new.strip()}.json"
        if target.exists():
            app_toast(self, f"A profile named '{new.strip()}' already exists", 'warning')
            return
        try:
            path.rename(target)
        except OSError as e:
            Messagebox.show_error(f"Couldn't rename the profile.\n\n({e})",
                                  title="Rename Failed", parent=self)
            return
        self._rebind_path(path, target)
        self._refresh(select=target.name)
        app_toast(self, f"Renamed to '{target.stem}'", 'success')

    def _duplicate(self):
        path = self._selected()
        if not path:
            return
        target = self._unique_path(f"{path.stem} (copy)")
        try:
            target.write_bytes(path.read_bytes())
        except OSError as e:
            Messagebox.show_error(f"Couldn't duplicate the profile.\n\n({e})",
                                  title="Duplicate Failed", parent=self)
            return
        self._refresh(select=target.name)
        app_toast(self, f"Duplicated as '{target.stem}'", 'success')

    def _delete(self):
        path = self._selected()
        if not path:
            return
        if not confirm(f"Delete the profile '{path.stem}'?\n\nThis can't be undone.",
                       title="Delete Profile", action="Delete profile",
                       parent=self, danger=True):
            return
        neighbor = self.tree.next(path.name) or self.tree.prev(path.name)
        try:
            path.unlink()
        except OSError as e:
            Messagebox.show_error(f"Couldn't delete the profile.\n\n({e})",
                                  title="Delete Failed", parent=self)
            return
        self._rebind_path(path, None)
        self._refresh(select=neighbor)
        app_toast(self, f"Deleted '{path.stem}'", 'info')

    def _set_default(self):
        path = self._selected()
        if not path:
            return
        profile_io.set_default_profile(self.app, path)
        self._refresh(select=path.name)
        app_toast(self, f"'{path.stem}' is now your default profile", 'success')

    def _export(self):
        path = self._selected()
        if not path:
            return
        data, corrupt = profile_io.read_profile_file(path)
        if corrupt:
            app_toast(self, "That profile is corrupt — can't export it", 'danger')
            return
        db = self.app.database
        buffs = profile_share.collect_referenced_user_buffs(data, db.by_id, db.by_name, db.provenance)
        string = profile_share.encode_profile(data, buffs)
        self.clipboard_clear()
        self.clipboard_append(string)
        n = len(buffs)
        extra = f" with {n} custom buff{'s' if n != 1 else ''}" if n else ""
        app_toast(self, f"Copied '{path.stem}'{extra} to the clipboard", 'success', 8)

    def _import(self):
        string = Querybox.get_string(
            prompt="Paste a KazBars profile string (KZBARS1:…):",
            title="Import Profile", parent=self)
        if not string:
            return
        try:
            profile, embedded = profile_share.decode_profile(string)
        except ValueError as e:
            Messagebox.show_error(str(e), title="Import Failed", parent=self)
            return
        n = len(embedded)
        prompt = (f"This profile includes {n} custom buff{'s' if n != 1 else ''}. Import it?"
                  if n else "Import this profile?")
        if not confirm(prompt, title="Import Profile", action="Import profile", parent=self):
            return

        target = self._unique_path("Imported Profile")
        try:
            profile_io.write_profile_file(target, profile)
        except OSError as e:
            Messagebox.show_error(f"Couldn't save the imported profile.\n\n({e})",
                                  title="Import Failed", parent=self)
            return

        added, skipped = profile_share.merge_imported_buffs(
            DeltaStore(database_user_path()), embedded,
            set(self.app.database.by_id), set(self.app.database.by_name))
        if added:
            self.app.database.reload()
            if getattr(self.app, 'db_panel', None):
                self.app.db_panel.refresh_from_database()

        self._refresh(select=target.name)
        tail = ""
        if added or skipped:
            parts = []
            if added:
                parts.append(f"{added} buff{'s' if added != 1 else ''} added")
            if skipped:
                parts.append(f"{skipped} already existed")
            tail = " — " + ", ".join(parts)
        app_toast(self, f"Imported '{target.stem}'{tail}", 'success', 8)

    # -- bookkeeping ------------------------------------------------------ #
    def _rebind_path(self, old, new):
        """Keep current_profile / default_profile pointers valid after a rename
        (new=target) or delete (new=None)."""
        old_s = str(old)
        if self.app.current_profile == old_s:
            self.app.current_profile = str(new) if new else None
            self.app._update_title()
        if self.app.settings.get('default_profile') == old_s:
            self.app.settings.set('default_profile', str(new) if new else None)
            self.app.settings.save()

    def _close(self):
        self.app._profile_manager = None
        self.destroy()
