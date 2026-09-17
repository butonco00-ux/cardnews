"""보도시점(엠바고) 읽기 → 인스타에 올려도 되는 가장 이른 시각(한국시간).

규칙(보수적으로):
- 시각이 적혀 있으면(예: 9. 17.(목) 11:00 이후) 그 시각. 여러 개면 가장 이른 것
  (예: "9.18.(금) 조간(9.17.(목) 12:00 이후 인터넷 게재)" → 9.17 12:00)
- 시각 없이 "조간"만 → 그날 06:00
- 시각 없이 "석간"만 → 그날 12:00
- "배포 즉시" / "즉시 보도" → 배포일 00:00(바로 가능)
- 못 읽으면 → 목록에 표시된 날짜의 다음 날 06:00
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .common import KST

_DATE = re.compile(
    r"(?:(20\d{2}|\d{2})\s*[.\-/년]\s*)?"
    r"(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*[.일]?\s*"
    r"(?:\(\s*[월화수목금토일]\s*\)\s*\.?)?\s*"
    r"(?:(오전|오후)\s*)?"
    r"(?:(\d{1,2})\s*(?::|시)\s*(\d{2})?\s*(?:분)?)?"
    r"\s*(조간|석간)?"
)


def _header(text: str) -> str:
    """보도시점 줄(첫 부분)만 본다. 본문 날짜를 엠바고로 착각하지 않게."""
    head = text[:600]
    # "보도자료"라는 머리글을 보도시점으로 착각하지 않게 '시점/일시/일' 또는 ':' 가 꼭 있어야 함
    m = re.search(r"보\s*도\s*(?:시\s*점|일\s*시|일)\s*[:：]?(.{0,160})", head) or \
        re.search(r"보\s*도\s*[:：](.{0,160})", head)
    return m.group(1) if m else ""


def _deploy_date(text: str, base_year: int) -> date | None:
    m = re.search(r"배\s*포\s*(?:일\s*시)?\s*[:：]?\s*(.{0,40})", text[:600])
    if not m:
        return None
    d = _DATE.search(m.group(1))
    if not d or not d.group(2):
        return None
    return _mk_date(d, base_year)


def _mk_date(m: re.Match, base_year: int) -> date | None:
    y = m.group(1)
    year = base_year if not y else (int(y) + 2000 if len(y) == 2 else int(y))
    try:
        return date(year, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse(text: str, list_date: date, filename: str = "") -> dict:
    """반환: {"available_at": ISO 문자열, "raw": 보도시점 원문, "rule": 설명, "certain": bool}"""
    header = _header(text)
    raw = header.split("/")[0].strip() if header else ""
    base_year = list_date.year
    candidates: list[tuple[datetime, str]] = []

    if header:
        if re.search(r"즉\s*시", header.split("/")[0]):
            dd = _deploy_date(text, base_year) or list_date
            return _result(datetime(dd.year, dd.month, dd.day, 0, 0, tzinfo=KST), raw, "배포 즉시 보도", True)
        for m in _DATE.finditer(header):
            if not m.group(2) or not m.group(3):
                continue
            # 뒤에 '배포' 날짜가 붙은 부분은 보도시점이 아님
            before = header[max(0, m.start() - 6):m.start()]
            if "배포" in before:
                continue
            d = _mk_date(m, base_year)
            if not d:
                continue
            if m.group(5):
                hour = int(m.group(5))
                if m.group(4) == "오후" and hour < 12:
                    hour += 12
                minute = int(m.group(6) or 0)
                if 0 <= hour <= 23:
                    candidates.append((datetime(d.year, d.month, d.day, hour, minute, tzinfo=KST), "적힌 시각"))
            elif m.group(7) == "조간":
                candidates.append((datetime(d.year, d.month, d.day, 6, 0, tzinfo=KST), "조간 → 그날 06:00"))
            elif m.group(7) == "석간":
                candidates.append((datetime(d.year, d.month, d.day, 12, 0, tzinfo=KST), "석간 → 그날 12:00"))
            else:
                # 날짜만 있고 조간/석간이 조금 뒤에 붙은 경우
                tail = header[m.end():m.end() + 8]
                if "조간" in tail:
                    candidates.append((datetime(d.year, d.month, d.day, 6, 0, tzinfo=KST), "조간 → 그날 06:00"))
                elif "석간" in tail:
                    candidates.append((datetime(d.year, d.month, d.day, 12, 0, tzinfo=KST), "석간 → 그날 12:00"))

    if not candidates and filename:
        m = re.match(r"\s*(\d{2})(\d{2})(\d{2})\s*\(\s*(조간|석간)", filename)
        if m:
            d = date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
            h = 6 if m.group(4) == "조간" else 12
            candidates.append((datetime(d.year, d.month, d.day, h, 0, tzinfo=KST), f"파일 이름의 {m.group(4)}"))
            raw = raw or filename

    if candidates:
        at, rule = min(candidates, key=lambda c: c[0])
        return _result(at, raw, rule, True)

    nd = list_date + timedelta(days=1)
    return _result(datetime(nd.year, nd.month, nd.day, 6, 0, tzinfo=KST), raw,
                   "보도시점을 읽지 못해 다음 날 06:00부터로 정했어요", False)


def _result(at: datetime, raw: str, rule: str, certain: bool) -> dict:
    return {"available_at": at.isoformat(), "raw": raw, "rule": rule, "certain": certain}


def is_open(info: dict, now: datetime) -> bool:
    return now >= datetime.fromisoformat(info["available_at"])


def describe(info: dict) -> str:
    at = datetime.fromisoformat(info["available_at"])
    return f"{at.month}월 {at.day}일 {at.hour:02d}:{at.minute:02d}"
