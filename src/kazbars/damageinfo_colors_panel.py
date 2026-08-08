"""KazBars — Damage Number Colors panel.

A per-source editor for AoC's floating combat numbers, opened from the Extras menu
("Damage number colors…"). Every flytext source (see
:data:`damageinfo_settings.PAIRED_GROUPS` / ``SHARED_SOURCES`` — ~35 types) gets a row with
its **color** and its **direction** (rising above the head / dropping into the fixed column
/ joining the zig-zag stack), laid out in two columns: **self** (numbers on you) on the
left, **other** (numbers on your target) on the right, with the shared resource/XP/murder
types in a full-width card below. Two macro checkboxes flip a whole group of directions at
once; they stage the same per-row controls, so the user can fine-tune afterwards.

This mirrors the Default Buff Bars editor: a modal Apply/Cancel dialog that edits the
skin's ``TextColors.xml`` **directly** on Apply — no build, no master-enable gate. Writes
always land in ``Customized/TextColors.xml`` (created from the stock ``Default/`` copy when
absent — the game patcher resets ``Default/`` on update, so edits there don't stick). Only
the ``color``/``direction`` attributes of each edited source change; every other byte is
preserved. "Reset to game default" reads the stock color *and* direction from ``Default/``
and stages them for the next Apply. Requires a game folder (the opener warns and bails
without one).
"""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ttkbootstrap.dialogs import Messagebox

from . import buff_xml
from . import damageinfo_settings as dis
from .settings_manager import safe_write_text
from .ui_components import create_scrollable_frame
from .ui_forms import ColorSwatch, create_card
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    FONT_BODY,
    MODULE_COLORS,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_tk_style import apply_dark_titlebar
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

logger = logging.getLogger(__name__)

_W = 640
_H = 700

# Skin-relative TextColors.xml — this panel is the only writer of the file.
_TEXTCOLORS_RELPATH = "TextColors.xml"
_FALLBACK_COLOR = "FFFFFF"  # swatch shown when a source has no color in the file

# The direction control's readable values. The names match the Damage Numbers panel's
# position cards (Rising / Dropping / Zig-zag numbers), so the two surfaces describe the
# same three behaviours with the same words.
_DIRECTIONS: tuple[tuple[str, int], ...] = (
    ('Rising', 1),
    ('Dropping', -1),
    ('Zig-zag', 0),
)
_DIRECTION_NAMES = [name for name, _ in _DIRECTIONS]
_LABEL_TO_DIRECTION = dict(_DIRECTIONS)
_DIRECTION_TO_LABEL = {value: name for name, value in _DIRECTIONS}
_FALLBACK_DIRECTION = 1  # AoC's own default for a type whose element omits the attribute

# Group macros: one checkbox flips a whole set of rows to the fixed column (and back).
# Both sets are the same ones the Damage Numbers mod used to flip at Build & Install.
_MACROS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ('Group my resource numbers', buff_xml.RESOURCE_LOSS_TYPES,
     "Sets your own mana and stamina losses to Dropping, so they land in the fixed column "
     "with your gains and every resource change reads in one place. Untick to send them "
     "back to Rising."),
    ('Send incoming numbers to the fixed column', buff_xml.INCOMING_DAMAGE_TYPES,
     "Sets everything that lands on you — hits, spells, combos, heals — to Dropping, so it "
     "stacks in one column instead of flying off your head. Untick to send it back to "
     "Rising."),
)


def _read_xml(path) -> str | None:
    """Text of one TextColors.xml, or None if it's missing/unreadable."""
    if path is None:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Could not read %s: %s", path, e)
        return None


def _read_colors(path) -> dict[str, str]:
    """Map source name → bare ``RRGGBB`` from one TextColors.xml, or ``{}`` if unreadable."""
    text = _read_xml(path)
    if text is None:
        return {}
    out: dict[str, str] = {}
    for name in dis.ALL_SOURCE_NAMES:
        color = buff_xml.read_source_color(text, name)
        if color:
            out[name] = color
    return out


def _read_directions(path) -> dict[str, int]:
    """Map source name → direction (1 / -1 / 0) from one TextColors.xml, or ``{}``.

    Sources whose element omits the attribute — or spells a value the control can't show —
    are left out; the panel falls back to the stock file, then to 1.
    """
    text = _read_xml(path)
    if text is None:
        return {}
    out: dict[str, int] = {}
    for name in dis.ALL_SOURCE_NAMES:
        raw = buff_xml.read_source_direction(text, name)
        if raw is not None and int(raw) in _DIRECTION_TO_LABEL:
            out[name] = int(raw)
    return out


