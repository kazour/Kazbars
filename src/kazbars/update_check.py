"""
KazBars — GitHub release lookup (pure, no Tk).

`fetch_release` asks the releases API for the latest tag and says whether it
is newer than the running version. `update_orchestrator` turns a hit into the
install offer and the About popup shows it in place; `self_update` does the
download. `_parts` is the shared version parser — `content_update` borrows it
for the `min_app_version` gate.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Overridable for local testing against a fake release document (precedent:
# KAZBARS_OTA_MANIFEST_URL in content_update); unset = the live GitHub API.
LATEST_RELEASE_URL = os.environ.get(
    "KAZBARS_RELEASE_API_URL",
    "https://api.github.com/repos/kazour/Kazbars/releases/latest",
)
FALLBACK_RELEASES_URL = "https://github.com/kazour/Kazbars/releases/latest"


def fetch_release(current_version):
    """Blocking lookup. Returns ('update', release) when a newer release exists
    — `release` is the API document, assets included; ('current', None) when
    up to date; ('error', None) on any network/parse failure."""
    try:
        req = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = release_tag(data)
        if not tag or _parts(tag) <= _parts(current_version):
            return ('current', None)
        return ('update', data)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError,
            AttributeError):
        return ('error', None)


def release_tag(release):
    """'3.1.0' from a release document's 'v3.1.0' tag ('' when absent)."""
    return (release.get('tag_name') or '').lstrip('v')


def _parts(version):
    """Leading digits of each dot-component, stopping at the first non-numeric
    one — so a suffixed tag like '2.3.0-rc1' still compares as (2, 3, 0)
    instead of silently reading as up-to-date."""
    parts = []
    for p in version.split('.'):
        m = re.match(r'\d+', p)
        if m is None:
            break
        parts.append(int(m.group()))
    return tuple(parts)
