"""보도자료 원문 → 카드 묶음. 글자를 바꾸지 않고 나누기만 한다(AI 없음).

1) 쪽 번호·머리글·보도시점 줄을 빼고, 담당부서 이후는 제외
2) PDF 줄바꿈을 원래 문단으로 잇기(기호로 시작하는 줄 = 새 문단)
3) □ 한 항목(+딸린 ㅇ, -, *) = 카드 한 장. 넘치면 딸린 항목·문장 단위로 다음 카드
4) 본문 카드가 max_body 를 넘으면 뒤는 (중략)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cards import BODY_H, Item, item_height, items_height
from .common import squash

MARKERS = [
    (re.compile(r"^(⟦표\d+(?::\d+-\d+)?⟧)\s*$"), "table"),
    (re.compile(r"^([➊-➓❶-❿])\s*"), "heading"),
    (re.compile(r"^(\d{1,2}\.)\s+"), "heading"),
    (re.compile(r"^([□■◆◇▣])\s*"), 0),
    (re.compile(r"^([①-⑳])\s*"), 0),
    (re.compile(r"^([ㅇ○◦•∙●])\s*"), 1),
    (re.compile(r"^([-–―‐])\s+"), 2),
    (re.compile(r"^(\*{1,3}|※)\s*"), "note"),
]

STOP = re.compile(r"^\s*(?:<?\s*담당\s*부서|담당\s*부서|\[?\s*붙임\s*\d*\s*\]?|별첨|참고\s*자료|문의\s*[:：]"
                  r"|[\[<〈(]?\s*참\s*고\s*\d*\s*[\]>〉)]?\s*$"            # '참고' 부록 제목 줄에서 본문 끝
                  r"|[\[<〈]?\s*참\s*고\s*\d*\s*[\]>〉]?\s+(?!로|하|해|할|한)\S)")  # "참고 ○○ 개요" 형태
DROP = re.compile(r"^\s*(?:-\s*\d+\s*-|보도자료|보\s*도\s*(?:시\s*점|일\s*시)\s*[:：].*|배\s*포\s*[:：].*)\s*$")

TENTATIVE = re.compile(r"개정안|추진|예정|입법\s*예고|검토|정부안|발표안|계획안|방안|초안")
CONFIRMED = re.compile(r"시행|통과|확정|의결|공포")

SENTENCE_END = re.compile(r"(?<=[다함음임됨])\.\s+|(?<=[다함음임됨]\.)(?=\S)|(?<=[.?!”\"])\s+(?=[가-힣A-Z“\"「(])")


@dataclass
class Parsed:
    title: str = ""
    subtitles: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)       # 원문 문단(대조용)
    excluded_tail: str = ""


def _classify(line: str):
    for rx, level in MARKERS:
        m = rx.match(line)
        if m:
            return level, m.group(1), line[m.end():]
    return None, "", line


def logical_lines(text: str, hard_wrapped: bool = True) -> tuple[list[str], str]:
    raw = text.replace("\r", "").replace(" ", " ").replace("　", " ").split("\n")
    out: list[str] = []
    tail: list[str] = []
    stopped = False
    prev_raw = ""
    for r in raw:
        if stopped:
            tail.append(r)
            continue
        if not r.strip():
            continue
        if STOP.match(r):
            stopped = True
            tail.append(r)
            continue
        if DROP.match(r):
            continue
        s = r.strip()
        level, _, _ = _classify(s)
        if not out or level is not None or not hard_wrapped:
            out.append(s)
        else:
            # PDF 줄 끝에 공백이 있었으면 띄어 쓰고, 없으면 붙인다(단어 중간 줄바꿈)
            joiner = " " if prev_raw.endswith((" ", "\t")) else ""
            out[-1] = out[-1] + joiner + s
        prev_raw = r
    return out, "\n".join(tail)


def parse(text: str, page_title: str = "", hard_wrapped: bool = True) -> Parsed:
    lines, tail = logical_lines(text, hard_wrapped)
    p = Parsed(lines=lines, excluded_tail=tail)
    # 첫 □(또는 번호 소제목) 전까지는 제목·부제
    start = 0
    for i, ln in enumerate(lines):
        lv, _, _ = _classify(ln)
        if lv in (0, "heading") or lv == 1:
            start = i
            break
    else:
        # 기호(□ ㅇ -)가 전혀 없는 글(생활법령 등): 첫 줄만 제목, 나머지는 본문
        start = 1 if len(lines) > 1 else len(lines)
    head = lines[:start]
    for ln in head:
        lv, mk, rest = _classify(ln)
        if lv == 2:
            p.subtitles.append(rest.strip())
        elif not p.title:
            p.title = ln.strip()
        elif lv is None and not p.subtitles:
            p.title = (p.title + " " + ln.strip()).strip()
    if page_title:
        p.title = page_title
    for ln in lines[start:]:
        lv, mk, rest = _classify(ln)
        if lv == "table":
            p.items.append(Item("table", "", mk))
            continue
        if lv is None:
            lv, mk = 1, ""
        rest = rest.strip()
        if rest or mk:
            p.items.append(Item(lv, mk, rest))
    return p


def is_tentative(title: str, subtitles: list[str]) -> bool:
    t = " ".join([title] + subtitles)
    return bool(TENTATIVE.search(t)) and not CONFIRMED.search(title)


# ---------------------------------------------------------------- 카드로 묶기

def _groups(items: list[Item]) -> list[list[Item]]:
    groups: list[list[Item]] = []
    for it in items:
        if it.level == "heading":
            groups.append([it])
        elif it.level == 0:
            if groups and len(groups[-1]) == 1 and groups[-1][0].level == "heading":
                groups[-1].append(it)
            else:
                groups.append([it])
        else:
            if not groups:
                groups.append([])
            groups[-1].append(it)
    # 아주 짧은 묶음(예: "□ 주요 내용은 다음과 같다.")은 다음 묶음에 붙인다
    merged: list[list[Item]] = []
    carry: list[Item] = []
    for g in groups:
        g = carry + g
        carry = []
        if sum(len(i.text) for i in g) < 40 and g is not groups[-1]:
            carry = g
            continue
        merged.append(g)
    if carry:
        merged.append(carry)
    return merged


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    pos = 0
    for m in SENTENCE_END.finditer(text):
        end = m.start() if text[m.start():m.end()].strip() == "" else m.end()
        if m.group(0).startswith("."):
            end = m.start() + 1
        piece = text[pos:end].strip()
        if piece:
            parts.append(piece)
        pos = m.end()
    rest = text[pos:].strip()
    if rest:
        parts.append(rest)
    return parts or [text]


def _pieces(it: Item) -> list[Item]:
    """한 카드에 안 들어가는 항목을 문장 단위로 나눈다(표는 줄 단위)."""
    if item_height(it, True) <= BODY_H:
        return [it]
    if it.level == "table":
        from . import tables
        from .cards import BODY_W, font, wrap
        return [Item("table", "", t) for t in tables.split(it.text, BODY_H, BODY_W, font, wrap)]
    out: list[Item] = []
    cur = ""
    for s in _sentences(it.text):
        cand = (cur + " " + s).strip()
        probe = Item(it.level, it.marker, cand, cont=bool(out))
        if item_height(probe, True) <= BODY_H or not cur:
            cur = cand
        else:
            out.append(Item(it.level, it.marker, cur, cont=bool(out)))
            cur = s
    if cur:
        out.append(Item(it.level, it.marker, cur, cont=bool(out)))
    return out


OMIT = "(중략)"


def build_cards(items: list[Item], max_body: int = 8) -> tuple[list[list[Item]], dict]:
    """반환: (카드별 항목 목록, 정보{omitted, skipped})"""
    cards: list[list[Item]] = []
    info = {"omitted": False, "skipped": []}
    for g in _groups(items):
        flat: list[Item] = []
        for it in g:
            for pc in _pieces(it):
                if item_height(pc, True) > BODY_H:
                    info["skipped"].append(pc.text[:40])   # 한 문장이 카드보다 김 → 건너뜀
                    continue
                flat.append(pc)
        cur: list[Item] = []
        for it in flat:
            if items_height(cur + [it]) <= BODY_H:
                cur.append(it)
                continue
            carry: list[Item] = []
            if it.level == "note":
                # 각주는 혼자 떨어지지 않게 앞 문단과 함께 다음 카드로
                while cur and cur[-1].level == "note":
                    carry.insert(0, cur.pop())
                if len(cur) > 1:
                    carry.insert(0, cur.pop())
                if items_height(carry + [it]) > BODY_H:
                    cur, carry = cur + carry, []
            if cur:
                cards.append(cur)
            cur = carry + [it]
        if cur:
            cards.append(cur)

    # 짧은 카드끼리 합치기(다음 카드가 번호 소제목으로 시작하면 합치지 않음)
    packed: list[list[Item]] = []
    for card in cards:
        if (packed and card and card[0].level != "heading" and not card[0].cont
                and items_height(packed[-1] + card) <= BODY_H):
            packed[-1] = packed[-1] + card
        else:
            packed.append(card)
    cards = packed

    if len(cards) > max_body:
        cards = cards[:max_body]
        info["omitted"] = True
    if info["omitted"] or info["skipped"]:
        last = cards[-1] if cards else []
        mark = Item("system", "", OMIT + " 전체 내용은 원문에서 확인하세요")
        while last and items_height(last + [mark]) > BODY_H:
            last.pop()
            info["omitted"] = True
        if cards:
            last.append(mark)
    return cards, info


def verify(cards: list[list[Item]], original: str, raw: str | None = None) -> list[str]:
    """카드 글자가 모두 원문 글자인지 확인. 문제 목록(비면 통과)."""
    # 쪽 번호("- 3 -")·머리글("보도자료") 줄은 빼고 비교(쪽을 넘어가는 문장도 원문 그대로 이어지게)
    kept = [ln for ln in original.replace(chr(13), "").split(chr(10)) if not DROP.match(ln)]
    src = squash(chr(10).join(kept))
    problems = []
    raw_src = squash(raw or original)
    for n, card in enumerate(cards, 1):
        for it in card:
            if it.level == "system":
                continue
            if it.level == "table":
                from . import tables
                for cell in tables.cells(it.text):
                    if squash(cell) not in raw_src:
                        problems.append(f"{n}번째 카드: 표 칸 글자가 원문과 다름 → {cell[:20]}")
                continue
            if squash(it.text) not in src:
                problems.append(f"{n}번째 카드: 원문에 없는 글자 → {it.text[:30]}")
            if it.marker and not it.cont and squash(it.marker + it.text) not in src:
                problems.append(f"{n}번째 카드: 기호와 글이 원문과 다름 → {it.marker} {it.text[:20]}")
    return problems
