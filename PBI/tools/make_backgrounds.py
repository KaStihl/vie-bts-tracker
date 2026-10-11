"""
Generates the page background pictures for the report (decoration only - NO text is baked in, so every
word stays editable in Power BI):

  * dark navy gradient with a soft teal glow and a faint network of flight routes
  * a darker header strip with a teal -> gold accent line and the FK's LAB logo in a light tile
  * a thin footer rule
  * (home page only) the arrows between the "How it works" boxes

Needs Pillow:  pip install pillow
The logo comes from the blog repo (assets/logo/fk-lab-logo.png) when it sits next to this repo, else a copy
in PBI/assets/fk-lab-logo.png.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

W, H = 1920, 1080
SS = 2  # supersampling for smooth lines

NAVY_TOP, NAVY_BOTTOM = (11, 30, 54), (7, 18, 36)
TEAL, GOLD = (44, 166, 164), (188, 134, 43)


def _gradient() -> Image.Image:
    base = Image.new("RGB", (W, H))
    px = base.load()
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(NAVY_TOP[i] * (1 - t) + NAVY_BOTTOM[i] * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    return base


def _glow(base: Image.Image, cx, cy, radius, color, alpha) -> Image.Image:
    # PIL's radial_gradient reaches 255 only in the corners (~181 at the edge midpoints), so rescale
    # it: the mask must be exactly 0 at the edge or the square shows as a hard rectangle.
    mask = Image.radial_gradient("L").point(lambda v: int(max(0.0, 255 - v * 255 / 170) * alpha))
    mask = mask.resize((radius * 2, radius * 2), Image.LANCZOS)
    layer = Image.new("RGB", (radius * 2, radius * 2), color)
    base.paste(layer, (cx - radius, cy - radius), mask)
    return base


HUBS = [(560, 210), (980, 170), (1420, 240), (1810, 190), (700, 520), (1150, 470), (1630, 560),
        (1860, 780), (840, 840), (1300, 900), (1700, 950), (520, 930)]
ROUTES = [(0, 1), (1, 2), (2, 3), (0, 4), (1, 5), (2, 6), (3, 6), (4, 5), (5, 6), (6, 7), (4, 8), (5, 9),
          (8, 9), (9, 10), (6, 10), (0, 5), (1, 6), (8, 11), (4, 11), (7, 10)]


def _routes(base: Image.Image) -> Image.Image:
    ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i, j in ROUTES:
        (x1, y1), (x2, y2) = HUBS[i], HUBS[j]
        dist = math.hypot(x2 - x1, y2 - y1)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 - dist * 0.16
        seq = []
        for k in range(81):
            t = k / 80
            seq.append((((1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2) * SS,
                        ((1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2) * SS))
        d.line(seq, fill=(120, 190, 215, 34), width=2 * SS)
    for x, y in HUBS:
        d.ellipse((x * SS - 11 * SS, y * SS - 11 * SS, x * SS + 11 * SS, y * SS + 11 * SS), fill=(80, 190, 190, 16))
        d.ellipse((x * SS - 3 * SS, y * SS - 3 * SS, x * SS + 3 * SS, y * SS + 3 * SS), fill=(150, 225, 225, 80))
    ov = ov.resize((W, H), Image.LANCZOS)
    base.paste(ov, (0, 0), ov)
    return base


def _header(base: Image.Image, logo_path: Path) -> Image.Image:
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle((0, 0, W, 108), fill=(5, 16, 31, 238))
    for x in range(W):                                  # teal -> gold accent line
        t = x / (W - 1)
        c = tuple(int(TEAL[i] * (1 - t) + GOLD[i] * t) for i in range(3))
        d.line((x, 108, x, 110), fill=c + (255,))
    base.paste(ov, (0, 0), ov)
    logo = Image.open(logo_path).convert("RGBA")
    h = 84
    logo = logo.resize((int(logo.width * h / logo.height), h), Image.LANCZOS)
    mask = Image.new("L", (logo.width * SS, logo.height * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=14 * SS, fill=255)
    mask = mask.resize(logo.size, Image.LANCZOS)
    base.paste(logo, (W - 24 - logo.width, 12), mask)
    return base


def _footer_rule(base: Image.Image) -> Image.Image:
    d = ImageDraw.Draw(base)
    d.line((240, 994, 1896, 994), fill=(34, 64, 98), width=1)
    return base


def _arrows(base: Image.Image, arrows) -> Image.Image:
    ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for x1, x2, y in arrows:
        d.line((x1 * SS, y * SS, (x2 - 4) * SS, y * SS), fill=TEAL + (255,), width=3 * SS)
        d.polygon([((x2 + 2) * SS, y * SS), ((x2 - 14) * SS, (y - 9) * SS), ((x2 - 14) * SS, (y + 9) * SS)], fill=TEAL + (255,))
    ov = ov.resize((W, H), Image.LANCZOS)
    base.paste(ov, (0, 0), ov)
    return base


def make(out_dir: Path, logo_path: Path, home_arrows) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _gradient()
    base = _glow(base, 1560, 120, 760, (20, 120, 130), 0.30)
    base = _glow(base, 120, 1020, 640, (150, 110, 40), 0.14)
    base = _routes(base)
    base = _header(base, logo_path)
    base = _footer_rule(base)
    main = out_dir / "bg_main.png"
    base.save(main, optimize=True)
    home = _arrows(base.copy(), home_arrows)
    home_path = out_dir / "bg_home.png"
    home.save(home_path, optimize=True)
    return {"main": main, "home": home_path}


if __name__ == "__main__":
    here = Path(__file__).resolve().parents[1]
    logo = next(p for p in (here.parent.parent / "vie-bts-blog" / "assets" / "logo" / "fk-lab-logo.png", here / "assets" / "fk-lab-logo.png") if p.exists())
    res = make(here / "_art", logo, [(602, 696, 745), (1028, 1122, 745), (1454, 1548, 745)])
    print({k: f"{v.stat().st_size // 1024} KB" for k, v in res.items()})
