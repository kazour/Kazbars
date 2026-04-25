import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .ui_helpers import (
    THEME_COLORS, GRID_TYPE_COLORS, TK_COLORS,
    FONT_BODY, FONT_SECTION,
    PAD_TAB, PAD_SMALL, PAD_XS, PAD_ROW, PAD_INNER,
)
from .ui_widgets import CollapsibleSection
from .ui_components import create_scrollable_frame


class InstructionsPanel(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._wrap_labels = []  # (label, margin) pairs for dynamic wraplength
        self._create_widgets()

    def _create_widgets(self):
        outer, inner, canvas = create_scrollable_frame(self)
        outer.pack(fill='both', expand=True)
        self._canvas = canvas
        self._frame_bg = ttk.Style().lookup('TFrame', 'background') or TK_COLORS['bg']

        intro = ttk.Label(
            inner,
            text="Kaz Grids is a Windows app for designing buff and debuff "
            "overlays for Age of Conan. Track effects on your own character "
            "or on your current target.",
            font=FONT_BODY, foreground=THEME_COLORS['body'],
            wraplength=700, justify='left',
        )
        intro.pack(fill='x', padx=PAD_TAB, pady=(PAD_TAB, PAD_SMALL))
        self._wrap_labels.append((intro, PAD_TAB * 2))

        # --- Quick Start ---

        qs = self._add_section(inner, "Quick Start", [
            "Follow these steps to get your first grid running:",
        ], initially_open=True)
        self._add_subsection(qs.content, "1. Set your game folder", [
            "Click the \"Game:\" label at the bottom and choose your Age of "
            "Conan install folder. Right-click later to change or clear it.",
        ])
        self._add_subsection(qs.content, "2. Create a grid", [
            "Click + Add Grid in the Grids tab. The 1\u00d710 horizontal bar "
            "is a good starting point for tracking player buffs.",
        ])
        self._add_subsection(qs.content, "3. Choose which buffs to track", [
            "Use the Tracked Buffs button to pick buffs from the database. "
            "Only buffs you've selected will appear in the grid.",
        ])
        self._add_subsection(qs.content, "4. Build and install", [
            [("Click ", None),
             ("Build & Install", THEME_COLORS['success']),
             (" at the bottom. This compiles your grids and writes them "
              "to your game folder.", None)],
            "How you apply later changes depends on your setup \u2014 "
            "see 'Building and Installing' below.",
        ])

        # --- Player vs Target ---

        grid_types = self._add_section(inner, "Player vs Target Grids", [
            "Each grid is tied to one source \u2014 chosen when you create the grid.",
        ])
        self._add_subsection(grid_types.content, "Player grid", [
            "Tracks buffs and debuffs on your own character.",
        ], title_color=GRID_TYPE_COLORS['player'])
        self._add_subsection(grid_types.content, "Target grid", [
            "Tracks buffs and debuffs on whoever you're targeting \u2014 "
            "a mob, a friendly player, or an enemy player.",
        ], title_color=GRID_TYPE_COLORS['target'])

        # --- Grid Modes ---

        modes = self._add_section(inner, "Dynamic vs Static Mode", [
            "Each grid runs in one of two modes:",
        ])
        self._add_subsection(modes.content, "Dynamic", [
            "Slots fill automatically as buffs activate, and empty when they expire. "
            "You control the fill direction, sort order, and grouping.",
        ])
        self._add_subsection(modes.content, "Dynamic options", [
            "Fill direction \u2014 left-to-right, right-to-left, top-to-bottom, "
            "bottom-to-top, or diagonal.",
            "Sort order \u2014 longest timer first, shortest timer first, or "
            "the order buffs were applied.",
            "Grouping \u2014 Buff First: misc, then buffs, then debuffs. "
            "Debuff First: misc, then debuffs, then buffs. "
            "Mixed: no type grouping; all effects sorted together by time.",
        ])
        self._add_subsection(modes.content, "Static", [
            "Each slot is pinned to one or more specific buffs. The slot shows "
            "the buff when active and stays empty when it's not.",
            "If multiple buffs are assigned to the same slot, the most recently "
            "applied one is shown.",
        ])

        # --- Whitelist & Slot Assignments ---

        wl_section = self._add_section(inner, "Tracked Buffs", [
            "These are the two ways to tell a grid which buffs to track.",
        ])
        self._add_subsection(wl_section.content, "Tracked Buffs (Dynamic mode)", [
            "A list of buff names the grid watches for. Only buffs on this list "
            "appear in the grid. If no buffs are tracked, nothing is shown.",
        ])
        self._add_subsection(wl_section.content, "Tracked Buffs (Static mode)", [
            "Assign one or more buffs to each slot by position. "
            "Unassigned slots stay empty.",
            "If multiple buffs share a slot, the most recently applied one is shown.",
        ])

        # --- Buffs, Debuffs, and Misc ---

        types_section = self._add_section(inner, "Buffs, Debuffs, and Misc", [
            "Age of Conan doesn't label effects as buffs or debuffs \u2014 you "
            "make the call. Each buff ID in the database is tagged Buff, "
            "Debuff, or Misc; the type sets the icon border color and "
            "controls grouping.",
        ])
        self._add_subsection(types_section.content, "Buff", [
            "Effects you consider positive \u2014 typically the removable bar "
            "on your own character. Grey border.",
        ], title_color=THEME_COLORS['muted'])
        self._add_subsection(types_section.content, "Debuff", [
            "Effects you consider negative \u2014 typically the non-removable "
            "bar, or anything you track on a target. Red border.",
        ], title_color=THEME_COLORS['danger'])
        self._add_subsection(types_section.content, "Misc", [
            "Anything you want separated from Buff/Debuff. Golden border.",
            "The included database uses Misc for CC durations and heals-over-time.",
        ], title_color=THEME_COLORS['warning'])
        self._add_paragraph(types_section.content,
            "Non-Unique debuffs on Target grids show unreliable timers \u2014 "
            "multiple casters' copies overwrite each other.",
            foreground=THEME_COLORS['warning'])

        # --- Buff Database ---

        db_section = self._add_section(inner, "The Buff Database", [
            "Every effect in Age of Conan has one or more numeric buff IDs. "
            "The Database tab is where you map those IDs to human-readable names "
            "and decide how each one is classified \u2014 so you can pick effects "
            "by name when setting up grids and have them grouped and colored correctly.",
            "Use the search bar and category/type filters to find what you need.",
        ])
        self._add_subsection(db_section.content, "Adding or editing an entry", [
            "Name \u2014 a unique label for this effect (e.g. \"Cunning Deflection\").",
            "ID(s) \u2014 the numeric buff ID(s). Enter one per line or "
            "comma-separated.",
            "Category \u2014 groups related entries together for easier browsing.",
            "Type \u2014 your classification of this effect. Sets the icon border "
            "color and controls grouping: Buff (grey), Debuff (red), Misc (golden).",
        ])

        # --- Stacking ---

        stacking = self._add_section(inner, "Stacking", [
            "Some buffs have multiple stack levels, each with its own buff ID. "
            "The stacking options in the database editor control how multiple IDs "
            "are interpreted.",
        ])
        self._add_subsection(stacking.content, "Stacking disabled (default)", [
            "Multiple IDs are treated as different ranks of the same buff. "
            "Only one rank can be active at a time \u2014 a higher rank replaces "
            "a lower one.",
        ])
        self._add_subsection(stacking.content, "Stacking enabled", [
            "IDs represent increasing stack levels. Enter them in order: "
            "stack 1 first, stack 2 second, and so on. The current stack "
            "number is displayed over the icon.",
        ])
        self._add_subsection(stacking.content, "Partial list (stacking only)", [
            "Turn this on when you only have IDs for part of the stack range. "
            "For example, if you have the last 5 IDs of a \u00d715 buff, enter "
            "those 5 IDs and set 'Start at' to 11.",
        ])
        self._add_subsection(stacking.content, "Stack range (stacking only, partial list off)", [
            "When you have the full ID list but only want the icon to appear "
            "within a certain range. 'Start at' is when the icon becomes visible, "
            "'End at' is the last stack shown (0 means show all).",
        ])

        # --- Grid display options ---

        self._add_section(inner, "Grid Display Options", [
            "Timers \u2014 show the remaining duration below each buff icon.",
            "Flash \u2014 icons pulse when a buff is about to expire. Set the "
            "threshold in seconds.",
            "Icon size and gaps are also per-grid settings in the Grids tab. "
            "For where grids appear on screen, see "
            "'Positioning Grids In-Game'.",
        ])

        # --- Building & Installing ---

        build_section = self._add_section(inner, "Building and Installing", [
            [("Build & Install", THEME_COLORS['success']),
             (" compiles your grid layout and writes it to your game folder. "
              "The compiler is bundled \u2014 no extra setup needed.", None)],
        ])
        self._add_paragraph(build_section.content,
            "Aoc.exe is a third-party tool that bypasses the standard launcher. "
            "Kaz Grids asks once at first launch whether you use it; that answer "
            "drives every future build. Aoc.exe users must close the game before "
            "the first build — after that, rebuild any time and /reloadui."
        )
        self._add_subsection(build_section.content, "With Aoc.exe (launcher bypass)", [
            "Rebuild any time, then type /reloadui in chat to apply.",
        ])
        self._add_subsection(build_section.content, "Without Aoc.exe (standard launcher)", [
            "Rebuild any time, then type /reloadui then /reloadgrids to apply.",
            "The launcher resets grid positions each session \u2014 "
            "see 'Positioning Grids In-Game'.",
        ])
        self._add_paragraph(build_section.content,
            "If you install or remove Aoc.exe, change the game folder so Kaz "
            "Grids re-asks the bypass question \u2014 grids won't work if built "
            "for the wrong mode.",
            foreground=THEME_COLORS['warning'])
        self._add_subsection(build_section.content, "After game patches", [
            [("A patch may overwrite your overlay files. If grids disappear "
              "in-game, just click ", None),
             ("Build & Install", THEME_COLORS['success']),
             (" again.", None)],
        ])
        self._add_subsection(build_section.content, "Removing Kaz Grids from your game folder", [
            "File \u2192 Uninstall from game folder\u2026 removes KazGrids.swf "
            "and related files from your Age of Conan install.",
        ])

        # --- Positioning ---

        positioning = self._add_section(inner, "Positioning Grids In-Game", [
            "Preview mode is how you place grids on screen. Press "
            "Shift+Ctrl+Alt while in-game to toggle it \u2014 all your grids "
            "appear with sample icons so you can see them even when no "
            "buffs are active.",
            "Preview mode is only for positioning. All other grid settings "
            "\u2014 icon size, gaps, colors, tracked buffs, mode \u2014 are "
            "configured in the app.",
        ])
        self._add_subsection(positioning.content, "With Aoc.exe (launcher bypass)", [
            "Drag grids to where you want them. Positions save automatically "
            "and persist between sessions.",
        ])
        self._add_subsection(positioning.content, "Without Aoc.exe (standard launcher)", [
            "The launcher resets grid positions each session, so dragging "
            "in-game doesn't stick. Instead: read each grid's X/Y coordinates "
            "from preview mode, enter them in the Grids tab, and rebuild.",
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
            lbl.configure(wraplength=min(self._MAX_TEXT_WIDTH, max(200, w - margin)))
        # Rich paragraphs relayout themselves via their own <Configure> binding

    # Section/subsection margins relative to canvas edge:
    #   section content:    PAD_TAB + collapse_indent + scrollbar ≈ 80
    #   subsection content: PAD_TAB + collapse_indent + PAD_INNER + scrollbar ≈ 100
    _SECTION_MARGIN = 80
    _SUBSECTION_MARGIN = 100
    _MAX_TEXT_WIDTH = 700   # Cap reading line width so wide windows stay scannable

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
        if isinstance(item, str):
            margin = self._SUBSECTION_MARGIN if subsection else self._SECTION_MARGIN
            wl = 620 if subsection else 650
            lbl = ttk.Label(parent, text=item, font=FONT_BODY,
                            foreground=THEME_COLORS['body'], wraplength=wl,
                            justify='left')
            lbl.pack(fill='x', pady=(0, PAD_XS))
            self._wrap_labels.append((lbl, margin))
        else:
            self._add_rich_paragraph(parent, item)

    def _add_rich_paragraph(self, parent, parts):
        font = tkfont.Font(font=FONT_BODY)
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
        canvas.pack(fill='x', pady=(0, PAD_XS))

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

        canvas.bind('<Configure>', lambda e: relayout(min(self._MAX_TEXT_WIDTH, e.width)))
        self.after_idle(lambda: relayout(min(self._MAX_TEXT_WIDTH, canvas.winfo_width())))
        return canvas

    def _add_paragraph(self, parent, text, foreground=None):
        lbl = ttk.Label(parent, text=text, font=FONT_BODY,
                        foreground=foreground or THEME_COLORS['body'],
                        wraplength=650, justify='left')
        lbl.pack(fill='x', padx=(PAD_INNER, 0), pady=PAD_XS)
        self._wrap_labels.append((lbl, self._SUBSECTION_MARGIN))
