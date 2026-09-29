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
            j = httpx.get(u, timeout=30).json()
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


def _footer(d, img, settings: dict) -> None:
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    y = cards.BUTO_FOOTER_Y
    d.rectangle((0, y, W, y + 1), fill="#D9D9D9")
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
         when: date | None = None) -> Image.Image:
    F, T, TR, MX, W = cards.font, cards.tdraw, cards.tdraw_t, cards.MX, cards.W
    img, d = cards._new(BG)
    when = when or us[-1][0]
    up = move == "인상"
    ACC = RED if up else BLUE
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

    # 그래프: 선 두 개만, 움직인 나라만 색
    x0, x1, y0, y1 = MX, W - MX - 210, 700, 1090
    vmin, vmax = 0.0, max(v for _, v in us + kr) + 0.5
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 20
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("medium", 28)
    for v in range(0, int(vmax) + 1, 2):
        d.line((x0, Y(v), x1 + 120, Y(v)), fill=LINE, width=1)
        if v:                                    # 0% 글자는 선과 겹쳐서 넣지 않는다
            T(d, (x0, Y(v) - 38), f"{v}%", fa, SUB)
    for yy in range(start.year + 1, when.year + 1, 1):
        d.text((X(date(yy, 1, 1)), y1 + 16), str(yy), font=fa, fill=SUB, anchor="mt")

    main_pts, other_pts = (us, kr) if country == "미국" else (kr, us)
    d.line(_path(other_pts, X, Y, x1), fill=MUTE, width=6, joint="curve")
    d.line(_path(main_pts, X, Y, x1), fill=ACC, width=8, joint="curve")

    fv = F("black", 40)
    ym, yo = Y(main_pts[-1][1]), Y(other_pts[-1][1])
    if abs(ym - yo) < 52:
        mid = (ym + yo) / 2
        ym, yo = (mid - 26, mid + 26) if main_pts[-1][1] >= other_pts[-1][1] else (mid + 26, mid - 26)
    d.text((x1 + 22, ym), f"{country} {main_pts[-1][1]:.2f}", font=fv, fill=ACC, anchor="lm")
    d.text((x1 + 22, yo), f"{other_name} {other_pts[-1][1]:.2f}", font=fv, fill="#9A9A9A", anchor="lm")

    T(d, (MX, 1168), "자료: 한국은행 ECOS · FRED(미국은 연방기금금리 목표범위 상한)", F("light", 26), SUB)
    _footer(d, img, settings)
    return img
