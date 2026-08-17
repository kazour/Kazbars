"""KazBars — AoC HUD XML helpers (pure data layer).

Regex-only edits of <BuffListView/> tags inside AoC's HUD XML files. No Tk,
no ttkbootstrap — safe to import from CI without the UI extra.

Also owns the ``buff_bars`` PATCH-lane profile section (sparse — see
``PROFILE_SECTION`` below): the per-file (Player/Target/Top/Floating)
attribute *overrides* ``buff_display_editor.py`` writes into these XML files.
Registered by app.py.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any

from .profile_document import LANE_PATCH
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema

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

# <BuffListView> attribute bounds — stock icon size is 31; bounds bracket the
# usable range so a stray scroll-wheel can't make the HUD invisible (4px) or
# destroy layout (200px). Shared by buff_display_editor.py's spinboxes and
# the buff_bars section validator below, so the two can't drift.
ICON_SIZE_MIN, ICON_SIZE_MAX = 8, 128
SPACING_MIN, SPACING_MAX = 0, 50
COLS_MIN, COLS_MAX = 1, 30

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
# TEXTCOLORS.xml — per-source flytext direction (Damage Number Colors panel)
# ============================================================================
# AoC's TextColors.xml gives each flying-text type a `direction`: 1 = float above the
# head, -1 = drop into the fixed column, 0 = join the zig-zag stack. The colors panel
# edits it per source alongside the color; these two group lists back its macro
# checkboxes ("Group my resource numbers" / "Send incoming numbers to the fixed column"),
# which flip a whole group at once.
RESOURCE_LOSS_TYPES = (
    'stamina_lost', 'mana_lost', 'stamina_loss_critical', 'mana_loss_critical',
)

# The "self" side of the color catalog's paired groups (Attacks / Spells / Combos / Heals)
# — numbers shown over your own avatar. Kept in step with damageinfo_settings.PAIRED_GROUPS
# by test_damageinfo_settings.
INCOMING_DAMAGE_TYPES = (
    'self_attacked', 'self_attacked_unshielded', 'self_attacked_critical',
    'self_attacked_environment', 'self_dodged',
    'self_attacked_spell', 'self_attacked_spell_critical',
    'self_attacked_combo', 'self_attacked_combo_critical', 'self_combo_name',
    'self_healed', 'self_healed_critical',
)

_DIRECTION_ATTR_RE = re.compile(r'(\bdirection\s*=\s*["\'])(-?\d+)(["\'])')


def _elem_re(name):
    return re.compile(rf'<[^>]*\bname\s*=\s*["\']{re.escape(name)}["\'][^>]*>')


def read_source_direction(xml_text, name):
    """Return the ``direction`` of the ``name="<name>"`` flytext element as a bare string
    (``'1'`` / ``'-1'`` / ``'0'``), or None if the element or its direction attr is absent.
    Element-scoped like :func:`read_source_color` (any attribute order, single- or
    multi-line)."""
    m = _elem_re(name).search(xml_text)
    if not m:
        return None
    d = _DIRECTION_ATTR_RE.search(m.group(0))
    return d.group(2) if d else None


def set_source_direction(xml_text, name, value):
    """Rewrite the ``direction`` attr of the ``name="<name>"`` flytext element to ``value``
    (1 = above the head, -1 = fixed column, 0 = zig-zag stack), preserving all other bytes.

    Unlike :func:`set_source_color`, a missing attribute is *injected* before the element's
    closing bracket: every flytext type has a direction whether or not the source spelled it
    out, and the game reads the absent case as its own default — so a user picking a
    direction for such a source must be able to write one. Returns ``(new_text, changed)``;
    ``changed`` is False when the element is missing or already carries that direction.
    """
    m = _elem_re(name).search(xml_text)
    if not m:
        return xml_text, False
    elem = m.group(0)
    new_elem, n = _DIRECTION_ATTR_RE.subn(rf'\g<1>{int(value)}\g<3>', elem)
    if not n:
        close = re.search(r'\s*/?>$', elem)
        assert close is not None, "_elem_re matches only up to a closing bracket"
        new_elem = elem[:close.start()] + f' direction="{int(value)}"' + close.group(0)
    if new_elem == elem:
        return xml_text, False
    return xml_text[:m.start()] + new_elem + xml_text[m.end():], True


# ============================================================================
# TEXTCOLORS.xml — per-source flytext color (Damage Numbers color editor)
# ============================================================================
# Each flytext type also carries a `color="0xRRGGBB"`. The color editor reads these to
# seed its swatches and writes the user's picks back. Element-scoped like the direction
# flip (find the element by name, rewrite only its color attr) so every other byte is
# preserved.
_COLOR_ATTR_RE = re.compile(r'(\bcolor\s*=\s*["\'])(?:0x|#)?([0-9A-Fa-f]{6})(["\'])')


def read_source_color(xml_text, name):
    """Return the bare ``RRGGBB`` (upper-case) of the ``name="<name>"`` flytext element,
    or None if the element or its color attr is absent. Accepts ``0x``/``#``/bare hex."""
    m = _elem_re(name).search(xml_text)
    if not m:
        return None
    c = _COLOR_ATTR_RE.search(m.group(0))
    return c.group(2).upper() if c else None


