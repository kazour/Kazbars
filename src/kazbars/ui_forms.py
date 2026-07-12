"""
KazBars — form fields and settings-panel builders.

Labeled input widgets (spinbox, combobox, position entry), the grid-cell
preview, the rounded color swatch, and the shared settings-panel builders
(card, status block, slider row, Start/Stop toggle button) used by the Deeps
and Live Tracker config panels.
"""

import tkinter as tk
from tkinter import ttk

from .ui_helpers import (
    CELL_GAP,
    CELL_PX,
    CELL_PX_LARGE,
    FONT_BODY,
    FONT_FORM_LABEL,
    FONT_SMALL,
    PAD_INNER,
    PAD_ROW,
    PAD_SMALL,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import add_tooltip


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


def create_slider_row(parent, label_text, from_, to, initial, suffix, on_drag, on_commit,
                      value_width=5, notch=False, label_width=None, label_sink=None):
    """One row: descriptor label · ttk.Scale · live value label.

    `on_drag(value)` fires continuously while dragging (refresh the label + push
    live, but do NOT persist); `on_commit()` fires on button/key release so a
    drag is a single write. Returns `(scale, value_label)` — keep the scale to
    move it programmatically (e.g. on profile load).

    `value_width` is the readout label width in chars — default 5 fits short
    units like `48pt` / `100%`; widen it for longer readouts (e.g. `4000/s`).

    `label_width` fixes the descriptor label's width in chars (left-anchored) so
    every slider in a panel starts its trough at the same x — pass the longest
    label's length to keep a column of rows aligned. None = shrink-to-fit (the
    sliders start ragged, fine when the labels are uniform).

    `label_sink`, when given a list, receives the descriptor + value labels so a
    caller can grey them in step with the controls (the labels are not
    interactive, so a disabled state never reaches them otherwise).

    `notch=True` draws a thin tick under the trough's centre — use it on
    symmetric sliders (`from_ == -to`) so the midpoint reads as the default. It
    is pure chrome (no effect on the value), and the centre is robust because
    the thumb inset is symmetric, so the midpoint maps to value 0.
    """
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=PAD_XS)
    label_kw = {"width": label_width, "anchor": "w"} if label_width else {}
    desc_label = ttk.Label(
        row, text=label_text, font=FONT_BODY, foreground=THEME_COLORS["body"], **label_kw,
    )
    desc_label.pack(side="left")
    value_label = ttk.Label(
        row, text=f"{initial}{suffix}", font=FONT_SMALL,
        foreground=THEME_COLORS["muted"], width=value_width, anchor="e",
    )
    value_label.pack(side="right")
    if notch:
        # Overlay a centre tick on the trough's lower edge (relx=0.5 == value 0 for a
        # symmetric range — the thumb inset is symmetric, so the midpoint maps to 0).
        # It tucks behind the thumb at the default and reappears the moment you drag
        # away, marking "home". Tick lives in the same frame as the scale so widths and
        # x-origins match exactly.
        track = ttk.Frame(row)
        track.pack(side="left", fill="x", expand=True, padx=PAD_SMALL)
        scale = ttk.Scale(
            track, from_=from_, to=to, value=initial, orient="horizontal", command=on_drag,
        )
        scale.pack(fill="x", expand=True)
        tk.Frame(track, width=2, height=7, bg=THEME_COLORS["muted"]).place(
            relx=0.5, rely=1.0, anchor="s",
        )
    else:
        scale = ttk.Scale(
            row, from_=from_, to=to, value=initial, orient="horizontal", command=on_drag,
        )
        scale.pack(side="left", fill="x", expand=True, padx=PAD_SMALL)
    scale.bind("<ButtonRelease-1>", lambda _e: on_commit())
    scale.bind("<KeyRelease>", lambda _e: on_commit())
    if label_sink is not None:
        label_sink.extend((desc_label, value_label))
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