def apply_colors(game_path, colors: dict[str, str],
                 directions: dict[str, int] | None = None) -> Path | None:
    """Write ``colors`` (``{source_name: RRGGBB}``) and ``directions``
    (``{source_name: 1|-1|0}``, ``None`` = leave every direction alone) into the skin's
    ``TextColors.xml``.

    Pure file I/O (no Tk) so the write path is unit-testable. Edits go to
    ``Customized/TextColors.xml``, created from the stock ``Default/`` copy when absent —
    the game patcher resets ``Default/`` on update, so edits there don't stick. Both
    writers are element-scoped + skip-when-equal, so only the named attributes change and
    every other byte is preserved; a source left out of a dict keeps whatever the file
    already says. A pre-existing skin file gets a one-time ``.kazbars.bak`` first. Returns
    the written path, or ``None`` if no TextColors.xml exists in the game folder at all.
    Raises ``OSError`` on a failed read/write.
    """
    _default, customized, source = buff_xml._resolve_paths(game_path, _TEXTCOLORS_RELPATH)
    if source is None:
        return None
    text = source.read_text(encoding="utf-8")
    for name, hex6 in colors.items():
        text, _ = buff_xml.set_source_color(text, name, hex6)
    for name, direction in (directions or {}).items():
        text, _ = buff_xml.set_source_direction(text, name, direction)

    customized.parent.mkdir(parents=True, exist_ok=True)
    buff_xml._backup_once(customized)  # one-time backup of a pre-existing skin file
    safe_write_text(customized, text)
    return customized


