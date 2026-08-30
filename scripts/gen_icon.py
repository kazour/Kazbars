"""KazBars app icon — generator (repo tooling, not shipped).

Mark: a 3x3 buff grid on the app's dark plate, top row lit in the accent blue
(the "bar"). Colours are the ui_helpers.py design tokens, copied here as
literals because tests/test_design_tokens.py scans src/kazbars/ for hex
literals — which is also why this lives under scripts/. Every size is drawn on
its own pixel-snapped layout (no downscaled blur at 16-32 px), then packed into
one Windows .ico plus loose PNGs.

    python scripts/gen_icon.py  -> src/kazbars/assets/icon/KazBars.ico (the shipped asset)
                                   build/icon/png/kazbars_<size>.png, build/icon/preview.png

Deterministic per Pillow build: a rerun on unchanged tokens rewrites the .ico
byte-identical; across Pillow versions the frames stay pixel-identical while the
PNG-compressed 256 frame may differ in bytes. Only dependency: Pillow.
"""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# ---- design tokens (src/kazbars/ui_helpers.py) -------------------------------
BG = "#222222"           # TK_COLORS bg
STATUS_BG = "#1a1a1a"    # TK_COLORS status_bg (header canvas)
ACCENT = "#3498db"       # THEME_COLORS accent — the KAZBARS title glow colour

LIT = ((0, 0), (0, 1), (0, 2))   # top row

# size -> (plate margin to first cell, cell, gap, plate px used, corner radius of cells)
# 2*margin + 3*cell + 2*gap == plate. Plate < size leaves a transparent
# column/row so odd geometry can still be centred (15 in 16, 23 in 24).
LAYOUT = {
    16:  dict(m=2,  cell=3,  gap=1,  plate=15,  cr=0,    border=1),
    20:  dict(m=2,  cell=4,  gap=2,  plate=20,  cr=0,    border=1),
    24:  dict(m=2,  cell=5,  gap=2,  plate=23,  cr=1,    border=1),
    32:  dict(m=5,  cell=6,  gap=2,  plate=32,  cr=1,    border=1),
    40:  dict(m=6,  cell=8,  gap=2,  plate=40,  cr=1.5,  border=1),
    48:  dict(m=9,  cell=8,  gap=3,  plate=48,  cr=1.5,  border=1),
    64:  dict(m=13, cell=10, gap=4,  plate=64,  cr=2,    border=1),
    128: dict(m=25, cell=22, gap=6,  plate=128, cr=4,    border=1),
    256: dict(m=51, cell=42, gap=14, plate=256, cr=8,    border=1.5),
    512: dict(m=102, cell=84, gap=28, plate=512, cr=16,  border=3),
}


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def blend(fg: str, bg: str, a: int) -> tuple[int, int, int]:
    """ui_widgets.blend_alpha — fg over bg at alpha a/255."""
    f, b = hex_rgb(fg), hex_rgb(bg)
    return tuple(round(b[i] + (f[i] - b[i]) * a / 255) for i in range(3))  # type: ignore[return-value]


def rgba(rgb, a: int = 255):
    return (*rgb, a)


def _glow(shape: Image.Image, color: str, radius: float, strength: float) -> Image.Image:
    a = shape.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        a = a.point(lambda v: min(255, int(v * strength)))
    g = Image.new("RGBA", shape.size, rgba(hex_rgb(color), 0))
    g.putalpha(a)
    return g


def _scanlines(img: Image.Image, step: int, alpha: int) -> Image.Image:
    """1px dark lines every `step` px, only over the plate (app: step 3, alpha 12)."""
    lines = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(lines)
    for y in range(1, img.size[1], step):
        d.line([(0, y), (img.size[0], y)], fill=255)
    plate = img.getchannel("A").point(lambda v: alpha if v > 200 else 0)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.putalpha(ImageChops.multiply(lines, plate))
    return Image.alpha_composite(img, layer)


