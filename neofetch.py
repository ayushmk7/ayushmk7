"""Render config.toml + live GitHub stats + ASCII avatar into neofetch.svg and neofetch.txt."""
import os, subprocess, tomllib
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from ascii_art import avatar_ascii
from stats import fetch_stats

FS, CW, LH, PAD = 14, 8.4, 19, 28  # font size, char width, line height, padding (px)
AFS = 8  # art font size in the SVG (smaller = more detail)
GAP = 4  # chars between art and panel


def uptime(created: str) -> str:
    c = datetime.fromisoformat(created.replace("Z", "+00:00"))
    n = datetime.now(timezone.utc)
    months = (n.year - c.year) * 12 + n.month - c.month - (n.day < c.day)
    y, m = divmod(months, 12)
    part = lambda v, u: f"{v} {u}{'s' * (v != 1)}"
    return ", ".join(p for p in (y and part(y, "year"), m and part(m, "month")) if p) or "new"


def row(key, val, w):
    val = val[: max(w - len(key) - 6, 1)]
    return [(". ", "dim"), (key + ":", "key"), (" " + "." * (w - 5 - len(key) - len(val)) + " ", "dim"), (val, "value")]


def panel(cfg, live):
    w = cfg["panel_width"]
    head = f"{cfg['user']}@{cfg['host']}"
    lines = [[(head, "key b"), (" " + "─" * (w - len(head) - 1), "dim")]]
    for s in cfg["sections"]:
        if "title" in s:
            lines += [[], [("─ ", "dim"), (s["title"], "key b"), (" " + "─" * (w - len(s["title"]) - 3), "dim")]]
        rows = [(k, v.format_map(live)) for k, v in s["rows"]]
        if s.get("columns", 1) == 2:
            lw = (w - 3) // 2
            for i in range(0, len(rows), 2):
                right = row(*rows[i + 1], w - 3 - lw) if i + 1 < len(rows) else []
                lines.append(row(*rows[i], lw) + [(" | ", "dim")] + right)
        else:
            lines += [row(k, v, w) for k, v in rows]
    return lines


def runs(row, mono=None):
    """[(char, hex)] -> merged [(text, hex)] segments; spaces join any run."""
    out = []
    for ch, col in row:
        col = mono or col
        if out and (ch == " " or out[-1][1] == col):
            out[-1] = (out[-1][0] + ch, out[-1][1])
        else:
            out.append((ch, col))
    return out


