"""Tests for the pure Start/Stop toggle-button state mapping."""

from kazbars.ui_widgets import toggle_button_state


def test_idle_enabled_is_green_start():
    assert toggle_button_state(running=False, enabled=True) == (
        "Start Monitoring",
        "success",
        "normal",
    )


def test_running_is_red_stop():
    assert toggle_button_state(running=True, enabled=True) == (
        "Stop Monitoring",
        "danger",
        "normal",
    )


def test_disabled_overrides_running():
    text, bootstyle, state = toggle_button_state(
        running=True,
        enabled=False,
        disabled_label="Set game folder first",
    )
    assert text == "Set game folder first"
    assert bootstyle == "secondary"
    assert state == "disabled"


def test_disabled_without_label_falls_back_to_start_label():
    text, _bootstyle, state = toggle_button_state(running=False, enabled=False)
    assert text == "Start Monitoring"
    assert state == "disabled"


def test_custom_labels():
    assert toggle_button_state(False, True, start_label="Start", stop_label="Stop")[0] == "Start"
    assert toggle_button_state(True, True, start_label="Start", stop_label="Stop")[0] == "Stop"
