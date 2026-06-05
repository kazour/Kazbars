"""KazBars — Damage Numbers panel (the configuration Toplevel).

Opened from Game ▸ Damage Numbers…, this is the single surface for tuning AoC's
floating combat-number overlay. Unlike Deeps/Live Tracker it has no live overlay or
meter: every value here is an *offset* baked into a modded ``DamageInfo.swf`` at the
next Build & Install (see :mod:`damageinfo_settings` / :mod:`damageinfo_generator`).

A master **Enable** toggle gates everything — when off, the controls grey out and the
build leaves the stock file in place (reverting any prior mod). Settings persist to
``damageinfo_settings.json`` on every change. Single-instance, opened via
``open_damage_numbers_panel`` (mirrors ``open_deeps_panel``).

Sliders run in offset space but their readout shows the resulting game value
(``compute_final_value``), so a 0 offset reads as the stock number, not "0".
"""

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import damageinfo_settings as dis
from .ui_components import create_scrollable_frame
from .ui_forms import create_card, create_slider_row
from .ui_headers import create_dialog_header, create_tip_bar
from .ui_helpers import (
    FONT_BODY,
    MODULE_COLORS,
    PAD_ROW,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import add_tooltip, app_toast
from .window_position import bind_window_position_save, restore_window_position

logger = logging.getLogger(__name__)

_W = 470
_H = 620

# Cards, in display order: (title, [setting keys]). The keep-ranged-big toggle (the
# headline distance fix) lives in Behavior alongside the other on/off behaviours.
_CARDS = (
    ('Shadow', ['shadow_mode', 'shadow_distance', 'shadow_blur']),
    ('Size', ['text_scale']),
    ('Above-target position', ['dir1_x_offset', 'dir1_y_offset']),
    ('Fixed columns', ['fixed_col_x', 'fixed_col_y', 'fixed_col_split', 'col_b_x', 'col_b_y']),
    ('Zig-zag (static)', ['fixed_x_base', 'fixed_y_base', 'spread_spacing']),
    ('Behavior', ['ranged_keep', 'show_titles', 'other_resource_loss_to_target']),
)


class DamageNumbersPanel(tk.Toplevel):
    """Configuration window for the Damage Numbers mod."""

    def __init__(self, parent: tk.Misc, settings_path: str | Path) -> None:
        super().__init__(parent)
        self.title("Damage Numbers - KazBars")
        self.resizable(False, False)
        self.transient(parent)

        restore_window_position(self, "damage_numbers", _W, _H, parent, resizable=False)
        bind_window_position_save(self, "damage_numbers", save_size=False)

        self.settings_folder = str(settings_path)
        self.settings = dis.load_settings(self.settings_folder)

        # Widget registries (keyed by setting) so presets can re-sync the UI.
        self._scales: dict[str, ttk.Scale] = {}
        self._value_labels: dict[str, ttk.Label] = {}
        self._enum_vars: dict[str, tuple[tk.StringVar, list]] = {}
        self._bool_vars: dict[str, tk.BooleanVar] = {}
        self._all_controls: list = []      # everything gated by the master enable
        self._colb_scales: list = []       # gated by fixed_col_split
        self._shadow_dist_scale: ttk.Scale | None = None
        self._shadow_blur_scale: ttk.Scale | None = None
        self._spread_spacing_var: tk.StringVar | None = None  # the coupled spread/spacing radio

        self._enabled_var = tk.BooleanVar(value=bool(self.settings['enabled']))

        self._build_ui()
        self._sync_enabled_state()

        self.geometry(f"{_W}x{_H}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------------ #
    # UI construction                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        create_dialog_header(self, "Damage Numbers", MODULE_COLORS['damage_numbers'], width=_W)
        create_tip_bar(
            self,
            "Tune AoC's floating combat numbers. Changes apply on your next Build & Install.",
        )
        self._build_master(self)

        outer, inner, _canvas = create_scrollable_frame(self)
        outer.pack(fill="both", expand=True)
        body = ttk.Frame(inner, padding=(PAD_TAB, 0))
        body.pack(fill="both", expand=True)

        self._build_presets(body)
        for title, keys in _CARDS:
            card = create_card(body, title)
            card.pack(fill="x", pady=(0, PAD_ROW))
            for key in keys:
                self._build_control(card, key)

    def _build_master(self, parent: tk.Misc) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=PAD_TAB, pady=(0, PAD_XS))
        cb = ttk.Checkbutton(
            row, text="Enable the Damage Numbers mod", variable=self._enabled_var,
            command=self._on_enabled,
        )
        cb.pack(side="left")
        add_tooltip(cb, "When off, builds leave AoC's stock DamageInfo.swf untouched "
                        "(and revert any mod previously installed).")

    def _build_presets(self, parent: tk.Misc) -> None:
        card = create_card(parent, "Presets")
        card.pack(fill="x", pady=(0, PAD_ROW))
        row = ttk.Frame(card)
        row.pack(fill="x")
        for name in dis.PRESETS:
            btn = ttk.Button(
                row, text=name, bootstyle="secondary", width=12,
                command=lambda n=name: self._apply_preset(n),
            )
            btn.pack(side="left", padx=(0, PAD_XS))
            self._all_controls.append(btn)

    def _build_control(self, card: ttk.LabelFrame, key: str) -> None:
        if key == 'spread_spacing':  # composite radio driving two baked offsets
            self._build_spread_spacing(card)
            return
        kind = dis.GLOBAL_SETTINGS[key].get('type')
        if kind == 'enum':
            self._build_enum(card, key)
        elif kind == 'bool':
            self._build_bool(card, key)
        else:
            self._build_slider(card, key)

    def _build_slider(self, card: ttk.LabelFrame, key: str) -> None:
        meta = dis.GLOBAL_SETTINGS[key]
        offset = self.settings[key]
        # Vertical-position sliders run high→low so dragging right moves the number up
        # (screen Y grows downward). The stored offset and baked value are unchanged.
        lo, hi = (meta['max'], meta['min']) if meta.get('invert') else (meta['min'], meta['max'])
        scale, label = create_slider_row(
            card, meta['description'] + ":", lo, hi, offset, meta['unit'],
            on_drag=lambda v, k=key: self._on_slider(k, v),
            on_commit=self._save,
            value_width=6,
            notch=dis.is_offset_key(key),
        )
        label.configure(text=self._readout(key, offset))
        if meta.get('tooltip'):
            add_tooltip(scale, meta['tooltip'])
        self._scales[key] = scale
        self._value_labels[key] = label
        self._all_controls.append(scale)
        if key == 'shadow_distance':
            self._shadow_dist_scale = scale
        elif key == 'shadow_blur':
            self._shadow_blur_scale = scale
        elif key in ('col_b_x', 'col_b_y'):
            self._colb_scales.append(scale)

    def _build_enum(self, card: ttk.LabelFrame, key: str) -> None:
        meta = dis.GLOBAL_SETTINGS[key]
        options = meta['options']
        row = ttk.Frame(card)
        row.pack(fill="x", pady=PAD_XS)
        lbl = ttk.Label(row, text=meta['description'] + ":", font=FONT_BODY,
                        foreground=THEME_COLORS['body'])
        lbl.pack(side="left")
        if meta.get('tooltip'):
            add_tooltip(lbl, meta['tooltip'])
        var = tk.StringVar(value=options[int(self.settings[key])])
        self._enum_vars[key] = (var, options)
        for opt in options:
            rb = ttk.Radiobutton(
                row, text=opt, value=opt, variable=var,
                command=lambda k=key: self._on_enum(k),
            )
            rb.pack(side="left", padx=PAD_XS)
            self._all_controls.append(rb)

    def _build_spread_spacing(self, card: ttk.LabelFrame) -> None:
        """One radio that sets the zig-zag spread + spacing together (no per-axis slider)."""
        row = ttk.Frame(card)
        row.pack(fill="x", pady=PAD_XS)
        lbl = ttk.Label(row, text="Spread-spacing:", font=FONT_BODY,
                        foreground=THEME_COLORS['body'])
        lbl.pack(side="left")
        add_tooltip(lbl, "Zig-zag swing width and row gap together. "
                         "Compact = tight, Extended = wide.")
        var = tk.StringVar(value=dis.spread_spacing_option(self.settings))
        self._spread_spacing_var = var
        for name, _values in dis.SPREAD_SPACING_OPTIONS:
            rb = ttk.Radiobutton(
                row, text=name, value=name, variable=var, command=self._on_spread_spacing,
            )
            rb.pack(side="left", padx=PAD_XS)
            self._all_controls.append(rb)

    def _build_bool(self, card: ttk.LabelFrame, key: str) -> None:
        meta = dis.GLOBAL_SETTINGS[key]
        var = tk.BooleanVar(value=bool(self.settings[key]))
        self._bool_vars[key] = var
        cb = ttk.Checkbutton(
            card, text=meta['description'], variable=var,
            command=lambda k=key: self._on_bool(k),
        )
        cb.pack(anchor="w", pady=PAD_XS)
        if meta.get('tooltip'):
            add_tooltip(cb, meta['tooltip'])
        self._all_controls.append(cb)

    # ------------------------------------------------------------------ #
    # Value helpers                                                      #
    # ------------------------------------------------------------------ #

    def _readout(self, key: str, offset) -> str:
        """The slider's right-side label (pure; see ``dis.readout``)."""
        return dis.readout(key, offset)

    def _quantize(self, key: str, raw: float):
        """Snap a continuous scale value to the key's step and clamp it.

        The extra round(..., 10) collapses binary-float drift (e.g. 0.7000000000000001)
        so the stored offset and the JSON stay canonical; the readout/bake already format
        defensively, so this is hygiene, not a behavior change.
        """
        step = dis.GLOBAL_SETTINGS[key]['step']
        return dis.validate_setting(key, round(round(raw / step) * step, 10))

    def _save(self) -> None:
        dis.save_settings(self.settings_folder, self.settings)

    # ------------------------------------------------------------------ #
    # Change handlers                                                    #
    # ------------------------------------------------------------------ #

    def _on_slider(self, key: str, raw) -> None:
        offset = self._quantize(key, float(raw))
        self.settings[key] = offset
        self._value_labels[key].configure(text=self._readout(key, offset))

    def _on_enum(self, key: str) -> None:
        var, options = self._enum_vars[key]
        self.settings[key] = options.index(var.get())
        self._save()
        if key == 'shadow_mode':
            self._sync_shadow_state()

    def _on_bool(self, key: str) -> None:
        self.settings[key] = int(self._bool_vars[key].get())
        self._save()
        if key == 'fixed_col_split':
            self._sync_split_state()

    def _on_spread_spacing(self) -> None:
        name = self._spread_spacing_var.get()
        for opt_name, values in dis.SPREAD_SPACING_OPTIONS:
            if opt_name == name:
                self.settings.update(values)  # writes both fixed_x_offset + fixed_y_spacing
                break
        self._save()

    def _on_enabled(self) -> None:
        self.settings['enabled'] = bool(self._enabled_var.get())
        self._save()
        self._sync_enabled_state()

    def _apply_preset(self, name: str) -> None:
        self.settings = dis.apply_preset(self.settings, name)
        self._save()
        self._refresh_all()
        app_toast(self, f"Applied the {name} preset", "info", 3)

    # ------------------------------------------------------------------ #
    # State sync                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _set_state(widget, on: bool) -> None:
        if widget is not None:
            widget.configure(state="normal" if on else "disabled")

    def _sync_enabled_state(self) -> None:
        """Master gate: grey every control when the mod is disabled."""
        on = self._enabled_var.get()
        for widget in self._all_controls:
            self._set_state(widget, on)
        if on:
            self._sync_shadow_state()
            self._sync_split_state()

    def _sync_shadow_state(self) -> None:
        """Shadow offset needs Fast or Real; softness (blur) needs Real."""
        if not self._enabled_var.get():
            return
        mode = self.settings['shadow_mode']
        self._set_state(self._shadow_dist_scale, mode >= 1)
        self._set_state(self._shadow_blur_scale, mode == 2)

    def _sync_split_state(self) -> None:
        """Column B controls only matter when the split is on."""
        if not self._enabled_var.get():
            return
        on = bool(self.settings['fixed_col_split'])
        for scale in self._colb_scales:
            self._set_state(scale, on)

    def _refresh_all(self) -> None:
        """Re-sync every widget to ``self.settings`` (after a preset apply)."""
        for key, scale in self._scales.items():
            offset = self.settings[key]
            # A disabled ttk.Scale silently ignores .set(); enable first, then let
            # _sync_enabled_state below re-apply the master + shadow/split gates.
            scale.configure(state="normal")
            scale.set(offset)
            self._value_labels[key].configure(text=self._readout(key, offset))
        for key, (var, options) in self._enum_vars.items():
            var.set(options[int(self.settings[key])])
        for key, var in self._bool_vars.items():
            var.set(bool(self.settings[key]))
        if self._spread_spacing_var is not None:
            self._spread_spacing_var.set(dis.spread_spacing_option(self.settings))
        self._sync_enabled_state()


def open_damage_numbers_panel(app: tk.Misc) -> DamageNumbersPanel:
    """Open or focus the singleton Damage Numbers panel (mirrors open_deeps_panel)."""
    panel = getattr(app, "damage_numbers_panel", None)
    if panel is not None:
        try:
            if panel.winfo_exists():
                panel.deiconify()
                panel.lift()
                panel.focus_force()
                return panel
        except tk.TclError:
            pass
    panel = DamageNumbersPanel(app, app.settings_path)
    app.damage_numbers_panel = panel  # type: ignore[attr-defined]
    return panel
