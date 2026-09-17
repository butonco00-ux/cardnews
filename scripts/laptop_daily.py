"""노트북 매일 실행: 정부 보도자료 카드(세트 1)를 만들어 GitHub에 올린다.

한국 정부 사이트는 해외(GitHub 서버) 접속을 막아서 이 단계만 노트북이 한다.
- 윈도우 예약 작업이 매일 07:00과 로그인할 때 실행(꺼져 있었으면 켜질 때 따라잡음)
- 오늘 이미 만들었으면 건너뜀(--force 로 다시 만들기)
- --url 로 원하는 보도자료를 골라 만들 수 있음

python scripts/laptop_daily.py [--force] [--url 주소] [--date 2026-09-17]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "laptop.log"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def log(msg: str) -> None:
    from engine.common import now_kst
    LOG.parent.mkdir(exist_ok=True)
    line = f"[{now_kst():%Y-%m-%d %H:%M:%S}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        pass


INTERACTIVE = False   # bat 로 직접 실행할 때만 GitHub 로그인 창 허용


def git(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if not INTERACTIVE:
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)


def wait_internet(limit_s: int = 600) -> bool:
    import httpx
    start = time.time()
    while time.time() - start < limit_s:
        try:
            httpx.get("https://www.korea.kr/", timeout=15)
            return True
        except Exception:
            time.sleep(20)
    return False


def push_paths(paths: list[str], message: str) -> bool:
    for path in paths:
        if (ROOT / path).exists() or git("ls-files", "--", path).stdout.strip():
            git("add", "-A", "--", path)
    if git("diff", "--cached", "--quiet").returncode == 0:
        log("올릴 변경 없음")
        return True
    r = git("commit", "-q", "-m", message)
    if r.returncode != 0:
        log(f"기록 실패: {r.stderr.strip()[:200]}")
        return False
    for i in range(4):
        pr = git("pull", "-q", "--rebase", "--autostash")
        if pr.returncode != 0:
            log(f"GitHub에서 받아오기 실패: {pr.stderr.strip()[:200]}")
        ps = git("push", "-q")
        if ps.returncode == 0:
            return True
        err = ps.stderr.strip()
        if "Authentication" in err or "could not read Username" in err or "403" in err:
            log("GitHub 로그인이 필요해요. '카드뉴스_지금만들기.bat'을 한 번 실행해 로그인 창에서 로그인해 주세요")
            return False
        time.sleep(10 * (i + 1))
    log(f"GitHub에 올리지 못했어요: {err[:200]}")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--url", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--interactive", action="store_true", help="로그인 창을 띄워도 됨(bat에서 실행할 때)")
    a = ap.parse_args()
    global INTERACTIVE
    INTERACTIVE = a.interactive

    from engine import make
    from engine.common import docs_dir, now_kst, read_json

    day = a.date.strip() or now_kst().strftime("%Y-%m-%d")
    log(f"시작: {day} {'주소 지정' if a.url else ''}")

    if not wait_internet():
        log("인터넷(정책브리핑)에 연결되지 않아 멈췄어요. 다음 실행 때 다시 해요")
        return 1

    r = git("pull", "-q", "--rebase", "--autostash")
    if r.returncode != 0:
        log(f"GitHub에서 최신 내용을 받지 못했어요: {r.stderr.strip()[:200]}")

    run_file = docs_dir() / day / "run-gov.json"
    if not a.force and not a.url and run_file.exists():
        prev = read_json(run_file, {})
        if not any(m.get("level") == "bad" for m in prev.get("messages", [])):
            log("오늘 보도자료 카드는 이미 만들었어요(건너뜀)")
            return 0

    info = make.run(day, a.url.strip() or None, only="gov", build_pages=False)
    for m in info["messages"]:
        log(f"{m['level']}: {m['text']}")

    ok = push_paths([f"docs/{day}/set-1", f"docs/{day}/run-gov.json"], f"보도자료 카드 {day} (노트북)")
    if ok:
        log("GitHub에 올렸어요. 몇 분 뒤 확인 페이지에 나와요")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
