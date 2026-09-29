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


# 아파트LAP 스타일(사용자 선택): 흰 바탕·굵은 큰 제목·빨간 강조·굵은 그래프
BG, INK, SUB, LINE = "#FFFFFF", "#111111", "#7A7A7A", "#111111"
RED, BLUE, GREY = "#D22C22", "#2E62D9", "#BDBDBD"


def _footer(d, img, settings: dict) -> None:
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    y = cards.BUTO_FOOTER_Y
    d.rectangle((0, y, W, y + 2), fill=INK)
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


def _shadow_text(d, xy, text, f, em=-0.03):
    """제목: 옅은 그림자를 깔고 검정 글씨(아파트LAP 느낌)."""
    x, y = xy
    cards.tdraw_t(d, (x + 8, y + 8), text, f, "#DCDCDC", em)
    return cards.tdraw_t(d, (x, y), text, f, INK, em)


def _path(pts, X, Y, x1):
    out = []
    for dt, v in pts:
        if out:
            out.append((X(dt), out[-1][1]))
        out.append((X(dt), Y(v)))
    out.append((x1, out[-1][1]))
    return out


def _plateaus(pts, keep=2):
    """가장 높은 값과 시작 값의 위치(라벨용)."""
    hi = max(p[1] for p in pts)
    run = [p[0] for p in pts if p[1] == hi]
    mid = run[0] + (run[-1] - run[0]) / 2
    return [(mid, hi), (pts[0][0], pts[0][1])][:keep]


def draw(us, kr, settings: dict, country: str = "미국", move: str = "인상", step_pp: float = 0.25,
         when: date | None = None) -> Image.Image:
    F, T, MX, W, H = cards.font, cards.tdraw, cards.MX, cards.W, cards.H
    img, d = cards._new(BG)
    when = when or us[-1][0]
    bank = "미국 중앙은행" if country == "미국" else "한국은행"
    up = move == "인상"

    d.rectangle((14, 14, W - 15, H - 15), outline=INK, width=3)          # 바깥 테두리

    # 머리 줄: 출처 + 분야 칩
    T(d, (MX - 30, 60), f"* {bank} 기준금리({when:%Y.%m.%d}.)", F("bold", 30), INK)
    chip = "금리 이슈"
    fc = F("bold", 28)
    cw = cards.tlen(chip, fc) + 44
    d.rectangle((W - MX + 30 - cw, 56, W - MX + 30, 104), fill=INK)
    d.text((W - MX + 30 - cw / 2, 80), chip, font=fc, fill="#FFFFFF", anchor="mm")

    # 큰 제목: "미국금리" / "인상"(빨간 상자 옆)
    big = F("black", 168)
    _shadow_text(d, (MX - 30, 130), f"{country}금리", big)
    y2 = 320
    fb = F("black", 64)
    tag = f"{step_pp:.2f}%p"
    bw = int(cards.tlen(tag, fb)) + 64
    d.rounded_rectangle((MX - 30, y2 + 28, MX - 30 + bw, y2 + 158), radius=30, fill=RED if up else BLUE)
    d.text((MX - 30 + bw / 2, y2 + 93), tag, font=fb, fill="#FFFFFF", anchor="mm")
    _shadow_text(d, (MX - 30 + bw + 34, y2), move, big)

    # 그래프
    x0, x1, y0, y1 = MX + 60, W - MX - 170, 560, 1020
    vmin, vmax = 0.0, max(v for _, v in us + kr) + 0.6
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 25
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("bold", 30)
    for v in range(0, int(vmax) + 1):
        d.line((x0, Y(v), x1, Y(v)), fill="#E6E6E6", width=2)
        d.text((x0 - 18, Y(v)), f"{v}%", font=fa, fill=INK, anchor="rm")
    d.rectangle((x0, y1, x1, y1 + 4), fill=INK)
    for yy in range(start.year, when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 20), str(yy), font=fa, fill=INK, anchor="mt")

    d.line(_path(kr, X, Y, x1), fill=BLUE, width=11, joint="curve")
    d.line(_path(us, X, Y, x1), fill=RED, width=11, joint="curve")

    fl = F("black", 52)
    def label(x, y, text, col, anchor):
        d.text((x, y), text, font=fl, fill=col, anchor=anchor, stroke_width=8, stroke_fill=BG)
    (us_mid, us_hi), (us_d0, us_v0) = _plateaus(us)
    (kr_mid, kr_hi), (kr_d0, kr_v0) = _plateaus(kr)
    label(X(us_mid), Y(us_hi) - 16, f"{us_hi:.2f}", RED, "mb")
    label(X(kr_mid), Y(kr_hi) - 16, f"{kr_hi:.2f}", BLUE, "mb")
    label(X(kr_d0), Y(kr_v0) - 16, f"{kr_v0:.2f}", BLUE, "lb")            # 시작 값은 좌우로 어긋나게
    label(X(us_d0) + 190, Y(us_v0) - 16, f"{us_v0:.2f}", RED, "lb")
    ye = {"us": Y(us[-1][1]), "kr": Y(kr[-1][1])}
    if abs(ye["us"] - ye["kr"]) < 66:
        mid = (ye["us"] + ye["kr"]) / 2
        hi_k = "us" if us[-1][1] >= kr[-1][1] else "kr"
        lo_k = "kr" if hi_k == "us" else "us"
        ye = {hi_k: mid - 33, lo_k: mid + 33}
    label(x1 + 18, ye["us"], f"{us[-1][1]:.2f}", RED, "lm")
    label(x1 + 18, ye["kr"], f"{kr[-1][1]:.2f}", BLUE, "lm")

    # 국기 범례(그래프 왼쪽 위 빈 자리)
    fleg = F("bold", 32)
    for i, (name, col) in enumerate((("미국", RED), ("한국", BLUE))):
        by = y0 + 6 + i * 74
        f_img = (flags.usa(96) if name == "미국" else flags.korea(96)).resize((96, 62), Image.LANCZOS)
        flags.paste(img, f_img, x0 + 24, by, border=INK)
        dd = ImageDraw.Draw(img)
        dd.rectangle((x0 + 140, by + 26, x0 + 190, by + 36), fill=col)
        cards.tdraw(dd, (x0 + 206, by + 12), name, fleg, INK)
    d = ImageDraw.Draw(img)

    # 아래 한 줄 요약
    gap = abs(us[-1][1] - kr[-1][1])
    note = _years_since_prev_hike(us if country == "미국" else kr, when)
    line = f"미국 {us[-1][1]:.2f}% · 한국 {kr[-1][1]:.2f}% · 차이 {gap:.2f}%p"
    if note:
        line += f" · {note}"
    d.rectangle((MX - 30, 1090, W - MX + 30, 1094), fill=INK)
    T(d, (MX - 30, 1112), line, F("bold", 34), INK)
    T(d, (MX - 30, 1166), "자료: 한국은행 ECOS · FRED(미국은 연방기금금리 목표범위 상한)", F("light", 26), SUB)
    _footer(d, img, settings)
    return img
