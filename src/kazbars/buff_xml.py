"""KazBars — AoC HUD XML helpers (pure data layer).

Regex-only edits of <BuffListView/> tags inside AoC's HUD XML files. No Tk,
no ttkbootstrap — safe to import from CI without the UI extra.
"""

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


BUFF_FILES = [
    ("Player",   "Views/HUD/CharPortraitLeft.xml"),
    ("Target",   "Views/HUD/CharPortraitRight.xml"),
    ("Top",      "Views/HUD/HUDView.xml"),
    ("Floating", "Views/HUD/FloatingPortraitView.xml"),
]

FILTER_FRIENDLY = 'friendly'
FILTER_HOSTILE = 'hostile'
FILTER_BOTH = 'friendly | hostile'

BACKUP_SUFFIX = '.kazbars.bak'

_BUFFLISTVIEW_TAG_RE = re.compile(r'<BuffListView\b[^>]*?/>', re.DOTALL)
_KZ_OFF_RE = re.compile(
    r'<!--\s*KZ_OFF\s*(<BuffListView\b[^>]*?/>)\s*KZ_OFF\s*-->',
    re.DOTALL,
)


# ============================================================================
# PATH HELPERS
# ============================================================================
def _resolve_paths(game_path, relpath):
    """Return (default_path, customized_path, source_path).

    source_path is Customized if it exists, else Default, else None.
    """
    base = Path(game_path) / "Data" / "Gui"
    default_path = base / "Default" / relpath
    customized_path = base / "Customized" / relpath
    if customized_path.is_file():
        source_path = customized_path
    elif default_path.is_file():
        source_path = default_path
    else:
        source_path = None
    return default_path, customized_path, source_path


def _detect_custom_ui(game_path):
    """True if Customized/Views/HUD/ contains files we don't manage, or
    Customized/Views/ has any subfolder other than HUD."""
    base = Path(game_path) / "Data" / "Gui" / "Customized" / "Views"
    if not base.is_dir():
        return False
    managed = {Path(rp).name for _, rp in BUFF_FILES}
    hud_dir = base / "HUD"
    if hud_dir.is_dir():
        for entry in hud_dir.iterdir():
            if entry.is_file() and entry.name not in managed:
                if entry.name.endswith(BACKUP_SUFFIX):
                    continue
                return True
            if entry.is_dir():
                return True
    for entry in base.iterdir():
        if entry.is_dir() and entry.name != "HUD":
            return True
        if entry.is_file():
            return True
    return False


# ============================================================================
# XML EDITS (regex-only, no parser)
# ============================================================================
def _read_attr(tag_text, attr_name):
    m = re.search(rf'\b{re.escape(attr_name)}\s*=\s*"([^"]*)"', tag_text)
    return m.group(1) if m else None


def _replace_attr(tag_text, attr_name, value):
    """Set an attribute inside a self-closing tag, injecting before `/>` if absent.

    Caller guarantees the tag matches `_BUFFLISTVIEW_TAG_RE` (so it ends with
    `/>`). The four attrs this dialog manages are all documented BuffListView
    attributes — AoC's parser handles them whether or not the source listed them.
    """
    pattern = re.compile(rf'(\b{re.escape(attr_name)}\s*=\s*")[^"]*(")')
    new_text, n = pattern.subn(lambda m: m.group(1) + value + m.group(2), tag_text)
    if n:
        return new_text
    m = re.search(r'(\s*/>)\s*$', tag_text)
    assert m is not None, "caller guarantees the tag ends with />"
    return tag_text[:m.start()] + f' {attr_name}="{value}"' + m.group(1)


def _normalise_filter(raw):
    """Map a raw filter= value to FILTER_FRIENDLY/HOSTILE/BOTH, or raw if no fit.

    Strips whitespace around the pipe so 'friendly|hostile',
    'friendly | hostile', and 'hostile|friendly' all map to BOTH.
    """
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split('|')]
    parts = [p for p in parts if p]
    parts_lower = sorted(p.lower() for p in parts)
    if parts_lower == ['friendly', 'hostile']:
        return FILTER_BOTH
    if len(parts) == 1:
        v = parts[0].lower()
        if v == 'friendly':
            return FILTER_FRIENDLY
        if v == 'hostile':
            return FILTER_HOSTILE
    return raw


def _read_bufflistview(xml_text):
    """Extract attrs from a <BuffListView /> in the file.

    Returns dict (icon_size, icon_spacing, max_columns, filter, enabled), or
    None if no <BuffListView> tag is present. enabled is False when wrapped in
    a KZ_OFF comment.
    """
    enabled = True
    m_off = _KZ_OFF_RE.search(xml_text)
    if m_off:
        enabled = False
        tag_text = m_off.group(1)
    else:
        m = _BUFFLISTVIEW_TAG_RE.search(xml_text)
        if not m:
            return None
        tag_text = m.group(0)

    return {
        'icon_size':    _read_attr(tag_text, 'icon_size'),
        'icon_spacing': _read_attr(tag_text, 'icon_spacing'),
        'max_columns':  _read_attr(tag_text, 'max_columns'),
        'filter':       _normalise_filter(_read_attr(tag_text, 'filter')),
        'enabled':      enabled,
    }


