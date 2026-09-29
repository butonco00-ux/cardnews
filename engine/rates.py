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
    return f"{int(yrs)}년 만" if yrs >= 1 else ""


DARK_BG, DARK_INK, DARK_SUB, DARK_LINE = "#000000", "#FFFFFF", "#9A9A9A", "#2A2A2A"
GOLD, SKY = "#C9A227", "#7FA6E8"


def _footer(d, img, settings: dict) -> None:
    """검정 카드용 아래 띠(다른 카드와 같은 자리·같은 기준선)."""
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    y = cards.BUTO_FOOTER_Y
    d.rectangle((0, y, W, y + 1), fill=DARK_LINE)
    right = W - MX
    brand = settings.get("brand_name") or settings.get("account_name") or ""
    if brand:
        fb = F("black", 54)
        bw = cards.tlen(brand, fb)
        T(d, (right - bw, y + 34), brand, fb, DARK_INK)
        right -= bw + 30
    note = settings.get("footer_note", "")
    if note:
        fn = F("light", 28)
        T(d, (MX, y + 50), cards.wrap(note, fn, right - MX)[0], fn, DARK_SUB)


def draw(us, kr, settings: dict, country: str = "미국", move: str = "인상", step_pp: float = 0.25,
         when: date | None = None) -> Image.Image:
    """검정 바탕 금리 카드(절제형): 라벨 → 큰 숫자 → 세 칸 비교 → 가는 꺾은선."""
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    TR = cards.tdraw_t
    img, d = cards._new(DARK_BG)
    when = when or us[-1][0]
    main = us if country == "미국" else kr
    other_name = "한국" if country == "미국" else "미국"

    # 1) 머리: 라벨(회색) + 날짜
    fl = F("bold", 26)
    xx = MX
    for ch in "금리":
        T(d, (xx, 100), ch, fl, DARK_SUB)
        xx += cards.tlen(ch, fl) + 13
    d.rectangle((xx + 16, 100 + 23, xx + 112, 100 + 24), fill=DARK_LINE)
    fdate = F("medium", 26)
    T(d, (W - MX - cards.tlen(f"{when:%Y.%m.%d}", fdate), 100), f"{when:%Y.%m.%d}", fdate, DARK_SUB)

    # 2) 큰 숫자: 숫자는 굵게, %는 한 단계 작게 위로 맞춘다
    T(d, (MX, 200), f"{country} 기준금리", F("medium", 40), DARK_SUB)
    fnum, fpct = F("black", 216), F("bold", 88)
    num = f"{main[-1][1]:.2f}"
    nx = TR(d, (MX - 10, 268), num, fnum, DARK_INK, -0.03)
    T(d, (nx + 16, 268 + 216 - 88 - 18), "%", fpct, DARK_INK)

    # 3) 변동 한 줄: 금색은 이 줄에만
    y = 560
    d.rectangle((MX, y, MX + 64, y + 2), fill=GOLD)
    move_txt = f"{step_pp:.2f}%p {move}"
    mx2 = T(d, (MX, y + 30), move_txt, F("bold", 38), GOLD)
    note = _years_since_prev_hike(main, when)
    if note:
        T(d, (mx2 + 22, y + 32), f"· {note}", F("medium", 34), DARK_SUB)

    # 4) 세 칸 비교(미국 / 한국 / 격차)
    top, bot = 690, 846
    d.rectangle((MX, top, W - MX, top + 1), fill=DARK_LINE)
    d.rectangle((MX, bot, W - MX, bot + 1), fill=DARK_LINE)
    # 머리 숫자와 겹치지 않게, 비교 칸에는 '상대 나라'와 '차이'만 둔다
    other = kr if country == "미국" else us
    cols = [(f"{other_name} 기준금리", f"{other[-1][1]:.2f}%", DARK_INK),
            ("한미 금리 차이", f"{abs(us[-1][1] - kr[-1][1]):.2f}%p", DARK_SUB)]
    colw = (W - MX * 2) / 2
    flab, fval = F("medium", 26), F("bold", 64)
    for i, (label, value, col) in enumerate(cols):
        cx = MX + colw * i
        if i:
            d.rectangle((int(cx) - 1, top + 26, int(cx), bot - 26), fill=DARK_LINE)
        T(d, (cx + (0 if i == 0 else 30), top + 34), label, flab, DARK_SUB)
        TR(d, (cx + (0 if i == 0 else 30), top + 74), value, fval, col, -0.02)

    # 5) 꺾은선(가늘게) + 끝점 동그란 국기
    x0, x1, y0, y1 = MX + 64, W - MX - 40, 900, 1120
    vmin, vmax = -0.2, max(v for _, v in us + kr) + 0.4
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 20
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("medium", 24)
    for v in range(0, int(vmax) + 2, 2):
        d.line((x0, Y(v), x1, Y(v)), fill="#1C1C1C", width=1)
        d.text((x0 - 14, Y(v)), f"{v}%", font=fa, fill="#6E6E6E", anchor="rm")
    for yy in range(start.year + 1, when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 14), f"'{yy % 100:02d}", font=fa, fill="#6E6E6E", anchor="mt")

    def step(pts, col, width):
        path = []
        for dt, v in pts:
            if path:
                path.append((X(dt), path[-1][1]))
            path.append((X(dt), Y(v)))
        path.append((x1, path[-1][1]))
        d.line(path, fill=col, width=width, joint="curve")

    step(kr, "#5D7FBF", 3)
    step(us, "#D8D2C4", 4)
    SZ = 46
    ys = {"미국": Y(us[-1][1]), "한국": Y(kr[-1][1])}
    if abs(ys["미국"] - ys["한국"]) < SZ + 4:
        mid = (ys["미국"] + ys["한국"]) / 2
        hi = "미국" if us[-1][1] >= kr[-1][1] else "한국"
        lo = "한국" if hi == "미국" else "미국"
        ys = {hi: mid - (SZ + 4) / 2, lo: mid + (SZ + 4) / 2}
    for name, ring in (("미국", "#D8D2C4"), ("한국", "#5D7FBF")):
        b = flags.circle(name, SZ, ring=ring, ring_w=2)
        img.paste(b, (int(x1 - SZ // 2), int(ys[name] - SZ // 2)), b)

    T(d, (MX, 1168), "자료: 한국은행 ECOS · FRED(미국은 연방기금금리 목표범위 상한)", F("light", 26), "#6E6E6E")
    _footer(d, img, settings)
    return img
