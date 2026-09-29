"""한미 기준금리 카드(숫자를 받아 직접 그림 — 남의 그래프 그림을 가져오지 않음).

자료(모두 무료):
- 미국: FRED DFEDTARU(연방기금금리 목표범위 상한, 일별). 열쇠 없이 CSV 로 받음.
  https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU
- 한국: 한국은행 ECOS 722Y001 / 0101000(한국은행 기준금리, 월별).
  열쇠가 없으면 시험용 'sample'(한 번에 10건)로 반년씩 나눠 받음. settings["ecos_key"] 또는 환경변수 ECOS_API_KEY.
확인(2026-09-20): FRED 200, ECOS sample 200.
"""
from __future__ import annotations

import csv
import io
import os
import time
from datetime import date

import httpx
from PIL import Image, ImageDraw

from . import cards, flags

RED, BLUE, INK, GRID = "#D9362B", "#2E62D9", "#111111", "#D5D2CE"


def fetch_us(start: date) -> list[tuple[date, float]]:
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                  params={"id": "DFEDTARU", "cosd": start.isoformat()}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    return [(date.fromisoformat(a), float(b)) for a, b in rows if b not in ("", ".")]


def fetch_kr(start: date, end: date, key: str = "") -> list[tuple[date, float]]:
    key = key or os.environ.get("ECOS_API_KEY", "") or "sample"
    out = []
    y = start.year
    while y <= end.year:
        for a, b in (("01", "06"), ("07", "12")):
            u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10/722Y001/M/"
                 f"{y}{a}/{y}{b}/0101000")
            j = {}
            for attempt in range(3):                      # 시험용 열쇠는 가끔 끊긴다 → 재시도
                try:
                    j = httpx.get(u, timeout=30).json()
                    break
                except Exception:
                    time.sleep(1.5 * (attempt + 1))
            for row in (j.get("StatisticSearch") or {}).get("row", []):
                t = row["TIME"]
                out.append((date(int(t[:4]), int(t[4:]), 1), float(row["DATA_VALUE"])))
        y += 1
    return [p for p in sorted(out) if start <= p[0] <= end]


def last_change(pts: list[tuple[date, float]]) -> tuple[date, float, float] | None:
    """(바뀐 날, 이전 값, 새 값)."""
    for i in range(len(pts) - 1, 0, -1):
        if pts[i][1] != pts[i - 1][1]:
            return pts[i][0], pts[i - 1][1], pts[i][1]
    return None


def _peak_label(pts, ymax_only=True):
    v = max(p[1] for p in pts)
    run = [p[0] for p in pts if p[1] == v]
    mid = run[0] + (run[-1] - run[0]) / 2
    return mid, v


def _years_since_prev_hike(pts, when) -> str:
    """이번 인상 직전의 인상이 언제였는지 → "3년 만의 인상" 같은 문구(계산해서 씀)."""
    ups = [pts[i][0] for i in range(1, len(pts)) if pts[i][1] > pts[i - 1][1]]
    ups = [d0 for d0 in ups if d0 < when]
    if not ups:
        return ""
    yrs = (when - ups[-1]).days / 365.25
    return f"{int(yrs)}년 만" if yrs >= 1 else ""


# 흰 바탕·큰 제목 한 덩어리·선 두 개. 색은 움직인 나라에만 쓴다.
BG, INK, SUB, LINE = "#FFFFFF", "#111111", "#8A8A8A", "#E2E2E2"
RED, BLUE, MUTE = "#D6291E", "#1F4FD8", "#C9C9C9"

# 밝은 버전 / 검정 버전 색(배치는 똑같다)
THEMES = {
    "light": {"bg": "#FFFFFF", "ink": "#111111", "sub": "#8A8A8A", "grid": "#F0F0F0", "axis": "#E4E4E4",
              "tick": "#B5B5B5", "other": "#D2D2D2", "other_text": "#A3A3A3", "dash": "#D8D8D8",
              "foot": "#D9D9D9", "up": "#D6291E", "down": "#1F4FD8", "tint": 20},
    "dark": {"bg": "#000000", "ink": "#FFFFFF", "sub": "#8E8E8E", "grid": "#1C1C1C", "axis": "#2A2A2A",
             "tick": "#6E6E6E", "other": "#4A4A4A", "other_text": "#8E8E8E", "dash": "#3A3A3A",
             "foot": "#262626", "up": "#FF4A3D", "down": "#5B8CFF", "tint": 34},
}


def _footer(d, img, settings: dict, t: dict) -> None:
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    INK, SUB = t["ink"], t["sub"]
    y = cards.BUTO_FOOTER_Y
    d.rectangle((0, y, W, y + 1), fill=t["foot"])
    right = W - MX
    brand = settings.get("brand_name") or settings.get("account_name") or ""
    if brand:
        fb = F("black", 54)
        bw = cards.tlen(brand, fb)
        T(d, (right - bw, y + 34), brand, fb, INK)
        right -= bw + 30
    note = settings.get("footer_note", "")
    if note:
        fn = F("light", 28)
        T(d, (MX, y + 50), cards.wrap(note, fn, right - MX)[0], fn, SUB)


