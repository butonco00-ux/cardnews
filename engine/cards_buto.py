"""스타일 2 (Buto): 밝은 회색 배경 · 검정 굵은 제목 · 노란 형광펜 · 검정 날짜 상자 · 아래 구분선과 로고.

본문 글 크기·줄 간격은 스타일 1과 같게 둬서 카드 나누기(장 수)가 두 스타일에서 똑같다.
글자는 넘겨받은 그대로 그린다.
"""
from __future__ import annotations

from datetime import date

from PIL import Image, ImageDraw

from .cards import (BODY_BOTTOM, BODY_TOP, BODY_W, H, HIGHLIGHT, MX, W, Item, _draw_circled, _fit_lines,
                    _item_layout, font, tdraw, tlen, wrap)

BG = "#EDEBE8"
INK = "#111111"
SUB = "#3A3A3A"
MUTED = "#6B6B6B"
YELLOW = "#EEEA5E"
RULE = "#9A9A9A"

FOOTER_Y = 1222


def _c(settings: dict) -> dict:
    b = settings.get("buto") or {}
    return {"bg": b.get("bg", BG), "ink": b.get("ink", INK), "sub": b.get("sub", SUB), "muted": b.get("muted", MUTED),
            "yellow": b.get("yellow", YELLOW), "rule": b.get("rule", RULE)}


def _new(c) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), c["bg"])
    return img, ImageDraw.Draw(img)


def _footer(d, c, settings: dict, page: int | None = None, total: int | None = None) -> None:
    d.rectangle((0, FOOTER_Y, W, FOOTER_Y + 2), fill=c["rule"])
    note = settings.get("footer_note", "저작권 보호를 위해 무단 복제 및 배포를 삼가 주시기 바랍니다.")
    brand = settings.get("brand_name") or settings.get("account_name") or ""
    fb = font("black", 54)
    right = W - 64
    if brand:
        bw = tlen(brand, fb)
        tdraw(d, (right - bw, FOOTER_Y + 34), brand, fb, c["ink"])
        right -= bw + 30
    if page and total:
        # 쪽 번호는 구분선 위, 로고 바로 위(오른쪽 맞춤)
        fp = font("light", 28)
        label = f"{page}/{total}"
        tdraw(d, (W - 64 - tlen(label, fp), FOOTER_Y - 48), label, fp, c["muted"])
    if note:
        fn = font("light", 27)
        line = wrap(note, fn, right - 64)[0]
        tdraw(d, (64, FOOTER_Y + 50), line, fn, c["sub"])


def _tag(d, c, x: int, y: int, text: str, size: int = 38) -> int:
    f = font("bold", size)
    tw = tlen(text, f)
    h = int(size * 1.55)
    d.rectangle((x, y, x + tw + size * 0.9, y + h), fill=c["ink"])
    tdraw(d, (x + size * 0.45, y + (h - size * 1.2) / 2), text, f, "#FFFFFF")
    return y + h


def _headline(d, c, x: int, y: int, text: str, sizes: range, max_lines: int, width: int = BODY_W + 40) -> int:
    """큰 제목. 숫자가 든 줄(없으면 첫 줄)에 노란 형광펜."""
    f, lines, size = _fit_lines(text, "extrabold", sizes, width, max_lines)
    lines = lines[:max_lines]
    mark = next((i for i, ln in enumerate(lines) if HIGHLIGHT.search(ln) and any(ch.isdigit() for ch in ln)), 0)
    lh = int(size * 1.3)
    for i, ln in enumerate(lines):
        if i == mark:
            d.rectangle((x - 6, y + size * 0.1, x + tlen(ln, f) + 6, y + size * 1.22), fill=c["yellow"])
        tdraw(d, (x, y), ln, f, c["ink"])
        y += lh
    return y


def _marked(d, c, xy, text: str, f, color) -> None:
    """숫자·금액·날짜 뒤에 노란 형광펜(글자는 그대로)."""
    x, y = xy
    pos = 0
    for m in HIGHLIGHT.finditer(text):
        if m.start() == m.end() or not any(ch.isdigit() for ch in m.group(0)):
            continue
        if m.start() > pos:
            x = tdraw(d, (x, y), text[pos:m.start()], f, color)
        seg = text[m.start():m.end()]
        w = tlen(seg, f)
        d.rectangle((x - 2, y + f.size * 0.18, x + w + 2, y + f.size * 1.2), fill=c["yellow"])
        x = tdraw(d, (x, y), seg, f, color)
        pos = m.end()
    if pos < len(text):
        tdraw(d, (x, y), text[pos:], f, color)


def _month_label(iso: str) -> str:
    d = date.fromisoformat(iso[:10].replace(".", "-"))
    return f"{d.year}년 {d.month}월 {d.day}일"


