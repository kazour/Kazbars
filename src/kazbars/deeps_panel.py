"""KazBars — Deeps panel (the configuration Toplevel).

The single user-facing surface for Deeps: opened from the bottom-bar
`⚔ Deeps` button, it shows monitoring status, holds the Start/Stop
control, and exposes the DPS-out alarm slider + survival-tint presets
+ pet toggle + layout radio + overlay lock. Single-instance: closing
withdraws (monitoring stays running so the overlay keeps updating in-game).

Owns three pieces:
  - `DeepsMeter`  — background tail thread (Step 6 module).
  - `DeepsOverlay` — transparent always-on-top numbers (Step 7).
  - The 100 ms UI tick that ferries data between them: snapshot →
    status line → overlay paint. Overlay visibility is gated by the
    app-owned `ForegroundWatcher`, not here.

Alarm hysteresis lives here, not in the meter (matches Deeps's
Rust split — main.rs owns alarm state). The transition rule:

  - was OFF, dps >= threshold       → become ON
  - was ON,  dps <  threshold * 0.9 → become OFF
  - otherwise no change

The overlay paints every tick while monitoring is running; the
app-owned `ForegroundWatcher` gates its visibility on AoC focus
(`paint()` no-ops while focus-suppressed). Stop hides it entirely.
"""

