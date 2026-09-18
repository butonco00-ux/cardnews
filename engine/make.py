"""만들기: 수집 → 선정 → 카드 → (확인 페이지).

한국 정부 사이트는 해외(GitHub 서버) 접속을 막는다(2026-09-17 확인). 그래서 둘로 나눈다.
  - 노트북: python -m engine.make --only gov   → docs/날짜/set-1 + run-gov.json
  - GitHub: python -m engine.make --only news  → docs/날짜/set-2 + run-news.json + 확인 페이지
둘이 서로 다른 파일만 쓰므로 동시에 올려도 부딪히지 않는다.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import date, datetime, timedelta

from . import build, govlink, history, instagram, pages, sources_easylaw, sources_gov, sources_law, sources_news, splitter
from . import filter as flt
from .common import data_dir, docs_dir, log, now_kst, read_json, write_json


def _window_start(today: date) -> date:
    # 월요일이면 금요일부터, 아니면 어제부터
    return today - timedelta(days=3 if today.weekday() == 0 else 1)


# ---------------------------------------------------------------- 정책·세금(노트북)

def _record_release(records: list[dict], rel: dict) -> None:
    """뉴스 카드에 붙일 수 있게 보도자료 첫 문단을 모아 둔다(공공누리 제1유형만)."""
    if not rel["license"]["usable"]:
        return
    try:
        parsed = splitter.parse(rel["text"], page_title=rel["title"],
                                hard_wrapped=rel.get("source_file", "").lower().endswith(".pdf"))
    except Exception:
        return
    lead = next((it.text for it in parsed.items if it.level in (0, 1) and len(it.text) >= 30), "")
    if lead:
        records.append(govlink.release_record(rel, lead, parsed.subtitles))


def _save_releases(day: str, records: list[dict]) -> None:
    path = docs_dir() / day / "releases.json"
    old = read_json(path, {}).get("releases", [])
    urls = {r["url"] for r in records}
    merged = records + [r for r in old if r["url"] not in urls]
    write_json(path, {"date": day, "releases": merged})


def make_gov(day: str, url: str | None, settings: dict) -> dict:
    today = date.fromisoformat(day)
    messages: list[dict] = []
    candidates: list[dict] = []
    h = history.load()
    posted = history.posted_urls(h)
    made_before = history.made_urls_before(day)

    if history.find_post(h, day, 1, "실제"):
        messages.append({"level": "warn", "text": "오늘 세트 1은 이미 인스타에 올려서 새로 만들지 않았어요"})
        return _save_run(day, "gov", messages, candidates=candidates)

    chosen = None
    records: list[dict] = []
    try:
        with sources_gov.client() as c:
            if url:
                nid = sources_gov.news_id_from_url(url)
                if not nid:
                    raise RuntimeError("정책브리핑 보도자료 주소가 아니에요(newsId가 없어요)")
                rel = sources_gov.fetch_release(c, nid)
                _record_release(records, rel)
                s, tag, _ = flt.score(rel["title"], rel["text"], settings)
                cand = {"title": rel["title"], "dept": rel["dept"], "url": rel["url"], "score": s}
                if not rel["license"]["usable"]:
                    cand["status"] = rel["license"]["reason"]
                elif rel["url"] in posted:
                    cand["status"] = "이미 인스타에 올린 보도자료"
                else:
                    cand["status"] = "직접 고른 보도자료로 만듦"
                    chosen = (rel, tag or "정책")
                candidates.append(cand)
            else:
                chosen = _pick(c, today, settings, posted, made_before, candidates, messages, records)
    except Exception as e:
        log(traceback.format_exc())
        messages.append({"level": "bad", "text": f"보도자료를 가져오다 문제가 생겼어요: {e}"})
    if records:
        _save_releases(day, records)

    if chosen:
        rel, tag = chosen
        meta = build.build_policy(rel, tag, day, 1, settings)
        if meta.get("ok"):
            messages.append({"level": "ok", "text": f"정책·세금 카드 {len(meta['cards'])}장을 만들었어요: {rel['title']}"})
        else:
            messages.append({"level": "bad", "text": "카드를 만들지 못했어요: " + " / ".join(meta["problems"])})
    elif url:
        why = candidates[0]["status"] if candidates else "보도자료를 읽지 못했어요"
        messages.append({"level": "bad", "text": f"넣어 주신 보도자료로 만들지 못했어요: {why}"})
    elif not any(m["level"] == "bad" for m in messages):
        messages.append({"level": "warn", "text": "오늘은 조건에 맞는 정책·세금 보도자료가 없어요"})
    return _save_run(day, "gov", messages, candidates=candidates[:80])


def _pick(c, today, settings, posted, made_before, candidates, messages, records):
    start = _window_start(today)
    listed = []
    failed = 0
    depts = settings.get("gov_departments") or {}
    for code, name in depts.items():
        try:
            for it in sources_gov.list_releases(c, code, pages=2):
                it["dept"] = it["dept"] or name
                if it["list_date"] and start <= date.fromisoformat(it["list_date"]) <= today:
                    listed.append(it)
        except Exception as e:
            failed += 1
            messages.append({"level": "warn", "text": f"{name} 보도자료 목록을 읽지 못했어요: {e}"})
    if depts and failed == len(depts):
        raise RuntimeError("정책브리핑에 접속하지 못했어요(인터넷 연결 확인)")
    log(f"기간 안 보도자료 {len(listed)}건")
    min_score = int(settings.get("min_score", 4))
    ranked = []
    fetched = 0
    for it in listed:
        ts, tag, _ = flt.score(it["title"], "", settings)
        cand = {"title": it["title"], "dept": it["dept"], "url": it["url"], "score": ts}
        candidates.append(cand)
        if it["url"] in posted:
            cand["status"] = "이미 인스타에 올림"
            continue
        if ts < 3:
            cand["status"] = "부동산 관련 단어가 제목에 없음"
            continue
        if fetched >= 15:
            cand["status"] = "후보가 많아 건너뜀"
            continue
        try:
            rel = sources_gov.fetch_release(c, it["news_id"], it)
            fetched += 1
        except Exception as e:
            cand["status"] = f"원문을 읽지 못함({e})"
            continue
        _record_release(records, rel)
        s, tag, _ = flt.score(rel["title"], rel["text"], settings)
        cand["score"] = s
        if not rel["license"]["usable"]:
            cand["status"] = rel["license"]["reason"]
            continue
        if s < min_score:
            cand["status"] = f"관련도 낮음({s}점)"
            continue
        penalty = 5 if rel["url"] in made_before else 0
        cand["status"] = "후보" + (" (전에 만든 적 있음)" if penalty else "")
        ranked.append((s - penalty, rel["list_date"], rel, tag, cand))
    ranked.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if not ranked:
        return None
    _, _, rel, tag, cand = ranked[0]
    cand["status"] = "선택됨 → 세트 1"
    return rel, tag


# ---------------------------------------------------------------- 법령(노트북)

def _used_urls(kind_set: int) -> set[str]:
    """예전 세트에서 이미 쓴 자료 주소."""
    urls: set[str] = set()
    for p in docs_dir().glob(f"20*-*-*/set-{kind_set}/set.json"):
        m = read_json(p, {})
        urls.update(m.get("source_urls") or [])
        for a in m.get("news_items") or []:
            urls.add(a.get("link", ""))
    return {u for u in urls if u}


def make_law(day: str, settings: dict) -> dict:
    """국가법령정보센터: 최근 공포·시행 부동산 법령 묶음(세트 3)."""
    messages: list[dict] = []
    if history.find_post(history.load(), day, 3, "실제"):
        messages.append({"level": "warn", "text": "오늘 법령 세트는 이미 올려서 새로 만들지 않았어요"})
        return _save_run(day, "law", messages)
    used = _used_urls(3)
    try:
        laws = sources_law.search(day, settings)
    except Exception as e:
        log(traceback.format_exc())
        messages.append({"level": "bad", "text": f"법령을 가져오다 문제가 생겼어요: {e}"})
        return _save_run(day, "law", messages)

    items, skipped = [], []
    for law in laws:
        if law["url"] in used:
            skipped.append({"title": law["name"], "reason": "전에 소개한 법령"})
            continue
        try:
            why = sources_law.reason(law["mst"], settings)
        except Exception as e:
            skipped.append({"title": law["name"], "reason": f"개정이유를 읽지 못함({e})"})
            continue
        keys = settings.get("law_queries") or []
        why_hit = any(k in why for k in keys)
        name_hit = any(k in law["name"] for k in keys)
        if law["kind"] == "타법개정":
            # 다른 법을 고치면서 딸려 바뀐 경우: 개정이유가 그 법 이야기라 카드로 쓰지 않는다
            skipped.append({"title": law["name"], "reason": "다른 법 개정에 딸린 변경(타법개정)"})
            continue
        if not (why_hit or name_hit):
            skipped.append({"title": law["name"], "reason": "부동산과 관련이 적음"})
            continue
        text = sources_law.first_reason_sentences(why)
        if not text:
            skipped.append({"title": law["name"], "reason": "개정이유 내용이 없음"})
            continue
        items.append({
            "title": law["name"], "link": law["url"], "press": law["dept"] or "법제처",
            "published": law["effective_raw"], "date_label": f"시행 {law['effective']}",
            "gov": {"dept": "국가법령정보센터", "title": law["name"], "url": law["url"],
                    "date_label": f"공포 {law['announced']}", "text": text,
                    "license_label": "법제처 국가법령정보센터", "embargo": None},
            "source_note": "법령 출처: 국가법령정보센터(법제처) — 법령은 저작권 보호 대상이 아닙니다.",
        })
        if len(items) >= int(settings.get("law_count", 5)):
            break

    if len(items) >= 1:
        cover = {"tag": "법령", "lines": ("곧 시행되는", "부동산 법령"), "count_label": "법령 {n}건",
                 "title": "곧 시행되는 부동산 법령", "caption_title": "곧 시행되는 부동산 법령",
                 "note": "법령명·시행일과 개정이유 원문을 그대로 실었어요. 자세한 내용은 국가법령정보센터에서 확인하세요."}
        meta = build.build_news(items, day, 3, settings, kind="law", cover=cover)
        messages.append({"level": "ok", "text": f"법령 카드 {len(meta['cards'])}장을 만들었어요(법령 {len(items)}건)"})
    else:
        messages.append({"level": "warn", "text": "오늘은 새로 소개할 부동산 법령이 없어요"})
    return _save_run(day, "law", messages, skipped=skipped[:40])


# ---------------------------------------------------------------- 생활법령(노트북)

def make_easylaw(day: str, settings: dict) -> dict:
    """찾기쉬운 생활법령정보: 부동산·임대차 항목 하나를 원문 그대로(세트 4)."""
    messages: list[dict] = []
    if history.find_post(history.load(), day, 4, "실제"):
        messages.append({"level": "warn", "text": "오늘 생활법령 세트는 이미 올려서 새로 만들지 않았어요"})
        return _save_run(day, "easylaw", messages)
    used = _used_urls(4)
    try:
        with sources_easylaw.client() as c:
            got = sources_easylaw.pick(c, used, settings)
    except Exception as e:
        log(traceback.format_exc())
        messages.append({"level": "bad", "text": f"생활법령을 가져오다 문제가 생겼어요: {e}"})
        return _save_run(day, "easylaw", messages)

    if not got:
        messages.append({"level": "warn", "text": "새로 소개할 생활법령 항목을 찾지 못했어요"})
        return _save_run(day, "easylaw", messages)

    topic, section, text = got
    rel = sources_easylaw.as_release(topic["title"], section, text, day)
    meta = build.build_policy(rel, "생활법령", day, 4, settings, kind="easylaw")
    if meta.get("ok"):
        messages.append({"level": "ok", "text": f"생활법령 카드 {len(meta['cards'])}장을 만들었어요: {rel['title']}"})
    else:
        messages.append({"level": "bad", "text": "생활법령 카드를 만들지 못했어요: " + " / ".join(meta["problems"])})
    return _save_run(day, "easylaw", messages)


# ---------------------------------------------------------------- 뉴스(GitHub)

def make_news(day: str, settings: dict) -> dict:
    messages: list[dict] = []
    excluded: list[dict] = []
    h = history.load()
    cid, secret = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
    if not (cid and secret):
        messages.append({"level": "warn", "text": "네이버 검색 열쇠가 없어 뉴스 헤드라인은 건너뛰었어요(설정안내.md 5단계)"})
    elif history.find_post(h, day, 2, "실제"):
        messages.append({"level": "warn", "text": "오늘 뉴스 세트는 이미 올려서 새로 만들지 않았어요"})
    else:
        try:
            items, excluded = sources_news.fetch(cid, secret, settings, now_kst())
            posted = history.posted_urls(h)
            items = [a for a in items if a["link"] not in posted][: int(settings.get("news_count", 5))]
            if len(items) >= 2:
                items = govlink.attach(items, day, settings)
                meta = build.build_news(items, day, 2, settings)
                linked = sum(1 for a in items if a.get("gov"))
                messages.append({"level": "ok", "text": f"뉴스 헤드라인 카드 {len(meta['cards'])}장을 만들었어요"
                                 + (f" (정부 발표 원문 {linked}건 붙임)" if linked else "")})
            else:
                messages.append({"level": "warn", "text": "최근 24시간 부동산 뉴스가 2건보다 적어 만들지 않았어요"})
        except Exception as e:
            log(traceback.format_exc())
            messages.append({"level": "bad", "text": f"뉴스를 가져오다 문제가 생겼어요: {e}"})
    return _save_run(day, "news", messages, news_excluded=excluded)


def refresh_news_gov(day: str, settings: dict) -> bool:
    """노트북이 보도자료 목록을 늦게 올린 경우: 아직 안 올린 뉴스 카드에 정부 발표 원문을 다시 붙인다."""
    meta = read_json(docs_dir() / day / "set-2" / "set.json", None)
    if not meta or not meta.get("news_items") or history.find_post(history.load(), day, 2, "실제"):
        return False
    items = govlink.attach(meta["news_items"], day, settings)
    before = [(a.get("gov") or {}).get("url") for a in meta["news_items"]]
    after = [(a.get("gov") or {}).get("url") for a in items]
    if before == after:
        return False
    build.build_news(items, day, 2, settings, meta.get("notes") or [])
    log(f"{day} 뉴스 카드에 정부 발표 원문을 다시 붙였어요({sum(1 for u in after if u)}건)")
    return True


def _save_run(day: str, name: str, messages: list[dict], **extra) -> dict:
    info = {"date": day, "finished_at": now_kst().isoformat(), "messages": messages, **extra}
    (docs_dir() / day).mkdir(parents=True, exist_ok=True)
    write_json(docs_dir() / day / f"run-{name}.json", info)
    for m in messages:
        log(m["text"])
    return info


# ---------------------------------------------------------------- 토큰 상태(GitHub)

def check_token(settings: dict) -> None:
    """인스타 토큰 확인. 만료 7일 전부터 경고. GH_PAT 가 있으면 자동 갱신해 비밀 보관함에 저장."""
    path = data_dir() / "token_status.json"
    st = read_json(path, {})
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    user = os.environ.get("IG_USER_ID", "")
    now = now_kst()
    if not token:
        st.update(level="warn", message="인스타 열쇠(토큰)가 아직 없어요. 설정안내.md 4단계를 따라 넣어 주세요",
                  checked_at=now.isoformat())
        write_json(path, st)
        return
    host = settings.get("instagram_host", "graph.instagram.com")
    try:
        ig = instagram.Instagram(user, token, host, settings.get("instagram_api_version", "v25.0"))
        ig.check()
    except Exception as e:
        st.update(level="bad", message=f"인스타 연결 확인 실패: {e}", checked_at=now.isoformat())
        write_json(path, st)
        return

    last = st.get("refreshed_at")
    due = (not last) or (now - datetime.fromisoformat(last)).days >= 20
    if host == "graph.instagram.com" and os.environ.get("GH_PAT") and due:
        try:
            body = instagram.refresh_token(token)
            if _save_secret("IG_ACCESS_TOKEN", body["access_token"]):
                st["refreshed_at"] = now.isoformat()
                st["expires_at"] = (now + timedelta(seconds=int(body.get("expires_in", 5184000)))).isoformat()
        except Exception as e:
            log(f"토큰 자동 갱신 실패: {e}")

    exp = st.get("expires_at")
    if exp:
        left = (datetime.fromisoformat(exp) - now).days
        if left <= 7:
            st.update(level="bad" if left <= 2 else "warn",
                      message=f"인스타 열쇠(토큰)가 {max(left, 0)}일 뒤 만료돼요. 설정안내.md '토큰 새로 받기'를 해 주세요")
        else:
            st.update(level="ok", message=f"인스타 연결 정상(토큰 {left}일 남음)")
    else:
        st.update(level="ok", message="인스타 연결 정상(토큰은 60일마다 새로 받아야 해요)")
    st["checked_at"] = now.isoformat()
    write_json(path, st)


def _save_secret(name: str, value: str) -> bool:
    """gh CLI 로 저장소 비밀 보관함 값 바꾸기(값은 표준입력으로만 전달)."""
    import subprocess

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return False
    env = dict(os.environ, GH_TOKEN=os.environ.get("GH_PAT", ""))
    r = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value, text=True,
                       capture_output=True, env=env)
    if r.returncode != 0:
        log("토큰을 비밀 보관함에 저장하지 못했어요(GH_PAT 권한 확인)")
        return False
    return True


# ---------------------------------------------------------------- 실행

def run(day: str | None = None, url: str | None = None, only: str = "all", build_pages: bool = True) -> dict:
    settings = read_json(data_dir() / "settings.json", {})
    day = day or now_kst().strftime("%Y-%m-%d")
    results = {"date": day, "messages": []}
    # 노트북(한국)에서 하는 것: 보도자료·법령·생활법령
    if only in ("all", "gov", "local"):
        results["messages"] += make_gov(day, url, settings)["messages"]
    if only in ("all", "law", "local") and not url:
        results["messages"] += make_law(day, settings)["messages"]
    if only in ("all", "easylaw", "local") and not url:
        results["messages"] += make_easylaw(day, settings)["messages"]
    if only in ("all", "news") and not url:
        results["messages"] += make_news(day, settings)["messages"]
    if only in ("all", "news"):
        check_token(settings)
    if build_pages:
        pages.build_day(day, settings)
        pages.build_index(settings)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--url")
    ap.add_argument("--only", choices=["all", "local", "gov", "law", "easylaw", "news", "pages"], default="all")
    ap.add_argument("--no-pages", action="store_true")
    a = ap.parse_args()
    day = (a.date or "").strip() or None
    if a.only == "pages":
        settings = read_json(data_dir() / "settings.json", {})
        for p in sorted(docs_dir().glob("20*-*-*"))[-3:]:
            if p.is_dir():
                refresh_news_gov(p.name, settings)
        for p in sorted(docs_dir().glob("20*-*-*")):
            if p.is_dir():
                pages.build_day(p.name, settings)
        pages.build_index(settings)
        return 0
    info = run(day, (a.url or "").strip() or None, a.only, not a.no_pages)
    return 1 if any(m["level"] == "bad" for m in info["messages"]) else 0


if __name__ == "__main__":
    sys.exit(main())
