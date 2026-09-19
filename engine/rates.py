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


def draw(us, kr, settings: dict, country: str = "미국", move: str = "인상", step_pp: float = 0.25,
         when: date | None = None) -> Image.Image:
    c = cards.colors_from(settings)
    img, d = cards._new(c["bg"])
    F, T, MX = cards.font, cards.tdraw, cards.MX
    when = when or us[-1][0]
    bank = "미국 중앙은행" if country == "미국" else "한국은행"
    T(d, (MX, 70), f"* {bank} 기준금리 ({when:%Y.%m.%d}.)", F("semibold", 30), INK)
    cards._pill(d, 860, 58, "금리 이슈", F("bold", 28), INK, "#FFFFFF")

    big = F("black", 170)
    title = f"{country}금리"
    T(d, (MX - 6, 120), title, big, INK)
    tb = d.textbbox((MX - 6, 120), title, font=big)
    fl = flags.usa(250) if country == "미국" else flags.korea(210)
    if tb[2] + 40 + fl.width <= 1000:
        flags.paste(img, fl, 1000 - fl.width, (tb[1] + tb[3]) // 2 - fl.height // 2)

    fb = F("black", 66)
    y2 = 330
    tag = f"{step_pp:.2f}%p"
    bw = int(fb.getlength(tag)) + 56
    x_in = MX + bw + 30
    bb = d.textbbox((x_in, y2 - 4), move, font=big)
    d.rectangle((bb[0] - 8, bb[1] + (bb[3] - bb[1]) * 0.55, bb[2] + 8, bb[3] + 8), fill=c.get("mark", "#EEEA5E"))
    T(d, (x_in, y2 - 4), move, big, INK)
    cy = (bb[1] + bb[3]) / 2
    d.rounded_rectangle((MX, cy - 62, MX + bw, cy + 62), radius=26, fill=RED if move == "인상" else BLUE)
    d.text((MX + bw / 2, cy), tag, font=fb, fill="#FFFFFF", anchor="mm")

    # 그래프
    x0, x1, y0, y1 = 150, 880, 600, 1120
    vmin = -0.8
    vmax = max(6.0, max(v for _, v in us + kr) + 0.5)
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), date(when.year, when.month, 28).toordinal() + 10
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("bold", 30)
    for v in range(0, int(vmax) + 1):
        d.line((x0, Y(v), x1, Y(v)), fill=GRID, width=2)
        d.text((x0 - 20, Y(v)), f"{v}%", font=fa, fill=INK, anchor="rm")
    for yy in range(start.year + (0 if start.month == 1 else 1), when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 14), str(yy), font=fa, fill=INK, anchor="mt")

    def step(pts, col):
        path = []
        for dt, v in pts:
            if path:
                path.append((X(dt), path[-1][1]))
            path.append((X(dt), Y(v)))
        path.append((x1, path[-1][1]))
        d.line(path, fill=col, width=8, joint="curve")

    step(us, RED)
    step(kr, BLUE)
    fl_ = F("black", 48)
    # 시작 값: 위쪽 선은 위에, 아래쪽 선은 아래에
    (hi, hi_c), (lo, lo_c) = sorted(((us[0][1], RED), (kr[0][1], BLUE)), reverse=True)
    d.text((X(start), Y(max(hi, lo) + 0.8)), f"{hi:.2f}", font=fl_, fill=hi_c, anchor="lb")
    d.text((X(start), Y(lo) + 14), f"{lo:.2f}", font=fl_, fill=lo_c, anchor="lt")
    for pts, col in ((us, RED), (kr, BLUE)):
        mid, v = _peak_label(pts)
        d.text((X(mid), Y(v) - 14), f"{v:.2f}", font=fl_, fill=col, anchor="mb")
    ends = sorted(((us[-1][1], RED), (kr[-1][1], BLUE)), reverse=True)
    gap = abs(Y(ends[0][0]) - Y(ends[1][0]))
    for i, (v, col) in enumerate(ends):
        yy = Y(v) + ((-1 if i == 0 else 1) * max(0, 60 - gap) / 2)
        d.text((x1 + 14, yy), f"{v:.2f}", font=fl_, fill=col, anchor="lm")

    fk = F("bold", 34)
    FW, FH = 66, 44                                     # 두 국기 같은 크기
    for i, (fimg, col, name) in enumerate(((flags.usa(FW), RED, "미국"), (flags.korea(FW), BLUE, "한국"))):
        yy = 606 + i * 58
        fimg = fimg.resize((FW, FH), Image.LANCZOS)
        flags.paste(img, fimg, x0 + 10, yy + 20 - FH // 2)
        d.rectangle((x0 + 90, yy + 15, x0 + 130, yy + 25), fill=col)
        T(d, (x0 + 142, yy), name, fk, INK)
    T(d, (MX, 1180), "자료: 한국은행 ECOS, FRED(미국은 연방기금금리 목표범위 상한)", F("light", 24), c["sub"])
    cards._buto_footer(d, c, settings, None, None, "")
    return img
