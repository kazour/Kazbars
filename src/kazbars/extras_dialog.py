"""
KazBars — the shell every Extras dialog shares.

Cast timer, Console, Inspect panel, Onslaught tracker and Stopwatch each open
one modal dialog from the Extras menu or their shortcut card: a header, a tip
bar, the master gate row ("Include … in builds"), titled cards, Cancel /
Apply (Enter applies, Esc cancels), centred on the app. `ExtrasShell` builds
that frame in the order the dialogs always built it — the withdrawn
Toplevel, header, tip bar, gate row, the footer packed first at the bottom,
then the content frame the dialog fills with its cards — keeps the registry
of what greys with the gate (`gate`, `dim`; `sync` applies it, then the
dialog's own `on_sync` step) and finishes the window (`finish`: the buttons,
the centring, the bindings). Every control and static label registered
greys with the gate, so a disabled dialog reads fully off, not half on.
The dialog keeps its cards and its Apply.
"""

import tkinter as tk
from tkinter import ttk

from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import BTN_DIALOG, MODULE_COLORS, PAD_SMALL, PAD_TAB, PAD_XS, TK_COLORS
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip
from .window_position import center_on_parent


def raise_if_open(window):
    """Bring an open dialog back (shown, lifted, focused): True. False when
    there is none, or it is gone."""
    try:
        if window is None or not window.winfo_exists():
            return False
    except tk.TclError:
        return False
    window.deiconify()
    window.lift()
    window.focus_force()
    return True


class ExtrasShell:
    """See the module docstring. `base` is the profile's overlay size, for
    the Size slider's hint; `enabled_var` the master gate."""

    def __init__(self, app, attr, *, title, tip, gate_text, gate_tip, enabled, width):
        self.app = app
        self.width = width
        self.base = app.grids_panel.base_size()
        dialog = self.dialog = tk.Toplevel(app)
        setattr(app, attr, dialog)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(app)
        dialog.grab_set()

        create_dialog_header(dialog, title, MODULE_COLORS['grids'], width=width)
        create_tip_bar(dialog, tip)

        self.enabled_var = tk.BooleanVar(value=enabled)
        master = ttk.Frame(dialog)
        master.pack(fill='x', padx=PAD_TAB, pady=(0, PAD_XS))
        self.enable_cb = ttk.Checkbutton(master, text=gate_text, variable=self.enabled_var,
                                         command=self.sync)
        self.enable_cb.pack(side='left')
        add_tooltip(self.enable_cb, gate_tip)

        # The footer first, so it keeps its height before the cards claim the rest.
        self.footer = ttk.Frame(dialog, padding=(PAD_TAB, PAD_XS))
        self.footer.pack(fill='x', side='bottom')
        self.content = ttk.Frame(dialog, padding=(PAD_TAB, 0))
        self.content.pack(fill='both', expand=True)

        # (widget, rule): live while the gate is on and the rule, if any, holds.
        self._gated: list = []
        # (label, its resting colour, rule).
        self._dim: list = []
        # The dialog's own step after the registry, given the gate's state.
        self.on_sync = None

    def gate(self, *widgets, rule=None):
        """Controls that follow the gate (by ttk state)."""
        self._gated.extend((w, rule) for w in widgets)

    def dim(self, *labels, rule=None):
        """Static text that follows the gate (by foreground)."""
        self._dim.extend((lbl, str(lbl.cget('foreground')), rule) for lbl in labels)

    def sync(self):
        on = self.enabled_var.get()
        for widget, rule in self._gated:
            live = on and (rule is None or rule())
            widget.configure(state='normal' if live else 'disabled')
        for lbl, fg, rule in self._dim:
            live = on and (rule is None or rule())
            lbl.configure(foreground=fg if live else TK_COLORS['dim_text'])
        if self.on_sync is not None:
            self.on_sync(on)

    def finish(self, apply, height, *, enter_except=None, fit=False):
        """Apply / Cancel in the footer, the window centred on the app at
        `width` x `height` (`fit`: or its own height, when taller) and shown;
        Enter applies (except from `enter_except`), Escape and the close box
        cancel, the gate takes focus."""
        dialog = self.dialog
        ttk.Button(self.footer, text="Apply", bootstyle="success",
                   command=apply, width=BTN_DIALOG).pack(side='right')
        ttk.Button(self.footer, text="Cancel", bootstyle="secondary",
                   command=dialog.destroy, width=BTN_DIALOG
                   ).pack(side='right', padx=(0, PAD_SMALL))
        if fit:
            dialog.update_idletasks()
            height = max(height, dialog.winfo_reqheight())
        center_on_parent(dialog, self.app, self.width, height)
        dialog.deiconify()

        dialog.bind("<Return>", lambda e: apply() if e.widget is not enter_except else None)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        # The global one-shot dark-titlebar patch can miss a Toplevel built
        # this late, so re-assert it on the dialog's own map.
        dialog.bind("<Map>",
                    lambda e: apply_dark_titlebar(dialog) if e.widget is dialog else None,
                    add="+")
        dialog.after(0, self.enable_cb.focus_set)
