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
    "dt.co.kr": "디지털타임스", "etnews.com": "전자신문", "ytn.co.kr": "YTN", "mbn.co.kr": "MBN",
    "tvchosun.com": "TV조선", "ichannela.com": "채널A", "nocutnews.co.kr": "노컷뉴스", "ohmynews.com": "오마이뉴스",
    "pressian.com": "프레시안", "sisajournal.com": "시사저널", "koreadaily.com": "코리아데일리", "newdaily.co.kr": "뉴데일리",
    "dailian.co.kr": "데일리안", "ebn.co.kr": "EBN", "joseilbo.com": "조세일보", "taxtimes.co.kr": "세무사신문",
    "koreaherald.com": "코리아헤럴드", "hankyung.co.kr": "한국경제", "kukinews.com": "쿠키뉴스", "wowtv.co.kr": "한국경제TV",
    "sbscnbc.co.kr": "SBS Biz", "sbs.co.kr/news": "SBS", "busan.com": "부산일보", "kookje.co.kr": "국제신문",
    "kyongbuk.co.kr": "경북일보", "imaeil.com": "매일신문", "yeongnam.com": "영남일보", "kado.net": "강원도민일보",
    "kwnews.co.kr": "강원일보", "jjan.kr": "전북일보", "kjdaily.com": "광주매일신문", "joongdo.co.kr": "중도일보",
    "daejonilbo.com": "대전일보", "kyeonggi.com": "경기일보", "kihoilbo.co.kr": "기호일보", "incheonilbo.com": "인천일보",
    "housingherald.co.kr": "하우징헤럴드", "arunews.com": "한국주택경제", "rtimes.co.kr": "부동산타임스", "r114.com": "부동산R114",
    "kpinews.kr": "KPI뉴스", "fntimes.com": "한국금융신문", "thebell.co.kr": "더벨", "mk.co.kr/news": "매일경제",
}


# 연예·예능·생활 기사 제외(제목에 '아파트'만 들어간 경우가 많음)
DEFAULT_OFF_TOPIC = ["구해줘", "홈즈", "예능", "케미", "찐친", "배우", "가수", "아이돌", "드라마", "셀럽", "연예",
                     "유튜버", "열애", "결혼", "이혼", "방송인", "개그맨", "출연", "전참시", "나혼산", "나 혼자",
                     "화보", "근황", "스타", "톱스타", "재벌집", "집 공개", "럭셔리 하우스"]


def off_topic(title: str, settings: dict) -> bool:
    words = settings.get("news_off_topic") or DEFAULT_OFF_TOPIC
    return any(w in title for w in words)


def known_press(url: str, settings: dict) -> bool:
    return press_name(url, settings) != _host(url)


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


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
    excluded: list[dict] = []
    pool = fetch_pool(client_id, client_secret, settings, now, settings.get("news_queries") or DEFAULT_QUERIES, hours)
    return select(pool, settings, excluded), excluded


# ------------------------------------------------------------ 연예인 부동산(세트 5)
STAR_QUERIES = ["연예인 건물", "연예인 빌딩 매입", "배우 건물 매입", "가수 빌딩 매입", "아이돌 건물",
                "스타 건물주", "연예인 부동산", "연예인 빌딩 매각", "연예인 아파트 매입", "배우 빌딩 시세차익"]
STAR_PERSON = ["연예인", "배우", "가수", "아이돌", "스타", "방송인", "개그맨", "개그우먼", "MC", "유튜버",
               "모델", "셀럽", "아나운서", "골퍼", "야구선수", "축구선수", "감독", "멤버"]
STAR_DEAL = ["매입", "매각", "샀", "팔았", "팔아", "사들", "시세차익", "차익", "건물주", "소유", "보유", "매수",
             "매도", "투자", "낙찰", "경매"]
STAR_PROPERTY = ["빌딩", "건물", "아파트", "주택", "펜트하우스", "부동산", "오피스텔", "토지", "땅", "상가", "꼬마빌딩"]
STAR_EXCLUDE = ["구해줘", "홈즈", "나혼산", "나 혼자", "전참시", "예능", "드라마", "영화", "화보", "열애", "결혼", "이혼"]


def fetch_star(client_id: str, client_secret: str, settings: dict, now: datetime, hours: int = 72) -> tuple[list[dict], list[dict]]:
    """연예인·유명인이 부동산을 사고팔거나 가진 소식(제목·언론사·날짜·링크만)."""
    excluded: list[dict] = []
    pool = fetch_pool(client_id, client_secret, settings, now, settings.get("star_queries") or STAR_QUERIES, hours)
    return select_star(pool, settings, excluded, int(settings.get("star_count", 5))), excluded


