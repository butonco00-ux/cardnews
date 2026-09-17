"""뉴스 기사 ↔ 정부 보도자료 연결. 같은 소식이면 뉴스 카드에 '정부 발표 원문' 한두 문장을 붙인다.

- 보도자료 목록(docs/날짜/releases.json)은 노트북이 만든다(정부 사이트 해외 차단).
- 붙이는 글은 보도자료 원문 첫 문단의 **문장 그대로**(공공누리 제1유형만). 기사 문장은 쓰지 않는다.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import filter as flt
from .common import docs_dir, read_json, squash
from .splitter import _sentences

MAX_CHARS = 170


def load_releases(day: str, days: int = 4) -> list[dict]:
    d = date.fromisoformat(day)
    seen: set[str] = set()
    out: list[dict] = []
    for i in range(days):
        p = docs_dir() / (d - timedelta(days=i)).isoformat() / "releases.json"
        for r in read_json(p, {}).get("releases", []):
            if r.get("url") in seen or not r.get("license_usable") or not r.get("lead"):
                continue
            seen.add(r["url"])
            out.append(r)
    return out


def _bigrams(t: str) -> set[str]:
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def match(title: str, releases: list[dict], settings: dict) -> dict | None:
    best, best_score = None, 0.0
    tk = flt.topic_keys(title, settings)
    tb = _bigrams(title)
    for r in releases:
        rtext = r["title"] + " " + " ".join(r.get("subtitles", []))
        rk = flt.topic_keys(rtext, settings)
        overlap = len(tk & rk)
        rb = _bigrams(rtext)
        jacc = len(tb & rb) / max(1, len(tb | rb))
        if overlap >= 2 or (overlap >= 1 and jacc >= 0.18):
            score = overlap + jacc
            if score > best_score:
                best, best_score = r, score
    return best


def excerpt(lead: str) -> str:
    """첫 문단에서 앞 문장부터, 문장 단위로 MAX_CHARS 안에서 자른다(글자 그대로)."""
    out = ""
    for s in _sentences(lead):
        cand = (out + " " + s).strip()
        if out and len(cand) > MAX_CHARS:
            break
        out = cand
        if len(out) >= MAX_CHARS:
            break
    return out


def attach(items: list[dict], day: str, settings: dict) -> list[dict]:
    """기사마다 'gov'(정부 발표 원문)를 붙인 새 목록. 같은 보도자료는 한 기사에만."""
    releases = load_releases(day)
    used: set[str] = set()
    out = []
    for a in items:
        a = {k: v for k, v in a.items() if k != "gov"}
        r = match(a["title"], [x for x in releases if x["url"] not in used], settings)
        if r:
            text = excerpt(r["lead"])
            if text and squash(text) in squash(r["lead"]):
                used.add(r["url"])
                a["gov"] = {"dept": r["dept"], "title": r["title"], "url": r["url"], "date_label": r["date_label"],
                            "text": text, "license_label": r["license_label"], "embargo": r["embargo"]}
        out.append(a)
    return out


def release_record(rel: dict, lead: str, subtitles: list[str]) -> dict:
    d = rel["list_date"]
    return {
        "title": rel["title"], "url": rel["url"], "dept": rel["dept"], "list_date": d,
        "date_label": d.replace("-", "."), "subtitles": subtitles, "lead": lead,
        "license_usable": rel["license"]["usable"], "license_label": rel["license"]["label"],
        "embargo": rel["embargo"],
    }
