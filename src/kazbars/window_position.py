"""
KazBars — Window position persistence.

Save and restore window geometry (position + optional size) via the settings
proxy, clamping to the screen so no window ever opens off-visible. Geometry for
all windows lives under the single ``window_positions`` prefs field keyed by
window name (a strict Schema can't enumerate per-window keys), not N top-level
``window_pos_*`` keys.
"""

import tkinter as tk

from .settings_manager import get_setting, set_setting


def clamp_to_screen(x, y, width, height):
    """Clamp (x, y) to the work area of the monitor nearest the target rect.

    Multi-monitor aware: positions on secondary monitors are preserved, and a
    position on a now-disconnected monitor snaps to the nearest live one. Uses
    the monitor work area so a window never opens under the taskbar. Falls back
    to a primary-screen clamp if win32 is unavailable.
    """
    try:
        import win32api
        import win32con

        rect = (int(x), int(y), int(x + width), int(y + height))
        hmon = win32api.MonitorFromRect(rect, win32con.MONITOR_DEFAULTTONEAREST)
        left, top, right, bottom = win32api.GetMonitorInfo(hmon)["Work"]
        x = max(left, min(x, right - width))
        y = max(top, min(y, bottom - height))
        return x, y
    except Exception:
        try:
            root = tk._default_root
            screen_w = root.winfo_screenwidth() if root else 1920
            screen_h = root.winfo_screenheight() if root else 1080
        except (tk.TclError, AttributeError):
            screen_w, screen_h = 1920, 1080
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height - 50))
        return x, y


def save_window_position(window_name, x, y, width=None, height=None):
    """Persist a window's position and optional size into the shared
    ``window_positions`` prefs dict, keyed by window name."""
    pos_data = {'x': x, 'y': y}
    if width is not None:
        pos_data['width'] = width
    if height is not None:
        pos_data['height'] = height
    positions = dict(get_setting('window_positions') or {})
    positions[window_name] = pos_data
    set_setting('window_positions', positions)


def restore_window_position(window, window_name, default_width, default_height, parent=None, resizable=True, offset=(0, 0)):
    """Restore a window's saved position and size, or center it as a fallback.

    `offset` nudges the first-launch centered position (no effect once a
    position is saved) — used to stagger sibling panels so they don't spawn
    exactly on top of each other.
    """
    pos_data = (get_setting('window_positions') or {}).get(window_name)

    if pos_data:
        x = pos_data.get('x', 0)
        y = pos_data.get('y', 0)
        width = pos_data.get('width', default_width) if resizable else default_width
        height = pos_data.get('height', default_height) if resizable else default_height
    else:
        width, height = default_width, default_height
        if parent:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2 + offset[0]
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2 + offset[1]
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