def _path(pts, X, Y, x1):
    out = []
    for dt, v in pts:
        if out:
            out.append((X(dt), out[-1][1]))
        out.append((X(dt), Y(v)))
    out.append((x1, out[-1][1]))
    return out


def draw(us, kr, settings: dict, country: str = "미국", move: str = "인상", step_pp: float = 0.25,
         when: date | None = None, theme: str = "light", thin: bool = False) -> Image.Image:
    F, T, TR, MX, W = cards.font, cards.tdraw, cards.tdraw_t, cards.MX, cards.W
    t = THEMES.get(theme or "light", THEMES["light"])
    BG, INK, SUB = t["bg"], t["ink"], t["sub"]
    img, d = cards._new(BG)
    when = when or us[-1][0]
    up = move == "인상"
    ACC = t["up"] if up else t["down"]
    main = us if country == "미국" else kr
    other = kr if country == "미국" else us
    other_name = "한국" if country == "미국" else "미국"

    # 머리: 작은 한 줄만
    bank = "미국 중앙은행" if country == "미국" else "한국은행"
    T(d, (MX, 96), f"{bank} 기준금리", F("bold", 30), SUB)
    fdate = F("medium", 30)
    T(d, (W - MX - cards.tlen(f"{when:%Y.%m.%d}", fdate), 96), f"{when:%Y.%m.%d}", fdate, SUB)

    # 제목 한 덩어리: 나라 + 금리 / 0.25%p 인상
    big = F("black", 132)
    y = 176
    TR(d, (MX - 6, y), f"{country}금리", big, INK, -0.03)
    y += 158
    x = TR(d, (MX - 6, y), f"{step_pp:.2f}%p ", big, ACC, -0.03)
    TR(d, (x, y), move, big, ACC, -0.03)
    note = _years_since_prev_hike(main, when)
    T(d, (MX, y + 176), f"{main[-1][1]:.2f}% · " + (f"{note} · " if note else "")
      + f"{other_name} {other[-1][1]:.2f}%", F("bold", 40), INK)

    # 그래프: 옅은 면 + 선 두 개, 이번에 바뀐 지점만 표시
    x0, x1, y0, y1 = MX, W - MX - 278, 700, 1086
    vmin, vmax = 0.0, max(v for _, v in us + kr) + 0.5
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 20
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)

    fa = F("medium", 24)
    for v in range(2, int(vmax) + 1, 2):                 # 가로선은 2%마다 아주 옅게
        d.line((x0, Y(v), x1 + 170, Y(v)), fill=t["grid"], width=1)
        T(d, (x0, Y(v) - 34), f"{v}%", fa, t["tick"])
    d.line((x0, y1, x1 + 170, y1), fill=t["axis"], width=1)
    for yy in range(start.year + 1, when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 14), str(yy), font=fa, fill=t["tick"], anchor="mt")

    main_pts, other_pts = (us, kr) if country == "미국" else (kr, us)
    p_main = _path(main_pts, X, Y, x1)
    p_other = _path(other_pts, X, Y, x1)

    tint = Image.new("RGBA", (W, cards.H), (0, 0, 0, 0))     # 움직인 나라 선 아래를 아주 옅게
    rgb = tuple(int(ACC[i:i + 2], 16) for i in (1, 3, 5))
    ImageDraw.Draw(tint).polygon(p_main + [(x1, y1), (x0, y1)], fill=rgb + (t["tint"],))
    img.paste(Image.alpha_composite(img.convert("RGBA"), tint).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    w_main = w_other = 4 if thin else 6          # 두 나라 선 굵기는 같게(색으로만 구분)
    d.line(p_other, fill=t["other"], width=w_other, joint="curve")
    d.line(p_main, fill=ACC, width=w_main, joint="curve")

    # 이번에 바뀐 지점: 가는 세로선 + 점
    cx, cy = X(when), Y(main_pts[-1][1])
    for yy in range(int(cy) + 14, int(y1), 16):              # 점선
        d.line((cx, yy, cx, min(yy + 8, y1)), fill=t["dash"], width=2)


    fv = F("black", 38)
    ym, yo = Y(main_pts[-1][1]), Y(other_pts[-1][1])
    if abs(ym - yo) < 56:
        mid = (ym + yo) / 2
        ym, yo = (mid - 28, mid + 28) if main_pts[-1][1] >= other_pts[-1][1] else (mid + 28, mid - 28)
    FSZ = 44 if thin else 52                                             # 선이 끝나는 자리에 동그란 국기를 올린다
    for name, ytxt, col, val, yend in ((country, ym, ACC, main_pts[-1][1], Y(main_pts[-1][1])),
                                       (other_name, yo, t["other_text"], other_pts[-1][1], Y(other_pts[-1][1]))):
        badge = flags.circle(name, FSZ, ring=col, ring_w=3)
        img.paste(badge, (int(x1 - FSZ / 2), int(yend - FSZ / 2)), badge)
        ImageDraw.Draw(img).text((x1 + FSZ / 2 + 18, ytxt), f"{name} {val:.2f}", font=fv, fill=col, anchor="lm")
    d = ImageDraw.Draw(img)

    T(d, (MX, 1168), "자료: 한국은행 ECOS · FRED(미국은 연방기금금리 목표범위 상한)", F("light", 26), SUB)
    _footer(d, img, settings, t)
    return img