def _source_right(d, c, text: str, y: int = 1150) -> None:
    f = font("light", 34)
    tdraw(d, (W - 64 - tlen(text, f), y), text, f, c["sub"])


# ---------------------------------------------------------------- 정책·세금 세트

def draw_cover(meta: dict, settings: dict) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    x = 110
    y = _tag(d, c, x, 130, f"{meta.get('tag', '정책')} · {_month_label(meta.get('date_label', meta.get('date', '')))}")
    y = _headline(d, c, x, y + 28, meta["title"], range(104, 67, -4), 4)
    y += 26
    fs = font("light", 52)
    for sub in meta.get("subtitles", [])[:2]:
        for ln in wrap(sub, fs, W - x - 90)[:2]:
            tdraw(d, (x, y), ln, fs, c["sub"])
            y += 70
        y += 8
    if meta.get("badge"):
        fb = font("bold", 34)
        d.rectangle((x, y + 24, x + tlen(meta["badge"], fb) + 36, y + 24 + 58), outline=c["ink"], width=3)
        tdraw(d, (x + 18, y + 33), meta["badge"], fb, c["ink"])
    _source_right(d, c, f"출처 : {meta.get('dept', '')} 보도자료")
    _footer(d, c, settings)
    return img


def draw_body(items: list[Item], meta: dict, settings: dict, page: int, total: int) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    # 제목은 한 줄: 넘치면 글자를 줄이고(최소 30), 그래도 넘치면 끝을 … 로
    title = meta["title"]
    for size in range(50, 29, -2):
        ft = font("extrabold", size)
        if tlen(title, ft) <= BODY_W:
            break
    line = title
    if tlen(line, ft) > BODY_W:
        while tlen(line + "…", ft) > BODY_W and line:
            line = line[:-1]
        line += "…"
    tdraw(d, (MX, 120 - ft.size // 2), line, ft, c["ink"])

    y = BODY_TOP
    for i, it in enumerate(items):
        f, marker, mw, indent, wl, line_h, gap, color_key = _item_layout(it)
        if i:
            y += gap
        color = c["muted"] if color_key == "sub" else (c["ink"] if it.level in (0, "heading") else c["sub"])
        for j, ln in enumerate(wl):
            if j == 0 and marker:
                if not _draw_circled(d, MX + indent, y, marker, f, c["ink"]):
                    tdraw(d, (MX + indent, y), marker, f, c["ink"])
            if it.level == "system":
                tdraw(d, (MX + indent + mw, y), ln, f, c["muted"])
            elif it.level == "heading":
                d.rectangle((MX + indent + mw - 4, y + f.size * 0.12, MX + indent + mw + tlen(ln, f) + 4, y + f.size * 1.2),
                            fill=c["yellow"])
                tdraw(d, (MX + indent + mw, y), ln, f, c["ink"])
            else:
                _marked(d, c, (MX + indent + mw, y), ln, f, color)
            y += line_h
    _footer(d, c, settings, page, total)
    return img


def draw_source(meta: dict, settings: dict, page: int, total: int) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    x = 110
    y = _tag(d, c, x, 130, "출처")
    y += 60
    fb = font("bold", 44)
    for ln in wrap(f"{meta.get('dept', '')} 보도자료", fb, W - x - 90):
        tdraw(d, (x, y), ln, fb, c["ink"])
        y += 62
    fr = font("regular", 38)
    for ln in wrap(f"「{meta['title']}」 ({meta.get('date_label', '')})", fr, W - x - 90):
        tdraw(d, (x, y), ln, fr, c["sub"])
        y += 56
    y += 20
    fl = font("light", 34)
    for ln in ("대한민국 정책브리핑 www.korea.kr", meta.get("license_label", "공공누리 제1유형")):
        tdraw(d, (x, y), ln, fl, c["sub"])
        y += 50
    y += 30
    note = "카드의 글은 보도자료 원문 그대로이며, 일부 내용은 생략했을 수 있어요. 전체 내용은 캡션의 원문 링크에서 확인하세요."
    for ln in wrap(note, fl, W - x - 90):
        tdraw(d, (x, y), ln, fl, c["muted"])
        y += 50
    y = max(y + 50, 800)
    _office(d, c, settings, x, y)
    _footer(d, c, settings, page, total)
    return img


def _office(d, c, settings: dict, x: int, y: int) -> int:
    disc = settings.get("disclaimer") or "정보 제공용 콘텐츠입니다. 세금·대출은 반드시 전문가와 상담하세요."
    fd = font("bold", 34)
    lines = wrap(disc, fd, W - x - 90)
    d.rectangle((x - 6, y + 4, x + max(tlen(ln, fd) for ln in lines) + 6, y + 4 + 52 * len(lines)), fill=c["yellow"])
    for ln in lines:
        tdraw(d, (x, y), ln, fd, c["ink"])
        y += 52
    office = settings.get("office") or {}
    rows = [office.get("name"), office.get("ceo") and f"대표 {office['ceo']}",
            office.get("reg_no") and f"등록번호 {office['reg_no']}", office.get("phone"), office.get("address")]
    y += 24
    fl = font("light", 32)
    for r in [r for r in rows if r]:
        for ln in wrap(r, fl, W - x - 90):
            tdraw(d, (x, y), ln, fl, c["sub"])
            y += 46
    return y


# ---------------------------------------------------------------- 뉴스 헤드라인 세트

def draw_news_cover(date_label: str, count: int, settings: dict) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    x = 110
    y = _tag(d, c, x, 130, _month_label(date_label))
    y += 28
    f = font("extrabold", 116)
    for i, ln in enumerate(("오늘의", "부동산 뉴스")):
        if i == 1:
            d.rectangle((x - 6, y + 116 * 0.1, x + tlen(ln, f) + 6, y + 116 * 1.22), fill=c["yellow"])
        tdraw(d, (x, y), ln, f, c["ink"])
        y += 150
    y += 20
    tdraw(d, (x, y), f"헤드라인 {count}건", font("light", 56), c["sub"])
    fl = font("light", 32)
    yy = 1020
    for ln in wrap("기사는 제목과 언론사만 소개하고, 정부 발표가 있는 소식은 보도자료 원문을 함께 실었어요.", fl, W - x - 90):
        tdraw(d, (x, yy), ln, fl, c["muted"])
        yy += 46
    _footer(d, c, settings)
    return img


def draw_news_item(n: int, item: dict, note: str, settings: dict, page: int, total: int) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    x = 110
    y = _tag(d, c, x, 110, f"뉴스 {n:02d} · {item.get('date_label', '')[:10]}", 34)
    gov = item.get("gov")
    y = _headline(d, c, x, y + 24, item["title"], range(88, 55, -3), 3 if (gov or note) else 4)
    y += 14
    fs = font("light", 40)
    tdraw(d, (x, y), item.get("press", ""), fs, c["sub"])
    y += 80

    if gov:
        from .splitter import _sentences
        fl = font("bold", 32)
        tdraw(d, (x, y), f"정부 발표 원문 · {gov['dept']} ({gov['date_label']})", fl, c["ink"])
        y += 58
        fg = font("regular", 38)
        width = W - x - 90
        room = (BODY_BOTTOM - (140 if note else 0)) - y - 60
        max_lines = max(2, room // 58)
        sents = _sentences(gov["text"])
        while len(sents) > 1 and len(wrap(" ".join(sents), fg, width)) > max_lines:
            sents = sents[:-1]
        first_len = len(sents[0]) if sents else 0
        consumed = 0
        for ln in wrap(" ".join(sents), fg, width)[:max_lines]:
            if consumed < first_len:   # 첫 문장에 형광펜
                d.rectangle((x - 4, y + 38 * 0.14, x + tlen(ln, fg) + 4, y + 38 * 1.22), fill=c["yellow"])
            tdraw(d, (x, y), ln, fg, c["ink"])
            consumed += len(ln) + 1
            y += 58
        tdraw(d, (x, y + 6), f"{gov.get('license_label', '공공누리 제1유형')} · 정책브리핑", font("light", 26), c["muted"])
        y += 70

    if note:
        fb = font("bold", 32)
        tdraw(d, (x, y), settings.get("note_label") or "중개사 한마디", fb, c["ink"])
        y += 54
        fn = font("regular", 36)
        for ln in wrap(note, fn, W - x - 90)[:2]:
            tdraw(d, (x, y), ln, fn, c["sub"])
            y += 54

    _source_right(d, c, f"출처 : {item.get('press', '')}", y=1110)
    _footer(d, c, settings, page, total)
    return img


def draw_news_end(settings: dict, page: int, total: int) -> Image.Image:
    c = _c(settings)
    img, d = _new(c)
    x = 110
    y = _tag(d, c, x, 130, "알려드려요")
    y += 70
    fr = font("regular", 40)
    txt = ("이 카드는 기사 제목·언론사·날짜만 소개하며, 기사 내용의 저작권은 각 언론사에 있어요. "
           "'정부 발표 원문'은 정책브리핑(www.korea.kr) 보도자료를 공공누리 제1유형 조건에 따라 그대로 옮긴 거예요. "
           "자세한 내용은 캡션의 링크에서 확인하세요.")
    for ln in wrap(txt, fr, W - x - 90):
        tdraw(d, (x, y), ln, fr, c["sub"])
        y += 62
    _office(d, c, settings, x, max(y + 60, 760))
    _footer(d, c, settings, page, total)
    return img
