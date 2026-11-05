"""Tests for `swf_font` — setting KazBars.swf and DamageInfo.swf in another
face, as pure functions of bytes.

`splice` runs against the real `base.swf` and the nineteen baked blobs (each
spliced body pinned by the SHA-256 the font baking recorded, so a regenerated
blob has to come with new hashes), and against small synthetic SWFs for the
rules the real base cannot show. The game-font swaps run against `base.swf`,
AoC's own `DamageInfo.swf` and a baked blob.

Run: `pytest tests/test_swf_font.py` (from repo root).
"""

import hashlib
import struct
import zlib

import pytest

from as2c.swf import Movie
from kazbars import overlay
from kazbars.paths import ASSETS, KAZBARS_ASSETS
from kazbars.swf_font import (
    DEFINE_FONT3,
    DEFINE_FONT_NAME,
    DN_DEFAULT_FONT,
    DN_FONTS,
    EXPORT_ASSETS,
    IMPORT_ASSETS,
    IMPORT_ASSETS2,
    SwfFontError,
    _free_id,
    _parse_import,
    dn_scale,
    font_id,
    font_tags,
    import_game_font,
    records,
    set_damage_font,
    splice,
)

BODY_SHA256 = {
    "roboto": "2b6b4190845577a7f2b412cbcf1419eeb82ec2c0d1bbb34b5bf90733f1af8e6e",
    "inter": "e873e5bf3a42cb68a99df65ffba387bd97a1e3350fcc7e96dce0e6cd7489adbd",
    "noto-sans": "b96810a9e774187bc8c9733a4e0bcf67428fff56c7aeda4c13507634c31df804",
    "source-sans-3": "35ead7e928c0ca22568ce14b84155d3413a8e907fb22c7ef9b433e12f6c8c7f0",
    "pt-sans": "36a294e0655622fabbe3b13e3ebdb28f5dccce345c0d577b816e54d2f8c980d6",
    "fira-sans": "5c002cc602a88778961935accbb910a5fcc1f1c47194c2c01fe59e3739995a53",
    "barlow-semi-condensed": "61e5e907528be631ed835edecbe9a8e6834424a02a6f02fc2eb2b1099da75d24",
    "exo-2": "e6462797a89c9abcccf33626ecfe3816651965d8edd6383af4d5314039b8f6db",
    "alegreya-sans": "bfe19cead5275c421f25ebb5ef2b623b2d6655ceb6e6c169484a4c82d255b45d",
    "gg": "2214e722e7f9f85f9a2c8655fe14f6561484a6fe5712862aad4d60fa45490d77",
    "gg-comic": "b28cfda163dd614da094c52c9b20a626235c75806b15ee03f22710c2161412dc",
    "bangers": "a399d67835a652a366cc55da6dde52abdbda8328a032092a484cd5480fa41827",
    "lilita-one": "bd0ff053b3c4c9e58b7d0f986e58ea692ef5b9ac32e96573513c3bce1210c3cd",
    "rubik-black": "acbc570a047caa085001a160ba8e42dea9e54f2bb9c3d2ab5661ae4bf3853c28",
    "bungee": "e14f6955e6a62f8bf9c9cfb97f415536b65755be1425d31ad7aa58986d635858",
    "changa-one": "e58cc36a60eace4439b1218ecaa7918901cf01eb68a15eb3c43003465b8a63e9",
    "cinzel-decorative-black": "56f1f9a3c9d93ff52e478b3febb87404cf266dea4aa8f6620c21af0423abb63b",
    "alfa-slab-one": "4fb61ab7951bbdd99331b6c125face6f70fac2ba081661dd64472bcec121d6e2",
    "bevan": "b301911a7830d80ad60152701e6bb19cf5cd58369b2344ba6e3d255a0886d986",
}


def _base():
    return (KAZBARS_ASSETS / "base.swf").read_bytes()


def _blob(slug):
    return (KAZBARS_ASSETS / "fonts" / f"{slug}.bin").read_bytes()


