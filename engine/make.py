"""매일 만들기: 수집 → 선정 → 카드 → 확인 페이지.

사용: python -m engine.make [--date 2026-09-17] [--url 보도자료주소] [--no-news]
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import date, timedelta

from . import build, history, instagram, pages, sources_gov, sources_news
from . import filter as flt
from .common import data_dir, docs_dir, log, now_kst, read_json, write_json


def _window_start(today: date) -> date:
    # 월요일이면 금요일부터, 아니면 어제부터
    return today - timedelta(days=3 if today.weekday() == 0 else 1)


def run(day: str | None = None, url: str | None = None, with_news: bool = True) -> dict:
    settings = read_json(data_dir() / "settings.json", {})
    now = now_kst()
    day = day or now.strftime("%Y-%m-%d")
    today = date.fromisoformat(day)
    messages: list[dict] = []
    candidates: list[dict] = []
    h = history.load()
    posted = history.posted_urls(h)
    made_before = history.made_urls_before(h, day)

    # ---------------------------------------------------------------- 1. 정책·세금
    chosen = None
    try:
        with sources_gov.client() as c:
            if url:
                nid = sources_gov.news_id_from_url(url)
                if not nid:
                    raise RuntimeError("정책브리핑 보도자료 주소가 아니에요(newsId가 없어요)")
                rel = sources_gov.fetch_release(c, nid)
                s, tag, found = flt.score(rel["title"], rel["text"], settings)
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
                start = _window_start(today)
                listed = []
                for code, name in (settings.get("gov_departments") or {}).items():
                    try:
                        for it in sources_gov.list_releases(c, code, pages=2):
                            it["dept"] = it["dept"] or name
                            if it["list_date"] and start <= date.fromisoformat(it["list_date"]) <= today:
                                listed.append(it)
                    except Exception as e:
                        messages.append({"level": "warn", "text": f"{name} 보도자료 목록을 읽지 못했어요: {e}"})
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
                    s, tag, found = flt.score(rel["title"], rel["text"], settings)
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
                if ranked:
                    _, _, rel, tag, cand = ranked[0]
                    cand["status"] = "선택됨 → 세트 1"
                    chosen = (rel, tag)
    except Exception as e:
        log(traceback.format_exc())
        messages.append({"level": "bad", "text": f"보도자료를 가져오다 문제가 생겼어요: {e}"})

    existing_post_1 = history.find_post(h, day, 1, "실제")
    if chosen and existing_post_1:
        messages.append({"level": "warn", "text": "오늘 세트 1은 이미 인스타에 올려서 새로 만들지 않았어요"})
    elif chosen:
        rel, tag = chosen
        meta = build.build_policy(rel, tag, day, 1, settings)
        if meta.get("ok"):
            history.add_made(h, day, 1, "policy", meta["source_urls"])
            messages.append({"level": "ok", "text": f"정책·세금 카드 {len(meta['cards'])}장을 만들었어요: {rel['title']}"})
        else:
            messages.append({"level": "bad", "text": "카드를 만들지 못했어요: " + " / ".join(meta["problems"])})
    elif url:
        why = candidates[0]["status"] if candidates else "보도자료를 읽지 못했어요"
        messages.append({"level": "bad", "text": f"넣어 주신 보도자료로 만들지 못했어요: {why}"})
    else:
        messages.append({"level": "warn", "text": "오늘은 조건에 맞는 정책·세금 보도자료가 없어요"})

    # ---------------------------------------------------------------- 2. 뉴스 헤드라인
    news_excluded: list[dict] = []
    if with_news and not url:
        cid, secret = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
        if not (cid and secret):
            messages.append({"level": "warn", "text": "네이버 검색 열쇠가 없어 뉴스 헤드라인은 건너뛰었어요"})
        elif history.find_post(h, day, 2, "실제"):
            messages.append({"level": "warn", "text": "오늘 뉴스 세트는 이미 올려서 새로 만들지 않았어요"})
        else:
            try:
                items, news_excluded = sources_news.fetch(cid, secret, settings, now)
                items = [a for a in items if a["link"] not in posted][: int(settings.get("news_count", 5))]
                if len(items) >= 2:
                    meta = build.build_news(items, day, 2, settings)
                    history.add_made(h, day, 2, "news", meta["source_urls"])
                    messages.append({"level": "ok", "text": f"뉴스 헤드라인 카드 {len(meta['cards'])}장을 만들었어요"})
                else:
                    messages.append({"level": "warn", "text": "최근 24시간 부동산 뉴스가 2건보다 적어 만들지 않았어요"})
            except Exception as e:
                log(traceback.format_exc())
                messages.append({"level": "bad", "text": f"뉴스를 가져오다 문제가 생겼어요: {e}"})

    # ---------------------------------------------------------------- 3. 토큰 상태
    check_token(settings)

    history.save(h)
    run_info = {"date": day, "finished_at": now_kst().isoformat(), "messages": messages,
                "candidates": candidates[:80], "news_excluded": news_excluded}
    (docs_dir() / day).mkdir(parents=True, exist_ok=True)
    write_json(docs_dir() / day / "run.json", run_info)
    pages.build_day(day, settings)
    pages.build_index(settings)
    for m in messages:
        log(m["text"])
    return run_info


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

    # 갱신: Instagram 로그인 방식 + GH_PAT(비밀 보관함 쓰기 권한) 있을 때, 20일마다
    from datetime import datetime
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
        st.update(level="ok", message="인스타 연결 정상(만료일은 설정안내.md 기준으로 60일마다 확인해 주세요)")
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--url")
    ap.add_argument("--no-news", action="store_true")
    a = ap.parse_args()
    info = run(a.date or None, (a.url or "").strip() or None, not a.no_news)
    bad = [m for m in info["messages"] if m["level"] == "bad"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
