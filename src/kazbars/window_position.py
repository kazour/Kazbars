"""
KazBars — Window position persistence.

Save and restore window geometry (position + optional size) via the app's
SettingsManager, clamping to the screen so no window ever opens off-visible.
"""

import tkinter as tk

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
