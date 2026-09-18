"""국가법령정보센터(법제처) 최근 공포·시행 법령.

확인(2026-09-18):
- 목록: GET https://www.law.go.kr/DRF/lawSearch.do?OC={id}&target=law&type=JSON
        &query=검색어(UTF-8 %인코딩) &display=1~100 &sort=efdes(시행일 최신)|ddes(공포일 최신)
        &efYd=시작~끝 (시행일 범위, YYYYMMDD~YYYYMMDD) &ancYd=시작~끝 (공포일 범위)
  응답: 법령명한글 / 공포일자 / 시행일자 / 소관부처명 / 제개정구분명 / 법령일련번호(MST) / 법령상세링크
- 본문: GET .../DRF/lawService.do?OC={id}&target=law&MST={법령일련번호}&type=JSON
  → 법령.제개정이유.제개정이유내용 에 "◇ 개정이유 … ◇ 주요내용 …" 원문
- OC 는 open.law.go.kr 에 신청한 이용자 ID(이메일 앞부분). 없으면 'test' 로도 응답하지만
  공식 사용을 위해 사용자 발급을 권한다(settings.law_oc 또는 환경변수 LAW_OC).
- 법령·조문·개정이유는 저작권법 제7조에 따라 저작권 보호 대상이 아니다(출처만 밝힌다).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import httpx

from .common import USER_AGENT, log

SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "https://www.law.go.kr/DRF/lawService.do"
VIEW = "https://www.law.go.kr/법령/"

DEFAULT_QUERIES = ["주택", "부동산", "임대차", "공인중개사", "토지", "재건축", "재개발", "종합부동산세", "취득세", "양도소득세"]
DEFAULT_DEPTS = ["국토교통부", "기획재정부", "재정경제부", "행정안전부", "금융위원회", "법무부", "국세청"]


def oc(settings: dict) -> str:
    import os
    return (os.environ.get("LAW_OC") or settings.get("law_oc") or "test").strip()


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)


def _get_json(c: httpx.Client, url: str, params: dict) -> dict:
    # 한글 검색어는 UTF-8 %인코딩이어야 한다(EUC-KR 로 보내면 0건)
    r = c.get(url, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"국가법령정보센터 응답 오류(HTTP {r.status_code})")
    try:
        return r.json()
    except ValueError:
        raise RuntimeError("국가법령정보센터가 예상과 다른 답을 보냈어요(이용자 ID 확인)")


def _as_list(x) -> list:
    if not x:
        return []
    return x if isinstance(x, list) else [x]


def _flat(x) -> str:
    if isinstance(x, list):
        return " ".join(_flat(i) for i in x)
    return str(x or "")


def _fmt_date(s: str) -> str:
    s = re.sub(r"\D", "", s or "")
    return f"{s[:4]}.{s[4:6]}.{s[6:8]}" if len(s) == 8 else s


def search(day: str, settings: dict, ahead_days: int = 120, back_days: int = 45) -> list[dict]:
    """오늘 기준 최근 공포되었거나 곧 시행되는 부동산 관련 법령 목록."""
    today = date.fromisoformat(day)
    ef_range = f"{today:%Y%m%d}~{today + timedelta(days=ahead_days):%Y%m%d}"
    anc_range = f"{(today - timedelta(days=back_days)):%Y%m%d}~{today:%Y%m%d}"
    depts = settings.get("law_departments") or DEFAULT_DEPTS
    out: dict[str, dict] = {}
    with _client() as c:
        for q in (settings.get("law_queries") or DEFAULT_QUERIES):
            for kind, rng in (("efYd", ef_range), ("ancYd", anc_range)):
                params = {"OC": oc(settings), "target": "law", "type": "JSON", "display": 20,
                          "sort": "efdes", "query": q, kind: rng}
                try:
                    body = _get_json(c, SEARCH, params)
                except Exception as e:
                    log(f"법령 목록 실패({q}/{kind}): {e}")
                    continue
                for it in _as_list(body.get("LawSearch", {}).get("law")):
                    dept = (it.get("소관부처명") or "").strip()
                    if depts and dept not in depts:
                        continue
                    mst = str(it.get("법령일련번호") or "")
                    if not mst:
                        continue
                    out.setdefault(mst, {
                        "mst": mst,
                        "name": (it.get("법령명한글") or "").strip(),
                        "dept": dept,
                        "kind": (it.get("제개정구분명") or "").strip(),
                        "announced": _fmt_date(it.get("공포일자")),
                        "effective": _fmt_date(it.get("시행일자")),
                        "effective_raw": re.sub(r"\D", "", str(it.get("시행일자") or "")),
                        "url": VIEW + (it.get("법령명한글") or "").strip(),
                        "found_by": q,
                    })
    # 곧 시행될 법령을 먼저, 그다음 최근 공포된 법령(시행일 최신순)
    laws = list(out.values())
    soon = sorted([x for x in laws if x["effective_raw"] >= f"{today:%Y%m%d}"], key=lambda x: x["effective_raw"])
    recent = sorted([x for x in laws if x["effective_raw"] < f"{today:%Y%m%d}"], key=lambda x: x["effective_raw"], reverse=True)
    return soon + recent


def reason(mst: str, settings: dict) -> str:
    """제개정이유·주요내용 원문(없으면 빈 문자열)."""
    with _client() as c:
        body = _get_json(c, SERVICE, {"OC": oc(settings), "target": "law", "MST": mst, "type": "JSON"})
    law = body.get("법령", {})
    text = _flat(law.get("제개정이유", {}).get("제개정이유내용"))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def as_release(law: dict, text: str, day: str) -> dict:
    """보도자료와 같은 모양으로 바꿔 카드 만들기에 넘긴다."""
    return {
        "news_id": law["mst"],
        "url": law["url"],
        "title": law["name"],
        "dept": law["dept"] or "법제처",
        "list_date": day,
        "license": {"type": 0, "usable": True, "text_only": True,
                    "label": "국가법령정보센터(법제처) — 법령은 저작권 보호 대상 아님", "reason": None},
        "embargo": None,
        "source_file": "",
        "text": text,
    }


def to_cards_text(law: dict, reason_text: str) -> str:
    """카드로 나눌 원문 만들기: 머리 정보 + 개정이유/주요내용(원문 그대로)."""
    head = [f"□ 법령명: {law['name']}",
            f"□ 소관부처: {law['dept']}   구분: {law['kind']}",
            f"□ 공포일: {law['announced']}   시행일: {law['effective']}"]
    body = reason_text.replace("◇ 개정이유", "\n□ 개정이유\n").replace("◇개정이유", "\n□ 개정이유\n")
    body = body.replace("◇ 주요내용", "\n□ 주요내용\n").replace("◇주요내용", "\n□ 주요내용\n")
    body = re.sub(r"\s(?=[가-하]\.\s)", "\n ㅇ ", body)            # "가. 나. 다." 항목만 줄 바꾸기
    body = re.sub(r"\n{2,}", "\n", body)
    return "\n".join(head) + "\n" + body.strip()


def first_reason_sentences(reason_text: str, max_chars: int = 170) -> str:
    """개정이유에서 앞 문장만(글자 그대로). 카드 상자에 들어갈 분량."""
    from .splitter import _sentences
    body = re.sub(r"^\[[^\]]*\]\s*", "", reason_text)
    body = body.split("◇ 주요내용")[0].split("◇주요내용")[0]
    body = re.sub(r"◇\s*개정이유(\s*및\s*주요내용)?\s*", "", body)
    body = re.sub(r"^\s*(및\s*주요내용|주요내용)\s*", "", body).strip()
    out = ""
    for s in _sentences(body):
        cand = (out + " " + s).strip()
        if out and len(cand) > max_chars:
            break
        out = cand
        if len(out) >= max_chars:
            break
    return out
