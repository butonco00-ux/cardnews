"""인스타 캡션. 한도: 2,200자, 해시태그 30개."""
from __future__ import annotations

import re

from .splitter import _sentences

MAX_CHARS = 2200
MAX_TAGS = 30


# 세트 분야 태그 → 부동산 해시태그(부동산과 관련된 태그만 붙인다)
TAG_TO_HASHTAG = {"세금": "부동산세금", "시장": "부동산시장", "뉴스": "부동산뉴스",
                  "법령": "부동산법", "생활법령": "부동산법률"}


def _tags(settings: dict, extra: list[str] | None = None) -> str:
    tags = []
    extra = [TAG_TO_HASHTAG.get(e.lstrip("#"), e) for e in (extra or []) if e]
    for t in (settings.get("hashtags") or []) + extra:
        t = "#" + t.lstrip("#").replace(" ", "")
        if t not in tags:
            tags.append(t)
    return " ".join(tags[:MAX_TAGS])


def _disclaimer(settings: dict) -> str:
    return settings.get("disclaimer") or "정보 제공용 콘텐츠입니다. 세금·대출은 반드시 전문가와 상담하세요."


def policy(meta: dict, first_paragraph: str, settings: dict) -> str:
    """캡션: 제목 + 원문 첫 문단 + 짧은 출처 + 해시태그(사용자 요청: 원문 보기 링크·면책 문구 없음)."""
    head = f"[{meta.get('tag', '정책')}] {meta['title']}"
    kind = meta.get("kind", "policy")
    source = f"출처: {meta.get('dept', '')} 보도자료" if kind == "policy" else f"출처: {meta.get('dept', '')}"
    tags = _tags(settings, [meta.get("tag", "")])
    tail = "\n\n".join([source, tags])

    body_sentences = _sentences(first_paragraph) if first_paragraph else []
    while True:
        body = " ".join(body_sentences)
        text = "\n\n".join(p for p in [head, body, tail] if p)
        if len(text) <= MAX_CHARS or not body_sentences:
            break
        body_sentences = body_sentences[:-1]
    return text[:MAX_CHARS]


def star(meta: dict, item: dict, settings: dict) -> str:
    """스타 부동산(기사 1건): 제목 + AI 사실 정리 + 출처(언론사·기사 링크) + 해시태그."""
    head = f"[스타] {meta['title']}"
    body = " ".join(item.get("summary") or [])
    source = "\n".join([f"출처: {item['press']} 「{item['title']}」({item.get('date_label', '')})",
                         item["link"],
                         "기사 속 사실을 AI가 새 문장으로 정리했어요. 기사 저작권은 언론사에 있습니다."])
    tags = _tags(settings, ["연예인부동산"])
    return "\n\n".join(p for p in [head, body, source, tags] if p)[:MAX_CHARS]


def news(items: list[dict], date_label: str, settings: dict, notes: list[str] | None = None,
         title: str | None = None, hashtag: str | None = None) -> str:
    lines = [f"{title or '오늘의 부동산 뉴스'} ({date_label})", ""]
    for i, a in enumerate(items, 1):
        lines.append(f"{i}. {a['title']} — {a['press']}")
        if a.get("summary"):
            lines.append("   " + " ".join(a["summary"]))
        if notes and i <= len(notes) and notes[i - 1]:
            lines.append(f"   💬 {notes[i - 1]}")
        lines.append(f"   {a['link']}")
        gov = a.get("gov")
        if gov:
            lines.append(f"   📄 정부 발표: {gov['dept']} 「{gov['title']}」({gov['date_label']}) {gov['url']}")
    extra = ["정부 발표 원문 출처: 대한민국 정책브리핑 www.korea.kr — 공공누리 제1유형"] if any(a.get("gov") for a in items) else []
    if any(a.get("source_note") for a in items):
        extra = [a["source_note"] for a in items if a.get("source_note")][:1] + extra
        head_note = "출처를 밝힌 공공 자료입니다."
    elif any(a.get("summary") for a in items):
        head_note = "기사 속 사실을 AI가 새 문장으로 정리했어요. 자세한 내용은 기사 원문 링크에서 확인하세요. 기사 저작권은 각 언론사에 있습니다."
    else:
        head_note = "기사 제목·언론사만 소개하며, 기사 저작권은 각 언론사에 있습니다."
    lines += ["", head_note, *extra, "",
              _tags(settings, [hashtag or "부동산뉴스"])]
    return "\n".join(lines)[:MAX_CHARS]


def check(text: str) -> list[str]:
    problems = []
    if len(text) > MAX_CHARS:
        problems.append(f"캡션이 {len(text)}자로 2,200자를 넘어요")
    if len(re.findall(r"#\S+", text)) > MAX_TAGS:
        problems.append("해시태그가 30개를 넘어요")
    return problems
