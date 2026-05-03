"""
Timer Overlay Module for KazBars
Transparent, always-on-top overlay window for displaying boss timer information.
"""

import logging
import tkinter as tk

from .live_tracker_settings import COLORS, TIMERS_DEFAULTS
from .ui_helpers import (
    FONT_FAMILY,
    FONT_SMALL,
    OVERLAY_COLORS,
    PAD_MICRO,
    PAD_SMALL,
    PAD_XS,
    TK_COLORS,
)

logger = logging.getLogger(__name__)

# Optional win32 import for click-through functionality
try:
    import win32con
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class TimerOverlay:
    """
    Transparent overlay window for displaying Ethram-Fal timer phases.

    Features:
    - Always-on-top display
    - Draggable when unlocked
    - Resizable via corner handle
    - Click-through when locked (requires pywin32)
    - Transparent background option (text rendered with outline stroke for
      readability over arbitrary game scenes)
    - Configurable opacity and font size
    """

    # Visual constants. BG_OUTER doubles as the text outline color.
    TRANSPARENT_COLOR = OVERLAY_COLORS['transparent']
    BG_OUTER = OVERLAY_COLORS['bg_outer']
    BG_INNER = TK_COLORS['status_bg']
    BG_BORDER = TK_COLORS['separator']

    # Lock indicator glyphs — monochrome, render consistently in Segoe UI.
    LOCK_GLYPH = '●'    # Black circle
    UNLOCK_GLYPH = '○'  # White circle

    # Resize handle placement (relative to bottom-right of inner frame)
    RESIZE_HANDLE_PLACE = {'relx': 1.0, 'rely': 1.0, 'anchor': 'se', 'x': -1, 'y': -1}
    LOCK_INDICATOR_PLACE = {'relx': 1.0, 'rely': 1.0, 'anchor': 'se', 'x': -18, 'y': -1}

    # Minimum width is fixed; minimum height scales with font (see _min_height).
    MIN_WIDTH = 150

    def __init__(self, root, settings, on_settings_changed=None):
        """
        Initialize the overlay window.

        Args:
            root: Parent Tk window
            settings: Dict with x, y, width, height, locked, transparent_bg, opacity, font_size
            on_settings_changed: Callback when position/settings change (for auto-save)
        """
        self.root = tk.Toplevel(root)
        self._on_settings_changed = on_settings_changed
        self._suspend_notify = False

        # Load settings — fall back to TIMERS_DEFAULTS so the source of truth is single
        self.is_visible = settings.get('visible', TIMERS_DEFAULTS['visible'])
        self.transparent_bg = settings.get('transparent_bg', TIMERS_DEFAULTS['transparent_bg'])
        self.opacity = settings.get('opacity', TIMERS_DEFAULTS['opacity'])
        self.font_size = settings.get('font_size', TIMERS_DEFAULTS['font_size'])
        self.overlay_width = settings.get('width', TIMERS_DEFAULTS['width'])
        self.overlay_height = settings.get('height', TIMERS_DEFAULTS['height'])
        # Lock state is applied via set_locked() at the end of __init__ so the
        # state machine path runs (UI sync + click-through arming).
        self.is_locked = False

        # Window attributes
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', self.opacity)
        self.root.overrideredirect(True)  # title() unused — no title bar
        self.root.attributes('-transparentcolor', self.TRANSPARENT_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self._block_close)

        # Track widgets that need background updates
        self._bg_widgets = []

        # Last-known display state, used to repaint the canvas on resize/theme change
        self._display_state = {
            'row1_msg': "Waiting for Seed...",
            'row1_player': "", 'row1_timer': "", 'row1_color': COLORS["default"],
            'row2_msg': "", 'row2_player': "", 'row2_timer': "",
            'row2_color': COLORS["default"],
            'cycle_timer': "",
        }

        # Position window
        x = settings.get('x', TIMERS_DEFAULTS['x'])
        y = settings.get('y', TIMERS_DEFAULTS['y'])
        if not settings.get('positioned', False):
            self.root.update_idletasks()
            screen_w = self.root.winfo_screenwidth()
            x = screen_w // 2 - self.overlay_width // 2

        self.root.geometry(f'{self.overlay_width}x{self.overlay_height}+{x}+{y}')

        # Build UI
        self._build_ui()
        self._setup_dragging()
        self._apply_background()

        # Apply initial lock state via set_locked so click-through arms via after_idle
        target_locked = settings.get('locked', TIMERS_DEFAULTS['locked'])
        if target_locked:
            self._suspend_notify = True
            try:
                self.set_locked(True)
            finally:
                self._suspend_notify = False
        else:
            # Set the indicator glyph for the initial unlocked state.
            self.lock_indicator.config(text=self.UNLOCK_GLYPH)

        # Apply initial visibility
        if not self.is_visible:
            self.root.withdraw()

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        """Build the overlay UI structure.

        Layout (pack with side='bottom' for the bottom dock):
          ┌──────────────────────────┐
          │ text_canvas (top, fills) │  rows 1+2
          │ ──── separator (1px) ─── │
          │ cycle_timer_canvas       │  cycle timer + chrome (lock, resize)
          └──────────────────────────┘
        text_canvas and cycle_timer_canvas are discrete widgets, so the
        cycle timer can never overlap the messages on resize.
        """
        self.root.config(bg=self.TRANSPARENT_COLOR)

        # Outer container
        self.container = tk.Frame(self.root, bg=self.BG_OUTER, bd=0)
        self.container.pack(fill='both', expand=True)
        self._bg_widgets.append(('outer', self.container))

        # Inner frame with border
        self.frame = tk.Frame(
            self.container, bg=self.BG_INNER, bd=1, relief='flat',
            highlightthickness=1, highlightbackground=self.BG_BORDER
        )
        self.frame.pack(fill='both', expand=True, padx=PAD_MICRO, pady=PAD_MICRO)
        self._bg_widgets.append(('inner', self.frame))

        # === BOTTOM: cycle timer canvas (docked, fixed height). Hosts the
        # cycle timer text plus the chrome (lock indicator, resize handle).
        self.cycle_timer_canvas = tk.Canvas(
            self.frame, bg=self.BG_INNER, bd=0, highlightthickness=0,
            height=self._cycle_timer_height()
        )
        self.cycle_timer_canvas.pack(side='bottom', fill='x',
                                     padx=PAD_XS, pady=(0, PAD_MICRO))
        self._bg_widgets.append(('inner', self.cycle_timer_canvas))
        self.cycle_timer_canvas.bind('<Configure>', self._on_cycle_canvas_resize)

        # === MIDDLE: 1px separator frame, docked above the cycle timer.
        self.separator = tk.Frame(self.frame, bg=self.BG_BORDER, height=1)
        self.separator.pack(side='bottom', fill='x', padx=PAD_XS)
        self._bg_widgets.append(('border', self.separator))

        # === TOP: message canvas (fills remaining vertical space).
        self.text_canvas = tk.Canvas(
            self.frame, bg=self.BG_INNER, bd=0, highlightthickness=0
        )
        self.text_canvas.pack(side='top', fill='both', expand=True,
                              padx=PAD_XS, pady=(PAD_MICRO, 0))
        self._bg_widgets.append(('inner', self.text_canvas))
        self.text_canvas.bind('<Configure>', self._on_text_canvas_resize)

        # Chrome lives on the cycle_timer_canvas so it's naturally docked
        # bottom-right, never colliding with the message rows.
        self.lock_indicator = tk.Label(
            self.cycle_timer_canvas, text="", font=FONT_SMALL,
            fg=TK_COLORS['border'], bg=self.BG_INNER, cursor='hand2'
        )
        self.lock_indicator.place(**self.LOCK_INDICATOR_PLACE)
        self.lock_indicator.bind('<Button-1>', self._on_lock_click)
        self._bg_widgets.append(('inner', self.lock_indicator))

        self.resize_handle = tk.Label(
            self.cycle_timer_canvas, text="◢", font=FONT_SMALL,
            fg=TK_COLORS['border'], bg=self.BG_INNER
        )
        self.resize_handle.place(**self.RESIZE_HANDLE_PLACE)
        self._bg_widgets.append(('inner', self.resize_handle))

    def _cycle_timer_height(self):
        """Pixel height of the docked cycle-timer canvas. Scales with font."""
        return self.font_size + 14

    def _row_line_height(self):
        """Vertical space per message row. Mirrors the formula in
        _redraw_text_canvas so layout math stays in one place."""
        return max(self.font_size + 9, int(self.font_size * 1.6))

    def _min_height(self):
        """Minimum overlay height for the current font size: cycle dock +
        separator + two rows + frame chrome. Prevents resize from squashing
        the layout below something readable."""
        rows = 2 * self._row_line_height() + 6  # rows + top/bottom pad
        chrome = 8  # 1px frame border × 2 + 1px pad × 2 + safety
        return self._cycle_timer_height() + 1 + rows + chrome

    def _setup_dragging(self):
        """Set up drag and resize handlers."""
        self.drag_data = {'x': 0, 'y': 0}
        self.resize_data = {'x': 0, 'y': 0, 'width': 0, 'height': 0}

        # Drag works from the inner frame and either canvas surface.
        for widget in (self.frame, self.text_canvas, self.cycle_timer_canvas):
            widget.bind('<Button-1>', self._start_drag)
            widget.bind('<B1-Motion>', self._on_drag)
            widget.bind('<ButtonRelease-1>', self._stop_drag)

        # Resize handle bindings
        self.resize_handle.bind('<Button-1>', self._start_resize)
        self.resize_handle.bind('<B1-Motion>', self._on_resize)
        self.resize_handle.bind('<ButtonRelease-1>', self._stop_resize)
        self.resize_handle.config(cursor='size_nw_se')

    # =========================================================================
    # CANVAS RENDERING
    # =========================================================================

    def _on_text_canvas_resize(self, _event):
        self._redraw_text_canvas()

    def _on_cycle_canvas_resize(self, _event):
        self._redraw_cycle_timer()

    def _redraw(self):
        """Repaint both canvases from the last-known display state."""
        self._redraw_text_canvas()
        self._redraw_cycle_timer()

    def _redraw_text_canvas(self):
        """Repaint message rows 1 and 2."""
        c = self.text_canvas
        c.delete('all')
        s = self._display_state

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return  # Canvas not realized yet — next <Configure> redraws

        msg_font = (FONT_FAMILY, self.font_size, 'bold')

        line_h = self._row_line_height()

        pad_top = 3
        row1_y = pad_top
        row2_y = row1_y + line_h

        self._draw_row(c, row1_y, s['row1_msg'], s['row1_player'], s['row1_timer'],
                       s['row1_color'], msg_font, w)
        self._draw_row(c, row2_y, s['row2_msg'], s['row2_player'], s['row2_timer'],
                       s['row2_color'], msg_font, w)

    def _redraw_cycle_timer(self):
        """Repaint the cycle timer in its docked canvas."""
        c = self.cycle_timer_canvas
        c.delete('all')
        s = self._display_state

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4 or h < 4:
            return

        if not s['cycle_timer']:
            return

        timer_font = (FONT_FAMILY, self.font_size + 4, 'bold')
        # Anchor west: vertically centered, left-aligned. Tracker palette only.
        self._draw_text(c, PAD_SMALL, h // 2, s['cycle_timer'],
                        COLORS["default"], timer_font, anchor='w')

    def _draw_row(self, canvas, y, msg, player, timer_text, color, font, width):
        """Render one row: left-aligned message + player, right-aligned timer."""
        if timer_text:
            self._draw_text(canvas, width - 2, y, timer_text, color, font, anchor='ne')
        if msg:
            msg_id = self._draw_text(canvas, PAD_XS, y, msg, color, font, anchor='nw')
            if player and msg_id is not None:
                bbox = canvas.bbox(msg_id)
                player_x = bbox[2] if bbox else PAD_XS
                self._draw_text(canvas, player_x, y, player,
                                COLORS["player"], font, anchor='nw')
        elif player:
            self._draw_text(canvas, PAD_XS, y, player,
                            COLORS["player"], font, anchor='nw')

    def _draw_text(self, canvas, x, y, text, color, font, anchor='nw'):
        """Render a text element on the canvas. When transparent_bg is on, an
        8-direction outline in BG_OUTER is drawn behind it for legibility
        over arbitrary game scenes."""
        if not text:
            return None
        if self.transparent_bg:
            for dx, dy in ((-1, -1), (0, -1), (1, -1),
                           (-1,  0),          (1,  0),
                           (-1,  1), (0,  1), (1,  1)):
                canvas.create_text(x + dx, y + dy, text=text, fill=self.BG_OUTER,
                                   font=font, anchor=anchor)
        return canvas.create_text(x, y, text=text, fill=color,
                                  font=font, anchor=anchor)

    # =========================================================================
    # DRAG / RESIZE
    # =========================================================================

    def _start_drag(self, event):
        if not self.is_locked:
            self.drag_data['x'] = event.x
            self.drag_data['y'] = event.y

    def _on_drag(self, event):
        if not self.is_locked:
            x = self.root.winfo_x() + event.x - self.drag_data['x']
            y = self.root.winfo_y() + event.y - self.drag_data['y']
            self.root.geometry(f'+{x}+{y}')

    def _stop_drag(self, _event):
        if not self.is_locked:
            self._notify_settings_changed()

    def _start_resize(self, event):
        if not self.is_locked:
            self.resize_data['x'] = event.x_root
            self.resize_data['y'] = event.y_root
            self.resize_data['width'] = self.root.winfo_width()
            self.resize_data['height'] = self.root.winfo_height()

    def _on_resize(self, event):
        if not self.is_locked:
            delta_x = event.x_root - self.resize_data['x']
            delta_y = event.y_root - self.resize_data['y']
            new_width = max(self.MIN_WIDTH, self.resize_data['width'] + delta_x)
            new_height = max(self._min_height(), self.resize_data['height'] + delta_y)
            self.overlay_width = new_width
            self.overlay_height = new_height
            self.root.geometry(f'{new_width}x{new_height}')

    def _stop_resize(self, _event):
        if not self.is_locked:
            self._notify_settings_changed()

    def _notify_settings_changed(self):
        """Notify parent that settings changed (for auto-save). Skipped while
        a batch operation suspends notifications."""
        if self._suspend_notify:
            return
        if self._on_settings_changed:
            self._on_settings_changed()

    def _block_close(self):
        """No-op WM_DELETE_WINDOW handler — overlay can't be closed via the
        window manager; only the panel can hide or destroy it."""

    def _on_lock_click(self, _event):
        self.toggle_lock()

    def _arm_click_through_on(self):
        """Apply click-through after the window is realized (called via after_idle)."""
        self._set_click_through(True)

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    def update_display(self, row1_msg, row1_player, row1_timer, row1_color,
                       row2_msg, row2_player, row2_timer, row2_color, cycle_timer):
        """
        Update all display elements.

        Args:
            row1_msg: Text for row 1 (e.g., "Seed: ")
            row1_player: Player name for row 1
            row1_timer: Timer text for row 1 (e.g., "3s")
            row1_color: Color for row 1 text
            row2_msg: Text for row 2
            row2_player: Player name for row 2
            row2_timer: Timer text for row 2
            row2_color: Color for row 2 text
            cycle_timer: Overall cycle timer (e.g., "25s")
        """
        new_state = {
            'row1_msg': row1_msg, 'row1_player': row1_player,
            'row1_timer': row1_timer, 'row1_color': row1_color,
            'row2_msg': row2_msg, 'row2_player': row2_player,
            'row2_timer': row2_timer, 'row2_color': row2_color,
            'cycle_timer': cycle_timer,
        }
        # Boss timer pushes state every 50ms; skip the redraw when the integer
        # second hasn't ticked, ~9 of every 10 calls in steady state.
        if new_state == self._display_state:
            return
        self._display_state = new_state
        self._redraw()

    def set_locked(self, locked):
        """Set lock state to a target (idempotent). Updates UI and click-through."""
        if locked == self.is_locked:
            return
        self.is_locked = locked
        if locked:
            self.lock_indicator.config(text=self.LOCK_GLYPH, fg=TK_COLORS['border'])
            self.resize_handle.place_forget()
            # Defer click-through enable until the window is realized.
            self.root.after_idle(self._arm_click_through_on)
        else:
            self.lock_indicator.config(text=self.UNLOCK_GLYPH, fg=TK_COLORS['border'])
            self.resize_handle.place(**self.RESIZE_HANDLE_PLACE)
            self._set_click_through(False)
        self._notify_settings_changed()

    def toggle_lock(self):
        """Toggle lock state."""
        self.set_locked(not self.is_locked)

    def _set_click_through(self, enabled):
        """Enable/disable click-through (requires pywin32)."""
        if not HAS_WIN32:
            return
        try:
            hwnd = win32gui.GetParent(self.root.winfo_id())
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if enabled:
                ex_style |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
            else:
                ex_style &= ~win32con.WS_EX_TRANSPARENT
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
        except Exception as e:
            logger.warning("Failed to set click-through: %s", e)

    def set_transparent(self, transparent):
        """Toggle transparent background."""
        self.transparent_bg = transparent
        self._apply_background()
        self._redraw()  # Stroke layer toggles with this state
        self._notify_settings_changed()

    def _apply_background(self):
        """Apply current background mode to all widgets."""
        if self.transparent_bg:
            outer_color = self.TRANSPARENT_COLOR
            inner_color = self.TRANSPARENT_COLOR
            border_color = self.TRANSPARENT_COLOR
        else:
            outer_color = self.BG_OUTER
            inner_color = self.BG_INNER
            border_color = self.BG_BORDER

        for widget_type, widget in self._bg_widgets:
            try:
                if widget_type == 'outer':
                    widget.config(bg=outer_color)
                elif widget_type == 'inner':
                    widget.config(bg=inner_color)
                elif widget_type == 'border':
                    widget.config(bg=border_color)
            except (tk.TclError, AttributeError):
                pass

        try:
            if self.transparent_bg:
                self.frame.config(
                    highlightbackground=self.TRANSPARENT_COLOR,
                    highlightthickness=0
                )
            else:
                self.frame.config(
                    highlightbackground=border_color,
                    highlightthickness=1
                )
        except (tk.TclError, AttributeError):
            pass

    def set_opacity(self, value):
        """Set overlay opacity (0.3 - 1.0)."""
        self.opacity = float(value)
        self.root.attributes('-alpha', self.opacity)
        self._notify_settings_changed()

    def set_font_size(self, size):
        """Set font size for all text (8 - 20). Resizes the cycle-timer dock,
        re-clamps overlay height to the new minimum if needed, and repaints
        both canvases."""
        self.font_size = int(size)
        self.cycle_timer_canvas.config(height=self._cycle_timer_height())
        min_h = self._min_height()
        if self.overlay_height < min_h:
            self.overlay_height = min_h
            self.root.geometry(f'{self.overlay_width}x{self.overlay_height}')
        self._redraw()
        self._notify_settings_changed()

    def show(self, notify=True):
        """Show the overlay window. Pass notify=False when the call is a UI
        nudge that shouldn't overwrite a saved visibility preference
        (e.g., the panel force-showing on launch)."""
        self.is_visible = True
        self.root.deiconify()
        if notify:
            self._notify_settings_changed()

    def hide(self, notify=True):
        """Hide the overlay window. notify=False has the same semantics as show."""
        self.is_visible = False
        self.root.withdraw()
        if notify:
            self._notify_settings_changed()

    def destroy(self):
        """Destroy the overlay window."""
        try:
            self.root.destroy()
        except (tk.TclError, AttributeError):
            pass

    def apply_settings(self, settings):
        """Apply a settings dict to the overlay (used by profile load).

        Suspends per-setter notifications so the cascade saves once at the end
        instead of N times.
        """
        self._suspend_notify = True
        try:
            self.set_opacity(settings.get('opacity', TIMERS_DEFAULTS['opacity']))
            self.set_font_size(settings.get('font_size', TIMERS_DEFAULTS['font_size']))
            self.set_transparent(settings.get('transparent_bg', TIMERS_DEFAULTS['transparent_bg']))
            self.set_locked(settings.get('locked', TIMERS_DEFAULTS['locked']))
            if settings.get('visible', TIMERS_DEFAULTS['visible']):
                self.show()
            else:
                self.hide()
            x = settings.get('x', self.root.winfo_x())
            y = settings.get('y', self.root.winfo_y())
            width = max(self.MIN_WIDTH, settings.get('width', self.overlay_width))
            height = max(self._min_height(), settings.get('height', self.overlay_height))
            self.overlay_width = width
            self.overlay_height = height
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        finally:
            self._suspend_notify = False
        self._notify_settings_changed()

    def get_settings(self):
        """
        Get current overlay settings dict.

        Returns:
            dict: Current position, size, and state settings
        """
        return {
            'x': self.root.winfo_x(),
            'y': self.root.winfo_y(),
            'width': self.overlay_width,
            'height': self.overlay_height,
            'locked': self.is_locked,
            'transparent_bg': self.transparent_bg,
            'opacity': self.opacity,
            'font_size': self.font_size,
            'visible': self.is_visible,
            'positioned': True,
        }
