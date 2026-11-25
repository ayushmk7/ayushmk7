"""Render a GitHub avatar as colored ASCII art: rows of (char, "#rrggbb"); background -> spaces."""
import io
import statistics
import urllib.request

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def _fetch(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers={"User-Agent": "ascii-avatar/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return Image.open(io.BytesIO(r.read()))


def _background(img: Image.Image) -> tuple[int, int, int]:
    w, h = img.size
    p = max(2, min(w, h) // 16)
    px = []
    for x, y in ((0, 0), (w - p, 0), (0, h - p), (w - p, h - p)):
        px += [img.getpixel((x + i, y + j)) for i in range(p) for j in range(p)]
    return tuple(int(statistics.median(c[i] for c in px)) for i in range(3))


def avatar_ascii(url: str, width: int = 64, height: int = 34, keep_background: bool = False) -> list[list[tuple[str, str]]]:
    img = _fetch(url).convert("RGBA")
    bg = _background(img.convert("RGB"))
    img = Image.alpha_composite(Image.new("RGBA", img.size, bg + (255,)), img).convert("RGB")
    s = min(img.size)
    img = img.crop(((img.width - s) // 2, (img.height - s) // 2, (img.width + s) // 2, (img.height + s) // 2))
    if not keep_background:  # zoom to subject so it fills the art area
        d = ImageChops.difference(img, Image.new("RGB", img.size, _background(img)))
        box = ImageChops.lighter(ImageChops.lighter(*d.split()[:2]), d.split()[2]).point(lambda v: 255 * (v > 40)).getbbox()
        if box:
            cx, cy, half = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, max(box[2] - box[0], box[3] - box[1]) * 0.54
            canvas = Image.new("RGB", (int(2 * half),) * 2, _background(img))
            canvas.paste(img, (int(half - cx), int(half - cy)))
            img = canvas
    img = ImageEnhance.Sharpness(ImageOps.autocontrast(img, cutoff=1)).enhance(1.6)
    bg = _background(img)
    big = img.resize((width * 4, height * 4), Image.LANCZOS)
    diff = ImageChops.difference(big, Image.new("RGB", big.size, bg))
    mask = ImageChops.lighter(ImageChops.lighter(*diff.split()[:2]), diff.split()[2]).resize((width, height), Image.BOX)
    edges = big.convert("L").filter(ImageFilter.FIND_EDGES).resize((width, height), Image.BOX)
    small = img.resize((width, height), Image.LANCZOS)
    lum = small.convert("L")
    pe = max(max(edges.tobytes()), 1)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            if not keep_background and mask.getpixel((x, y)) < 40:  # ponytail: flat-bg threshold; busy photos → keep_background
                row.append((" ", "#000000"))
                continue
            # density: brightness, but strong edges (outlines) stay dense so they read
            v = max(lum.getpixel((x, y)) / 255, edges.getpixel((x, y)) / pe)
            ch = RAMP[max(1, min(len(RAMP) - 1, round(v * (len(RAMP) - 1))))]
            r, g, b = small.getpixel((x, y))
            k = max(0, 90 - max(r, g, b))  # lift near-black so outlines stay visible on dark card
            row.append((ch, f"#{min(r + k, 255):02x}{min(g + k, 255):02x}{min(b + k, 255):02x}"))
        rows.append(row)
    return rows


if __name__ == "__main__":
    art = avatar_ascii("https://github.com/ayushmk7.png")
    print("\n".join("".join(c for c, _ in r) for r in art))
    assert len(art) == 34 and all(len(r) == 64 for r in art)
    assert all(32 <= ord(c) < 127 for r in art for c, _ in r)