def compose(cfg, left, aw, pan, rows=0):
    n = max(len(left), len(pan), rows)
    left = [[]] * ((n - len(left)) // 2) + left
    pan = [[]] * ((n - len(pan)) // 2) + pan
    body = []
    for i in range(n):
        l = left[i] if i < len(left) else []
        pad = aw + GAP - sum(len(t) for t, _ in l)
        body.append(l + [(" " * pad, "dim")] + (pan[i] if i < len(pan) else []))
    prompt = [(f"{cfg['user']}@{cfg['host']}", "key b"), (":~$ ", "value")]
    return [prompt + [(cfg["command"], "value cmd")], []] + body + [[], prompt + [("█", "cursor")]]


def svg(cfg, lines, art, art_top):
    fill = lambda k: f'fill="{k}"' if k.startswith("#") else f'class="{k}"'
    c = cfg["colors"]
    cols = max(sum(len(t) for t, _ in l) for l in lines)
    W, H = PAD * 2 + cols * CW, PAD * 2 + len(lines) * LH
    plen = len(cfg["user"] + cfg["host"]) + 5
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H}" viewBox="0 0 {W:.0f} {H}" xml:space="preserve">',
           f"""<style>
text{{white-space:pre;font:{FS}px ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;fill:{c['value']}}}
.key{{fill:{c['key']}}}.b{{font-weight:700}}.dim{{fill:{c['dim']}}}.art{{fill:{c['art']}}}.cursor{{fill:{c['key']};animation:blink 1s steps(1) infinite}}
.l{{opacity:0;animation:in .35s ease-out forwards}}
@keyframes in{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
@keyframes blink{{50%{{opacity:0}}}}
</style>""",
           f'<clipPath id="type"><rect x="0" y="0" height="{H}" width="0"><animate attributeName="width" '
           f'values="{";".join(str(PAD + (plen + i) * CW) for i in range(len(cfg["command"]) + 1))};{W}" '
           f'dur="{0.09 * (len(cfg["command"]) + 1):.2f}s" begin="0.3s" fill="freeze" calcMode="discrete"/></rect></clipPath>',
           f'<rect x="1" y="1" width="{W - 2:.0f}" height="{H - 2}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}" stroke-opacity=".7"/>']
    for i, l in enumerate(lines):
        if not l:
            continue
        n = sum(len(t) for t, _ in l)
        y = PAD + (i + 0.8) * LH
        spans = "".join(f'<tspan {fill(k)}>{escape(t).replace(' ', '&#160;')}</tspan>' for t, k in l)
        attrs = ' clip-path="url(#type)"' if i == 0 else f' class="l" style="animation-delay:{1.1 + i * 0.04:.2f}s"'
        out.append(f'<text x="{PAD}" y="{y:.1f}" textLength="{n * CW:.1f}" lengthAdjust="spacingAndGlyphs"{attrs}>{spans}</text>')
    ah = AFS * 1.15
    rows = "".join(f'<text x="{PAD}" y="{art_top + (j + 0.8) * ah:.1f}" font-size="{AFS}" textLength="{len(r) * AFS * 0.6:.1f}" '
                   f'lengthAdjust="spacingAndGlyphs">' + "".join(f'<tspan {fill(k)}>{escape(t).replace(" ", "&#160;")}</tspan>' for t, k in runs(r)) + "</text>"
                   for j, r in enumerate(art))
    out.append(f'<g class="l" style="animation-delay:1s">{rows}</g>')
    return "\n".join(out + ["</svg>"])


def ansi(cfg, lines):
    rgb = lambda h: ";".join(str(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    c = cfg["colors"]
    code = lambda k: "\x1b[0;" + ("1;" if " b" in k else "") + "38;2;" + rgb(k if k[0] == "#" else c[k.split()[0] if k != "cursor" else "key"]) + "m"
    return "\n".join("".join(code(k) + t for t, k in l) + "\x1b[0m" for l in lines) + "\n"


def main():
    cfg = tomllib.load(open("config.toml", "rb"))
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or \
        subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    s = fetch_stats(cfg["user"], token)
    live = {k: f"{v:,}" if isinstance(v, int) else v for k, v in s.items()}
    live |= {"uptime": uptime(s["created_at"]), "languages": ", ".join(s["top_languages"])}
    url = cfg["avatar_url"] or f"https://github.com/{cfg['user']}.png"
    mono = None if cfg.get("art_photo_colors", True) else cfg["colors"]["art"]
    pan = panel(cfg, live)
    # SVG: hi-res art in its own small-font block, panel laid out beside it
    w = cfg["art_width"]
    art = avatar_ascii(url, w, round(w * 0.6 / 1.15), cfg.get("keep_background", False))
    if mono: art = [[(ch, mono) for ch, _ in r] for r in art]
    aw, ah = -(-w * AFS * 0.6 // CW), len(art) * AFS * 1.15
    rows = -(-ah // LH)
    lines = compose(cfg, [], int(aw), pan, int(rows))
    art_top = PAD + 2 * LH + (len(lines) - 4 - rows) // 2 * LH + (rows * LH - ah) / 2
    open("neofetch.svg", "w").write(svg(cfg, lines, art, art_top))
    # terminal: ~2:1 cells, so half as many rows
    tw = cfg["term_art_width"]
    tart = [runs(r, mono) for r in avatar_ascii(url, tw, tw // 2, cfg.get("keep_background", False))]
    while tart and not "".join(t for t, _ in tart[0]).strip(): tart.pop(0)
    while tart and not "".join(t for t, _ in tart[-1]).strip(): tart.pop()
    open("neofetch.txt", "w").write(ansi(cfg, compose(cfg, tart, tw, pan)))

if __name__ == "__main__":
    main()
