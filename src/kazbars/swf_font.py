"""KazBars — the fonts of KazBars.swf and DamageInfo.swf, as pure functions of
bytes (no Tk, no file I/O).

`base.swf` embeds two fonts, Arial (DefineFont3 id 1) and Arial Bold (id 2),
each followed by a DefineFontAlignZones and a DefineFontName, and every text
field the generated AS2 makes asks for the face `d.PF.face` names. The game's
Scaleform never falls back to a system font, so another look needs other
outlines inside the SWF:

- A baked face (`assets/kazbars/fonts/<slug>.bin`, `overlay.font_slug`): a font
  blob of exactly four tag records — DefineFont3 id 1, DefineFontName id 1,
  DefineFont3 id 2, DefineFontName id 2 — named "Arial" and "Arial Bold", so the
  AS2 stays as it is. `splice` puts them over the base's two faces, drops the
  replaced faces' align zones (they describe outlines that are gone), keeps
  every other tag byte for byte and in place, and recompresses.
- The game's own Verdana: `import_game_font` drops the two Arials (with their
  zones, names and exports) and imports `_StandardFont` / `_StandardFont_bold`
  from `gfxfontlib.swf` under their ids; the AS2 then asks for `_StandardFont`.
  Nothing of the face is copied, so its licence is never touched.
- DamageInfo.swf binds its damage text to the imported `_ConanFont` (Hyborian).
  `set_damage_font` keeps that for Hyborian and otherwise replaces the import
  with a baked face's two fonts, the regular one under the imported id and the
  bold one under a free id. `dn_scale` is how much larger a face is drawn so its
  digits read as big as Hyborian's.

Strict where a wrong input would otherwise pass quietly: a blob must hold the
four records and nothing but font tags, a base must decode and account for
every byte its header states, and every refusal is a `SwfFontError` naming the
tag at fault.
"""

import struct
import zlib

from as2c.swf import Movie, SwfError, Tag, encode_tag

from .overlay import HYBORIAN

ALIGN_ZONES = 73
DEFINE_FONT3 = 75
DEFINE_FONT_NAME = 88
EXPORT_ASSETS = 56
IMPORT_ASSETS = 57
IMPORT_ASSETS2 = 71
_FONT_TAGS = (ALIGN_ZONES, DEFINE_FONT3, DEFINE_FONT_NAME)
_TAG_NAMES = {DEFINE_FONT3: 'DefineFont3', DEFINE_FONT_NAME: 'DefineFontName',
              ALIGN_ZONES: 'DefineFontAlignZones'}

# The two faces base.swf embeds: Arial and Arial Bold.
FONT_IDS = (1, 2)

_FONT_LIB = b'gfxfontlib.swf'
_STANDARD_FONT = b'_StandardFont'
_STANDARD_FONT_BOLD = b'_StandardFont_bold'
_CONAN_FONT = b'_ConanFont'

# Tags whose body opens with the character id they define (free_id's scan).
_DEFINES = (2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37, 39, 46, 48, 60, 62,
            75, 83, 84, 87, 90, 91)

# The Damage Numbers font choices, in the dropdown's order: heavy display faces
# picked for floating numbers. Hyborian, the game's own, is the default and
# leaves DamageInfo.swf as built; every other one is embedded.
DN_FONTS = (HYBORIAN, 'GG Comic', 'Bangers', 'Lilita One', 'Rubik Black', 'Bungee',
            'Changa One', 'Cinzel Decorative Black', 'Alfa Slab One', 'Bevan')
DN_DEFAULT_FONT = HYBORIAN

# How much larger, in percent, damage numbers are drawn in a face so they read as
# big as in Hyborian: each face scaled until its bold digits are, on average, as
# wide as Hyborian's, rounded to 5 %. GG Comic stays at 100, as tried in game.
_DN_SCALES = {'Bangers': 155, 'Lilita One': 125, 'Changa One': 115,
              'Cinzel Decorative Black': 110, 'Bevan': 110, 'Alfa Slab One': 105}


class SwfFontError(ValueError):
    """A font could not be set into a SWF; the message names the tag at fault."""


def dn_scale(font: str) -> int:
    """The percent a damage-number face is drawn at (100 for Hyborian)."""
    return _DN_SCALES.get(font, 100)


def font_id(tag: Tag) -> int | None:
    """The font id a font tag's body opens with, or None when it is cut short."""
    return struct.unpack_from('<H', tag.data, 0)[0] if len(tag.data) >= 2 else None


