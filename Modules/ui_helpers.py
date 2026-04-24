"""
Kaz Grids — UI Helper Functions
Design system, window position persistence, and shared widgets.
"""

import logging
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

# ============================================================================
# SHARED FONT CONSTANTS
# ============================================================================
FONT_FAMILY = 'Segoe UI'
FONT_HEADING = ('Segoe UI', 14, 'bold')
FONT_BODY_LG = ('Segoe UI', 10)
FONT_SECTION = ('Segoe UI', 10, 'bold')
FONT_BODY = ('Segoe UI', 9)
FONT_FORM_LABEL = ('Segoe UI', 9)
FONT_SMALL_BOLD = ('Segoe UI', 8, 'bold')
FONT_SMALL = ('Segoe UI', 8)
FONT_TINY = ('Segoe UI', 7, 'bold')               # Slot count badges, compact labels
FONT_SYMBOL = ('Segoe UI', 13)                    # Symbol/glyph labels (×, +, etc.)
FONT_DIALOG_HEADER = ('Segoe UI', 13, 'bold')    # CRT-styled dialog header text
FONT_STATUS_ICON = ('Segoe UI', 26, 'bold')      # Build status icon (main)
FONT_STATUS_ICON_LG = ('Segoe UI', 28, 'bold')   # Build status icon (glow layers)

# ============================================================================
# THEME COLOR CONSTANTS (darkly theme)
# ============================================================================
# Semantic colors for ttk widget foreground text
THEME_COLORS = {
    'heading':    '#FFFFFF',   # Section headings
    'body':       '#C0C7CE',   # Body/descriptions (~7.2:1 WCAG AAA on #222)
    'muted':      '#B0B0B0',   # Hints, placeholders (~6.0:1 on #222)
    'accent':     '#3498db',   # Links, emphasis
    'warning':    '#f39c12',   # Warnings
    'danger':     '#e74c3c',   # Errors
    'success':    '#00bc8c',   # Success
    'info_value': '#3498db',   # Info display values
    'purple':     '#9b59b6',   # Grids nav accent
}

# Colors for raw tk widgets (Canvas, Listbox, Text) that ttkbootstrap can't theme
TK_COLORS = {
    'bg':         '#222222',   # darkly background
    'input_bg':   '#2f2f2f',   # darkly input background
    'input_fg':   '#ffffff',   # darkly input text
    'select_bg':  '#555555',   # darkly selection background
    'select_fg':  '#ffffff',   # darkly selection text
    'border':     '#444444',   # subtle border
    'separator':  '#333333',   # thin separator lines
    'status_bg':  '#1a1a1a',   # status bar background (darker than main bg)
    'dim_text':   '#888888',   # dimmed text on dark bg (unassigned slots, disabled labels)
}

# Overlay-specific colors (Windows transparency hack — not theme colors)
OVERLAY_COLORS = {
    'transparent': '#010101',  # Windows -transparentcolor key
    'bg_outer':    '#0a0a0a',  # Outer background (near-black, distinct from transparent key)
}


# ============================================================================
# LAYOUT CONSTANTS
# ============================================================================
PAD_TAB = 10              # Padding inside tab frames
PAD_INNER = 12            # Padding inside LabelFrames
PAD_ROW = 6               # Vertical gap between setting rows
PAD_BUTTON_GAP = 2        # Horizontal gap between buttons
PAD_TIP_BAR = (0, 4)      # Vertical padding for tip bar
PAD_COLLAPSE_INDENT = 14  # Left indent for CollapsibleSection content
PAD_RADIO_INDENT = 18     # Left indent for sub-labels beneath radio buttons
PAD_MICRO = 1             # Tight button grouping (preset buttons, action rows)
PAD_TINY = 3              # Minimal gap
PAD_XS = 4                # Asymmetric element spacing (widget-to-widget gaps)
PAD_SMALL = 5             # Compact dialog padding, widget horizontal gaps
PAD_MID = 6               # Sidebar section padding
PAD_LF = 8                # LabelFrame internal padding (dialogs)
PAD_LIST_ITEM = 15        # Section/item left indent
PAD_SECTION_GAP = 20      # Visual separation between button groups

# Button width standards
BTN_SMALL = 7             # Add, Edit, Delete, Clear, Copy
BTN_MEDIUM = 12           # Export, Import, Reset, Browse
BTN_LARGE = 20            # Build & Install, Generate & Install

# Scanline overlay alpha (0-255). Used for CRT decorative scanline overlays.
SCANLINE_ALPHA = 12

# Module accent colors (grids-only)
MODULE_COLORS = {
    'grids': '#3498db',   # Blue
}

# Retro/CRT decorative colors — DECORATIVE ONLY.
# Do not use for text or interactive states (fails WCAG contrast on #222 bg).
# Use THEME_COLORS for all readable text. These are for CRT tinting, glow layers, and accents.
_RETRO_COLORS = {
    'phosphor_green':  '#4A7A5A',   # Desaturated green — decorative accents, CRT tint
    'phosphor_amber':  '#8A7040',   # Warm amber — hover tints, secondary accents
    'phosphor_dim':    '#1A2B22',   # Near-black green — CRT background tint
    'crt_glow':        '#224433',   # Subtle glow behind header text
    'pixel_border':    '#2a2a2a',   # Pixel-art cell borders
    'green_bright':    '#33FF66',   # Full phosphor — ONLY for 1-2px accent lines
    'amber_bright':    '#FFAA33',   # Full amber — ONLY for tiny highlight details
}

# Grid type accent colors (player vs target differentiation)
GRID_TYPE_COLORS = {
    'player': '#3498db',   # Blue
    'target': '#e67e22',   # Orange
}


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
    return f'#{r:02x}{g:02x}{b:02x}'



