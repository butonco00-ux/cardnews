"""보도자료 표를 카드 안에 새로 그린다(칸 글자는 원문 그대로).

- 상자형(2칸×2줄, 둘째 줄 오른쪽이 빈 칸): 대표 사례 상자 → "제목 줄 + 설명"으로 그림
- 일반 표: 칸 너비를 글자 양에 맞춰 나누고, 첫 줄은 머리글, 줄 사이 가는 선
- 한 카드보다 길면 여러 장으로 나눔(머리글 반복). 5칸보다 넓으면 그리지 않고 "(표 생략)".
카드 항목의 글자는 "⟦표N⟧" 또는 "⟦표N:시작-끝⟧"(줄 번호, 머리글 제외) 형태로 표를 가리킨다.
"""
from __future__ import annotations

import re

_CURRENT: list[list[list[str]]] = []

MARK = re.compile(r"^⟦표(\d+)(?::(\d+)-(\d+))?⟧$")
MAX_COLS = 5
CELL_SIZE = 29
HEAD_SIZE = 29
PAD_X, PAD_Y = 14, 12
BOX_TITLE = 33
BOX_BODY = 33


def set_current(tables: list[list[list[str]]] | None) -> None:
    global _CURRENT
    _CURRENT = tables or []


def parse(text: str):
    m = MARK.match(text.strip())
    if not m:
        return None
    n = int(m.group(1))
    if not 1 <= n <= len(_CURRENT):
        return None
    rows = _CURRENT[n - 1]
    if m.group(2):
        a, b = int(m.group(2)), int(m.group(3))
        return n, rows, a, b
    return n, rows, 1, len(rows) - 1


def is_box(rows: list[list[str]]) -> bool:
    return (len(rows) == 2 and len(rows[0]) == 2 and rows[1][0] and not (rows[1][1] or "").strip())


def cells(text: str) -> list[str]:
    """원문 대조용: 이 항목이 그리는 칸 글자들."""
    p = parse(text)
    if not p:
        return []
    n, rows, a, b = p
    use = [rows[0]] + rows[a:b + 1] if not is_box(rows) else rows
    return [c for r in use for c in r if c]


def too_wide(text: str) -> bool:
    p = parse(text)
    return bool(p) and not is_box(p[1]) and max(len(r) for r in p[1]) > MAX_COLS


# ------------------------------------------------------------ 배치 계산

def _widths(rows, total: float, font_fn=None) -> list[float]:
    """칸 너비: 각 칸의 '끊으면 안 되는 가장 긴 덩어리'(숫자·짧은 단어·머리글)는 한 줄에 들어가게 하고,
    남는 폭은 글자 양에 비례해 나눈다."""
    ncol = max(len(r) for r in rows)
    f_head = font_fn("semibold", HEAD_SIZE) if font_fn else None
    f_cell = font_fn("regular", CELL_SIZE) if font_fn else None
    need = [0.0] * ncol
    minw = [0.0] * ncol
    for ri, r in enumerate(rows):
        f = f_head if ri == 0 else f_cell
        for i, c in enumerate(r):
            c = c or ""
            need[i] = max(need[i], min(len(c), 40))
            if f is None:
                continue
            short = c if (ri == 0 and len(c) <= 6) else ""
            tokens = [short] + re.findall(r"[\d,.%]+[가-힣%]*|\S{1,5}", c) if c else [short]
            longest = max((f.getlength(t) for t in tokens if t), default=0)
            minw[i] = max(minw[i], longest + PAD_X * 2 + 2)
    base = sum(minw)
    if base >= total:                      # 최소 너비만으로도 꽉 차면 비율대로 줄임
        return [m * total / base for m in minw] if base else [total / ncol] * ncol
    need = [max(n, 1) for n in need]
    rest = total - base
    s = sum(need)
    return [m + rest * n / s for m, n in zip(minw, need)]


def _grid_rows(rows, a, b, width, font_fn, wrap):
    head_f = font_fn("semibold", HEAD_SIZE)
    cell_f = font_fn("regular", CELL_SIZE)
    widths = _widths(rows, width, font_fn)
    out = []
    for idx in [0] + list(range(a, b + 1)):
        r = rows[idx]
        f = head_f if idx == 0 else cell_f
        lines = [wrap(c or "", f, int(w - PAD_X * 2)) if c else [""] for c, w in zip(r + [""] * (len(widths) - len(r)), widths)]
        h = max(len(ls) for ls in lines) * int(f.size * 1.42) + PAD_Y * 2
        out.append((idx, f, lines, h))
    return widths, out


