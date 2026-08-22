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
_DANGER = THEME_COLORS['danger']
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
                'Click Tracked Buffs... and pick from the database. Only '
                'selected buffs appear in the grid.',
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
                [('Grids, Damage Numbers, the Stopwatch, the Inspect Panel and '
                  'the Cast Timer are compiled in by ', None),
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
        'title': 'Profiles',
        'body': [
            'A profile is a saved set of grids. The File menu manages them: '
            'New, Open…, Save, Save as…, Manage profiles….',
            'Load default profile loads the starter layout — the one from '
            'first launch.',
            _sub('Which profile opens on launch', [
                'KazBars reopens the profile you last had loaded. The ★ '
                'default is different: first launch and Load default profile '
                'load that one.',
            ]),
            _sub('Sharing a profile', [
                'Export to clipboard (in Manage profiles…) turns a profile '
                'into one long string. Paste it anywhere — Discord, forum, '
                'text file. Import from string… reads one back.',
                'Custom buffs travel inside the string. The importer needs '
                'nothing from your database.',
                'Screen positions do not travel; they belong to this PC.',
                _link('Cast Timer', 'cast-timer'),
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
            "How you pick buffs depends on the grid's mode.",
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
            'Where a grid sits on screen is decided in-game, not here.',
            _link('Applying and Positioning In-Game', 'positioning'),
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
            ], _DANGER),
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
            'The buff-discovery console logs every in-game effect with its '
            'name and buff ID, live. It switches on in Extras ▸ Inspect '
            'panel….',
            _sub('Turn it on', [
                [('Tick ', None),
                 ('Include the buff-discovery console in builds', _SUCCESS),
                 (', then ', None),
                 ('Build & Install', _SUCCESS),
                 ('. Preview mode (Shift+Ctrl+Alt) shows the console.', None)],
                'Everything landing on you or your target is logged. Copy the '
                'ID into the Database tab.',
            ]),
            'Drag it by its title bar; − collapses it to a small bar, click '
            'to reopen. The game remembers spot, fold, and open state.',
            'Its text uses the size all four in-game panels share, set in '
            'the same dialog.',
            "Off by default, so finished builds don't carry it. Turn it off "
            'and rebuild to remove it.',
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
             ('Close the game and the patcher before your first build.', _DANGER),
             (' After that, rebuild anytime and /reloadui.', None)],
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
                'colored rectangle with live X/Y. Drag things where you want '
                '— the game remembers, across relogs and restarts.',
            ]),
            _sub('The KazBars Preview panel', [
                'Preview mode also shows a KazBars Preview panel: one '
                'checkbox per grid and extra, grouped under Player Grids, '
                'Target Grids and Tools. Click a header to toggle its whole '
                'group. Each box is a persistent master switch — unchecked '
                'stays off until you re-check it.',
                'Its footer repeats the exit keybind, the /reloadui '
                'reminder and the app version. Its text uses the size all '
                'four in-game panels share (Extras ▸ Inspect panel…). With '
                'many grids it shrinks itself to stay on screen.',
            ]),
            _sub('X/Y in the app', [
                'The Grids-tab X/Y only seed a first-ever session. Once you '
                'drag in-game, the dragged spot wins.',
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
            'Change it and loaded grids re-anchor — 1920×1080 scales to '
            '2560×1440 by itself. Rebuild to apply.',
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
            'The Extras menu holds two kinds of add-on — its own captions '
            'split them. Every extra applies one of these two ways.',
            _sub('Build & Install to apply', [
                [('Damage Numbers, Stopwatch, Inspect Panel and Cast Timer '
                  'are off by default — off means zero code in the build. '
                  'Tick the box, ', None),
                 ('Apply', _SUCCESS),
                 (', then ', None),
                 ('Build & Install', _SUCCESS),
                 ('. Cancel, Escape or the X discard.', None)],
                'The toggle cards above the grid list flip the same switches. '
                'Configuring stays in the dialogs.',
            ]),
            _sub('/reloadui to apply', [
                'Default Buff Bars and Damage Number Colors edit the '
                "game's own files on Apply.",
                'Nothing to build — /reloadui in-game shows the change.',
            ]),
            _sub('One text size, four panels', [
                'Stopwatch, inspect panel, buff console and control panel '
                'share one text size (8–48), baked at build time. Each '
                'panel scales as one piece, collapsed bars included.',
                'Set it in Extras ▸ Inspect panel…, under Text size. It '
                'lives there because the console and control panel have no '
                'dialog of their own.',
                [('To size the stopwatch or inspect panel differently, '
                  'untick ', None),
                 ('Use the shared size for this panel', _SUCCESS),
                 (' in its own dialog.', None)],
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
                'Drag the title bar; live coordinates show. The game '
                "remembers position and fold — the dialog's X/Y only seed "
                'the first session.',
                'Text size is the one all four in-game panels share — the '
                'dialog can override it for the stopwatch alone.',
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
        'title': 'Inspect Panel',
        'body': [
            'Extras ▸ Inspect panel… shows the combat sheet of whatever you '
            "target — stats the game's own inspect window can't reveal. It "
            'appears moments after you target; clears when you do.',
            _sub('What it shows', [
                'The name strip reads Name Class (Level/PvP level). A mob '
                'just reads Name (83).',
                'Health, armor, protections, crit and critigation, heal '
                'rating, spell damage, combat and weapon damage, tenacity, '
                "ferocity — in the game sheet's own Rating (Effect%) "
                'language. A dash: the target lacks it. Below level 80: raw '
                'ratings only.',
                [('Player targets add a PvP block. Untick ', None),
                 ('Show the PvP section', _SUCCESS),
                 (' to drop it from the build.', None)],
            ]),
            _sub('The Perks row', [
                "Six boxes mirror the game's perk bar — blue General, red "
                'Archetype, dark Class. Double-slot Class perks paint two '
                'identical icons.',
                [('The row reads perk buffs: active perks show only while '
                  "running; a groupmate's perk can appear too. Untick ", None),
                 ('Track slotted perks', _SUCCESS),
                 (' to drop the row.', None)],
            ]),
            _sub('Positioning and text size', [
                'Drag by the name strip; − collapses to just the strip. The '
                'game remembers position and fold.',
                'No target? Preview mode (Shift+Ctrl+Alt) shows a '
                'placeholder.',
                'This dialog sets the text size all four in-game panels '
                'share — or the inspect panel alone.',
            ]),
            [('Tick ', None),
             ('Include the inspect panel in builds', _SUCCESS),
             (' to ship it. The same dialog holds the buff-discovery console.',
              None)],
            _link('How Extras Ship', 'extras-shipping'),
            _link('Finding Buff IDs', 'finding-buff-ids'),
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
                'Text — Bold, Font size (8–48), Color; shared by both timers. '
                'The sample shows the result.',
                'Show — Elapsed counts up, Total is the estimated cast '
                'length, Both shows 1.2 / 2.5.',
            ]),
            _sub('Positioning', [
                'Preview mode (Shift+Ctrl+Alt): drag each timer, the game '
                "remembers. The dialog's X/Y only seed the first session.",
            ]),
            _sub('Saved on this PC, not in your profile', [
                'Settings live with your app preferences, like the stopwatch '
                'and inspect panel. Switching profiles leaves the timer '
                "alone; shared profiles don't carry positions.",
            ]),
            [('Tick ', None),
             ('Include the cast timer in builds', _SUCCESS),
             (' to ship it. One toggle runs both the Player and Target sides.',
              None)],
            _link('How Extras Ship', 'extras-shipping'),
            _note(
                'Had a cast timer before this version? Set it once more in '
                'the dialog — old profile values are no longer read.',
                _WARNING),
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
            'The Updates menu covers two things: the buff database, and '
            'KazBars itself.',
            _sub('Buff-database updates', [
                [('The stock buff catalog refreshes over the internet. ', None),
                 ('Automatically update the buff database', _SUCCESS),
                 (' is on by default; Check for buff-database updates now '
                  'asks immediately.', None)],
                'Updates never touch your own entries. Your edits sit in a '
                'layer above the stock catalog and always win.',
                'Revert last buff-database update undoes the most recent one '
                'only — not a history.',
            ]),
            _sub('App updates', [
                'Check for app updates now asks GitHub for a newer release. '
                'The notice opens its download page.',
                'KazBars never updates itself — you download and replace '
                'your copy.',
            ]),
        ],
    },
    {
        'cat': 'Maintenance',
        'id': 'backup',
        'title': 'Backup and Restore',
        'body': [
            'Game ▸ Backup & restore game settings... writes one portable '
            '.zip: your full Age of Conan config plus KazBars profiles and '
            'settings. Your recovery path after a reformat.',
            _sub('Restoring', [
                'Restore snapshots your current settings first, so a bad '
                'restore is reversible. Close the game before either.',
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
            'everything on this PC — profiles, database entries, settings.',
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
