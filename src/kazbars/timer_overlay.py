"""
Timer Overlay Module for KazBars
Transparent, always-on-top overlay window for displaying boss timer information.
"""

import logging
import tkinter as tk

from .live_tracker_settings import COLORS
from .ui_helpers import (
    FONT_FAMILY,
    FONT_SMALL,
    OVERLAY_COLORS,
    PAD_MICRO,
    PAD_SMALL,
    PAD_XS,
    THEME_COLORS,
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
    - Transparent background option
    - Configurable opacity and font size
    """

    # Visual constants
    TRANSPARENT_COLOR = OVERLAY_COLORS['transparent']
    BG_OUTER = OVERLAY_COLORS['bg_outer']
    BG_INNER = TK_COLORS['status_bg']
    BG_BORDER = TK_COLORS['separator']

    def __init__(self, root, settings, on_settings_changed=None):
        """
        Initialize the overlay window.

        Args:
            root: Parent Tk window
            settings: Dict with x, y, width, height, locked, transparent_bg, opacity, font_size
            on_settings_changed: Callback when position/settings change (for auto-save)
        """
        self.root = tk.Toplevel(root)
        self.root.title("KazBars Seed Timer")
        self._on_settings_changed = on_settings_changed

        # Load settings with defaults
        self.is_locked = settings.get('locked', False)
        self.is_visible = settings.get('visible', True)
        self.transparent_bg = settings.get('transparent_bg', False)
        self.opacity = settings.get('opacity', 0.90)
        self.font_size = settings.get('font_size', 11)
        self.overlay_width = settings.get('width', 210)
        self.overlay_height = settings.get('height', 75)

        # Window attributes
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', self.opacity)
        self.root.overrideredirect(True)
        self.root.attributes('-transparentcolor', self.TRANSPARENT_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent closing

        # Track widgets that need background updates
        self._bg_widgets = []

        # Position window
        x = settings.get('x', 0)
        y = settings.get('y', 50)

        # Center on screen on first run (no saved position yet)
        if not settings.get('positioned', False):
            self.root.update_idletasks()
            screen_w = self.root.winfo_screenwidth()
            x = screen_w // 2 - self.overlay_width // 2

        self.root.geometry(f'{self.overlay_width}x{self.overlay_height}+{x}+{y}')

        # Build UI
        self._build_ui()
        self._setup_dragging()
        self._apply_background()

        # Apply initial lock state
        if self.is_locked:
            self.lock_indicator.config(text="🔒")
            self.resize_handle.config(fg=self.BG_INNER)  # Hide
            self.root.after(100, lambda: self._set_click_through(True))
        else:
            self.lock_indicator.config(text="🔓")

        # Apply initial visibility
        if not self.is_visible:
            self.root.withdraw()

    def _build_ui(self):
        """Build the overlay UI structure."""
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

        # Message container
        self.msg_container = tk.Frame(self.frame, bg=self.BG_INNER)
        self.msg_container.pack(fill='both', expand=True, padx=PAD_XS, pady=PAD_MICRO)
        self._bg_widgets.append(('inner', self.msg_container))

        # Create the two message rows
        self._create_message_row(1)
        self._create_message_row(2)

        # Separator line
        self.separator = tk.Frame(self.frame, bg=self.BG_BORDER, height=1)
        self.separator.pack(fill='x', padx=PAD_XS, pady=PAD_MICRO)
        self._bg_widgets.append(('border', self.separator))

        # Cycle timer label (bottom)
        self.timer_label = tk.Label(
            self.frame, text="", font=(FONT_FAMILY, self.font_size + 4, 'bold'),
            fg=THEME_COLORS['muted'], bg=self.BG_INNER, padx=PAD_SMALL, pady=0, anchor='w'
        )
        self.timer_label.pack(fill='both', expand=True)
        self._bg_widgets.append(('inner', self.timer_label))

        # Lock indicator (bottom right, left of resize handle)
        self.lock_indicator = tk.Label(
            self.frame, text="", font=FONT_SMALL,
            fg=TK_COLORS['border'], bg=self.BG_INNER
        )
        self.lock_indicator.place(relx=1.0, rely=1.0, anchor='se', x=-18, y=-1)
        self._bg_widgets.append(('inner', self.lock_indicator))

        # Resize handle (bottom right corner)
        self.resize_handle = tk.Label(
            self.frame, text="◢", font=FONT_SMALL,
            fg=TK_COLORS['border'], bg=self.BG_INNER
        )
        self.resize_handle.place(relx=1.0, rely=1.0, anchor='se', x=-1, y=-1)
        self._bg_widgets.append(('inner', self.resize_handle))

    def _create_message_row(self, row_num):
        """Create a single message row with text, player, and timer labels."""
        frame = tk.Frame(self.msg_container, bg=self.BG_INNER)
        frame.pack(fill='x', pady=0)
        self._bg_widgets.append(('inner', frame))

        # Timer on right side
        timer_label = tk.Label(
            frame, text="", font=(FONT_FAMILY, self.font_size, 'bold'),
            fg=COLORS["default"], bg=self.BG_INNER, anchor='e', width=5
        )
        timer_label.pack(side='right')
        self._bg_widgets.append(('inner', timer_label))

        # Message frame (left side)
        msg_frame = tk.Frame(frame, bg=self.BG_INNER)
        msg_frame.pack(side='left', fill='x', expand=True)
        self._bg_widgets.append(('inner', msg_frame))

        # Text label
        initial_text = "Waiting for Seed..." if row_num == 1 else ""
        text_label = tk.Label(
            msg_frame, text=initial_text,
            font=(FONT_FAMILY, self.font_size, 'bold'),
            fg=COLORS["default"], bg=self.BG_INNER, anchor='w'
        )
        text_label.pack(side='left')
        self._bg_widgets.append(('inner', text_label))

        # Player name label
        player_label = tk.Label(
            msg_frame, text="",
            font=(FONT_FAMILY, self.font_size, 'bold'),
            fg=COLORS["player"], bg=self.BG_INNER, anchor='w'
        )
        player_label.pack(side='left')
        self._bg_widgets.append(('inner', player_label))

        # Store references
        setattr(self, f'row{row_num}_frame', frame)
        setattr(self, f'row{row_num}_msg_frame', msg_frame)
        setattr(self, f'row{row_num}_text', text_label)
        setattr(self, f'row{row_num}_player', player_label)
        setattr(self, f'row{row_num}_timer', timer_label)

    def _setup_dragging(self):
        """Set up drag and resize handlers."""
        self.drag_data = {'x': 0, 'y': 0}
        self.resize_data = {'x': 0, 'y': 0, 'width': 0, 'height': 0}

        # All draggable widgets
        draggable = [
            self.frame, self.msg_container,
            self.row1_frame, self.row1_msg_frame, self.row1_text,
            self.row1_player, self.row1_timer,
            self.row2_frame, self.row2_msg_frame, self.row2_text,
            self.row2_player, self.row2_timer, self.timer_label
        ]

        for widget in draggable:
            widget.bind('<Button-1>', self._start_drag)
            widget.bind('<B1-Motion>', self._on_drag)
            widget.bind('<ButtonRelease-1>', self._stop_drag)

        # Resize handle bindings
        self.resize_handle.bind('<Button-1>', self._start_resize)
        self.resize_handle.bind('<B1-Motion>', self._on_resize)
        self.resize_handle.bind('<ButtonRelease-1>', self._stop_resize)
        self.resize_handle.config(cursor='size_nw_se')

    def _start_drag(self, event):
        if not self.is_locked:
            self.drag_data['x'] = event.x
            self.drag_data['y'] = event.y

    def _on_drag(self, event):
        if not self.is_locked:
            x = self.root.winfo_x() + event.x - self.drag_data['x']
            y = self.root.winfo_y() + event.y - self.drag_data['y']
            self.root.geometry(f'+{x}+{y}')

    def _stop_drag(self, event):
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
            new_width = max(150, self.resize_data['width'] + delta_x)
            new_height = max(60, self.resize_data['height'] + delta_y)
            self.overlay_width = new_width
            self.overlay_height = new_height
            self.root.geometry(f'{new_width}x{new_height}')

    def _stop_resize(self, event):
        if not self.is_locked:
            self._notify_settings_changed()

    def _notify_settings_changed(self):
        """Notify parent that settings changed (for auto-save)."""
        if self._on_settings_changed:
            self._on_settings_changed()

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
        self.row1_text.config(text=row1_msg, fg=row1_color)
        self.row1_player.config(text=row1_player)
        self.row1_timer.config(text=row1_timer, fg=row1_color)

        self.row2_text.config(text=row2_msg, fg=row2_color)
        self.row2_player.config(text=row2_player)
        self.row2_timer.config(text=row2_timer, fg=row2_color)

        self.timer_label.config(
            text=cycle_timer if cycle_timer else "",
            fg=THEME_COLORS['muted']
        )

    def toggle_lock(self):
        """Toggle lock state (drag/click-through)."""
        self.is_locked = not self.is_locked
        if self.is_locked:
            self.lock_indicator.config(text="🔒", fg=TK_COLORS['border'])
            self.resize_handle.config(fg=self.BG_INNER)  # Hide
            self._set_click_through(True)
        else:
            self.lock_indicator.config(text="🔓", fg=TK_COLORS['border'])
            self.resize_handle.config(fg=TK_COLORS['border'])  # Show
            self._set_click_through(False)
        self._notify_settings_changed()

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
        except Exception:
            pass

    def set_transparent(self, transparent):
        """Toggle transparent background."""
        self.transparent_bg = transparent
        self._apply_background()
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
        """Set font size for all text (8 - 20)."""
        self.font_size = int(size)
        msg_font = (FONT_FAMILY, self.font_size, 'bold')
        timer_font = (FONT_FAMILY, self.font_size + 4, 'bold')

        self.row1_text.config(font=msg_font)
        self.row1_player.config(font=msg_font)
        self.row1_timer.config(font=msg_font)
        self.row2_text.config(font=msg_font)
        self.row2_player.config(font=msg_font)
        self.row2_timer.config(font=msg_font)
        self.timer_label.config(font=timer_font)
        self._notify_settings_changed()

    def show(self):
        """Show the overlay window."""
        self.is_visible = True
        self.root.deiconify()
        self._notify_settings_changed()

    def hide(self):
        """Hide the overlay window."""
        self.is_visible = False
        self.root.withdraw()
        self._notify_settings_changed()

    def destroy(self):
        """Destroy the overlay window."""
        try:
            self.root.destroy()
        except (tk.TclError, AttributeError):
            pass

    def apply_settings(self, settings):
        """Apply a settings dict to the overlay (used by profile load)."""
        self.set_opacity(settings.get('opacity', 0.9))
        self.set_font_size(settings.get('font_size', 11))
        self.set_transparent(settings.get('transparent_bg', False))
        if settings.get('locked', False) != self.is_locked:
            self.toggle_lock()
        x = settings.get('x', self.root.winfo_x())
        y = settings.get('y', self.root.winfo_y())
        self.root.geometry(f"+{x}+{y}")

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
