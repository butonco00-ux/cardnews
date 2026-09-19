"""스타 부동산 기사 → 사실만 새 문장으로 정리(노트북의 claude CLI, 사용자 Claude 구독으로만).

비용 원칙(사용자 지시 2026-09-19: 추가 비용 절대 금지):
- API 열쇠를 쓰지 않는다. 자식 프로세스 환경에서 ANTHROPIC_API_KEY 등을 지운다.
- 실행 전 확인: `claude auth status` 가 claude.ai 구독 로그인이고, ~/.claude.json 의
  hasExtraUsageEnabled(한도 초과 시 유료 추가 사용)가 꺼져 있을 때만 동작. 아니면 멈추고 알린다.
- 구독 사용 한도에 걸리면 그날은 멈춘다(재시도 없음).

저작권 원칙: 기사 문장을 옮기지 않는다. 사실(누가·어디·얼마·언제)만 새 문장으로.
검사: ① 기사와 16자 이상 연속으로 같은 부분이 있으면 버림 ② 기사에 없는 숫자가 있으면 버림.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import httpx
from bs4 import BeautifulSoup

from .common import USER_AGENT, log, squash

ARTICLE_SELECTORS = ["[itemprop=articleBody]", "#articleBody", "#article-view-content-div", "#newsct_article",
                     "#dic_area", ".article_body", ".article-body", "#articletxt", ".news_cnt_detail_wrap",
                     "#article_body", ".view_con", "article"]
MAX_CALLS_PER_RUN = 8
STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


class Stop(RuntimeError):
    """오늘은 AI 정리를 더 하지 않음(비용·한도 이유). 사용자에게 알린다."""


def _env() -> dict:
    env = dict(os.environ)
    for k in STRIP_ENV:
        env.pop(k, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cost_guard() -> None:
    """구독 로그인·추가 과금 꺼짐을 확인. 문제면 Stop."""
    try:
        r = subprocess.run("claude auth status", shell=True, capture_output=True, text=True,
                           encoding="utf-8", env=_env(), timeout=60)
        st = json.loads(r.stdout or "{}")
    except Exception as e:
        raise Stop(f"claude 로그인 상태를 확인하지 못했어요({type(e).__name__})")
    if not st.get("loggedIn") or st.get("authMethod") != "claude.ai":
        raise Stop("claude 가 Claude 구독(claude.ai)으로 로그인돼 있지 않아요 — 요금이 생길 수 있어 멈췄어요")
    try:
        cfg = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8"))
        oa = cfg.get("oauthAccount") or {}
        if oa.get("hasExtraUsageEnabled"):
            raise Stop("Claude 구독에 '추가 사용(유료)'이 켜져 있어 멈췄어요 — 한도를 넘으면 요금이 나갈 수 있어요")
        if cfg.get("primaryApiKey"):
            raise Stop("claude 에 API 열쇠가 저장돼 있어 멈췄어요 — 쓴 만큼 요금이 나갈 수 있어요")
    except Stop:
        raise
    except Exception:
        raise Stop("claude 설정 파일을 확인하지 못해 멈췄어요")


def article_text(url: str) -> str:
    """기사 페이지에서 본문 글자만(요약 재료로만 쓰고 카드·캡션에는 넣지 않음)."""
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=25, follow_redirects=True)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")
    for tag in s.select("script, style, figure, figcaption, iframe, .reporter, .copyright"):
        tag.decompose()
    best = ""
    for sel in ARTICLE_SELECTORS:
        el = s.select_one(sel)
        if el:
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
            if len(t) > len(best):
                best = t
        if len(best) > 400:
            break
    if len(best) < 200:
        ps = " ".join(p.get_text(" ", strip=True) for p in s.select("p"))
        best = re.sub(r"\s+", " ", ps)
    return best[:6000]


PROMPT = """너는 부동산 뉴스 카드의 사실 정리 담당이다. 아래 기사에서 **사실만** 뽑아 한국어 기사체 문장 4~7개로 새로 써라.
규칙:
- 기사 문장을 그대로 옮기지 말고 새 문장으로 쓴다(8어절 이상 똑같이 쓰지 말 것).
- 누가(실명은 기사에 나온 그대로), 어디(구·동·건물 종류), 얼마(금액), 언제(연·월), 무엇을(매입/매각/보유) 중심.
- 기사에 없는 숫자·추측·평가·감정 표현 금지. 시세차익 등 계산하지 말고 기사에 있는 숫자만.
- 연예인 사생활·가족 이야기는 넣지 말고 부동산 거래 사실만.
- 한 문장은 60자 안쪽. "~했다." "~이다." 체.
출력은 JSON 한 줄만: {"lines": ["문장1", "문장2", ...]}

