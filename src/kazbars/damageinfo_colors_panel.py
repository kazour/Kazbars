"""KazBars — Damage Number Colors panel.

A per-source color editor for AoC's floating combat numbers, opened from the Extras menu
("Damage number colors…"). Every flytext source (see
:data:`damageinfo_settings.PAIRED_GROUPS` / ``SHARED_SOURCES`` — ~35 types) gets its own
swatch, laid out in two columns: **self** (numbers on you) on the left, **other** (numbers
on your target) on the right, with the shared resource/XP/murder types in a full-width
card below.

This mirrors the Default Buff Bars editor: a modal Apply/Cancel dialog that edits the
skin's ``TextColors.xml`` **directly** on Apply — no build, no master-enable gate. Writes
always land in ``Customized/TextColors.xml`` (created from the stock ``Default/`` copy when
absent — the game patcher resets ``Default/`` on update, so edits there don't stick). Only
the ``color`` attribute of each edited source changes; every other byte is preserved.
"Reset to game default" reads the stock color from ``Default/`` and stages it for the next
Apply. Requires a game folder (the opener warns and bails without one).
"""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ttkbootstrap.dialogs import Messagebox

from . import buff_xml
from . import damageinfo_settings as dis
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

_W = 600
_H = 660

# Skin-relative TextColors.xml (kept in step with build_executor.TEXTCOLORS_RELPATH).
_TEXTCOLORS_RELPATH = "TextColors.xml"
_FALLBACK_COLOR = "FFFFFF"  # swatch shown when a source has no color in the file


