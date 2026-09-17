"""네이버 뉴스 검색 — 기사 제목·언론사·날짜·링크만 쓴다.

주의: description(요약문)과 본문은 저작권 때문에 절대 저장·표시하지 않는다.

확인(2026-09-17): 네이버 개발자센터 검색 API는 2026-07-31 신규 신청이 막히고 NAVER API HUB(네이버 클라우드)로 이관,
2027-06-30 개발자센터 키 호출 종료.
- 새 방식(기본): GET https://naverapihub.apigw.ntruss.com/search/v1/news?query&display(1~100)&sort=date&format=json
  헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY, 하루 25,000회
- 예전 방식(개발자센터 키가 이미 있는 경우): https://openapi.naver.com/v1/search/news.json
  헤더 X-Naver-Client-Id / X-Naver-Client-Secret
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from . import filter as flt
from .common import KST, log, redact, register_secret

HUB_API = "https://naverapihub.apigw.ntruss.com/search/v1/news"
OLD_API = "https://openapi.naver.com/v1/search/news.json"

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
    endpoints = [
        (HUB_API, {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}, {"format": "json"}),
        (OLD_API, {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}, {}),
    ]
    if settings.get("naver_api") == "old":
        endpoints.reverse()
    with httpx.Client(timeout=20) as c:
        api, headers, extra = endpoints[0]
        for q in queries:
            try:
                r = c.get(api, params={"query": q, "display": 50, "sort": "date", **extra}, headers=headers)
                if r.status_code in (401, 403) and len(endpoints) > 1:
                    log(f"네이버 거절 이유({api.split('/')[2]}, HTTP {r.status_code}): {redact(r.text[:300])}")
                    # 열쇠가 다른 방식용이면 한 번만 바꿔 본다
                    api, headers, extra = endpoints.pop()
                    r = c.get(api, params={"query": q, "display": 50, "sort": "date", **extra}, headers=headers)
            except httpx.HTTPError as e:
                log(f"네이버 뉴스 연결 실패({q}): {type(e).__name__}")
                continue
            if r.status_code in (401, 403):
                detail = redact(r.text[:300])
                log(f"네이버 거절 이유({api.split('/')[2]}, HTTP {r.status_code}): {detail}")
                raise RuntimeError("네이버 뉴스 열쇠(Client ID/Secret)가 맞지 않거나, NAVER API HUB에서 뉴스 검색을 신청하지 않았어요"
                                   f" (네이버 응답: {detail[:120]})")
            if r.status_code != 200:
                log(f"네이버 뉴스 오류({q}): HTTP {r.status_code} {redact(r.text[:200])}")
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
