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
from PIL import Image

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
    return f"{int(yrs)}년 만의 인상" if yrs >= 1 else ""


def draw(us, kr, settings: dict, country: str = "미국", move: str = "인상", step_pp: float = 0.25,
         when: date | None = None) -> Image.Image:
    """에디토리얼 스타일: 라벨 → 제목 → 숫자 두 칸 → 꺾은선. 색은 최소로 쓴다."""
    c = cards.colors_from(settings)
    img, d = cards._new(c["bg"])
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    when = when or us[-1][0]
    up = move == "인상"
    ACC = RED if up else BLUE
    sub = c.get("text2", c["sub"])

    cards._tag(d, c, settings, MX, 96, "금 리", 30, cover=False)

    # 제목
    T(d, (MX, 190), f"{country} 기준금리", F("extrabold", 92), INK)
    line2 = f"{step_pp:.2f}%p {move}"
    f2 = F("extrabold", 92)
    bb = d.textbbox((MX, 296), line2, font=f2)
    d.rectangle((bb[0] - 6, bb[3] - 26, bb[2] + 6, bb[3] - 4), fill=c.get("mark", "#EEEA5E"))
    T(d, (MX, 296), line2, f2, INK)
    note = _years_since_prev_hike(us if country == "미국" else kr, when)
    T(d, (MX, 424), f"{when:%Y년 %m월 %d일}" + (f"  ·  {note}" if note else ""), F("medium", 34), sub)

    # 숫자 두 칸
    top, bot = 500, 660
    d.rectangle((MX, top, W - MX, top + 1), fill=c["line"])
    d.rectangle((MX, bot, W - MX, bot + 1), fill=c["line"])
    d.rectangle((W // 2, top + 26, W // 2 + 1, bot - 26), fill=c["line"])
    FW, FH = 54, 36
    for i, (name, pts, col) in enumerate((("미국", us, RED), ("한국", kr, BLUE))):
        x = MX + 4 + i * (W // 2 - MX + 26)
        fimg = (flags.usa(FW) if i == 0 else flags.korea(FW)).resize((FW, FH), Image.LANCZOS)
        flags.paste(img, fimg, x, top + 34)
        T(d, (x + FW + 16, top + 30), name, F("bold", 34), INK)
        fn = F("black", 76)
        val = f"{pts[-1][1]:.2f}%"
        T(d, (x, top + 84), val, fn, INK)
        ch = last_change(pts)
        if ch:
            arrow = "▲" if ch[2] > ch[1] else "▼"
            T(d, (x + cards.tlen(val, fn) + 22, top + 112), f"{arrow} {abs(ch[2] - ch[1]):.2f}%p",
              F("bold", 28), RED if ch[2] > ch[1] else BLUE)
    gapv = abs(us[-1][1] - kr[-1][1])
    T(d, (MX, bot + 24), f"한미 금리 차이 {gapv:.2f}%p", F("medium", 30), sub)

    # 꺾은선
    x0, x1, y0, y1 = MX + 70, W - MX - 70, 780, 1090
    vmin = -0.3
    vmax = max(v for _, v in us + kr) + 0.7
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 20
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("medium", 24)
    for v in range(0, int(vmax) + 1, 2):
        d.line((x0, Y(v), x1, Y(v)), fill=c["line"], width=1)
        d.text((x0 - 16, Y(v)), f"{v}%", font=fa, fill=sub, anchor="rm")
    for yy in range(start.year + 1, when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 16), f"{yy % 100:02d}", font=fa, fill=sub, anchor="mt")
    d.line((x0, y1, x1, y1), fill=c["line"], width=1)

    def step(pts, col, width=5):
        path = []
        for dt, v in pts:
            if path:
                path.append((X(dt), path[-1][1]))
            path.append((X(dt), Y(v)))
        path.append((x1, path[-1][1]))
        d.line(path, fill=col, width=width, joint="curve")
        return path

    step(kr, BLUE, 4)
    p_us = step(us, RED, 5)
    ex, ey = p_us[-1]
    d.ellipse((ex - 9, ey - 9, ex + 9, ey + 9), fill=RED)
    # 끝점 값(겹치면 위아래로 벌림)
    fe = F("bold", 34)
    ends = sorted(((us[-1][1], RED), (kr[-1][1], BLUE)), reverse=True)
    spread = max(0, 44 - abs(Y(ends[0][0]) - Y(ends[1][0]))) / 2
    for i, (v, col) in enumerate(ends):
        d.text((x1 + 14, Y(v) + (-spread if i == 0 else spread)), f"{v:.2f}", font=fe, fill=col, anchor="lm")

    T(d, (MX, 1140), "자료: 한국은행 ECOS · FRED(미국은 연방기금금리 목표범위 상한)", F("light", 24), c["sub"])
    cards._buto_footer(d, c, settings, None, None, "")
    return img
