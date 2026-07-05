"""KazBars — Damage Number Colors panel.

A per-source color editor for AoC's floating combat numbers, opened from the Game menu
("Damage number colors…"). Every flytext source (see
:data:`damageinfo_settings.PAIRED_GROUPS` / ``SHARED_SOURCES`` — ~35 types) gets its own
swatch, laid out in two columns: **self** (numbers on you) on the left, **other** (numbers
on your target) on the right, with the shared resource/XP/murder types in a full-width
card below.

Like the rest of Damage Numbers this is settings-only: picks are stored in
``damageinfo_settings.json`` (``source_colors``) and written to the skin's ``TextColors.xml``
on the next Build & Install (``build_executor._prepare_textcolors``). Baseline swatch colors
are read from that file (preferring the one-time stock backup so "reset" reverts to the
game default, not a previously-applied pick). Single-instance, mirrors
``open_damage_numbers_panel``.
"""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import buff_xml
from . import damageinfo_settings as dis
from .ui_components import create_scrollable_frame
from .ui_forms import ColorSwatch, create_card
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    BTN_DIALOG,
    FONT_BODY,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_ROW,
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
_FALLBACK_COLOR = "FFFFFF"  # swatch shown when no baseline + no override is known


def _read_baseline_colors(game_path) -> dict[str, str]:
    """Map source name → bare ``RRGGBB`` from the skin's *stock* TextColors.xml.

    Prefers the one-time stock backup (so "reset" reverts to the game default rather than a
    color we applied on a previous build); falls back to the live file. ``{}`` when the game
    folder is unset or the file is unreadable.
    """
    if not game_path:
        return {}
    try:
        _default, _customized, source = buff_xml._resolve_paths(game_path, _TEXTCOLORS_RELPATH)
        if source is None:
            return {}
        backup = source.with_name(source.name + buff_xml.BACKUP_SUFFIX)
        text = (backup if backup.exists() else source).read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Could not read TextColors.xml baseline colors: %s", e)
        return {}
    out: dict[str, str] = {}
    for name in dis.ALL_SOURCE_NAMES:
        color = buff_xml.read_source_color(text, name)
        if color:
            out[name] = color
    return out


class DamageNumberColorsPanel(tk.Toplevel):
    """Per-source flytext color editor (Toplevel)."""

    def __init__(self, parent: tk.Misc, settings_path: str | Path, game_path: str | None) -> None:
        super().__init__(parent)
        self.title("Damage Number Colors - KazBars")
        self.resizable(False, False)
        self.transient(parent)

        restore_window_position(self, "damage_number_colors", _W, _H, parent, resizable=False)
        bind_window_position_save(self, "damage_number_colors", save_size=False)

        self.settings_folder = str(settings_path)
        self.settings = dis.load_settings(self.settings_folder)
        self._baseline = _read_baseline_colors(game_path)
        self._swatches: dict[str, ColorSwatch] = {}

        self._build_ui()

        self.geometry(f"{_W}x{_H}")
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
            "Pick a color per combat-number source. Applies on your next Build & Install.",
        )
        if not self._baseline:
            ttk.Label(
                self, text="Set your game folder to read your current colors — picks still save.",
                font=FONT_SMALL, foreground=THEME_COLORS['muted'], wraplength=_W - 2 * PAD_TAB,
                justify="left",
            ).pack(fill="x", padx=PAD_TAB, pady=(0, PAD_XS))

        # Footer first so it reserves height before the scrollable body claims the rest.
        footer = ttk.Frame(self, padding=(PAD_TAB, PAD_XS))
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="Close", width=BTN_DIALOG, bootstyle="secondary",
                   command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Reset all to game default", bootstyle="link",
                   command=self._reset_all).pack(side="left")

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

        current = self.settings['source_colors'].get(name) or self._baseline.get(name) or _FALLBACK_COLOR
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
        self.settings['source_colors'][name] = hex_str.lstrip("#").upper()
        self._save()

    def _reset_one(self, name: str) -> None:
        self.settings['source_colors'].pop(name, None)
        self._save()
        base = self._baseline.get(name) or _FALLBACK_COLOR
        self._swatches[name].set_color(f"#{base}")

    def _reset_all(self) -> None:
        self.settings['source_colors'] = {}
        self._save()
        for name, swatch in self._swatches.items():
            base = self._baseline.get(name) or _FALLBACK_COLOR
            swatch.set_color(f"#{base}")
        app_toast(self, "Reset all colors to game default", "info", 3)

    def _save(self) -> None:
        dis.save_source_colors(self.settings_folder, self.settings['source_colors'])


def open_damage_number_colors_panel(app: tk.Misc) -> DamageNumberColorsPanel:
    """Open or focus the singleton Damage Number Colors panel."""
    panel = getattr(app, "damage_number_colors_panel", None)
    if panel is not None:
        try:
            if panel.winfo_exists():
                panel.deiconify()
                panel.lift()
                panel.focus_force()
                return panel
        except tk.TclError:
            pass
    panel = DamageNumberColorsPanel(app, app.settings_path, getattr(app, "game_path", None))
    app.damage_number_colors_panel = panel  # type: ignore[attr-defined]
    return panel