기사 제목: {title}
기사 본문:
{body}
"""


def _run_claude(prompt: str) -> str:
    r = subprocess.run("claude -p --output-format json --tools \"\" --no-session-persistence",
                       input=prompt, shell=True, capture_output=True, text=True, encoding="utf-8",
                       env=_env(), timeout=240)
    LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "5-hour limit", "weekly limit", "credit", "billing")
    try:
        body = json.loads(r.stdout or "")
    except ValueError:
        body = None
    if body is None or r.returncode != 0 or body.get("is_error"):
        # 실패했을 때만 이유를 본다(정상 답의 글자는 검사하지 않음 - 잘못 멈추는 것 방지)
        why = ((r.stderr or "") + " " + (str(body.get("result", "")) if body else (r.stdout or ""))).lower()
        if any(w in why for w in LIMIT_WORDS):
            raise Stop("Claude 구독 사용량 한도(또는 결제 관련 안내)에 걸려 오늘 AI 정리는 멈췄어요")
        if body is None:
            raise RuntimeError("claude 응답을 읽지 못했어요")
        raise RuntimeError(f"claude 오류: {str(body.get('result', ''))[:120]}")
    return str(body.get("result", ""))


def _numbers(s: str) -> set[str]:
    return {re.sub(r"[,\s]", "", n) for n in re.findall(r"\d[\d,.]*", s)}


OVERLAP = 25


def check(lines: list[str], article: str) -> str | None:
    """문제 있으면 이유, 없으면 None."""
    if not (3 <= len(lines) <= 8):
        return "문장 수가 맞지 않음"
    src = squash(article)
    for ln in lines:
        s = squash(ln)
        # 이름·숫자가 들어간 사실 표현은 짧게 겹칠 수 있음. 25자 이상 똑같으면 기사 문장 복사로 본다
        for i in range(0, max(0, len(s) - 24)):
            if s[i:i + OVERLAP] in src:
                return "기사 문장과 너무 비슷함"
    art_nums = _numbers(article)
    for ln in lines:
        for n in _numbers(ln):
            if n and n not in art_nums and n.rstrip(".") not in art_nums:
                return f"기사에 없는 숫자({n})"
    return None


def summarize(item: dict) -> list[str]:
    body = article_text(item["link"])
    if len(body) < 150:
        raise RuntimeError("기사 본문을 읽지 못함")
    prompt = PROMPT.replace("{title}", item["title"]).replace("{body}", body)
    why = None
    for attempt in range(2):                      # 기사 문장과 비슷하면 한 번만 다시 쓰게 함
        if attempt:
            prompt += ("\n\n[다시 쓰기] 앞의 답이 기사 문장을 너무 많이 그대로 썼습니다. "
                       "사실(이름·날짜·금액)은 그대로 두고 문장 표현은 모두 새로 바꿔 쓰세요.")
        out = _run_claude(prompt)
        m = re.search(r"\{.*\}", out, re.S)
        lines = json.loads(m.group(0)).get("lines", []) if m else []
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in lines if str(ln).strip()]
        why = check(lines, body)
        if not why:
            return lines
        if "비슷" not in why:
            break
    raise RuntimeError(why)


def fill(items: list[dict]) -> tuple[list[dict], list[str]]:
    """아직 정리 안 된 기사에 summary 채우기. 반환: (새 목록, 알림 문장들)."""
    cost_guard()                                   # 비용 조건이 안 맞으면 Stop
    notes, calls = [], 0
    out = []
    for a in items:
        a = dict(a)
        if not a.get("summary") and calls < MAX_CALLS_PER_RUN:
            calls += 1
            try:
                a["summary"] = summarize(a)
                a["summary_note"] = "AI 사실 정리"
            except Stop:
                raise
            except Exception as e:
                notes.append(f"'{a['title'][:20]}…' 정리 안 함: {e}")
                log(f"사실 정리 실패: {a['title'][:30]} ({e})")
        out.append(a)
    return out, notes
