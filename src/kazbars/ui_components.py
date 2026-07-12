"""
KazBars — Complex shared UI components.

DragReorderManager, ToastManager, and the scrollable-frame helper with its
global mousewheel routing. (CustomMenuBar lives in custom_menu_bar.py.)
"""

import tkinter as tk
from tkinter import ttk

from .ui_helpers import (
    FONT_SMALL,
    PAD_LF,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_tk_style import style_tk_canvas
from .ui_widgets import blend_alpha


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
class _Toast:
    """One notification's state. The renderer hangs its Tk frame on `widget`;
    the model never touches it."""

    def __init__(self, message, style, duration, key, on_click):
        self.message = message
        self.style = style
        self.duration = duration
        self.key = key
        self.on_click = on_click
        self.exiting = False
        self.widget = None


class ToastModel:
    """Pure-state core of the toast system: arrival order, coalesce-by-key,
    the visible cap, the overflow queue, and two-tier priority. No Tk —
    ToastManager renders against it, tests drive it headlessly."""

    MAX_VISIBLE = 3
    HIGH_PRIORITY = ('warning', 'danger', 'error')
    DEFAULT_DURATIONS = {'info': 4, 'success': 4, 'warning': 6, 'danger': 8, 'error': 8}

    def __init__(self):
        self.visible = []  # arrival order, newest last; exiting toasts hold their slot
        self.queued = []   # overflow FIFO, high-priority styles ahead of low

    def show(self, message, style='info', duration=None, key=None, on_click=None):
        """Returns ('coalesced'|'visible'|'queued', toast). 'coalesced' updated
        an existing record in place; 'visible' needs mounting; 'queued' waits
        for remove() to free a slot."""
        if duration is None:
            duration = self.DEFAULT_DURATIONS.get(style, 6)
        if key is not None:
            live = next((t for t in self.visible if t.key == key and not t.exiting), None)
            if live is not None:
                live.message = message
                live.duration = duration
                return 'coalesced', live
            waiting = next((t for t in self.queued if t.key == key), None)
            if waiting is not None:
                waiting.message = message
                waiting.duration = duration
                return 'queued', waiting
        toast = _Toast(message, style, duration, key, on_click)
        if len(self.visible) < self.MAX_VISIBLE:
            self.visible.append(toast)
            return 'visible', toast
        self._enqueue(toast)
        return 'queued', toast

    def _enqueue(self, toast):
        if toast.style in self.HIGH_PRIORITY:
            idx = next((i for i, t in enumerate(self.queued)
                        if t.style not in self.HIGH_PRIORITY), len(self.queued))
            self.queued.insert(idx, toast)
        else:
            self.queued.append(toast)

    def start_exit(self, toast):
        """Begin dismissal: the toast keeps its slot until remove(), but no
        longer coalesces."""
        toast.exiting = True

    def remove(self, toast):
        """Drop a toast and promote queued ones into freed slots.
        Returns the newly visible toasts (for the renderer to mount)."""
        if toast in self.visible:
            self.visible.remove(toast)
        promoted = []
        while self.queued and len(self.visible) < self.MAX_VISIBLE:
            t = self.queued.pop(0)
            self.visible.append(t)
            promoted.append(t)
        return promoted

    @staticmethod
    def slot_offsets(heights, base, gap):
        """Bottom-anchored stack offsets. `heights` ordered oldest→newest;
        returns each toast's bottom-edge distance from the parent's bottom
        (newest sits at `base`, older ones step up by height + gap)."""
        offsets = []
        off = base
        for h in reversed(heights):
            offsets.append(off)
            off += h + gap
        offsets.reverse()
        return offsets


class ToastManager:
    """Tk renderer for ToastModel: toast frames stacked bottom-right of a
    parent widget, slide-up entrance, color-fade exit.

    All placement flows through _layout(), the single layout authority. It
    measures only after update_idletasks — a frame's requested size is
    computed at idle, so reading it earlier returns 1 and stacks toasts on
    top of each other — and places each frame at its model slot plus the
    frame's own animation offset, so a relayout mid-slide is harmless.

    Hover pauses the dismiss timer (restarts at full duration on leave);
    click runs on_click if set, then dismisses.
    """

    STYLES = {
        'info':    'accent',
        'success': 'success',
        'warning': 'warning',
        'error':   'danger',
        'danger':  'danger',
    }

    _SLIDE_STEPS = 6       # entrance animation frames
    _SLIDE_MS = 16          # ms between entrance frames
    _FADE_STEPS = 14        # exit animation frames
    _FADE_MS = 30           # ms between exit frames (~420ms total fade)

    def __init__(self, parent):
        self._parent = parent
        self._model = ToastModel()

    def show(self, message, style='info', duration=None, on_click=None, key=None):
        state, toast = self._model.show(message, style, duration, key, on_click)
        if state == 'coalesced':
            toast.widget.message_label.configure(text=toast.message)
            self._reset_exit_timer(toast)
            self._layout()
        elif state == 'visible':
            self._mount(toast)
        # 'queued': mounted later, when remove() promotes it

    def _mount(self, toast):
        color = THEME_COLORS.get(self.STYLES.get(toast.style, 'accent'),
                                 THEME_COLORS['accent'])
        frame = tk.Frame(self._parent, bg=TK_COLORS['input_bg'],
                         highlightbackground=TK_COLORS['border'],
                         highlightcolor=TK_COLORS['border'], highlightthickness=1)
        accent_bar = tk.Frame(frame, bg=color, width=3)
        accent_bar.pack(side='left', fill='y')
        label = ttk.Label(frame, text=toast.message, font=FONT_SMALL,
                          foreground=THEME_COLORS['body'],
                          background=TK_COLORS['input_bg'],
                          wraplength=360, justify='left')
        label.pack(side='left', padx=(PAD_LF, PAD_TAB), pady=PAD_XS)

        frame.message_label = label
        frame.accent_color = color
        frame.exit_after_id = None
        frame.hovered = False
        toast.widget = frame

        for w in (frame, accent_bar, label):
            if toast.on_click:
                w.configure(cursor='hand2')
            w.bind('<Button-1>', lambda _e: self._on_click(toast))
            w.bind('<Enter>', lambda _e: self._on_hover(toast, True))
            w.bind('<Leave>', lambda _e: self._on_hover(toast, False))

        self._parent.update_idletasks()  # real reqheight before first placement
        frame.anim_offset = frame.winfo_reqheight() + PAD_TAB
        self._layout()
        self._animate_entrance(toast)
        self._schedule_exit(toast)

    def _on_click(self, toast):
        if toast.on_click is not None:
            toast.on_click()
        self._begin_exit(toast)

    def _on_hover(self, toast, inside):
        toast.widget.hovered = inside
        if inside:
            self._cancel_exit_timer(toast)
        elif not toast.exiting:
            self._schedule_exit(toast)

    def _schedule_exit(self, toast):
        frame = toast.widget
        if frame.hovered:
            return  # paused; rescheduled on <Leave>
        frame.exit_after_id = frame.after(
            toast.duration * 1000, lambda: self._begin_exit(toast))

    def _cancel_exit_timer(self, toast):
        frame = toast.widget
        if frame.exit_after_id is not None:
            frame.after_cancel(frame.exit_after_id)
            frame.exit_after_id = None

    def _reset_exit_timer(self, toast):
        self._cancel_exit_timer(toast)
        self._schedule_exit(toast)

    def _begin_exit(self, toast):
        if toast.exiting:
            return
        self._model.start_exit(toast)
        self._cancel_exit_timer(toast)
        self._animate_exit(toast)

    def _layout(self):
        """Single layout authority: measure, compute slots, place, restack."""
        try:
            self._parent.update_idletasks()
            toasts = [t for t in self._model.visible if t.widget is not None]
            heights = [t.widget.winfo_reqheight() for t in toasts]
            offsets = ToastModel.slot_offsets(heights, PAD_TAB, PAD_XS)
            for toast, offset in zip(toasts, offsets):
                toast.widget.slot_y = -offset
                self._place(toast.widget)
                toast.widget.lift()  # oldest→newest order: newest ends on top
        except tk.TclError:
            pass

    def _place(self, frame):
        frame.place(relx=1.0, rely=1.0, anchor='se',
                    x=-PAD_TAB, y=frame.slot_y + frame.anim_offset)

    def _animate_entrance(self, toast):
        """Slide up from below the slot: eases the frame's anim_offset to 0,
        re-placing against the current slot each step so a mid-slide relayout
        (another toast arriving) is respected instead of stomped."""
        frame = toast.widget
        slide_dist = frame.anim_offset

        def _step(i):
            if toast.widget is not frame:
                return
            try:
                t = i / self._SLIDE_STEPS
                frame.anim_offset = int(slide_dist * (1 - t) ** 2)
                self._place(frame)
                if i < self._SLIDE_STEPS:
                    frame.after(self._SLIDE_MS, lambda: _step(i + 1))
                else:
                    frame.anim_offset = 0
                    self._place(frame)
            except tk.TclError:
                pass

        _step(0)

    def _animate_exit(self, toast):
        """Fade colors toward the background, then remove. The slot is held
        for the whole fade so neighbors don't jump until the toast is gone."""
        frame = toast.widget
        bg = TK_COLORS['input_bg']
        body_color = THEME_COLORS['body']
        accent_color = frame.accent_color

        def _step(i):
            if toast.widget is not frame:
                return
            try:
                t = i / self._FADE_STEPS
                faded_bg = blend_alpha(bg, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_fg = blend_alpha(body_color, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_accent = blend_alpha(accent_color, TK_COLORS['bg'], int(100 * (1 - t)))
                faded_border = blend_alpha(TK_COLORS['border'], TK_COLORS['bg'], int(100 * (1 - t)))
                frame.configure(bg=faded_bg,
                                highlightbackground=faded_border,
                                highlightcolor=faded_border)
                for child in frame.winfo_children():
                    if isinstance(child, tk.Frame):
                        child.configure(bg=faded_accent)
                    elif isinstance(child, ttk.Label):
                        child.configure(foreground=faded_fg, background=faded_bg)
                if i < self._FADE_STEPS:
                    frame.after(self._FADE_MS, lambda: _step(i + 1))
                else:
                    self._finish_remove(toast)
            except tk.TclError:
                self._finish_remove(toast)

        _step(1)

    def _finish_remove(self, toast):
        if toast.widget is None:
            return
        frame = toast.widget
        toast.widget = None
        promoted = self._model.remove(toast)
        try:
            frame.place_forget()
            frame.destroy()
        except tk.TclError:
            pass
        self._layout()
        for t in promoted:
            self._mount(t)


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

    _last_width = [0]

    def _on_canvas_configure(event):
        if event.width == _last_width[0]:
            return
        _last_width[0] = event.width
        if resize_flag and resize_flag[0]:
            return
        canvas.itemconfig(canvas_window, width=event.width)
    canvas.bind('<Configure>', _on_canvas_configure)

    def _force_layout():
        w = canvas.winfo_width()
        if w > 1:
            canvas.itemconfig(canvas_window, width=w)
            _set_scrollregion()
    canvas._force_layout = _force_layout
    _bind_canvas_mousewheel(canvas, inner)

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


def _bind_canvas_mousewheel(canvas, *extra_widgets):
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