def _blob_error(why: str) -> SwfFontError:
    return SwfFontError(f'the font data is malformed: {why}')


def _missing(where: str, tag: str, font: int) -> SwfFontError:
    if where == 'blob':
        return SwfFontError(f'the font data has no {tag} id {font}')
    return SwfFontError(f'the base SWF has no {tag} id {font} to replace')


def records(blob: bytes) -> list[Tag]:
    """The blob as a bare run of font tag records. A cut-short header or body, a
    tag that is not a font tag, two records for one tag and font, and a blob
    without the four records the swap needs are all errors."""
    out: list[Tag] = []
    pos = 0
    while pos < len(blob):
        if pos + 2 > len(blob):
            raise _blob_error(f'a tag header is cut short at byte {pos}')
        word = struct.unpack_from('<H', blob, pos)[0]
        code, short = word >> 6, word & 0x3F
        if short == 0x3F:
            if pos + 6 > len(blob):
                raise _blob_error(f'a long tag header is cut short at byte {pos}')
            header, length = 6, struct.unpack_from('<I', blob, pos + 2)[0]
        else:
            header, length = 2, short
        if code not in _FONT_TAGS:
            raise _blob_error(f'tag code {code} at byte {pos} is not a font tag')
        end = pos + header + length
        if end > len(blob):
            raise _blob_error(f'the {_TAG_NAMES[code]} tag at byte {pos} runs past the end')
        tag = Tag(code, blob[pos + header:end], header == 6)
        fid = font_id(tag)
        if fid is None:
            raise _blob_error(f'the {_TAG_NAMES[code]} tag at byte {pos} is too short to hold a font id')
        if any(r.code == code and font_id(r) == fid for r in out):
            raise _blob_error(f'two {_TAG_NAMES[code]} tags for font id {fid}')
        out.append(tag)
        pos = end
    for fid in FONT_IDS:
        for code in (DEFINE_FONT3, DEFINE_FONT_NAME):
            if not any(r.code == code and font_id(r) == fid for r in out):
                raise _missing('blob', _TAG_NAMES[code], fid)
    return out


def _movie(swf: bytes) -> Movie:
    """`swf` decoded whole: it must parse, end with an End tag, and come to
    exactly the length its header states."""
    try:
        movie = Movie.from_bytes(swf)
        stamped = struct.unpack_from('<I', swf, 4)[0]
        flat = movie.to_bytes(compressed=False)
    except (SwfError, zlib.error, struct.error, IndexError, ValueError) as e:
        raise SwfFontError(f'the base SWF cannot be used: {e}') from None
    if not movie.tags or movie.tags[-1].code != 0:
        raise SwfFontError('the base SWF cannot be used: it has no End tag')
    if len(flat) != stamped:
        raise SwfFontError(f'the base SWF cannot be used: its header states {stamped} bytes '
                           f'but its tags come to {len(flat)}')
    return movie


def splice(base: bytes, blob: bytes) -> bytes:
    """`base` (a SWF file's bytes) with the faces of `blob` in place of its
    fonts, as a SWF file of the same version and compression."""
    new = records(blob)
    movie = _movie(base)
    replaced = {font_id(r) for r in new if r.code == DEFINE_FONT3}
    used = [False] * len(new)
    kept: list[Tag] = []
    for tag in movie.tags:
        fid = font_id(tag) if tag.code in _FONT_TAGS else None
        if fid is None:
            kept.append(tag)
            continue
        i = next((i for i, r in enumerate(new) if r.code == tag.code and font_id(r) == fid), None)
        if i is not None:
            kept.append(new[i])
            used[i] = True
        elif not (tag.code == ALIGN_ZONES and fid in replaced):
            kept.append(tag)
    if not all(used):
        r = new[used.index(False)]
        raise _missing('base', _TAG_NAMES[r.code], font_id(r) or 0)
    movie.tags = kept
    return movie.to_bytes()


def font_tags(swf: bytes) -> bytes:
    """The DefineFont3 and DefineFontName records of `swf`, concatenated in
    order: for a KazBars.swf built in a baked face, that face's blob."""
    movie = Movie.from_bytes(swf)
    return b''.join(encode_tag(t) for t in movie.tags if t.code in (DEFINE_FONT3, DEFINE_FONT_NAME))


def _cstr(b: bytes, at: int) -> tuple[bytes, int]:
    end = b.index(b'\0', at)
    return b[at:end], end + 1