def create_dialog_header(parent, title_text, accent_color, width=460):
    """CRT-styled header canvas strip for dialogs — matches BuildLoadingScreen aesthetic.

    Resize-aware: accent strip and scanlines stretch when the dialog is resizable.
    Fixed-width dialogs still work — initial draw uses the provided width.

    Args:
        parent: Parent frame/toplevel
        title_text: Title to display (will be wrapped in Unicode brackets)
        accent_color: Hex color string for accent strip (e.g. MODULE_COLORS['grids'])
        width: Canvas width in pixels

    Returns:
        The canvas widget (already packed).
    """
    height = 50
    bg = TK_COLORS['status_bg']  # #1a1a1a

    canvas = tk.Canvas(parent, width=width, height=height, highlightthickness=0,
                       bg=bg)
    canvas.pack(fill='x')

    display_text = f"\u3014 {title_text} \u3015"
    scanline_color = blend_alpha('#000000', bg, SCANLINE_ALPHA)
    glow_color = blend_alpha(accent_color, bg, 25)
    mid_glow = blend_alpha(accent_color, bg, 50)

    def _draw(w):
        canvas.delete('all')
        canvas.create_rectangle(0, 0, w, 3, fill=accent_color, outline='')
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cx, cy = w // 2, height // 2 + 2
        canvas.create_text(cx, cy, text=display_text, anchor='center',
                           fill=glow_color, font=FONT_DIALOG_HEADER)
        canvas.create_text(cx, cy, text=display_text, anchor='center',
                           fill=mid_glow, font=FONT_DIALOG_HEADER)
        canvas.create_text(cx, cy, text=display_text, anchor='center',
                           fill=THEME_COLORS['heading'], font=FONT_DIALOG_HEADER)

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
    canvas.bind('<Configure>', _on_dlg_configure)

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
    bg = TK_COLORS['status_bg']  # #1a1a1a

    canvas = tk.Canvas(parent, width=1, height=height, highlightthickness=0, bg=bg)
    canvas.pack(fill='x')

    scanline_color = blend_alpha('#000000', bg, SCANLINE_ALPHA)
    _state = {'accent': accent_color}

    def _draw(w, color=None):
        if color:
            _state['accent'] = color
        ac = _state['accent']
        glow_color = blend_alpha(ac, bg, 25)
        mid_glow = blend_alpha(ac, bg, 50)
        canvas.delete('all')
        canvas.create_rectangle(0, 0, w, 4, fill=ac, outline='')
        for y in range(0, height, 3):
            canvas.create_line(0, y, w, y, fill=scanline_color)
        cx, cy = w // 2, height // 2 + 2
        canvas.create_text(cx, cy, text=title_text, anchor='center',
                           fill=glow_color, font=FONT_HEADING)
        canvas.create_text(cx, cy, text=title_text, anchor='center',
                           fill=mid_glow, font=FONT_HEADING)
        canvas.create_text(cx, cy, text=title_text, anchor='center',
                           fill=THEME_COLORS['heading'], font=FONT_HEADING)

    _header_after = [None]
    _header_last_w = [0]
    canvas._redraw = _draw
    canvas._last_w = _header_last_w

    def _on_header_configure(e):
        if e.width <= 1 or e.width == _header_last_w[0]:
            return
        _header_last_w[0] = e.width
        if _header_after[0] is not None:
            try:
                canvas.after_cancel(_header_after[0])
            except (ValueError, tk.TclError):
                pass
        _header_after[0] = canvas.after(33, lambda w=e.width: _draw(w))
    canvas.bind('<Configure>', _on_header_configure)

    return canvas


def update_app_header_color(canvas, new_color):
    """Update the app header accent strip and glow to a new color."""
    w = canvas._last_w[0] or canvas.winfo_width() or 900
    canvas._redraw(w, color=new_color)


# ============================================================================
# UI HELPER WIDGETS
# ============================================================================
def create_tip_bar(parent, text):
    """Create a compact single-line tip bar replacing verbose description boxes."""
    tip_frame = ttk.Frame(parent)
    tip_frame.pack(fill='x', padx=PAD_TAB, pady=PAD_TIP_BAR)
    ttk.Label(tip_frame, text="?", font=FONT_SMALL_BOLD,
              foreground=THEME_COLORS['accent'], width=2).pack(side='left')
    ttk.Label(tip_frame, text=text, font=FONT_SMALL,
              foreground=THEME_COLORS['muted']).pack(side='left', fill='x')
    return tip_frame



def bind_card_events(card_border, color, hover_color=None):
    """Bind hover highlight on a card frame.

    Uses a single Enter/Leave pair on the card itself. On Leave, walks the
    widget ancestry of whatever is under the mouse to decide whether the
    pointer is still inside the card (moved to a child) or truly left.
    Works reliably for both tk and ttk widgets — no debounce needed.
    """
    _hover = hover_color or '#ffffff'
    _normal = color

    def _is_descendant(widget):
        """Walk .master chain to check if widget is inside card_border."""
        w = widget
        while w is not None:
            if w is card_border:
                return True
            w = getattr(w, 'master', None)
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
        card_border.config(highlightbackground=_normal, highlightcolor=_normal)

    card_border.bind('<Enter>', on_enter)
    card_border.bind('<Leave>', on_leave)


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
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._cancel, add='+')
        widget.bind('<ButtonPress>', self._cancel, add='+')

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
        tip = tk.Frame(root, bg=TK_COLORS['input_bg'], highlightthickness=1,
                       highlightbackground=TK_COLORS['border'])
        lbl = tk.Label(tip, text=self.text() if callable(self.text) else self.text, bg=TK_COLORS['input_bg'],
                       fg=THEME_COLORS['body'], font=FONT_SMALL,
                       wraplength=260, justify='left',
                       padx=self.PAD, pady=self.PAD)
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


def bind_button_press_effect(button, bootstyle='primary'):
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

    button.bind('<ButtonPress-1>', _on_press, add='+')
    button.bind('<ButtonRelease-1>', _on_release, add='+')


