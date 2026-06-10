"""
Frameless dark popup family — welcome, About, and the close-game-required
modal, plus the shared chrome they're built from (shell, close button,
centering). Same CRT visual language as the build loading screen, which
imports the chrome from here.
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
    SCANLINE_ALPHA,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import blend_alpha

# Layout — the popup family's shared frame (build_loading imports these)
WIDTH = 420
BG = TK_COLORS['status_bg']
BORDER_COLOR = TK_COLORS['border']
SCANLINE_STEP = 3


# ============================================================================
# SHARED POPUP CHROME
# ============================================================================

def make_popup_shell(parent, height):
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


def draw_close_button(popup, canvas, btn_y, on_close=None):
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


def center_popup(popup, parent, height):
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
    popup, canvas = make_popup_shell(parent, h)

    # Warning icon with glow
    warn_color = THEME_COLORS['warning']
    icon_y = 72
    for i in range(3, 0, -1):
        glow = blend_alpha(warn_color, BG, 15 * i)
        canvas.create_text(WIDTH // 2, icon_y, text='⚠',
                           font=FONT_STATUS_ICON_LG, fill=glow)
    canvas.create_text(WIDTH // 2, icon_y, text='⚠',
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

    draw_close_button(popup, canvas, icon_y + 112)
    center_popup(popup, parent, h)
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

    popup, canvas = make_popup_shell(parent, h)

    # Status icon with glow
    status_color = THEME_COLORS['success']
    for i in range(3, 0, -1):
        glow = blend_alpha(status_color, BG, 15 * i)
        canvas.create_text(WIDTH // 2, status_y, text='✓',
                           font=FONT_STATUS_ICON_LG, fill=glow)
    canvas.create_text(WIDTH // 2, status_y, text='✓',
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
                           text=f"{disabled_count} are disabled — enable them when you're ready",
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

    draw_close_button(popup, canvas, btn_y)
    center_popup(popup, parent, h)
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

    popup, canvas = make_popup_shell(parent, h)

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
    # Credit line — colored segments for Kazour (green) and I-Spartans-I (golden)
    _font_sm = tkfont.Font(font=FONT_SMALL)
    _credit = [
        ("Created by ", THEME_COLORS['muted']),
        ("Kazour", THEME_COLORS['success']),
        ("  ·  ", THEME_COLORS['muted']),
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

    make_link("▸ Join our Discord", DISCORD_URL, y)
    y += 22
    if GITHUB_URL:
        make_link("▸ GitHub", GITHUB_URL, y)
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

    draw_close_button(popup, canvas, scene_bottom + 20, on_close=close)
    popup.protocol("WM_DELETE_WINDOW", close)
    center_popup(popup, parent, h)
    popup.deiconify()
    popup.grab_set()
    popup.focus_set()
    animate()
    return popup
