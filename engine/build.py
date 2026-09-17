"""세트 만들기: 보도자료 → 카드·캡션·set.json / 뉴스 → 헤드라인 카드."""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

from . import caption, cards, splitter
from .common import docs_dir, now_kst, squash, write_json


def set_dir(day: str, set_no: int) -> Path:
    return docs_dir() / day / f"set-{set_no}"


def _date_label(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.year}.{d.month:02d}.{d.day:02d}"


def build_policy(rel: dict, tag: str, day: str, set_no: int, settings: dict) -> dict:
    parsed = splitter.parse(rel["text"], page_title=rel["title"],
                            hard_wrapped=rel.get("source_file", "").lower().endswith(".pdf"))
    body_cards, info = splitter.build_cards(parsed.items, max_body=8)
    problems = splitter.verify(body_cards, rel["text"])
    if not body_cards:
        problems.append("원문에서 카드로 만들 내용을 찾지 못했어요")

    badge = "확정 아님 · 정부안" if splitter.is_tentative(rel["title"], parsed.subtitles) else ""
    meta = {
        "kind": "policy", "date": day, "set": set_no, "tag": tag,
        "title": rel["title"], "subtitles": parsed.subtitles, "dept": rel["dept"],
        "date_label": _date_label(rel["list_date"]), "url": rel["url"],
        "license": rel["license"], "license_label": rel["license"]["label"],
        "embargo": rel["embargo"], "badge": badge, "source_file": rel.get("source_file", ""),
        "created_at": now_kst().isoformat(),
    }
    out = set_dir(day, set_no)
    if out.exists():
        shutil.rmtree(out)
    if problems:
        meta.update(ok=False, problems=problems, cards=[], card_items=[])
        write_json(out / "set.json", meta)
        return meta

    total = len(body_cards) + 2
    files = []
    img = cards.draw_cover(meta, settings)
    cards.save(img, out / "cards" / "01.jpg")
    files.append("cards/01.jpg")
    for i, items in enumerate(body_cards, 2):
        cards.save(cards.draw_body(items, meta, settings, i, total), out / "cards" / f"{i:02d}.jpg")
        files.append(f"cards/{i:02d}.jpg")
    cards.save(cards.draw_source(meta, settings, total, total), out / "cards" / f"{total:02d}.jpg")
    files.append(f"cards/{total:02d}.jpg")

    first_para = next((it.text for it in parsed.items if it.level in (0, 1)), "")
    cap = caption.policy(meta, first_para, settings)

    used = [squash(it.text) for c in body_cards for it in c if it.level != "system"]
    original = []
    for ln in parsed.lines:
        s = squash(ln)
        part = any(u and u in s for u in used)
        original.append({"text": ln, "used": "all" if part and _covered(s, used) else ("part" if part else "no")})

    meta.update(
        ok=True, problems=[], cards=files,
        card_items=[[it.to_dict() for it in c] for c in body_cards],
        omitted=info["omitted"], skipped=info["skipped"],
        original=original, excluded_tail=parsed.excluded_tail[:2000],
        caption=cap, caption_problems=caption.check(cap),
        source_urls=[rel["url"]],
    )
    (out / "caption.txt").write_text(cap, encoding="utf-8")
    write_json(out / "set.json", meta)
    return meta


def _covered(s: str, used: list[str]) -> bool:
    rest = s
    for u in used:
        if u and u in rest:
            rest = rest.replace(u, "", 1)
    return len(re.sub(r"^[□■◆◇ㅇ○◦•\-–*※➊-➓①-⑳]+", "", rest)) <= 2


def build_news(items: list[dict], day: str, set_no: int, settings: dict, notes: list[str] | None = None) -> dict:
    notes = notes or []
    out = set_dir(day, set_no)
    if out.exists():
        shutil.rmtree(out)
    dl = _date_label(day)
    total = len(items) + 2
    files = []
    cards.save(cards.draw_news_cover(dl, len(items), settings), out / "cards" / "01.jpg")
    files.append("cards/01.jpg")
    for i, a in enumerate(items, 1):
        note = notes[i - 1] if i <= len(notes) else ""
        cards.save(cards.draw_news_item(i, a, note, settings, i + 1, total), out / "cards" / f"{i + 1:02d}.jpg")
        files.append(f"cards/{i + 1:02d}.jpg")
    cards.save(cards.draw_news_end(settings, total, total), out / "cards" / f"{total:02d}.jpg")
    files.append(f"cards/{total:02d}.jpg")
    cap = caption.news(items, dl, settings, notes)
    meta = {
        "kind": "news", "date": day, "set": set_no, "tag": "뉴스", "title": f"오늘의 부동산 뉴스 ({dl})",
        "date_label": dl, "news_items": items, "notes": notes, "ok": True, "problems": [],
        "cards": files, "caption": cap, "caption_problems": caption.check(cap),
        "embargo": None, "license": None, "badge": "",
        "source_urls": [a["link"] for a in items], "created_at": now_kst().isoformat(),
    }
    (out / "caption.txt").write_text(cap, encoding="utf-8")
    write_json(out / "set.json", meta)
    return meta
