"""KazBars — Deeps panel (the configuration Toplevel).

The single user-facing surface for Deeps: opened from the bottom-bar
`⚔ Deeps` button, it shows monitoring status, holds the Start/Stop
control, and exposes the three thresholds + pet toggle + layout radio
+ overlay lock. Single-instance: closing withdraws (monitoring stays
running so the overlay keeps updating in-game).

Owns three pieces:
  - `DeepsMeter`  — background tail thread (Step 6 module).
  - `DeepsOverlay` — transparent always-on-top numbers (Step 7).
  - The 100 ms UI tick that ferries data between them and decides
    when to show / hide the overlay (based on `aoc_in_focus`).

Alarm hysteresis lives here, not in the meter (matches Deeps's
Rust split — main.rs owns alarm state). The transition rule:

  - was OFF, dps >= threshold       → become ON
  - was ON,  dps <  threshold * 0.9 → become OFF
  - otherwise no change

The overlay only repaints when monitoring is running AND
`snapshot.aoc_in_focus` is True. Everything else hides it.
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
    FONT_FAMILY_CHOICES,
    get_default_settings,
    load_settings,
    save_settings,
    validate_setting,
)
from .ui_helpers import (
    BTN_DIALOG,
    BTN_LARGE,
    FONT_BODY,
    FONT_SECTION,
    FONT_SMALL,
    INPUT_WIDTH_NUM,
    INPUT_WIDTH_TYPE,
    MODULE_COLORS,
    PAD_INNER,
    PAD_LF,
    PAD_ROW,
    PAD_SMALL,
    PAD_TAB,
    PAD_XS,
    THEME_COLORS,
)
from .ui_widgets import create_dialog_header
from .window_position import restore_window_position, save_window_position

logger = logging.getLogger(__name__)

# UI tick cadence — matches the meter's housekeeping cadence so the
# painter and scorer rendezvous at the same rate.
_UI_TICK_MS = 100

# Alarm hysteresis multiplier — turn-off threshold = on-threshold * 0.9.
_ALARM_HYSTERESIS = 0.9

# Header dimensions
_HEADER_WIDTH = 360
_PANEL_DEFAULT_WIDTH = 360
# Provisional height — the panel auto-tightens to its natural reqheight after
# `_build_ui` so adding controls never clips the bottom of the window.
_PANEL_PROVISIONAL_HEIGHT = 380

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
        self.title("Deeps — KazBars")
        self.resizable(False, False)

        restore_window_position(
            self, "deeps",
            _PANEL_DEFAULT_WIDTH, _PANEL_PROVISIONAL_HEIGHT,
            parent, resizable=False,
        )

        self.settings_folder = str(settings_path)
        self.game_path_getter = game_path_getter

        # Persisted state — load before building widgets so var defaults
        # come from the user's saved settings.
        self.settings = load_settings(self.settings_folder)

        # Runtime state
        self.meter = DeepsMeter()
        self.meter.set_include_pet_damage(self.settings["include_pet_damage"])
        self.overlay: DeepsOverlay | None = None
        self._tick_id: str | None = None
        self._alarm_active: bool = False

        # tk vars for two-way binding with widgets
        self._alarm_var = tk.StringVar(value=str(int(self.settings["alarm_threshold"])))
        self._green_var = tk.StringVar(value=str(int(self.settings["hpis_green_threshold"])))
        self._yellow_var = tk.StringVar(value=str(int(self.settings["dpis_yellow_threshold"])))
        self._pet_var = tk.BooleanVar(value=bool(self.settings["include_pet_damage"]))
        self._layout_var = tk.StringVar(value=str(self.settings["layout"]))
        self._font_family_var = tk.StringVar(value=str(self.settings["overlay_font_family"]))
        self._font_size_var = tk.StringVar(value=str(int(self.settings["overlay_font_size"])))
        self._bg_opacity_var = tk.StringVar(
            value=str(round(float(self.settings["overlay_bg_opacity"]) * 100))
        )
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
        create_dialog_header(self, "Deeps", MODULE_COLORS["deeps"], width=_HEADER_WIDTH)

        body = ttk.Frame(self, padding=(PAD_TAB, PAD_LF))
        body.pack(fill="both", expand=True)

        self._build_status_block(body)
        self._build_primary_action(body)
        self._build_overlay_row(body)
        self._build_appearance(body)
        self._build_cells_picker(body)
        self._build_thresholds(body)
        self._build_pet_toggle(body)

    def _build_status_block(self, parent: ttk.Frame) -> None:
        """Two-line status: small 'Status:' label + colored body line."""
        ttk.Label(
            parent, text="Status", font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
        ).pack(anchor="w", pady=(0, PAD_XS))
        self._status_label = ttk.Label(
            parent, text="", font=FONT_BODY,
            foreground=THEME_COLORS["body"],
            wraplength=_PANEL_DEFAULT_WIDTH - 2 * PAD_TAB,
        )
        self._status_label.pack(anchor="w", pady=(0, PAD_ROW))

    def _build_primary_action(self, parent: ttk.Frame) -> None:
        """Big Start / Stop button — the headline interaction."""
        self._start_btn = ttk.Button(
            parent, text="Start Monitoring",
            width=BTN_LARGE,
            bootstyle="success",  # type: ignore[call-arg]
            command=self._on_start_stop_click,
        )
        self._start_btn.pack(anchor="w", pady=(0, PAD_ROW))

    def _build_overlay_row(self, parent: ttk.Frame) -> None:
        """Overlay group: section header + lock button + layout radio."""
        ttk.Label(
            parent, text="Overlay", font=FONT_SECTION,
            foreground=THEME_COLORS["body"],
        ).pack(anchor="w", pady=(PAD_SMALL, PAD_XS))

        row = ttk.Frame(parent)
        row.pack(anchor="w", fill="x", pady=(0, PAD_XS))

        self._lock_btn = ttk.Button(
            row, text="Lock Overlay",
            width=BTN_DIALOG + 4,
            bootstyle="secondary",  # type: ignore[call-arg]
            command=self._on_lock_click,
        )
        self._lock_btn.pack(side="left", padx=(0, PAD_TAB))

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
        """LabelFrame with font family dropdown + size and background sliders."""
        lf = ttk.LabelFrame(
            parent, text="Appearance",
            style="Card.TLabelframe",
            padding=PAD_INNER,
        )
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        # Font family — curated dropdown (FONT_FAMILY_CHOICES). Combobox is
        # readonly so the user can't type an off-list name.
        font_row = ttk.Frame(lf)
        font_row.pack(fill="x", pady=PAD_XS)
        ttk.Label(
            font_row, text="Font:", font=FONT_BODY,
            foreground=THEME_COLORS["body"],
        ).pack(side="left")
        font_combo = ttk.Combobox(
            font_row, textvariable=self._font_family_var,
            values=list(FONT_FAMILY_CHOICES),
            state="readonly",
            width=INPUT_WIDTH_TYPE + 4,
        )
        font_combo.pack(side="left", padx=(PAD_SMALL, 0))
        font_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_appearance_change())

        # Font size — slider 12-48 pt. The live label tracks the drag; the
        # setting persists on release so one drag is a single write.
        self._size_value_label = self._build_slider_row(
            lf, "Size:", from_=12, to=48,
            initial=int(self.settings["overlay_font_size"]),
            suffix="pt", on_drag=self._on_size_slider,
        )

        # Background opacity — slider 0-100 %, mapped to smooth per-pixel alpha
        # in the overlay. 0 keeps the bg fully transparent.
        self._opacity_value_label = self._build_slider_row(
            lf, "Background:", from_=0, to=100,
            initial=round(float(self.settings["overlay_bg_opacity"]) * 100),
            suffix="%", on_drag=self._on_opacity_slider,
        )

    def _build_slider_row(
        self,
        parent: tk.Misc,
        label_text: str,
        from_: int,
        to: int,
        initial: int,
        suffix: str,
        on_drag: Callable[[str], None],
    ) -> ttk.Label:
        """One row: descriptor label · ttk.Scale · live value label.

        `on_drag(value)` fires continuously while dragging — it refreshes the
        value label and pushes live to the overlay, but does NOT save. The
        setting persists on button/key release so a drag is a single write.
        Returns the value label for the drag handler to update.
        """
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=PAD_XS)
        ttk.Label(
            row, text=label_text, font=FONT_BODY,
            foreground=THEME_COLORS["body"],
        ).pack(side="left")
        value_label = ttk.Label(
            row, text=f"{initial}{suffix}", font=FONT_SMALL,
            foreground=THEME_COLORS["muted"], width=5, anchor="e",
        )
        value_label.pack(side="right")
        scale = ttk.Scale(
            row, from_=from_, to=to, value=initial,
            orient="horizontal", command=on_drag,
        )
        scale.pack(side="left", fill="x", expand=True, padx=PAD_SMALL)
        scale.bind("<ButtonRelease-1>", lambda _e: self._on_appearance_change())
        scale.bind("<KeyRelease>", lambda _e: self._on_appearance_change())
        return value_label

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

    def _build_cells_picker(self, parent: ttk.Frame) -> None:
        """LabelFrame with one checkbox per overlay cell (5 total): the four
        rate cells in one row, with ΔHP in on a second row beneath them.

        The checkbox arrangement is cosmetic — the overlay's render order is
        fixed by `ALL_CELL_IDS`; the user controls only which cells are shown.
        Labels come from the shared `CELL_LABELS` so picker and overlay agree.
        """
        lf = ttk.LabelFrame(
            parent, text="Overlay cells",
            style="Card.TLabelframe",
            padding=PAD_INNER,
        )
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
        """LabelFrame with the three threshold spinboxes."""
        lf = ttk.LabelFrame(
            parent, text="Alarm & Tints",
            style="Card.TLabelframe",
            padding=PAD_INNER,
        )
        lf.pack(fill="x", pady=(PAD_SMALL, PAD_ROW))

        self._build_threshold_row(
            lf, "DPS-out alarm",
            self._alarm_var, increment=100,
            command=self._on_thresholds_change,
            suffix="/s",
        )
        self._build_threshold_row(
            lf, "Green when ΔHP in > +",
            self._green_var, increment=10,
            command=self._on_thresholds_change,
            suffix="/s",
        )
        self._build_threshold_row(
            lf, "Orange when ΔHP in < −",
            self._yellow_var, increment=10,
            command=self._on_thresholds_change,
            suffix="/s",
        )

    def _build_threshold_row(
        self,
        parent: tk.Misc,
        label_text: str,
        var: tk.StringVar,
        increment: int,
        command: Callable[[], None],
        suffix: str,
    ) -> None:
        """One row: label · spinbox · suffix unit."""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=PAD_XS)

        ttk.Label(
            row, text=label_text + ":", font=FONT_BODY,
            foreground=THEME_COLORS["body"],
        ).pack(side="left")

        spin = ttk.Spinbox(
            row, textvariable=var,
            from_=0, to=999_999, increment=increment,
            width=INPUT_WIDTH_NUM,
            command=command,
        )
        spin.pack(side="left", padx=(PAD_SMALL, PAD_XS))
        # Spinbox `command=` fires only on arrow click — bind typing paths too.
        spin.bind("<FocusOut>", lambda _e: command())
        spin.bind("<Return>", lambda _e: command())

        ttk.Label(
            row, text=suffix, font=FONT_SMALL,
            foreground=THEME_COLORS["muted"],
        ).pack(side="left")

    def _build_pet_toggle(self, parent: ttk.Frame) -> None:
        """Checkbox + small caveat line beneath it."""
        ttk.Checkbutton(
            parent, text="Include pet damage in DPS",
            variable=self._pet_var,
            command=self._on_pet_change,
        ).pack(anchor="w", pady=(PAD_SMALL, 0))

        self._pet_caveat = ttk.Label(
            parent,
            text="Counts only your own pet's damage.",
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
        )
        # Push the latest thresholds so initial tints react correctly.
        self.overlay.update_thresholds(
            float(self.settings["alarm_threshold"]),
            float(self.settings["hpis_green_threshold"]),
            float(self.settings["dpis_yellow_threshold"]),
        )

    def _on_overlay_position_changed(self, x: int, y: int, positioned: bool) -> None:
        """Persist drag-end position to settings."""
        self.settings["overlay_x"] = x
        self.settings["overlay_y"] = y
        self.settings["overlay_positioned"] = positioned
        save_settings(self.settings_folder, self.settings)

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
        game = self.game_path_getter()
        running = self.meter.is_running()
        if not game and not running:
            self._start_btn.configure(
                text="Set game folder first",
                state="disabled",
                bootstyle="secondary",  # type: ignore[call-arg]
            )
            return
        if running:
            self._start_btn.configure(
                text="Stop Monitoring",
                state="normal",
                bootstyle="danger",  # type: ignore[call-arg]
            )
        else:
            self._start_btn.configure(
                text="Start Monitoring",
                state="normal",
                bootstyle="success",  # type: ignore[call-arg]
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
            self._lock_btn.configure(text="Unlock Overlay")
        else:
            self._lock_btn.configure(text="Lock Overlay")

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
    # Thresholds                                                         #
    # ------------------------------------------------------------------ #

    def _on_thresholds_change(self) -> None:
        """Parse + validate the three threshold fields; push to overlay + save."""
        alarm = validate_setting("alarm_threshold", self._alarm_var.get())
        green = validate_setting("hpis_green_threshold", self._green_var.get())
        yellow = validate_setting("dpis_yellow_threshold", self._yellow_var.get())

        # Snap the displayed values back to validated form (handles
        # garbage-in cases — Spinbox might show "abc" until this normalises).
        self._alarm_var.set(str(int(alarm)))
        self._green_var.set(str(int(green)))
        self._yellow_var.set(str(int(yellow)))

        self.settings["alarm_threshold"] = alarm
        self.settings["hpis_green_threshold"] = green
        self.settings["dpis_yellow_threshold"] = yellow
        save_settings(self.settings_folder, self.settings)

        if self.overlay is not None:
            self.overlay.update_thresholds(alarm, green, yellow)

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
                color = THEME_COLORS["danger"]
            else:
                text = "Not monitoring — click Start to begin."
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
        """Show/hide based on AoC focus; paint if shown."""
        if self.overlay is None:
            return
        # Always push the latest alarm state in case it didn't transition
        # this tick (the pulse cadence depends on a fresh paint every tick).
        self.overlay.update_alarm_active(self._alarm_active)
        if snapshot.aoc_in_focus:
            self.overlay.show()
            self.overlay.paint(snapshot, time.monotonic())
        else:
            self.overlay.hide()

    # ------------------------------------------------------------------ #
    # Window lifecycle                                                   #
    # ------------------------------------------------------------------ #

    def _on_withdraw(self) -> None:
        """Close button → withdraw (single-instance pattern).

        Monitoring keeps running so the overlay continues to update during
        play; the user reopens the panel from the bottom-bar button. Window
        position is saved on every withdraw so it sticks across sessions.
        """
        try:
            save_window_position(self, "deeps")
        except Exception:
            logger.debug("Failed to save Deeps window position", exc_info=True)
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
            self.overlay.destroy()
            self.overlay = None

    def restore_overlay(self) -> None:
        """Re-deiconify on next bottom-bar click while monitoring is active.

        Mirrors `LiveTrackerPanel.restore_overlay` — when the user clicks
        the bottom-bar button on an already-monitoring panel, the overlay
        gets a chance to re-show in case AoC focus changed in the meantime.
        """
        if self.meter.is_running() and self.overlay is not None:
            # Force a tick to re-evaluate aoc_in_focus + repaint.
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
