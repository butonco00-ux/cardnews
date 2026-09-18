"""찾기쉬운 생활법령정보(법제처) — 부동산/임대차 생활법령 풀이.

확인(2026-09-18):
- 분야 목록: /CSP/CsmSortRetrieveLst.laf?sortType=cate&csmAstSeq=3  (부동산/임대차, 주제 27개)
  주제 링크: /CSP/CsmMain.laf?csmSeq=NNN  (제목은 <span class="astTitle">)
- 주제 안의 항목: /CSP/CnpClsMain.laf?popMenu=ov&csmSeq=..&ccfNo=..&cciNo=..&cnpClsNo=..
- 본문: div#ovDiv (또는 .ovDivbox1). "인쇄체크" 같은 버튼 글자는 뺀다.
- 저작권: 법제처 저작권정책 — 법령정보는 영리 목적 포함 자유 이용(제3자 저작물 제외). 출처를 밝힌다.
"""
from __future__ import annotations

import html
import re

import httpx
from bs4 import BeautifulSoup

from .common import USER_AGENT

BASE = "https://www.easylaw.go.kr"
CATEGORY = BASE + "/CSP/CsmSortRetrieveLst.laf?sortType=cate&csmAstSeq=3"   # 부동산/임대차
DROP_WORDS = ["인쇄체크", "인쇄하기", "목록", "이전", "다음", "위로"]


def client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)


def topics(c: httpx.Client) -> list[dict]:
    h = c.get(CATEGORY).text
    found = re.findall(r'href="(/CSP/CsmMain\.laf\?csmSeq=\d+)"[^>]*>\s*<span class="astTitle">\s*([^<]+)', h)
    out, seen = [], set()
    for u, t in found:
        t = re.sub(r"\s+", " ", html.unescape(t)).strip()
        if u in seen or not t:
            continue
        seen.add(u)
        out.append({"title": t, "url": BASE + html.unescape(u)})
    return out


def sections(c: httpx.Client, topic_url: str) -> list[dict]:
    h = c.get(topic_url).text
    found = re.findall(r'href="(/CSP/CnpClsMain\.laf\?[^"]+)"[^>]*>\s*([^<]{2,60})', h)
    out, seen = [], set()
    for u, t in found:
        t = re.sub(r"\s+", " ", html.unescape(t)).strip()
        u = BASE + html.unescape(u)
        if not t or u in seen or t in DROP_WORDS:
            continue
        seen.add(u)
        out.append({"title": t, "url": u})
    return out


def body(c: httpx.Client, url: str) -> tuple[str, str]:
    """반환: (제목, 본문 원문). 본문은 줄 단위 그대로."""
    s = BeautifulSoup(c.get(url).text, "html.parser")
    el = s.select_one("#ovDiv") or s.select_one(".ovDivbox1") or s.select_one(".ovDivbox")
    if not el:
        return "", ""
    for tag in el.select("script, style, button"):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in el.get_text("\n", strip=True).split("\n")]
    lines = [ln for ln in lines if ln and ln not in DROP_WORDS and len(ln) > 1]
    title = lines[0] if lines else ""
    body_lines = []
    for ln in lines[1:]:
        # 법 조문 인용이 줄로 쪼개져 있으면 앞 줄에 붙인다("「…법」 제3조" + "제1항")
        cont = re.match(r"^(에|을|를|이|가|의|은|는|와|과|및|또는|에서|으로|로|한|할|다\)|\)|·|「|제\d)", ln)
        prev_open = body_lines and body_lines[-1].rstrip().endswith(("「", "(", "," , "및", "또는"))
        if body_lines and ((cont and len(ln) < 60) or prev_open):
            body_lines[-1] = body_lines[-1] + " " + ln
        else:
            body_lines.append(ln)
    return title, "\n".join(body_lines)


def as_release(topic: str, section: dict, text: str, day: str) -> dict:
    """보도자료와 같은 모양으로 바꿔 카드 만들기에 넘긴다."""
    return {
        "news_id": section["url"],
        "url": section["url"],
        "title": f"{topic} — {section['title']}" if section["title"] not in topic else topic,
        "dept": "찾기쉬운 생활법령정보",
        "list_date": day,
        "license": {"type": 0, "usable": True, "text_only": True,
                    "label": "법제처 찾기쉬운 생활법령정보(영리 목적 포함 자유 이용)", "reason": None},
        "embargo": None,
        "source_file": "",
        "text": text,
    }


def pick(c: httpx.Client, used_urls: set[str], settings: dict) -> tuple[dict, dict, str] | None:
    """아직 안 쓴 항목 하나 고르기 → (주제, 항목, 본문)."""
    want = settings.get("easylaw_topics") or []
    ts = topics(c)
    if want:
        ts = [t for t in ts if any(w in t["title"] for w in want)] or ts
    for t in ts:
        try:
            secs = sections(c, t["url"])
        except httpx.HTTPError:
            continue
        for sec in secs:
            if sec["url"] in used_urls:
                continue
            try:
                title, text = body(c, sec["url"])
            except httpx.HTTPError:
                continue
            if len(text) < 300:        # 너무 짧은 항목은 건너뜀
                continue
            sec = dict(sec, title=title or sec["title"])
            return t, sec, text
    return None
