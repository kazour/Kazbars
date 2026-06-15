"""KazBars — Standalone buff-tracking grid editor for Age of Conan."""

__version__ = "2.2.0"
APP_NAME = "KazBars"

# The buff-content version this build ships with — the floor for the OTA check.
# Stamped by scripts/gen_manifest.py at build time (kept == ota/manifest.json's
# content_version; test_manifest.py enforces). PREFS_SCHEMA.content_version
# defaults to this, so a fresh install already knows it ships current and the
# first-run OTA is a silent no-op unless the server has moved past the build.
CONTENT_BASELINE_VERSION = 8
