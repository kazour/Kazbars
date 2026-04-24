"""
Kaz Grids — Complex shared UI components.

DragReorderManager, ToastManager, CustomMenuBar, and the scrollable-frame
helper with its global mousewheel routing.
"""

import tkinter as tk
from tkinter import ttk

from .ui_helpers import (
    THEME_COLORS, TK_COLORS,
    FONT_SMALL, FONT_BODY,
    PAD_TAB, PAD_LF, PAD_XS,
)
from .ui_widgets import blend_alpha
from .ui_tk_style import style_tk_canvas


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