def bind_label_press_effect(label, press_color=None):
    """Add a brief press flash to a clickable ttk.Label.

    On ButtonPress the foreground snaps to press_color (default: accent),
    then restores on ButtonRelease. Pairs with existing Enter/Leave hover.
    """
    _color = press_color or THEME_COLORS['accent']

    def _on_press(e):
        label._pre_press_fg = label.cget('foreground')
        label.configure(foreground=_color)

    def _on_release(e):
        fg = getattr(label, '_pre_press_fg', THEME_COLORS['body'])
        label.configure(foreground=fg)

    label.bind('<ButtonPress-1>', _on_press, add='+')
    label.bind('<ButtonRelease-1>', _on_release, add='+')


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

    def __init__(self, parent, title="", accent_color=None, initially_open=False,
                 badge_text=None, badge_color=None):
        """Initialize a collapsible section with a clickable header and togglable content area."""
        super().__init__(parent)
        self._is_open = initially_open

        # --- Header bar (always visible) ---
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill='x')

        # Clickable left side: arrow + accent + title + badge + summary
        left = ttk.Frame(self.header_frame)
        left.pack(side='left', fill='x', expand=True)
        clickable = [left]

        arrow_text = "\u25BC" if initially_open else "\u25B6"
        self._arrow_label = ttk.Label(
            left, text=arrow_text, font=FONT_SMALL,
            foreground=THEME_COLORS['muted'], width=2
        )
        self._arrow_label.pack(side='left')
        clickable.append(self._arrow_label)

        if accent_color:
            accent = tk.Canvas(left, width=3, height=16,
                               highlightthickness=0, bg=accent_color)
            accent.pack(side='left', padx=(0, PAD_MID))

        self._title_label = ttk.Label(
            left, text=title, font=FONT_SECTION,
            foreground=THEME_COLORS['heading']
        )
        self._title_label.pack(side='left')
        clickable.append(self._title_label)

        # Optional type badge (always visible, even when expanded)
        if badge_text:
            self._badge_label = ttk.Label(
                left, text=badge_text, font=FONT_SMALL,
                foreground=badge_color or THEME_COLORS['muted']
            )
            self._badge_label.pack(side='left', padx=(PAD_LF, 0))
            clickable.append(self._badge_label)

        # Optional summary label (shown when collapsed, hidden when expanded)
        self._summary_label = ttk.Label(
            left, text="", font=FONT_SMALL,
            foreground=THEME_COLORS['muted']
        )
        self._summary_label.pack(side='left', padx=(PAD_TAB, 0))
        clickable.append(self._summary_label)

        # Keyboard accessibility — left frame is focusable
        left.configure(takefocus=True)
        left.bind('<Return>', lambda e: self.toggle())
        left.bind('<space>', lambda e: self.toggle())
        def _on_focus_in(e):
            self._arrow_label.config(foreground=THEME_COLORS['accent'])
            self._title_label.config(foreground=THEME_COLORS['accent'])
        def _on_focus_out(e):
            self._arrow_label.config(foreground=THEME_COLORS['muted'])
            self._title_label.config(foreground=THEME_COLORS['heading'])
        left.bind('<FocusIn>', _on_focus_in)
        left.bind('<FocusOut>', _on_focus_out)

        # Bind click on all header elements
        for widget in clickable:
            widget.bind('<Button-1>', lambda e: self.toggle())

        # Hover highlight on the container frame — avoids flicker when
        # moving between child widgets by checking winfo_containing on Leave
        _left = left
        def _on_header_enter(e):
            self._arrow_label.config(foreground=THEME_COLORS['heading'])
        def _on_header_leave(e):
            try:
                w = _left.winfo_containing(e.x_root, e.y_root)
                while w is not None:
                    if w is _left:
                        return
                    w = getattr(w, 'master', None)
            except (tk.TclError, RuntimeError):
                pass
            self._arrow_label.config(foreground=THEME_COLORS['muted'])
        _left.bind('<Enter>', _on_header_enter)
        _left.bind('<Leave>', _on_header_leave)

        # --- Content area (toggled) ---
        # Wrapper holds optional left accent bar + content side-by-side
        self._content_wrapper = ttk.Frame(self)
        if badge_color:
            tint = blend_alpha(badge_color, TK_COLORS['bg'], 8)
            bar = tk.Frame(self._content_wrapper, width=2, bg=badge_color)
            bar.pack(side='left', fill='y')
            bar.pack_propagate(False)
            style_name = f"Tint_{tint.replace('#', '')}.TFrame"
            ttk.Style().configure(style_name, background=tint)
            self.content = ttk.Frame(self._content_wrapper, style=style_name)
        else:
            self.content = ttk.Frame(self._content_wrapper)
        self.content.pack(side='left', fill='x', expand=True)
        if initially_open:
            self._content_wrapper.pack(fill='x', padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))

    def toggle(self):
        if self._is_open:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if not self._is_open:
            self._is_open = True
            self._arrow_label.config(text="\u25BC")
            self._content_wrapper.pack(fill='x', padx=(PAD_COLLAPSE_INDENT, 0), pady=(PAD_XS, 0))
            self._summary_label.pack_forget()

    def collapse(self):
        if self._is_open:
            self._is_open = False
            self._arrow_label.config(text="\u25B6")
            self._content_wrapper.pack_forget()
            self._summary_label.pack(side='left', padx=(PAD_TAB, 0),
                                     in_=self._title_label.master)

    def set_title(self, text):
        self._title_label.config(text=text)

    def set_summary(self, text):
        self._summary_label.config(text=text)

    @property
    def is_open(self):
        return self._is_open


# ============================================================================
# RAW TK WIDGET STYLING
# ============================================================================
def style_tk_listbox(listbox):
    """Style a raw tk.Listbox to match the darkly theme."""
    listbox.configure(
        bg=TK_COLORS['input_bg'], fg=TK_COLORS['input_fg'],
        selectbackground=TK_COLORS['select_bg'], selectforeground=TK_COLORS['select_fg'],
        highlightbackground=TK_COLORS['border'], highlightcolor=TK_COLORS['border'])


