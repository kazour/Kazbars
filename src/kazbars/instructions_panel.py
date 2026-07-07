import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import TypedDict

from .ui_components import create_scrollable_frame
from .ui_helpers import (
    FONT_BODY,
    FONT_HEADING,
    FONT_SECTION,
    FONT_SMALL,
    FONT_SMALL_BOLD,
    GRID_TYPE_COLORS,
    PAD_INNER,
    PAD_MICRO,
    PAD_SMALL,
    PAD_TAB,
    PAD_TINY,
    PAD_XS,
    THEME_COLORS,
    TK_COLORS,
)

# ============================================================================
# CONTENT MODEL
# ============================================================================
# The guide is data, not layout. Each section carries a category (for the nav
# grouping), a stable id (for selection + search), a title, and a list of
# blocks. A block is one of:
#   "text"                      a plain body paragraph
#   [("text", color), ...]      a rich paragraph (per-run color; None = body)
#   _note("text", color)        a colored standalone paragraph
#   _sub("Title", [items], c)   a subsection: a titled label over its own items
#                               (each item a plain or rich paragraph)
# Renderers below walk this structure; the nav and the search index are both
# built from it, so adding a section is a one-place edit.

_SUCCESS = THEME_COLORS['success']
_ACCENT = THEME_COLORS['accent']
_DANGER = THEME_COLORS['danger']
_WARNING = THEME_COLORS['warning']
_MUTED = THEME_COLORS['muted']


def _sub(title, items, color=None):
    return ('sub', title, items, color)


def _note(text, color):
    return ('note', text, color)


class _Section(TypedDict):
    cat: str
    id: str
    title: str
    body: list[object]


# Display order of the nav categories.
CATEGORIES = [
    'Getting Started',
    'Grids',
    'Buff Database',
    'Building & In-Game',
    'Live Overlays',
    'Extras',
    'Maintenance',
]

