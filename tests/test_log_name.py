"""Tests for the combat-log display-name sanitizer."""

from kazbars.live_tracker_settings import sanitize_log_name


def test_full_filename_with_extension():
    assert sanitize_log_name("CombatLog-2026-05-16_2152.txt") == "CombatLog_2152"


def test_filename_without_extension():
    assert sanitize_log_name("CombatLog-2026-05-16_2152") == "CombatLog_2152"


def test_full_path_is_reduced_to_name():
    assert sanitize_log_name(r"D:\AoC\CombatLog-2026-05-16_2152.txt") == "CombatLog_2152"
    assert sanitize_log_name("/home/u/AgeOfConan/CombatLog-2026-01-02_0007.txt") == "CombatLog_0007"


def test_unmatched_name_falls_back_to_stem():
    assert sanitize_log_name("CombatLog.txt") == "CombatLog"
    assert sanitize_log_name("weird-name.log") == "weird-name"
    assert sanitize_log_name("CombatLog-bad_format.txt") == "CombatLog-bad_format"