def style_tk_text(text_widget):
    """Style a raw tk.Text widget to match the darkly theme."""
    text_widget.configure(
        bg=TK_COLORS['input_bg'], fg=TK_COLORS['input_fg'],
        insertbackground=TK_COLORS['input_fg'],
        selectbackground=TK_COLORS['select_bg'], selectforeground=TK_COLORS['select_fg'],
        highlightbackground=TK_COLORS['border'], highlightcolor=TK_COLORS['border'])


def style_tk_canvas(canvas):
    """Style a raw tk.Canvas to match the darkly theme."""
    canvas.configure(bg=TK_COLORS['bg'], highlightthickness=0)


def apply_dark_titlebar(window):
    """Apply dark title bar on Windows 11 via pywinstyles."""
    try:
        import pywinstyles
        pywinstyles.apply_style(window, 'dark')
        pywinstyles.change_header_color(window, TK_COLORS['bg'])
    except (ImportError, Exception):
        pass  # Silently skip if pywinstyles unavailable or not on Windows 11


def enable_global_dark_titlebar():
    """Monkey-patch tk.Toplevel so every popup gets a dark title bar automatically."""
    _original_init = tk.Toplevel.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        # Defer until window is mapped so the HWND exists
        def _apply(event=None):
            self.unbind('<Map>', _map_id[0])
            apply_dark_titlebar(self)
        _map_id = [self.bind('<Map>', _apply)]

    tk.Toplevel.__init__ = _patched_init


# ============================================================================
# WINDOW POSITION HELPERS
# ============================================================================
from .settings_manager import get_setting, set_setting

def clamp_to_screen(x, y, width, height):
    """Clamp window coordinates so the window stays within screen bounds."""
    try:
        root = tk._default_root
        if root:
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
        else:
            screen_w, screen_h = 1920, 1080
    except (tk.TclError, AttributeError):
        screen_w, screen_h = 1920, 1080
    x = max(0, min(x, screen_w - width))
    y = max(0, min(y, screen_h - height - 50))
    return x, y


def save_window_position(window_name, x, y, width=None, height=None):
    """Persist a window's position and optional size to settings."""
    pos_data = {'x': x, 'y': y}
    if width is not None:
        pos_data['width'] = width
    if height is not None:
        pos_data['height'] = height
    set_setting(f'window_pos_{window_name}', pos_data)


def restore_window_position(window, window_name, default_width, default_height, parent=None, resizable=True):
    """Restore a window's saved position and size, or center it as a fallback."""
    pos_data = get_setting(f'window_pos_{window_name}')

    if pos_data:
        x = pos_data.get('x', 0)
        y = pos_data.get('y', 0)
        width = pos_data.get('width', default_width) if resizable else default_width
        height = pos_data.get('height', default_height) if resizable else default_height
    else:
        width, height = default_width, default_height
        if parent:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        else:
            try:
                screen_w = window.winfo_screenwidth()
                screen_h = window.winfo_screenheight()
            except (tk.TclError, RuntimeError, AttributeError):
                screen_w, screen_h = 1920, 1080
            x = (screen_w - width) // 2
            y = (screen_h - height) // 2

    x, y = clamp_to_screen(x, y, width, height)
    window.geometry(f"{width}x{height}+{x}+{y}")


def bind_window_position_save(window, window_name, save_size=True):
    """Bind a debounced Configure handler that auto-saves window position on move or resize."""
    save_timer = [None]  # Mutable container for closure

    def _do_save():
        save_timer[0] = None
        if save_size:
            save_window_position(window_name, window.winfo_x(), window.winfo_y(),
                                window.winfo_width(), window.winfo_height())
        else:
            save_window_position(window_name, window.winfo_x(), window.winfo_y())

    def on_configure(event):
        """Schedule a debounced position save when the window is moved or resized."""
        if event.widget == window and getattr(window, '_pos_initialized', False):
            # Debounce: only save 300ms after the last configure event
            if save_timer[0] is not None:
                try:
                    window.after_cancel(save_timer[0])
                except (ValueError, tk.TclError):
                    pass
            save_timer[0] = window.after(300, _do_save)

    window._pos_initialized = False
    window.after(500, lambda: setattr(window, '_pos_initialized', True))
    window.bind('<Configure>', on_configure)


# ============================================================================
# CUSTOM TTK STYLES
# ============================================================================
def setup_custom_styles(root):
    """Configure custom ttk styles for a more polished look. Call once at startup."""
    style = ttk.Style()

    # Card-style LabelFrame
    style.configure('Card.TLabelframe', borderwidth=1)
    style.configure('Card.TLabelframe.Label',
                    font=FONT_SECTION,
                    foreground=THEME_COLORS['body'])



