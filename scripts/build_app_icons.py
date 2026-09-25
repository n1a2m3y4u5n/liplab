#!/usr/bin/env python3
"""앱 아이콘 만들기(탭 아이콘·홈 화면 아이콘·PWA). Figma 로고(58:13)의 보라 캐릭터를 그대로 쓴다.

로고의 캐릭터는 이미지(frontend/public/ui/logo.png)라서, 알파 윤곽을 중심에서 방사선으로 따 벡터 경로로 만들고
(손그림 같은 가장자리를 살림), 눈 두 점은 Logo.jsx(Figma 58:16·58:17)와 같은 자리에 놓는다.
색은 로고 이미지의 보라(#7959d6), 마스커블 아이콘 배경은 brand/primary-tint(#efe9fc)다.

  python3 scripts/build_app_icons.py      → frontend/public/ 아래 icon.svg, icon-192.png, icon-512.png,
                                             icon-maskable-512.png, apple-touch-icon.png, favicon-32.png
의존: Pillow, numpy
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "frontend", "public")
LOGO = os.path.join(PUB, "ui", "logo.png")
BLOB = "#7959d6"
EYE = "#000000"
TINT = "#efe9fc"

# Logo.jsx(Figma 58:13) 좌표: 블롭 상자 32.5×28.75(위 4.38), 눈 3.75 상자 (12.747, 19.627)·(18.75, 17.5)
BOX_W, BOX_H, BOX_TOP = 32.5, 28.75, 4.38
EYES = [(12.747, 19.627), (18.75, 17.5)]
EYE_D = 3.75


def outline(n=144):
    """logo.png 알파 윤곽 → PNG 좌표 점 n개(중심에서 방사선, 이웃 3개 평균으로 계단 무늬만 누름)."""
    a = np.array(Image.open(LOGO).convert("RGBA"))[..., 3] > 128
    ys, xs = np.nonzero(a)
    cx, cy = xs.mean(), ys.mean()
    h, w = a.shape
    radii = []
    for k in range(n):
        th = 2 * math.pi * k / n
        dx, dy = math.cos(th), math.sin(th)
        r, last = 0.0, 0.0
        while r < max(w, h):
            x, y = int(round(cx + r * dx)), int(round(cy + r * dy))
            if not (0 <= x < w and 0 <= y < h):
                break
            if a[y, x]:
                last = r
            r += 0.5
        radii.append(last)
    radii = np.array(radii)
    radii = (np.roll(radii, 1) + radii + np.roll(radii, -1)) / 3
    pts = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k, r in enumerate(radii)]
    img_w, img_h = a.shape[1], a.shape[0]
    return pts, img_w, img_h


def eyes_png(img_w, img_h):
    """Logo.jsx 좌표(블롭 상자 기준) → PNG 좌표의 눈 중심·반지름."""
    sx, sy = img_w / BOX_W, img_h / BOX_H
    out = [((x + EYE_D / 2) * sx, (y + EYE_D / 2 - BOX_TOP) * sy) for x, y in EYES]
    return out, EYE_D / 2 * (sx + sy) / 2


def fit(pts, size, frac):
    """윤곽 경계 상자를 size 캔버스 가운데에 긴 변이 size*frac가 되게 놓는 변환."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    s = size * frac / max(max(xs) - min(xs), max(ys) - min(ys))
    tx = size / 2 - s * (min(xs) + max(xs)) / 2
    ty = size / 2 - s * (min(ys) + max(ys)) / 2
    return lambda x, y: (s * x + tx, s * y + ty), s


def path_d(pts):
    """닫힌 Catmull-Rom → 3차 베지어 경로."""
    n = len(pts)
    d = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return "".join(d) + "Z"


def svg(size, frac, bg=None):
    pts, iw, ih = outline()
    eyes, er = eyes_png(iw, ih)
    tf, s = fit(pts, size, frac)
    tp = [tf(*p) for p in pts]
    body = []
    if bg:
        body.append(f'<rect width="{size}" height="{size}" fill="{bg}"/>')
    body.append(f'<path d="{path_d(tp)}" fill="{BLOB}"/>')
    for ex, ey in eyes:
        x, y = tf(ex, ey)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{er * s:.1f}" fill="{EYE}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="LIPLAB">'
            + "".join(body) + "</svg>\n")


def png(size, frac, bg=None, ss=4):
    pts, iw, ih = outline()
    eyes, er = eyes_png(iw, ih)
    big = size * ss
    tf, s = fit(pts, big, frac)
    im = Image.new("RGBA", (big, big), bg or (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.polygon([tf(*p) for p in pts], fill=BLOB)
    for ex, ey in eyes:
        x, y = tf(ex, ey)
        r = er * s
        dr.ellipse([x - r, y - r, x + r, y + r], fill=EYE)
    return im.resize((size, size), Image.LANCZOS)


def main():
    out = {"icon.svg": svg(512, 0.94)}
    for name, text in out.items():
        with open(os.path.join(PUB, name), "w", encoding="utf-8") as f:
            f.write(text)
    png(192, 0.94).save(os.path.join(PUB, "icon-192.png"))
    png(512, 0.94).save(os.path.join(PUB, "icon-512.png"))
    png(512, 0.62, TINT).save(os.path.join(PUB, "icon-maskable-512.png"))
    png(180, 0.70, TINT).convert("RGB").save(os.path.join(PUB, "apple-touch-icon.png"))
    png(32, 0.96).save(os.path.join(PUB, "favicon-32.png"))
    for n in list(out) + ["icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"]:
        print(n, os.path.getsize(os.path.join(PUB, n)))


if __name__ == "__main__":
    main()
