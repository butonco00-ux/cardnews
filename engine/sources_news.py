"""네이버 검색 API(뉴스) — 기사 제목·언론사·날짜·링크만 쓴다.

주의: description(요약문)과 본문은 저작권 때문에 절대 저장·표시하지 않는다.
API: GET https://openapi.naver.com/v1/search/news.json (헤더 X-Naver-Client-Id / X-Naver-Client-Secret)
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from . import filter as flt
from .common import KST, log, register_secret

API = "https://openapi.naver.com/v1/search/news.json"

DEFAULT_QUERIES = ["부동산 정책", "주택 공급", "양도세", "종부세", "취득세", "전세", "주택담보대출", "아파트 가격", "재건축"]

# 주소 → 언론사 이름(모르면 주소 그대로)
DEFAULT_PRESS = {
    "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보", "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문", "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "sedaily.com": "서울경제",
    "edaily.co.kr": "이데일리", "mt.co.kr": "머니투데이", "fnnews.com": "파이낸셜뉴스", "heraldcorp.com": "헤럴드경제",
    "asiae.co.kr": "아시아경제", "news1.kr": "뉴스1", "newsis.com": "뉴시스", "yna.co.kr": "연합뉴스",
    "yonhapnewstv.co.kr": "연합뉴스TV", "kbs.co.kr": "KBS", "imbc.com": "MBC", "sbs.co.kr": "SBS",
    "jtbc.co.kr": "JTBC", "ytn.co.kr": "YTN", "hankookilbo.com": "한국일보", "seoul.co.kr": "서울신문",
    "segye.com": "세계일보", "kmib.co.kr": "국민일보", "munhwa.com": "문화일보", "etoday.co.kr": "이투데이",
    "biz.chosun.com": "조선비즈", "bizwatch.co.kr": "비즈워치", "ajunews.com": "아주경제", "newspim.com": "뉴스핌",
    "dt.co.kr": "디지털타임스", "etnews.com": "전자신문", "hankyung.com/realestate": "한국경제",
}


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def press_name(url: str, settings: dict) -> str:
    table = dict(DEFAULT_PRESS)
    table.update(settings.get("press_names") or {})
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in table:
            return table[cand]
    return host


def fetch(client_id: str, client_secret: str, settings: dict, now: datetime, hours: int = 24) -> tuple[list[dict], list[dict]]:
    """반환: (고른 기사, 제외 목록[제목·이유])."""
    register_secret(client_id)
    register_secret(client_secret)
    queries = settings.get("news_queries") or DEFAULT_QUERIES
    since = now - timedelta(hours=hours)
    seen_links: set[str] = set()
    pool: list[dict] = []
    excluded: list[dict] = []
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    with httpx.Client(timeout=20) as c:
        for q in queries:
            try:
                r = c.get(API, params={"query": q, "display": 50, "sort": "date"}, headers=headers)
            except httpx.HTTPError as e:
                log(f"네이버 뉴스 연결 실패({q}): {type(e).__name__}")
                continue
            if r.status_code == 401:
                raise RuntimeError("네이버 검색 열쇠(Client ID/Secret)가 맞지 않아요")
            if r.status_code != 200:
                log(f"네이버 뉴스 오류({q}): HTTP {r.status_code}")
                continue
            for it in r.json().get("items", []):
                link = it.get("originallink") or it.get("link") or ""
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                try:
                    pub = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
                except Exception:
                    continue
                if pub < since:
                    continue
                # 제목·언론사·날짜·링크만 남긴다(description 은 버림)
                pool.append({
                    "title": clean(it.get("title", "")),
                    "link": link,
                    "naver_link": it.get("link", ""),
                    "press": press_name(link, settings),
                    "published": pub.isoformat(),
                    "date_label": f"{pub:%Y.%m.%d %H:%M}",
                })
    return select(pool, settings, excluded), excluded


def select(pool: list[dict], settings: dict, excluded: list[dict], count: int = 5) -> list[dict]:
    scored = []
    for a in pool:
        if flt.is_ad(a["title"], settings):
            excluded.append({"title": a["title"], "reason": "광고·분양 홍보성 제목"})
            continue
        s, tag, found = flt.score(a["title"], "", settings)
        if s < 3:
            continue
        a = dict(a, score=s, tag=tag)
        scored.append(a)
    scored.sort(key=lambda a: (a["published"], a["score"]), reverse=True)
    chosen: list[dict] = []
    presses: set[str] = set()
    for a in scored:
        if any(flt.similar(a["title"], b["title"]) for b in chosen):
            excluded.append({"title": a["title"], "reason": "같은 내용의 기사가 이미 있음"})
            continue
        if a["press"] in presses:
            continue
        chosen.append(a)
        presses.add(a["press"])
        if len(chosen) >= count:
            break
    return chosen