# ============================================================================
# DRAG-TO-REORDER MANAGER
# ============================================================================
class DragReorderManager:
    """Manages drag-to-reorder for widgets packed vertically in a scrollable frame."""

    def __init__(self, canvas, inner_frame, on_reorder):
        self._canvas = canvas
        self._inner = inner_frame
        self._on_reorder = on_reorder
        self._handles = []
        self._panels = []  # ordered list of panel widgets (excludes separators)
        self._dragging = False
        self._drag_index = None
        self._indicator = tk.Frame(inner_frame, bg=THEME_COLORS['accent'], height=3)
        self._auto_scroll_id = None

    def bind_handle(self, handle_widget, index, panel_widget=None):
        handle_widget.bind('<ButtonPress-1>', lambda e: self._start_drag(index, e) or 'break')
        handle_widget.bind('<B1-Motion>', lambda e: self._on_drag(e) or 'break')
        handle_widget.bind('<ButtonRelease-1>', lambda e: self._end_drag(e) or 'break')
        self._handles.append(handle_widget)
        if panel_widget:
            self._panels.append(panel_widget)

    def clear(self):
        for h in self._handles:
            try:
                h.unbind('<ButtonPress-1>')
                h.unbind('<B1-Motion>')
                h.unbind('<ButtonRelease-1>')
            except tk.TclError:
                pass
        self._handles.clear()
        self._panels.clear()
        # Indicator gets destroyed when inner_frame children are cleared;
        # recreate it fresh for the next drag cycle
        try:
            self._indicator.place_forget()
            self._indicator.destroy()
        except tk.TclError:
            pass
        self._indicator = tk.Frame(self._inner, bg=THEME_COLORS['accent'], height=3)

    def _start_drag(self, index, event):
        self._dragging = True
        self._drag_index = index
        self._drag_widget = event.widget
        event.widget.grab_set()

    def _find_insert_index(self, y_root):
        """Find the insertion index based on cursor y position among panels."""
        for i, panel in enumerate(self._panels):
            mid = panel.winfo_rooty() + panel.winfo_height() // 2
            if y_root < mid:
                return i
        return len(self._panels)

    def _on_drag(self, event):
        if not self._dragging or not self._panels:
            return
        y_root = event.widget.winfo_rooty() + event.y
        insert = self._find_insert_index(y_root)

        # Show indicator line at insertion point
        try:
            if insert < len(self._panels):
                ref = self._panels[insert]
                rel_y = ref.winfo_y()
                self._indicator.place(in_=self._inner,
                                      x=0, y=rel_y - 2, relwidth=1.0, height=3)
            else:
                last = self._panels[-1]
                rel_y = last.winfo_y() + last.winfo_height()
                self._indicator.place(in_=self._inner,
                                      x=0, y=rel_y, relwidth=1.0, height=3)
            self._indicator.lift()
        except tk.TclError:
            pass

        # Auto-scroll when near canvas edges
        canvas_y = y_root - self._canvas.winfo_rooty()
        self._handle_auto_scroll(canvas_y)

    def _end_drag(self, event):
        if not self._dragging:
            return
        self._dragging = False
        try:
            event.widget.grab_release()
        except tk.TclError:
            pass
        try:
            self._indicator.place_forget()
        except tk.TclError:
            pass
        if self._auto_scroll_id:
            try:
                self._canvas.after_cancel(self._auto_scroll_id)
            except (ValueError, tk.TclError):
                pass
            self._auto_scroll_id = None

        y_root = event.widget.winfo_rooty() + event.y
        new_index = self._find_insert_index(y_root)

        old = self._drag_index
        if new_index != old and new_index != old + 1:
            actual_new = new_index if new_index < old else new_index - 1
            self._on_reorder(old, actual_new)

    def _handle_auto_scroll(self, canvas_y):
        if self._auto_scroll_id:
            try:
                self._canvas.after_cancel(self._auto_scroll_id)
            except (ValueError, tk.TclError):
                pass
            self._auto_scroll_id = None

        canvas_h = self._canvas.winfo_height()
        edge = 40
        if canvas_y < edge:
            self._canvas.yview_scroll(-1, 'units')
            self._auto_scroll_id = self._canvas.after(50, lambda: self._handle_auto_scroll(canvas_y))
        elif canvas_y > canvas_h - edge:
            self._canvas.yview_scroll(1, 'units')
            self._auto_scroll_id = self._canvas.after(50, lambda: self._handle_auto_scroll(canvas_y))