def render(size: int) -> Image.Image:
    """One icon frame at `size`, RGBA."""
    lay = LAYOUT[size]
    small = size <= 24
    ss = 1 if small else 8                     # supersample factor
    canvas_px = size * ss
    plate_px = lay["plate"] * ss
    off = (canvas_px - plate_px) // 2                         # centre an odd plate in the canvas
    img = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- plate: rounded square, vertical gradient #222 -> #1a1a1a, 1px border
    pr = round(plate_px * 0.22)
    if small:
        pr = 3 if size == 16 else 4
        d.rounded_rectangle([off, off, off + plate_px - 1, off + plate_px - 1], radius=pr,
                            fill=rgba(hex_rgb(STATUS_BG)), outline=(0x4a, 0x4a, 0x4a, 255))
    else:
        grad = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        top, bot = hex_rgb(BG), hex_rgb(STATUS_BG)
        for y in range(plate_px):
            t = y / max(1, plate_px - 1)
            c = tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            gd.line([(off, off + y), (off + plate_px, off + y)], fill=(*c, 255))
        mask = Image.new("L", (canvas_px, canvas_px), 0)
        ImageDraw.Draw(mask).rounded_rectangle([off, off, off + plate_px - 1, off + plate_px - 1], radius=pr, fill=255)
        img.paste(grad, (0, 0), mask)
        bw = max(1, round(lay["border"] * ss))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([off + bw / 2, off + bw / 2, off + plate_px - 1 - bw / 2, off + plate_px - 1 - bw / 2],
                            radius=pr, outline=rgba((0x3a, 0x3a, 0x3a)), width=bw)

    # --- cells
    m, cell, gap, cr = lay["m"] * ss, lay["cell"] * ss, lay["gap"] * ss, lay["cr"] * ss
    # unlit: dim accent tint. Small sizes get more contrast (fewer pixels to read).
    dim = blend(ACCENT, STATUS_BG, 115 if small else 80)
    dim_edge = blend(ACCENT, BG, 135)
    cells = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    lit = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    dc, dl = ImageDraw.Draw(cells), ImageDraw.Draw(lit)
    for r in range(3):
        for c in range(3):
            x0 = off + m + c * (cell + gap)
            y0 = off + m + r * (cell + gap)
            box = [x0, y0, x0 + cell - 1, y0 + cell - 1]
            if (r, c) in LIT:
                if small:
                    dl.rectangle(box, fill=rgba(hex_rgb(ACCENT)))
                else:
                    dl.rounded_rectangle(box, radius=cr, fill=rgba(hex_rgb(ACCENT)))
            else:
                if small:
                    dc.rectangle(box, fill=rgba(dim))
                else:
                    dc.rounded_rectangle(box, radius=cr, fill=rgba(dim), outline=rgba(dim_edge),
                                         width=max(1, round(ss * 0.9)))
    img = Image.alpha_composite(img, cells)

    if small:
        # 1px halo under the lit row — the glow that survives at 16 px.
        halo = blend(ACCENT, STATUS_BG, 70)
        x0 = y0 = off + m
        x1 = off + m + 3 * cell + 2 * gap - 1
        y1 = y0 + cell - 1
        hd = ImageDraw.Draw(img)
        hd.rectangle([x0 - 1, y0 - 1, x1 + 1, y1 + 1], outline=rgba(halo))
        # keep the gaps between lit cells dark so the three tiles stay three tiles
        img = Image.alpha_composite(img, lit)
        for c in range(1, 3):
            gx = off + m + c * (cell + gap) - gap
            hd.rectangle([gx, y0, gx + gap - 1, y1], fill=rgba(hex_rgb(STATUS_BG)))
        return img

    # --- glow (two radii: wide soft + tight hot), then the sharp row, then a hot core
    img = Image.alpha_composite(img, _glow(lit, ACCENT, canvas_px * 0.045, 0.85))
    img = Image.alpha_composite(img, _glow(lit, ACCENT, canvas_px * 0.012, 1.0))
    img = Image.alpha_composite(img, lit)
    if size >= 64:
        # phosphor bloom: a soft lighter core in each lit cell. Below 64 px it
        # collapses into a dot and the cells start reading as checkboxes.
        hot = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hot)
        inset = cell * 0.24
        for (r, c) in LIT:
            x0 = off + m + c * (cell + gap)
            y0 = off + m + r * (cell + gap)
            hd.rounded_rectangle([x0 + inset, y0 + inset, x0 + cell - inset, y0 + cell - inset],
                                 radius=cr, fill=rgba(blend("#ffffff", ACCENT, 70)))
        hot = hot.filter(ImageFilter.GaussianBlur(canvas_px * 0.02))
        img = Image.alpha_composite(img, hot)

    out = img.resize((size, size), Image.LANCZOS)
    if size >= 128:
        out = _scanlines(out, step=3 if size == 128 else 4, alpha=14)
    return out


# ---- .ico writer ----------------------------------------------------------------
# BMP (DIB) entries up to 128 px — every ICO reader (Windows, Tk, PyInstaller)
# handles those; the 256 frame is PNG-compressed, the Windows convention for
# that size (a 256 DIB alone would be 260 KB).