def _damage_info():
    return (ASSETS / "damageinfo" / "DamageInfo.swf").read_bytes()


def _body_of(swf):
    """A SWF's body, decompressed on its own terms, after checking the header
    restates the file length."""
    body = zlib.decompress(swf[8:]) if swf[:3] == b"CWS" else swf[8:]
    assert swf[:3] in (b"CWS", b"FWS")
    assert struct.unpack_from("<I", swf, 4)[0] == 8 + len(body), "the file length is restated"
    return body


def _walk(stream, start):
    """A tag stream from `start` as (code, the record's exact bytes)."""
    out, pos = [], start
    while pos < len(stream):
        word = struct.unpack_from("<H", stream, pos)[0]
        header, length = (6, struct.unpack_from("<I", stream, pos + 2)[0]) \
            if word & 0x3F == 0x3F else (2, word & 0x3F)
        out.append((word >> 6, stream[pos:pos + header + length]))
        pos += header + length
    return out


def _tags_of(swf):
    body = _body_of(swf)
    return _walk(body, (5 + 4 * (body[0] >> 3) + 7) // 8 + 4)


def _rid(raw):
    header = 6 if raw[0] & 0x3F == 0x3F else 2
    return struct.unpack_from("<H", raw, header)[0] if len(raw) >= header + 2 else None


def _record(code, body):
    return struct.pack("<H", (code << 6) | len(body)) + body


def _font(code, fid, fill):
    return _record(code, struct.pack("<H", fid) + bytes([fill, fill]))


def _fws(tags):
    body = bytes([0x00, 0x00, 0x0C, 0x01, 0x00]) + b"".join(tags) + b"\0\0"
    return b"FWS\x08" + struct.pack("<I", 8 + len(body)) + body


# --------------------------------------------------------------------------
# splice
# --------------------------------------------------------------------------


def test_every_baked_face_splices_into_the_base_to_its_pinned_hash():
    base = _base()
    assert sorted(BODY_SHA256) == sorted(p.stem for p in (KAZBARS_ASSETS / "fonts").glob("*.bin"))
    for slug, want in BODY_SHA256.items():
        out = splice(base, _blob(slug))
        assert out[:3] == b"CWS" and out[3] == base[3], slug
        assert hashlib.sha256(_body_of(out)).hexdigest() == want, slug


def test_only_the_two_faces_and_their_zones_change():
    base = _base()
    before = _tags_of(base)
    for slug in BODY_SHA256:
        blob = _blob(slug)
        new = _walk(blob, 0)
        assert [code for code, _ in new] == [75, 88, 75, 88], slug
        want = []
        for code, raw in before:
            if code == 73 and _rid(raw) in (1, 2):
                continue
            if code in (75, 88):
                want.append(next((c, r) for c, r in new if c == code and _rid(r) == _rid(raw)))
            else:
                want.append((code, raw))
        assert len(want) == len(before) - 2, slug
        assert _tags_of(splice(base, blob)) == want, slug
        assert font_tags(splice(base, blob)) == blob, slug


def test_the_bases_own_faces_spliced_back_in_change_nothing():
    base = _base()
    own = b"".join(raw for code, raw in _tags_of(base)
                   if code in (73, 75, 88) and _rid(raw) in (1, 2))
    assert len(_walk(own, 0)) == 6
    assert _body_of(splice(base, own)) == _body_of(base)


def test_zones_of_a_replaced_font_go_other_zones_stay():
    other_zones = _font(73, 7, 9)
    export = _record(56, bytes([1, 0, 1, 0, 2, 0, ord("x"), 0]))
    show = _record(1, b"")
    base = _fws([_font(75, 1, 1), _font(73, 1, 1), _font(88, 1, 1),
                 _font(75, 2, 1), _font(73, 2, 1), _font(88, 2, 1), other_zones, export, show])
    end = (0, b"\0\0")
    new = [_font(75, 1, 2), _font(88, 1, 2), _font(75, 2, 2), _font(88, 2, 2)]
    out = splice(base, b"".join(new))
    assert _tags_of(out) == [(75, new[0]), (88, new[1]), (75, new[2]), (88, new[3]),
                             (73, other_zones), (56, export), (1, show), end]
    assert out[:3] == b"FWS", "an uncompressed base stays uncompressed"
    zoned = [_font(75, 1, 3), _font(73, 1, 3), _font(88, 1, 3), _font(75, 2, 3), _font(88, 2, 3)]
    assert _tags_of(splice(base, b"".join(zoned))) == [
        (75, zoned[0]), (73, zoned[1]), (88, zoned[2]), (75, zoned[3]), (88, zoned[4]),
        (73, other_zones), (56, export), (1, show), end]


def test_a_blob_missing_a_record_is_refused_and_says_which():
    base, recs = _base(), [raw for _, raw in _walk(_blob("roboto"), 0)]
    for skip, (tag, fid) in enumerate([("DefineFont3", 1), ("DefineFontName", 1),
                                       ("DefineFont3", 2), ("DefineFontName", 2)]):
        partial = b"".join(r for i, r in enumerate(recs) if i != skip)
        with pytest.raises(SwfFontError, match=f"^the font data has no {tag} id {fid}$"):
            splice(base, partial)
    with pytest.raises(SwfFontError, match="no DefineFont3 id 1"):
        splice(base, b"")


def test_a_base_without_the_faces_is_refused_and_says_which():
    blob = b"".join([_font(75, 1, 2), _font(88, 1, 2), _font(75, 2, 2), _font(88, 2, 2)])
    show = _record(1, b"")
    with pytest.raises(SwfFontError, match="has no DefineFont3 id 1 to replace"):
        splice(_fws([show]), blob)
    with pytest.raises(SwfFontError, match=r"^the base SWF has no DefineFont3 id 2 to replace$"):
        splice(_fws([_font(75, 1, 1), _font(88, 1, 1), show]), blob)
    with pytest.raises(SwfFontError, match="has no DefineFontName id 2 to replace"):
        splice(_fws([_font(75, 1, 1), _font(88, 1, 1), _font(75, 2, 1), show]), blob)


def test_every_cut_of_a_blob_and_every_odd_blob_is_an_error():
    base, whole = _base(), _blob("roboto")
    for cut in range(len(whole)):
        with pytest.raises(SwfFontError):
            splice(base, whole[:cut])

    def long(code, length):
        return struct.pack("<HI", (code << 6) | 0x3F, length)

    for _what, data in (("noise", b"\xff" * 64), ("an End tag", b"\0\0"),
                       ("a ShowFrame", _record(1, b"")), ("no id", _record(75, b"")),
                       ("half an id", _record(75, b"\x01")),
                       ("a tag claiming 4 GB", long(75, 0xFFFFFFFF)),
                       ("a long header and no body", long(75, 10)),
                       ("the same face twice", _font(75, 1, 1) + _font(75, 1, 2))):
        with pytest.raises(SwfFontError, match="malformed"):
            splice(base, data)


def test_a_malformed_base_is_an_error():
    blob, real = _blob("roboto"), _base()
    faces = [_font(75, 1, 1), _font(88, 1, 1), _font(75, 2, 1), _font(88, 2, 1)]

    def restamp(swf):
        return swf[:4] + struct.pack("<I", len(swf)) + swf[8:]

    wrong_stamp = real[:4] + bytes([real[4] ^ 1]) + real[5:]
    padded = restamp(_fws(faces) + b"junk")
    unterminated = restamp(_fws(faces)[:-2])
    for _what, data in (("empty", b""), ("three bytes", b"CWS"), ("not a SWF", b"GIF89a...."),
                       ("LZMA", b"ZWS    "), ("header only", b"FWS   "),
                       ("not zlib", b"CWS@   " + bytes([0xDE, 0xAD, 0xBE, 0xEF, 1, 2])),
                       ("a wrong stamped length", wrong_stamp), ("padded", padded),
                       ("unterminated", unterminated)):
        with pytest.raises(SwfFontError, match="cannot be used"):
            splice(data, blob)
    for cut in range(8, len(real), 1601):
        with pytest.raises(SwfFontError):
            splice(real[:cut], blob)


def test_records_reads_the_four_records_in_order():
    recs = records(_blob("inter"))
    assert [(r.code, font_id(r)) for r in recs] == [(75, 1), (88, 1), (75, 2), (88, 2)]


# --------------------------------------------------------------------------
# The game's fonts
# --------------------------------------------------------------------------


def _imports(swf):
    out = []
    for t in Movie.from_bytes(swf).tags:
        if t.code in (IMPORT_ASSETS, IMPORT_ASSETS2):
            url, _, entries = _parse_import(t)
            out.append((url, [(cid, name) for cid, name in entries]))
    return out


def _fonts(swf):
    return [(t.code, font_id(t)) for t in Movie.from_bytes(swf).tags if t.code in (73, 75, 88)]


def test_verdana_imports_the_games_font_in_place_of_both_arials():
    base = _base()
    out = import_game_font(base)
    assert _fonts(out) == []
    assert _imports(out) == [(b"gfxfontlib.swf", [(1, b"_StandardFont"), (2, b"_StandardFont_bold")])]
    exported = [[cid for cid, _ in t.exports()]
                for t in Movie.from_bytes(out).tags if t.code == EXPORT_ASSETS]
    assert all(1 not in ids and 2 not in ids for ids in exported)
    assert len(Movie.from_bytes(out).tags) == len(Movie.from_bytes(base).tags) - 7
    assert len(out) < len(base) / 2, "the Arial outlines are most of base.swf"


def test_hyborian_leaves_damage_info_alone():
    di = _damage_info()
    assert _imports(di) == [(b"gfxfontlib.swf", [(1, b"_ConanFont")])]
    assert set_damage_font(di, "Hyborian", None) is di


def test_a_baked_face_replaces_the_damage_import_regular_under_its_id():
    di, blob = _damage_info(), _blob("bangers")
    out = set_damage_font(di, "Bangers", blob)
    assert _imports(out) == []
    bold = _free_id(Movie.from_bytes(di).tags)
    assert bold > 2, "DamageInfo already uses ids 1 and 2"
    assert _fonts(out) == [(DEFINE_FONT3, 1), (DEFINE_FONT_NAME, 1),
                           (DEFINE_FONT3, bold), (DEFINE_FONT_NAME, bold)]
    assert len(Movie.from_bytes(out).tags) == len(Movie.from_bytes(di).tags) + 3
    ours = [t.data[2:] for t in Movie.from_bytes(out).tags if t.code == DEFINE_FONT3]
    assert ours == [r.data[2:] for r in records(blob) if r.code == DEFINE_FONT3]


def test_bad_damage_font_input_is_an_error():
    di = _damage_info()
    with pytest.raises(SwfFontError):
        set_damage_font(di, "Bevan", None)
    with pytest.raises(SwfFontError):
        set_damage_font(di, "Bevan", b"\x01\x02\x03")
    with pytest.raises(SwfFontError):
        set_damage_font(b"not a swf", "Bevan", _blob("bevan"))
    with pytest.raises(SwfFontError):
        import_game_font(di)


def test_every_damage_face_but_hyborian_is_baked_and_shipped():
    assert DN_FONTS[0] == DN_DEFAULT_FONT == "Hyborian"
    for font in DN_FONTS[1:]:
        assert (KAZBARS_ASSETS / "fonts" / f"{overlay.font_slug(font)}.bin").is_file(), font


def test_damage_number_sizes_match_hyborian_in_5_percent_steps():
    assert (dn_scale("Hyborian"), dn_scale("GG Comic")) == (100, 100)
    for font in DN_FONTS:
        assert 100 <= dn_scale(font) <= 160 and dn_scale(font) % 5 == 0, font
    assert dn_scale("Bangers") == 155
