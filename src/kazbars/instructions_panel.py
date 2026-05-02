import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .ui_components import create_scrollable_frame
from .ui_helpers import (
    FONT_BODY,
    FONT_SECTION,
    GRID_TYPE_COLORS,
    PAD_COLLAPSE_INDENT,
    PAD_INNER,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)
from .ui_widgets import CollapsibleSection

# Pixel margins from canvas-outer width to text-wrap width. Built up by adding
# the chrome layered between the canvas edge and each nesting level:
#   top:        PAD_TAB padding both sides + scrollbar + ttk frame chrome
#   section:    above + CollapsibleSection collapse indent
#   subsection: above + PAD_INNER (subsection padx) + frame border slack
# Empirically tuned for ttkbootstrap-darkly chrome — revisit if the theme changes.
_CHROME_SLACK       = 36   # scrollbar (~16) + ttk frame internal padding
_TOP_MARGIN         = PAD_TAB * 2 + _CHROME_SLACK
_SECTION_MARGIN     = _TOP_MARGIN + PAD_COLLAPSE_INDENT + 10
_SUBSECTION_MARGIN  = _SECTION_MARGIN + PAD_INNER + 8

# Reading column constraints. ~75ch upper bound at 9px Segoe (≈5px/char average)
# keeps line length within the 65-75ch comfort range from the design laws.
_MIN_TEXT_WIDTH = 220
_MAX_TEXT_WIDTH = 460


