"""Tests for the shared OverlayConfig + per-cluster settings adapters.

The adapters must round-trip without renaming any on-disk key — the disk
schemas (Deeps `overlay_*`, Live Tracker bare keys) are validated by their own
suites and must stay byte-stable.
"""

from kazbars.deeps_settings import (
    apply_overlay_config_to_deeps,
    overlay_config_from_deeps,
)
from kazbars.deeps_settings import (
    get_default_settings as deeps_defaults,
)
from kazbars.live_tracker_settings import (
    get_default_settings as timer_defaults,
)
from kazbars.live_tracker_settings import (
    overlay_config_from_timer,
    overlay_config_to_timer,
)
from kazbars.overlay_engine import OverlayConfig


def test_deeps_round_trip_preserves_overlay_keys():
    settings = deeps_defaults()
    settings.update(
        overlay_x=120,
        overlay_y=240,
        overlay_positioned=True,
        overlay_locked=True,
        overlay_font_family="Consolas",
        overlay_font_size=30,
        overlay_bg_opacity=0.5,
    )
    before = dict(settings)
    cfg = overlay_config_from_deeps(settings)
    assert cfg == OverlayConfig(
        x=120,
        y=240,
        positioned=True,
        locked=True,
        font_family="Consolas",
        font_size=30,
        bg_opacity=0.5,
        visible=True,
    )
    apply_overlay_config_to_deeps(settings, cfg)
    # Non-overlay keys (thresholds, cells, pet) are untouched; overlay keys match.
    assert settings == before


def test_deeps_apply_does_not_introduce_renamed_keys():
    settings = deeps_defaults()
    apply_overlay_config_to_deeps(settings, overlay_config_from_deeps(settings))
    # No bare keys leaked in from the timer schema.
    for bare in ("x", "y", "locked", "positioned", "font_family", "bg_opacity"):
        assert bare not in settings


def test_timer_round_trip_preserves_bare_keys():
    settings = timer_defaults()
    settings.update(
        x=80,
        y=60,
        positioned=True,
        locked=True,
        font_family="Courier New",
        font_size=16,
        bg_opacity=0.25,
        visible=False,
    )
    cfg = overlay_config_from_timer(settings)
    assert cfg == OverlayConfig(
        x=80,
        y=60,
        positioned=True,
        locked=True,
        font_family="Courier New",
        font_size=16,
        bg_opacity=0.25,
        visible=False,
    )
    projected = overlay_config_to_timer(cfg)
    for key in (
        "x",
        "y",
        "positioned",
        "locked",
        "font_family",
        "font_size",
        "bg_opacity",
        "visible",
    ):
        assert projected[key] == settings[key]
    # No Deeps-prefixed keys leaked in.
    assert not any(k.startswith("overlay_") for k in projected)


def test_defaults_map_to_default_config():
    assert overlay_config_from_timer(timer_defaults()).font_family == "Segoe UI"
    assert overlay_config_from_deeps(deeps_defaults()).font_size == 22