import logging
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from .deeps_meter import DeepsMeter, MeterSnapshot, Status
from .deeps_overlay import ALL_CELL_IDS as _ALL_CELL_IDS
from .deeps_overlay import CELL_LABELS, DeepsOverlay
from .deeps_settings import (
    get_default_settings,
    load_settings,
    normalize_readout_preset,
    normalize_survival_preset,
    save_settings,
    validate_setting,
)
from .ui_helpers import (
    BTN_LARGE,
    BTN_SMALL,
    FONT_BODY,
    FONT_SMALL,
    MODULE_COLORS,
    PAD_LF,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import (
    add_tooltip,
    create_card,
    create_dialog_header,
    create_slider_row,
    create_status_block,
    create_tip_bar,
    create_toggle_action_button,
    refresh_toggle_button,
)
from .window_position import bind_window_position_save, restore_window_position

logger = logging.getLogger(__name__)

# UI tick cadence — matches the meter's housekeeping cadence so the
# painter and scorer rendezvous at the same rate.
_UI_TICK_MS = 100

# Alarm hysteresis multiplier — turn-off threshold = on-threshold * 0.9.
_ALARM_HYSTERESIS = 0.9

# Header dimensions — width matched to the Live Tracker panel so the two
# sibling config windows read as a set.
_HEADER_WIDTH = 440
_PANEL_DEFAULT_WIDTH = 440
# Provisional height — the panel auto-tightens to its natural reqheight after
# `_build_ui` so adding controls never clips the bottom of the window.
_PANEL_PROVISIONAL_HEIGHT = 380

# Readout-card window-width choices (mirrors `deeps_settings._WINDOW_CHOICES`;
# settings validation is the source of truth for *acceptance*, this is the
# offered option set).
_WINDOW_CHOICES = (5, 7, 11, 13)

# Readout-display PRESETS — the three named bundles that replace the old
# smoothing/round/refresh trio of controls. Window stays its own dropdown
# because it sizes the rolling buffer (the measured rate) and therefore also
# shifts where the alarm + tint ramp fire, which is a different concern from
# "how should the digits read".
#
#   Live   — exact, jittery, reactive. Every spike shows. For active parsing.
#   Steady — calm but responsive. Gentle EMA + tens rounding. The all-purpose
#            middle. Default for new installs.
#   Calm   — heavy smoothing + chunky rounding + half-second redraw. Sits
#            quietly in peripheral vision; only the colors pull the eye.
#
# Values map 1:1 onto the overlay smoother's three knobs; the panel writes
# them into `self.settings` whenever the user picks a preset, so the disk
# state, the panel state, and the overlay state never drift. The preset
# table itself lives in `deeps_settings._READOUT_PRESETS` so the normalize
# logic is unit-testable without spinning up Tk.
_READOUT_PRESET_ORDER: tuple[tuple[str, str, str], ...] = (
    ("live",   "Live",   "Exact, jittery — every spike shows. For active parsing."),
    ("steady", "Steady", "Calm but responsive. The all-purpose middle."),
    ("calm",   "Calm",   "Heavy smoothing, chunky numbers, half-second redraw."),
)
_DEFAULT_READOUT_PRESET = "steady"

# DPS-out alarm slider band (threat axis). The stored value is clamped to this
# range on display; an older out-of-band value just snaps into it on first load.
_ALARM_MIN = 1000
_ALARM_MAX = 4000
_ALARM_STEP = 50

# Survival-tint presets — two named bundles driving the four ΔHP-in tint
# thresholds together (always ordered by construction). The value table lives
# in `deeps_settings._SURVIVAL_PRESETS`; this is just the panel's display order
# + per-radio tooltip. Standard (default) glows green on a small surplus with a
# tighter danger ramp; Tank is a symmetric ±200 neutral band for big-hit play.
_SURVIVAL_PRESET_ORDER: tuple[tuple[str, str, str], ...] = (
    ("standard", "Standard", "DPS / healers — green on a small surplus, tighter danger ramp."),
    ("tank",     "Tank",     "Tanks — symmetric ±200 neutral band before any tint."),
)

# =========================================================================== #
# DeepsPanel                                                                  #
# =========================================================================== #

class DeepsPanel(tk.Toplevel):
    """Configuration + control window for the Deeps cluster."""

    def __init__(
        self,
        parent: tk.Misc,
        settings_path: str | Path,
        game_path_getter: Callable[[], str | None],
    ) -> None:
        super().__init__(parent)
        self.title("Deeps - KazBars")
        self.resizable(False, False)
        self.transient(parent)

        restore_window_position(
            self, "deeps",
            _PANEL_DEFAULT_WIDTH, _PANEL_PROVISIONAL_HEIGHT,
            parent, resizable=False,
        )
        bind_window_position_save(self, "deeps", save_size=False)

        self.settings_folder = str(settings_path)
        self.game_path_getter = game_path_getter

        # Persisted state — load before building widgets so var defaults
        # come from the user's saved settings.
        self.settings = load_settings(self.settings_folder)
        # Normalize the three smoother keys to match the persisted preset, so
        # the overlay starts coherent (`disk == memory == overlay`). A
        # power-user JSON edit that desyncs preset name vs. underlying values
        # gets snapped back to the preset on next load.
        self._normalize_readout_preset(save=False)
        # Same coherence pass for the survival-tint preset (Tank / Standard).
        self._normalize_survival_preset(save=False)
        # Snap any out-of-band stored alarm into the slider's 1000-4000/s band
        # (in-memory; persisted on the next settings write).
        self.settings["alarm_threshold"] = float(self._clamp_alarm(self.settings["alarm_threshold"]))

        # Runtime state
        self.meter = DeepsMeter()
        self.meter.set_include_pet_damage(self.settings["include_pet_damage"])
        self.meter.set_window_seconds(self.settings["window_seconds"])
        self.overlay: DeepsOverlay | None = None
        self._tick_id: str | None = None
        self._alarm_active: bool = False
        # Last (text, color) painted to the status label — lets _render_status
        # skip redundant configures on the 100 ms tick when nothing changed.
        self._last_status: tuple[str, str] | None = None
        self._focus_watcher = getattr(parent, "focus_watcher", None)

        # tk vars for two-way binding with widgets. The DPS-out alarm is
        # slider-driven — its value lives in `self.settings`, not a tk var.
        self._survival_var = tk.StringVar(value=str(self.settings["survival_preset"]))
        self._pet_var = tk.BooleanVar(value=bool(self.settings["include_pet_damage"]))
        self._layout_var = tk.StringVar(value=str(self.settings["layout"]))
        self._font_family_var = tk.StringVar(value=str(self.settings["overlay_font_family"]))
        self._font_size_var = tk.StringVar(value=str(int(self.settings["overlay_font_size"])))
        self._bg_opacity_var = tk.StringVar(
            value=str(round(float(self.settings["overlay_bg_opacity"]) * 100))
        )
        # Readout tuning vars (the "Readout" card).
        self._window_var = tk.StringVar(value=str(int(self.settings["window_seconds"])))
        self._preset_var = tk.StringVar(value=str(self.settings["readout_preset"]))
        # Cell-visibility toggles — one BooleanVar per cell ID. Initialised
        # from settings; flips push to the overlay + persist on change.
        visible_set = set(self.settings.get("visible_cells", []))
        self._cell_vars: dict[str, tk.BooleanVar] = {
            cid: tk.BooleanVar(value=(cid in visible_set))
            for cid in _ALL_CELL_IDS
        }
        # Widget refs filled in by _build_*
        self._status_label: ttk.Label | None = None
        self._start_btn: ttk.Button | None = None
        self._lock_btn: ttk.Button | None = None
        self._pet_caveat: ttk.Label | None = None
        self._size_value_label: ttk.Label | None = None
        self._opacity_value_label: ttk.Label | None = None
        self._alarm_value_label: ttk.Label | None = None
        self._survival_caption: ttk.Label | None = None

        self._build_ui()
        self._create_overlay()
        self._refresh_start_button()
        self._refresh_lock_button()
        self._render_status(MeterSnapshot.empty())  # initial idle line

        # Tighten the panel height to the natural size of its packed content.
        # `resizable=False` means the saved height is ignored anyway, so this
        # is the only place geometry is locked in for non-saved-position runs;
        # for saved-position runs, only the height changes (x/y preserved).
        self.update_idletasks()
        self.geometry(f"{_PANEL_DEFAULT_WIDTH}x{self.winfo_reqheight()}")

        self.protocol("WM_DELETE_WINDOW", self._on_withdraw)

    # ------------------------------------------------------------------ #
    # UI construction                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Compose the panel: header → status → primary action → overlay
        controls → thresholds → pet toggle."""
        # CRT dialog header — brand-defining strip, same pattern as Live Tracker.
        create_dialog_header(
            self, "Deeps", MODULE_COLORS["deeps"], width=_HEADER_WIDTH,
            accent_segments=[("by ", THEME_COLORS["muted"]), ("Veni", THEME_COLORS["warning"])],
        )
        create_tip_bar(self, "Live DPS, HPS, and net-HP readout from your combat log.")

        body = ttk.Frame(self, padding=(PAD_TAB, PAD_LF))
        body.pack(fill="both", expand=True)

        self._build_status_block(body)
        self._build_primary_action(body)
        self._build_overlay_row(body)
        self._build_appearance(body)
        self._build_readout(body)
        self._build_cells_picker(body)
        self._build_thresholds(body)
        self._build_pet_toggle(body)

    def _build_status_block(self, parent: ttk.Frame) -> None:
        """Two-line status: small 'Status' label + colored body line."""
        self._status_label = create_status_block(
            parent, "Status", wraplength=_PANEL_DEFAULT_WIDTH - 2 * PAD_TAB,
        )

    def _build_primary_action(self, parent: ttk.Frame) -> None:
        """Big Start / Stop button — the headline interaction."""
        self._start_btn = create_toggle_action_button(
            parent, self._on_start_stop_click, width=BTN_LARGE,
        )
        self._start_btn.pack(anchor="w", pady=(0, PAD_ROW))
        add_tooltip(self._start_btn, "Start or stop reading your combat log")

    def _build_overlay_row(self, parent: ttk.Frame) -> None:
        """Overlay group card: lock button + layout radio."""
        lf = create_card(parent, "Overlay")
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        row = ttk.Frame(lf)
        row.pack(anchor="w", fill="x")

        self._lock_btn = ttk.Button(
            row, text="Lock", width=BTN_SMALL,
            bootstyle="secondary",  # type: ignore[call-arg]
            command=self._on_lock_click,
        )
        self._lock_btn.pack(side="left", padx=(0, PAD_TAB))
        add_tooltip(self._lock_btn, "Lock the overlay so it can't be moved (unlock here too)")

        ttk.Radiobutton(
            row, text="Horizontal", value="horizontal",
            variable=self._layout_var,
            command=self._on_layout_change,
        ).pack(side="left", padx=(0, PAD_SMALL))
        ttk.Radiobutton(
            row, text="Vertical", value="vertical",
            variable=self._layout_var,
            command=self._on_layout_change,
        ).pack(side="left")

    def _build_appearance(self, parent: ttk.Frame) -> None:
        """Card with size + background sliders. Font family is fixed to
        Segoe UI — there is no font picker."""
        lf = create_card(parent, "Appearance")
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        # Font size — slider 12-48 pt. The live label tracks the drag; the
        # setting persists on release so one drag is a single write.
        _, self._size_value_label = create_slider_row(
            lf, "Size:", 12, 48,
            int(self.settings["overlay_font_size"]), "pt",
            self._on_size_slider, self._on_appearance_change,
        )

        # Background opacity — slider 0-100 %, mapped to smooth per-pixel alpha.
        _, self._opacity_value_label = create_slider_row(
            lf, "Background:", 0, 100,
            round(float(self.settings["overlay_bg_opacity"]) * 100), "%",
            self._on_opacity_slider, self._on_appearance_change,
        )

    def _on_size_slider(self, value: str) -> None:
        """Live font-size drag: refresh label + push to overlay (no save)."""
        size = round(float(value))
        self._font_size_var.set(str(size))
        if self._size_value_label is not None:
            self._size_value_label.configure(text=f"{size}pt")
        if self.overlay is not None:
            self.overlay.set_font(str(self._font_family_var.get()), size)

    def _on_opacity_slider(self, value: str) -> None:
        """Live background-opacity drag: refresh label + push to overlay (no save)."""
        pct = round(float(value))
        self._bg_opacity_var.set(str(pct))
        if self._opacity_value_label is not None:
            self._opacity_value_label.configure(text=f"{pct}%")
        if self.overlay is not None:
            self.overlay.set_bg_opacity(pct / 100.0)

    # ------------------------------------------------------------------ #
    # Readout (rolling window + display smoothing)                        #
    # ------------------------------------------------------------------ #

    def _build_readout(self, parent: ttk.Frame) -> None:
        """Card tuning how the numbers read: rolling-window width + a single
        Style preset (three named bundles of smoothing / rounding / refresh
        cadence). The four-control clutter (slider + two dropdowns + window
        dropdown) collapses to two surfaces — window plus preset radios.

        Window stays its own control because it sizes the rolling buffers, so
        changing it also shifts where the DPS-out alarm fires and where the
        ΔHP-in tint ramp lights up. The other three knobs only affect how the
        already-computed numbers are drawn; bundling them into presets removes
        the "what do these knobs interact with" guesswork.
        """
        lf = create_card(parent, "Readout")
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        self._build_combo_row(
            lf, "Window:", self._window_var,
            [str(s) for s in _WINDOW_CHOICES], self._on_window_change, suffix="s",
        )
        # Caveat: window affects more than just the readout numbers, so flag
        # the cross-coupling here rather than buried in a tooltip.
        ttk.Label(
            lf,
            text="Wider window = slower rate response. Alarm + tints react later.",
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
        ).pack(anchor="w", padx=(PAD_TAB + PAD_SMALL, 0))

        # Style preset selector — three radios in a row, with a tooltip on
        # each explaining the feel. Same widget pattern as the layout radios
        # above so the panel reads as one consistent control family.
        style_row = ttk.Frame(lf)
        style_row.pack(anchor="w", fill="x", pady=(PAD_SMALL, 0))
        ttk.Label(
            style_row, text="Style:", font=FONT_BODY, foreground=THEME_COLORS["body"],
        ).pack(side="left")
        for key, label, hint in _READOUT_PRESET_ORDER:
            rb = ttk.Radiobutton(
                style_row, text=label, value=key,
                variable=self._preset_var,
                command=self._on_preset_change,
            )
            rb.pack(side="left", padx=(PAD_SMALL, 0))
            add_tooltip(rb, hint)

    def _build_combo_row(
        self,
        parent: tk.Misc,
        label_text: str,
        var: tk.StringVar,
        values: list[str],
        command: Callable[[], None],
        suffix: str | None = None,
    ) -> ttk.Combobox:
        """One row: label · readonly combobox · optional suffix unit."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=PAD_XS)
        ttk.Label(
            row, text=label_text, font=FONT_BODY, foreground=THEME_COLORS["body"],
        ).pack(side="left")
        combo = ttk.Combobox(
            row, textvariable=var, values=values, state="readonly", width=8,
        )
        combo.pack(side="left", padx=(PAD_SMALL, PAD_XS))
        combo.bind("<<ComboboxSelected>>", lambda _e: command())
        if suffix:
            ttk.Label(
                row, text=suffix, font=FONT_SMALL, foreground=THEME_COLORS["muted"],
            ).pack(side="left")
        return combo

    def _on_window_change(self) -> None:
        """Window-width dropdown — persist + rebuild the meter's trackers.

        Resets the in-flight rolling average (the width IS the buffer capacity),
        so the readout re-warms over the new window.
        """
        secs = validate_setting("window_seconds", self._window_var.get())
        self._window_var.set(str(int(secs)))
        self.settings["window_seconds"] = secs
        save_settings(self.settings_folder, self.settings)
        self.meter.set_window_seconds(secs)

    def _normalize_readout_preset(self, *, save: bool) -> None:
        """Force `self.settings` to be coherent with the persisted preset name.

        Writes the preset's three values into `smoothing`/`round_step`/
        `refresh_ms`, replacing whatever was there. Called on init (no save —
        first user action will commit) and on preset click (save = True). The
        overlay is updated by the caller when it exists; on init the overlay
        is constructed *after* this runs, so its smoother starts with the
        already-normalized values without an extra push.
        """
        normalize_readout_preset(self.settings)
        if save:
            save_settings(self.settings_folder, self.settings)

    def _normalize_survival_preset(self, *, save: bool) -> None:
        """Force `self.settings` coherent with the persisted survival preset.

        Twin of `_normalize_readout_preset`: writes the preset's four tint
        thresholds into settings, replacing whatever was there. Called on init
        (no save — first user action commits) and on preset click (save=True)."""
        normalize_survival_preset(self.settings)
        if save:
            save_settings(self.settings_folder, self.settings)

    def _on_preset_change(self) -> None:
        """User picked a Readout style — normalize settings, persist, push all
        three smoother knobs to the overlay so the change is immediate."""
        self.settings["readout_preset"] = self._preset_var.get()
        self._normalize_readout_preset(save=True)
        # Re-read the (now validated) name in case the radio supplied junk.
        self._preset_var.set(self.settings["readout_preset"])
        if self.overlay is not None:
            self.overlay.set_smoothing(int(self.settings["smoothing"]))
            self.overlay.set_round_step(int(self.settings["round_step"]))
            self.overlay.set_refresh_ms(int(self.settings["refresh_ms"]))

    def _build_cells_picker(self, parent: ttk.Frame) -> None:
        """Card with one checkbox per overlay cell (5 total): the four
        rate cells in one row, with ΔHP in on a second row beneath them.

        The checkbox arrangement is cosmetic — the overlay's render order is
        fixed by `ALL_CELL_IDS`; the user controls only which cells are shown.
        Labels come from the shared `CELL_LABELS` so picker and overlay agree.
        """
        lf = create_card(parent, "Overlay Cells")
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        # Row 1: the four rate cells; row 2: ΔHP in on its own.
        for row_ids in (("dps", "dpis", "hps", "hps-out"), ("net",)):
            row = ttk.Frame(lf)
            row.pack(anchor="w", fill="x", pady=PAD_XS)
            for cid in row_ids:
                ttk.Checkbutton(
                    row, text=CELL_LABELS[cid],
                    variable=self._cell_vars[cid],
                    command=self._on_cells_change,
                ).pack(side="left", padx=(0, PAD_SMALL))

    def _on_cells_change(self) -> None:
        """Push the current visible-cells selection to the overlay + save."""
        visible = [cid for cid in _ALL_CELL_IDS if self._cell_vars[cid].get()]
        self.settings["visible_cells"] = visible
        save_settings(self.settings_folder, self.settings)
        if self.overlay is not None:
            self.overlay.set_visible_cells(visible)

    def _build_thresholds(self, parent: ttk.Frame) -> None:
        """Card holding the DPS-out alarm slider (threat) + the survival-tint
        preset radios. Replaces the old five-spinbox grid: the alarm is one
        slider, and the four ΔHP-in tint thresholds collapse into two named
        presets (Tank / Standard) since they're breakpoints on one axis."""
        lf = create_card(parent, "Alarm & Tints")
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        # DPS-out alarm — slider over the 1000-4000/s threat band. The value
        # lives in settings (no tk var); drag updates in-memory so the tick's
        # hysteresis reacts live, release persists. Seed is clamped into band.
        alarm_seed = self._clamp_alarm(self.settings["alarm_threshold"])
        _, self._alarm_value_label = create_slider_row(
            lf, "DPS-out alarm:", _ALARM_MIN, _ALARM_MAX, alarm_seed, "/s",
            self._on_alarm_slider, self._on_alarm_commit, value_width=7,
        )

        # Survival tints — two named presets driving the four tint thresholds.
        preset_row = ttk.Frame(lf)
        preset_row.pack(anchor="w", fill="x", pady=(PAD_SMALL, 0))
        ttk.Label(
            preset_row, text="Survival tints:", font=FONT_BODY,
            foreground=THEME_COLORS["body"],
        ).pack(side="left")
        for key, label, hint in _SURVIVAL_PRESET_ORDER:
            rb = ttk.Radiobutton(
                preset_row, text=label, value=key,
                variable=self._survival_var,
                command=self._on_survival_preset_change,
            )
            rb.pack(side="left", padx=(PAD_SMALL, 0))
            add_tooltip(rb, hint)

        # Live caption restating the selected preset's breakpoints in plain
        # terms, so "Tank" / "Standard" isn't a black box.
        self._survival_caption = ttk.Label(
            lf, text="", font=FONT_SMALL, foreground=THEME_COLORS["muted"],
            wraplength=_PANEL_DEFAULT_WIDTH - 2 * PAD_TAB,
        )
        self._survival_caption.pack(anchor="w", padx=(PAD_TAB + PAD_SMALL, 0))
        self._refresh_survival_caption()

    @staticmethod
    def _clamp_alarm(value: float) -> int:
        """Clamp a stored alarm threshold into the slider's display band."""
        return max(_ALARM_MIN, min(round(float(value)), _ALARM_MAX))

    def _on_alarm_slider(self, value: str) -> None:
        """Live DPS-out alarm drag: round to the step, refresh the label, and
        update the in-memory threshold so the tick's hysteresis reacts live.
        No save — the slider's release commits."""
        v = int(round(float(value) / _ALARM_STEP) * _ALARM_STEP)
        self.settings["alarm_threshold"] = float(v)
        if self._alarm_value_label is not None:
            self._alarm_value_label.configure(text=f"{v}/s")

    def _on_alarm_commit(self) -> None:
        """Alarm slider released — persist + sync the overlay's threshold field."""
        save_settings(self.settings_folder, self.settings)
        self._push_thresholds()

    def _on_survival_preset_change(self) -> None:
        """User picked Tank/Standard — snap the four tint values, persist, push
        to the overlay, refresh the caption."""
        self.settings["survival_preset"] = self._survival_var.get()
        self._normalize_survival_preset(save=True)
        # Re-read the (now validated) name in case the radio supplied junk.
        self._survival_var.set(self.settings["survival_preset"])
        self._refresh_survival_caption()
        self._push_thresholds()

    def _refresh_survival_caption(self) -> None:
        """Restate the active preset's breakpoints (U+2212 minus to match the
        overlay's signed numbers)."""
        if self._survival_caption is None:
            return
        g = int(self.settings["hpis_green_threshold"])
        s = int(self.settings["dpis_tint_start"])
        f = int(self.settings["dpis_flash"])
        self._survival_caption.configure(
            text=f"Orange from −{s}/s · flash −{f}/s · green above +{g}/s",
        )

    def _push_thresholds(self) -> None:
        """Push the five current threshold values from settings to the overlay."""
        if self.overlay is None:
            return
        self.overlay.update_thresholds(
            float(self.settings["alarm_threshold"]),
            float(self.settings["hpis_green_threshold"]),
            float(self.settings["dpis_tint_start"]),
            float(self.settings["dpis_tint_full"]),
            float(self.settings["dpis_flash"]),
        )

    def _build_pet_toggle(self, parent: ttk.Frame) -> None:
        """Checkbox + small caveat line beneath it."""
        ttk.Checkbutton(
            parent, text="Include pet damage in DPS",
            variable=self._pet_var,
            command=self._on_pet_change,
        ).pack(anchor="w", pady=(PAD_SMALL, 0))

        self._pet_caveat = ttk.Label(
            parent,
            text="Counts only your own pet's damage. Also affects DPS-out alarm timing.",
            font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
            wraplength=_PANEL_DEFAULT_WIDTH - 2 * PAD_TAB,
        )
        self._pet_caveat.pack(anchor="w", padx=(PAD_TAB + PAD_SMALL, 0))

    # ------------------------------------------------------------------ #
    # Overlay lifecycle                                                  #
    # ------------------------------------------------------------------ #

    def _create_overlay(self) -> None:
        """Build the overlay Toplevel (hidden until Start clicked).

        Font + bg-opacity are read from settings inside `DeepsOverlay.__init__`,
        so no extra push is needed here — only the thresholds need a hand-off
        since they're stored separately from the appearance fields.
        """
        self.overlay = DeepsOverlay(
            self, self.settings,
            on_position_changed=self._on_overlay_position_changed,
            on_lock_changed=self._on_overlay_lock_changed,
        )
        if self._focus_watcher:
            self._focus_watcher.register(self.overlay)
        # Push the latest thresholds so initial tints react correctly.
        self._push_thresholds()

    def _on_overlay_position_changed(self, x: int, y: int, positioned: bool) -> None:
        """Persist drag-end position to settings."""
        self.settings["overlay_x"] = x
        self.settings["overlay_y"] = y
        self.settings["overlay_positioned"] = positioned
        save_settings(self.settings_folder, self.settings)

    def _on_overlay_lock_changed(self, locked: bool) -> None:
        """The overlay's own lock indicator was clicked — persist + resync the
        panel's Lock button so both surfaces agree."""
        self.settings["overlay_locked"] = locked
        save_settings(self.settings_folder, self.settings)
        self._refresh_lock_button()

    # ------------------------------------------------------------------ #
    # Start / Stop                                                       #
    # ------------------------------------------------------------------ #

    def _on_start_stop_click(self) -> None:
        if self.meter.is_running():
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self) -> None:
        game = self.game_path_getter()
        if not game:
            # Defensive — _refresh_start_button should have disabled the
            # button, but handle the race just in case.
            return
        self.meter.set_include_pet_damage(bool(self._pet_var.get()))
        self.meter.start(game)
        self._alarm_active = False
        if self.overlay is not None:
            self.overlay.show()  # wanted-visible; the watcher gates on focus
        self._refresh_start_button()
        self._begin_tick()

    def _stop_monitoring(self) -> None:
        self.meter.stop()
        self._end_tick()
        # Hide the overlay (monitoring off → not visible per the locked decision).
        if self.overlay is not None:
            self.overlay.hide()
        self._alarm_active = False
        if self.overlay is not None:
            self.overlay.update_alarm_active(False)
        self._refresh_start_button()
        # Refresh the status line one last time to the empty/idle message.
        self._render_status(MeterSnapshot.empty())

    def _refresh_start_button(self) -> None:
        """Sync Start/Stop button label, color, and enabled-state."""
        if self._start_btn is None:
            return
        running = self.meter.is_running()
        enabled = bool(self.game_path_getter()) or running
        refresh_toggle_button(
            self._start_btn, running=running, enabled=enabled,
            disabled_label="Set game folder first",
        )

    # ------------------------------------------------------------------ #
    # Lock                                                               #
    # ------------------------------------------------------------------ #

    def _on_lock_click(self) -> None:
        if self.overlay is None:
            return
        new_state = not self.overlay.is_locked()
        self.overlay.set_locked(new_state)
        self.settings["overlay_locked"] = new_state
        save_settings(self.settings_folder, self.settings)
        self._refresh_lock_button()

    def _refresh_lock_button(self) -> None:
        if self._lock_btn is None or self.overlay is None:
            return
        if self.overlay.is_locked():
            self._lock_btn.configure(text="Unlock")
        else:
            self._lock_btn.configure(text="Lock")

    # ------------------------------------------------------------------ #
    # Layout (overlay)                                                   #
    # ------------------------------------------------------------------ #

    def _on_layout_change(self) -> None:
        layout = self._layout_var.get()
        self.settings["layout"] = layout
        save_settings(self.settings_folder, self.settings)
        if self.overlay is not None:
            self.overlay.set_layout(layout)

    # ------------------------------------------------------------------ #
    # Appearance (font family, size, bg opacity)                         #
    # ------------------------------------------------------------------ #

    def _on_appearance_change(self) -> None:
        """Parse + validate the three appearance fields; push to overlay + save.

        Single handler for all three controls so a font + size change in the
        same frame writes settings once instead of three times. The bg-opacity
        spinbox uses 0-100 (%) for friendlier units; we convert to 0.0-1.0
        before storing and pushing to the overlay.
        """
        family = validate_setting("overlay_font_family", self._font_family_var.get())
        size = validate_setting("overlay_font_size", self._font_size_var.get())
        try:
            pct = int(self._bg_opacity_var.get())
        except (ValueError, TypeError):
            pct = round(self.settings["overlay_bg_opacity"] * 100)
        opacity = validate_setting("overlay_bg_opacity", max(0, min(pct, 100)) / 100.0)

        # Snap displayed values back to validated form (handles garbage-in).
        self._font_family_var.set(str(family))
        self._font_size_var.set(str(int(size)))
        self._bg_opacity_var.set(str(round(float(opacity) * 100)))

        self.settings["overlay_font_family"] = family
        self.settings["overlay_font_size"] = size
        self.settings["overlay_bg_opacity"] = opacity
        save_settings(self.settings_folder, self.settings)

        if self.overlay is not None:
            self.overlay.set_font(str(family), int(size))
            self.overlay.set_bg_opacity(float(opacity))

    # ------------------------------------------------------------------ #
    # Pet toggle                                                         #
    # ------------------------------------------------------------------ #

    def _on_pet_change(self) -> None:
        on = bool(self._pet_var.get())
        self.settings["include_pet_damage"] = on
        save_settings(self.settings_folder, self.settings)
        self.meter.set_include_pet_damage(on)

    # ------------------------------------------------------------------ #
    # UI tick — the heartbeat                                            #
    # ------------------------------------------------------------------ #

    def _begin_tick(self) -> None:
        """Schedule the first tick (idempotent — cancels any pending)."""
        self._end_tick()
        self._tick_id = self.after(_UI_TICK_MS, self._tick)

    def _end_tick(self) -> None:
        """Cancel the pending tick if any. Safe to call multiple times."""
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except (ValueError, tk.TclError):
                pass
            self._tick_id = None

    def _tick(self) -> None:
        """The 100 ms heartbeat. Read snapshot → update status → drive overlay → reschedule."""
        # Guard against shutdown races — Toplevel destroyed mid-after.
        if not self.winfo_exists():
            return
        try:
            snapshot = self.meter.snapshot()
            self._render_status(snapshot)
            self._update_alarm_state(snapshot)
            self._update_overlay(snapshot)
        except tk.TclError:
            # Widget vanished mid-tick — give up cleanly.
            return
        self._tick_id = self.after(_UI_TICK_MS, self._tick)

    def _render_status(self, snapshot: MeterSnapshot) -> None:
        """Map (status, monitoring, game_path) to a colored status string."""
        if self._status_label is None:
            return
        running = self.meter.is_running()
        game = self.game_path_getter()

        if not running:
            if not game:
                text = "No game folder set in KazBars main window."
                color = THEME_COLORS["danger_text"]
            else:
                text = "Not monitoring. Click Start to begin."
                color = THEME_COLORS["muted"]
        elif snapshot.status is Status.NOT_STARTED:
            # Brief transition window — meter is spinning up.
            text = "Starting…"
            color = THEME_COLORS["muted"]
        elif snapshot.status is Status.WAITING_FOR_LOG:
            text = "Waiting for combat log in game folder…"
            color = THEME_COLORS["warning"]
        elif snapshot.status is Status.OLD_LOG:
            text = (
                f"Found {snapshot.log_filename}. "
                "AoC isn’t writing this log."
            )
            color = THEME_COLORS["warning"]
        elif snapshot.status is Status.TAILING:
            text = f"Tailing {snapshot.log_filename}"
            color = THEME_COLORS["success"]
        else:
            text = ""
            color = THEME_COLORS["body"]

        # Skip the configure when nothing changed — the 100 ms tick calls this
        # every frame, but the status line rarely moves while tailing.
        if (text, color) == self._last_status:
            return
        self._last_status = (text, color)
        self._status_label.configure(text=text, foreground=color)

    def _update_alarm_state(self, snapshot: MeterSnapshot) -> None:
        """Hysteresis state machine on the DPS rate.

        On with `dps >= threshold`; off with `dps < threshold * 0.9`. None /
        warm-up values don't move the state.
        """
        dps = snapshot.dps
        if dps is None:
            return
        threshold = float(self.settings["alarm_threshold"])
        off_threshold = threshold * _ALARM_HYSTERESIS
        prev = self._alarm_active
        if not prev and dps >= threshold:
            self._alarm_active = True
        elif prev and dps < off_threshold:
            self._alarm_active = False
        if self.overlay is not None and self._alarm_active != prev:
            self.overlay.update_alarm_active(self._alarm_active)

    def _update_overlay(self, snapshot: MeterSnapshot) -> None:
        """Push the latest snapshot to the overlay (single paint per tick).

        Focus-gating is the shared ForegroundWatcher's job now
        (`set_focus_suppressed`); visibility follows Start/Stop. `paint()`
        no-ops while focus-suppressed, so calling it every tick is safe and the
        alarm pulse still gets a fresh frame whenever the overlay is visible.
        """
        if self.overlay is None:
            return
        self.overlay.update_alarm_active(self._alarm_active)
        self.overlay.paint(snapshot, time.monotonic())

    # ------------------------------------------------------------------ #
    # Window lifecycle                                                   #
    # ------------------------------------------------------------------ #

    def _on_withdraw(self) -> None:
        """Close button → withdraw (single-instance pattern).

        Monitoring keeps running so the overlay continues to update during
        play; the user reopens the panel from the bottom-bar button. Position
        is persisted live by bind_window_position_save (wired in __init__).
        """
        self.withdraw()

    def cleanup(self) -> None:
        """Hard teardown — called on full app close.

        Stops monitoring, cancels the tick, destroys the overlay. Safe to
        call multiple times.
        """
        self._end_tick()
        if self.meter.is_running():
            self.meter.stop()
        if self.overlay is not None:
            if self._focus_watcher:
                self._focus_watcher.unregister(self.overlay)
            self.overlay.destroy()
            self.overlay = None

    def restore_overlay(self) -> None:
        """Re-deiconify on next bottom-bar click while monitoring is active.

        Mirrors `LiveTrackerPanel.restore_overlay` — when the user clicks
        the bottom-bar button on an already-monitoring panel, the overlay
        gets a chance to re-show in case AoC focus changed in the meantime.
        """
        if self.meter.is_running() and self.overlay is not None:
            # Force a tick to refresh the status line + repaint the overlay.
            self._tick()


# =========================================================================== #
# Entry point — called from src/kazbars/app.py                                #
# =========================================================================== #

def open_deeps_panel(app: tk.Misc) -> DeepsPanel:
    """Open or focus the singleton Deeps panel.

    Mirrors the pattern used by `_open_boss_timer` in app.py. The app
    owns the panel reference; this helper just constructs one when needed.
    """
    panel = getattr(app, "deeps_panel", None)
    if panel is not None:
        try:
            if panel.winfo_exists():
                panel.deiconify()
                panel.lift()
                panel.focus_force()
                panel.restore_overlay()
                return panel
        except tk.TclError:
            pass
    panel = DeepsPanel(app, app.settings_path, lambda: app.game_path)
    app.deeps_panel = panel  # type: ignore[attr-defined]
    return panel


def _ensure_settings_seeded(settings_folder: str | Path) -> None:
    """Write the defaults file if one doesn't exist yet — helps users see the
    file location after first install. Called lazily by `open_deeps_panel`
    only if needed; not exported."""
    Path(settings_folder).mkdir(parents=True, exist_ok=True)
    settings_file = Path(settings_folder) / "deeps_settings.json"
    if not settings_file.exists():
        save_settings(settings_folder, get_default_settings())
