"""Render a GitHub avatar as neofetch-style ASCII art (background -> spaces)."""
import io
import statistics
import urllib.request

from PIL import Image, ImageChops, ImageFilter

RAMP = " .`:-=+*cs#S"


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


def avatar_ascii(url: str, width: int = 44, height: int = 22) -> list[str]:
    img = _fetch(url)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = _background(img.convert("RGB"))
        img = Image.alpha_composite(Image.new("RGBA", img.size, bg + (255,)), img)
    img = img.convert("RGB")
    s = min(img.size)
    left, top = (img.width - s) // 2, (img.height - s) // 2
    img = img.crop((left, top, left + s, top + s))
    bg = _background(img)
    # Work at 4x cell resolution, then average down so edges survive.
    big = img.resize((width * 4, height * 4), Image.LANCZOS)
    diff = ImageChops.difference(big, Image.new("RGB", big.size, bg))
    dist = ImageChops.lighter(ImageChops.lighter(*diff.split()[:2]), diff.split()[2])
    edges = big.convert("L").filter(ImageFilter.FIND_EDGES)
    dist = dist.resize((width, height), Image.BOX)
    edges = edges.resize((width, height), Image.BOX)
    d, e = list(dist.tobytes()), list(edges.tobytes())
    peak_d, peak_e = max(max(d), 1), max(max(e), 1)
    lines = []
    for y in range(height):
        row = []
        for x in range(width):
            i = y * width + x
            v = 0.7 * d[i] / peak_d + 0.3 * e[i] / peak_e
            v = 0.0 if v < 0.12 else (v - 0.12) / 0.88
            row.append(RAMP[min(len(RAMP) - 1, round(v ** 0.8 * (len(RAMP) - 1)))])
        lines.append("".join(row).ljust(width)[:width])
    return lines


if __name__ == "__main__":
    art = avatar_ascii("https://github.com/ayushmk7.png")
    print("\n".join(art))
    assert len(art) == 22 and all(len(l) == 44 for l in art)
    assert all(32 <= ord(c) < 127 for l in art for c in l)
