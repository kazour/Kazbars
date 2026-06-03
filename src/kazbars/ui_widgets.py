"""
KazBars — core UI glue: bindings, tooltip, toast, and small helpers.

Event helpers (bind_card_events, bind_button_press_effect,
bind_label_press_effect, bind_label_hover_colors), the in-app tooltip, a
debounce utility, the alpha-blend color helper, the status-bar flash, and the
app toast. The widget builders that used to live here moved to ui_headers
(headers/tip bar), ui_forms (fields + settings-panel builders), and
ui_collapsible (CollapsibleSection).
"""

import tkinter as tk

from .ui_helpers import (
    FONT_SMALL,
    THEME_COLORS,
    TK_COLORS,
)


def debounced_callback(widget, delay_ms, callback):
    """Return a wrapper that debounces calls via after() timers.

    Repeated calls within delay_ms cancel the previous timer, so the
    callback only fires once after input settles.  Useful for spinbox
    command= and trace_add callbacks that trigger expensive redraws.

    Args:
        widget: Any tkinter widget (used for after/after_cancel).
        delay_ms: Milliseconds to wait after the last call before firing.
        callback: The function to invoke (receives *args from the wrapper).
    """
    after_id = [None]

    def wrapper(*args):
        if after_id[0] is not None:
            try:
                widget.after_cancel(after_id[0])
            except (ValueError, tk.TclError):
                pass
        after_id[0] = widget.after(delay_ms, lambda: callback(*args))

    return wrapper


def blend_alpha(fg_hex: str, bg_hex: str, alpha: int) -> str:
    """Blend foreground color over background at given alpha (0-100).
    Used to simulate AS2 opacity on tkinter Canvas (which lacks transparency).
    """
    fr, fg, fb = int(fg_hex[1:3], 16), int(fg_hex[3:5], 16), int(fg_hex[5:7], 16)
    br, bg_, bb = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    a = max(0, min(alpha, 100)) / 100.0
    r = int(fr * a + br * (1 - a))
    g = int(fg * a + bg_ * (1 - a))
    b = int(fb * a + bb * (1 - a))
    return f"#{r:02x}{g:02x}{b:02x}"


def flash_status_bar(bar, color=None, steps=8, interval=30):
    """Brief color pulse on a status-bar widget — subtle success/failure feedback.

    Settles back to TK_COLORS['status_bg']. Defaults to the success tint when
    no color is given. Swallows TclError if the bar is destroyed mid-fade.
    """
    color = color or THEME_COLORS["success"]
    bg = TK_COLORS["status_bg"]

    def _step(i):
        try:
            t = i / steps
            blended = blend_alpha(color, bg, int(40 * (1 - t)))
            bar.configure(bg=blended)
            if i < steps:
                bar.after(interval, lambda: _step(i + 1))
            else:
                bar.configure(bg=bg)
        except tk.TclError:
            pass

    _step(0)


def app_toast(widget, message, style="info", duration=6, key=None, on_click=None):
    """Show a toast via the app's runtime-attached ToastManager.

    Walks `widget` upward looking for a `.toast` attribute (set by
    KazBarsApp on the root window — the walker checks `widget` itself
    before traversing `.master`, so passing the root works). Silently
    no-ops if no manager is found, so callers can use this from dialogs
    that are sometimes parented to non-app roots (tests, isolated previews).

    `key`, when set, makes repeat emits coalesce into the existing toast
    rather than stacking — see ToastManager.show.
    """
    w = widget
    while w is not None:
        toast = getattr(w, "toast", None)
        if toast is not None:
            toast.show(message, style=style, duration=duration, key=key, on_click=on_click)
            return
        w = getattr(w, "master", None)


def bind_card_events(card_border, color, hover_color=None):
    """Bind hover highlight on a card frame.

    Uses a single Enter/Leave pair on the card itself. On Leave, walks the
    widget ancestry of whatever is under the mouse to decide whether the
    pointer is still inside the card (moved to a child) or truly left.
    Works reliably for both tk and ttk widgets — no debounce needed.

    `color` may be a callable returning the current resting color, so the
    caller can flip the resting state (e.g. enabled -> disabled) without
    rebinding.
    """
    _hover = hover_color or "#ffffff"
    _resting = color if callable(color) else (lambda c=color: c)

    def _is_descendant(widget):
        """Walk .master chain to check if widget is inside card_border."""
        w = widget
        while w is not None:
            if w is card_border:
                return True
            w = getattr(w, "master", None)
        return False

    def on_enter(e):
        card_border.config(highlightbackground=_hover, highlightcolor=_hover)

    def on_leave(e):
        try:
            w = card_border.winfo_containing(e.x_root, e.y_root)
            if w is not None and _is_descendant(w):
                return
        except (tk.TclError, RuntimeError):
            pass
        normal = _resting()
        card_border.config(highlightbackground=normal, highlightcolor=normal)

    card_border.bind("<Enter>", on_enter)
    card_border.bind("<Leave>", on_leave)