# ============================================================================
# TOAST NOTIFICATIONS
# ============================================================================
class ToastManager:
    """Lightweight toast notifications placed at bottom-right of a parent widget.

    Toasts slide up on entrance and fade out on exit for polished visual feedback.
    """

    STYLES = {
        'info':    'accent',
        'success': 'success',
        'warning': 'warning',
        'error':   'danger',
    }

    _SLIDE_STEPS = 6       # entrance animation frames
    _SLIDE_MS = 16          # ms between entrance frames
    _FADE_STEPS = 8         # exit animation frames
    _FADE_MS = 25           # ms between exit frames

    def __init__(self, parent):
        self._parent = parent
        self._toasts = []

    def show(self, message, style='info', duration=4, on_click=None):
        color = THEME_COLORS.get(self.STYLES.get(style, 'accent'), THEME_COLORS['accent'])

        toast = tk.Frame(self._parent, bg=TK_COLORS['status_bg'],
                         highlightbackground=TK_COLORS['border'],
                         highlightcolor=TK_COLORS['border'], highlightthickness=1)
        accent_bar = tk.Frame(toast, bg=color, width=3)
        accent_bar.pack(side='left', fill='y')
        label = ttk.Label(toast, text=message, font=FONT_SMALL,
                          foreground=THEME_COLORS['body'],
                          background=TK_COLORS['status_bg'])
        label.pack(side='left', padx=(PAD_LF, PAD_TAB), pady=PAD_XS)

        if on_click:
            for w in (toast, accent_bar, label):
                w.configure(cursor='hand2')
                w.bind('<Button-1>', lambda _e: on_click())

        self._toasts.append(toast)
        self._reposition()

        # Slide-up entrance animation
        self._animate_entrance(toast)

        # Schedule fade-out exit
        toast.after(duration * 1000, lambda: self._animate_exit(toast, color))

    def _animate_entrance(self, toast):
        """Slide toast up from below its final position."""
        toast.update_idletasks()
        slide_dist = toast.winfo_reqheight() + PAD_TAB

        def _step(i):
            if toast not in self._toasts:
                return
            try:
                # Current position
                info = toast.place_info()
                if not info:
                    return
                final_y = int(info.get('y', 0))
                # Ease-out: offset shrinks non-linearly
                t = i / self._SLIDE_STEPS
                offset = int(slide_dist * (1 - t) ** 2)
                toast.place_configure(y=final_y + offset)
                if i < self._SLIDE_STEPS:
                    toast.after(self._SLIDE_MS, lambda: _step(i + 1))
                else:
                    toast.place_configure(y=final_y)
            except tk.TclError:
                pass

        _step(0)

    def _animate_exit(self, toast, accent_color):
        """Fade out toast by interpolating colors toward background, then remove."""
        bg = TK_COLORS['status_bg']
        body_color = THEME_COLORS['body']

        def _step(i):
            if toast not in self._toasts:
                return
            try:
                t = i / self._FADE_STEPS
                faded_bg = blend_alpha(bg, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_fg = blend_alpha(body_color, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_accent = blend_alpha(accent_color, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_border = blend_alpha(TK_COLORS['border'], TK_COLORS['bg'], int(100 * (1 - t)))
                toast.configure(bg=faded_bg,
                                highlightbackground=faded_border,
                                highlightcolor=faded_border)
                for child in toast.winfo_children():
                    if isinstance(child, tk.Frame):
                        child.configure(bg=faded_accent)
                    elif isinstance(child, ttk.Label):
                        child.configure(foreground=faded_fg, background=faded_bg)
                if i < self._FADE_STEPS:
                    toast.after(self._FADE_MS, lambda: _step(i + 1))
                else:
                    self._remove_toast(toast)
            except tk.TclError:
                self._remove_toast(toast)

        _step(1)

    def _remove_toast(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)
        try:
            toast.place_forget()
            toast.destroy()
        except tk.TclError:
            pass
        self._reposition()

    def _reposition(self):
        offset = PAD_TAB
        for toast in reversed(self._toasts):
            toast.place(relx=1.0, rely=1.0, anchor='se',
                        x=-PAD_TAB, y=-offset)
            toast.lift()
            toast.update_idletasks()
            offset += toast.winfo_reqheight() + PAD_XS


# ============================================================================
# SCROLLABLE FRAME HELPER
# ============================================================================
def create_scrollable_frame(parent, resize_flag=None):
    """Create a scrollable frame with canvas + scrollbar + mousewheel binding.

    Returns (outer_frame, inner_frame, canvas).
    Pack outer_frame with fill='both', expand=True.
    Add widgets to inner_frame.

    resize_flag: optional list [bool] — when True, layout updates are deferred.
    """
    outer = ttk.Frame(parent)
    canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
    inner = ttk.Frame(canvas)

    # Debounce scrollregion recalc — fires once after layout settles
    _scroll_after = [None]

    def _set_scrollregion():
        bbox = canvas.bbox('all')
        if bbox:
            # Ensure scrollregion is at least as tall as the canvas so
            # content can't scroll when it fits within the visible area.
            canvas_h = canvas.winfo_height()
            region = (bbox[0], bbox[1], bbox[2], max(bbox[3], canvas_h))
            canvas.configure(scrollregion=region)

    def _update_scrollregion(e):
        if resize_flag and resize_flag[0]:
            return
        if _scroll_after[0] is not None:
            try:
                canvas.after_cancel(_scroll_after[0])
            except (ValueError, tk.TclError):
                pass
        _scroll_after[0] = canvas.after(50, _set_scrollregion)

    inner.bind('<Configure>', _update_scrollregion)
    canvas_window = canvas.create_window((0, 0), window=inner, anchor='nw')
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')
    style_tk_canvas(canvas)

    _resize_after = [None]
    _last_width = [0]

    def _on_canvas_configure(event):
        if event.width == _last_width[0]:
            return
        _last_width[0] = event.width
        if resize_flag and resize_flag[0]:
            return
        if _resize_after[0] is not None:
            try:
                canvas.after_cancel(_resize_after[0])
            except (ValueError, tk.TclError):
                pass
        _resize_after[0] = canvas.after(
            50, lambda w=event.width: canvas.itemconfig(canvas_window, width=w))
    canvas.bind('<Configure>', _on_canvas_configure)

    def _force_layout():
        w = canvas.winfo_width()
        if w > 1:
            canvas.itemconfig(canvas_window, width=w)
            _set_scrollregion()
    canvas._force_layout = _force_layout
    bind_canvas_mousewheel(canvas, inner)

    # Keyboard scrolling
    canvas.configure(takefocus=True)
    canvas.bind('<Up>', lambda e: canvas.yview_scroll(-1, 'units'))
    canvas.bind('<Down>', lambda e: canvas.yview_scroll(1, 'units'))
    canvas.bind('<Prior>', lambda e: canvas.yview_scroll(-1, 'pages'))
    canvas.bind('<Next>', lambda e: canvas.yview_scroll(1, 'pages'))
    canvas.bind('<Home>', lambda e: canvas.yview_moveto(0))
    canvas.bind('<End>', lambda e: canvas.yview_moveto(1.0))

    return outer, inner, canvas


# ============================================================================
# CANVAS MOUSEWHEEL SCROLLING
# ============================================================================
def disable_mousewheel_on_inputs(root):
    """Remove class-level mousewheel bindings from Spinbox, Combobox, and Scale.

    ttkbootstrap adds <MouseWheel> bindings to TSpinbox and TCombobox that
    intercept scroll events, changing widget values when the user is just
    trying to scroll the parent panel. Call once at startup.
    """
    root.unbind_class('TSpinbox', '<MouseWheel>')
    root.unbind_class('TCombobox', '<MouseWheel>')
    root.unbind_class('TScale', '<MouseWheel>')
    root.unbind_class('Scale', '<MouseWheel>')


# Set of canvas widgets registered for mousewheel scrolling.
# Used by the global handler to find which canvas to scroll.
_scrollable_canvases = set()


def _global_mousewheel_handler(event):
    """Global mousewheel handler that scrolls the correct canvas.

    Walks up the widget tree from the event target to find a registered
    scrollable canvas. This works even when the mouse is over child widgets
    (labels, frames, buttons, etc.) inside the scrollable area.
    """
    widget = event.widget
    # Walk up the widget tree looking for a registered scrollable canvas
    try:
        while widget is not None:
            if widget in _scrollable_canvases:
                # Only scroll if content overflows the visible area
                bbox = widget.bbox('all')
                if bbox and bbox[3] > widget.winfo_height():
                    widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return "break"
            widget = widget.master
    except (AttributeError, tk.TclError):
        pass


def bind_canvas_mousewheel(canvas, *extra_widgets):
    """Bind mousewheel scrolling to a canvas.

    Registers the canvas so the global mousewheel handler can find it.
    Scrolling works anywhere inside the canvas or its child widgets.
    Extra widgets parameter is accepted but ignored (kept for call-site convenience).
    """
    _scrollable_canvases.add(canvas)

    # Install the global handler once on the root window
    root = canvas.winfo_toplevel()
    if not getattr(root, '_mousewheel_handler_installed', False):
        root.bind_all('<MouseWheel>', _global_mousewheel_handler)
        root._mousewheel_handler_installed = True

    # Clean up when canvas is destroyed
    def _on_destroy(event):
        if event.widget is canvas:
            _scrollable_canvases.discard(canvas)
    canvas.bind('<Destroy>', _on_destroy)


# ============================================================================
# CUSTOM DARK MENU BAR
# ============================================================================
_DD_MIN_WIDTH = 200
_DD_BORDER_COLOR = '#444444'


class CustomMenuBar(tk.Canvas):
    """Dark-themed menu bar replacing native tk.Menu.

    Uses a Canvas for the bar (immune to ttkbootstrap theme overrides) and a
    place()-based Frame overlay for dropdowns (no Toplevel = no Windows flash).
    Supports accelerator text, separators, disabled items, keyboard nav, and Alt activation.
    """

    _MENU_BG = TK_COLORS['status_bg']      # #1a1a1a
    _MENU_FG = THEME_COLORS['body']         # #C0C7CE
    _MENU_HOVER_BG = '#2a2a2a'
    _MENU_ACTIVE_BG = '#333333'
    _MENU_DISABLED_FG = '#666666'
    _ACCEL_FG = THEME_COLORS['muted']       # #B0B0B0
    _SEP_COLOR = TK_COLORS['separator']     # #333333
    _FONT = FONT_BODY                       # ('Segoe UI', 9)
    _BAR_HEIGHT = 24

    def __init__(self, parent):
        super().__init__(
            parent, bg=self._MENU_BG, highlightthickness=0,
            height=self._BAR_HEIGHT,
        )
        self._cascades = []        # [(tag, x1, x2, menu_def), ...]
        self._dd_frame = None      # Dropdown overlay frame (placed on root)
        self._dd_inner = None      # Inner content frame
        self._open_index = -1      # Index of open cascade
        self._hover_index = -1     # Currently hovered cascade
        self._hover_mode = False   # After clicking, hover opens adjacent menus
        self._rows = []            # Rows in current dropdown (for keyboard nav)
        self._focused_row = -1     # Keyboard-focused row index
        self._click_bind_id = None # Stored bind ID for safe unbinding
        self._cursor_x = 6        # Next cascade label x position

        self.bind('<Button-1>', self._bar_click)
        self.bind('<Motion>', self._bar_motion)
        self.bind('<Leave>', self._bar_leave)

    def add_cascade(self, label, menu_def):
        """Add a top-level menu. Returns the menu_def list for later mutation."""
        text = f"  {label}  "
        tag = f"cascade_{len(self._cascades)}"
        tid = self.create_text(
            self._cursor_x, self._BAR_HEIGHT // 2,
            text=text, anchor='w', fill=self._MENU_FG, font=self._FONT,
            tags=(tag,),
        )
        bbox = self.bbox(tid)
        x1, x2 = bbox[0], bbox[2]
        self._cursor_x = x2
        idx = len(self._cascades)
        self._cascades.append((tag, x1, x2, menu_def))
        return menu_def

    def activate(self):
        """Standard Windows Alt behavior: open/close the first cascade."""
        if self._open_index >= 0:
            self._close_dropdown()
        else:
            self._open_at(0)

    # --- Canvas bar events ---

    def _hit_cascade(self, x):
        for i, (_, x1, x2, _) in enumerate(self._cascades):
            if x1 <= x <= x2:
                return i
        return -1

    def _bar_click(self, event):
        idx = self._hit_cascade(event.x)
        if idx < 0:
            return
        if self._open_index == idx:
            self._close_dropdown()
        else:
            self._open_at(idx)

    def _bar_motion(self, event):
        idx = self._hit_cascade(event.x)
        # Update hover highlight
        if idx != self._hover_index:
            if self._hover_index >= 0 and self._hover_index != self._open_index:
                self._draw_cascade_bg(self._hover_index, self._MENU_BG)
            self._hover_index = idx
            if idx >= 0 and idx != self._open_index:
                self._draw_cascade_bg(idx, self._MENU_HOVER_BG)
        # Hover-to-switch when a menu is open
        if self._hover_mode and self._open_index >= 0 and idx >= 0 and idx != self._open_index:
            self._open_at(idx)

    def _bar_leave(self, event):
        if self._hover_index >= 0 and self._hover_index != self._open_index:
            self._draw_cascade_bg(self._hover_index, self._MENU_BG)
        self._hover_index = -1

    def _draw_cascade_bg(self, idx, color):
        tag = f"cascade_bg_{idx}"
        self.delete(tag)
        if color != self._MENU_BG:
            _, x1, x2, _ = self._cascades[idx]
            self.create_rectangle(
                x1, 0, x2, self._BAR_HEIGHT,
                fill=color, outline='', tags=(tag,),
            )
            # Re-raise text above background rect
            text_tag = self._cascades[idx][0]
            self.tag_raise(text_tag)

    # --- Dropdown lifecycle ---

    def _ensure_dropdown(self):
        if self._dd_frame is not None:
            return
        root = self.winfo_toplevel()
        self._dd_frame = tk.Frame(root, bg=_DD_BORDER_COLOR)

    def _open_at(self, idx):
        self._ensure_dropdown()

        # Reset old cascade highlight
        if self._open_index >= 0:
            self._draw_cascade_bg(self._open_index, self._MENU_BG)

        _, x1, x2, menu_def = self._cascades[idx]
        self._open_index = idx
        self._hover_mode = True
        self._draw_cascade_bg(idx, self._MENU_ACTIVE_BG)

        # Clear old dropdown content
        if self._dd_inner:
            self._dd_inner.destroy()
        inner = tk.Frame(self._dd_frame, bg=self._MENU_BG)
        inner.pack(padx=1, pady=1)
        self._dd_inner = inner

        self._rows = []
        self._focused_row = -1

        for entry in menu_def:
            if entry['type'] == 'separator':
                tk.Frame(inner, bg=self._SEP_COLOR, height=1).pack(
                    fill='x', padx=6, pady=3)
                continue

            row = tk.Frame(inner, bg=self._MENU_BG)
            row.pack(fill='x', ipady=2)

            state = entry.get('state', 'normal')
            fg = self._MENU_FG if state == 'normal' else self._MENU_DISABLED_FG
            accel_fg = self._ACCEL_FG if state == 'normal' else self._MENU_DISABLED_FG

            text_lbl = tk.Label(
                row, text=f"  {entry['label']}", bg=self._MENU_BG, fg=fg,
                font=self._FONT, anchor='w',
            )
            text_lbl.pack(side='left', fill='x', expand=True, padx=(2, 0))

            accel = entry.get('accelerator')
            if accel:
                accel_lbl = tk.Label(
                    row, text=f"{accel}  ", bg=self._MENU_BG, fg=accel_fg,
                    font=FONT_SMALL, anchor='e',
                )
                accel_lbl.pack(side='right', padx=(12, 2))
            else:
                tk.Label(row, text="  ", bg=self._MENU_BG, font=FONT_SMALL).pack(
                    side='right', padx=(12, 2))

            cmd = entry.get('command') if state == 'normal' else None
            self._rows.append({'row': row, 'cmd': cmd, 'state': state})
            row_idx = len(self._rows) - 1

            if state == 'normal':
                for w in row.winfo_children():
                    w.bind('<Enter>', lambda e, ri=row_idx: self._on_row_enter(ri))
                    w.bind('<Leave>', lambda e, ri=row_idx: self._on_row_leave(ri))
                    w.bind('<Button-1>', lambda e, c=cmd: self._invoke(c))
                row.bind('<Enter>', lambda e, ri=row_idx: self._on_row_enter(ri))
                row.bind('<Leave>', lambda e, ri=row_idx: self._on_row_leave(ri))
                row.bind('<Button-1>', lambda e, c=cmd: self._invoke(c))

        # Enforce minimum width
        inner.update_idletasks()
        if inner.winfo_reqwidth() < _DD_MIN_WIDTH:
            inner.configure(width=_DD_MIN_WIDTH)
        self._dd_frame.update_idletasks()

        # Position dropdown below the cascade label using place() on root
        root = self.winfo_toplevel()
        bar_x = self.winfo_rootx() - root.winfo_rootx()
        bar_y = self.winfo_rooty() - root.winfo_rooty()
        dd_x = bar_x + x1
        dd_y = bar_y + self._BAR_HEIGHT
        self._dd_frame.place(x=dd_x, y=dd_y)
        self._dd_frame.lift()

        # Keyboard bindings
        root.bind('<Escape>', lambda e: self._close_dropdown())
        root.bind('<Up>', lambda e: self._nav_rows(-1))
        root.bind('<Down>', lambda e: self._nav_rows(1))
        root.bind('<Return>', lambda e: self._invoke_focused())
        root.bind('<Left>', lambda e: self._nav_cascade(-1))
        root.bind('<Right>', lambda e: self._nav_cascade(1))

        # Close on click outside (store bind ID for safe unbinding)
        if not self._click_bind_id:
            self._click_bind_id = root.bind('<Button-1>', self._on_root_click, add=True)

    def _on_root_click(self, event):
        if self._open_index < 0:
            return
        w = event.widget
        try:
            # Click on the menu bar canvas itself — handled by _bar_click
            if w is self:
                return
            # Click inside dropdown
            dd = self._dd_frame
            if dd:
                p = w
                while p:
                    if p is dd:
                        return
                    p = getattr(p, 'master', None)
        except tk.TclError:
            pass
        self._close_dropdown()

    def _close_dropdown(self):
        root = self.winfo_toplevel()
        if self._click_bind_id:
            try:
                root.unbind('<Button-1>', self._click_bind_id)
            except (tk.TclError, ValueError):
                pass
            self._click_bind_id = None

        for key in ('<Escape>', '<Up>', '<Down>', '<Return>', '<Left>', '<Right>'):
            try:
                root.unbind(key)
            except tk.TclError:
                pass

        if self._dd_frame:
            self._dd_frame.place_forget()
        if self._open_index >= 0:
            self._draw_cascade_bg(self._open_index, self._MENU_BG)
        self._open_index = -1
        self._hover_mode = False
        self._rows = []
        self._focused_row = -1

    # --- Row hover and keyboard navigation ---

    def _on_row_enter(self, row_idx):
        self._set_focused_row(row_idx)

    def _on_row_leave(self, row_idx):
        if self._focused_row == row_idx:
            self._highlight_row(self._rows[row_idx]['row'], False)
            self._focused_row = -1

    def _highlight_row(self, row, on):
        bg = self._MENU_HOVER_BG if on else self._MENU_BG
        row.configure(bg=bg)
        for child in row.winfo_children():
            child.configure(bg=bg)

    def _set_focused_row(self, row_idx):
        if 0 <= self._focused_row < len(self._rows):
            self._highlight_row(self._rows[self._focused_row]['row'], False)
        self._focused_row = row_idx
        if row_idx >= 0:
            self._highlight_row(self._rows[row_idx]['row'], True)

    def _nav_rows(self, direction):
        if not self._rows:
            return
        idx = self._focused_row
        for _ in range(len(self._rows)):
            idx = (idx + direction) % len(self._rows)
            if self._rows[idx]['state'] == 'normal':
                self._set_focused_row(idx)
                return

    def _invoke_focused(self):
        if 0 <= self._focused_row < len(self._rows):
            cmd = self._rows[self._focused_row].get('cmd')
            self._invoke(cmd)

    def _nav_cascade(self, direction):
        new_idx = (self._open_index + direction) % len(self._cascades)
        self._open_at(new_idx)

    # --- Invoke and configure ---

    def _invoke(self, cmd):
        self._close_dropdown()
        if cmd:
            self.after_idle(cmd)

    def entryconfigure(self, menu_def, index, **kw):
        """Update a menu entry. Mirrors tk.Menu.entryconfigure interface."""
        menu_def[index].update(kw)

