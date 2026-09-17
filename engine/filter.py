"""부동산 관련도 점수, 광고성 제외, 중복 제외."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

DEFAULT_KEYWORDS = {
    "정책": ["부동산", "주택", "공급", "재건축", "재개발", "정비사업", "청약", "분양가", "전세", "월세", "임대차",
           "전세사기", "주택담보대출", "주담대", "DSR", "LTV", "규제지역", "조정대상지역", "투기과열지구",
           "토지거래허가", "실거주", "거주의무", "세입자", "임차인", "부동산 거래", "공공주택", "임대주택", "신도시", "택지", "아파트", "부동산 시장", "주거"],
    "세금": ["양도소득세", "양도세", "종합부동산세", "종부세", "취득세", "재산세", "보유세", "임대소득",
           "공시가격", "공시지가", "다주택", "1세대 1주택", "등록세", "증여세", "상속세"],
    "시장": ["주택가격", "아파트 가격", "매매가격", "전세가격", "가격동향", "거래량", "미분양", "실거래가",
           "주택 통계", "인허가", "착공", "준공"],
}

DEFAULT_AD_WORDS = ["분양 홍보", "모델하우스", "견본주택", "선착순", "특별분양", "투자 설명회", "그랜드 오픈",
                    "오픈 예정", "청약 접수 시작", "잔여세대", "줍줍", "[분양]", "[광고]", "분양 중"]


# 단어 안에 우연히 들어 있는 경우를 빼기 위한 목록(예: 인재개발원 ⊃ 재개발, 공급망 ⊃ 공급)
DEFAULT_FALSE_HITS = ["인재개발", "공급망", "전력공급", "에너지 공급", "공급업체", "물량 공급", "백신 공급", "의료 공급",
                      "주거래", "가구당 소득", "착공식 참석", "준공식 참석"]


def _clean(text: str, settings: dict) -> str:
    for w in settings.get("false_hits") or DEFAULT_FALSE_HITS:
        text = text.replace(w, " ")
    return text


def keywords(settings: dict) -> dict:
    return settings.get("keywords") or DEFAULT_KEYWORDS


def score(title: str, body: str, settings: dict) -> tuple[int, str, list[str]]:
    """반환: (점수, 분야, 찾은 단어). 제목 1개당 3점, 본문은 단어 종류당 1점(최대 10)."""
    kw = keywords(settings)
    title, body = _clean(title, settings), _clean(body or "", settings)
    best_tag, tag_scores, found = "정책", {}, []
    total = 0
    for tag, words in kw.items():
        s = 0
        for w in words:
            if w in title:
                s += 3
                found.append(w)
            elif body and w in body:
                s += 1
                found.append(w)
        tag_scores[tag] = s
        total += s
    if tag_scores:
        best_tag = max(tag_scores, key=lambda k: tag_scores[k])
    body_part = min(sum(1 for w in set(found) if w not in title), 10)
    title_part = sum(3 for w in set(found) if w in title)
    return title_part + body_part, best_tag, sorted(set(found))


def is_ad(title: str, settings: dict) -> bool:
    words = settings.get("ad_words") or DEFAULT_AD_WORDS
    return any(w in title for w in words)


def _norm(t: str) -> str:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|<[^>]*>", "", t)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t)


# 같은 소식을 다르게 쓴 제목을 묶기 위한 줄임말·일반어
ALIASES = {"토허구역": "토지거래허가", "토허제": "토지거래허가", "주담대": "주택담보대출", "종부세": "종합부동산세",
           "양도세": "양도소득세", "재초환": "재건축초과이익", "갭투자": "갭투자"}
GENERIC = {"부동산", "주택", "아파트", "전세", "월세", "공급", "주거", "부동산 시장", "매매가격", "전세가격",
           "아파트 가격", "가격동향", "착공", "준공", "인허가"}


def topic_keys(title: str, settings: dict) -> set[str]:
    t = title
    for k, v in ALIASES.items():
        t = t.replace(k, v)
    extra = ["실거주", "갱신계약", "재건축초과이익", "갭투자", "스트레스 DSR", "생애최초", "신생아 특례", "특례대출",
             "공시가격", "보유세", "다주택", "임대사업자", "전세사기", "역전세", "청약", "분양가상한제"]
    words = [w for ws in keywords(settings).values() for w in ws] + extra
    return {w for w in words if w in t and w not in GENERIC}


def same_topic(a: str, b: str, settings: dict) -> bool:
    return bool(topic_keys(a, settings) & topic_keys(b, settings))


def similar(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na or SequenceMatcher(None, na, nb).ratio() >= 0.6