class DamageNumberColorsPanel(tk.Toplevel):
    """Per-source flytext color + direction editor (modal Toplevel, mirrors BuffDisplayDialog)."""

    def __init__(self, parent: tk.Misc, game_path: str) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title("Damage Number Colors")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.game_path = game_path
        # source = the file the game reads (Customized if present, else Default); we always
        # WRITE to Customized. `_current*` seeds the rows + is the dirty baseline;
        # `_default*` is the stock Default value each "reset" reverts to.
        self._default_path, self._customized_path, self._source_path = buff_xml._resolve_paths(
            game_path, _TEXTCOLORS_RELPATH
        )
        self._current = _read_colors(self._source_path)
        self._defaults = _read_colors(self._default_path)
        self._current_dirs = _read_directions(self._source_path)
        self._default_dirs = _read_directions(self._default_path)

        self._swatches: dict[str, ColorSwatch] = {}
        self._dir_vars: dict[str, tk.StringVar] = {}
        self._macro_vars: list[tuple[tk.BooleanVar, tuple[str, ...]]] = []
        self._picks: dict[str, str] = {}
        self._dir_picks: dict[str, int] = {}
        self._baseline: dict[str, str] = {}
        self._dir_baseline: dict[str, int] = {}
        self._apply_btn: ttk.Button | None = None
        self._apply_enabled: bool | None = None
        self._focus_target: ttk.Checkbutton | None = None  # first macro (initial focus)

        self._build_ui()
        self._baseline = dict(self._picks)
        self._dir_baseline = dict(self._dir_picks)
        self._refresh_macros()
        self._refresh_apply_state()

        restore_window_position(self, "damage_number_colors", _W, _H, parent, resizable=False)
        bind_window_position_save(self, "damage_number_colors", save_size=False)
        self.deiconify()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._on_apply())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # Re-assert the dark titlebar on the panel's own map — the global one-shot patch
        # can miss a deep/scrollable Toplevel like this one. Same fix as buff_display_editor.
        self.bind("<Map>", self._reassert_dark_titlebar, add="+")
        if self._focus_target is not None:
            self.after(0, self._focus_target.focus_set)

    def _reassert_dark_titlebar(self, event) -> None:
        if event.widget is self:
            apply_dark_titlebar(self)

    # ------------------------------------------------------------------ #
    # UI construction                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        create_dialog_header(self, "Damage Number Colors", MODULE_COLORS['damage_numbers'], width=_W)
        create_tip_bar(
            self,
            "Set each number's color and direction, then Apply and type /reloadui in-game.",
        )

        # Footer first so it reserves height before the scrollable body claims the rest.
        footer = ttk.Frame(self, padding=(PAD_TAB, PAD_XS))
        footer.pack(fill="x", side="bottom")
        self._apply_btn = ttk.Button(footer, text="Apply", width=BTN_DIALOG, bootstyle="success",
                                     command=self._on_apply)
        self._apply_btn.pack(side="right")
        ttk.Button(footer, text="Cancel", width=BTN_DIALOG, bootstyle="secondary",
                   command=self.destroy).pack(side="right", padx=(0, PAD_SMALL))
        ttk.Button(footer, text="Reset all to game default", bootstyle="link",
                   command=self._reset_all).pack(side="left")

        if self._source_path is None:
            ttk.Label(
                self, text="TextColors.xml isn't in your game folder. Verify your install.",
                font=FONT_BODY, foreground=THEME_COLORS['muted'],
                wraplength=_W - 2 * PAD_TAB, justify="left",
            ).pack(fill="x", padx=PAD_TAB, pady=PAD_ROW)
            return

        outer, inner, _canvas = create_scrollable_frame(self)
        outer.pack(fill="both", expand=True)
        body = ttk.Frame(inner, padding=(PAD_TAB, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")

        self._build_macros(body)

        ttk.Label(body, text="Self — on you", font=FONT_BODY,
                  foreground=THEME_COLORS['accent']).grid(row=1, column=0, sticky="w", pady=(0, PAD_XS))
        ttk.Label(body, text="Other — on your target", font=FONT_BODY,
                  foreground=THEME_COLORS['accent']).grid(row=1, column=1, sticky="w", pady=(0, PAD_XS))

        r = 2
        for title, self_rows, other_rows in dis.PAIRED_GROUPS:
            self._build_group_card(body, title, self_rows, row=r, column=0)
            self._build_group_card(body, title, other_rows, row=r, column=1)
            r += 1
        shared = create_card(body, "Resources & misc")
        shared.grid(row=r, column=0, columnspan=2, sticky="nsew", pady=(0, PAD_ROW))
        for name, label in dis.SHARED_SOURCES:
            self._build_source_row(shared, name, label)

    def _build_macros(self, parent) -> None:
        """The two group macros — shortcuts that stage a whole set of per-row directions."""
        card = create_card(parent, "Number directions")
        card.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, PAD_ROW))
        for label, names, tip in _MACROS:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(card, text=label, variable=var,
                                 command=lambda n=names, v=var: self._on_macro(n, v))
            cb.pack(anchor="w", pady=PAD_XS)
            add_tooltip(cb, tip)
            self._macro_vars.append((var, names))
            if self._focus_target is None:
                self._focus_target = cb

    def _build_group_card(self, parent, title, rows, *, row, column) -> None:
        pad = (0, PAD_XS) if column == 0 else (PAD_XS, 0)
        card = create_card(parent, title)
        card.grid(row=row, column=column, sticky="nsew", padx=pad, pady=(0, PAD_ROW))
        for name, label in rows:
            self._build_source_row(card, name, label)

    def _build_source_row(self, card, name, label) -> None:
        """One source: label · direction · reset · swatch (packed right-to-left)."""
        row = ttk.Frame(card)
        row.pack(fill="x", pady=PAD_XS)
        ttk.Label(row, text=label, font=FONT_BODY,
                  foreground=THEME_COLORS['body']).pack(side="left")

        current = self._current.get(name) or _FALLBACK_COLOR
        self._picks[name] = current
        swatch = ColorSwatch(row, initial_color=f"#{current}",
                             on_change=lambda hex_, n=name: self._on_color(n, hex_))
        swatch.pack(side="right")
        self._swatches[name] = swatch

        reset = ttk.Button(row, text="↺", width=3, bootstyle="link",
                           command=lambda n=name: self._reset_one(n))
        reset.pack(side="right", padx=(0, PAD_XS))
        add_tooltip(reset, "Reset this source's color and direction to the game default")

        # Seed from the live file, then the stock file, then AoC's own default.
        direction = self._current_dirs.get(
            name, self._default_dirs.get(name, _FALLBACK_DIRECTION))
        self._dir_picks[name] = direction
        var = tk.StringVar(value=_DIRECTION_TO_LABEL[direction])
        self._dir_vars[name] = var
        combo = ttk.Combobox(row, textvariable=var, values=_DIRECTION_NAMES,
                             width=9, state="readonly")
        combo.pack(side="right", padx=(0, PAD_XS))
        combo.bind("<<ComboboxSelected>>", lambda e, n=name: self._on_direction(n))

    # ------------------------------------------------------------------ #
    # Change handlers                                                    #
    # ------------------------------------------------------------------ #

    def _on_color(self, name: str, hex_str: str) -> None:
        self._picks[name] = dis.normalize_color(hex_str) or _FALLBACK_COLOR
        self._refresh_apply_state()

    def _on_direction(self, name: str) -> None:
        self._dir_picks[name] = _LABEL_TO_DIRECTION[self._dir_vars[name].get()]
        self._refresh_macros()
        self._refresh_apply_state()

    def _on_macro(self, names: tuple[str, ...], var: tk.BooleanVar) -> None:
        """Flip a whole group to the fixed column (checked) or back above the head."""
        target = -1 if var.get() else 1
        for name in names:
            self._set_direction(name, target)
        self._refresh_apply_state()

    def _set_direction(self, name: str, value: int) -> None:
        """Stage one row's direction and move its visible control with it."""
        self._dir_picks[name] = value
        self._dir_vars[name].set(_DIRECTION_TO_LABEL[value])

    def _restore_stock(self, name: str) -> None:
        """Stage the stock color + direction from the Default/ file for one source."""
        base = self._defaults.get(name) or _FALLBACK_COLOR
        self._picks[name] = base
        self._swatches[name].set_color(f"#{base}")
        self._set_direction(name, self._default_dirs.get(name, _FALLBACK_DIRECTION))

    def _reset_one(self, name: str) -> None:
        self._restore_stock(name)
        self._refresh_macros()
        self._refresh_apply_state()

    def _reset_all(self) -> None:
        for name in self._swatches:
            self._restore_stock(name)
        self._refresh_macros()
        self._refresh_apply_state()

    def _refresh_macros(self) -> None:
        """Derive each macro checkbox from its rows — a hand-tweaked mixed group reads off."""
        for var, names in self._macro_vars:
            var.set(all(self._dir_picks.get(n) == -1 for n in names))

    def _refresh_apply_state(self) -> None:
        dirty = self._picks != self._baseline or self._dir_picks != self._dir_baseline
        if self._apply_btn is None or dirty == self._apply_enabled:
            return
        self._apply_enabled = dirty
        self._apply_btn.configure(state="normal" if dirty else "disabled")

    # ------------------------------------------------------------------ #
    # Apply                                                              #
    # ------------------------------------------------------------------ #

    def _on_apply(self) -> None:
        if self._source_path is None:
            return
        # Colors are safe to re-write wholesale (skip-when-equal, never injected), but a
        # direction write *injects* the attribute when the source omits it — so only the
        # rows the user actually moved are sent, keeping the file's diff to the real edit.
        directions = {n: v for n, v in self._dir_picks.items() if v != self._dir_baseline.get(n)}
        if self._picks == self._baseline and not directions:
            return
        try:
            apply_colors(self.game_path, self._picks, directions)
        except OSError as e:
            logger.warning("Damage Number Colors apply failed: %s", e)
            app_toast(
                self,
                "Couldn't write TextColors.xml. Check folder permissions and disk space.",
                "danger", duration=10, key="textcolors_apply_failed",
            )
            return
        # Customized is now the live file — re-baseline so Apply disables until the next edit.
        self._source_path = self._customized_path
        self._current = dict(self._picks)
        self._current_dirs = dict(self._dir_picks)
        self._baseline = dict(self._picks)
        self._dir_baseline = dict(self._dir_picks)
        self._refresh_apply_state()
        app_toast(self, "Saved. Type /reloadui in-game to see it.", "success")


def open_damage_number_colors_panel(app: tk.Misc) -> DamageNumberColorsPanel | None:
    """Open the Damage Number Colors editor (modal). Validates the game folder first."""
    game_path = getattr(app, "game_path", None)
    if not game_path or not Path(game_path).is_dir():
        Messagebox.show_warning(
            "No game folder set. Configure one in the bottom bar first.",
            title="No Game Folder",
        )
        return None
    return DamageNumberColorsPanel(app, game_path)