def add_tooltip(widget, text):
    """Add a hover tooltip that stays inside the app window."""
    _InAppToolTip(widget, text)


class _InAppToolTip:
    """Tooltip rendered as a tk.Frame inside the root window, clamped to app bounds."""

    DELAY = 400
    PAD = 6

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._tip_frame = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.DELAY, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        self._hide()
        root = self.widget.winfo_toplevel()
        tip = tk.Frame(
            root,
            bg=TK_COLORS["input_bg"],
            highlightthickness=1,
            highlightbackground=TK_COLORS["border"],
        )
        lbl = tk.Label(
            tip,
            text=self.text() if callable(self.text) else self.text,
            bg=TK_COLORS["input_bg"],
            fg=THEME_COLORS["body"],
            font=FONT_SMALL,
            wraplength=260,
            justify="left",
            padx=self.PAD,
            pady=self.PAD,
        )
        lbl.pack()
        self._tip_frame = tip

        # Position: below the widget, clamped inside root
        root.update_idletasks()
        wx = self.widget.winfo_rootx() - root.winfo_rootx()
        wy = self.widget.winfo_rooty() - root.winfo_rooty() + self.widget.winfo_height() + 4
        tip.place(x=wx, y=wy)
        tip.update_idletasks()

        tw = tip.winfo_reqwidth()
        th = tip.winfo_reqheight()
        rw = root.winfo_width()
        rh = root.winfo_height()

        # Clamp horizontal
        if wx + tw > rw:
            wx = rw - tw - 4
        if wx < 4:
            wx = 4
        # Clamp vertical — flip above widget if needed
        if wy + th > rh:
            wy = self.widget.winfo_rooty() - root.winfo_rooty() - th - 4
        if wy < 4:
            wy = 4

        tip.place_configure(x=wx, y=wy)
        tip.lift()

    def _hide(self):
        if self._tip_frame:
            self._tip_frame.destroy()
            self._tip_frame = None


def bind_button_press_effect(button, bootstyle="primary"):
    """Add a subtle press micro-interaction to a ttk.Button.

    On press, briefly switches to outline variant. Restores on release.
    bootstyle must be passed explicitly (not retrievable via cget).
    """

    def _on_press(e):
        try:
            button.configure(bootstyle=f"{bootstyle}-outline")
        except tk.TclError:
            pass

    def _on_release(e):
        try:
            button.configure(bootstyle=bootstyle)
        except tk.TclError:
            pass

    button.bind("<ButtonPress-1>", _on_press, add="+")
    button.bind("<ButtonRelease-1>", _on_release, add="+")


def bind_label_hover_colors(label, normal_color, hover_color):
    """Toggle a label's foreground on Enter/Leave/FocusIn/FocusOut.

    Centralizes the 4-line bind block used by clickable header labels
    (delete ×, dismiss ×, etc.) so hover and keyboard-focus visuals stay
    consistent.
    """
    label.bind("<Enter>", lambda e: label.config(foreground=hover_color))
    label.bind("<Leave>", lambda e: label.config(foreground=normal_color))
    label.bind("<FocusIn>", lambda e: label.config(foreground=hover_color))
    label.bind("<FocusOut>", lambda e: label.config(foreground=normal_color))


def bind_label_press_effect(label, press_color=None):
    """Add a brief press flash to a clickable ttk.Label.

    On ButtonPress the foreground snaps to press_color (default: accent),
    then restores on ButtonRelease. Pairs with existing Enter/Leave hover.
    """
    _color = press_color or THEME_COLORS["accent"]

    def _on_press(e):
        label._pre_press_fg = label.cget("foreground")
        label.configure(foreground=_color)

    def _on_release(e):
        fg = getattr(label, "_pre_press_fg", THEME_COLORS["body"])
        label.configure(foreground=fg)

    label.bind("<ButtonPress-1>", _on_press, add="+")
    label.bind("<ButtonRelease-1>", _on_release, add="+")
