"""카드 그리기(Pillow). 1080×1350(4:5) JPEG.

글자는 넘겨받은 그대로 그린다(바꾸지 않음). 숫자·금액·날짜만 색으로 강조.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import FONTS

W, H = 1080, 1350
MX = 90                      # 좌우 여백
BODY_TOP = 250
BODY_BOTTOM = 1165
BODY_W = W - MX * 2

DEFAULT_COLORS = {
    "primary": "#9E9577",     # 표지 배경·태그
    "accent": "#955330",      # 숫자 강조·소제목
    "bg": "#F7F5F2",          # 본문 배경
    "text": "#2F2B28",
    "sub": "#827E79",
    "line": "#CEC1B6",
    "badge": "#F2C94C",
    "badge_text": "#2F2B28",
    "cover_text": "#FFFFFF",      # 표지 글자
    "cover_sub": "#FFFFFFDD",     # 표지 부제·설명
    "on_primary": "#FFFFFF",      # 주색 위 글자(태그)
    "box": "#FFFFFF",             # 정부 발표·한마디 상자
}

WEIGHTS = {
    "light": "Pretendard-Light.otf",
    "regular": "Pretendard-Regular.otf",
    "medium": "Pretendard-Medium.otf",
    "semibold": "Pretendard-SemiBold.otf",
    "bold": "Pretendard-Bold.otf",
    "extrabold": "Pretendard-ExtraBold.otf",
    "black": "Pretendard-Black.otf",
}


@lru_cache(maxsize=None)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / WEIGHTS[weight]), size)


# ---------------------------------------------------------------- 글꼴에 없는 글자
# Pretendard 에 없는 글자(｢｣ 같은 반각 괄호, 한자 同 등)는 모양만 대신 그린다(저장된 글자는 원문 그대로).
import unicodedata

FALLBACK_PATHS = [
    FONTS / "fallback.otf",
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("C:/Windows/Fonts/malgun.ttf"),
]


@lru_cache(maxsize=None)
def _notdef() -> bytes:
    return bytes(font("regular", 40).getmask("͸"))


@lru_cache(maxsize=None)
def _has(ch: str) -> bool:
    if ch.isspace() or ord(ch) < 128:
        return True
    return bytes(font("regular", 40).getmask(ch)) != _notdef()


@lru_cache(maxsize=None)
def _fallback(size: int):
    for p in FALLBACK_PATHS:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    return None


# 글꼴에 없고 대신 그릴 글꼴도 없는 기호 → 비슷한 모양으로만 그림
DRAW_AS = {"▸": "▶", "▹": "▷", "►": "▶", "▪": "■", "▫": "□", "‣": "▶"}


def _runs(text: str, f):
    """(글자들, 그릴 글꼴, 그릴 글자) 조각으로 나눈다."""
    out = []
    for ch in text:
        if _has(ch):
            item = (f, ch)
        elif ch in DRAW_AS and _has(DRAW_AS[ch]):
            item = (f, DRAW_AS[ch])
        else:
            alt = unicodedata.normalize("NFKC", ch)
            if alt != ch and all(_has(a) for a in alt):
                item = (f, alt)
            else:
                fb = _fallback(f.size)
                item = (fb, ch) if fb else (f, ch)
        if out and out[-1][0] is item[0]:
            out[-1][1] += item[1]
        else:
            out.append([item[0], item[1]])
    return out


def tlen(text: str, f) -> float:
    return sum(ff.getlength(t) for ff, t in _runs(text, f))


def tdraw(d, xy, text: str, f, fill) -> float:
    x, y = xy
    for ff, t in _runs(text, f):
        dy = 0
        if ff is not f:
            dy = (f.getbbox("가")[1] - ff.getbbox("가")[1])
        d.text((x, y + dy), t, font=ff, fill=fill)
        x += ff.getlength(t)
    return x


# 본문 줄 종류별 모양
STYLES = {
    # level: (weight, size, indent, color_key, gap_before)
    "heading": ("bold", 46, 0, "accent", 34),
    0: ("semibold", 42, 0, "text", 30),
    1: ("regular", 39, 34, "text", 18),
    2: ("regular", 37, 72, "text", 12),
    "note": ("regular", 31, 72, "sub", 10),
    "system": ("medium", 31, 0, "sub", 24),
    "table": ("regular", 29, 0, "text", 26),     # 표(높이는 tables 모듈이 계산)
}
LINE_SPACING = 1.52

HIGHLIGHT = re.compile(
    r"[’‘']?\d[\d,.]*\s*(?:%p|％p|%|％|조\s*원|억\s*원|만\s*원|천\s*원|원|조|억|만|천|"
    r"년|개월|월|일|개|호|층|㎡|평|건|명|배|세대|가구|호실|채|곳|시간|분|주|차|회|km|m|p)?"
)


def colors_from(settings: dict) -> dict:
    c = dict(DEFAULT_COLORS)
    c.update({k: v for k, v in (settings.get("colors") or {}).items() if v})
    return c


# ---------------------------------------------------------------- 줄바꿈

def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """띄어쓰기 단위로 줄바꿈. 한 단어가 너무 길면 글자 단위."""
    lines: list[str] = []
    cur = ""
    for tok in re.split(r"(\s+)", text):
        if not tok:
            continue
        if tok.isspace():
            if cur:
                cur += " "
            continue
        cand = cur + tok
        if tlen(cand, f) <= width:
            cur = cand
            continue
        if cur.strip():
            lines.append(cur.rstrip())
        cur = ""
        if tlen(tok, f) <= width:
            cur = tok
        else:
            for ch in tok:
                if tlen(cur + ch, f) > width and cur:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


@dataclass
class Item:
    """본문 한 줄(원문 한 항목)."""
    level: object          # "heading" | 0 | 1 | 2 | "note" | "system"
    marker: str
    text: str
    cont: bool = False     # 앞 카드에서 이어지는 문장(기호 생략)

    def to_dict(self) -> dict:
        return {"level": self.level, "marker": self.marker, "text": self.text, "cont": self.cont}

    @staticmethod
    def from_dict(d: dict) -> "Item":
        return Item(d["level"], d.get("marker", ""), d["text"], d.get("cont", False))


def _item_layout(item: Item):
    weight, size, indent, color_key, gap = STYLES[item.level]
    f = font(weight, size)
    marker = "" if item.cont else item.marker
    if marker and _circled_number(marker):
        mw = int(size * 0.92 + f.getlength(" ") + 4)
    else:
        mw = int(f.getlength(marker + " ")) if marker else 0
    width = BODY_W - indent - mw
    lines = wrap(item.text, f, width)
    line_h = int(size * LINE_SPACING)
    return f, marker, mw, indent, lines, line_h, gap, color_key


def item_height(item: Item, first: bool) -> int:
    if item.level == "table":
        from . import tables
        return (0 if first else STYLES["table"][4]) + tables.height(item.text, BODY_W, font, wrap)
    _, _, _, _, lines, line_h, gap, _ = _item_layout(item)
    return (0 if first else gap) + line_h * len(lines)


def items_height(items: list[Item]) -> int:
    return sum(item_height(it, i == 0) for i, it in enumerate(items))


BODY_H = BODY_BOTTOM - BODY_TOP


# ---------------------------------------------------------------- 그리기 도우미

def _buto(settings: dict) -> bool:
    """스타일 2: 1번 배치 + Buto 색(회색 바탕·검정 글씨·노란 형광펜·검정 상자) + Buto 아래쪽."""
    return settings.get("variant") == "buto"


def _draw_highlighted(d: ImageDraw.ImageDraw, xy, text: str, f, color, accent, mark: str | None = None):
    """숫자·금액·날짜 강조. mark(형광펜 색)가 있으면 글자색 대신 뒤에 형광펜."""
    x, y = xy
    pos = 0
    for m in HIGHLIGHT.finditer(text):
        if m.start() == m.end():
            continue
        if m.start() > pos:
            x = tdraw(d, (x, y), text[pos:m.start()], f, color)
        seg = text[m.start():m.end()]
        if mark:
            if any(ch.isdigit() for ch in seg):
                d.rectangle((x - 2, y + f.size * 0.16, x + tlen(seg, f) + 2, y + f.size * 1.2), fill=mark)
            x = tdraw(d, (x, y), seg, f, color)
        else:
            x = tdraw(d, (x, y), seg, f, accent)
        pos = m.end()
    if pos < len(text):
        tdraw(d, (x, y), text[pos:], f, color)


def _circled_number(marker: str) -> tuple[int, bool] | None:
    """➊❶(채운 동그라미)·①(빈 동그라미) → (숫자, 채움). 글꼴에 ➊ 모양이 없어 직접 그린다."""
    o = ord(marker[0]) if marker else 0
    if 0x278A <= o <= 0x2793:
        return o - 0x278A + 1, True
    if 0x2776 <= o <= 0x277F:
        return o - 0x2776 + 1, True
    if 0x2460 <= o <= 0x2473:
        return o - 0x2460 + 1, False
    return None


def _draw_circled(d, x, y, marker, f, color) -> bool:
    cn = _circled_number(marker)
    if not cn:
        return False
    n, filled = cn
    size = f.size
    r = size * 0.46
    cx, cy = x + r + 1, y + size * 0.62
    if filled:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        d.text((cx, cy), str(n), font=font("bold", int(size * 0.62)), fill="#FFFFFF", anchor="mm")
    else:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=max(2, size // 16))
        d.text((cx, cy), str(n), font=font("bold", int(size * 0.58)), fill=color, anchor="mm")
    return True


def _fit_lines(text: str, weight: str, sizes: range, width: int, max_lines: int):
    for size in sizes:
        f = font(weight, size)
        lines = wrap(text, f, width)
        if len(lines) <= max_lines:
            return f, lines, size
    f = font(weight, sizes[-1])
    return f, wrap(text, f, width), sizes[-1]


def _pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, f, fill, fg, outline=None) -> int:
    tw = f.getlength(text)
    h = int(f.size * 1.9)
    d.rounded_rectangle((x, y, x + tw + f.size * 1.4, y + h), radius=h // 2, fill=fill, outline=outline, width=2)
    d.text((x + f.size * 0.7, y + h / 2), text, font=f, fill=fg, anchor="lm")
    return int(x + tw + f.size * 1.4)


def _fin(settings: dict) -> dict:
    """스타일 2 마감 옵션(settings["finish"]): editorial(얇은 선·라벨), mark("box"|"under"), cover_dark."""
    return settings.get("finish") or {} if _buto(settings) else {}


def _mark(d, c, settings: dict, x: float, y: float, w: float, size: float) -> None:
    """형광펜. under 이면 글자 아래쪽 절반만 칠해 더 단정하게."""
    if _fin(settings).get("cover_dark") and c.get("bg") == c.get("dark_bg", "#171717"):
        # 어두운 표지: 형광펜 대신 글자 아래 노란 밑줄(흰 글자가 잘 읽히게)
        d.rectangle((x, y + size * 1.14, x + w, y + size * 1.14 + max(5, size // 12)), fill=c["mark"])
    elif _fin(settings).get("mark") == "under":
        d.rectangle((x - 4, y + size * 0.66, x + w + 4, y + size * 1.16), fill=c["mark"])
    else:
        d.rectangle((x - 6, y + size * 0.1, x + w + 6, y + size * 1.22), fill=c["mark"])


def _dark_cover(c: dict, settings: dict) -> dict:
    """표지만 어둡게(다크 표지 옵션)."""
    if not _fin(settings).get("cover_dark"):
        return c
    c = dict(c)
    c["dark_bg"] = c.get("dark_bg", "#171717")
    c.update(bg=c["dark_bg"], cover_text="#F3F0EA", cover_sub="#B9B3A8", text="#F3F0EA",
             sub="#9D978D", line="#3A3835", primary="#F3F0EA", on_primary="#171717")
    return c


def _tag(d, c, settings: dict, x: int, y: int, text: str, size: int, cover: bool) -> None:
    """분야 태그. 스타일 1은 둥근 알약, 스타일 2는 검정 네모 상자."""
    f = font("bold", size)
    if _buto(settings) and _fin(settings).get("editorial"):
        # 잡지식 라벨: 글자 사이를 넓힌 굵은 글씨 + 가는 선
        fl = font("bold", int(size * 1.1))
        xx = x
        for ch in text:
            tdraw(d, (xx, y + size * 0.35), ch, fl, c["text"] if not cover else c["cover_text"])
            xx += tlen(ch, fl) + size * 0.22
        yy = y + size * 0.35 + fl.size * 0.62
        d.rectangle((xx + 16, yy, xx + 16 + 110, yy + 2), fill=c["cover_text"] if cover else c["text"])
    elif _buto(settings):
        _pill(d, x, y, text, f, c["primary"], c["on_primary"])   # 1번과 같은 둥근 모양, 검정 바탕
    elif cover:
        _pill(d, x, y, text, f, None, c["cover_text"], outline=c["cover_text"])
    else:
        _pill(d, x, y, text, f, c["primary"], c["on_primary"])


def _title_lines(d, c, settings: dict, x: int, y: int, lines: list[str], f, size: int, lh: int, color) -> int:
    """표지 큰 제목. 스타일 2는 숫자가 든 줄(없으면 첫 줄)에 노란 형광펜."""
    mark = -1
    if _buto(settings):
        mark = next((i for i, ln in enumerate(lines) if any(ch.isdigit() for ch in ln)), 0)
    for i, ln in enumerate(lines):
        if i == mark:
            _mark(d, c, settings, x, y, tlen(ln, f), size)
        tdraw(d, (x, y), ln, f, color)
        y += lh
    return y


BUTO_FOOTER_Y = 1222


def _buto_footer(d, c, settings: dict, page: int | None, total: int | None, source_short: str) -> None:
    fl = font("light", 28)
    ed = _fin(settings).get("editorial")
    if source_short:
        tdraw(d, (MX, BUTO_FOOTER_Y - 48), source_short, fl, c["sub"])
    if page and total:
        label = f"{page:02d} / {total:02d}" if ed else f"{page}/{total}"
        fp = font("medium", 26) if ed else fl
        tdraw(d, (W - 64 - tlen(label, fp), BUTO_FOOTER_Y - 48), label, fp, c["sub"])
    d.rectangle((0, BUTO_FOOTER_Y, W, BUTO_FOOTER_Y + (1 if ed else 2)), fill=c["line"])
    brand = settings.get("brand_name") or settings.get("account_name") or ""
    right = W - 64
    if brand:
        fb = font("black", 54)
        bw = tlen(brand, fb)
        tdraw(d, (right - bw, BUTO_FOOTER_Y + 34), brand, fb, c["text"])
        right -= bw + 30
    note = settings.get("footer_note", "")
    if note:
        fn = font("light", 27)
        tdraw(d, (64, BUTO_FOOTER_Y + 50), wrap(note, fn, right - 64)[0], fn, c["sub"])


def _footer(d, c, settings: dict, page: int | None, total: int | None, source_short: str):
    if _buto(settings):
        _buto_footer(d, c, settings, page, total, source_short)
        return
    f = font("medium", 26)
    d.line((MX, 1215, W - MX, 1215), fill=c["line"], width=2)
    account = settings.get("account_name") or ""
    if account:
        d.text((MX, 1262), account, font=f, fill=c["sub"], anchor="lm")
    right = source_short
    if page and total:
        right = f"{source_short}   {page} / {total}" if source_short else f"{page} / {total}"
    if right:
        d.text((W - MX, 1262), right, font=f, fill=c["sub"], anchor="rm")


def _new(bg) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img)


def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=90, optimize=True, progressive=False)


# ---------------------------------------------------------------- 정책·세금 세트

def draw_cover(meta: dict, settings: dict) -> Image.Image:
    c = colors_from(settings)
    buto = _buto(settings)
    if buto:
        c = _dark_cover(c, settings)
    img, d = _new(c["bg"] if buto else c["primary"])
    x = MX
    _tag(d, c, settings, x, 110, meta.get("tag", "정책"), 32, cover=True)

    # 표지 제목은 피드에서도 잘 보이게 크게(2026-09-20 사용자 요청: 86 → 최대 128)
    f, lines, size = _fit_lines(meta["title"], "extrabold", range(128, 79, -4), BODY_W, 4)
    y = _title_lines(d, c, settings, x, 250, lines, f, size, int(size * 1.26), c["cover_text"])

    y += 30
    fs = font("medium", 38)
    stop = 1000 if meta.get("badge") else 1060          # 아래 발표처 줄과 겹치지 않게
    for sub in meta.get("subtitles", [])[:3]:
        sub_lines = wrap(sub, fs, BODY_W - 40)
        if y + len(sub_lines) * 56 > stop:
            break
        for ln in sub_lines:
            tdraw(d, (x, y), ln, fs, c["cover_sub"])
            y += 56
        y += 10

    if meta.get("badge"):
        _pill(d, x, max(960, min(y + 10, 1000)), meta["badge"], font("bold", 32), c["badge"], c["badge_text"])

    fd = font("bold", 44)
    tdraw(d, (x, 1090), f"{meta.get('dept', '')}  |  {meta.get('date_label', '')}", fd, c["cover_text"])
    if buto:
        _buto_footer(d, c, settings, None, None, "")
        return img
    account = settings.get("account_name") or ""
    if account:
        d.text((x, 1250), account, font=font("medium", 28), fill=c["cover_sub"], anchor="lm")
    d.text((W - MX, 1250), "보도자료 원문", font=font("medium", 28), fill=c["cover_sub"], anchor="rm")
    return img


def draw_body(items: list[Item], meta: dict, settings: dict, page: int, total: int) -> Image.Image:
    c = colors_from(settings)
    img, d = _new(c["bg"])
    _tag(d, c, settings, MX, 90, meta.get("tag", "정책"), 28, cover=False)
    ft = font("semibold", 30)
    title_line = wrap(meta["title"], ft, BODY_W)[0]
    if title_line != meta["title"]:
        while ft.getlength(title_line + "…") > BODY_W and title_line:
            title_line = title_line[:-1]
        title_line += "…"
    tdraw(d, (MX, 175), title_line, ft, c["sub"])

    y = BODY_TOP
    for i, it in enumerate(items):
        if it.level == "table":
            from . import tables
            if i:
                y += STYLES["table"][4]
            y = tables.draw(d, it.text, MX, y, BODY_W, c, font, wrap, tdraw,
                            _draw_highlighted, _buto(settings))
            continue
        f, marker, mw, indent, lines, line_h, gap, color_key = _item_layout(it)
        if i:
            y += gap
        color = c[color_key]
        if _buto(settings) and it.level in (1, 2):
            color = c.get("text2", color)     # 스타일 2: 본문은 짙은 회색, 숫자만 검정
        for j, ln in enumerate(lines):
            if j == 0 and marker:
                mcolor = c["accent"] if it.level in (0, "heading") else color
                if not _draw_circled(d, MX + indent, y, marker, f, mcolor):
                    tdraw(d, (MX + indent, y), marker, f, mcolor)
            if it.level == "system":
                tdraw(d, (MX + indent + mw, y), ln, f, color)
            else:
                _draw_highlighted(d, (MX + indent + mw, y), ln, f, color, c["accent"])
            y += line_h
    _footer(d, c, settings, page, total, meta.get("source_label") or f"출처: {meta.get('dept', '')} 보도자료")
    return img


def draw_source(meta: dict, settings: dict, page: int, total: int) -> Image.Image:
    c = colors_from(settings)
    img, d = _new(c["bg"])
    y = 130
    d.text((MX, y), "출처", font=font("bold", 50), fill=c["text"])
    y += 100
    fb = font("regular", 36)
    label = "보도자료 " if meta.get("kind", "policy") == "policy" else ""
    src = f"{meta.get('dept', '')} {label}「{meta['title']}」({meta.get('date_label', '')})"
    for ln in wrap(src, fb, BODY_W):
        tdraw(d, (MX, y), ln, fb, c["text"])
        y += 56
    # 정책브리핑 주소·공공누리·면책 문구는 카드에서 빼고 캡션에만 둔다(사용자 요청)
    _office_rows(d, c, settings, max(y + 60, 760))
    _footer(d, c, settings, page, total, "")
    return img


def _disclaimer_and_office(d, c, settings: dict, y: int) -> int:
    disc = settings.get("disclaimer") or "정보 제공용 콘텐츠입니다. 세금·대출은 반드시 전문가와 상담하세요."
    for ln in wrap(disc, font("medium", 32), BODY_W):
        tdraw(d, (MX, y), ln, font("medium", 32), c["text"])
        y += 50
    return _office_rows(d, c, settings, y)


def _office_rows(d, c, settings: dict, y: int) -> int:
    """중개사무소 정보(설정에 넣었을 때만)."""
    office = settings.get("office") or {}
    rows = [office.get("name"), office.get("ceo") and f"대표 {office['ceo']}",
            office.get("reg_no") and f"등록번호 {office['reg_no']}",
            office.get("phone"), office.get("address")]
    rows = [r for r in rows if r]
    if rows:
        y += 30
        for r in rows:
            for ln in wrap(r, font("regular", 30), BODY_W):
                tdraw(d, (MX, y), ln, font("regular", 30), c["sub"])
                y += 46
    return y


# ---------------------------------------------------------------- 뉴스 헤드라인 세트

def draw_news_cover(date_label: str, count: int, settings: dict, cover: dict | None = None) -> Image.Image:
    c = colors_from(settings)
    buto = _buto(settings)
    if buto:
        c = _dark_cover(c, settings)
    img, d = _new(c["bg"] if buto else c["primary"])
    cover = cover or {}
    _tag(d, c, settings, MX, 110, cover.get("tag", "뉴스"), 32, cover=True)
    f = font("extrabold", 140)                  # 피드에서 잘 보이게(104 → 140)
    y = 300
    for i, ln in enumerate(cover.get("lines") or ("오늘의", "부동산 뉴스")):
        if buto and i == 1:
            _mark(d, c, settings, MX, y, tlen(ln, f), 140)
        tdraw(d, (MX, y), ln, f, c["cover_text"])
        y += 176
    count_label = (cover.get("count_label") or "헤드라인 {n}건").replace("{n}", str(count))
    d.text((MX, y + 40), f"{date_label}  |  {count_label}", font=font("bold", 44), fill=c["cover_text"])
    note = cover.get("note")
    if note is None:
        note = "기사는 제목과 언론사만 소개하고, 정부 발표가 있는 소식은 보도자료 원문을 함께 실었어요."
    y = 1010
    for ln in wrap(note, font("medium", 32), BODY_W):
        tdraw(d, (MX, y), ln, font("medium", 32), c["cover_sub"])
        y += 50
    if buto:
        _buto_footer(d, c, settings, None, None, "")
        return img
    account = settings.get("account_name") or ""
    if account:
        d.text((MX, 1250), account, font=font("medium", 28), fill=c["cover_sub"], anchor="lm")
    return img


def draw_news_item(n: int, item: dict, note: str, settings: dict, page: int, total: int) -> Image.Image:
    c = colors_from(settings)
    img, d = _new(c["bg"])
    d.text((MX, 120), f"{n:02d}", font=font("extrabold", 96), fill=c.get("number") or c["primary"])
    gov = item.get("gov")
    summary = item.get("summary") or []
    max_title_lines = 3 if summary else (4 if (gov or note) else 5)
    f, lines, size = _fit_lines(item["title"], "bold", range(58, 41, -3), BODY_W, max_title_lines)
    y = 290
    for ln in lines[:max_title_lines]:
        tdraw(d, (MX, y), ln, f, c["text"])
        y += int(size * 1.36)
    y += 20
    tdraw(d, (MX, y), f"{item.get('press', '')}  ·  {item.get('date_label', '')}", font("medium", 32), c["sub"])
    y += 80

    if summary:
        # AI 사실 정리(새로 쓴 문장). 기사 문장이 아님을 표시한다.
        fs = font("regular", 35)
        room = (BODY_BOTTOM - (150 if note else 0)) - y - 60
        lines_out = []
        for sent in summary:
            lines_out += wrap(sent, fs, BODY_W)
        max_l = max(3, room // 54)
        if len(lines_out) > max_l:                      # 넘치면 뒤 문장부터 뺀다
            keep = list(summary)
            while len(keep) > 1 and sum(len(wrap(s_, fs, BODY_W)) for s_ in keep) > max_l:
                keep = keep[:-1]
            lines_out = [ln for s_ in keep for ln in wrap(s_, fs, BODY_W)]
        for ln in lines_out:
            _draw_highlighted(d, (MX, y), ln, fs, c.get("text2", c["text"]) if _buto(settings) else c["text"], c["accent"])
            y += 54
        y += 20

    if gov and not summary:
        from .splitter import _sentences
        fg = font("regular", 34)
        label = f"정부 발표 원문 · {gov['dept']} ({gov['date_label']})"
        room = (BODY_BOTTOM - (150 if note else 0)) - y - 150
        max_lines = max(2, room // 52)
        sents = _sentences(gov["text"])
        while len(sents) > 1 and len(wrap(" ".join(sents), fg, BODY_W - 64)) > max_lines:
            sents = sents[:-1]          # 넘치면 뒤 문장을 뺀다(글자는 그대로)
        glines = wrap(" ".join(sents), fg, BODY_W - 64)[:max_lines]
        box_h = 76 + 52 * len(glines) + 60
        d.rounded_rectangle((MX, y, W - MX, y + box_h), radius=22, fill=c["box"], outline=c["primary"], width=3)
        tdraw(d, (MX + 32, y + 24), label, font("bold", 29), c["accent"])
        yy = y + 76
        for ln in glines:
            _draw_highlighted(d, (MX + 32, yy), ln, fg, c.get("text2", c["text"]) if _buto(settings) else c["text"], c["accent"])
            yy += 52
        tdraw(d, (MX + 32, yy + 8), f"{gov.get('license_label', '공공누리 제1유형')} · 정책브리핑", font("regular", 24), c["sub"])
        y += box_h + 26

    if note:
        fn = font("regular", 34)
        nl = wrap(note, fn, BODY_W - 60)[:3]
        box_h = 66 + 50 * len(nl) + 24
        if y + box_h > BODY_BOTTOM + 30:
            nl = nl[:1]
            box_h = 66 + 50 + 24
        d.rounded_rectangle((MX, y, W - MX, y + box_h), radius=22, fill=c["box"], outline=c["line"], width=2)
        d.text((MX + 30, y + 22), settings.get("note_label") or "중개사 한마디", font=font("bold", 28), fill=c["accent"])
        yy = y + 66
        for ln in nl:
            tdraw(d, (MX + 30, yy), ln, fn, c["text"])
            yy += 50
    _footer(d, c, settings, page, total, "")
    return img


def draw_news_end(settings: dict, page: int, total: int) -> Image.Image:
    c = colors_from(settings)
    img, d = _new(c["bg"])
    y = 130
    d.text((MX, y), "알려드려요", font=font("bold", 50), fill=c["text"])
    y += 110
    txt = ("이 카드는 기사 제목·언론사·날짜만 소개하며, 기사 내용의 저작권은 각 언론사에 있어요. "
           "'정부 발표 원문'은 정책브리핑(www.korea.kr) 보도자료를 공공누리 제1유형 조건에 따라 그대로 옮긴 거예요. "
           "자세한 내용은 캡션의 링크에서 확인하세요.")
    for ln in wrap(txt, font("regular", 36), BODY_W):
        tdraw(d, (MX, y), ln, font("regular", 36), c["text"])
        y += 58
    y = max(y + 50, 700)
    d.line((MX, y, W - MX, y), fill=c["line"], width=2)
    _disclaimer_and_office(d, c, settings, y + 40)
    _footer(d, c, settings, page, total, "")
    return img
