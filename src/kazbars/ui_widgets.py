"""
KazBars — UI widget helpers and interaction bindings.

Widget-builder functions (create_dialog_header, create_app_header,
create_tip_bar), event helpers (bind_card_events, bind_button_press_effect,
bind_label_press_effect, bind_label_hover_colors), the in-app tooltip,
a debounce utility, the alpha-blend color helper, and CollapsibleSection.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .ui_helpers import (
    CELL_GAP,
    CELL_PX,
    CELL_PX_LARGE,
    FONT_BODY,
    FONT_DIALOG_HEADER,
    FONT_FORM_LABEL,
    FONT_HEADING,
    FONT_SECTION,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    PAD_COLLAPSE_INDENT,
    PAD_INNER,
    PAD_LF,
    PAD_MID,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_TIP_BAR,
    PAD_XS,
    SCANLINE_ALPHA,
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


def create_dialog_header(parent, title_text, accent_color, width=460, accent_segments=None):
    """CRT-styled header canvas strip for dialogs — matches BuildLoadingScreen aesthetic.

    Resize-aware: accent strip and scanlines stretch when the dialog is resizable.
    Fixed-width dialogs still work — initial draw uses the provided width.

    Args:
        parent: Parent frame/toplevel
        title_text: Title to display (will be wrapped in Unicode brackets)
        accent_color: Hex color string for accent strip (e.g. MODULE_COLORS['grids'])
        width: Canvas width in pixels
        accent_segments: Optional list of (text, color) drawn smaller (FONT_SMALL)
            to the right of the bracketed title — e.g. a "by <name>" credit.

    Returns:
        The canvas widget (already packed).
    """
    height = 50
    bg = TK_COLORS["status_bg"]  # #1a1a1a

    canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0, bg=bg)
    canvas.pack(fill="x")

    display_text = f"〔 {title_text} 〕"
    scanline_color = blend_alpha("#000000", bg, SCANLINE_ALPHA)
    glow_color = blend_alpha(accent_color, bg, 25)
    mid_glow = blend_alpha(accent_color, bg, 50)

    # Measure title + optional smaller accent suffix so the pair stays centered.
    _title_font = tkfont.Font(font=FONT_DIALOG_HEADER)
    _accent_font = tkfont.Font(font=FONT_SMALL)
    _title_w = _title_font.measure(display_text)
    _accent_gap = 8
    _accent_w = (
        _accent_gap + sum(_accent_font.measure(t) for t, _ in accent_segments)
        if accent_segments
        else 0
    )

    def _draw(w):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, 3, fill=accent_color, outline="")
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cy = height // 2 + 2
        left = w // 2 - (_title_w + _accent_w) // 2
        cx = left + _title_w // 2
        canvas.create_text(
            cx, cy, text=display_text, anchor="center", fill=glow_color, font=FONT_DIALOG_HEADER
        )
        canvas.create_text(
            cx, cy, text=display_text, anchor="center", fill=mid_glow, font=FONT_DIALOG_HEADER
        )
        canvas.create_text(
            cx,
            cy,
            text=display_text,
            anchor="center",
            fill=THEME_COLORS["heading"],
            font=FONT_DIALOG_HEADER,
        )
        if accent_segments:
            sx = left + _title_w + _accent_gap
            for _seg_text, _seg_fill in accent_segments:
                canvas.create_text(
                    sx, cy, text=_seg_text, anchor="w", fill=_seg_fill, font=FONT_SMALL
                )
                sx += _accent_font.measure(_seg_text)

    _draw(width)
    _dlg_after = [None]
    _dlg_last_w = [0]

    def _on_dlg_configure(e):
        if e.width <= 1 or e.width == _dlg_last_w[0]:
            return
        _dlg_last_w[0] = e.width
        if _dlg_after[0] is not None:
            try:
                canvas.after_cancel(_dlg_after[0])
            except (ValueError, tk.TclError):
                pass
        _dlg_after[0] = canvas.after(33, lambda w=e.width: _draw(w))

    canvas.bind("<Configure>", _on_dlg_configure)

    return canvas


def create_app_header(parent, title_text, accent_color):
    """CRT-styled header canvas for the main application window.

    Scaled-up variant of create_dialog_header: 4px accent strip (vs 3px),
    no bracket decoration, taller canvas, larger font.
    Resize-aware: accent strip and scanlines stretch on window resize.

    Args:
        parent: Parent frame/toplevel
        title_text: App name to display
        accent_color: Hex color string for accent strip

    Returns:
        The canvas widget (already packed).
    """
    height = 55
    bg = TK_COLORS["status_bg"]  # #1a1a1a

    canvas = tk.Canvas(parent, width=1, height=height, highlightthickness=0, bg=bg)
    canvas.pack(fill="x")

    scanline_color = blend_alpha("#000000", bg, SCANLINE_ALPHA)
    _state = {"accent": accent_color}

    def _draw(w, color=None):
        if color:
            _state["accent"] = color
        ac = _state["accent"]
        glow_color = blend_alpha(ac, bg, 25)
        mid_glow = blend_alpha(ac, bg, 50)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, 4, fill=ac, outline="")
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cx, cy = w // 2, height // 2 + 2
        canvas.create_text(
            cx, cy, text=title_text, anchor="center", fill=glow_color, font=FONT_HEADING
        )
        canvas.create_text(
            cx, cy, text=title_text, anchor="center", fill=mid_glow, font=FONT_HEADING
        )
        canvas.create_text(
            cx,
            cy,
            text=title_text,
            anchor="center",
            fill=THEME_COLORS["heading"],
            font=FONT_HEADING,
        )

    _header_last_w = [0]
    canvas._redraw = _draw
    canvas._last_w = _header_last_w

    def _on_header_configure(e):
        if e.width <= 1 or e.width == _header_last_w[0]:
            return
        _header_last_w[0] = e.width
        _draw(e.width)

    canvas.bind("<Configure>", _on_header_configure)

    return canvas


def update_app_header_color(canvas, new_color):
    """Update the app header accent strip and glow to a new color."""
    w = canvas._last_w[0] or canvas.winfo_width() or 900
    canvas._redraw(w, color=new_color)


def create_tip_bar(parent, text):
    """Create a compact single-line tip bar replacing verbose description boxes."""
    tip_frame = ttk.Frame(parent)
    tip_frame.pack(fill="x", padx=PAD_TAB, pady=PAD_TIP_BAR)
    ttk.Label(
        tip_frame, text="?", font=FONT_SMALL_BOLD, foreground=THEME_COLORS["accent"], width=2
    ).pack(side="left")
    ttk.Label(tip_frame, text=text, font=FONT_SMALL, foreground=THEME_COLORS["muted"]).pack(
        side="left", fill="x"
    )
    return tip_frame


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


def labeled_spinbox(
    parent,
    label,
    var,
    *,
    from_,
    to,
    width=5,
    tooltip=None,
    on_change=None,
    label_font=FONT_FORM_LABEL,
    label_color=None,
    padx=0,
):
    """Labeled spinbox with key-validation and focus-out clamp.

    `var` is a caller-owned StringVar or IntVar; the helper reads its type
    to drive the clamp. `on_change`, if given, fires on spinbox arrows AND
    after focus-out clamp. Returns the Spinbox so callers can bind extras.
    """
    lbl = ttk.Label(parent, text=label, font=label_font)
    if label_color:
        lbl.configure(foreground=label_color)
    lbl.pack(side="left")

    def _validate(value):
        if value in ("", "-"):
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False

    vcmd = (parent.register(_validate), "%P")
    spin = ttk.Spinbox(
        parent,
        from_=from_,
        to=to,
        textvariable=var,
        width=width,
        validate="key",
        validatecommand=vcmd,
        command=on_change or "",
    )
    spin.pack(side="left", padx=padx)

    is_str_var = isinstance(var, tk.StringVar)

    def _clamp(_evt=None):
        try:
            v = int(var.get()) if is_str_var else var.get()
        except (ValueError, tk.TclError):
            v = from_
        clamped = max(from_, min(to, v))
        var.set(str(clamped) if is_str_var else clamped)
        if on_change is not None:
            on_change()

    spin.bind("<FocusOut>", _clamp)
    if tooltip:
        add_tooltip(spin, tooltip)
    return spin


def labeled_combobox(
    parent, label, var, values, *, width=11, tooltip=None, padx=0, label_font=FONT_FORM_LABEL
):
    """Labeled readonly combobox. Returns the Combobox widget."""
    ttk.Label(parent, text=label, font=label_font).pack(side="left")
    combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state="readonly")
    combo.pack(side="left", padx=padx)
    if tooltip:
        add_tooltip(combo, tooltip)
    return combo


def position_entry(
    parent,
    label,
    var,
    *,
    lo,
    hi,
    width=5,
    tooltip=None,
    on_change=None,
    label_font=FONT_FORM_LABEL,
    label_color=None,
    padx=0,
):
    """Screen-pixel coordinate field: a label + right-justified Entry.

    Spinbox stepping doesn't fit thousands of pixels, so this is a plain Entry
    that key-validates to int (allowing transient '' / '-') and clamps to
    [lo, hi] on focus-out. Shared by the grid cards and the cast-timer strip so
    their X/Y columns are built identically. `on_change`, if given, fires after
    the clamp. Returns the Entry so callers can grey it when disabled.
    """
    lbl = ttk.Label(parent, text=label, font=label_font)
    if label_color:
        lbl.configure(foreground=label_color)
    lbl.pack(side="left")

    def _validate(value):
        if value in ("", "-"):
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False

    vcmd = (parent.register(_validate), "%P")
    entry = ttk.Entry(
        parent, textvariable=var, width=width, justify="right",
        validate="key", validatecommand=vcmd,
    )
    entry.pack(side="left", padx=padx)

    def _clamp(_evt=None):
        try:
            v = int(var.get())
        except (ValueError, tk.TclError):
            v = lo
        var.set(str(max(lo, min(hi, v))))
        if on_change is not None:
            on_change()

    entry.bind("<FocusOut>", _clamp)
    if tooltip:
        add_tooltip(entry, tooltip)
    return entry


def draw_grid_cells(canvas, rows, cols, type_color, area_w, area_h, tag="cells"):
    """Draw a miniature grid of colored rectangles on *canvas*."""
    canvas.delete(tag)
    cell_border = TK_COLORS["separator"]
    display_rows = min(rows, 5)
    display_cols = min(cols, 5)
    cell = CELL_PX_LARGE if rows == 1 and cols == 1 else CELL_PX
    gap = CELL_GAP
    while display_rows * cell + (display_rows - 1) * gap > area_h - 8 and cell > 3:
        cell -= 1
    while display_cols * cell + (display_cols - 1) * gap > area_w - 16 and cell > 3:
        cell -= 1
    total_w = display_cols * cell + (display_cols - 1) * gap
    total_h = display_rows * cell + (display_rows - 1) * gap
    sx = (area_w - total_w) // 2
    sy = (area_h - total_h) // 2
    for r in range(display_rows):
        for c in range(display_cols):
            x = sx + c * (cell + gap)
            y = sy + r * (cell + gap)
            canvas.create_rectangle(
                x, y, x + cell, y + cell, fill=type_color, outline=cell_border, tags=tag
            )


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


def create_rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """Draw a rounded rectangle on a tkinter Canvas (smoothed polygon)."""
    if radius <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class ColorSwatch(tk.Canvas):
    """Rounded color swatch with hover + click-to-pick via ttkbootstrap's themed
    ColorChooserDialog (the dark picker — not the white OS dialog). Handles
    RRGGBB / #RRGGBB / 0xRRGGBB. `on_change(hex)` fires when the user picks.
    """

    WIDTH = 34
    HEIGHT = 22
    RADIUS = 3

    def __init__(self, parent, color_var=None, on_change=None, initial_color="#FFFFFF", **kwargs):
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("takefocus", True)
        super().__init__(parent, width=self.WIDTH, height=self.HEIGHT, **kwargs)
        self.configure(bg=TK_COLORS["bg"])
        self._border_idle = TK_COLORS["border"]
        self._border_hover = THEME_COLORS["muted"]
        self._color_var = color_var
        self._on_change = on_change
        self._color = initial_color

        self.bind("<Enter>", lambda e: self._draw(self._border_hover))
        self.bind("<Leave>", lambda e: self._draw(self._border_idle))
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.bind(seq, self._on_click)
        self.bind("<FocusIn>", lambda e: self._draw(THEME_COLORS["accent"]))
        self.bind("<FocusOut>", lambda e: self._draw(self._border_idle))

        if color_var:
            color_var.trace_add("write", lambda *_: self._sync_from_var())
            self._sync_from_var()
        else:
            self._draw(self._border_idle)

    def set_color(self, hex_color):
        """Programmatically update the displayed color."""
        self._color = self._normalize(hex_color)
        self._draw(self._border_idle)

    def get_color(self):
        """Return the current displayed color as #RRGGBB."""
        return self._color

    def _sync_from_var(self):
        raw = self._color_var.get().strip()
        if raw:
            self._color = self._normalize(raw)
            self._draw(self._border_idle)

    @staticmethod
    def _normalize(raw):
        """Accept RRGGBB / #RRGGBB / 0xRRGGBB → #RRGGBB."""
        raw = raw.strip()
        if raw.startswith(("0x", "0X")):
            return "#" + raw[2:]
        if not raw.startswith("#"):
            return "#" + raw
        return raw

    def _draw(self, border_color):
        self.delete("all")
        create_rounded_rect(
            self,
            1,
            1,
            self.WIDTH - 1,
            self.HEIGHT - 1,
            self.RADIUS,
            fill=self._color,
            outline=border_color,
        )

    def _on_click(self, event):
        from ttkbootstrap.dialogs import ColorChooserDialog

        cd = ColorChooserDialog(initialcolor=self._color, title="Timer Color")
        # Build first so _toplevel exists, then force topmost before showing.
        cd.build()
        cd._locate()
        try:
            cd._toplevel.attributes("-topmost", True)
        except (AttributeError, tk.TclError):
            pass
        cd._toplevel.deiconify()
        cd._toplevel.grab_set()
        cd._toplevel.wait_window()
        if cd.result:
            self._color = cd.result.hex
            self._draw(self._border_hover)
            if self._on_change:
                self._on_change(self._color)


