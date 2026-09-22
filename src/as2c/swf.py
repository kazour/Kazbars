"""SWF container I/O — just enough to read a movie, edit its tag list, and write it back.

Only the tag types the compiler injects or must recognise are decoded; every other tag is
carried through as opaque bytes, so a round-trip never disturbs authored content (shapes,
fonts, sprites, linkage). Format reference: Adobe "SWF File Format Specification" v19.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

# Tag codes used by the compiler / inject path.
TAG_END = 0
TAG_SHOW_FRAME = 1
TAG_SET_BACKGROUND_COLOR = 9
TAG_DO_ACTION = 12
TAG_DEFINE_SPRITE = 39
TAG_FRAME_LABEL = 43
TAG_EXPORT_ASSETS = 56
TAG_DO_INIT_ACTION = 59
TAG_FILE_ATTRIBUTES = 69

TAG_NAMES = {
    0: 'End', 1: 'ShowFrame', 2: 'DefineShape', 9: 'SetBackgroundColor', 12: 'DoAction',
    32: 'DefineShape3', 33: 'DefineText2', 36: 'DefineBitsLossless2', 37: 'DefineEditText',
    39: 'DefineSprite', 43: 'FrameLabel', 56: 'ExportAssets', 57: 'ImportAssets',
    59: 'DoInitAction', 69: 'FileAttributes', 71: 'ImportAssets2', 73: 'DefineFontAlignZones',
    74: 'CSMTextSettings', 75: 'DefineFont3', 77: 'Metadata', 83: 'DefineShape4',
    88: 'DefineFontName',
}


class SwfError(Exception):
    pass


@dataclass
class Tag:
    code: int
    data: bytes
    long: bool = False  # header written in the 6-byte long form (kept for byte-faithful round-trips)

    @property
    def name(self) -> str:
        return TAG_NAMES.get(self.code, f'Tag{self.code}')

    # -- typed views over the tags the compiler cares about ------------------------------
    def sprite_id(self) -> int:
        """Character id for DefineSprite / DoInitAction."""
        if self.code not in (TAG_DEFINE_SPRITE, TAG_DO_INIT_ACTION):
            raise SwfError(f'{self.name} has no sprite id')
        return struct.unpack_from('<H', self.data, 0)[0]

    def actions(self) -> bytes:
        """Raw AVM1 action bytes of a DoAction / DoInitAction tag."""
        if self.code == TAG_DO_ACTION:
            return self.data
        if self.code == TAG_DO_INIT_ACTION:
            return self.data[2:]
        raise SwfError(f'{self.name} carries no actions')

    def exports(self) -> list[tuple[int, str]]:
        """(character id, linkage name) pairs of an ExportAssets tag."""
        if self.code != TAG_EXPORT_ASSETS:
            raise SwfError(f'{self.name} is not ExportAssets')
        (n,) = struct.unpack_from('<H', self.data, 0)
        pos = 2
        out = []
        for _ in range(n):
            (cid,) = struct.unpack_from('<H', self.data, pos)
            pos += 2
            end = self.data.index(b'\0', pos)
            out.append((cid, self.data[pos:end].decode('utf-8', 'replace')))
            pos = end + 1
        return out


def define_sprite(sprite_id: int, frame_count: int = 0, body: bytes = b'') -> Tag:
    """An (empty) DefineSprite: the container mtasc gives every compiled class."""
    return Tag(TAG_DEFINE_SPRITE, struct.pack('<HH', sprite_id, frame_count) + body + b'\0\0')


def export_assets(entries: list[tuple[int, str]]) -> Tag:
    data = struct.pack('<H', len(entries))
    for cid, name in entries:
        data += struct.pack('<H', cid) + name.encode('utf-8') + b'\0'
    return Tag(TAG_EXPORT_ASSETS, data)


def do_init_action(sprite_id: int, actions: bytes) -> Tag:
    return Tag(TAG_DO_INIT_ACTION, struct.pack('<H', sprite_id) + actions)


def do_action(actions: bytes) -> Tag:
    return Tag(TAG_DO_ACTION, actions)


@dataclass
class Movie:
    version: int
    compressed: bool
    frame_size: bytes  # the raw RECT bits, kept verbatim
    frame_rate: int  # 8.8 fixed, raw u16
    frame_count: int
    tags: list[Tag] = field(default_factory=list)

    # -- parsing --------------------------------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes) -> Movie:
        sig = data[:3]
        if sig not in (b'FWS', b'CWS'):
            raise SwfError(f'not an FWS/CWS movie (signature {sig!r})')
        version = data[3]
        (total_len,) = struct.unpack_from('<I', data, 4)
        body = data[8:]
        if sig == b'CWS':
            body = zlib.decompress(body)
        if len(body) + 8 != total_len:
            # Tolerate — some writers stamp a wrong length — but never silently truncate.
            body = body[: max(0, total_len - 8)] if len(body) + 8 > total_len else body
        nbits = body[0] >> 3
        rect_len = (5 + 4 * nbits + 7) // 8
        frame_size = body[:rect_len]
        frame_rate, frame_count = struct.unpack_from('<HH', body, rect_len)
        pos = rect_len + 4
        tags: list[Tag] = []
        while pos < len(body):
            (hdr,) = struct.unpack_from('<H', body, pos)
            pos += 2
            code, length = hdr >> 6, hdr & 0x3F
            long = length == 0x3F
            if long:
                (length,) = struct.unpack_from('<I', body, pos)
                pos += 4
            tags.append(Tag(code, body[pos : pos + length], long))
            pos += length
            if code == TAG_END:
                break
        return cls(version, sig == b'CWS', frame_size, frame_rate, frame_count, tags)

    @classmethod
    def load(cls, path) -> Movie:
        with open(path, 'rb') as f:
            return cls.from_bytes(f.read())

    # -- serialisation --------------------------------------------------------------------
    def to_bytes(self, compressed: bool | None = None) -> bytes:
        if compressed is None:
            compressed = self.compressed
        body = bytearray(self.frame_size)
        body += struct.pack('<HH', self.frame_rate, self.frame_count)
        for tag in self.tags:
            body += encode_tag(tag)
        total = len(body) + 8
        payload = zlib.compress(bytes(body), 9) if compressed else bytes(body)
        return (b'CWS' if compressed else b'FWS') + bytes([self.version]) + struct.pack('<I', total) + payload

    def save(self, path, compressed: bool | None = None) -> None:
        with open(path, 'wb') as f:
            f.write(self.to_bytes(compressed))

    # -- queries --------------------------------------------------------------------------
    def find_tags(self, code: int) -> list[Tag]:
        return [t for t in self.tags if t.code == code]

    def max_character_id(self) -> int:
        """Highest character id in use; DefineSprite ids plus anything exported."""
        best = 0
        for t in self.tags:
            if t.code == TAG_DEFINE_SPRITE:
                best = max(best, t.sprite_id())
            elif 0 < t.code and t.code in DEFINING_TAGS:
                best = max(best, struct.unpack_from('<H', t.data, 0)[0])
        return best

    def class_exports(self) -> dict[str, int]:
        """`__Packages.<path>` linkage name → character id, for every compiled class present."""
        out: dict[str, int] = {}
        for t in self.find_tags(TAG_EXPORT_ASSETS):
            for cid, name in t.exports():
                if name.startswith('__Packages.'):
                    out[name[len('__Packages.') :]] = cid
        return out


# Tags whose data starts with a u16 character id (spec: all Define* tags).
DEFINING_TAGS = frozenset({
    2, 6, 7, 10, 11, 13, 14, 20, 21, 22, 32, 34, 35, 36, 37, 39, 46, 48, 60, 73, 75, 83, 84,
    87, 90, 91,
})


def encode_tag(tag: Tag) -> bytes:
    length = len(tag.data)
    if tag.long or length >= 0x3F:
        return struct.pack('<HI', (tag.code << 6) | 0x3F, length) + tag.data
    return struct.pack('<H', (tag.code << 6) | length) + tag.data


def new_movie(version: int = 8, width: int = 100, height: int = 100, fps: int = 30,
              background: int | None = 0xFFFFFF) -> Movie:
    """A minimal one-frame movie — the synthetic base the test fixtures inject into."""
    # RECT in twips: 5-bit nbits then xmin,xmax,ymin,ymax.
    xmax, ymax = width * 20, height * 20
    nbits = max(xmax, ymax).bit_length() + 1
    bits = f'{nbits:05b}' + f'{0:0{nbits}b}' + f'{xmax:0{nbits}b}' + f'{0:0{nbits}b}' + f'{ymax:0{nbits}b}'
    bits += '0' * (-len(bits) % 8)
    rect = int(bits, 2).to_bytes(len(bits) // 8, 'big')
    tags = []
    if background is not None:
        tags.append(Tag(TAG_SET_BACKGROUND_COLOR, bytes([(background >> 16) & 255, (background >> 8) & 255, background & 255])))
    tags.append(Tag(TAG_SHOW_FRAME, b''))
    tags.append(Tag(TAG_END, b''))
    return Movie(version, False, rect, fps << 8, 1, tags)
