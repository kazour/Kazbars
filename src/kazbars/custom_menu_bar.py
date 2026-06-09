"""
KazBars — Dark-themed menu bar.

Canvas-based alternative to tk.Menu that plays nicely with the ttkbootstrap
darkly theme. Uses place()-positioned Frame overlays for dropdowns instead of
Toplevel windows — no brief white flash on open, no native titlebar to style.
"""

import tkinter as tk

from .ui_helpers import _RETRO_COLORS, FONT_BODY, FONT_SMALL, THEME_COLORS, TK_COLORS

# ============================================================================
# CUSTOM DARK MENU BAR
# ============================================================================
_DD_MIN_WIDTH = 220
_DD_BORDER_COLOR = TK_COLORS['menu_border']


class CustomMenuBar(tk.Canvas):
    """Dark-themed menu bar replacing native tk.Menu.

    Uses a Canvas for the bar (immune to ttkbootstrap theme overrides) and a
    place()-based Frame overlay for dropdowns (no Toplevel = no Windows flash).
    Supports accelerator text, separators, disabled items, and keyboard nav.
    """

    _MENU_BG = TK_COLORS['status_bg']
    _MENU_FG = THEME_COLORS['body']
    _MENU_HOVER_BG = TK_COLORS['input_bg']
    _MENU_ACTIVE_BG = TK_COLORS['input_bg']      # Same bg as hover; active differs via underline + white text
    _MENU_ACTIVE_FG = THEME_COLORS['heading']
    _MENU_DISABLED_FG = TK_COLORS['menu_disabled_fg']
    _ACCEL_FG = THEME_COLORS['muted']
    _SEP_COLOR = TK_COLORS['separator']
    _FONT = FONT_BODY
    _BAR_HEIGHT = 26
    _CELL_PADX = 10
    _ACTIVE_UNDERLINE = _RETRO_COLORS['phosphor_green']

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
        self._cursor_x = 4        # Next cascade label x position

        self.bind('<Button-1>', self._bar_click)
        self.bind('<Motion>', self._bar_motion)
        self.bind('<Leave>', self._bar_leave)

    def add_cascade(self, label, menu_def):
        """Add a top-level menu. Returns the menu_def list for later mutation."""
        self._add_top_item(label, menu_def, None)
        return menu_def

    def add_command(self, label, command):
        """Add a top-level clickable command (no dropdown)."""
        self._add_top_item(label, None, command)

    def _add_top_item(self, label, menu_def, command):
        tag = f"cascade_{len(self._cascades)}"
        tid = self.create_text(
            self._cursor_x + self._CELL_PADX, self._BAR_HEIGHT // 2,
            text=label, anchor='w', fill=self._MENU_FG, font=self._FONT,
            tags=(tag,),
        )
        bbox = self.bbox(tid)
        cell_x1 = self._cursor_x
        cell_x2 = bbox[2] + self._CELL_PADX
        self._cursor_x = cell_x2
        self._cascades.append((tag, cell_x1, cell_x2, menu_def, command))

    # --- Canvas bar events ---

    def _hit_cascade(self, x):
        for i, (_, x1, x2, _, _) in enumerate(self._cascades):
            if x1 <= x <= x2:
                return i
        return -1

    def _bar_click(self, event):
        idx = self._hit_cascade(event.x)
        if idx < 0:
            return
        command = self._cascades[idx][4]
        if command is not None:
            self._invoke(command)
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
        # Hover-to-switch when a menu is open (only to other cascades, not commands)
        if (self._hover_mode and self._open_index >= 0 and idx >= 0
                and idx != self._open_index and self._cascades[idx][3] is not None):
            self._open_at(idx)

    def _bar_leave(self, event):
        if self._hover_index >= 0 and self._hover_index != self._open_index:
            self._draw_cascade_bg(self._hover_index, self._MENU_BG)
        self._hover_index = -1

    def _draw_cascade_bg(self, idx, color):
        tag = f"cascade_bg_{idx}"
        self.delete(tag)
        if color != self._MENU_BG:
            _, x1, x2, _, _ = self._cascades[idx]
            self.create_rectangle(
                x1, 0, x2, self._BAR_HEIGHT,
                fill=color, outline='', tags=(tag,),
            )
            # Re-raise text above background rect
            text_tag = self._cascades[idx][0]
            self.tag_raise(text_tag)

    def _set_cascade_active(self, idx, on):
        """Apply or revert the active visual state (bg + text + underline) for a cascade."""
        text_tag, x1, x2, _, _ = self._cascades[idx]
        self.delete('active_underline')
        if on:
            self._draw_cascade_bg(idx, self._MENU_ACTIVE_BG)
            self.itemconfigure(text_tag, fill=self._MENU_ACTIVE_FG)
            # 6px inset on each side so the underline tracks the label, not the cell.
            self.create_rectangle(
                x1 + 6, self._BAR_HEIGHT - 2, x2 - 6, self._BAR_HEIGHT,
                fill=self._ACTIVE_UNDERLINE, outline='', tags=('active_underline',),
            )
        else:
            self._draw_cascade_bg(idx, self._MENU_BG)
            self.itemconfigure(text_tag, fill=self._MENU_FG)

    # --- Dropdown lifecycle ---

    def _ensure_dropdown(self):
        if self._dd_frame is not None:
            return
        root = self.winfo_toplevel()
        # Border is via highlightthickness — Tk paints this intrinsically, so it
        # survives the ttkbootstrap pady-leak (see note in _open_at).
        self._dd_frame = tk.Frame(
            root, bg=self._MENU_BG,
            highlightthickness=1, highlightbackground=_DD_BORDER_COLOR,
            highlightcolor=_DD_BORDER_COLOR,
        )
        # Unhighlight focused row when cursor exits the dropdown entirely
        self._dd_frame.bind('<Leave>', self._on_dropdown_leave)

    def _open_at(self, idx):
        self._ensure_dropdown()

        if self._open_index >= 0:
            self._set_cascade_active(self._open_index, False)

        _, x1, x2, menu_def, _ = self._cascades[idx]
        self._open_index = idx
        self._hover_mode = True
        self._set_cascade_active(idx, True)

        if self._dd_inner:
            self._dd_inner.destroy()

        content = tk.Frame(self._dd_frame, bg=self._MENU_BG)
        content.pack(fill='both', expand=True)
        self._dd_inner = content

        # Spacers/separators use tk.Canvas (not tk.Frame) because under ttkbootstrap,
        # empty Frames and pack pady gaps both leak the theme bg (#222222) instead of
        # painting the parent's bg. Canvas always paints. width=1 because Canvas
        # defaults to width=378, which would force the dropdown wider than its content.
        def spacer(height, color=self._MENU_BG, padx=0):
            tk.Canvas(content, bg=color, width=1, height=height,
                      highlightthickness=0).pack(fill='x', padx=padx)

        spacer(5)
        self._rows = []
        self._focused_row = -1

        for entry in menu_def:
            if entry['type'] == 'separator':
                spacer(6)
                spacer(1, color=self._SEP_COLOR, padx=8)
                spacer(6)
                continue

            row = tk.Frame(content, bg=self._MENU_BG)
            row.pack(fill='x')

            pill = tk.Frame(row, bg=self._MENU_BG)
            pill.pack(fill='x', padx=5, ipady=5)

            state = entry.get('state', 'normal')
            fg = self._MENU_FG if state == 'normal' else self._MENU_DISABLED_FG
            accel_fg = self._ACCEL_FG if state == 'normal' else self._MENU_DISABLED_FG

            label_text = entry['label']
            cmd = entry.get('command') if state == 'normal' else None
            if entry['type'] == 'checkbutton':
                var = entry['variable']
                glyph = '☑' if var.get() else '☐'
                label_text = f"{glyph}  {label_text}"
                user_cmd = cmd
                def _toggle(v=var, c=user_cmd):
                    v.set(not v.get())
                    if c is not None:
                        c()
                cmd = _toggle

            text_lbl = tk.Label(
                pill, text=label_text, bg=self._MENU_BG, fg=fg,
                font=self._FONT, anchor='w',
            )
            text_lbl.pack(side='left', fill='x', expand=True, padx=(8, 0))

            accel_lbl = tk.Label(
                pill, text=entry.get('accelerator', ''), bg=self._MENU_BG, fg=accel_fg,
                font=FONT_SMALL, anchor='e',
            )
            accel_lbl.pack(side='right', padx=(14, 8))

            self._rows.append({
                'row': row, 'pill': pill, 'text_lbl': text_lbl, 'accel_lbl': accel_lbl,
                'cmd': cmd, 'state': state,
            })
            row_idx = len(self._rows) - 1

            if state == 'normal':
                for w in (row, pill, text_lbl, accel_lbl):
                    w.bind('<Enter>', lambda e, ri=row_idx: self._set_focused_row(ri))
                    w.bind('<Button-1>', lambda e, c=cmd: self._invoke(c))

        spacer(5)

        # Enforce minimum width
        content.update_idletasks()
        if content.winfo_reqwidth() < _DD_MIN_WIDTH:
            content.configure(width=_DD_MIN_WIDTH)
        self._dd_frame.update_idletasks()

        # Force the unhighlighted state explicitly so initial render matches
        # the post-hover render (avoids Tk first-paint quirk on Windows).
        for entry in self._rows:
            self._highlight_row(entry, False)

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
            self._set_cascade_active(self._open_index, False)
        self._open_index = -1
        self._hover_mode = False
        self._rows = []
        self._focused_row = -1

    # --- Row hover and keyboard navigation ---

    def _on_dropdown_leave(self, event):
        # NotifyInferior leaves (cursor moving onto a child of _dd_frame) shouldn't unhighlight
        dd = self._dd_frame
        rx, ry = dd.winfo_rootx(), dd.winfo_rooty()
        if (rx <= event.x_root < rx + dd.winfo_width()
                and ry <= event.y_root < ry + dd.winfo_height()):
            return
        if self._focused_row >= 0:
            self._highlight_row(self._rows[self._focused_row], False)
            self._focused_row = -1

    def _highlight_row(self, row_entry, on):
        # Only the pill changes; the surrounding gutter stays the surface color.
        normal = row_entry['state'] == 'normal'
        if on:
            bg = self._MENU_FG
            fg = self._MENU_BG
            accel_fg = self._MENU_BG
        else:
            bg = self._MENU_BG
            fg = self._MENU_FG if normal else self._MENU_DISABLED_FG
            accel_fg = self._ACCEL_FG if normal else self._MENU_DISABLED_FG
        row_entry['pill'].configure(bg=bg)
        row_entry['text_lbl'].configure(bg=bg, fg=fg)
        row_entry['accel_lbl'].configure(bg=bg, fg=accel_fg)

    def _set_focused_row(self, row_idx):
        if row_idx == self._focused_row:
            return
        # Defensively reset every other row so nothing can stay stuck
        # regardless of any Enter/Leave event quirks.
        for i, entry in enumerate(self._rows):
            if i != row_idx:
                self._highlight_row(entry, False)
        self._focused_row = row_idx
        if 0 <= row_idx < len(self._rows):
            self._highlight_row(self._rows[row_idx], True)

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
        n = len(self._cascades)
        idx = self._open_index
        for _ in range(n):
            idx = (idx + direction) % n
            if self._cascades[idx][3] is not None:
                self._open_at(idx)
                return

    # --- Invoke and configure ---

    def _invoke(self, cmd):
        self._close_dropdown()
        if cmd:
            self.after_idle(cmd)

    def entryconfigure(self, menu_def, index, **kw):
        """Update a menu entry. Mirrors tk.Menu.entryconfigure interface."""
        menu_def[index].update(kw)