def _read_colors(path) -> dict[str, str]:
    """Map source name → bare ``RRGGBB`` from one TextColors.xml, or ``{}`` if unreadable."""
    if path is None:
        return {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Could not read %s: %s", path, e)
        return {}
    out: dict[str, str] = {}
    for name in dis.ALL_SOURCE_NAMES:
        color = buff_xml.read_source_color(text, name)
        if color:
            out[name] = color
    return out


def apply_colors(game_path, colors: dict[str, str]) -> Path | None:
    """Write ``colors`` (``{source_name: RRGGBB}``) into the skin's ``TextColors.xml``.

    Pure file I/O (no Tk) so the write path is unit-testable. Edits go to
    ``Customized/TextColors.xml``, created from the stock ``Default/`` copy when absent —
    the game patcher resets ``Default/`` on update, so edits there don't stick. Each
    ``set_source_color`` is surgical + skip-when-equal, so only the named color attributes
    change; direction attributes and every other byte are preserved (a build's direction
    flips survive, and vice versa). A pre-existing skin file gets a one-time
    ``.kazbars.bak`` first. Returns the written path, or ``None`` if no TextColors.xml
    exists in the game folder at all. Raises ``OSError`` on a failed read/write.
    """
    _default, customized, source = buff_xml._resolve_paths(game_path, _TEXTCOLORS_RELPATH)
    if source is None:
        return None
    text = source.read_text(encoding="utf-8")
    for name, hex6 in colors.items():
        text, _ = buff_xml.set_source_color(text, name, hex6)

    customized.parent.mkdir(parents=True, exist_ok=True)
    buff_xml._backup_once(customized)  # one-time backup of a pre-existing skin file
    customized.write_text(text, encoding="utf-8")
    return customized


class DamageNumberColorsPanel(tk.Toplevel):
    """Per-source flytext color editor (modal Toplevel, mirrors BuffDisplayDialog)."""

    def __init__(self, parent: tk.Misc, game_path: str) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title("Damage Number Colors - KazBars")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.game_path = game_path
        # source = the file the game reads (Customized if present, else Default); we always
        # WRITE to Customized. `_current` seeds the swatches + is the dirty baseline; `_defaults`
        # is the stock Default color each "reset" reverts to.
        self._default_path, self._customized_path, self._source_path = buff_xml._resolve_paths(
            game_path, _TEXTCOLORS_RELPATH
        )
        self._current = _read_colors(self._source_path)
        self._defaults = _read_colors(self._default_path)

        self._swatches: dict[str, ColorSwatch] = {}
        self._picks: dict[str, str] = {}
        self._baseline: dict[str, str] = {}
        self._apply_btn: ttk.Button | None = None
        self._apply_enabled: bool | None = None

        self._build_ui()
        self._baseline = dict(self._picks)
        self._refresh_apply_state()

        restore_window_position(self, "damage_number_colors", _W, _H, parent, resizable=False)
        bind_window_position_save(self, "damage_number_colors", save_size=False)
        self.geometry(f"{_W}x{_H}")
        self.deiconify()

        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        # Re-assert the dark titlebar on the panel's own map — the global one-shot patch
        # can miss a deep/scrollable Toplevel like this one. Same fix as buff_display_editor.
        self.bind("<Map>", self._reassert_dark_titlebar, add="+")

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
            "Pick a color per combat-number source, then Apply. Type /reloadui in-game to see it.",
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

        ttk.Label(body, text="Self — on you", font=FONT_BODY,
                  foreground=THEME_COLORS['accent']).grid(row=0, column=0, sticky="w", pady=(0, PAD_XS))
        ttk.Label(body, text="Other — on your target", font=FONT_BODY,
                  foreground=THEME_COLORS['accent']).grid(row=0, column=1, sticky="w", pady=(0, PAD_XS))

        r = 1
        for title, self_rows, other_rows in dis.PAIRED_GROUPS:
            self._build_group_card(body, title, self_rows, row=r, column=0)
            self._build_group_card(body, title, other_rows, row=r, column=1)
            r += 1
        shared = create_card(body, "Resources & misc")
        shared.grid(row=r, column=0, columnspan=2, sticky="nsew", pady=(0, PAD_ROW))
        for name, label in dis.SHARED_SOURCES:
            self._build_color_row(shared, name, label)

    def _build_group_card(self, parent, title, rows, *, row, column) -> None:
        pad = (0, PAD_XS) if column == 0 else (PAD_XS, 0)
        card = create_card(parent, title)
        card.grid(row=row, column=column, sticky="nsew", padx=pad, pady=(0, PAD_ROW))
        for name, label in rows:
            self._build_color_row(card, name, label)

    def _build_color_row(self, card, name, label) -> None:
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
        add_tooltip(reset, "Reset to game default")

    # ------------------------------------------------------------------ #
    # Change handlers                                                    #
    # ------------------------------------------------------------------ #

    def _on_color(self, name: str, hex_str: str) -> None:
        self._picks[name] = dis.normalize_color(hex_str) or _FALLBACK_COLOR
        self._refresh_apply_state()

    def _reset_one(self, name: str) -> None:
        base = self._defaults.get(name) or _FALLBACK_COLOR
        self._picks[name] = base
        self._swatches[name].set_color(f"#{base}")
        self._refresh_apply_state()

    def _reset_all(self) -> None:
        for name, swatch in self._swatches.items():
            base = self._defaults.get(name) or _FALLBACK_COLOR
            self._picks[name] = base
            swatch.set_color(f"#{base}")
        self._refresh_apply_state()

    def _refresh_apply_state(self) -> None:
        dirty = self._picks != self._baseline
        if self._apply_btn is None or dirty == self._apply_enabled:
            return
        self._apply_enabled = dirty
        self._apply_btn.configure(state="normal" if dirty else "disabled")

    # ------------------------------------------------------------------ #
    # Apply                                                              #
    # ------------------------------------------------------------------ #

    def _on_apply(self) -> None:
        if self._source_path is None or self._picks == self._baseline:
            return
        try:
            apply_colors(self.game_path, self._picks)
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
        self._baseline = dict(self._picks)
        self._refresh_apply_state()
        app_toast(self, "Colors saved. Type /reloadui in-game to see them.", "success")


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
