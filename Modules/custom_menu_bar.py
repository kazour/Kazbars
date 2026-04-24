"""
Kaz Grids — Dark-themed menu bar.

Canvas-based alternative to tk.Menu that plays nicely with the ttkbootstrap
darkly theme. Uses place()-positioned Frame overlays for dropdowns instead of
Toplevel windows — no brief white flash on open, no native titlebar to style.
"""

import tkinter as tk

from .ui_helpers import FONT_BODY, FONT_SMALL, THEME_COLORS, TK_COLORS


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