def _dib_entry(im: Image.Image) -> bytes:
    w, h = im.size
    px = im.convert("RGBA").tobytes()
    rows = [px[y * w * 4:(y + 1) * w * 4] for y in range(h)]
    xor = bytearray()
    for row in reversed(rows):                              # bottom-up
        for i in range(0, len(row), 4):
            r, g, b, a = row[i:i + 4]
            xor += bytes((b, g, r, a))
    mask_row_bytes = ((w + 31) // 32) * 4
    and_mask = bytearray()
    alpha = im.getchannel("A").tobytes()
    for y in reversed(range(h)):
        bits = bytearray(mask_row_bytes)
        for x in range(w):
            if alpha[y * w + x] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        and_mask += bits
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + bytes(and_mask)


def _png_entry(im: Image.Image) -> bytes:
    buf = BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def write_ico(frames: list[Image.Image], path: Path) -> None:
    frames = sorted(frames, key=lambda f: f.size[0])
    entries = []
    for f in frames:
        data = _png_entry(f) if f.size[0] >= 256 else _dib_entry(f)
        entries.append((f, data))
    offset = 6 + 16 * len(entries)
    dir_ = struct.pack("<HHH", 0, 1, len(entries))
    body = b""
    for f, data in entries:
        w = f.size[0]
        dir_ += struct.pack("<BBBBHHII", 0 if w >= 256 else w, 0 if w >= 256 else w, 0, 0, 1, 32,
                            len(data), offset + len(body))
        body += data
    path.write_bytes(dir_ + body)


# ---- preview sheet -------------------------------------------------------------
def _font(bold: bool):
    """DejaVu (Linux) or Arial (Windows) by bare name, else Pillow's bitmap default."""
    from PIL import ImageFont
    for name in (("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, 13)
        except OSError:
            continue
    return ImageFont.load_default()


def preview(frames: dict[int, Image.Image], path: Path) -> None:
    font, fontb = _font(False), _font(True)
    w, h = 900, 560
    cv = Image.new("RGBA", (w, h), (0x11, 0x11, 0x11, 255))
    d = ImageDraw.Draw(cv)

    # row 1: all sizes 1:1 on the app title-bar colour
    d.rectangle([0, 0, w, 180], fill=rgba(hex_rgb(BG)))
    d.text((12, 8), "every .ico frame, 1:1, on the app's title-bar colour", font=font,
           fill=(200, 200, 200, 255))
    x = 16
    for s in (16, 20, 24, 32, 40, 48, 64, 128):
        cv.alpha_composite(frames[s], (x, 160 - s))
        d.text((x, 164), str(s), font=font, fill=(160, 160, 160, 255))
        x += s + 22
    cv.alpha_composite(frames[256].resize((140, 140), Image.LANCZOS), (w - 160, 20))
    d.text((w - 160, 164), "256 @140", font=font, fill=(160, 160, 160, 255))

    # row 2: in-context mocks — title bar (16), Win11 dark taskbar (24), light taskbar (24)
    y = 196
    d.rectangle([0, y, w, y + 40], fill=rgba(hex_rgb(BG)))
    cv.alpha_composite(frames[16], (12, y + 12))
    d.text((36, y + 12), "KazBars — Untitled", font=font, fill=(230, 230, 230, 255))
    d.text((w - 90, y + 10), "—    ☐    ✕", font=font, fill=(200, 200, 200, 255))
    y += 52
    for bgc, label in (("#1f1f1f", "Win11 taskbar, dark"), ("#eeeeee", "Win11 taskbar, light")):
        d.rectangle([0, y, w, y + 48], fill=rgba(hex_rgb(bgc)))
        tcol = (150, 150, 150, 255) if bgc == "#1f1f1f" else (90, 90, 90, 255)
        d.text((12, y + 16), label, font=font, fill=tcol)
        cv.alpha_composite(frames[24], (400, y + 12))
        cv.alpha_composite(frames[32], (450, y + 8))
        # neighbours: generic grey tiles so the icon is judged against company
        for i in range(3):
            d.rounded_rectangle([510 + i * 44, y + 12, 510 + i * 44 + 24, y + 36], radius=5,
                                fill=(110, 110, 110, 255) if bgc == "#1f1f1f" else (170, 170, 170, 255))
        y += 56

    # row 3: pixel zooms
    y += 6
    d.text((12, y), "pixel grid ×4 — 16 / 20 / 24 / 32", font=fontb, fill=(200, 200, 200, 255))
    x = 12
    y += 22
    for s in (16, 20, 24, 32):
        z = frames[s].resize((s * 4, s * 4), Image.NEAREST)
        cv.alpha_composite(z, (x, y))
        x += s * 4 + 20
    cv.alpha_composite(frames[64].resize((128, 128), Image.NEAREST), (x + 10, y))
    d.text((x + 10, y + 132), "64 ×2", font=font, fill=(160, 160, 160, 255))
    cv.convert("RGB").save(path)


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    ico = repo / "src" / "kazbars" / "assets" / "icon" / "KazBars.ico"
    out = repo / "build" / "icon"
    (out / "png").mkdir(parents=True, exist_ok=True)
    ico.parent.mkdir(parents=True, exist_ok=True)
    frames = {s: render(s) for s in LAYOUT}
    for s, im in frames.items():
        im.save(out / "png" / f"kazbars_{s}.png", "PNG", optimize=True)
    write_ico([frames[s] for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)], ico)
    preview(frames, out / "preview.png")
    print("wrote", ico.relative_to(repo).as_posix(), "+", out.relative_to(repo).as_posix())


if __name__ == "__main__":
    main()
