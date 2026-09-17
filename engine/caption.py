"""인스타 캡션. 한도: 2,200자, 해시태그 30개."""
from __future__ import annotations

import re

from .splitter import _sentences

MAX_CHARS = 2200
MAX_TAGS = 30


def _tags(settings: dict, extra: list[str] | None = None) -> str:
    tags = []
    for t in (settings.get("hashtags") or []) + (extra or []):
        t = "#" + t.lstrip("#").replace(" ", "")
        if t not in tags:
            tags.append(t)
    return " ".join(tags[:MAX_TAGS])


def _disclaimer(settings: dict) -> str:
    return settings.get("disclaimer") or "정보 제공용 콘텐츠입니다. 세금·대출은 반드시 전문가와 상담하세요."


def policy(meta: dict, first_paragraph: str, settings: dict) -> str:
    head = f"[{meta.get('tag', '정책')}] {meta['title']}"
    source = (f"출처: {meta.get('dept', '')} 보도자료 「{meta['title']}」({meta.get('date_label', '')}), "
              f"대한민국 정책브리핑 www.korea.kr — {meta.get('license_label', '공공누리 제1유형')}")
    link = f"▶ 원문 보기: {meta['url']}"
    tags = _tags(settings, [meta.get("tag", "")])
    tail = "\n\n".join([link, source, _disclaimer(settings), tags])

    body_sentences = _sentences(first_paragraph) if first_paragraph else []
    while True:
        body = " ".join(body_sentences)
        text = "\n\n".join(p for p in [head, body, tail] if p)
        if len(text) <= MAX_CHARS or not body_sentences:
            break
        body_sentences = body_sentences[:-1]
    return text[:MAX_CHARS]


def news(items: list[dict], date_label: str, settings: dict, notes: list[str] | None = None) -> str:
    lines = [f"오늘의 부동산 뉴스 ({date_label})", ""]
    for i, a in enumerate(items, 1):
        lines.append(f"{i}. {a['title']} — {a['press']}")
        if notes and i <= len(notes) and notes[i - 1]:
            lines.append(f"   💬 {notes[i - 1]}")
        lines.append(f"   {a['link']}")
        gov = a.get("gov")
        if gov:
            lines.append(f"   📄 정부 발표: {gov['dept']} 「{gov['title']}」({gov['date_label']}) {gov['url']}")
    extra = ["정부 발표 원문 출처: 대한민국 정책브리핑 www.korea.kr — 공공누리 제1유형"] if any(a.get("gov") for a in items) else []
    lines += ["", "기사 제목·언론사만 소개하며, 기사 저작권은 각 언론사에 있습니다.", *extra, _disclaimer(settings), "",
              _tags(settings, ["부동산뉴스"])]
    return "\n".join(lines)[:MAX_CHARS]


def check(text: str) -> list[str]:
    problems = []
    if len(text) > MAX_CHARS:
        problems.append(f"캡션이 {len(text)}자로 2,200자를 넘어요")
    if len(re.findall(r"#\S+", text)) > MAX_TAGS:
        problems.append("해시태그가 30개를 넘어요")
    return problems