def set_source_color(xml_text, name, hex6):
    """Rewrite the ``color`` attr of the ``name="<name>"`` flytext element to
    ``0x<HEX6>`` (AoC's format), preserving all other bytes. ``hex6`` is bare 6-hex
    (``0x``/``#`` accepted and stripped). Returns ``(new_text, changed)``; ``changed`` is
    False when the element/color attr is missing or already equal."""
    clean = hex6.strip().lstrip('#')
    if clean[:2].lower() == '0x':
        clean = clean[2:]
    clean = clean.upper()
    m = _elem_re(name).search(xml_text)
    if not m:
        return xml_text, False
    new_elem, n = _COLOR_ATTR_RE.subn(rf'\g<1>0x{clean}\g<3>', m.group(0))
    if not n or new_elem == m.group(0):
        return xml_text, False
    return xml_text[:m.start()] + new_elem + xml_text[m.end():], True


# ============================================================================
# buff_bars — sparse PATCH-lane overrides (one sub-section per BUFF_FILES label)
# ============================================================================
def _validate_buff_bars_overrides(value: Any) -> dict[str, Any]:
    """Sparse per-field overrides for one <BuffListView> file — unknown keys
    drop, each present field is clamped/coerced independently."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    if 'icon_size' in value:
        n = _maybe_int(value['icon_size'])
        if n is not None:
            out['icon_size'] = max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, n))
    if 'icon_spacing' in value:
        n = _maybe_int(value['icon_spacing'])
        if n is not None:
            out['icon_spacing'] = max(SPACING_MIN, min(SPACING_MAX, n))
    if 'max_columns' in value:
        n = _maybe_int(value['max_columns'])
        if n is not None:
            out['max_columns'] = max(COLS_MIN, min(COLS_MAX, n))
    if 'filter' in value and value['filter'] in (FILTER_FRIENDLY, FILTER_HOSTILE, FILTER_BOTH):
        out['filter'] = value['filter']
    if 'enabled' in value:
        out['enabled'] = bool(value['enabled'])
    return out


_BUFF_BARS_SCHEMA = Schema('', 1, {
    label: Field({}, validate=_validate_buff_bars_overrides)
    for label, _relpath in BUFF_FILES
})

# The Default Buff Bars editor's slice of the profile document — sparse:
# `{}` default, one sub-dict per file label, absent field = "no opinion" (the
# editor shows whatever the file already says). PATCH lane: written to game
# XML only on explicit Apply, never on profile switch. Registered by app.py.
PROFILE_SECTION = ProfileSectionSpec('buff_bars', _BUFF_BARS_SCHEMA, LANE_PATCH, sparse=True)
