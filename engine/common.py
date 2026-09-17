"""공통: 경로, 한국시간, 설정·기록 파일 읽기/쓰기, 로그."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
FONTS = ROOT / "fonts"

KST = timezone(timedelta(hours=9))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def now_kst() -> datetime:
    return datetime.now(KST)


def data_dir() -> Path:
    """테스트는 CARDNEWS_DATA 로 임시 폴더를 쓰게 해서 사용자 데이터를 덮어쓰지 않는다."""
    return Path(os.environ.get("CARDNEWS_DATA", DATA))


def docs_dir() -> Path:
    return Path(os.environ.get("CARDNEWS_DOCS", DOCS))


def read_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_settings() -> dict:
    s = read_json(data_dir() / "settings.json", None)
    if s is None:
        s = read_json(DATA / "settings.json", {})
    return s


# 열쇠(토큰)가 로그에 찍히지 않도록 가리는 목록
_SECRETS: list[str] = []


def register_secret(value: str | None) -> None:
    if value and len(value) >= 6 and value not in _SECRETS:
        _SECRETS.append(value)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{value}")


def redact(text: str) -> str:
    text = str(text)
    for s in _SECRETS:
        text = text.replace(s, "****")
    text = re.sub(r"(access_token=)[^&\s\"']+", r"\1****", text)
    return text


def log(msg: str) -> None:
    print(redact(f"[{now_kst():%H:%M:%S}] {msg}"), flush=True)


def squash(text: str) -> str:
    """원문 대조용: 공백·줄바꿈만 없앤다(글자는 바꾸지 않음)."""
    return re.sub(r"\s+", "", text or "")