class CollapsibleSection(ttk.Frame):
    """A section with a clickable header that shows/hides its content.

    The header shows an arrow indicator, title text, and optional right-side
    widgets (passed via add_header_widget). The content frame is toggled
    via pack/pack_forget.

    Usage:
        section = CollapsibleSection(parent, "Grid Name", initially_open=True)
        section.pack(fill='x', pady=2)
        # Add widgets to section.header_frame (right side) and section.content
        ttk.Label(section.content, text="Settings go here").pack()
    """

    def __init__(
        self,
        parent,
        title="",
        accent_color=None,
        initially_open=False,
        badge_text=None,
        badge_color=None,
    ):
        """Initialize a collapsible section with a clickable header and togglable content area."""
        super().__init__(parent)
        self._is_open = initially_open
        self._dimmed = False
        self._accent_color = accent_color
        self._badge_color = badge_color

        # --- Header bar (always visible) ---
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x")

        # Clickable left side: arrow + accent + title + badge + summary.
        # Exposed as `header_left` so callers can pack always-visible widgets
        # (e.g. status indicators) right after the title.
        left = ttk.Frame(self.header_frame)
        left.pack(side="left", fill="x", expand=True)
        self.header_left = left
        clickable = [left]

        arrow_text = "▼" if initially_open else "▶"
        self._arrow_label = ttk.Label(
            left, text=arrow_text, font=FONT_SMALL, foreground=THEME_COLORS["muted"], width=2
        )
        self._arrow_label.pack(side="left")
        clickable.append(self._arrow_label)

        self._accent_canvas = None
        if accent_color:
            self._accent_canvas = tk.Canvas(
                left, width=3, height=16, highlightthickness=0, bg=accent_color
            )
            self._accent_canvas.pack(side="left", padx=(0, PAD_MID))

        self._title_label = ttk.Label(
            left, text=title, font=FONT_SECTION, foreground=THEME_COLORS["heading"]
        )
        self._title_label.pack(side="left")
        clickable.append(self._title_label)

        self._badge_label = None
        if badge_text:
            self._badge_label = ttk.Label(
                left,
                text=badge_text,
                font=FONT_SMALL,
                foreground=badge_color or THEME_COLORS["muted"],
            )
            self._badge_label.pack(side="left", padx=(PAD_LF, 0))
            clickable.append(self._badge_label)

        # Optional summary (shown when collapsed, hidden when expanded). A frame
        # so it can hold one or more independently-colored segments. Exposed as
        # `summary_frame` so callers packing into `header_left` can anchor their
        # widgets before it (`pack(before=...)`) to sit flush after the title.
        self._summary_frame = ttk.Frame(left)
        self._summary_frame.pack(side="left", padx=(PAD_TAB, 0))
        self.summary_frame = self._summary_frame
        clickable.append(self._summary_frame)

        # Keyboard accessibility — left frame is focusable
        left.configure(takefocus=True)
        left.bind("<Return>", lambda e: self.toggle())
        left.bind("<space>", lambda e: self.toggle())

        def _on_focus_in(e):
            focus_color = THEME_COLORS["muted"] if self._dimmed else THEME_COLORS["accent"]
            self._arrow_label.config(foreground=focus_color)
            self._title_label.config(foreground=focus_color)

        def _on_focus_out(e):
            self._arrow_label.config(foreground=THEME_COLORS["muted"])
            self._title_label.config(foreground=self._resting_title_color())

        left.bind("<FocusIn>", _on_focus_in)
        left.bind("<FocusOut>", _on_focus_out)

        # Bind click on all header elements
        for widget in clickable:
            widget.bind("<Button-1>", lambda e: self.toggle())

        # Hover highlight on the container frame — avoids flicker when
        # moving between child widgets by checking winfo_containing on Leave
        _left = left

        def _on_header_enter(e):
            self._arrow_label.config(foreground=THEME_COLORS["heading"])

        def _on_header_leave(e):
            try:
                w = _left.winfo_containing(e.x_root, e.y_root)
                while w is not None:
                    if w is _left:
                        return
                    w = getattr(w, "master", None)
            except (tk.TclError, RuntimeError):
                pass
            self._arrow_label.config(foreground=THEME_COLORS["muted"])

        _left.bind("<Enter>", _on_header_enter)
        _left.bind("<Leave>", _on_header_leave)

        # --- Content area (toggled) ---
        self._content_wrapper = ttk.Frame(self)
        if badge_color:
            tint = blend_alpha(badge_color, TK_COLORS["bg"], 8)
            style_name = f"Tint_{tint.replace('#', '')}.TFrame"
            ttk.Style().configure(style_name, background=tint)
            self.content = ttk.Frame(self._content_wrapper, style=style_name)
        else:
            self.content = ttk.Frame(self._content_wrapper)
        self.content.pack(side="left", fill="x", expand=True)
        if initially_open:
            self._content_wrapper.pack(fill="x", padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))

    def toggle(self):
        if self._is_open:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if not self._is_open:
            self._is_open = True
            self._arrow_label.config(text="▼")
            self._content_wrapper.pack(fill="x", padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))
            self._summary_frame.pack_forget()

    def collapse(self):
        if self._is_open:
            self._is_open = False
            self._arrow_label.config(text="▶")
            self._content_wrapper.pack_forget()
            self._summary_frame.pack(side="left", padx=(PAD_TAB, 0), in_=self._title_label.master)

    def set_title(self, text):
        self._title_label.config(text=text)

    def _resting_title_color(self):
        return TK_COLORS["dim_text"] if self._dimmed else THEME_COLORS["heading"]

    def set_dimmed(self, dimmed):
        """Mark the section as inactive: title, badge, and accent strips drop to greys.

        Used for grids excluded from the build — the row stays interactive,
        but its identity drains so the user can see at a glance which grids
        won't ship.
        """
        if self._dimmed == bool(dimmed):
            return
        self._dimmed = bool(dimmed)
        self._title_label.config(foreground=self._resting_title_color())
        if self._badge_label is not None:
            badge_fg = (
                TK_COLORS["dim_text"]
                if self._dimmed
                else (self._badge_color or THEME_COLORS["muted"])
            )
            self._badge_label.config(foreground=badge_fg)
        if self._accent_canvas is not None:
            self._accent_canvas.config(
                bg=TK_COLORS["border"] if self._dimmed else self._accent_color
            )

    def set_summary(self, text, color=None):
        """Single-segment collapsed summary (color None → muted)."""
        self.set_summary_segments([(text, color)] if text else [])

    def set_summary_segments(self, segments):
        """Render the collapsed summary as one or more independently-colored
        segments. `segments`: iterable of (text, color); color None → muted.
        Each segment toggles the section on click, like the rest of the header."""
        for child in self._summary_frame.winfo_children():
            child.destroy()
        for seg_text, seg_color in segments:
            lbl = ttk.Label(
                self._summary_frame, text=seg_text, font=FONT_SMALL,
                foreground=seg_color or THEME_COLORS["muted"],
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e: self.toggle())

    @property
    def is_open(self):
        return self._is_open


