"""확인 페이지(GitHub Pages, docs/) 만들기. 아이패드·휴대폰용, 정적 HTML.

토큰·열쇠는 절대 넣지 않는다.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime

from . import embargo, history
from .common import data_dir, docs_dir, now_kst, read_json

CSS = """
:root{--bg:#F7F5F2;--card:#fff;--text:#2F2B28;--sub:#827E79;--line:#E4DDD5;--primary:#9E9577;--accent:#955330;
--ok:#2E7D4F;--warn:#B7791F;--bad:#B3261E}
@media (prefers-color-scheme:dark){:root{--bg:#1C1A18;--card:#26231F;--text:#EFEAE4;--sub:#A9A29A;--line:#3A3530}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Malgun Gothic",sans-serif;
padding:16px;padding-bottom:80px}
main{max-width:980px;margin:0 auto}
h1{font-size:24px;margin:8px 0 4px}h2{font-size:20px;margin:0 0 6px}h3{font-size:16px;margin:18px 0 6px}
a{color:var(--accent)}
.sub{color:var(--sub);font-size:14px}
.box{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:14px 0}
.alert{border-radius:12px;padding:12px 14px;margin:10px 0;font-weight:600}
.alert.warn{background:#FFF4DB;color:#6B4A00}.alert.bad{background:#FDE7E5;color:#7A1A14}.alert.ok{background:#E3F4EA;color:#1E5436}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{font-size:13px;border-radius:99px;padding:3px 10px;border:1px solid var(--line);background:var(--bg)}
.chip.ok{border-color:#9CD3B2;color:var(--ok)}.chip.warn{border-color:#F0C674;color:var(--warn)}.chip.bad{border-color:#F2A7A1;color:var(--bad)}
.slider{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:10px;-webkit-overflow-scrolling:touch;padding-bottom:6px}
.slider img{flex:0 0 min(78%,420px);width:min(78%,420px);max-width:100%;aspect-ratio:4/5;scroll-snap-align:center;border-radius:10px;border:1px solid var(--line);background:#ddd}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:0;border-radius:12px;padding:12px 16px;font-size:16px;font-weight:700;
background:var(--accent);color:#fff;text-decoration:none;cursor:pointer;min-height:48px}
.btn.gray{background:var(--line);color:var(--text)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
pre.caption{white-space:pre-wrap;word-break:break-all;background:var(--bg);border-radius:10px;padding:12px;font:14px/1.6 inherit;max-height:320px;overflow:auto}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:15px}
.kv b{white-space:nowrap}
.copy{font-size:14px;padding:6px 10px;min-height:36px}
details summary{cursor:pointer;font-weight:700;padding:6px 0}
.orig p{margin:4px 0;padding:4px 8px;border-radius:6px;font-size:14px}
.orig .all{background:#FFF1A8;color:#2F2B28}.orig .part{background:#FFF8D6;color:#2F2B28}.orig .no{color:var(--sub)}
ol.steps{padding-left:22px}ol.steps li{margin:4px 0}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--line);padding:6px;text-align:left;vertical-align:top}
.tablewrap{overflow-x:auto}
"""

JS = """
function copyText(id,btn){const t=document.getElementById(id).innerText;
 navigator.clipboard.writeText(t).then(()=>{const o=btn.innerText;btn.innerText='복사됨';setTimeout(()=>btn.innerText=o,1500)})
 .catch(()=>{const r=document.createRange();r.selectNodeContents(document.getElementById(id));const s=getSelection();s.removeAllRanges();s.addRange(r);});}
"""


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def repo_info(settings: dict) -> dict:
    repo = os.environ.get("GITHUB_REPOSITORY") or settings.get("github_repo") or ""
    if "/" not in repo:
        return {"repo": "", "pages": "", "make": "", "publish": "", "actions": ""}
    owner, name = repo.split("/", 1)
    return {
        "repo": repo,
        "pages": f"https://{owner.lower()}.github.io/{name}/",
        "make": f"https://github.com/{repo}/actions/workflows/make.yml",
        "publish": f"https://github.com/{repo}/actions/workflows/publish.yml",
        "actions": f"https://github.com/{repo}/actions",
    }


def _page(title: str, body: str, depth: int) -> str:
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<meta http-equiv='Cache-Control' content='no-cache'>"
            f"<meta name='robots' content='noindex'>"
            f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>{body}</main>"
            f"<script>{JS}</script></body></html>")


def _token_alert() -> str:
    st = read_json(data_dir() / "token_status.json", {})
    if not st:
        return ""
    msg = st.get("message")
    level = st.get("level", "warn")
    return f"<div class='alert {e(level)}'>{e(msg)}</div>" if msg and level != "ok" else ""


def _set_block(meta: dict, day: str, h: dict, info: dict, version: str) -> str:
    n = meta["set"]
    kind = meta["kind"]
    base = f"set-{n}/"
    posted = history.find_post(h, day, n, "실제")
    practice = history.find_post(h, day, n, "연습")
    out = [f"<section class='box' id='set-{n}'>"]
    out.append(f"<div class='sub'>세트 {n} · {'정책·세금 카드뉴스' if kind == 'policy' else '뉴스 헤드라인'}</div>")
    out.append(f"<h2>{e(meta.get('title'))}</h2>")

    chips = []
    if posted:
        chips.append(("ok", "인스타에 올림"))
    elif practice:
        chips.append(("", "연습 게시 해 봄"))
    else:
        chips.append(("", "아직 안 올림"))
    now = now_kst()
    if meta.get("embargo"):
        emb = meta["embargo"]
        if embargo.is_open(emb, now):
            chips.append(("ok", "지금 올릴 수 있어요"))
        else:
            chips.append(("warn", f"{embargo.describe(emb)}부터 올릴 수 있어요"))
    if meta.get("license"):
        lic = meta["license"]
        chips.append(("ok" if lic.get("usable") else "bad", lic.get("label", "")))
    if meta.get("badge"):
        chips.append(("warn", meta["badge"]))
    if meta.get("omitted"):
        chips.append(("", "뒷부분 (중략)"))
    out.append("<div class='chips'>" + "".join(f"<span class='chip {c}'>{e(t)}</span>" for c, t in chips) + "</div>")

    if not meta.get("ok"):
        out.append("<div class='alert bad'>카드를 만들지 않았어요: " + e(" / ".join(meta.get("problems", []))) + "</div>")
        out.append("</section>")
        return "".join(out)

    if posted and posted.get("permalink"):
        out.append(f"<p><a class='btn gray' href='{e(posted['permalink'])}' target='_blank' rel='noopener'>인스타 게시물 보기 ↗</a></p>")

    imgs = "".join(f"<img loading='lazy' src='{base}{e(f)}?v={version}' alt='카드 {i}'>"
                   for i, f in enumerate(meta.get("cards", []), 1))
    out.append(f"<div class='slider'>{imgs}</div><div class='sub'>옆으로 밀어서 넘겨 보세요 · {len(meta.get('cards', []))}장</div>")

    if kind == "policy":
        emb = meta.get("embargo") or {}
        out.append("<div class='kv' style='margin-top:10px'>"
                   f"<b>부처</b><span>{e(meta.get('dept'))}</span>"
                   f"<b>발표일</b><span>{e(meta.get('date_label'))}</span>"
                   f"<b>보도시점</b><span>{e(emb.get('raw') or '-')} → {e(embargo.describe(emb)) if emb else ''}"
                   f"{'' if emb.get('certain', True) else ' (읽지 못해 보수적으로 정함)'}</span>"
                   f"<b>원문</b><span><a href='{e(meta.get('url'))}' target='_blank' rel='noopener'>정책브리핑에서 보기 ↗</a></span>"
                   "</div>")
    else:
        rows = "".join(f"<tr><td>{i}</td><td><a href='{e(a['link'])}' target='_blank' rel='noopener'>{e(a['title'])}</a></td>"
                       f"<td>{e(a['press'])}</td><td>{e(a['date_label'])}</td></tr>"
                       for i, a in enumerate(meta.get("news_items", []), 1))
        out.append(f"<h3>기사 목록</h3><div class='tablewrap'><table><tr><th>#</th><th>제목</th><th>언론사</th><th>시각</th></tr>{rows}</table></div>")

    cap_id = f"cap-{day}-{n}"
    out.append(f"<h3>캡션</h3><pre class='caption' id='{cap_id}'>{e(meta.get('caption'))}</pre>"
               f"<button class='btn gray copy' onclick=\"copyText('{cap_id}',this)\">캡션 복사</button>")
    for p in meta.get("caption_problems") or []:
        out.append(f"<div class='alert warn'>{e(p)}</div>")

    if kind == "policy" and meta.get("original"):
        paras = "".join(f"<p class='{e(o['used'])}'>{e(o['text'])}</p>" for o in meta["original"])
        out.append("<details class='orig'><summary>원문과 대조하기</summary>"
                   "<div class='sub'>노란색 = 카드에 들어간 글(원문 그대로), 흐린 글 = 뺀 부분</div>"
                   f"{paras}</details>")

    # 올리기 안내
    if not posted:
        date_id, set_id = f"d-{day}-{n}", f"s-{day}-{n}"
        link = info.get("publish")
        btn = (f"<a class='btn' href='{e(link)}' target='_blank' rel='noopener'>인스타에 올리기 →</a>" if link
               else "<span class='sub'>(GitHub에 올린 뒤 버튼이 생겨요)</span>")
        out.append(
            "<h3>인스타에 올리기</h3>"
            "<div class='kv'>"
            f"<b>날짜</b><span><span id='{date_id}'>{e(day)}</span> <button class='btn gray copy' onclick=\"copyText('{date_id}',this)\">복사</button></span>"
            f"<b>세트 번호</b><span><span id='{set_id}'>{n}</span> <button class='btn gray copy' onclick=\"copyText('{set_id}',this)\">복사</button></span>"
            "</div>"
            "<ol class='steps'>"
            "<li>아래 버튼을 눌러 GitHub 화면으로 가요(GitHub 앱이나 사파리에 로그인돼 있어야 해요)</li>"
            "<li>오른쪽의 <b>Run workflow</b>를 눌러요</li>"
            "<li>날짜·세트 번호를 위 값으로 넣어요</li>"
            "<li>처음엔 <b>모드 = 연습</b>으로 해 보고, 실제로 올릴 땐 <b>실제</b> + 확인 칸에 <b>올립니다</b></li>"
            + ("<li>뉴스 세트는 '한마디' 칸에 기사별로 한 줄 설명을 적을 수 있어요(비우면 없음)</li>" if kind == "news" else "")
            + "<li>초록색 <b>Run workflow</b> → 2~5분 뒤 이 페이지에 결과가 나와요</li></ol>"
            f"<div class='row'>{btn}</div>"
        )
    out.append("</section>")
    return "".join(out)


def build_day(day: str, settings: dict) -> None:
    root = docs_dir() / day
    sets = []
    for p in sorted(root.glob("set-*/set.json"), key=lambda x: int(x.parent.name.split("-")[1])):
        sets.append(read_json(p, None))
    sets = [s for s in sets if s]
    run = read_json(root / "run.json", {})
    h = history.load()
    info = repo_info(settings)
    version = now_kst().strftime("%Y%m%d%H%M%S")

    body = [f"<p><a href='../index.html'>← 날짜 목록</a></p><h1>{e(day)} 카드뉴스</h1>",
            f"<div class='sub'>만든 시각 {e(run.get('finished_at', '')[:16].replace('T', ' '))}</div>", _token_alert()]
    for msg in run.get("messages", []):
        body.append(f"<div class='alert {e(msg.get('level', 'warn'))}'>{e(msg['text'])}</div>")
    if not sets:
        body.append("<div class='box'>오늘은 만들 내용이 없어요.</div>")
    for s in sets:
        body.append(_set_block(s, day, h, info, version))

    cands = run.get("candidates", [])
    if cands:
        rows = "".join(
            f"<tr><td>{e(c.get('dept'))}</td><td><a href='{e(c['url'])}' target='_blank' rel='noopener'>{e(c['title'])}</a></td>"
            f"<td>{e(c.get('score', ''))}</td><td>{e(c.get('status', ''))}</td></tr>" for c in cands)
        make_link = info.get("make")
        how = (f"<p class='sub'>다른 보도자료로 만들려면: 주소를 복사 → <a href='{e(make_link)}' target='_blank' rel='noopener'>만들기 화면</a> → "
               "Run workflow → '원문 주소' 칸에 붙여넣기</p>") if make_link else ""
        body.append(f"<details class='box'><summary>오늘 살펴본 보도자료 {len(cands)}건</summary>{how}"
                    f"<div class='tablewrap'><table><tr><th>부처</th><th>제목</th><th>점수</th><th>결과</th></tr>{rows}</table></div></details>")
    excluded_news = run.get("news_excluded", [])
    if excluded_news:
        rows = "".join(f"<tr><td>{e(x['title'])}</td><td>{e(x['reason'])}</td></tr>" for x in excluded_news[:30])
        body.append(f"<details class='box'><summary>뺀 기사 {len(excluded_news)}건</summary>"
                    f"<div class='tablewrap'><table>{rows}</table></div></details>")
    (root / "index.html").write_text(_page(f"{day} 카드뉴스", "".join(body), 1), encoding="utf-8")


def build_index(settings: dict) -> None:
    root = docs_dir()
    root.mkdir(parents=True, exist_ok=True)
    h = history.load()
    days = sorted([p.name for p in root.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"], reverse=True)
    items = []
    for day in days:
        sets = [read_json(p, {}) for p in sorted((root / day).glob("set-*/set.json"))]
        parts = []
        for s in sets:
            if not s:
                continue
            posted = history.find_post(h, day, s["set"], "실제")
            state = "✅ 올림" if posted else ("⚠️ 못 만듦" if not s.get("ok") else "⏳ 확인 대기")
            parts.append(f"<div>{state} · {e(s.get('title'))}</div>")
        items.append(f"<a class='box' style='display:block;text-decoration:none;color:inherit' href='{day}/index.html'>"
                     f"<h2>{e(day)}</h2>{''.join(parts) or '<div class=sub>만든 세트 없음</div>'}</a>")
    info = repo_info(settings)
    top = ""
    if info.get("actions"):
        top = f"<p class='sub'><a href='{e(info['actions'])}' target='_blank' rel='noopener'>GitHub 실행 기록 보기 ↗</a></p>"
    body = f"<h1>부동산 카드뉴스 확인</h1>{top}{_token_alert()}" + "".join(items)
    (root / "index.html").write_text(_page("부동산 카드뉴스 확인", body, 0), encoding="utf-8")
    (root / ".nojekyll").write_text("", encoding="utf-8")
