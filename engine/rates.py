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
    """검정 카드: 위는 큰 숫자, 아래는 카드 끝까지 닿는 큰 그래프.
    두 나라 금리 '차이'를 색 띠로 칠해서 한눈에 보이게 한다."""
    F, T, MX, W = cards.font, cards.tdraw, cards.MX, cards.W
    TR = cards.tdraw_t
    img, d = cards._new(DARK_BG)
    when = when or us[-1][0]
    main = us if country == "미국" else kr
    other_name = "한국" if country == "미국" else "미국"

    # 머리: 라벨 + 날짜
    fl = F("bold", 26)
    xx = MX
    for ch in "금리":
        T(d, (xx, 96), ch, fl, DARK_SUB)
        xx += cards.tlen(ch, fl) + 13
    d.rectangle((xx + 16, 96 + 23, xx + 112, 96 + 24), fill=DARK_LINE)
    fdate = F("medium", 26)
    T(d, (W - MX - cards.tlen(f"{when:%Y.%m.%d}", fdate), 96), f"{when:%Y.%m.%d}", fdate, DARK_SUB)

    # 큰 숫자
    T(d, (MX, 176), f"{country} 기준금리", F("medium", 38), DARK_SUB)
    fnum, fpct = F("black", 200), F("bold", 80)
    nx = TR(d, (MX - 10, 236), f"{main[-1][1]:.2f}", fnum, DARK_INK, -0.03)
    T(d, (nx + 16, 236 + 200 - 80 - 16), "%", fpct, DARK_INK)

    # 변동 한 줄(금색은 여기만)
    d.rectangle((MX, 500, MX + 64, 502), fill=GOLD)
    mx2 = T(d, (MX, 530), f"{step_pp:.2f}%p {move}", F("bold", 36), GOLD)
    note = _years_since_prev_hike(main, when)
    if note:
        T(d, (mx2 + 22, 532), f"· {note}", F("medium", 32), DARK_SUB)

    # ---------------- 큰 그래프(좌우 끝까지) ----------------
    x0, x1, y0, y1 = 0, W - 148, 690, 1104
    vmin, vmax = -0.15, max(v for _, v in us + kr) + 0.35
    start = min(us[0][0], kr[0][0])
    t0, t1 = start.toordinal(), when.toordinal() + 30
    X = lambda dt: x0 + (dt.toordinal() - t0) / (t1 - t0) * (x1 - x0)
    Y = lambda v: y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
    fa = F("medium", 24)
    for v in range(2, int(vmax) + 2, 2):                 # 0% 줄은 글자 없이(아래 연도와 겹침 방지)
        d.line((0, Y(v), W, Y(v)), fill="#1A1A1A", width=1)
        T(d, (MX, Y(v) - 34), f"{v}%", fa, "#5E5E5E")
    d.line((0, Y(0), W, Y(0)), fill="#1A1A1A", width=1)

    p_us, p_kr = _path(us, X, Y, x1), _path(kr, X, Y, x1)
    band = Image.new("RGBA", (W, cards.H), (0, 0, 0, 0))     # 두 선 사이(금리 차이)를 옅게 칠한다
    ImageDraw.Draw(band).polygon(p_us + list(reversed(p_kr)), fill=(201, 162, 39, 46))
    img.paste(Image.alpha_composite(img.convert("RGBA"), band).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    d.line(p_kr, fill="#6E90D0", width=4, joint="curve")
    d.line(p_us, fill="#E6DFCE", width=5, joint="curve")

    for yy in range(start.year + 1, when.year + 1):
        d.text((X(date(yy, 1, 1)), y1 + 14), f"'{yy % 100:02d}", font=fa, fill="#5E5E5E", anchor="mt")

    # 오른쪽 끝: 두 나라 값 + 차이 표시
    gap = abs(us[-1][1] - kr[-1][1])
    gx = x1 - 30
    yu, yk = Y(us[-1][1]), Y(kr[-1][1])
    d.line((gx, yu, gx, yk), fill=GOLD, width=2)                      # 금리 차이 자
    for yy in (yu, yk):
        d.line((gx - 9, yy, gx + 9, yy), fill=GOLD, width=2)
    fgap = F("bold", 30)
    T(d, (gx - 18 - cards.tlen(f"{gap:.2f}%p", fgap), (yu + yk) / 2 - 20), f"{gap:.2f}%p", fgap, GOLD)

    SZ = 54
    ys = {"미국": yu, "한국": yk}
    if abs(yu - yk) < SZ + 6:
        mid = (yu + yk) / 2
        hi = "미국" if us[-1][1] >= kr[-1][1] else "한국"
        lo = "한국" if hi == "미국" else "미국"
        ys = {hi: mid - (SZ + 6) / 2, lo: mid + (SZ + 6) / 2}
    fv = F("bold", 32)
    for name, ring, val in (("미국", "#E6DFCE", us[-1][1]), ("한국", "#6E90D0", kr[-1][1])):
        bx = W - MX - SZ
        b = flags.circle(name, SZ, ring=ring, ring_w=3)
        img.paste(b, (int(bx), int(ys[name] - SZ // 2)), b)
        dd = ImageDraw.Draw(img)
        up = val >= min(us[-1][1], kr[-1][1]) if us[-1][1] != kr[-1][1] else True
        if val == max(us[-1][1], kr[-1][1]):        # 위쪽 선은 글자를 위로, 아래쪽 선은 아래로
            dd.text((bx + SZ / 2, ys[name] - SZ / 2 - 8), f"{val:.2f}", font=fv, fill=ring, anchor="mb")
        else:
            dd.text((bx + SZ / 2, ys[name] + SZ / 2 + 8), f"{val:.2f}", font=fv, fill=ring, anchor="mt")
    d = ImageDraw.Draw(img)

    T(d, (MX, 1170), "가운데 띠 = 한미 금리 차이 · 자료: 한국은행 ECOS · FRED", F("light", 26), "#6E6E6E")
    _footer(d, img, settings)
    return img
