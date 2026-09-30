"""국기 그리기(그림 파일 없이 규격대로 직접 그림 → 저작권 걱정 없음).

- 태극기: 가로:세로 3:2, 태극 지름 = 세로의 1/2, 태극 축은 왼쪽 위→오른쪽 아래 대각선.
  괘 막대 길이 = 태극 지름의 1/2, 막대 두께 = 지름의 1/12, 막대 사이·끊긴 틈 = 지름의 1/24,
  태극 가장자리와 괘 사이 = 지름의 1/4.
- 성조기: 가로:세로 1.9:1, 줄 13개, 파란 칸은 가로 0.4 · 세로 7줄, 별 50개(6·5 줄 번갈아 9줄).
4배 크기로 그린 뒤 줄여서 가장자리를 매끈하게 한다.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

KR_RED, KR_BLUE, KR_BLACK = "#CD2E3A", "#0047A0", "#000000"
US_RED, US_BLUE = "#B22234", "#3C3B6E"
SS = 4


def korea(width: int) -> Image.Image:
    W, H = width * SS, int(width * 2 / 3) * SS
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    cx, cy = W / 2, H / 2
    D = H / 2                      # 태극 지름
    R = D / 2
    ang = math.atan2(H, W)         # 대각선 기울기
    ux, uy = math.cos(ang), math.sin(ang)          # 축(왼쪽 위→오른쪽 아래)
    nx, ny = uy, -ux                               # 축에 수직(위쪽)

    # 태극: 축 위쪽 반원 빨강, 아래쪽 반원 파랑 + 왼쪽 작은 원 빨강, 오른쪽 작은 원 파랑
    deg = math.degrees(ang)
    d.pieslice((cx - R, cy - R, cx + R, cy + R), 180 + deg, 360 + deg, fill=KR_RED)
    d.pieslice((cx - R, cy - R, cx + R, cy + R), deg, 180 + deg, fill=KR_BLUE)
    r = R / 2
    lx, ly = cx - ux * r, cy - uy * r
    rx, ry = cx + ux * r, cy + uy * r
    d.ellipse((lx - r, ly - r, lx + r, ly + r), fill=KR_RED)
    d.ellipse((rx - r, ry - r, rx + r, ry + r), fill=KR_BLUE)

    bar_len, bar_w, gap = D / 2, D / 12, D / 24
    depth = 3 * bar_w + 2 * gap
    dist = R + D / 4 + depth / 2

    def bar(px, py, dx, dy, length):
        """(px,py) 중심, 방향 (dx,dy) 로 length 길이, 두께 bar_w 인 막대."""
        ex, ey = -dy, dx                           # 두께 방향
        hl, hw = length / 2, bar_w / 2
        pts = [(px + dx * hl + ex * hw, py + dy * hl + ey * hw), (px - dx * hl + ex * hw, py - dy * hl + ey * hw),
               (px - dx * hl - ex * hw, py - dy * hl - ey * hw), (px + dx * hl - ex * hw, py + dy * hl - ey * hw)]
        d.polygon(pts, fill=KR_BLACK)

    def trigram(dirx, diry, pattern):
        """dir: 중심에서 괘 쪽 방향(단위벡터). pattern: 안쪽부터 True=이어짐, False=끊김."""
        # 막대 방향은 dir 에 수직
        bx, by = -diry, dirx
        for i, solid in enumerate(pattern):
            off = dist - depth / 2 + bar_w / 2 + i * (bar_w + gap)
            px, py = cx + dirx * off, cy + diry * off
            if solid:
                bar(px, py, bx, by, bar_len)
            else:
                seg = (bar_len - gap) / 2
                for s in (-1, 1):
                    q = (seg + gap) / 2 * s
                    bar(px + bx * q, py + by * q, bx, by, seg)

    # 건(☰) 왼쪽 위, 곤(☷) 오른쪽 아래, 감(☵) 오른쪽 위, 리(☲) 왼쪽 아래
    trigram(-ux, -uy, (True, True, True))
    trigram(ux, uy, (False, False, False))
    ax, ay = math.cos(-ang), math.sin(-ang)        # 다른 대각선(왼쪽 아래→오른쪽 위)
    trigram(ax, ay, (False, True, False))
    trigram(-ax, -ay, (True, False, True))
    return img.resize((width, int(width * 2 / 3)), Image.LANCZOS)


def _star(d, cx, cy, r, fill):
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.382
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def usa(width: int) -> Image.Image:
    W = width * SS
    H = int(W / 1.9)
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    sh = H / 13
    for i in range(13):
        if i % 2 == 0:
            d.rectangle((0, i * sh, W, (i + 1) * sh), fill=US_RED)
    cw, ch = W * 0.4, sh * 7
    d.rectangle((0, 0, cw, ch), fill=US_BLUE)
    gx, gy = cw / 12, ch / 10
    r = sh * 0.616 * 0.5 * 1.0
    for row in range(9):
        cols = 6 if row % 2 == 0 else 5
        for col in range(cols):
            x = gx * (1 + 2 * col + (0 if row % 2 == 0 else 1))
            y = gy * (1 + row)
            _star(d, x, y, r, "#FFFFFF")
    return img.resize((width, int(width / 1.9)), Image.LANCZOS)


def paste(img: Image.Image, flag: Image.Image, x: int, y: int, border: str = "#D5D2CE") -> None:
    """국기 붙이기(흰 바탕이 배경에 묻히지 않게 가는 테두리)."""
    img.paste(flag, (int(x), int(y)))
    ImageDraw.Draw(img).rectangle((x - 1, y - 1, x + flag.width, y + flag.height), outline=border, width=2)


def circle(country: str, size: int, ring: str | None = None, ring_w: int = 3) -> Image.Image:
    """동그란 국기 배지. 테두리는 선으로 긋지 않고 '원판을 칠하고 그 안에 국기를 얹는' 방식이라
    가장자리가 울퉁불퉁해지지 않는다. 반환: RGBA."""
    S, rw = size * SS, max(0, ring_w) * SS
    inner = max(4, S - rw * 2)
    src = usa(max(8, int(size * 2.0))) if country == "미국" else korea(max(8, int(size * 1.6)))
    left = (src.width - src.height) // 2
    face = src.crop((left, 0, left + src.height, src.height)).resize((inner, inner), Image.LANCZOS)

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    if ring and rw:
        ImageDraw.Draw(out).ellipse((0, 0, S - 1, S - 1), fill=ring)     # 원판(=테두리)
    mask_in = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask_in).ellipse((0, 0, inner - 1, inner - 1), fill=255)
    out.paste(face, (rw, rw), mask_in)                                   # 국기는 원 안쪽에만

    outer = Image.new("L", (S, S), 0)
    ImageDraw.Draw(outer).ellipse((0, 0, S - 1, S - 1), fill=255)        # 바깥도 정확히 원으로 자른다
    a = out.getchannel("A").point(lambda v: v)
    out.putalpha(Image.composite(a, Image.new("L", (S, S), 0), outer))
    return out.resize((size, size), Image.LANCZOS)