SECTIONS: list[_Section] = [
    {
        'cat': 'Getting Started',
        'id': 'quick-start',
        'title': 'Quick Start',
        'body': [
            'Four steps to a working grid.',
            _sub('1. Set your game folder', [
                'Click "(not set)" next to the Game: label at the bottom and '
                'pick your Age of Conan install folder. Click it again to '
                'change or clear it.',
            ]),
            _sub('2. Add a grid', [
                'In the Grids tab, click + Add Grid. The H-bar 1x10 preset is '
                'a good first grid for tracking your own buffs.',
            ]),
            _sub('3. Choose which buffs to track', [
                'Click Tracked Buffs... and pick buffs from the database. Only '
                'the buffs you select show up in the grid.',
            ]),
            _sub('4. Build and install', [
                [('Click ', None),
                 ('Build & Install', _SUCCESS),
                 (' at the bottom. This compiles your grids and writes them to '
                  'your game folder.', None)],
                "How you apply changes later depends on your setup — see "
                "'Building and Installing'.",
            ]),
        ],
    },
    {
        'cat': 'Getting Started',
        'id': 'what-builds',
        'title': 'What KazBars Builds',
        'body': [
            'Everything KazBars builds is one kind of mod or another. The kind '
            'tells you the one thing that matters: whether you ever need the '
            'app open again.',
            _sub('Set up once — then close the app', [
                [('Grids, the Cast Timer, the Stopwatch, Damage Numbers, and the '
                  'Default Buff Bars all install with one ', None),
                 ('Build & Install', _SUCCESS),
                 (". After that you type /reloadui in-game and you're done — they "
                  'keep working whether or not KazBars is running. Open it again '
                  'only when you want to change something.', None)],
            ]),
            _sub('Runs while you play — keep KazBars open', [
                [('The ', None),
                 ('Ethram-Fal Live Tracker', _ACCENT),
                 (' and ', None),
                 ('Deeps', _ACCENT),
                 (' are desktop overlays that read your combat log in real time. '
                  'They draw on top of the game while you play, so they only work '
                  'while KazBars is open.', None)],
            ]),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'player-target',
        'title': 'Player vs Target Grids',
        'body': [
            'Every grid tracks one source, set when you create it.',
            _sub('Player grid', [
                'Tracks buffs and debuffs on your own character.',
            ], GRID_TYPE_COLORS['player']),
            _sub('Target grid', [
                'Tracks buffs and debuffs on your current target (mob, '
                'friendly, or enemy player).',
            ], GRID_TYPE_COLORS['target']),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'modes',
        'title': 'Dynamic vs Static Mode',
        'body': [
            'Each grid runs in one of two modes:',
            _sub('Dynamic', [
                'Slots fill automatically as buffs activate, and empty when they expire.',
            ]),
            _sub('Dynamic options', [
                'Fill — left-to-right, right-to-left, top-to-bottom, '
                'bottom-to-top, or one of four diagonals.',
                'Sort — longest first, shortest first, or order applied.',
                'Order — Buffs first: misc, buffs, debuffs. '
                'Debuffs first: misc, debuffs, buffs. '
                'Mixed: sorted by time, no grouping.',
            ]),
            _sub('Static', [
                'Each slot is pinned to specific buffs. Empty when none are '
                'active; if several share a slot, the most recent wins.',
            ]),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'tracked-buffs',
        'title': 'Tracked Buffs',
        'body': [
            'You tell a grid which buffs to track in one of two ways, '
            'depending on its mode.',
            _sub('Dynamic mode', [
                'A list of buff names the grid watches for. Only listed buffs '
                'appear; an empty list shows nothing.',
            ]),
            _sub('Static mode', [
                'Assign buffs to each slot by position. Unassigned slots stay '
                'empty; if several share a slot, the most recent wins.',
            ]),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'display-options',
        'title': 'Grid Display Options',
        'body': [
            'These settings are per-grid.',
            'Timers — remaining duration below each icon.',
            'Flash — icons pulse near expiry. Set the threshold in seconds.',
            'Icon size and gaps — the size of each icon and the spacing '
            'between them.',
            "For where a grid sits on screen, see 'Applying and Positioning "
            "In-Game'.",
        ],
    },
    {
        'cat': 'Grids',
        'id': 'stacking',
        'title': 'Stacking',
        'body': [
            'Some buffs have multiple stack levels, each with its own ID. '
            'Stacking controls how those IDs are read.',
            _sub('Stacking disabled (default)', [
                'Multiple IDs are treated as ranks of the same buff. Only one '
                'rank is active at a time; a higher rank replaces a lower one.',
            ]),
            _sub('Stacking enabled', [
                'IDs are stack levels in order: stack 1 first, stack 2 second, '
                'and so on. The current level shows over the icon.',
            ]),
            _sub('Partial list (stacking only)', [
                'Turn on when you only have IDs for part of the stack range. '
                "Example: 5 IDs of a ×15 buff, set 'Start at' to 11.",
            ]),
            _sub('Stack range (stacking only, partial list off)', [
                "Show the icon only within a stack range. 'Start at' is when "
                "it appears; 'End at' is the last shown (0 means show all).",
            ]),
        ],
    },
    {
        'cat': 'Buff Database',
        'id': 'database',
        'title': 'The Buff Database',
        'body': [
            'Every effect has one or more numeric buff IDs. The Database '
            'tab maps those IDs to readable names and classifies them, so '
            'you can pick effects by name in grids.',
            'Use the search bar and category/type filters to find entries.',
            _sub('Adding or editing an entry', [
                'Name — a unique label (e.g. "Cunning Deflection").',
                'ID(s) — numeric buff IDs. One per line, or comma-separated.',
                'Category — groups related entries for browsing.',
                'Type — Buff (grey), Debuff (red), or Misc (golden). Sets the '
                'icon border and grouping.',
            ]),
        ],
    },
    {
        'cat': 'Buff Database',
        'id': 'buff-types',
        'title': 'Buffs, Debuffs, and Misc',
        'body': [
            "Age of Conan doesn't label effects as buffs or debuffs; you "
            'make the call. The type sets the icon border and grouping.',
            _sub('Buff', [
                'Positive effects, typically the removable bar on your '
                'character. Grey border.',
            ], _MUTED),
            _sub('Debuff', [
                'Negative effects, typically the non-removable bar or '
                'anything you track on a target. Red border.',
            ], _DANGER),
            _sub('Misc', [
                'Anything separated from Buff/Debuff. Golden border.',
                'The bundled database uses Misc for CC durations and heals-over-time.',
            ], _WARNING),
            _note(
                'Some debuffs create a new instance per cast instead of '
                'refreshing one timer. The Flash combat-log API only exposes '
                'the latest instance, so on Target grids the timer shows the '
                'most recent cast, not other active copies.',
                _WARNING),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'building',
        'title': 'Building and Installing',
        'body': [
            [('Build & Install', _SUCCESS),
             (' compiles your grid layout and writes it to your game folder. '
              'The compiler is bundled — nothing else to install.', None)],
            [('Aoc.exe is a third-party launcher bypass. KazBars asks once at '
              'first launch and reuses that answer for every build. ', None),
             ('Aoc.exe users must close the game before the first build.', _DANGER),
             (' After that, rebuild while playing.', None)],
            _note(
                'If you install or remove Aoc.exe later, clear and re-set the '
                'game folder. KazBars re-detects and adjusts.',
                _WARNING),
            _sub('After game patches', [
                [('A patch may overwrite your overlay files. If grids disappear '
                  'in-game, just click ', None),
                 ('Build & Install', _SUCCESS),
                 (' again.', None)],
            ]),
            _sub('Buff-discovery console', [
                "Don't know an effect's buff ID? Turn on Extras → Include "
                'buff-discovery console in builds, then Build & Install. In '
                'preview mode (Shift+Ctrl+Alt), the console logs every effect\'s '
                'name and buff ID as it lands on you or your target — copy the '
                'ID into the Database.',
                "It's off by default and only included when you enable it, so "
                "finished builds don't carry it. Turn it off and rebuild to "
                'remove it.',
            ]),
            _sub('Removing KazBars from your game folder', [
                'Game → Uninstall from game client… removes KazBars.swf '
                'and related files from your Age of Conan install.',
            ]),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'positioning',
        'title': 'Applying and Positioning In-Game',
        'body': [
            'How you reload the overlay and place grids on screen depends on '
            'whether you use Aoc.exe.',
            _sub('Preview mode', [
                'Press Shift+Ctrl+Alt in-game to toggle. Each grid appears as '
                'a colored rectangle with its name and live X/Y coordinates. '
                'Preview mode is only for positioning; all other settings are '
                'configured in the app.',
            ]),
            _sub('With Aoc.exe (launcher bypass)', [
                'Apply with /reloadui. Drag grids to position; they save '
                'automatically and persist between sessions.',
            ]),
            _sub('Without Aoc.exe (standard launcher)', [
                'Apply with /reloadui, then /reloadgrids. The launcher resets '
                "positions each session, so dragging doesn't stick. Read X/Y "
                'from preview mode, enter them in the Grids tab, and rebuild.',
            ]),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'resolution',
        'title': 'Game Resolution',
        'body': [
            'Game → Game resolution... sets the screen size KazBars builds '
            'for. Grid X/Y are positions on that screen, so the resolution '
            'has to match the one you play at.',
            'Change it and your loaded grids re-anchor to the new size — a '
            'layout built for 1920×1080 scales to 2560×1440 without '
            'repositioning every grid by hand. Rebuild to apply.',
        ],
    },
    {
        'cat': 'Live Overlays',
        'id': 'deeps',
        'title': 'Deeps',
        'body': [
            'Always-on-top combat meter that reads your combat log. Five '
            'rolling numbers: DPS out, DPS in, HPS out, HPS in, and ΔHP in '
            "(your net health change per second). It's a live overlay, so it "
            'only shows numbers while KazBars is open.',
            _sub('Setup', [
                [('Click ', None),
                 ('⚔ Deeps', _ACCENT),
                 (' at the bottom right, then ', None),
                 ('Start', _SUCCESS),
                 (". Numbers appear once you're in a fight.", None)],
            ]),
            _sub('Positioning', [
                'Drag the overlay to position. Use Lock in the panel to fix it '
                'in place and pass game clicks through; unlock from the same '
                'button. Choose a Horizontal or Vertical layout, and pick which '
                'of the five cells to show under Overlay Cells.',
            ]),
            _sub('Readout', [
                'Window — how many seconds the rolling average covers. A wider '
                'window is steadier but reacts later.',
                'Style — Live shows every spike, Steady is the calm middle, Calm '
                'smooths heavily for peripheral glances.',
            ]),
            _sub('Alarms and pet damage', [
                'Alarm & Tints set when the DPS-out cell pulses and when the '
                'ΔHP-in cell ramps to orange as your deficit grows.',
                'Pet damage counts only your own pet, and is off unless you '
                'enable it.',
            ]),
        ],
    },
    {
        'cat': 'Live Overlays',
        'id': 'ethram-fal',
        'title': 'Ethram-Fal Live Tracker',
        'body': [
            'Always-on-top overlay for the Viscous Seed cycle in the '
            'Ethram-Fal raid. It reads your combat log so the raid can '
            'coordinate scorpion kills. Keep KazBars open for the pull — it '
            'only runs while the app is.',
            _sub('Setup', [
                [('Click ', None),
                 ('⏱ Ethram-Fal', _ACCENT),
                 (' at the bottom right. Type /logcombat on in-game once per '
                  'session, then ', None),
                 ('Start Monitoring', _SUCCESS),
                 ('.', None)],
                'Test Cycle simulates a full ~40s cycle for positioning.',
            ]),
            _sub('Positioning', [
                'Drag to position. Click the ○ glyph to lock; it becomes ●, '
                'and game clicks pass through to AoC. Unlock from the panel\'s '
                'Lock button.',
            ]),
            _sub('The cycle', [
                'Every ~40s: Viscous Seed debuffs a player, Lotus Fixation '
                'locks onto another 4s later. Silence the plants, drag the '
                'scorpions to the pile, and kill them after 31s but before '
                'the next seed.',
                'Phase 4: two seeds at once, kite the scorpions. Syphon '
                'clouds interrupt the cycle.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'cast-timer',
        'title': 'Cast Timer',
        'body': [
            "A timer-only overlay for your own and your target's cast time — "
            "floating text over the game's cast bar, with no bar of its own. "
            'Off by default.',
            _sub('Turn it on', [
                'Open the Cast Timer strip pinned above the grid list and flip '
                'Enabled. One toggle runs both the Player and Target sides.',
            ]),
            _sub('Settings', [
                'Player / Target X/Y — where each timer sits on screen.',
                'Bold, Size, Color — shared by both sides.',
                'Show — Elapsed counts up, Total is the estimated cast length, '
                'Both shows 1.2 / 2.5.',
            ]),
            _sub('Positioning', [
                'Set X/Y in the strip, or press Shift+Ctrl+Alt in-game to drag '
                'the timer. Rebuild and reload to apply.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'default-buff-bars',
        'title': 'Default Buff Bars',
        'body': [
            "Extras → Default buff bars… edits Age of Conan's own built-in "
            'buff bars — the Player and Target portrait icons, the top bar, '
            'and floating portraits. This is separate from your KazBars grids, '
            'which it leaves alone.',
            _sub('What you can change', [
                'Icon size, spacing, and column count per bar, plus a friendly / '
                'hostile filter. Toggle a bar off to hide it entirely.',
            ]),
            _sub('Where it writes', [
                'Edits go only to your Customized UI skin, and each file is '
                'backed up once before the first change. Set your game folder '
                'first.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'damage-numbers',
        'title': 'Damage Numbers',
        'body': [
            'Extras → Damage number mod… installs a leaner rewrite of Age of '
            "Conan's floating combat numbers, in place of the stock ones. The "
            'headline fix: ranged hits stop shrinking to nothing at distance.',
            _sub('Turn it on', [
                [('Off by default. Flip ', None),
                 ('Enable', _SUCCESS),
                 (', set your options, then ', None),
                 ('Build & Install', _SUCCESS),
                 (' — it applies on your next build, same as grids.', None)],
                'Your stock file is backed up the first time, so turning it off '
                'and rebuilding restores the original.',
            ]),
            _sub('What you can tune', [
                'Keep ranged numbers big — holds the size of ranged hits past '
                "~15 real metres so they don't fade with distance. Melee is "
                'never touched.',
                'Shadow, pop-in, and fade speed — with Default and Performance '
                'presets.',
                'Where numbers land — above the target, in fixed columns, or a '
                'zig-zag stack.',
                'Group my resource numbers — routes your own mana / stamina '
                'losses into the same column as your resource gains. Drains '
                'from enemies still float over them.',
                'Separate resources into Column B — drops everything that lands '
                'on you into fixed columns: incoming damage in one, heals / '
                'mana / stamina in the next.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'damage-number-colors',
        'title': 'Damage Number Colors',
        'body': [
            'Extras → Damage number colors… recolors every combat-number '
            'source on its own — incoming vs outgoing hits, crits, spells, '
            'combos, heals, mana, and stamina — laid out self on the left, '
            'your target on the right.',
            [('Works like the ', None),
             ('Default Buff Bars', _ACCENT),
             (' editor: pick colors, hit ', None),
             ('Apply', _SUCCESS),
             (', then type /reloadui in-game to see them. No ', None),
             ('Build & Install', _SUCCESS),
             (' and no master toggle — it edits the game files directly.', None)],
            _sub('It stands alone', [
                "These are Age of Conan's own colors — you don't need the "
                'Damage Numbers mod turned on to change them.',
                'Reset to game default pulls the original color straight from '
                'the game files.',
                'Colors you set stick even if you turn the mod off or uninstall '
                'it — use Reset if you want stock back.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'stopwatch',
        'title': 'In-Game Stopwatch',
        'body': [
            'Extras → In-game stopwatch… adds a count-up Start / Pause / Reset '
            'timer that lives inside the overlay. It works in fullscreen and '
            'never steals focus from AoC. Off by default; when off, the build '
            'carries no stopwatch code at all.',
            _sub('Turn it on', [
                [('Open the dialog, flip ', None),
                 ('Enabled', _SUCCESS),
                 (', then ', None),
                 ('Build & Install', _SUCCESS),
                 ('. It ships with your next build, same as grids.', None)],
            ]),
            _sub('Using it in-game', [
                'A compact draggable panel shows h:mm:ss. The − button collapses '
                'it to just the title bar, which then shows the running time.',
                'Drag the title bar to move it; live coordinates show as you '
                'drag. Type them into the dialog to pin a spot. Aoc.exe clients '
                'remember the position and collapsed state on their own.',
            ]),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'backup',
        'title': 'Backup and Restore',
        'body': [
            'Game → Backup & restore game settings... writes one portable '
            '.zip of your Age of Conan config — keybinds, HUD layout, '
            'graphics, every character — plus your KazBars profiles and '
            'settings. This is your recovery path after a reformat or a '
            'corrupted profile.',
            _sub('Restoring', [
                'Restore replaces your current settings, so it snapshots them '
                'first — a bad restore is reversible. Close Age of Conan before '
                'backing up or restoring.',
            ]),
        ],
    },
]


# ============================================================================
# SEARCH INDEX
# ============================================================================
def _flatten_text(value, out):
    """Collect every human-readable string in a block tree into `out`."""
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, list):
        for part in value:
            _flatten_text(part, out)
    elif isinstance(value, tuple):
        kind = value[0]
        if kind == 'note':
            out.append(value[1])
        elif kind == 'sub':
            out.append(value[1])
            for item in value[2]:
                _flatten_text(item, out)
        else:
            # A rich run: ("text", color)
            out.append(value[0])


def _haystack(section):
    words = [section['title'], section['cat']]
    for block in section['body']:
        _flatten_text(block, words)
    return ' '.join(words).lower()


# Reading column constraints. ~75ch upper bound at 9px Segoe (≈5px/char average)
# keeps line length within the 65-75ch comfort range from the design laws.
_MIN_TEXT_WIDTH = 220
_MAX_TEXT_WIDTH = 460

# Pixel margins from the content canvas width to the text-wrap width: outer
# padding both sides + scrollbar + ttk frame chrome, with subsections one
# indent deeper. Empirically tuned for ttkbootstrap-darkly chrome.
_CONTENT_MARGIN = PAD_TAB * 2 + 24
_SUBSECTION_MARGIN = _CONTENT_MARGIN + PAD_INNER + 4

_NAV_WIDTH = 210


class InstructionsPanel(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        self._body_font = tkfont.Font(font=FONT_BODY)
        self._frame_bg = ttk.Style().lookup('TFrame', 'background') or TK_COLORS['bg']
        self._haystacks = {s['id']: _haystack(s) for s in SECTIONS}
        self._section_by_id = {s['id']: s for s in SECTIONS}
        self._nav_rows = {}        # id -> tk.Label
        self._nav_order = []       # ordered [('header', cat, w, [ids]) | ('row', id, w, None)]
        self._wrap_labels = []     # [(label, margin)] for the live content section
        self._current = None
        self._last_content_w = 0
        self._resize_after_id = None
        self._create_widgets()

    # -- layout ------------------------------------------------------------
    def _create_widgets(self):
        nav = ttk.Frame(self, width=_NAV_WIDTH)
        nav.pack(side='left', fill='y')
        nav.pack_propagate(False)

        search_box = ttk.Frame(nav)
        search_box.pack(fill='x', padx=PAD_SMALL, pady=(PAD_SMALL, PAD_XS))
        ttk.Label(search_box, text='Search the guide', font=FONT_SMALL,
                  foreground=_MUTED).pack(anchor='w')
        self._search_var = tk.StringVar()
        entry = ttk.Entry(search_box, textvariable=self._search_var)
        entry.pack(fill='x', pady=(PAD_TINY, 0))
        self._search_var.trace_add('write', lambda *_: self._apply_filter())

        nav_outer, nav_inner, _nav_canvas = create_scrollable_frame(nav)
        nav_outer.pack(fill='both', expand=True)
        self._nav_inner = nav_inner

        tk.Frame(self, width=1, bg=TK_COLORS['border']).pack(side='left', fill='y')

        content_outer, content_inner, content_canvas = create_scrollable_frame(self)
        content_outer.pack(side='left', fill='both', expand=True)
        self._content_inner = content_inner
        self._content_canvas = content_canvas
        content_canvas.bind('<Configure>', self._on_content_resize)

        self._build_nav()
        self._apply_filter()  # packs the nav and selects the first section

    def _build_nav(self):
        for cat in CATEGORIES:
            ids = [s['id'] for s in SECTIONS if s['cat'] == cat]
            if not ids:
                continue
            header = tk.Label(self._nav_inner, text=cat.upper(), font=FONT_SMALL_BOLD,
                              fg=_MUTED, bg=TK_COLORS['bg'], anchor='w',
                              padx=PAD_SMALL, pady=PAD_MICRO)
            self._nav_order.append(('header', cat, header, ids))
            for sid in ids:
                row = tk.Label(self._nav_inner, text=self._section_by_id[sid]['title'],
                               font=FONT_BODY, fg=THEME_COLORS['body'], bg=TK_COLORS['bg'],
                               anchor='w', padx=PAD_INNER, pady=PAD_TINY, cursor='hand2')
                self._bind_nav_row(row, sid)
                self._nav_rows[sid] = row
                self._nav_order.append(('row', sid, row, None))

    def _bind_nav_row(self, row, sid):
        row.bind('<Button-1>', lambda _e: self._select(sid))
        row.bind('<Enter>', lambda _e: self._hover(sid, True))
        row.bind('<Leave>', lambda _e: self._hover(sid, False))

    # -- nav behavior ------------------------------------------------------
    def _matches(self, sid, query):
        return not query or query in self._haystacks[sid]

    def _apply_filter(self):
        query = self._search_var.get().strip().lower()
        for _kind, _key, widget, _extra in self._nav_order:
            widget.pack_forget()
        visible = []
        for kind, key, widget, ids in self._nav_order:
            if kind == 'header':
                if any(self._matches(sid, query) for sid in ids):
                    widget.pack(fill='x', pady=(PAD_SMALL, 0))
            elif self._matches(key, query):
                widget.pack(fill='x')
                visible.append(key)
        if self._current not in visible:
            if visible:
                self._select(visible[0])
            else:
                self._render_no_match(query)

    def _hover(self, sid, inside):
        if sid == self._current:
            return
        self._nav_rows[sid].configure(
            bg=TK_COLORS['input_bg'] if inside else TK_COLORS['bg'])

    def _select(self, sid):
        self._current = sid
        for other, row in self._nav_rows.items():
            if other == sid:
                row.configure(bg=TK_COLORS['select_bg'], fg=TK_COLORS['select_fg'])
            else:
                row.configure(bg=TK_COLORS['bg'], fg=THEME_COLORS['body'])
        self._render_content(self._section_by_id[sid])

    # -- content rendering -------------------------------------------------
    def _clear_content(self):
        for child in self._content_inner.winfo_children():
            child.destroy()
        self._wrap_labels = []

    def _render_no_match(self, query):
        self._current = None
        self._clear_content()
        ttk.Label(self._content_inner,
                  text=f'No matches for "{query}".',
                  font=FONT_BODY, foreground=_MUTED).pack(
            anchor='w', padx=PAD_TAB, pady=PAD_TAB)

    def _render_content(self, section):
        self._clear_content()
        inner = self._content_inner

        ttk.Label(inner, text=section['cat'], font=FONT_SMALL,
                  foreground=_MUTED).pack(anchor='w', padx=PAD_TAB, pady=(PAD_TAB, 0))
        ttk.Label(inner, text=section['title'], font=FONT_HEADING,
                  foreground=THEME_COLORS['heading']).pack(
            anchor='w', fill='x', padx=PAD_TAB, pady=(0, PAD_SMALL))

        for block in section['body']:
            self._render_block(inner, block)

        ttk.Frame(inner).pack(pady=PAD_TAB)
        self._content_canvas.yview_moveto(0)
        self.after_idle(lambda: self._apply_wraplengths(self._content_canvas.winfo_width()))

    def _render_block(self, parent, block):
        if isinstance(block, str):
            self._paragraph(parent, block, _CONTENT_MARGIN, padx=PAD_TAB)
        elif isinstance(block, list):
            self._rich_paragraph(parent, block, padx=(PAD_TAB, PAD_TAB))
        elif isinstance(block, tuple) and block[0] == 'note':
            self._paragraph(parent, block[1], _CONTENT_MARGIN,
                            padx=PAD_TAB, foreground=block[2])
        elif isinstance(block, tuple) and block[0] == 'sub':
            self._subsection(parent, block[1], block[2], block[3])

    def _subsection(self, parent, title, items, title_color):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', padx=(PAD_TAB, PAD_TAB), pady=(PAD_SMALL, 0))
        ttk.Label(frame, text=title, font=FONT_SECTION,
                  foreground=title_color or THEME_COLORS['heading']).pack(
            anchor='w', pady=(0, PAD_XS))
        for item in items:
            if isinstance(item, list):
                self._rich_paragraph(frame, item, padx=(PAD_INNER, 0))
            else:
                self._paragraph(frame, item, _SUBSECTION_MARGIN, padx=(PAD_INNER, 0))

    def _paragraph(self, parent, text, margin, padx=0, foreground=None):
        lbl = ttk.Label(parent, text=text, font=FONT_BODY,
                        foreground=foreground or THEME_COLORS['body'],
                        wraplength=_MAX_TEXT_WIDTH, justify='left')
        lbl.pack(fill='x', padx=padx, pady=(0, PAD_XS))
        self._wrap_labels.append((lbl, margin))

    def _rich_paragraph(self, parent, parts, padx=(0, 0)):
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

    # -- resize ------------------------------------------------------------
    def _on_content_resize(self, event):
        w = event.width
        if w <= 1 or w == self._last_content_w:
            return
        self._last_content_w = w
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(50, self._apply_wraplengths, w)

    def _apply_wraplengths(self, w):
        self._resize_after_id = None
        for lbl, margin in self._wrap_labels:
            try:
                lbl.configure(wraplength=min(_MAX_TEXT_WIDTH,
                                             max(_MIN_TEXT_WIDTH, w - margin)))
            except tk.TclError:
                pass