def height(text: str, width: int, font_fn, wrap) -> int:
    p = parse(text)
    if not p:
        return 0
    n, rows, a, b = p
    if is_box(rows):
        tf, bf = font_fn("bold", BOX_TITLE), font_fn("regular", BOX_BODY)
        title = " — ".join(c for c in rows[0] if c)
        h = len(wrap(title, tf, width - 48)) * int(BOX_TITLE * 1.4)
        h += len(wrap(rows[1][0], bf, width - 48)) * int(BOX_BODY * 1.48)
        return h + 30 + 36
    if too_wide(text):
        return int(31 * 1.5)
    _, rs = _grid_rows(rows, a, b, width, font_fn, wrap)
    return sum(h for *_, h in rs) + 4


def split(text: str, max_h: int, width: int, font_fn, wrap) -> list[str]:
    """한 카드에 안 들어가는 일반 표를 줄 단위로 나눈다(머리글은 매 장 반복)."""
    p = parse(text)
    if not p or is_box(p[1]) or too_wide(text):
        return [text]
    n, rows, a, b = p
    _, rs = _grid_rows(rows, a, b, width, font_fn, wrap)
    head_h = rs[0][3]
    parts, start, used = [], a, head_h
    for idx, f, lines, h in rs[1:]:
        if used + h > max_h and idx > start:
            parts.append(f"⟦표{n}:{start}-{idx - 1}⟧")
            start, used = idx, head_h
        used += h
    parts.append(f"⟦표{n}:{start}-{b}⟧")
    return parts


# ------------------------------------------------------------ 그리기

def draw(d, text: str, x: int, y: int, width: int, c: dict, font_fn, wrap, tdraw, draw_hl, buto: bool) -> int:
    p = parse(text)
    if not p:
        return y
    n, rows, a, b = p
    line = c.get("line", "#CCCCCC")
    ink = c.get("text", "#222222")
    sub_ink = c.get("text2", ink) if buto else ink
    if is_box(rows):
        tf, bf = font_fn("bold", BOX_TITLE), font_fn("regular", BOX_BODY)
        title = " — ".join(cc for cc in rows[0] if cc)
        tl = wrap(title, tf, width - 48)
        bl = wrap(rows[1][0], bf, width - 48)
        h = len(tl) * int(BOX_TITLE * 1.4) + len(bl) * int(BOX_BODY * 1.48) + 30 + 36
        d.rounded_rectangle((x, y, x + width, y + h), radius=18, fill=c.get("box", "#FFFFFF"), outline=line, width=2)
        yy = y + 22
        for ln in tl:
            tdraw(d, (x + 24, yy), ln, tf, c.get("accent", ink) if not buto else ink)
            yy += int(BOX_TITLE * 1.4)
        yy += 8
        for ln in bl:
            draw_hl(d, (x + 24, yy), ln, bf, sub_ink, c.get("accent", ink))
            yy += int(BOX_BODY * 1.48)
        return y + h
    if too_wide(text):
        f = font_fn("medium", 31)
        tdraw(d, (x, y), "(표 생략 — 원문 링크에서 확인하세요)", f, c.get("sub", "#888888"))
        return y + int(31 * 1.5)
    widths, rs = _grid_rows(rows, a, b, width, font_fn, wrap)
    yy = y
    d.rectangle((x, yy, x + width, yy + 2), fill=ink)                  # 표 위 굵은 선
    for idx, f, lines, h in rs:
        xx = x
        for ls, w in zip(lines, widths):
            ty = yy + PAD_Y
            for ln in ls:
                if idx == 0:
                    tdraw(d, (xx + PAD_X, ty), ln, f, ink)
                else:
                    draw_hl(d, (xx + PAD_X, ty), ln, f, sub_ink, c.get("accent", ink))
                ty += int(f.size * 1.42)
            xx += w
        yy += h
        d.rectangle((x, yy, x + width, yy + 1), fill=line)
    return yy + 4
