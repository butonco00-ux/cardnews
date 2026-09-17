"""공공누리 유형 판별. 제1유형만 자동 사용한다."""
from __future__ import annotations

import re

REASONS = {
    1: None,
    2: "공공누리 제2유형(상업적 이용 금지)이라 쓸 수 없어요",
    3: "공공누리 제3유형(변경 금지)이라 카드로 나눌 수 없어요",
    4: "공공누리 제4유형(상업적 이용·변경 금지)이라 쓸 수 없어요",
    0: "공공누리 표시를 찾지 못해 쓸 수 없어요",
}


def detect(html: str) -> dict:
    """페이지 HTML에서 공공누리 유형을 읽는다.

    반환: {"type": 0~4, "text_only": bool, "label": str, "usable": bool, "reason": str|None}
    """
    kind = 0
    # 1) 이미지 alt: "공공누리 공공저작물 자유이용허락 1유형 출처표시"
    m = re.search(r"자유이용허락\s*([1-4])\s*유형", html)
    if m:
        kind = int(m.group(1))
    # 2) 이미지 파일명: open_type_01.png
    if not kind:
        m = re.search(r"open_type_0?([1-4])\.(?:png|gif|jpg)", html)
        if m:
            kind = int(m.group(1))
    # 3) 문구: "공공누리 제1유형"
    if not kind:
        m = re.search(r"공공누리\s*제?\s*([1-4])\s*유형", re.sub(r"<[^>]+>", "", html))
        if m:
            kind = int(m.group(1))
    text_only = bool(re.search(r"텍스트에\s*한하여", re.sub(r"<[^>]+>", "", html)))
    label = f"공공누리 제{kind}유형" if kind else "공공누리 표시 없음"
    if kind == 1 and text_only:
        label += "(텍스트에 한함)"
    return {
        "type": kind,
        "text_only": text_only,
        "label": label,
        "usable": kind == 1,
        "reason": REASONS[kind],
    }
