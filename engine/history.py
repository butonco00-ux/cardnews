"""기록: 만든 세트, 게시한 세트(data/history.json)."""
from __future__ import annotations

from .common import data_dir, now_kst, read_json, write_json


def path():
    return data_dir() / "history.json"


def load() -> dict:
    h = read_json(path(), {})
    h.setdefault("made", [])
    h.setdefault("posted", [])
    return h


def save(h: dict) -> None:
    write_json(path(), h)


def posted_urls(h: dict) -> set[str]:
    return {u for p in h["posted"] if p.get("mode") == "실제" for u in p.get("source_urls", [])}


def made_urls_before(h: dict, date: str) -> set[str]:
    return {u for m in h["made"] if m.get("date") != date for u in m.get("source_urls", [])}


def find_post(h: dict, date: str, set_no: int, mode: str = "실제") -> dict | None:
    for p in h["posted"]:
        if p.get("date") == date and p.get("set") == set_no and p.get("mode") == mode:
            return p
    return None


def add_made(h: dict, date: str, set_no: int, kind: str, urls: list[str]) -> None:
    h["made"] = [m for m in h["made"] if not (m.get("date") == date and m.get("set") == set_no)]
    h["made"].append({"date": date, "set": set_no, "kind": kind, "source_urls": urls, "at": now_kst().isoformat()})


def add_post(h: dict, record: dict) -> None:
    record.setdefault("at", now_kst().isoformat())
    h["posted"].append(record)
