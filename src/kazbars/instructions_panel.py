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
#   _link("Title", "id")        a click-through to another section
#   _sub("Title", [items], c)   a subsection: a titled label over its own items
#                               (each item a plain or rich paragraph, or a link)
# Renderers below walk this structure; the nav and the search index are both
# built from it, so adding a section is a one-place edit.
#
# Section ids are anchors: _link targets resolve against them at import time
# (see _validate_link_targets), so a typo'd or renamed id fails on import rather
# than dead-ending a reader. Renaming an id means updating every link to it.

_SUCCESS = THEME_COLORS['success']
_ACCENT = THEME_COLORS['accent']
_DANGER_TEXT = THEME_COLORS['danger_text']
_WARNING = THEME_COLORS['warning']
_MUTED = THEME_COLORS['muted']


def _sub(title, items, color=None):
    return ('sub', title, items, color)


def _note(text, color):
    return ('note', text, color)


def _link(label, target_id):
    """A jump to another section. `label` must be that section's exact title —
    the reason for following it belongs in the sentence before, not in here."""
    return ('link', label, target_id)


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
                'Click "(not set)" next to Game: at the bottom. Pick your '
                'Age of Conan folder. Click again to change or clear it.',
            ]),
            _sub('2. Add a grid', [
                'In the Grids tab, click + Add Grid. The H-bar 1x10 preset '
                'is a good first grid.',
            ]),
            _sub('3. Choose which buffs to track', [
                "Click the grid's preview and pick from the database. Only "
                'selected buffs appear in the grid. On a static grid, click '
                'a slot instead.',
            ]),
            _sub('4. Build and install', [
                [('Click ', None),
                 ('Build & Install', _SUCCESS),
                 (' at the bottom. It compiles your grids into the game.', None)],
                'First build: close the game and the patcher. After that, '
                'rebuild anytime and type /reloadui in-game.',
                _link('Building and Installing', 'building'),
            ]),
        ],
    },
    {
        'cat': 'Getting Started',
        'id': 'what-builds',
        'title': 'What KazBars Builds',
        'body': [
            'KazBars makes two kinds of thing. The difference: whether the '
            'app must stay open.',
            _sub('Built into the game — then close the app', [
                [('Grids, Damage Numbers, the Stopwatch, the Inspect Target, '
                  'the Cast Timer, the Console and the Onslaught Tracker are '
                  'compiled in by ', None),
                 ('Build & Install', _SUCCESS),
                 ('. They work with the app closed. Open it again only to '
                  'change something.', None)],
                'The two skin editors write to the game directly — no build '
                'at all.',
                _link('How Extras Ship', 'extras-shipping'),
            ]),
            _sub('Runs while you play — keep KazBars open', [
                [('The ', None),
                 ('Ethram-Fal Live Tracker', _ACCENT),
                 (' and ', None),
                 ('Deeps', _ACCENT),
                 (' read your combat log live. They draw over the game, so '
                  'they need KazBars open.', None)],
            ]),
        ],
    },
    {
        'cat': 'Getting Started',
        'id': 'profiles',
        'title': 'Your Profile',
        'body': [
            'KazBars keeps one profile — every grid, plus the extras and '
            'live overlays that go with it. It lives in '
            'userdata/profile.yml.',
            _sub("No Save button — it autosaves", [
                'Every edit writes to disk about a second after you stop '
                "typing or dragging. There's nothing to lose by closing the "
                'app. Ctrl+S saves right now.',
            ]),
            _sub('Starting over, and getting back', [
                'File ▸ Reset profile to defaults… asks first, then replaces '
                'your profile with the starter layout, sized for your game '
                'resolution. The profile keeps its name.',
                'File ▸ Revert to session start brings back the profile you '
                'had when KazBars opened — after edits, an Import or a '
                'Reset. It lasts until you close the app.',
            ]),
            _sub('Sharing a profile', [
                'File ▸ Export profile… writes one self-contained '
                '<name>.kazbars.yml file. File ▸ Import profile… opens one '
                'and replaces the profile you have open; Revert to session '
                'start undoes it.',
                'Import also opens a .kazbars.json export from 3.1, or a '
                'profile file copied from a 3.1 userdata/profiles folder.',
                'Custom buffs the profile tracks travel inside the file and '
                "are added to your database on import, so it doesn't need "
                "to know them first (if they can't be added, the profile "
                'still imports and the toast says so). Screen positions '
                'travel too, as fractions of your resolution — a shared '
                'profile lands proportionally on any screen.',
                'To share a few grids instead of the whole profile, use '
                "Export grid… in a grid card's Move… menu. File ▸ Import "
                'grid… adds a grids file to the Grids tab.',
                _link('Class Tabs', 'class-tabs'),
            ]),
            _sub('Updating from 3.1', [
                'On the first launch after the update, KazBars takes the '
                'profile you were using as your profile and says which one '
                'in a toast. Your other old profiles stay untouched in '
                'userdata/profiles; File ▸ Import profile… opens any of '
                'them.',
            ]),
            _sub('If the profile file is damaged', [
                'KazBars loads the copy from your last session instead, '
                'keeps the damaged file as profile.damaged.yml, and says so '
                'in a toast.',
            ]),
            _sub('Your data folder', [
                'File ▸ Open data folder opens userdata — the profile, your '
                'settings and your custom buffs.',
            ]),
            _sub('What travels with a profile', [
                'Grids, the Overlay size and font, Stopwatch, Inspect Target, '
                'Cast timer, Console, Onslaught tracker and Damage Numbers '
                'all live inside it — and so do Deeps and the '
                "Ethram-Fal Live Tracker's live settings. So do any Default "
                'Buff Bars or Damage Number Colors '
                "overrides you've set — only the fields you've actually "
                'changed; everything else still defers to the game, and '
                "only that editor's own Apply writes it.",
                'Machine-local instead: your game resolution and the '
                'overhead anchor, both under Game ▸ Game resolution….',
                _link('Deeps', 'deeps'),
                _link('Ethram-Fal Live Tracker', 'ethram-fal'),
            ]),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'player-target',
        'title': 'Player vs Target Grids',
        'body': [
            'A floating grid sits at a spot on screen and tracks one '
            'source, set when you create it.',
            _sub('Player grid', [
                'Tracks buffs and debuffs on your own character.',
            ], GRID_TYPE_COLORS['player']),
            _sub('Target grid', [
                'Tracks buffs and debuffs on your current target (mob, '
                'friendly, or enemy player).',
            ], GRID_TYPE_COLORS['target']),
            'Friendly and Hostile grids float over characters instead.',
            _link('Overhead Grids', 'overhead-grids'),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'overhead-grids',
        'title': 'Overhead Grids',
        'body': [
            'An overhead grid has no spot on screen. It floats over the '
            'head of each character it applies to — one set of icons per '
            'character.',
            _sub('Friendly and Hostile', [
                'Friendly shows over you (tick Over me), your group and '
                'friendly players. Hostile shows over your target and '
                'anyone fighting you or your group.',
                "The game doesn't list who is around you, so a character "
                'gets its grid once something names it: your group, your '
                'target, someone you hit or heal, or whoever casts on a '
                'character already known.',
            ]),
            _sub('Box or band', [
                'Static makes a box — up to 4 rows of 8, 16 slots in all.',
                'Dynamic makes a band: icons centred over the head, Row cap '
                '(3, 5 or 7) to a row, growing upward, up to Max slots '
                '(1–16). Fill reads Centred.',
            ]),
            _sub('Height and Range', [
                "Height — room left for the game's nameplate between the "
                'head and the grid, in px.',
                'Range — hidden past this many metres.',
                'Over me — Friendly only: also float the grid over your own '
                'character.',
            ]),
            'If the icons sit off a head, nudge the overhead anchor and '
            'rebuild.',
            _link('Game Resolution', 'resolution'),
            _link('Applying and Positioning In-Game', 'positioning'),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'class-tabs',
        'title': 'Class Tabs',
        'body': [
            'A row of tabs under the Grids toolbar sorts your grids by '
            'class: All, then the twelve classes in four groups — Guard '
            'Conq DT, PoM ToS BS, Barb Sin Ranger, Demo Necro HoX. Each tab '
            'shows how many grids it holds.',
            _sub('What a tab means', [
                'A tab lists its own grids only. A new grid joins the tab '
                'you add it on.',
                'In game you get the All grids plus the grids of the class '
                "you're playing. The set follows your character's class.",
            ]),
            _sub('Move… and Copy…', [
                "A grid card's Move… menu has Move to and Copy to, each "
                'listing All classes and the twelve classes. Copy leaves the '
                'original and makes a second grid named after it and the '
                'class.',
            ]),
            _sub('Sharing grids', [
                'The Move… menu ends with Export grid…, which saves that '
                'grid to a <grid name>.kazbars-grids.yml file.',
                'File ▸ Import grid…, right under Import profile…, adds the '
                'grids from a grids file to the class tab the Grids tab is '
                'showing, and switches to the Grids tab so you see them. '
                'Pick a grids file in Import profile… and it points you '
                'here instead.',
                'A grid whose name is taken gets _2 added to it on import, '
                'and the toast says so. Custom buffs travel inside the file '
                'and are added to your database.',
            ]),
            'KazBars reopens on the tab you left.',
        ],
    },
    {
        'cat': 'Grids',
        'id': 'grid-card',
        'title': 'The Grid Card',
        'body': [
            'Each grid is a card in the Grids tab: the grid drawn to scale '
            "and a line naming the buffs it holds. The ⚙ cog, just right of "
            "the preview, opens the grid's settings.",
            _sub('The preview', [
                'Icons are drawn at two-thirds of their in-game size. A grid '
                'too big for the card steps down to a smaller scale, and the '
                'title line says so.',
                'A disabled grid draws grey. The preset cards on an empty '
                'Grids tab are drawn the same way.',
                "It is also where you choose the grid's buffs. On a dynamic "
                'grid the whole preview lights as you hover, and one click '
                'picks for all of it; on a static grid, click a slot.',
                _link('Tracked Buffs', 'tracked-buffs'),
            ]),
            _sub('The buffs line', [
                'Under the preview: the buffs the grid holds, ending in '
                '"+ 3 more" when they do not all fit. Hover it for the full '
                'list.',
            ]),
            _sub('The title line', [
                'After the name and type, a muted note gives the mode — '
                'dynamic or static — and, once the preview is drawn '
                'smaller, its scale: "shown at 1:2". The Applied by me '
                'toggle comes right after it.',
                'Move…, Enabled and × sit at the right. To reorder cards, '
                'drag the ☰ handle, or Tab to it and press Alt+↑ / Alt+↓.',
                'Applied by me — the grid shows only effects you cast, with '
                'your own timer, even when other players cast the same '
                'effect on the same character. It greys with the card when '
                'the grid is disabled, and still works.',
            ]),
            _sub('Grid Settings', [
                'The cog opens a window centred on KazBars. Its sections: '
                'Grid and Icons, then Overhead on an overhead grid and '
                'Sorting on a dynamic one.',
                'Every change shows on the preview at once — Size too, '
                'while you drag. Apply (or Enter) saves; Cancel (or Esc) '
                'puts it back. Enter on the Cancel button cancels.',
                "A name that is empty or another grid's blocks Apply, with "
                'a hint under the Name field.',
                'Shrink a static grid and the slots past the new size are '
                'unassigned, with a warning toast. Grow it back and they '
                'return.',
                _link('Grid Display Options', 'display-options'),
            ]),
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
            "How you pick buffs depends on the grid's mode.",
            _sub('Dynamic mode', [
                'A list of buff names the grid watches for. Click the '
                "grid's preview (or Tab to it and press Enter) to pick from "
                'the database. Only listed buffs appear; an empty list shows '
                'nothing.',
            ]),
            _sub('Static mode', [
                "Click a slot's cell in the preview to choose that slot's "
                'buffs. The picker is titled with the slot, like "Slot 3 '
                'Buffs". Empty slots stay empty; if several buffs share a '
                'slot, the most recent wins.',
                "The picker walks the grid's slots, so you can fill a grid "
                'without closing it. Numbered chips under the header show '
                "where you are: the current slot filled in the grid's "
                'colour, assigned slots outlined. Hover one to see what it '
                'holds. Click a chip, press ◀ ▶ beside Cancel, or use '
                'Ctrl+PageUp / Ctrl+PageDown anywhere in the window to move.',
                'Moving saves the slot you leave. Done saves the current '
                "one. Cancel drops only the current slot's unsaved change — "
                'slots you moved past stay saved. Once every slot holds a '
                'buff, the status line adds "All N slots are assigned."',
                'Right-click a slot to clear it. A toast says "click to '
                'undo" for 8 seconds.',
                'From the keyboard: Tab to the preview, arrows move between '
                'slots, Enter opens the picker, Delete clears the slot.',
            ]),
            _sub("A tracked buff your database doesn't have", [
                "An imported profile (or a buff a database update dropped) "
                'can leave a reference your database no longer resolves. It '
                'shows greyed out as "unknown buff" at the bottom of the '
                "list — it rides along, tracking nothing, until the buff "
                'comes back.',
                'Build & Install counts these in its summary: "N unresolved '
                'buffs excluded — a database update can bring them back."',
            ]),
            _sub('A grid with nothing to track', [
                'A dynamic grid with no Tracked Buffs, or a static grid with '
                "nothing in its slots, isn't built. It stays in your profile "
                'and ships once you give it something. Its card says so '
                'under the preview.',
            ]),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'display-options',
        'title': 'Grid Display Options',
        'body': [
            'These settings are per-grid, in Grid Settings — the ⚙ cog on '
            'its card.',
            'Rows and Cols — the shape. A grid holds up to 64 slots on its '
            'own, an overhead grid 16; there is no total across grids.',
            'Size — a slider, 50–200 %, of the Overlay size. It sets the '
            'icon, and the timer and stack text while they are on Auto; the '
            'hint beside it shows the icon in px.',
            'Timer text and Stack text — Auto, the default, sizes them from '
            'Size and shows the result greyed out. Untick Auto to set your '
            'own, 6–72 pt: the grid uses exactly that in game, whatever Size '
            'or the Overlay size say, and large text can spill past the '
            'icon. Tick Auto to go back.',
            'Gap — the space between icons. Negative overlaps them.',
            'Timers — Digits shows the seconds left under each icon, Bar '
            "draws a line inside the icon's bottom edge that shrinks as "
            'time runs out, Off shows none. Y offset and Timer text apply '
            'to digits only, so they grey out for Bar and Off.',
            'A new grid starts with the Gap and Y offset that suit the '
            'Overlay size. Changing the Overlay size later leaves them '
            'as set.',
            'Flash — icons pulse near expiry. Under sets the threshold in '
            'seconds; it greys out while Flash is off.',
            "Applied by me is not here — it is the toggle on the card's "
            'title line.',
            'Where a floating grid sits on screen is decided in-game, not '
            'here.',
            _link('Overlay Size and Font', 'overlay-size'),
            _link('Applying and Positioning In-Game', 'positioning'),
        ],
    },
    {
        'cat': 'Grids',
        'id': 'overlay-size',
        'title': 'Overlay Size and Font',
        'body': [
            'Two dropdowns on the Grids toolbar set the size and the font '
            'of everything KazBars draws in game. Both are saved in the '
            'profile; rebuild to apply.',
            _sub('Overlay', [
                'The base size, 10 to 24 — 11 suits 720p, 13 suits 1080p, '
                '14 suits 1440p, 16 suits 4K. First launch and Reset '
                'profile to defaults… pick the one for your resolution; '
                'an imported profile keeps its own.',
                'Change it and every grid and panel resizes together, each '
                'in proportion.',
            ]),
            _sub('Size sliders', [
                'Each grid, and the Stopwatch, Inspect Target, Cast timer, '
                'Console and Onslaught tracker, has its own Size: a percent '
                'of the Overlay size, 50–200 %. The hint beside it says '
                'what that comes to — icon px for a grid, points of text '
                'for a panel.',
            ]),
            _sub('Font', [
                "Arial, Verdana (the game's own font), GG, or one of nine "
                'open fonts: Roboto, Inter, Noto Sans, Source Sans 3, PT '
                'Sans, Fira Sans, Barlow Semi Condensed, Exo 2, Alegreya '
                'Sans.',
                'Damage Numbers has its own Font.',
            ]),
            _link('Game Resolution', 'resolution'),
        ],
    },
    {
        'cat': 'Buff Database',
        'id': 'database',
        'title': 'The Buff Database',
        'body': [
            'Every effect has numeric buff IDs. The Database tab maps IDs to '
            'names, so grids can pick effects by name.',
            'Use the search bar and category/type filters to find entries.',
            _sub('Adding or editing an entry', [
                'Name — a unique label (e.g. "Cunning Deflection").',
                'ID(s) — numeric buff IDs. One per line, or comma-separated.',
                'Category — groups related entries for browsing.',
                'Type — Buff (grey), Debuff (red), or Misc (golden). Sets the '
                'icon border and grouping.',
            ]),
            "Don't know an effect's ID? The game can tell you.",
            _link('Finding Buff IDs', 'finding-buff-ids'),
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
            ], _DANGER_TEXT),
            _sub('Misc', [
                'Anything separated from Buff/Debuff. Golden border.',
                'The bundled database uses Misc for CC durations and heals-over-time.',
            ], _WARNING),
            _note(
                'Some debuffs spawn a new copy per cast instead of '
                'refreshing. The game API exposes only the latest copy, so '
                'Target grids time the most recent cast.',
                _WARNING),
        ],
    },
    {
        'cat': 'Buff Database',
        'id': 'finding-buff-ids',
        'title': 'Finding Buff IDs',
        'body': [
            "The Console's Buffs tab logs every in-game effect with its "
            'name and buff ID, live. It switches on in Extras ▸ Console….',
            _sub('Turn it on', [
                [('Tick ', None),
                 ('Include the console in builds', _SUCCESS),
                 (', keep Buffs ticked, then ', None),
                 ('Build & Install', _SUCCESS),
                 ('. If the console is not on screen after /reloadui, tick '
                  'its box in the KazBars Preview panel (Shift+Ctrl+Alt).',
                  None)],
                'Everything landing on you or your target is logged. Copy the '
                'ID into the Database tab.',
            ]),
            "Off by default, so finished builds don't carry it. Turn it off "
            'and rebuild to remove it.',
            _link('Console', 'console'),
        ],
    },
    {
        'cat': 'Buff Database',
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
        'cat': 'Building & In-Game',
        'id': 'building',
        'title': 'Building and Installing',
        'body': [
            [('Build & Install', _SUCCESS),
             (' compiles your layout into your game folder. The compiler is '
              'bundled — nothing else to install.', None)],
            [("The first build also registers KazBars with the game — two "
              'marked blocks in its config files, backed up beside them. ', None),
             ('Close the game and the patcher before your first build.', _DANGER_TEXT),
             (' After that, rebuild anytime and /reloadui.', None)],
            'A quiet status line above the extras cards reads "In game: '
            '<profile>" and turns orange when the game no longer matches '
            '— a profile imported or reset, an edit since the last build, '
            'or a changed game resolution or overhead anchor. It never '
            'blocks you; it just '
            'says a rebuild is due.',
            'From here, two things matter: how you launch, and game patches.',
            _link('Launching the Game', 'launching'),
            _link('After a Game Patch', 'game-patch'),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'launching',
        'title': 'Launching the Game',
        'body': [
            'Start the game straight from AgeOfConan.exe or '
            "AgeOfConanDX10.exe. KazBars sets the engine's own "
            'IgnorePatcher.enable flag, so a direct launch skips the patcher '
            'and loads your grids.',
            'After your first build, KazBars offers a desktop shortcut. '
            'Game ▸ Create game desktop shortcut… makes one anytime '
            '(DX10 or DX9).',
            'Launching through the patcher is harmless, just undoing — it '
            'restores stock files, registration included.',
            _link('After a Game Patch', 'game-patch'),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'positioning',
        'title': 'Applying and Positioning In-Game',
        'body': [
            'Apply a rebuild with /reloadui in chat. Positioning happens '
            'in-game, in preview mode.',
            _sub('Preview mode', [
                'Press Shift+Ctrl+Alt in-game to toggle. Each grid shows as a '
                'colored rectangle with its name. Drag things where you want '
                '— the game remembers, across relogs and restarts.',
                'Overhead grids follow their characters, so there is nothing '
                'to drag: preview shows an empty sample of each over your '
                'target.',
            ]),
            _sub('The KazBars Preview panel', [
                'Preview mode also shows a KazBars Preview panel: one '
                'checkbox per floating grid and extra, grouped under Player '
                'Grids, Target Grids and Tools. Click a header to toggle its '
                'whole group. Each box is a persistent master switch — '
                'unchecked stays off until you re-check it.',
                'Its footer repeats the exit keybind, the /reloadui '
                'reminder and the app version. Its text follows the Overlay '
                'size. With many grids it shrinks itself to stay on screen.',
            ]),
            _sub('X/Y in the app', [
                "The X/Y under Position in a floating grid's Grid Settings "
                'only seed a first-ever session. Once you drag in-game, the '
                'dragged spot wins.',
            ]),
        ],
    },
    {
        'cat': 'Building & In-Game',
        'id': 'resolution',
        'title': 'Game Resolution',
        'body': [
            'Game ▸ Game resolution... sets the screen size builds target. '
            'It must match the resolution you play at.',
            'Change it and nothing in your profile moves: positions are '
            'fractions of the screen and sizes a percent of the Overlay '
            'size. On a bigger screen, pick a bigger Overlay size on the '
            'Grids tab. Rebuild to apply.',
            _sub('Overhead anchor', [
                'The same dialog has Right and Up fields: where overhead '
                "grids sit against a character's head. Positive moves them "
                'right and up, negative left and down.',
                "It depends on your game's field of view, so it is kept on "
                'this PC, not in the profile. A change needs a rebuild.',
            ]),
            _link('Overlay Size and Font', 'overlay-size'),
            _link('Overhead Grids', 'overhead-grids'),
        ],
    },
    {
        'cat': 'Live Overlays',
        'id': 'deeps',
        'title': 'Deeps',
        'body': [
            'Always-on-top combat meter reading your combat log. Five rolling '
            'numbers: DPS out, DPS in, HPS out, HPS in, ΔHP in (net health '
            'change). Works only while KazBars is open.',
            _sub('Setup', [
                [('Click ', None),
                 ('⚔ Deeps', _ACCENT),
                 (' at the bottom right, then ', None),
                 ('Start', _SUCCESS),
                 (". Numbers appear once you're in a fight.", None)],
            ]),
            _sub('Positioning', [
                'Drag to position. Lock fixes it in place and passes clicks '
                'through to the game. Layout and visible cells sit under '
                'Overlay Cells.',
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
            'Ethram-Fal raid, read from your combat log. Keep KazBars open '
            'for the pull.',
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
                'Drag to position. ○ locks it (becomes ●) and passes clicks '
                "through to AoC. Unlock from the panel's Lock button.",
            ]),
            _sub('The cycle', [
                'Every ~40s: Viscous Seed debuffs a player, Lotus Fixation '
                'locks another 4s later. Silence the plants, pile the '
                'scorpions, kill after 31s but before the next seed.',
                'Phase 4: two seeds at once, kite the scorpions. Syphon '
                'clouds interrupt the cycle.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'extras-shipping',
        'title': 'How Extras Ship',
        'body': [
            'The Extras menu is one alphabetized list per group, split by a '
            'plain separator — no caption explains why. Every extra applies '
            'one of these two ways.',
            _sub('/reloadui to apply', [
                'Default Buff Bars and Damage Number Colors edit the '
                "game's own files on Apply.",
                'Nothing to build — /reloadui in-game shows the change.',
            ]),
            _sub('Build & Install to apply', [
                [('Cast Timer, Console, Damage Numbers, Inspect Target, '
                  'Onslaught Tracker and Stopwatch are off by default — off '
                  'means zero code in the build. Tick the box, ', None),
                 ('Apply', _SUCCESS),
                 (', then ', None),
                 ('Build & Install', _SUCCESS),
                 ('. Cancel, Escape or the X discard.', None)],
                [('The four cards at the bottom of the Grids tab, just '
                  'above ', None),
                 ('Build & Install', _SUCCESS),
                 (', are two controls: the switch flips whether the '
                  'feature ships, and clicking anywhere else on the card '
                  'opens its dialog.', None)],
                'Console and Stopwatch have no card — open them from the '
                'Extras menu.',
            ]),
            _sub('One size, set once', [
                'The Overlay size on the Grids tab is the base for every '
                'panel. Each dialog has a Size slider — a percent of it, '
                '50–200 % — and the panel scales as one piece, collapsed '
                'bars included.',
                _link('Overlay Size and Font', 'overlay-size'),
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'default-buff-bars',
        'title': 'Default Buff Bars',
        'body': [
            "Extras ▸ Default buff bars… edits the game's own buff bars — "
            'portrait icons, top bar, floating portraits. Your KazBars grids '
            'are untouched.',
            _sub('What you can change', [
                'Icon size, spacing, and column count per bar, plus a friendly / '
                'hostile filter. Toggle a bar off to hide it entirely.',
            ]),
            _sub('Where it writes', [
                'Edits go only to your Customized UI skin; each file is '
                'backed up once first. Set your game folder first.',
            ]),
            'Apply writes immediately; /reloadui shows the result.',
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'damage-number-colors',
        'title': 'Damage Number Colors',
        'body': [
            "Extras ▸ Damage number colors… sets each combat number's color "
            'and direction — hits, crits, spells, combos, heals, mana, '
            "stamina. Your numbers left, your target's right.",
            _sub('Direction', [
                'Each row picks where its number goes: Rising floats '
                'overhead, Dropping lands in the fixed column, Zig-zag joins '
                "the stacked swing. These are the game's own three behaviors.",
                'Two checkboxes move whole groups: Group my resource numbers '
                'drops your mana and stamina losses into the fixed column; '
                'Send incoming numbers to the fixed column does the same for '
                'what hits you. Both just set the dropdowns — tune any row '
                'after.',
            ]),
            _sub('It stands alone', [
                "These are the game's own colors and directions — the Damage "
                'Numbers mod is not needed.',
                'Reset to game default restores stock, per row or whole panel.',
                'Your settings survive mod-off, rebuilds and uninstall. Reset '
                'is the only way back to stock.',
            ]),
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'damage-numbers',
        'title': 'Damage Numbers',
        'body': [
            "Extras ▸ Damage number mod… replaces the game's floating combat "
            'numbers with a leaner rewrite. Headline fix: ranged hits stop '
            'shrinking at distance.',
            _sub('Turn it on', [
                [('Tick ', None),
                 ('Enable the Damage Numbers mod', _SUCCESS),
                 (' in the dialog and set your options.', None)],
                'The stock file is backed up first. Turn the mod off and '
                'rebuild to restore it.',
                _link('How Extras Ship', 'extras-shipping'),
            ]),
            _sub('What you can tune', [
                "Font — Hyborian, the game's own, is the default and leaves "
                'the stock file as it is. Nine heavy display faces are built '
                'into the mod on your next Build & Install. A face that runs '
                'small is drawn larger to read as big as Hyborian; the '
                'dialog shows by how much.',
                'Keep ranged numbers big — holds ranged hit size past ~15 '
                'metres. Melee is never touched.',
                'Shadow, pop-in, and fade speed — with Default and Performance '
                'presets.',
                'Where rising, dropping and zig-zag numbers land on screen. '
                'Which one a number uses is set in Damage Number Colors.',
                'Split signed numbers into Column B — heals, stamina and mana '
                'move to Column B; plain damage stays in A. Dropping numbers '
                'only.',
                'Keep enemy drains overhead — drained enemy mana and stamina '
                'keep floating over them, whatever your own numbers do.',
            ]),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'stopwatch',
        'title': 'Stopwatch',
        'body': [
            'Extras ▸ Stopwatch… adds a count-up Start / Pause / Reset timer '
            'inside the overlay. Works in fullscreen, never steals focus.',
            _sub('Using it in-game', [
                'A draggable panel shows h:mm:ss. − collapses it to the title '
                'bar, which keeps showing the time; click to reopen.',
                'Drag the title bar. The game remembers position and fold — '
                "the dialog's X/Y only seed the first session — and keeps "
                'the spot when the screen resizes.',
                'Size is a slider in the dialog: a percent of the Overlay '
                'size.',
            ]),
            [('Tick ', None),
             ('Include the stopwatch in builds', _SUCCESS),
             (' to ship it with your next build.', None)],
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'inspect',
        'title': 'Inspect Target',
        'body': [
            'Extras ▸ Inspect Target… shows the combat sheet of whatever you '
            "target — stats the game's own inspect window can't reveal. It "
            'appears moments after you target; clears when you do.',
            _sub('What it shows', [
                'The name strip reads Name Class (Level/PvP level). A mob '
                'just reads Name (83).',
                "The rows are yours to pick (below), in the game sheet's "
                'own Rating (Effect%) language, at any target level. A dash: '
                'the target lacks it.',
                'Player targets also get a PvP tab, from a button in the '
                'name strip: PvP combat stats, protections, bonus spell '
                'damage and their K/D record.',
            ]),
            _sub('Stat rows', [
                '112 rows in seven groups: Summary, Vitals, Attributes, '
                'Offensive, Defensive, PvP Stats and PvP Combat.',
                'Default shows the twelve Summary rows — health, armor, '
                'protection, crit, critigation, hate, tenacity, penetration, '
                'heal rating, combat rating, bonus spell damage, ferocity. '
                'Custom list shows the rows you pick.',
                'Add and Remove move rows between Available and Active; '
                'Add All and Clear fill or empty Active. Move up and Move '
                'down order them within their section. '
                'Any change pins the list as a Custom list.',
                'Search matches a name, a group or a stat ID; Group filters '
                'Available. Pick one row and the line under the lists says '
                'what it reads. It also warns when your rows would run '
                'taller than the game screen at this size.',
            ]),
            _sub('The Perks row', [
                "Six boxes mirror the game's perk bar — blue General, red "
                'Archetype, dark Class. Double-slot Class perks paint two '
                'identical icons.',
                'The row reads perk buffs on player targets: active perks '
                "show only while running; a groupmate's perk can appear "
                'too. Hover one to see its name.',
            ]),
            _sub('Positioning and size', [
                'Drag by the name strip; − collapses to just the strip. The '
                "game remembers position and fold — the dialog's X/Y only "
                'seed a first-ever session. Start collapsed loads it folded.',
                'No target? Preview mode (Shift+Ctrl+Alt) shows a '
                'placeholder.',
                'Size is a slider in this dialog: a percent of the Overlay '
                'size. The whole panel scales with it.',
            ]),
            [('Tick ', None),
             ('Include the Inspect Target in builds', _SUCCESS),
             (' to ship it.', None)],
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'cast-timer',
        'title': 'Cast Timer',
        'body': [
            "Extras ▸ Cast timer… shows your and your target's cast time as "
            "floating text over the game's cast bar — no bar of its own.",
            _sub('What you can set', [
                'Player position and Target position — where each timer sits '
                'on screen.',
                'Text — Bold, Size, Color; shared by both timers. Size is a '
                'percent of the Overlay size, and the face is the Overlay '
                'font. The sample shows the result.',
                'Show — Elapsed counts up, Total is the estimated cast '
                'length, Both shows 1.2 / 2.5.',
            ]),
            _sub('Positioning', [
                'Preview mode (Shift+Ctrl+Alt): drag each timer, the game '
                "remembers. The dialog's X/Y only seed the first session.",
            ]),
            _sub('Positions travel with your profile', [
                'Player and Target positions are fractions of your screen, '
                'so they land proportionally at any resolution — and ride '
                'along when you share the profile.',
            ]),
            [('Tick ', None),
             ('Include the cast timer in builds', _SUCCESS),
             (' to ship it. One toggle runs both the Player and Target sides.',
              None)],
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'console',
        'title': 'Console',
        'body': [
            'Extras ▸ Console… adds an in-game panel of tabs that logs what '
            "the game doesn't show you.",
            _sub('Tabs', [
                'Buffs — every buff and debuff on you and your target, with '
                'its buff ID. This is how you find IDs for the Database tab.',
                "Casts — your and your target's casts as they end: "
                'finished, interrupted or lost, and how long they took.',
                'Tick the tabs you want and use ▲ ▼ to order the strip. A '
                "tab you leave out isn't built; with none ticked, neither is "
                'the console.',
            ]),
            _sub('Using it in-game', [
                'Drag it by its title bar; − collapses it to a small bar, '
                'click to reopen. The game remembers spot, fold, open state '
                'and the tab you were on.',
                'Its box in the KazBars Preview panel (Shift+Ctrl+Alt) '
                'switches it off and on.',
                'Size is a slider in the dialog: a percent of the Overlay '
                'size.',
            ]),
            [('Tick ', None),
             ('Include the console in builds', _SUCCESS),
             (' to ship it.', None)],
            _link('How Extras Ship', 'extras-shipping'),
            _link('Finding Buff IDs', 'finding-buff-ids'),
        ],
    },
    {
        'cat': 'Extras',
        'id': 'onslaught',
        'title': 'Onslaught Tracker',
        'body': [
            'Extras ▸ Onslaught tracker… adds an in-game board for the '
            'Onslaught instances, Skull Gate and Kuthchemes. It does '
            'nothing anywhere else.',
            _sub('Five displays', [
                'Board — Mob list: the bosses, skulls and minis in view, '
                "with their health; a guard's bar turns light blue while "
                'its Ancient Ward, a magic-dampening ward it casts on '
                'itself, is up. Wave timer: the wave and the time to the '
                'next spawn, with the elapsed and remaining clocks drawn '
                'large, in bold, bright type. Hylda HP: Valkyrie Hylda, '
                'the ally you defend in Skull Gate, with alerts at 50 % and '
                '25 %.',
                'Alerts — Spawn alerts: a banner when a watched boss, skull '
                "or mini spawns. AoE warnings: a banner when Thugra Khotan's "
                'AoE helpers spawn in Kuthchemes.',
                'Tick the ones you want. Alert time (3–15 s) is how long a '
                'banner stays.',
            ]),
            _sub('Watched mobs', [
                'It always watches 27 mobs from its catalog, and the dialog '
                'lists them by name, one line per group. Include '
                'Kuthchemes camps adds the camp beasts to the board — '
                'listed, never alerted — and a line for them in that list.',
                'Guards in their own group — ticked by default — lists '
                'Gurnakhi Juggernaut (Skull Gate) and Ancient Kuthcheman '
                'Guardian (Kuthchemes) under GUARDS at the very bottom of '
                'the board, below CAMPS, and tags their spawn alert GUARD '
                'instead of SKULL. Untick it and they stay skulls. It greys '
                'out unless Mob list or Spawn alerts is on.',
                'Your own names — up to 20, watched as minis. A name has to '
                "match the game's exactly, capitals included; the dialog "
                'says why it refuses one as you type. × deletes a name; '
                "Cancel drops any change you haven't applied.",
                'These matter when Mob list or Spawn alerts is on.',
            ]),
            _sub('Camp names', [
                "A skull standing at one of its map's camps shows the "
                "camp's name where its distance would be: "
                '"Temple  72%". Out of view it reads "last Temple - 12 s '
                'ago". Always on, no setting.',
                'Skull Gate camps: Hub, Cave, WCave, Tower, Bridge, Altar. '
                'Kuthchemes: Respad, South West, South East, Temple, East, '
                'South, West, North.',
            ]),
            _sub('Using it in-game', [
                'Place the board and the alerts in preview mode '
                '(Shift+Ctrl+Alt): drag each where you want it, the game '
                'remembers.',
                'Size is a slider in the dialog: a percent of the Overlay '
                'size. The alerts draw larger than the board.',
            ]),
            [('Tick ', None),
             ('Include the onslaught tracker in builds', _SUCCESS),
             (' to ship it.', None)],
            _link('How Extras Ship', 'extras-shipping'),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'game-patch',
        'title': 'After a Game Patch',
        'body': [
            'A game patch restores stock files, registration included. The '
            'symptom: you launch, the grids are gone.',
            'Run the official patcher once, then Game ▸ Repair game install. '
            'Repair re-registers KazBars, restores saved positions, and puts '
            'Damage Numbers back.',
            _sub('You usually hear about it first', [
                'KazBars checks the registration at every start. Anything '
                'missing raises a warning — click it to repair.',
                'Close the game and the patcher before repairing — a running '
                'patcher undoes the fix on exit.',
            ]),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'updates',
        'title': 'Updates',
        'body': [
            'One check covers KazBars itself and the buff database. It runs '
            'at every launch; Updates ▸ Check for updates now — or Check for '
            'updates in the About window — runs it on demand. KazBars comes '
            'first; the buff database is only checked once the app is '
            'current.',
            _sub('App updates', [
                'A newer release shows "KazBars vX is available — click to '
                'install". Click it: the download runs in the background, '
                'progress in the same notice, which then reads "downloaded — '
                'click to restart and install".',
                'The second click closes KazBars, installs the new version '
                'over the existing folder, and reopens it. The usual '
                'unsaved-changes prompts still apply — cancel, and the '
                'downloaded update waits. Next launch: "KazBars updated to '
                'vX — click for what\'s new".',
                'Nothing you own moves. Your profile, settings, custom buffs and '
                'buff-database updates all stay — no first-run setup again, '
                'no old folder to delete, no SmartScreen prompt on the '
                'relaunch.',
                "If the download fails or doesn't verify, nothing changes. "
                'The notice says what failed — click it to open the release '
                'page.',
            ]),
            _sub('Buff-database updates', [
                [('The stock buff catalog refreshes over the internet once '
                  'KazBars itself is current. ', None),
                 ('Automatically update the buff database', _SUCCESS),
                 (' is on by default; Check for updates now asks '
                  'immediately.', None)],
                'Updates never touch your own entries. Your edits sit in a '
                'layer above the stock catalog and always win.',
                'Revert last buff-database update undoes the most recent one '
                'only — not a history.',
            ]),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'backup',
        'title': 'Backup and Restore',
        'body': [
            'Game ▸ Backup & restore game settings... writes one portable '
            '.zip: your full Age of Conan config plus your KazBars profile '
            'and settings. Your recovery path after a reformat.',
            _sub('Restoring', [
                'Restore snapshots your current settings first, so a bad '
                'restore is reversible. Close the game before either.',
                'A backup made by 3.1 brings back its profiles, and KazBars '
                'adopts the one that was active.',
            ]),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'uninstall',
        'title': 'Removing KazBars',
        'body': [
            'Game ▸ Uninstall from game client… removes everything KazBars '
            'put in the game folder. Every changed game file is restored '
            'byte-for-byte; Damage Numbers reverts to stock.',
            'Two things stay on purpose: your damage-number colors, and '
            'everything on this PC — your profile, database entries, '
            'settings.',
            _link('Damage Number Colors', 'damage-number-colors'),
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
        elif kind == 'link':
            # The label is the target's title — searching for it should still
            # land on the section that links there, not just the target.
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


def _link_targets(value, out):
    """Collect every `_link` target id in a block tree into `out`."""
    if isinstance(value, list):
        for part in value:
            _link_targets(part, out)
    elif isinstance(value, tuple):
        if value[0] == 'link':
            out.append(value[2])
        elif value[0] == 'sub':
            for item in value[2]:
                _link_targets(item, out)


def _validate_link_targets():
    """Fail on import if any link points at an id no section carries.

    Cross-references are only worth adding if they can't rot: a renamed id, or a
    typo, breaks here rather than dead-ending a reader mid-guide. Any test that
    imports this module is the gate.
    """
    known = {s['id'] for s in SECTIONS}
    for section in SECTIONS:
        targets = []
        for block in section['body']:
            _link_targets(block, targets)
        for target in targets:
            if target not in known:
                raise ValueError(
                    f"instructions_panel: section {section['id']!r} links to "
                    f"{target!r}, which is not a section id."
                )


_SECTION_BY_ID = {s['id']: s for s in SECTIONS}
_validate_link_targets()


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
        self._link_font_hover = tkfont.Font(font=FONT_BODY, underline=True)
        self._frame_bg = ttk.Style().lookup('TFrame', 'background') or TK_COLORS['bg']
        self._haystacks = {s['id']: _haystack(s) for s in SECTIONS}
        self._section_by_id = _SECTION_BY_ID
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
        elif isinstance(block, tuple) and block[0] == 'link':
            self._link_row(parent, block[1], block[2], padx=(PAD_TAB, PAD_TAB))
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
            elif isinstance(item, tuple) and item[0] == 'link':
                self._link_row(frame, item[1], item[2], padx=(PAD_INNER, 0))
            else:
                self._paragraph(frame, item, _SUBSECTION_MARGIN, padx=(PAD_INNER, 0))

    def _link_row(self, parent, label, target_id, padx=(0, 0)):
        """A click-through to another section — same selection path as the nav,
        so the nav highlight and scroll reset come along for free."""
        lbl = tk.Label(parent, text=f'→ {label}', font=FONT_BODY, fg=_ACCENT,
                       bg=self._frame_bg, anchor='w', cursor='hand2')
        lbl.pack(fill='x', padx=padx, pady=(0, PAD_XS))
        lbl.bind('<Button-1>', lambda _e: self._select(target_id))
        lbl.bind('<Enter>', lambda _e: lbl.configure(font=self._link_font_hover))
        lbl.bind('<Leave>', lambda _e: lbl.configure(font=FONT_BODY))

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

        # BOTH sizes must be explicit — the Tk default is 378x265, and fill='x'
        # stretches the rendered canvas without shrinking what it asks for.
        canvas = tk.Canvas(parent, bg=self._frame_bg, highlightthickness=0, borderwidth=0,
                           width=1, height=line_h, takefocus=0)
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
