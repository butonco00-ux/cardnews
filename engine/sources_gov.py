"""정책브리핑(korea.kr) 보도자료 수집.

확인한 사실(2026-09-17):
- 정책브리핑 RSS 서비스는 중단됨 → 목록 화면을 읽는다.
- 목록: /briefing/pressReleaseList.do?repCodeType=정부부처&repCode={부처코드}&pageIndex=N (한 쪽 10건)
- 본문: /briefing/pressReleaseView.do?newsId=N — 원문은 첨부(PDF·HWPX)에 있고,
  페이지에는 "텍스트에 한하여 공공누리 제1유형" 표시가 있다.
- 첨부 파일 이름에 "260918(조간)"처럼 보도시점이 붙고, 보도시점 전에 사이트에 먼저 올라온다.
"""
from __future__ import annotations

import html as htmllib
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from . import doctext, embargo, license
from .common import USER_AGENT, log

BASE = "https://www.korea.kr"


def client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=40, follow_redirects=True)


def _get(c: httpx.Client, url: str, tries: int = 3) -> httpx.Response:
    last = None
    for i in range(tries):
        try:
            r = c.get(url)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except httpx.HTTPError as e:
            last = e
    raise RuntimeError(f"정책브리핑에 연결하지 못했어요({last})")


def list_releases(c: httpx.Client, dept_code: str, pages: int = 2) -> list[dict]:
    items: list[dict] = []
    for page in range(1, pages + 1):
        url = (f"{BASE}/briefing/pressReleaseList.do?repCodeType=%EC%A0%95%EB%B6%80%EB%B6%80%EC%B2%98"
               f"&repCode={dept_code}&pageIndex={page}")
        soup = BeautifulSoup(_get(c, url).text, "html.parser")
        for a in soup.select("div.list_type li > a[href*='pressReleaseView.do']"):
            m = re.search(r"newsId=(\d+)", a["href"])
            title = a.select_one("strong")
            spans = a.select("span.source > span")
            if not (m and title):
                continue
            d = spans[0].get_text(strip=True) if spans else ""
            items.append({
                "news_id": m.group(1),
                "title": title.get_text(" ", strip=True),
                "list_date": d,
                "dept": spans[1].get_text(strip=True) if len(spans) > 1 else "",
                "url": f"{BASE}/briefing/pressReleaseView.do?newsId={m.group(1)}",
            })
    return items


def news_id_from_url(url: str) -> str | None:
    m = re.search(r"newsId=(\d+)", url or "")
    return m.group(1) if m else None


def fetch_release(c: httpx.Client, news_id: str, fallback: dict | None = None) -> dict:
    """본문 페이지 + 첨부 원문을 읽는다. 실패하면 예외(쉬운 문장)."""
    url = f"{BASE}/briefing/pressReleaseView.do?newsId={news_id}"
    page = _get(c, url).text
    soup = BeautifulSoup(page, "html.parser")
    fallback = fallback or {}

    title = fallback.get("title", "")
    # og:title 은 두 번 이스케이프돼 있어 제목 칸(h1)을 먼저 쓴다
    h = soup.select_one(".view_title h1")
    if h is not None and h.get_text(strip=True):
        title = h.get_text(" ", strip=True)
    title = re.sub(r"\s*\|\s*정책브리핑.*$", "", htmllib.unescape(title)).strip()

    dept = fallback.get("dept", "")
    list_date = fallback.get("list_date", "")
    info = soup.select_one(".article_head .info")
    if info:
        t = info.get_text(" ", strip=True)
        m = re.search(r"(20\d{2})\.(\d{2})\.(\d{2})", t)
        if m and not list_date:
            list_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if not dept:
            for cand in ("국토교통부", "재정경제부", "기획예산처", "국세청", "행정안전부", "금융위원회"):
                if cand in t:
                    dept = cand
    if not list_date:
        m = re.search(r"(20\d{2})-(\d{2})-(\d{2})", page)
        list_date = m.group(0) if m else datetime.now().strftime("%Y-%m-%d")

    lic = license.detect(page)

    files = []
    for a in soup.select("div.filedown a[href*='download.do']"):
        name = a.get_text(" ", strip=True)
        if not name:
            continue
        files.append({"name": name, "url": BASE + htmllib.unescape(a["href"])})
    pdfs = [f for f in files if f["name"].lower().endswith(".pdf")]
    hwpxs = [f for f in files if f["name"].lower().endswith(".hwpx")]

    text, source_file, info = "", "", {}
    for f in pdfs[:1] + hwpxs[:1]:
        try:
            data = _get(c, f["url"]).content
            text, info = (doctext.pdf_text(data, with_info=True) if f["name"].lower().endswith(".pdf")
                          else doctext.hwpx_text(data, with_info=True))
            if len(text.strip()) > 100:
                source_file = f["name"]
                break
        except Exception as e:  # 다음 파일로
            log(f"첨부 읽기 실패: {f['name']} ({e})")
    if not text.strip():
        raise RuntimeError("보도자료 원문(PDF·한글 파일)을 읽지 못했어요")

    ld = date.fromisoformat(list_date)
    emb = embargo.parse(text, ld, source_file)
    return {
        "news_id": news_id,
        "url": url,
        "title": title,
        "dept": dept,
        "list_date": list_date,
        "license": lic,
        "embargo": emb,
        "source_file": source_file,
        "text": text,
        "tables": info.get("tables", []),          # 표 칸 글자(카드에 표로 다시 그림)
        "raw_text": info.get("raw_text", text),    # 표까지 포함한 원문 전체(원문 대조용)
    }