def _write_bufflistview(xml_text, attrs, enabled):
    """Apply attrs to the file's <BuffListView /> in place.

    `attrs` keys (icon_size, icon_spacing, max_columns, filter) with a None
    value are left untouched. Skip-when-equal keeps unrelated bytes identical
    so a one-field edit produces a one-field diff. KZ_OFF wrap is stripped
    before edits and re-applied if `enabled` is False. Returns None if the
    file has no <BuffListView> tag at all.
    """
    m_off = _KZ_OFF_RE.search(xml_text)
    if m_off:
        xml_text = xml_text[:m_off.start()] + m_off.group(1) + xml_text[m_off.end():]

    m = _BUFFLISTVIEW_TAG_RE.search(xml_text)
    if not m:
        return None

    new_tag = m.group(0)
    for attr_name in ('icon_size', 'icon_spacing', 'max_columns', 'filter'):
        value = attrs.get(attr_name)
        if value is None or _read_attr(new_tag, attr_name) == value:
            continue
        new_tag = _replace_attr(new_tag, attr_name, value)

    if not enabled:
        new_tag = f'<!--KZ_OFF {new_tag} KZ_OFF-->'

    return xml_text[:m.start()] + new_tag + xml_text[m.end():]


def _backup_once(customized_path):
    """Copy customized_path → customized_path.kazbars.bak iff .bak doesn't
    already exist. Lets the user recover their pre-Kaz-Grids state by hand."""
    bak = customized_path.with_name(customized_path.name + BACKUP_SUFFIX)
    if customized_path.is_file() and not bak.exists():
        try:
            shutil.copy2(customized_path, bak)
        except OSError as e:
            logger.warning("Could not write backup %s: %s", bak, e)


def _maybe_int(value):
    """Parse value to int, or None if blank/unparseable. Blanks must not
    materialise as zero — they stay out of the write attrs so the source's
    existing value (or absence) is preserved."""
    try:
        s = str(value).strip()
        return int(s) if s else None
    except (ValueError, TypeError):
        return None


def _parse_point(raw):
    """Pull (x, y) from 'Point(31,31)'. None on parse failure."""
    if raw is None:
        return None
    m = re.match(r'\s*Point\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)\s*$', raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _format_point(x, y):
    return f'Point({x},{y})'


# ============================================================================
# TEXTCOLORS.xml — resource-loss flytext direction (Damage Numbers toggle)
# ============================================================================
# AoC's TextColors.xml gives each flying-text type a `direction`: 1 = float above the
# head, -1 = drop into the fixed column. These four resource-LOSS types ship at 1;
# flipping them to -1 routes your own mana/stamina losses into the same fixed column
# as your gains (already -1), so all your resource changes read in one place. The
# DamageInfo SWF separately keeps drains you deal to ENEMIES floating over them
# (OTHER_RESOURCE_LOSS_TO_TARGET). Surgical + reversible — restore flips back to 1.
RESOURCE_LOSS_TYPES = (
    'stamina_lost', 'mana_lost', 'stamina_loss_critical', 'mana_loss_critical',
)

_DIRECTION_ATTR_RE = re.compile(r'(\bdirection\s*=\s*["\'])(-?\d+)(["\'])')


def set_resource_loss_to_column(xml_text, to_column):
    """Set `direction` for the four resource-loss flytext types in TextColors.xml.

    ``to_column`` True → ``direction="-1"`` (fixed column, with your resource gains);
    False → ``direction="1"`` (above the head, stock). Only the element carrying each
    ``name="<type>"`` is touched (any attribute order, single- or multi-line); all other
    bytes are preserved. Returns ``(new_text, flips)`` — ``flips`` counts the direction
    attributes actually changed (0 ⇒ already in the wanted state or types absent).
    """
    target = '-1' if to_column else '1'
    flips = 0
    for name in RESOURCE_LOSS_TYPES:
        elem_re = re.compile(rf'<[^>]*\bname\s*=\s*["\']{re.escape(name)}["\'][^>]*>')
        m = elem_re.search(xml_text)
        if not m:
            continue
        new_elem, n = _DIRECTION_ATTR_RE.subn(rf'\g<1>{target}\g<3>', m.group(0))
        if n and new_elem != m.group(0):
            xml_text = xml_text[:m.start()] + new_elem + xml_text[m.end():]
            flips += n
    return xml_text, flips