class InstructionsPanel(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._wrap_labels = []
        self._body_font = tkfont.Font(font=FONT_BODY)
        self._create_widgets()

    def _target_width(self, margin, canvas_w):
        return min(_MAX_TEXT_WIDTH, max(_MIN_TEXT_WIDTH, canvas_w - margin))

    def _create_widgets(self):
        outer, inner, canvas = create_scrollable_frame(self)
        outer.pack(fill='both', expand=True)
        self._canvas = canvas
        self._frame_bg = ttk.Style().lookup('TFrame', 'background') or TK_COLORS['bg']

        intro = ttk.Label(
            inner,
            text="KazBars is a Windows app for designing buff and debuff "
            "overlays for Age of Conan. Track effects on your own character "
            "or on your current target.",
            font=FONT_BODY, foreground=THEME_COLORS['body'],
            wraplength=_MAX_TEXT_WIDTH, justify='left',
        )
        intro.pack(fill='x', padx=PAD_TAB, pady=(PAD_TAB, PAD_SMALL))
        self._wrap_labels.append((intro, _TOP_MARGIN))

        # --- Quick Start ---

        qs = self._add_section(inner, "Quick Start", [
            "Follow these steps to get your first grid running:",
        ], initially_open=True)
        self._add_subsection(qs.content, "1. Set your game folder", [
            "Click \"(not set)\" next to the Game: label at the bottom and "
            "choose your Age of Conan install folder. Click it again later "
            "to change or clear it.",
        ])
        self._add_subsection(qs.content, "2. Create a grid", [
            "Click + Add Grid in the Grids tab. The H-bar 1x10 preset "
            "is a good starting point for tracking player buffs.",
        ])
        self._add_subsection(qs.content, "3. Choose which buffs to track", [
            "Use the Tracked Buffs... button to pick buffs from the database. "
            "Only buffs you've selected will appear in the grid.",
        ])
        self._add_subsection(qs.content, "4. Build and install", [
            [("Click ", None),
             ("Build & Install", THEME_COLORS['success']),
             (" at the bottom. This compiles your grids and writes them "
              "to your game folder.", None)],
            "How you apply later changes depends on your setup — "
            "see 'Building and Installing' below.",
        ])

        # --- Player vs Target ---

        grid_types = self._add_section(inner, "Player vs Target Grids", [
            "Each grid is tied to one source — chosen when you create the grid.",
        ])
        self._add_subsection(grid_types.content, "Player grid", [
            "Tracks buffs and debuffs on your own character.",
        ], title_color=GRID_TYPE_COLORS['player'])
        self._add_subsection(grid_types.content, "Target grid", [
            "Tracks buffs and debuffs on your current target (mob, "
            "friendly, or enemy player).",
        ], title_color=GRID_TYPE_COLORS['target'])

        # --- Grid Modes ---

        modes = self._add_section(inner, "Dynamic vs Static Mode", [
            "Each grid runs in one of two modes:",
        ])
        self._add_subsection(modes.content, "Dynamic", [
            "Slots fill automatically as buffs activate, and empty when they expire.",
        ])
        self._add_subsection(modes.content, "Dynamic options", [
            "Fill — left-to-right, right-to-left, top-to-bottom, "
            "bottom-to-top, or one of four diagonals.",
            "Sort — longest first, shortest first, or order applied.",
            "Order — Buffs first: misc, buffs, debuffs. "
            "Debuffs first: misc, debuffs, buffs. "
            "Mixed: sorted by time, no grouping.",
        ])
        self._add_subsection(modes.content, "Static", [
            "Each slot is pinned to specific buffs. Empty when none are "
            "active; if several share a slot, the most recent wins.",
        ])

        # --- Whitelist & Slot Assignments ---

        wl_section = self._add_section(inner, "Tracked Buffs", [
            "These are the two ways to tell a grid which buffs to track.",
        ])
        self._add_subsection(wl_section.content, "Dynamic mode", [
            "A list of buff names the grid watches for. Only listed buffs "
            "appear; an empty list shows nothing.",
        ])
        self._add_subsection(wl_section.content, "Static mode", [
            "Assign buffs to each slot by position. Unassigned slots stay "
            "empty; if several share a slot, the most recent wins.",
        ])

        # --- Grid display options ---

        self._add_section(inner, "Grid Display Options", [
            "Timers — remaining duration below each icon.",
            "Flash — icons pulse near expiry. Set the threshold in seconds.",
            "Icon size and gaps are also per-grid. For position, see "
            "'Applying and Positioning In-Game'.",
        ])

        # --- Building & Installing ---

        build_section = self._add_section(inner, "Building and Installing", [
            [("Build & Install", THEME_COLORS['success']),
             (" compiles your grid layout and writes it to your game folder. "
              "The compiler is bundled.", None)],
        ])
        self._add_rich_paragraph(build_section.content, [
            ("Aoc.exe is a third-party launcher bypass. KazBars asks "
             "once at first launch and uses that answer for every build. ", None),
            ("Aoc.exe users must close the game before the first build.",
             THEME_COLORS['danger']),
            (" After that, rebuild while playing.", None),
        ], padx=(PAD_INNER, 0))
        self._add_paragraph(build_section.content,
            "If you install or remove Aoc.exe later, clear and re-set the "
            "game folder. KazBars re-detects and adjusts.",
            foreground=THEME_COLORS['warning'])
        self._add_subsection(build_section.content, "After game patches", [
            [("A patch may overwrite your overlay files. If grids disappear "
              "in-game, just click ", None),
             ("Build & Install", THEME_COLORS['success']),
             (" again.", None)],
        ])
        self._add_subsection(build_section.content, "Removing KazBars from your game folder", [
            "File → Uninstall from game client... removes KazBars.swf "
            "and related files from your Age of Conan install.",
        ])

        # --- Applying and Positioning In-Game ---

        in_game = self._add_section(inner, "Applying and Positioning In-Game", [
            "Reload the overlay in-game and place grids on screen. Both "
            "depend on whether you use Aoc.exe.",
        ])
        self._add_subsection(in_game.content, "Preview mode", [
            "Press Shift+Ctrl+Alt in-game to toggle. Each grid appears as "
            "a colored rectangle with its name and live X/Y coordinates. "
            "Preview mode is only for positioning; all other settings are "
            "configured in the app.",
        ])
        self._add_subsection(in_game.content, "With Aoc.exe (launcher bypass)", [
            "Apply with /reloadui. Drag grids to position; they save "
            "automatically and persist between sessions.",
        ])
        self._add_subsection(in_game.content, "Without Aoc.exe (standard launcher)", [
            "Apply with /reloadui, then /reloadgrids. The launcher resets "
            "positions each session, so dragging doesn't stick. Read X/Y "
            "from preview mode, enter them in the Grids tab, and rebuild.",
        ])

        # --- Buff Database ---

        db_section = self._add_section(inner, "The Buff Database", [
            "Every effect has one or more numeric buff IDs. The Database "
            "tab maps those IDs to readable names and classifies them, so "
            "you can pick effects by name in grids.",
            "Use the search bar and category/type filters to find entries.",
        ])
        self._add_subsection(db_section.content, "Adding or editing an entry", [
            "Name — a unique label (e.g. \"Cunning Deflection\").",
            "ID(s) — numeric buff IDs. One per line, or comma-separated.",
            "Category — groups related entries for browsing.",
            "Type — Buff (grey), Debuff (red), or Misc (golden). Sets the "
            "icon border and grouping.",
        ])

        # --- Buffs, Debuffs, and Misc ---

        types_section = self._add_section(inner, "Buffs, Debuffs, and Misc", [
            "Age of Conan doesn't label effects as buffs or debuffs; you "
            "make the call. The type sets the icon border and grouping.",
        ])
        self._add_subsection(types_section.content, "Buff", [
            "Positive effects, typically the removable bar on your "
            "character. Grey border.",
        ], title_color=THEME_COLORS['muted'])
        self._add_subsection(types_section.content, "Debuff", [
            "Negative effects, typically the non-removable bar or "
            "anything you track on a target. Red border.",
        ], title_color=THEME_COLORS['danger'])
        self._add_subsection(types_section.content, "Misc", [
            "Anything separated from Buff/Debuff. Golden border.",
            "The bundled database uses Misc for CC durations and heals-over-time.",
        ], title_color=THEME_COLORS['warning'])
        self._add_paragraph(types_section.content,
            "Some debuffs create a new instance per cast instead of "
            "refreshing one timer. The Flash combat-log API only exposes "
            "the latest instance, so on Target grids the timer shows the "
            "most recent cast, not other active copies.",
            foreground=THEME_COLORS['warning'])

        # --- Stacking ---

        stacking = self._add_section(inner, "Stacking", [
            "Some buffs have multiple stack levels, each with its own ID. "
            "Stacking options control how multiple IDs are read.",
        ])
        self._add_subsection(stacking.content, "Stacking disabled (default)", [
            "Multiple IDs are treated as ranks of the same buff. Only one "
            "rank is active at a time; a higher rank replaces a lower one.",
        ])
        self._add_subsection(stacking.content, "Stacking enabled", [
            "IDs are stack levels in order: stack 1 first, stack 2 second, "
            "and so on. The current level shows over the icon.",
        ])
        self._add_subsection(stacking.content, "Partial list (stacking only)", [
            "Turn on when you only have IDs for part of the stack range. "
            "Example: 5 IDs of a ×15 buff, set 'Start at' to 11.",
        ])
        self._add_subsection(stacking.content, "Stack range (stacking only, partial list off)", [
            "Show the icon only within a stack range. 'Start at' is when "
            "it appears; 'End at' is the last shown (0 means show all).",
        ])

        # Bottom spacer
        ttk.Frame(inner).pack(pady=PAD_TAB)

        # Dynamic wraplength on resize (debounced)
        self._last_canvas_w = 0
        self._resize_after_id = None
        canvas.bind('<Configure>', self._on_canvas_resize)

    def _on_canvas_resize(self, event):
        w = event.width
        if w <= 1 or w == self._last_canvas_w:
            return
        first_fire = self._last_canvas_w == 0
        self._last_canvas_w = w
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        if first_fire:
            # Apply immediately so initial wraplengths match real width before paint
            self._apply_wraplengths(w)
        else:
            self._resize_after_id = self.after(50, self._apply_wraplengths, w)

    def _apply_wraplengths(self, w):
        self._resize_after_id = None
        for lbl, margin in self._wrap_labels:
            lbl.configure(wraplength=self._target_width(margin, w))
        # Rich paragraphs relayout themselves via their own <Configure> binding,
        # which also fires when their CollapsibleSection is first opened.

    def _add_section(self, parent, title, paragraphs, initially_open=False, accent_color=None):
        section = CollapsibleSection(parent, title=title, initially_open=initially_open,
                                     accent_color=accent_color)
        section.pack(fill='x', padx=PAD_TAB, pady=(PAD_ROW, 0))
        for item in paragraphs:
            self._add_body_item(section.content, item, subsection=False)
        return section

    def _add_subsection(self, parent, title, paragraphs, title_color=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', padx=(PAD_INNER, 0), pady=(PAD_XS, 0))
        ttk.Label(frame, text=title, font=FONT_SECTION,
                  foreground=title_color or THEME_COLORS['heading']).pack(fill='x', pady=(0, PAD_XS))
        for item in paragraphs:
            self._add_body_item(frame, item, subsection=True)

    def _add_body_item(self, parent, item, subsection):
        margin = _SUBSECTION_MARGIN if subsection else _SECTION_MARGIN
        if isinstance(item, str):
            lbl = ttk.Label(parent, text=item, font=FONT_BODY,
                            foreground=THEME_COLORS['body'],
                            wraplength=_MAX_TEXT_WIDTH, justify='left')
            lbl.pack(fill='x', pady=(0, PAD_XS))
            self._wrap_labels.append((lbl, margin))
        else:
            self._add_rich_paragraph(parent, item)

    def _add_rich_paragraph(self, parent, parts, padx=(0, 0)):
        font = self._body_font
        line_h = font.metrics('linespace')

        tokens = []
        for text_part, color in parts:
            i = 0
            while i < len(text_part):
                j = i
                if text_part[i].isspace():
                    while j < len(text_part) and text_part[j].isspace():
                        j += 1
                    tokens.append((text_part[i:j], color, True))
                else:
                    while j < len(text_part) and not text_part[j].isspace():
                        j += 1
                    tokens.append((text_part[i:j], color, False))
                i = j

        canvas = tk.Canvas(parent, bg=self._frame_bg, highlightthickness=0, borderwidth=0,
                           height=line_h, takefocus=0)
        canvas.pack(fill='x', padx=padx, pady=(0, PAD_XS))

        def relayout(width):
            canvas.delete('all')
            if width <= 1:
                return
            x, y = 0, 0
            for word, color, is_space in tokens:
                word_w = font.measure(word)
                if is_space:
                    if x == 0:
                        continue
                    x += word_w
                    continue
                if x + word_w > width and x > 0:
                    x = 0
                    y += line_h
                canvas.create_text(x, y, text=word, anchor='nw', font=FONT_BODY,
                                   fill=color or THEME_COLORS['body'])
                x += word_w
            canvas.configure(height=y + line_h)

        canvas.bind('<Configure>', lambda e: relayout(min(_MAX_TEXT_WIDTH, e.width)))
        self.after_idle(lambda: relayout(min(_MAX_TEXT_WIDTH, canvas.winfo_width())))
        return canvas

    def _add_paragraph(self, parent, text, foreground=None):
        lbl = ttk.Label(parent, text=text, font=FONT_BODY,
                        foreground=foreground or THEME_COLORS['body'],
                        wraplength=_MAX_TEXT_WIDTH, justify='left')
        lbl.pack(fill='x', padx=(PAD_INNER, 0), pady=PAD_XS)
        self._wrap_labels.append((lbl, _SUBSECTION_MARGIN))
