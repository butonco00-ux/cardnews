"""노트북에서 '만들기'를 똑같이 돌려 보는 확인용 실행.

실제 data/, docs/ 는 건드리지 않고 preview/ 폴더에 만든다. 인스타 게시는 하지 않는다.
사용: python scripts/run_local.py [--date 2026-09-17] [--url 보도자료주소] [--no-open]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ROOT / "preview"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--url")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    (PREVIEW / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "settings.json", PREVIEW / "data" / "settings.json")
    os.environ["CARDNEWS_DATA"] = str(PREVIEW / "data")
    os.environ["CARDNEWS_DOCS"] = str(PREVIEW / "docs")
    os.environ.pop("IG_ACCESS_TOKEN", None)   # 확인용 실행에서는 인스타에 접속하지 않음

    sys.path.insert(0, str(ROOT))
    from engine import make

    info = make.run(a.date, a.url, with_news=True)
    index = PREVIEW / "docs" / info["date"] / "index.html"
    print(f"\n확인 페이지: {index}")
    if not a.no_open:
        webbrowser.open(index.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