# =========================================================================== #
# Settings-panel builders (shared by the Deeps + Live Tracker config panels)  #
# =========================================================================== #

def create_card(parent, title, padding=PAD_INNER):
    """A titled section card. Thin wrapper over the `Card.TLabelframe` style so
    both config panels group options identically."""
    return ttk.LabelFrame(parent, text=title, style="Card.TLabelframe", padding=padding)


def create_status_block(parent, title="Status", wraplength=0):
    """Two-line status: a small muted title above a colored body line.

    Returns the body `ttk.Label` for the caller to update via
    `.configure(text=..., foreground=...)`.
    """
    ttk.Label(
        parent, text=title, font=FONT_SMALL, foreground=THEME_COLORS["muted"],
    ).pack(anchor="w", pady=(0, PAD_XS))
    body = ttk.Label(
        parent, text="", font=FONT_BODY, foreground=THEME_COLORS["body"],
        wraplength=wraplength,
    )
    body.pack(anchor="w", pady=(0, PAD_ROW))
    return body


def create_slider_row(parent, label_text, from_, to, initial, suffix, on_drag, on_commit):
    """One row: descriptor label · ttk.Scale · live value label.

    `on_drag(value)` fires continuously while dragging (refresh the label + push
    live, but do NOT persist); `on_commit()` fires on button/key release so a
    drag is a single write. Returns `(scale, value_label)` — keep the scale to
    move it programmatically (e.g. on profile load).
    """
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=PAD_XS)
    ttk.Label(
        row, text=label_text, font=FONT_BODY, foreground=THEME_COLORS["body"],
    ).pack(side="left")
    value_label = ttk.Label(
        row, text=f"{initial}{suffix}", font=FONT_SMALL,
        foreground=THEME_COLORS["muted"], width=5, anchor="e",
    )
    value_label.pack(side="right")
    scale = ttk.Scale(
        row, from_=from_, to=to, value=initial, orient="horizontal", command=on_drag,
    )
    scale.pack(side="left", fill="x", expand=True, padx=PAD_SMALL)
    scale.bind("<ButtonRelease-1>", lambda _e: on_commit())
    scale.bind("<KeyRelease>", lambda _e: on_commit())
    return scale, value_label


def toggle_button_state(
    running, enabled=True, *,
    start_label="Start Monitoring",
    stop_label="Stop Monitoring",
    disabled_label=None,
):
    """Pure mapping `(running, enabled) -> (text, bootstyle, state)` for a single
    Start/Stop toggle button. Kept pure so it can be unit-tested without Tk."""
    if not enabled:
        return (disabled_label or start_label, "secondary", "disabled")
    if running:
        return (stop_label, "danger", "normal")
    return (start_label, "success", "normal")


def create_toggle_action_button(parent, command, width=None):
    """The headline Start/Stop button (one toggle, not two buttons). Style/label
    are applied by `refresh_toggle_button` via `toggle_button_state`."""
    btn = ttk.Button(parent, text="Start Monitoring", bootstyle="success", command=command)
    if width is not None:
        btn.configure(width=width)
    return btn


def refresh_toggle_button(btn, running, enabled=True, **labels):
    """Apply `toggle_button_state` to a toggle button (text + color + enabled)."""
    text, bootstyle, state = toggle_button_state(running, enabled, **labels)
    btn.configure(text=text, bootstyle=bootstyle, state=state)
