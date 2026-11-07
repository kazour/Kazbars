"""KazBars — the overlay section: the base size and the font of everything
KazBars.swf draws (pure data, no Tk).

`modules.overlay = {size, font}` (BUILD lane). `size` is the base size every
module's own `scale` multiplies (`overlay_size`); `font` is the face every text
field in game asks for. Arial is the face `base.swf` embeds; Verdana is the
game's own font, imported at run time (`swf_font.import_game_font`); every
other face is baked into SWF font tags shipped under
`assets/kazbars/fonts/<slug>.bin` and spliced over the Arials at build time.
"""

from .profile_document import LANE_BUILD
from .profile_document import SectionSpec as ProfileSectionSpec
from .settings_core import Field, Schema, validate_all

# The base size's choices as the toolbar dropdown rows: (size, label), the
# label naming the screen a size is meant for where there is one.
SIZE_CHOICES: tuple[tuple[int, str], ...] = (
    (10, '10 · Compact'),
    (11, '11'),
    (12, '12 · Default (1080p)'),
    (13, '13'),
    (14, '14 · Large (1080p)'),
    (16, '16 · 1440p'),
    (18, '18'),
    (20, '20 · Large (1440p)'),
    (24, '24 · 4K'),
)
DEFAULT_SIZE = 12

VERDANA = 'Verdana'
HYBORIAN = 'Hyborian'
DEFAULT_FONT = 'Arial'

# The Font dropdown, in order: Arial, the game's own Verdana, then the baked
# faces. A stored name that is not on this list reads as Arial.
FONT_CHOICES: tuple[str, ...] = (
    'Arial', VERDANA, 'GG', 'Roboto', 'Inter', 'Noto Sans', 'Source Sans 3',
    'PT Sans', 'Fira Sans', 'Barlow Semi Condensed', 'Exo 2', 'Alegreya Sans',
)

# The file stem of a face's baked tags (`fonts/<slug>.bin`, its licence in
# `fonts/LICENSES/<slug>.txt`). Arial (already in base.swf), Verdana and
# Hyborian (both the game's own) have none.
_SLUGS = {
    'Roboto': 'roboto',
    'Inter': 'inter',
    'Noto Sans': 'noto-sans',
    'Source Sans 3': 'source-sans-3',
    'PT Sans': 'pt-sans',
    'Fira Sans': 'fira-sans',
    'Barlow Semi Condensed': 'barlow-semi-condensed',
    'Exo 2': 'exo-2',
    'Alegreya Sans': 'alegreya-sans',
    'GG': 'gg',
    # Damage Numbers only (swf_font.DN_FONTS).
    'GG Comic': 'gg-comic',
    'Bangers': 'bangers',
    'Lilita One': 'lilita-one',
    'Rubik Black': 'rubik-black',
    'Bungee': 'bungee',
    'Changa One': 'changa-one',
    'Cinzel Decorative Black': 'cinzel-decorative-black',
    'Alfa Slab One': 'alfa-slab-one',
    'Bevan': 'bevan',
}


def font_slug(name: str) -> str | None:
    return _SLUGS.get(name)


def font_label(name: str) -> str:
    """A font name as a dropdown shows it: the game's own faces say so."""
    if name == VERDANA:
        return 'Verdana (game font)'
    if name == HYBORIAN:
        return 'Hyborian (game font)'
    return name


def as2_face(font: str) -> str:
    """The face name the AS2 sets on every text field (`d.PF.face`)."""
    return '_StandardFont' if font == VERDANA else 'Arial'


def size_for_height(height: int) -> int:
    """The base size a game resolution starts on: 12 up to 1080 px tall, 16
    up to 1440, 24 above (48 / 64 / 96 px icons at scale 100)."""
    if height <= 1080:
        return 12
    if height <= 1440:
        return 16
    return 24


_SCHEMA = Schema('', 1, {
    'size': Field(DEFAULT_SIZE, kind='int', choices=tuple(s for s, _ in SIZE_CHOICES)),
    'font': Field(DEFAULT_FONT, choices=FONT_CHOICES),
})


def validate_config(config) -> dict:
    """The section with exactly its two keys: absent or non-dict → 12 / Arial."""
    return validate_all(_SCHEMA, config)

# Registered by app.py at startup.
PROFILE_SECTION = ProfileSectionSpec('overlay', _SCHEMA, LANE_BUILD)
