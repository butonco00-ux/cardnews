"""인스타에 올리기(수동 실행 전용).

두 단계로 나뉜다(사이에 GitHub이 커밋·Pages 반영):
  python -m engine.publish prepare --date D --set N [--notes-json '[...]']   # 뉴스 한마디 반영해 카드 다시 그리기
  python -m engine.publish post --date D --set N --mode 연습|실제 --confirm 올립니다 [--caption "..."]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import httpx

from . import build, caption, embargo, history, instagram, pages
from .common import data_dir, docs_dir, log, now_kst, read_json, write_json

CONFIRM_WORD = "올립니다"


def _load(day: str, set_no: int) -> dict:
    meta = read_json(docs_dir() / day / f"set-{set_no}" / "set.json", None)
    if not meta:
        raise SystemExit(f"❌ {day} 세트 {set_no}을(를) 찾지 못했어요. 확인 페이지의 날짜·세트 번호를 그대로 넣어 주세요")
    return meta


def prepare(day: str, set_no: int, notes: list[str]) -> None:
    settings = read_json(data_dir() / "settings.json", {})
    meta = _load(day, set_no)
    notes = [n.strip() for n in notes]
    if meta["kind"] == "news" and any(notes) and notes != (meta.get("notes") or []):
        build.build_news(meta["news_items"], day, set_no, settings, notes)
        pages.build_day(day, settings)
        log("한마디를 넣어 뉴스 카드를 다시 그렸어요")
    else:
        log("다시 그릴 카드 없음")


def _pages_url(settings: dict) -> str:
    info = pages.repo_info(settings)
    return info.get("pages", "")


def _wait_images(meta: dict, day: str, settings: dict, limit_s: int = 600) -> list[str]:
    """확인 페이지(Pages)에 올라간 사진이 지금 파일과 같은지 확인. 반영이 늦으면 기다린다."""
    base = _pages_url(settings)
    if not base:
        raise SystemExit("❌ 확인 페이지 주소를 알 수 없어요(GitHub에서 실행해 주세요)")
    folder = docs_dir() / day / f"set-{meta['set']}"
    urls = []
    for f in meta["cards"]:
        digest = hashlib.sha1((folder / f).read_bytes()).hexdigest()
        urls.append((f"{base}{day}/set-{meta['set']}/{f}?v={digest[:10]}", folder / f))
    start = time.time()
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        while True:
            pending = []
            for u, local in urls:
                try:
                    r = c.get(u)
                    ok = (r.status_code == 200 and r.headers.get("content-type", "").startswith("image/jpeg")
                          and r.content == local.read_bytes())
                except httpx.HTTPError:
                    ok = False
                if not ok:
                    pending.append(u)
            if not pending:
                return [u for u, _ in urls]
            if time.time() - start > limit_s:
                raise SystemExit("❌ 카드 사진이 확인 페이지에 아직 안 올라왔어요. 5분쯤 뒤 다시 실행해 주세요")
            log(f"확인 페이지 반영 기다리는 중… ({len(pending)}장 남음)")
            time.sleep(20)


def post(day: str, set_no: int, mode: str, confirm: str, caption_override: str, style: str = "1") -> int:
    settings = read_json(data_dir() / "settings.json", {})
    meta = _load(day, set_no)
    style = (style or "1").strip()[:1]
    styles = meta.get("styles") or {"1": meta.get("cards", [])}
    if style not in styles:
        log(f"❌ 스타일 {style} 카드가 없어요. 있는 스타일: {', '.join(styles)}")
        return 1
    meta = dict(meta, cards=styles[style])
    h = history.load()
    now = now_kst()
    problems: list[str] = []

    if mode not in ("연습", "실제"):
        problems.append("모드는 '연습' 또는 '실제'로 골라 주세요")
    if mode == "실제" and confirm.strip() != CONFIRM_WORD:
        problems.append(f"실제로 올리려면 확인 칸에 '{CONFIRM_WORD}'라고 적어 주세요")
    if not meta.get("ok") or not meta.get("cards"):
        problems.append("이 세트는 카드가 만들어지지 않았어요")
    if meta.get("embargo") and not embargo.is_open(meta["embargo"], now):
        problems.append(f"보도시점 전이에요. {embargo.describe(meta['embargo'])}부터 올릴 수 있어요")
    for a in meta.get("news_items") or []:
        gov = a.get("gov")
        if gov and gov.get("embargo") and not embargo.is_open(gov["embargo"], now):
            problems.append(f"뉴스에 붙인 정부 발표({gov['dept']})가 보도시점 전이에요. {embargo.describe(gov['embargo'])}부터 올릴 수 있어요")
    if meta["kind"] == "policy" and not (meta.get("license") or {}).get("usable"):
        problems.append("공공누리 제1유형이 아니라 올릴 수 없어요")
    if history.find_post(h, day, set_no, "실제"):
        problems.append("이 세트는 이미 인스타에 올렸어요")
    already = history.posted_urls(h) & set(meta.get("source_urls", []))
    if mode == "실제" and already and meta["kind"] == "policy":
        problems.append("같은 보도자료를 이미 다른 날 올렸어요")
    if len(meta.get("cards", [])) > 10:
        problems.append("사진이 10장을 넘어요")

    cap = caption_override.strip() or meta.get("caption", "")
    if meta["kind"] == "policy" and "출처" not in cap:
        # 직접 쓴 캡션에도 출처는 꼭 붙인다
        auto = meta.get("caption", "")
        i = auto.find("▶ 원문 보기")
        cap = cap.rstrip() + "\n\n" + (auto[i:] if i >= 0 else auto)
    problems += caption.check(cap)

    if problems:
        for p in problems:
            log("❌ " + p)
        _record(h, day, set_no, meta, mode, ok=False, problems=problems)
        return 1

    token, user = os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID", "")
    host = settings.get("instagram_host", "graph.instagram.com")
    version = settings.get("instagram_api_version", "v25.0")

    if mode == "연습":
        notes = []
        if token:
            try:
                ig = instagram.Instagram(user, token, host, version)
                name = ig.check().get("username", "")
                q = ig.quota()
                notes.append(f"인스타 연결 정상(@{name}), 오늘 게시 {q['usage']}/{q['total']}")
            except Exception as e:
                notes.append(f"인스타 연결 확인 실패: {e}")
        else:
            notes.append("인스타 열쇠가 아직 없어요(연습이라 괜찮아요)")
        log(f"✅ 연습 모드: 실제로는 올리지 않았어요. 스타일 {style}, 사진 {len(meta['cards'])}장, 캡션 {len(cap)}자")
        for n in notes:
            log(n)
        _record(h, day, set_no, meta, mode, ok=True, problems=[], notes=notes)
        return 0

    # 실제 게시
    try:
        ig = instagram.Instagram(user, token, host, version)
        q = ig.quota()
        if q["usage"] >= q["total"]:
            raise instagram.IGError("오늘 인스타 게시 한도를 다 썼어요")
        urls = _wait_images(meta, day, settings)
        res = ig.publish_carousel(urls, cap)
    except (instagram.IGError, SystemExit) as e:
        log(f"❌ {e}")
        _record(h, day, set_no, meta, mode, ok=False, problems=[str(e)])
        return 1
    log(f"✅ 인스타에 올렸어요 {res.get('permalink', '')}")
    _record(h, day, set_no, meta, mode, ok=True, problems=[], result=res)
    return 0


def _record(h, day, set_no, meta, mode, ok, problems, notes=None, result=None):
    settings = read_json(data_dir() / "settings.json", {})
    rec = {"date": day, "set": set_no, "kind": meta.get("kind"), "mode": mode if ok else f"{mode}-실패",
           "source_urls": meta.get("source_urls", []), "problems": problems, "notes": notes or []}
    if result:
        rec.update(media_id=result.get("media_id"), permalink=result.get("permalink"))
    history.add_post(h, rec)
    history.save(h)
    run = read_json(docs_dir() / day / "run-publish.json", {"messages": []})
    label = "실제 게시" if mode == "실제" else "연습"
    if ok:
        text = f"세트 {set_no} {label} 완료" + (f": {result.get('permalink')}" if result and result.get("permalink") else "")
        for n in notes or []:
            text += f" · {n}"
        run.setdefault("messages", []).append({"level": "ok", "text": f"[{now_kst():%m/%d %H:%M}] {text}"})
    else:
        run.setdefault("messages", []).append(
            {"level": "bad", "text": f"[{now_kst():%m/%d %H:%M}] 세트 {set_no} {label} 안 됨: " + " / ".join(problems)})
    run["finished_at"] = now_kst().isoformat()
    write_json(docs_dir() / day / "run-publish.json", run)
    pages.build_day(day, settings)
    pages.build_index(settings)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "post"])
    ap.add_argument("--date", required=True)
    ap.add_argument("--set", type=int, required=True)
    ap.add_argument("--mode", default="연습")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--style", default="1")
    ap.add_argument("--notes", nargs="*", default=[])
    a = ap.parse_args()
    day = a.date.strip()
    if a.step == "prepare":
        prepare(day, a.set, a.notes)
        return 0
    return post(day, a.set, a.mode.strip(), a.confirm, a.caption, a.style)


if __name__ == "__main__":
    sys.exit(main())