def _parse_import(tag: Tag) -> tuple[bytes, bytes | None, list[tuple[int, bytes]]]:
    """An ImportAssets body: source URL, ImportAssets2's two reserved bytes, and
    (character id, name) entries."""
    b = tag.data
    url, at = _cstr(b, 0)
    reserved = None
    if tag.code == IMPORT_ASSETS2:
        reserved, at = b[at:at + 2], at + 2
        if len(reserved) != 2:
            raise ValueError('cut short')
    (count,) = struct.unpack_from('<H', b, at)
    at += 2
    entries = []
    for _ in range(count):
        (cid,) = struct.unpack_from('<H', b, at)
        name, at = _cstr(b, at + 2)
        entries.append((cid, name))
    return url, reserved, entries


def _import_tag(url: bytes, reserved: bytes | None, entries: list[tuple[int, bytes]]) -> Tag:
    body = url + b'\0' + (reserved or b'') + struct.pack('<H', len(entries))
    for cid, name in entries:
        body += struct.pack('<H', cid) + name + b'\0'
    return Tag(IMPORT_ASSETS2 if reserved is not None else IMPORT_ASSETS, body)


def _export_ids(tag: Tag) -> list[int] | None:
    try:
        return [cid for cid, _ in tag.exports()]
    except (SwfError, struct.error, ValueError):
        return None


def import_game_font(base: bytes) -> bytes:
    """`base` with its two embedded Arials (and their align zones, names and
    exports) replaced by one import of the game's Verdana under the same ids."""
    movie = _movie(base)
    kept: list[Tag] = []
    at = None
    for tag in movie.tags:
        if tag.code in _FONT_TAGS:
            ours = font_id(tag) in FONT_IDS
        elif tag.code == EXPORT_ASSETS:
            ids = _export_ids(tag) or []
            ours = bool(ids) and all(i in FONT_IDS for i in ids)
        else:
            ours = False
        if ours:
            if at is None:
                at = len(kept)
        else:
            kept.append(tag)
    if at is None:
        raise _missing('base', 'DefineFont3', FONT_IDS[0])
    entries = [(FONT_IDS[0], _STANDARD_FONT), (FONT_IDS[1], _STANDARD_FONT_BOLD)]
    reserved = b'\x01\x00' if movie.version >= 8 else None
    kept.insert(at, _import_tag(_FONT_LIB, reserved, entries))
    movie.tags = kept
    return movie.to_bytes()


def _free_id(tags: list[Tag]) -> int:
    """One past the highest character id `tags` define, import or export."""
    top = 0
    for t in tags:
        if t.code in _DEFINES and len(t.data) >= 2:
            top = max(top, struct.unpack_from('<H', t.data, 0)[0])
        elif t.code in (IMPORT_ASSETS, IMPORT_ASSETS2):
            try:
                top = max([top, *(cid for cid, _ in _parse_import(t)[2])])
            except (ValueError, struct.error):
                pass
        elif t.code == EXPORT_ASSETS:
            top = max([top, *(_export_ids(t) or [])])
    return top + 1


def set_damage_font(swf: bytes, font: str, blob: bytes | None) -> bytes:
    """DamageInfo.swf (`swf`) with its damage text in `font`, a DN_FONTS name.
    `blob` is the face's font data (four records, font ids 1 and 2); Hyborian
    needs none and returns `swf` unchanged."""
    if font == HYBORIAN:
        return swf
    movie = _movie(swf)
    found = None
    for pos, tag in enumerate(movie.tags):
        if tag.code not in (IMPORT_ASSETS, IMPORT_ASSETS2):
            continue
        try:
            url, reserved, entries = _parse_import(tag)
        except (ValueError, struct.error):
            continue
        entry = next((i for i, (_, name) in enumerate(entries) if name == _CONAN_FONT), None)
        if entry is not None:
            found = (pos, url, reserved, entries, entry)
            break
    if found is None:
        raise SwfFontError('the base SWF has no import of _ConanFont to replace')
    if blob is None:
        raise _blob_error(f'{font} has no font data')
    faces = records(blob)
    pos, url, reserved, entries, entry = found
    regular = entries.pop(entry)[0]
    bold = _free_id(movie.tags)
    fonts = [Tag(r.code, struct.pack('<H', regular if font_id(r) == FONT_IDS[0] else bold) + r.data[2:])
             for r in faces if r.code in (DEFINE_FONT3, DEFINE_FONT_NAME)]
    if entries:
        movie.tags[pos:pos + 1] = [_import_tag(url, reserved, entries), *fonts]
    else:
        movie.tags[pos:pos + 1] = fonts
    return movie.to_bytes()
