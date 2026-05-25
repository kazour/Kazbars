"""
Animated build loading screen — dark retro UI with glowing progress ring,
CRT scanlines, and pulsing text.

Transitions from progress view → results summary in the same window.
"""

import logging
import math
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser

logger = logging.getLogger(__name__)

from .ui_helpers import (
    FONT_BODY,
    FONT_HEADING,
    FONT_SECTION,
    FONT_SMALL,
    FONT_STATUS_ICON,
    FONT_STATUS_ICON_LG,
    MODULE_COLORS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import blend_alpha

# Layout
WIDTH = 420
HEIGHT_PROGRESS = 340
BG = TK_COLORS['status_bg']
BORDER_COLOR = TK_COLORS['border']
RING_RADIUS = 55
RING_WIDTH = 5
RING_TRACK_COLOR = TK_COLORS['separator']
DOT_RADIUS = 5
DOT_SPACING = 24
SCANLINE_ALPHA = 12
SCANLINE_STEP = 3

# Fixed accent color — single module, no per-step transitions
_ACCENT = MODULE_COLORS['grids']


# ============================================================================
# SHARED POPUP HELPERS
# ============================================================================

def _make_popup_shell(parent, height):
    """Create a frameless dark Toplevel + canvas with KAZBARS chrome.

    Returns (popup, canvas). Caller handles sizing/centering, focus, grab,
    and showing (deiconify).
    """
    popup = tk.Toplevel(parent)
    popup.withdraw()
    popup.overrideredirect(True)
    popup.transient(parent)
    popup.resizable(False, False)
    popup.configure(bg=BG)
    # overrideredirect popups can sink behind the parent on alt-tab;
    # -topmost keeps this modal reliably above the main window
    popup.attributes('-topmost', True)

    canvas = tk.Canvas(popup, width=WIDTH, height=height, bg=BG, highlightthickness=0)
    canvas.pack(fill='both', expand=True)

    # Border + CRT scanlines
    canvas.create_rectangle(1, 1, WIDTH - 1, height - 1, outline=BORDER_COLOR, width=1)
    scanline_color = blend_alpha('#000000', BG, SCANLINE_ALPHA)
    for sy in range(0, height, SCANLINE_STEP):
        canvas.create_line(2, sy, WIDTH - 2, sy, fill=scanline_color)

    # Title
    canvas.create_text(WIDTH // 2, 32, text='「 KAZBARS 」',
                       font=FONT_HEADING, fill=THEME_COLORS['accent'])

    return popup, canvas


def _draw_close_button(popup, canvas, btn_y, on_close=None):
    """Draw a styled Close button at btn_y with hover/click hit-test.

    Also binds Escape/Return on popup. on_close defaults to popup.destroy.
    Returns btn_y + btn_h for layout chaining.
    """
    if on_close is None:
        on_close = popup.destroy
    btn_w, btn_h = 100, 32
    btn_x = (WIDTH - btn_w) // 2

    glow_color = blend_alpha(THEME_COLORS['accent'], BG, 30)
    canvas.create_rectangle(btn_x - 2, btn_y - 2, btn_x + btn_w + 2, btn_y + btn_h + 2,
                            fill=glow_color, outline='')
    btn_rect = canvas.create_rectangle(btn_x, btn_y, btn_x + btn_w, btn_y + btn_h,
                                       fill=BG, outline=THEME_COLORS['accent'], width=1)
    btn_text = canvas.create_text(btn_x + btn_w // 2, btn_y + btn_h // 2,
                                  text="Close", font=FONT_SECTION,
                                  fill=THEME_COLORS['accent'])

    def _in_btn(x, y):
        return btn_x <= x <= btn_x + btn_w and btn_y <= y <= btn_y + btn_h

    def on_motion(e):
        if _in_btn(e.x, e.y):
            canvas.itemconfig(btn_rect, fill=THEME_COLORS['accent'])
            canvas.itemconfig(btn_text, fill=BG)
        else:
            canvas.itemconfig(btn_rect, fill=BG)
            canvas.itemconfig(btn_text, fill=THEME_COLORS['accent'])

    def on_click(e):
        if _in_btn(e.x, e.y):
            on_close()

    canvas.bind('<Motion>', on_motion)
    canvas.bind('<Button-1>', on_click)
    popup.bind('<Escape>', lambda e: on_close())
    popup.bind('<Return>', lambda e: on_close())
    return btn_y + btn_h


def _center_popup(popup, parent, height):
    """Center popup at (WIDTH, height) on parent."""
    popup.update_idletasks()
    px, py = parent.winfo_x(), parent.winfo_y()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    popup.geometry(f"{WIDTH}x{height}+{px + (pw - WIDTH) // 2}+{py + (ph - height) // 2}")


def show_close_game_required_dialog(parent, process_name="the game"):
    """Show a close-only modal: the running game process must be closed before build.

    No return value — caller always aborts the build. The user closes the
    popup, closes the game, and clicks Build & Install again.

    process_name is the actual running exe (Aoc.exe / AgeOfConan.exe /
    AgeOfConanDX10.exe) detected by build_executor.get_running_game_process.
    """
    h = 250
    popup, canvas = _make_popup_shell(parent, h)

    # Warning icon with glow
    warn_color = THEME_COLORS['warning']
    icon_y = 72
    for i in range(3, 0, -1):
        glow = blend_alpha(warn_color, BG, 15 * i)
        canvas.create_text(WIDTH // 2, icon_y, text='\u26A0',
                           font=FONT_STATUS_ICON_LG, fill=glow)
    canvas.create_text(WIDTH // 2, icon_y, text='\u26A0',
                       font=FONT_STATUS_ICON, fill=warn_color)

    # Message
    canvas.create_text(WIDTH // 2, icon_y + 34,
                       text=f"Close {process_name} to build",
                       font=FONT_BODY, fill=THEME_COLORS['heading'])
    canvas.create_text(WIDTH // 2, icon_y + 56,
                       text="Close the game, then click Build & Install again",
                       font=FONT_SMALL, fill=THEME_COLORS['muted'])
    canvas.create_text(WIDTH // 2, icon_y + 82,
                       text="One-time only — future builds work with the game open",
                       font=FONT_SMALL, fill=THEME_COLORS['success'])

    _draw_close_button(popup, canvas, icon_y + 112)
    _center_popup(popup, parent, h)
    popup.deiconify()
    popup.grab_set()
    popup.focus_set()
    parent.wait_window(popup)


def show_welcome_popup(parent, grid_count, enabled_count,
                       resolution_str=None, profile_name=None):
    """Show a welcome popup after loading the default profile.

    Same visual style as the build summary — frameless dark canvas, CRT scanlines,
    glowing accent, styled close button.
    """
    disabled_count = grid_count - enabled_count

    # Pre-compute height so we only draw once
    status_y = 68
    sep_y = status_y + 52
    y = sep_y + 20
    line_spacing = 22
    y += line_spacing  # grid count line
    if disabled_count > 0:
        y += line_spacing
    if resolution_str:
        y += line_spacing
    if profile_name:
        y += line_spacing
    y += line_spacing  # tip line
    btn_y = y + 12
    btn_h = 32
    h = btn_y + btn_h + 16

    popup, canvas = _make_popup_shell(parent, h)

    # Status icon with glow
    status_color = THEME_COLORS['success']
    for i in range(3, 0, -1):
        glow = blend_alpha(status_color, BG, 15 * i)
        canvas.create_text(WIDTH // 2, status_y, text='\u2713',
                           font=FONT_STATUS_ICON_LG, fill=glow)
    canvas.create_text(WIDTH // 2, status_y, text='\u2713',
                       font=FONT_STATUS_ICON, fill=status_color)
    canvas.create_text(WIDTH // 2, status_y + 30, text="You're almost done",
                       font=FONT_HEADING, fill=status_color)

    # Separator
    sep_color = blend_alpha(BORDER_COLOR, BG, 60)
    canvas.create_line(40, sep_y, WIDTH - 40, sep_y, fill=sep_color)

    # Info lines
    y = sep_y + 20
    canvas.create_text(WIDTH // 2, y,
                       text=f"{grid_count} grids loaded from default profile",
                       font=FONT_BODY, fill=THEME_COLORS['heading'])
    y += line_spacing
    if disabled_count > 0:
        canvas.create_text(WIDTH // 2, y,
                           text=f"{disabled_count} are disabled \u2014 enable them when you're ready",
                           font=FONT_SMALL, fill=THEME_COLORS['warning'])
        y += line_spacing
    if resolution_str:
        canvas.create_text(WIDTH // 2, y, text=f"Scaled to {resolution_str}",
                           font=FONT_SMALL, fill=THEME_COLORS['muted'])
        y += line_spacing
    if profile_name:
        canvas.create_text(WIDTH // 2, y, text=f"Saved as {profile_name}",
                           font=FONT_SMALL, fill=THEME_COLORS['muted'])
        y += line_spacing
    # Split into two text items so "Build & Install" can be green like in the help tab
    _font = tkfont.Font(font=FONT_SMALL)
    _prefix = "Customize the grids and press "
    _accent = "Build & Install"
    _total_w = _font.measure(_prefix + _accent)
    _x0 = WIDTH // 2 - _total_w // 2
    canvas.create_text(_x0, y, text=_prefix, anchor='w',
                       font=FONT_SMALL, fill=THEME_COLORS['muted'])
    canvas.create_text(_x0 + _font.measure(_prefix), y, text=_accent, anchor='w',
                       font=FONT_SMALL, fill=THEME_COLORS['success'])

    _draw_close_button(popup, canvas, btn_y)
    _center_popup(popup, parent, h)
    popup.deiconify()
    popup.grab_set()
    popup.focus_set()


DISCORD_URL = "https://discord.gg/ubK5Guryfa"
GITHUB_URL = "https://github.com/kazour/Kazbars"


def show_about_popup(parent, app_name, app_version):
    """About dialog — same frameless dark style as build popups, with an
    animated miniature buff-grid scene at the bottom.
    """
    h = 342 if GITHUB_URL else 320

    popup, canvas = _make_popup_shell(parent, h)

    # Separator
    sep_y = 60
    sep_color = blend_alpha(BORDER_COLOR, BG, 60)
    canvas.create_line(40, sep_y, WIDTH - 40, sep_y, fill=sep_color)

    # Info lines
    y = sep_y + 20
    canvas.create_text(WIDTH // 2, y,
                       text="Flash buff & debuff tracker for Age of Conan",
                       font=FONT_BODY, fill=THEME_COLORS['heading'])
    y += 22
    # Credit line \u2014 colored segments for Kazour (green) and I-Spartans-I (golden)
    _font_sm = tkfont.Font(font=FONT_SMALL)
    _credit = [
        ("Created by ", THEME_COLORS['muted']),
        ("Kazour", THEME_COLORS['success']),
        ("  \u00b7  ", THEME_COLORS['muted']),
        ("I-Spartans-I", THEME_COLORS['warning']),
    ]
    _total_w = sum(_font_sm.measure(t) for t, _ in _credit)
    _cx = WIDTH // 2 - _total_w // 2
    for _text, _fill in _credit:
        canvas.create_text(_cx, y, text=_text, anchor='w',
                           font=FONT_SMALL, fill=_fill)
        _cx += _font_sm.measure(_text)
    y += 20
    # Deeps meter credit — Veni (golden, Spartan)
    _deeps_credit = [
        ("Deeps meter by ", THEME_COLORS['muted']),
        ("Veni", THEME_COLORS['warning']),
    ]
    _dc_w = sum(_font_sm.measure(t) for t, _ in _deeps_credit)
    _dcx = WIDTH // 2 - _dc_w // 2
    for _text, _fill in _deeps_credit:
        canvas.create_text(_dcx, y, text=_text, anchor='w',
                           font=FONT_SMALL, fill=_fill)
        _dcx += _font_sm.measure(_text)
    y += 26

    # Clickable links
    link_color = THEME_COLORS['accent']
    link_hover = blend_alpha('#ffffff', link_color, 60)

    def make_link(text, url, ly):
        item = canvas.create_text(WIDTH // 2, ly, text=text,
                                  font=FONT_SECTION, fill=link_color)
        canvas.tag_bind(item, '<Enter>',
                        lambda e: (canvas.itemconfig(item, fill=link_hover),
                                   canvas.config(cursor='hand2')))
        canvas.tag_bind(item, '<Leave>',
                        lambda e: (canvas.itemconfig(item, fill=link_color),
                                   canvas.config(cursor='')))
        canvas.tag_bind(item, '<Button-1>',
                        lambda e: webbrowser.open(url))

    make_link("\u25B8 Join our Discord", DISCORD_URL, y)
    y += 22
    if GITHUB_URL:
        make_link("\u25B8 GitHub", GITHUB_URL, y)
        y += 22

    # Bottom separator + license
    y += 6
    canvas.create_line(40, y, WIDTH - 40, y, fill=sep_color)
    y += 14
    canvas.create_text(WIDTH // 2, y, text="MIT License",
                       font=FONT_SMALL, fill=THEME_COLORS['muted'])

    # Animated buff-grid scene — 2x10 mini row, traveling wave,
    # cells alternate between the app's blue and purple accents
    scene_y = y + 22
    cols, rows = 10, 2
    cell_w = 18
    cell_gap = 4
    total_w = cols * cell_w + (cols - 1) * cell_gap
    start_x = (WIDTH - total_w) // 2

    palette = [THEME_COLORS['accent'], THEME_COLORS['purple']]

    cells = []
    for r in range(rows):
        for c in range(cols):
            x0 = start_x + c * (cell_w + cell_gap)
            y0 = scene_y + r * (cell_w + cell_gap)
            color = palette[(c + r) % len(palette)]
            cid = canvas.create_rectangle(
                x0, y0, x0 + cell_w, y0 + cell_w,
                fill=BG, outline=blend_alpha(color, BG, 40), width=1)
            cells.append((cid, color, c, r))

    scene_bottom = scene_y + rows * cell_w + (rows - 1) * cell_gap

    # Animation — traveling pulse across the grid
    state = {'running': True, 'after_id': None}
    start_time = time.time()

    def animate():
        if not state['running']:
            return
        try:
            t = time.time() - start_time
            for cid, color, c, r in cells:
                phase = t * 2.4 - c * 0.55 - r * 0.35
                brightness = (math.sin(phase) + 1) / 2
                brightness = brightness ** 2
                intensity = int(15 + brightness * 110)
                canvas.itemconfig(cid, fill=blend_alpha(color, BG, intensity))
            state['after_id'] = canvas.after(33, animate)
        except tk.TclError:
            pass

    def close():
        state['running'] = False
        if state['after_id'] is not None:
            try:
                canvas.after_cancel(state['after_id'])
            except (ValueError, tk.TclError):
                pass
        popup.destroy()

    _draw_close_button(popup, canvas, scene_bottom + 20, on_close=close)
    popup.protocol("WM_DELETE_WINDOW", close)
    _center_popup(popup, parent, h)
    popup.deiconify()
    popup.grab_set()
    popup.focus_set()
    animate()
    return popup


class BuildLoadingScreen(tk.Toplevel):
    """Frameless modal loading screen shown during Build & Install.

    Two phases:
      1. Progress — animated ring, pulsing text, 2 step dots
      2. Summary — build results, reload instructions, close button
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()

        self._parent = parent
        self._total_steps = 2  # fixed: compile + install
        self._current_step = -1
        self._step_name = "Preparing..."
        self._destroyed = False
        self._after_id = None
        self._start_time = time.time()
        self._phase = 'progress'

        self.overrideredirect(True)
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG)
        # overrideredirect windows can sink behind the parent on alt-tab;
        # -topmost keeps this modal reliably above the main window
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind('<FocusIn>', lambda e: self.lift())

        self._build_progress_ui()
        self._center_on_parent(HEIGHT_PROGRESS)
        self.deiconify()
        self.grab_set()
        self._animate()

        # Safety timeout — allow Escape to force-close after 30s
        self._escape_armed = False
        def _arm_escape():
            self._escape_armed = True
        self._arm_timer = self.after(30000, _arm_escape)
        self.bind('<Escape>', self._on_escape)

    def _on_escape(self, event=None):
        if self._escape_armed or self._phase == 'summary':
            self.destroy()

    # ------------------------------------------------------------------
    # UI construction — progress phase
    # ------------------------------------------------------------------

    def _build_progress_ui(self):
        self._canvas = tk.Canvas(
            self, width=WIDTH, height=HEIGHT_PROGRESS,
            bg=BG, highlightthickness=0,
        )
        self._canvas.pack(fill='both', expand=True)

        # Border
        self._canvas.create_rectangle(
            1, 1, WIDTH - 1, HEIGHT_PROGRESS - 1,
            outline=BORDER_COLOR, width=1, tags='border',
        )

        # Ring center
        self._cx = WIDTH // 2
        self._cy = 130
        cx, cy, r = self._cx, self._cy, RING_RADIUS

        # Background track
        self._ring_track = self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=RING_TRACK_COLOR, width=RING_WIDTH, tags='ring',
        )
        # 4 glow layers (pre-computed, color fixed)
        self._ring_glows = []
        for i in range(4, 0, -1):
            gr = r + i * 3
            gw = RING_WIDTH + i * 3
            glow_color = blend_alpha(_ACCENT, BG, 12 * i)
            glow_id = self._canvas.create_arc(
                cx - gr, cy - gr, cx + gr, cy + gr,
                start=0, extent=270, outline=glow_color, width=gw, style='arc', tags='ring',
            )
            self._ring_glows.append(glow_id)
        # Main arc
        self._ring_main = self._canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=0, extent=270, outline=_ACCENT, width=RING_WIDTH, style='arc', tags='ring',
        )
        # Leading-edge highlight
        highlight_color = blend_alpha('#ffffff', _ACCENT, 40)
        self._ring_highlight = self._canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=250, extent=20, outline=highlight_color, width=RING_WIDTH, style='arc', tags='ring',
        )

        # Step dots
        self._dots_y = cy + RING_RADIUS + 26
        n = self._total_steps
        total_width = (n - 1) * DOT_SPACING
        start_x = cx - total_width // 2
        dy = self._dots_y
        self._dot_ids = []
        for i in range(n):
            x = start_x + i * DOT_SPACING
            dot_id = self._canvas.create_oval(
                x - DOT_RADIUS, dy - DOT_RADIUS,
                x + DOT_RADIUS, dy + DOT_RADIUS,
                fill=THEME_COLORS['muted'], outline='', tags='dots',
            )
            self._dot_ids.append(dot_id)

        # CRT scanlines
        scanline_color = blend_alpha('#000000', BG, SCANLINE_ALPHA)
        for y in range(0, HEIGHT_PROGRESS, SCANLINE_STEP):
            self._canvas.create_line(2, y, WIDTH - 2, y, fill=scanline_color, tags='scanline')

        # Title
        self._canvas.create_text(
            WIDTH // 2, 32,
            text='\u300c KAZBARS \u300d',
            font=FONT_HEADING,
            fill=THEME_COLORS['accent'],
            tags='title',
        )

        # Step name text (pulsing)
        self._name_id = self._canvas.create_text(
            WIDTH // 2, self._dots_y + 28,
            text=self._step_name,
            font=FONT_HEADING,
            fill=THEME_COLORS['heading'],
            tags='step_name',
        )

        # Subtitle
        self._sub_id = self._canvas.create_text(
            WIDTH // 2, self._dots_y + 50,
            text="",
            font=FONT_BODY,
            fill=THEME_COLORS['muted'],
            tags='subtitle',
        )

    def _center_on_parent(self, height):
        self.update_idletasks()
        px = self._parent.winfo_x()
        py = self._parent.winfo_y()
        pw = self._parent.winfo_width()
        ph = self._parent.winfo_height()
        x = px + (pw - WIDTH) // 2
        y = py + (ph - height) // 2
        self.geometry(f"{WIDTH}x{height}+{x}+{y}")

    # ------------------------------------------------------------------
    # Animation loop
    # ------------------------------------------------------------------

    def _animate(self):
        if self._destroyed or self._phase != 'progress':
            return

        now = time.time()
        elapsed = now - self._start_time
        angle = (elapsed * 120) % 360
        pulse = math.sin(elapsed * 2.5) * 0.5 + 0.5

        self._draw_ring(angle)
        self._draw_dots(pulse)
        self._draw_pulse_text(pulse)

        self._after_id = self.after(33, self._animate)

    def _draw_ring(self, angle):
        for glow_id in self._ring_glows:
            self._canvas.itemconfig(glow_id, start=angle)
        self._canvas.itemconfig(self._ring_main, start=angle)
        self._canvas.itemconfig(self._ring_highlight, start=angle + 250)

    def _draw_dots(self, pulse):
        for i, dot_id in enumerate(self._dot_ids):
            if i < self._current_step:
                fill = THEME_COLORS['success']
            elif i == self._current_step:
                fill = blend_alpha('#ffffff', _ACCENT, int(pulse * 40))
            else:
                fill = THEME_COLORS['muted']
            self._canvas.itemconfig(dot_id, fill=fill)

    def _draw_pulse_text(self, pulse):
        brightness = int(60 + pulse * 40)
        color = blend_alpha(THEME_COLORS['heading'], BG, brightness)
        self._canvas.itemconfig(self._name_id, fill=color, text=self._step_name)

        if self._current_step >= 0:
            sub = f"Step {self._current_step + 1} of {self._total_steps}"
        else:
            sub = ""
        self._canvas.itemconfig(self._sub_id, text=sub)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advance_step(self, name):
        """Advance to the next build step."""
        self._current_step += 1
        self._step_name = name
        self.update()

    def update_step_name(self, name):
        """Update step text without advancing the dot counter."""
        self._step_name = name

    def show_summary(self, client_results, compile_result, profile_name=None,
                     aoc_installed=False, aoc_running=False):
        """Transition from progress view to summary results view.

        Args:
            client_results: [(name, success, error_msg), ...] per-client install results
            compile_result: (success, message) from compilation step
            profile_name: name of saved profile (or None)
            aoc_installed: whether Aoc.exe file exists in any game folder
            aoc_running: whether Aoc.exe process is running
        """
        self._phase = 'summary'

        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

        self._canvas.delete('all')
        self._canvas.pack_forget()
        self._canvas.destroy()

        self._build_summary_ui(client_results, compile_result, profile_name,
                               aoc_installed, aoc_running)

        self.lift()
        self.focus_set()

    def _build_summary_ui(self, client_results, compile_result, profile_name,
                          aoc_installed, aoc_running):
        """Build the results summary view."""
        compile_ok, compile_msg = compile_result
        any_installed = compile_ok and any(s for _, s, _ in client_results)

        summary_height = 400  # initial size; resized to fit after layout

        frame = tk.Frame(self, bg=BG)
        frame.pack(fill='both', expand=True)

        canvas = tk.Canvas(frame, width=WIDTH, height=summary_height,
                           bg=BG, highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        # Border (tagged so it can be redrawn after resize)
        canvas.create_rectangle(1, 1, WIDTH - 1, summary_height - 1,
                                 outline=BORDER_COLOR, width=1, tags='border')

        # CRT scanlines
        scanline_color = blend_alpha('#000000', BG, SCANLINE_ALPHA)
        for y in range(0, summary_height, SCANLINE_STEP):
            canvas.create_line(2, y, WIDTH - 2, y, fill=scanline_color)

        # Title
        canvas.create_text(
            WIDTH // 2, 32,
            text='\u300c KAZBARS \u300d',
            font=FONT_HEADING,
            fill=THEME_COLORS['accent'],
        )

        # Status icon + text
        status_y = 68
        if any_installed:
            status_color = THEME_COLORS['success']
            status_icon = '\u2713'
            status_text = "Build Complete!"
        else:
            status_color = THEME_COLORS['danger']
            status_icon = '\u2716'
            status_text = "Build Failed"

        # Icon with glow
        for i in range(3, 0, -1):
            glow = blend_alpha(status_color, BG, 15 * i)
            canvas.create_text(WIDTH // 2, status_y, text=status_icon,
                                font=FONT_STATUS_ICON_LG, fill=glow)
        canvas.create_text(WIDTH // 2, status_y, text=status_icon,
                            font=FONT_STATUS_ICON, fill=status_color)
        canvas.create_text(WIDTH // 2, status_y + 30, text=status_text,
                            font=FONT_HEADING, fill=status_color)

        # Separator
        sep_y = status_y + 52
        sep_color = blend_alpha(BORDER_COLOR, BG, 60)
        canvas.create_line(40, sep_y, WIDTH - 40, sep_y, fill=sep_color)

        y = sep_y + 16

        if not compile_ok:
            # Compile failed — show compile error only
            canvas.create_oval(30, y - 4, 38, y + 4, fill=THEME_COLORS['danger'], outline='')
            canvas.create_text(46, y, text="Compilation", anchor='w',
                                font=FONT_SECTION, fill=THEME_COLORS['heading'])
            canvas.create_text(WIDTH - 40, y, text='\u2716', anchor='e',
                                font=FONT_BODY, fill=THEME_COLORS['danger'])
            canvas.create_text(WIDTH - 50, y, text="Failed", anchor='e',
                                font=FONT_BODY, fill=THEME_COLORS['warning'])
            y += 22
            if compile_msg:
                msg_id = canvas.create_text(46, y, text=compile_msg, anchor='nw',
                                    font=FONT_SMALL, fill=THEME_COLORS['warning'],
                                    width=WIDTH - 80)
                self.update_idletasks()
                bbox = canvas.bbox(msg_id)
                msg_h = (bbox[3] - bbox[1] + 12) if bbox else 28
                y += msg_h
        else:
            # Per-client result rows
            for name, ok, err in client_results:
                dot_color = _ACCENT if ok else THEME_COLORS['danger']
                icon = '\u2713' if ok else '\u2716'
                icon_color = THEME_COLORS['success'] if ok else THEME_COLORS['danger']
                label = "Updated" if ok else "Failed"
                label_color = THEME_COLORS['body'] if ok else THEME_COLORS['warning']

                canvas.create_oval(30, y - 4, 38, y + 4, fill=dot_color, outline='')
                canvas.create_text(46, y, text=name, anchor='w',
                                    font=FONT_SECTION, fill=THEME_COLORS['heading'])
                canvas.create_text(WIDTH - 40, y, text=icon, anchor='e',
                                    font=FONT_BODY, fill=icon_color)
                canvas.create_text(WIDTH - 50, y, text=label, anchor='e',
                                    font=FONT_BODY, fill=label_color)
                y += 22

                if not ok and err:
                    canvas.create_text(46, y, text=err, anchor='w',
                                        font=FONT_SMALL, fill=THEME_COLORS['warning'],
                                        width=WIDTH - 80)
                    y += 28

        # Profile saved
        if profile_name:
            y += 2
            canvas.create_text(30, y, text=f"\u2713 Profile saved: {profile_name}",
                                anchor='w', font=FONT_SMALL, fill=THEME_COLORS['success'])
            y += 18

        # Reload instructions (only if at least one client installed)
        if any_installed:
            y += 8
            sep_color2 = blend_alpha(BORDER_COLOR, BG, 40)
            canvas.create_line(40, y, WIDTH - 40, y, fill=sep_color2)
            y += 14

            canvas.create_text(30, y, text="To apply changes:", anchor='w',
                                font=FONT_SECTION, fill=THEME_COLORS['heading'])
            y += 20

            if aoc_running:
                instructions = [("In-game:", "/reloadui", THEME_COLORS['accent'])]
            elif aoc_installed:
                instructions = [
                    ("Start game from:", "AgeOfConan.exe", THEME_COLORS['accent']),
                    ("Or:", "AgeOfConanDX10.exe", THEME_COLORS['accent']),
                ]
            else:
                instructions = [
                    ("In game chat:", "/reloadui", THEME_COLORS['accent']),
                    ("Then:", "/reloadgrids", THEME_COLORS['accent']),
                ]

            label_x = 140
            cmd_x = label_x + 8
            for label, cmd, cmd_color in instructions:
                canvas.create_text(label_x, y, text=label, anchor='e',
                                    font=FONT_BODY, fill=THEME_COLORS['muted'])
                canvas.create_text(cmd_x, y, text=cmd, anchor='w',
                                    font=FONT_SECTION, fill=cmd_color)
                y += 20

            if aoc_installed and not aoc_running:
                y += 2
                canvas.create_text(
                    42, y,
                    text="\u26A0 Don't launch via Funcom patcher \u2014 it resets mods",
                    anchor='w', font=FONT_SMALL, fill=THEME_COLORS['warning'],
                )
                y += 16

            canvas.create_text(42, y, text="Tip: Ctrl+Shift+Alt for Preview Mode",
                                anchor='w', font=FONT_SMALL, fill=THEME_COLORS['muted'])
            y += 16

        # Close button — positioned after content, then resize to fit
        btn_bottom = _draw_close_button(self, canvas, y + 16)

        # Resize canvas and window to fit actual content
        final_height = max(btn_bottom + 16, 280)
        canvas.config(height=final_height)
        canvas.delete('border')
        canvas.create_rectangle(1, 1, WIDTH - 1, final_height - 1,
                                 outline=BORDER_COLOR, width=1)
        self._center_on_parent(final_height)
        self.update()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None
        if hasattr(self, '_arm_timer') and self._arm_timer is not None:
            try:
                self.after_cancel(self._arm_timer)
            except (ValueError, tk.TclError):
                pass
        super().destroy()