def is_star_deal(title: str, settings: dict) -> bool:
    if any(w in title for w in settings.get("star_exclude") or STAR_EXCLUDE):
        return False
    sold_bought = re.search(r"\d+억\S*\s*(에|원에)\s*(판|산|팔|사)", title)      # "166억에 판 강남빌딩"
    if sold_bought and any(w in title for w in STAR_PROPERTY):
        return True
    # "손예진 244억 강남 빌딩, 반년 넘게 공실"처럼 보유 소식: 금액+건물 이 있고 시장·정책 기사 말이 없으면
    market = ["아파트값", "집값", "평균", "중위", "시세", "매매가", "전세가", "거래량", "돌파", "정부", "대출", "청약",
              "공급", "서울시", "국토부", "금리", "분양가", "경매 물건"]
    if (re.search(r"\d+억", title) and any(w in title for w in ("빌딩", "건물", "펜트하우스", "꼬마빌딩"))
            and not any(w in title for w in market)):
        return True
    has_deal = any(w in title for w in STAR_DEAL)
    has_prop = any(w in title for w in STAR_PROPERTY)
    has_person = any(w in title for w in STAR_PERSON) or "," in title[:12]   # "제니, 한남동 빌딩…" 처럼 이름으로 시작
    return has_deal and has_prop and has_person


def select_star(pool: list[dict], settings: dict, excluded: list[dict], count: int = 5) -> list[dict]:
    allowed = settings.get("star_press_only") or settings.get("news_press_only") or []
    cands = []
    for a in pool:
        if allowed and a["press"] not in allowed:
            continue
        if flt.is_ad(a["title"], settings):
            continue
        if not is_star_deal(a["title"], settings):
            continue
        cands.append(a)
    cands.sort(key=lambda a: a["published"], reverse=True)
    chosen: list[dict] = []
    for a in cands:
        if any(flt.similar(a["title"], b["title"]) for b in chosen):
            excluded.append({"title": a["title"], "reason": "같은 소식 기사가 이미 있음"})
            continue
        chosen.append(a)
        if len(chosen) >= count:
            break
    return chosen


def fetch_pool(client_id: str, client_secret: str, settings: dict, now: datetime, queries: list[str],
               hours: int = 24) -> list[dict]:
    """네이버 뉴스 검색 결과 모으기(제목·언론사·날짜·링크만)."""
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    register_secret(client_id)
    register_secret(client_secret)
    since = now - timedelta(hours=hours)
    seen_links: set[str] = set()
    pool: list[dict] = []
    excluded: list[dict] = []
    endpoints = [
        (OLD_API, {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}, {}),
        # ID·Secret 을 바꿔 넣은 경우도 한 번 시도
        (HUB_API, {"X-NCP-APIGW-API-KEY-ID": client_secret, "X-NCP-APIGW-API-KEY": client_id}, {"format": "json"}),
        (HUB_API, {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}, {"format": "json"}),
    ]
    if settings.get("naver_api") == "old":
        endpoints.reverse()
    with httpx.Client(timeout=20) as c:
        api, headers, extra = endpoints.pop()
        for q in queries:
            try:
                r = c.get(api, params={"query": q, "display": 100, "sort": "date", **extra}, headers=headers)
                while r.status_code in (401, 403) and endpoints:
                    log(f"네이버 거절 이유({api.split('/')[2]}, HTTP {r.status_code}): {redact(r.text[:300])}")
                    api, headers, extra = endpoints.pop()
                    r = c.get(api, params={"query": q, "display": 100, "sort": "date", **extra}, headers=headers)
                    if r.status_code == 200 and len(endpoints) == 1:
                        log("네이버: ID·Secret이 서로 바뀌어 들어가 있어요. 동작은 하지만 비밀 보관함에서 바로잡아 주세요")
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
    return pool


def select(pool: list[dict], settings: dict, excluded: list[dict], count: int = 5) -> list[dict]:
    scored = []
    for a in pool:
        if flt.is_ad(a["title"], settings):
            excluded.append({"title": a["title"], "reason": "광고·분양 홍보성 제목"})
            continue
        if off_topic(a["title"], settings):
            excluded.append({"title": a["title"], "reason": "연예·예능성 제목"})
            continue
        allowed = settings.get("news_press_only") or []
        if allowed and a["press"] not in allowed:
            continue                                   # 정해 둔 언론사만(설정 news_press_only)
        if settings.get("news_known_press_only", True) and not known_press(a["link"], settings):
            excluded.append({"title": a["title"], "reason": f"잘 알려지지 않은 매체({a['press']})"})
            continue
        s, tag, found = flt.score(a["title"], "", settings)
        if s < 3:
            continue
        a = dict(a, score=s, tag=tag)
        scored.append(a)
    # 관련도 높은 기사 먼저, 같으면 최신
    scored.sort(key=lambda a: (min(a["score"], 9), a["published"]), reverse=True)
    chosen: list[dict] = []
    presses: set[str] = set()
    for a in scored:
        if any(flt.similar(a["title"], b["title"]) or flt.same_topic(a["title"], b["title"], settings) for b in chosen):
            excluded.append({"title": a["title"], "reason": "같은 내용의 기사가 이미 있음"})
            continue
        if a["press"] in presses:
            continue
        chosen.append(a)
        presses.add(a["press"])
        if len(chosen) >= count:
            break
    return chosen
