"""자체 검사. 사용자 데이터(data/, docs/)는 건드리지 않고 임시 폴더를 쓴다.

python scripts/self_check.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="cardnews_check_"))
os.environ["CARDNEWS_DATA"] = str(TMP / "data")
os.environ["CARDNEWS_DOCS"] = str(TMP / "docs")
(TMP / "data").mkdir()
(TMP / "data" / "settings.json").write_text((ROOT / "data" / "settings.json").read_text(encoding="utf-8"), encoding="utf-8")
for k in ("IG_ACCESS_TOKEN", "IG_USER_ID", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "GH_PAT"):
    os.environ.pop(k, None)

from engine import build, caption, doctext, embargo, filter as flt, history, license, pages, publish, sources_news, splitter  # noqa: E402
from engine.cards import H, W, Item  # noqa: E402
from engine.common import KST, squash  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
results: list[tuple[bool, str]] = []


def check(ok: bool, name: str) -> None:
    results.append((bool(ok), name))
    print(("  ✅ " if ok else "  ❌ ") + name)


def kst(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=KST)


print("1. 공공누리")
page = (FIX / "view_kogl1.html").read_text(encoding="utf-8")
lic = license.detect(page)
check(lic["type"] == 1 and lic["usable"] and lic["text_only"], "정책브리핑 실제 페이지 → 제1유형(텍스트에 한함)")
for n in (2, 3, 4):
    d = license.detect(f'<img src="/images/v5/common/open_type_0{n}.png" alt="공공누리 공공저작물 자유이용허락 {n}유형">')
    check(d["type"] == n and not d["usable"], f"제{n}유형 → 사용 불가")
check(license.detect("<p>아무 표시 없음</p>")["usable"] is False, "표시 없음 → 사용 불가")

print("2. 보도시점(엠바고)")
cases = [
    ("보도자료\n보도시점 : 2026. 9. 17.(목) 11:00 이후(9. 18.(금) 조간) / 배포 : 2026. 9. 17.(목)", kst(2026, 9, 17, 11)),
    ("보도시점 : 2026. 9. 18.(금) 조간 / 배포 : 2026. 9. 17.(목)", kst(2026, 9, 18, 6)),
    ("보도일시: 2026.9.17.(목) 석간", kst(2026, 9, 17, 12)),
    ("보도시점 : 배포 즉시 / 배포 : 2026. 9. 16.(수)", kst(2026, 9, 16, 0)),
    ("보도 : 9.18.(금) 조간(9.17.(목) 12:00 이후 인터넷 게재 가능)", kst(2026, 9, 17, 12)),
    ("보도시점 : 2026. 9. 17.(목) 오후 2:30", kst(2026, 9, 17, 14, 30)),
    ("보도 일시 2026.9.17.(목) 배포시 배포 2026. 9. 17.(목)", kst(2026, 9, 17, 0)),
]
for text, want in cases:
    got = datetime.fromisoformat(embargo.parse(text, date(2026, 9, 17))["available_at"])
    check(got == want, f"{text[:40]}… → {want:%m/%d %H:%M} (결과 {got:%m/%d %H:%M})")
unk = embargo.parse("보도자료\n제목만 있음", date(2026, 9, 17))
check(not unk["certain"] and datetime.fromisoformat(unk["available_at"]) == kst(2026, 9, 18, 6), "못 읽으면 다음 날 06:00(보수적)")
check(not embargo.is_open(embargo.parse(cases[1][0], date(2026, 9, 17)), kst(2026, 9, 18, 5, 59)), "보도시점 1분 전 → 올리기 막힘")

print("3. 원문 나누기(글자 그대로)")
for name in ("molit_sample.pdf", "molit_land.pdf"):
    text, info = doctext.pdf_text((FIX / name).read_bytes(), with_info=True)
    p = splitter.parse(text)
    cards, cinfo = splitter.build_cards(p.items)
    check(len(cards) >= 1, f"{name}: 본문 카드 {len(cards)}장")
    check(splitter.verify(cards, text) == [], f"{name}: 모든 카드 글자가 원문의 부분 문자열")
    check(all(squash(it.text) not in ("",) for c in cards for it in c), f"{name}: 빈 줄 없음")
    check(len(cards) <= 8, f"{name}: 본문 카드 8장 이하")
    mid = [it for c in cards for it in c if it.level != "system" and not it.cont and it.text and it.text[-1] not in ".다함음임됨”\")」’'"]
    check(True, f"{name}: 문장 끝이 아닌 항목 {len(mid)}개(제목형 소제목 포함, 참고용)")
    check("담당" not in " ".join(it.text for c in cards for it in c), f"{name}: 담당부서 줄 제외")
_, info = doctext.pdf_text((FIX / "molit_land.pdf").read_bytes(), with_info=True)
check(info["tables_removed"] >= 1, f"표 {info['tables_removed']}개를 원문에서 뺌")
fake = [[Item(0, "□", "원문에 없는 문장을 지어냈다.")]]
check(splitter.verify(fake, "□ 실제 원문 문장이다.") != [], "원문에 없는 글이 들어가면 검사에서 걸림")
page_break = chr(10).join(["□ 쪽을 넘어가는 문장은", "- 3 -", "보도자료", "원문 그대로 이어진다."])
pb_items = splitter.parse(page_break).items
check(splitter.verify([pb_items], page_break) == [], "쪽 번호 사이로 이어지는 문장도 원문으로 인정")

print("4. 관련도·광고·중복")
check(flt.score("토지거래허가구역 내 실거주 유예 연장", "", {})[0] >= 3, "부동산 제목 점수")
check(flt.score("지방자치인재개발원 한가위 장터", "", {})[0] == 0, "인재개발원 ≠ 재개발")
check(flt.score("핵심광물 공급망 MOU", "", {})[0] == 0, "공급망 ≠ 주택 공급")
check(flt.is_ad("[분양] ○○ 모델하우스 그랜드 오픈", {}), "광고성 제목 제외")
check(flt.similar("정부, 공공택지 3만호 공급 앞당긴다", "[속보] 정부 공공택지 3만호 공급 앞당긴다"), "같은 기사 중복 판정")

check(flt.same_topic("토지거래허가구역 실거주 유예 연장", "토허구역 내 실거주 의무 2029년까지 유예", {}), "같은 소식(토허구역=토지거래허가구역) 묶기")
check(not flt.same_topic("대구 아파트값 2주째 보합", "서울 아파트값 84주 상승", {}), "일반어(아파트값)만 같으면 다른 소식")
check(sources_news.off_topic("'구해줘! 홈즈' 분당 아파트 소개", {}), "예능 기사 제외")

print("5. 뉴스(본문·요약문 미사용)")
settings = json.loads((TMP / "data" / "settings.json").read_text(encoding="utf-8"))
raw_items = [{"title": f"<b>양도세</b> 중과 완화 {i}번째 &quot;효과&quot;", "link": f"https://www.yna.co.kr/{i}",
              "description": "이 요약문은 절대 쓰면 안 되는 기사 본문 일부 SECRET_DESC", "pubDate": "Thu, 17 Sep 2026 09:0%d:00 +0900" % i}
             for i in range(6)]
pool = [{"title": sources_news.clean(a["title"]) + f" 지역{i}", "link": a["link"], "press": sources_news.press_name(a["link"], {}) + str(i),
         "published": f"2026-09-17T09:0{i}:00+09:00", "date_label": "2026.09.17 09:00"} for i, a in enumerate(raw_items)]
check(pool[0]["title"].startswith("양도세 중과 완화 0번째 \"효과\""), "제목의 <b>·&quot; 정리")
check(sources_news.press_name("https://www.yna.co.kr/view/1", {}) == "연합뉴스", "주소 → 언론사 이름")
chosen = sources_news.select([dict(pool[0]), dict(pool[1], title="전혀 다른 전세 대출 규제 기사")], {}, [])
check(len(chosen) == 2, "뉴스 고르기")
meta = build.build_news(chosen, "2026-09-17", 2, settings, ["한 줄 설명"])
blob = json.dumps(meta, ensure_ascii=False) + meta["caption"]
check("SECRET_DESC" not in blob and "description" not in blob, "뉴스 세트에 기사 요약문(description) 없음")

print("6. 카드 파일·캡션")
text = doctext.pdf_text((FIX / "molit_land.pdf").read_bytes())
rel = {"news_id": "1", "url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156782110",
       "title": "토지거래허가구역 내 실거주 유예, '27년 12월 31일까지 연장·확대", "dept": "국토교통부", "list_date": "2026-09-17",
       "license": lic, "embargo": embargo.parse(text, date(2026, 9, 17)), "source_file": "a.pdf", "text": text}
m = build.build_policy(rel, "정책", "2026-09-17", 1, settings)
check(m["ok"], "정책 세트 만들기")
from PIL import Image  # noqa: E402
folder = TMP / "docs" / "2026-09-17" / "set-1"
sizes = [Image.open(folder / f).size for f in m["cards"]]
check(all(s == (W, H) for s in sizes), "모든 카드 1080×1350")
check(all((folder / f).stat().st_size < 8 * 1024 * 1024 for f in m["cards"]), "모든 카드 8MB 이하 JPEG")
check(2 <= len(m["cards"]) <= 10, f"카드 {len(m['cards'])}장(2~10)")
check(set(m.get("styles", {})) == {"1", "2"}, "스타일 1·2 모두 만들어짐")
check(len(m["styles"]["1"]) == len(m["styles"]["2"]), "두 스타일의 장 수가 같음")
check(all(Image.open(folder / f).size == (W, H) for f in m["styles"]["2"]), "스타일 2 카드도 1080×1350")
check(caption.check(m["caption"]) == [], "캡션 2,200자·해시태그 30개 이내")
check("출처: 국토교통부 보도자료" in m["caption"] and "원문 보기" not in m["caption"] and "상담하세요" not in m["caption"],
      "캡션: 짧은 출처만(원문 보기·면책 문구 없음)")
long_cap = caption.policy(dict(m), "가나다라마바사 다. " * 400, settings)
check(len(long_cap) <= 2200 and "출처" in long_cap, "긴 첫 문단은 줄이고 출처는 유지")

print("7. 게시 전 검사(연습 모드, 인스타 접속 없음)")
pages.build_day("2026-09-17", settings)
pages.build_index(settings)
idx = (TMP / "docs" / "2026-09-17" / "index.html").read_text(encoding="utf-8")
check("IG_ACCESS_TOKEN" not in idx and "access_token" not in idx, "확인 페이지에 열쇠 없음")
m["embargo"] = {"available_at": "2099-01-01T06:00:00+09:00", "raw": "", "rule": "", "certain": True}
(folder / "set.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
check(publish.post("2026-09-17", 1, "연습", "", "") == 1, "보도시점 전이면 연습 게시도 거부")
m["embargo"] = {"available_at": "2000-01-01T06:00:00+09:00", "raw": "", "rule": "", "certain": True}
(folder / "set.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
check(publish.post("2026-09-17", 1, "실제", "네", "") == 1, "실제 모드에 확인 문구가 틀리면 거부")
check(publish.post("2026-09-17", 1, "연습", "", "") == 0, "연습 모드는 올리지 않고 통과 기록")
h = history.load()
check(history.find_post(h, "2026-09-17", 1, "실제") is None, "연습은 '올림'으로 기록되지 않음")

print("8. 인스타 게시 순서(가짜 서버, 실제 접속 없음)")
import httpx  # noqa: E402
from engine import instagram  # noqa: E402

calls: list[str] = []
status_polls = {"n": 0}


def fake(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    body = dict(httpx.QueryParams(request.content.decode())) if request.method == "POST" else dict(request.url.params)
    calls.append(f"{request.method} {path} {body.get('media_type', '')}{'item' if body.get('is_carousel_item') else ''}")
    if "TOKEN_SHOULD_NOT_LEAK" in str(request.url) and request.method == "POST":
        return httpx.Response(500)
    if path.endswith("/media") and request.method == "POST":
        return httpx.Response(200, json={"id": f"c{len(calls)}"})
    if path.endswith("/media_publish"):
        return httpx.Response(200, json={"id": "M1"})
    if "status_code" in body.get("fields", ""):
        status_polls["n"] += 1
        return httpx.Response(200, json={"status_code": "IN_PROGRESS" if status_polls["n"] == 1 else "FINISHED"})
    if body.get("fields") == "permalink":
        return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/TEST/"})
    return httpx.Response(200, json={})


ig = instagram.Instagram("123", "TOKEN_SHOULD_NOT_LEAK")
ig.c = httpx.Client(transport=httpx.MockTransport(fake))
instagram.time.sleep = lambda s: None
res = ig.publish_carousel([f"https://x.github.io/c/{i}.jpg" for i in range(3)], "캡션")
seq = [c for c in calls if "status" not in c]
check(res["permalink"].endswith("/TEST/") and res["media_id"] == "M1", "게시 결과·링크 받음")
check(sum("item" in c for c in calls) == 3 and any("CAROUSEL" in c for c in calls), "사진 3장 준비 → 캐러셀 묶기")
check(calls.index(next(c for c in calls if "media_publish" in c)) > calls.index(next(c for c in calls if "CAROUSEL" in c)),
      "처리 완료(FINISHED) 확인 뒤 게시")
check(status_polls["n"] >= 2, "처리 중(IN_PROGRESS)이면 기다림")
from engine.common import redact  # noqa: E402
check("TOKEN_SHOULD_NOT_LEAK" not in redact("error https://graph.instagram.com/x?access_token=TOKEN_SHOULD_NOT_LEAK"),
      "오류 문장에서 토큰 가림")


def fake_expired(request):
    return httpx.Response(400, json={"error": {"message": "Error validating access token", "code": 190}})


ig2 = instagram.Instagram("123", "TOKEN_SHOULD_NOT_LEAK")
ig2.c = httpx.Client(transport=httpx.MockTransport(fake_expired))
try:
    ig2.check()
    check(False, "만료 토큰 안내")
except instagram.IGError as e:
    check("만료" in str(e) and "TOKEN_SHOULD_NOT_LEAK" not in str(e), "만료 토큰 → 쉬운 안내(토큰 노출 없음)")

ig3 = instagram.Instagram("", "TOKEN_SHOULD_NOT_LEAK")
ig3.c = httpx.Client(transport=httpx.MockTransport(
    lambda r: httpx.Response(200, json={"user_id": "17841400000000000", "username": "test"} if r.url.path.endswith("/me") else {"username": "test"})))
ig3.check()
check(ig3.user_id == "17841400000000000", "사용자 ID를 안 넣어도 토큰으로 알아냄")

print("9. 노트북·GitHub 나눠 쓰기")
from engine import make  # noqa: E402
from engine.common import write_json  # noqa: E402
day_dir = TMP / "docs" / "2026-09-17"
write_json(day_dir / "run-gov.json", {"messages": [{"level": "ok", "text": "노트북_보도자료_메시지"}], "candidates": [], "finished_at": "2026-09-17T07:01:00+09:00"})
write_json(day_dir / "run-news.json", {"messages": [{"level": "warn", "text": "클라우드_뉴스_메시지"}], "news_excluded": [], "finished_at": "2026-09-17T07:05:00+09:00"})
pages.build_day("2026-09-17", settings)
idx = (day_dir / "index.html").read_text(encoding="utf-8")
check("노트북_보도자료_메시지" in idx and "클라우드_뉴스_메시지" in idx, "노트북·GitHub 결과가 한 페이지에 합쳐짐")
before = {p.name for p in day_dir.iterdir()}
make.make_news("2026-09-17", settings)
after = {p.name for p in day_dir.iterdir()}
check("set-1" in after and (day_dir / "run-gov.json").read_text(encoding="utf-8").count("노트북_보도자료_메시지") == 1,
      "뉴스 만들기가 노트북 파일(set-1, run-gov)을 건드리지 않음")
wf = (ROOT / ".github" / "workflows" / "make.yml").read_text(encoding="utf-8")
check("--only news" in wf, "GitHub 매일 실행은 뉴스만(정부 사이트 해외 차단)")


print("9-1. 뉴스 ↔ 정부 발표 원문")
from engine import govlink  # noqa: E402
lead = ("토지거래허가구역 내 주택 거래 시, 세입자가 거주하고 있어 매수자가 바로 입주하기 어려운 주택에 대해, 내년 말까지 실거주 유예를 신청할 수 있게 된다. "
        "다만, 무주택 실수요자 요건과 입주 후 2년 거주의무는 그대로 유지 된다.")
rec = govlink.release_record(rel, lead, ["임대 중인 주택에 대한 실거주 유예 신청 기한을 '27.12.31일까지 연장"])
write_json(day_dir / "releases.json", {"date": "2026-09-17", "releases": [rec]})
news_items = [
    {"title": "토허구역 실거주 유예 내년 말까지 연장…임대차 갱신도 허용", "link": "https://www.joseilbo.com/1", "press": "조세일보", "published": "", "date_label": ""},
    {"title": "대구 아파트값 2주째 보합…경북 매매·전세 동반 하락", "link": "https://www.kyongbuk.co.kr/2", "press": "경북일보", "published": "", "date_label": ""},
]
linked = govlink.attach(news_items, "2026-09-17", settings)
check(bool(linked[0].get("gov")) and not linked[1].get("gov"), "같은 소식 기사에만 정부 발표 원문이 붙음")
check(squash(linked[0]["gov"]["text"]) in squash(lead) and squash(lead) in squash(text), "붙인 글은 보도자료 원문 그대로")
check(len(linked[0]["gov"]["text"]) <= govlink.MAX_CHARS + 60, "원문은 한두 문장만")
bad_rec = dict(rec, url="https://x/2", license_usable=False)
write_json(day_dir / "releases.json", {"date": "2026-09-17", "releases": [bad_rec]})
check(not govlink.attach(news_items, "2026-09-17", settings)[0].get("gov"), "공공누리 제1유형이 아니면 붙이지 않음")
nm = build.build_news(linked, "2026-09-17", 2, settings)
check("정책브리핑" in nm["caption"] and "상담하세요" not in nm["caption"], "뉴스 캡션에 정부 발표 출처, 면책 문구 없음")
nm["news_items"][0]["gov"]["embargo"] = {"available_at": "2099-01-01T06:00:00+09:00", "raw": "", "rule": "", "certain": True}
write_json(day_dir / "set-2" / "set.json", nm)
check(publish.post("2026-09-17", 2, "연습", "", "") == 1, "붙인 정부 발표가 보도시점 전이면 뉴스 게시도 거부")

print("9-2. 법령·생활법령 세트")
from engine import sources_law, sources_easylaw  # noqa: E402
why = "[일부개정] ◇ 개정이유 및 주요내용 도심 공공주택 복합사업의 유효기간을 2029년 12월 31일까지로 3년 연장한다. 그 밖에 절차를 정비한다. ◇ 주요내용 가. 어쩌고"
one = sources_law.first_reason_sentences(why)
check(one.startswith("도심 공공주택") and "주요내용" not in one and squash(one) in squash(why), "법령 개정이유 앞 문장만 원문 그대로")
law_items = [{"title": "주택법", "link": "https://www.law.go.kr/법령/주택법", "press": "국토교통부",
              "published": "20260918", "date_label": "시행 2026.09.18",
              "gov": {"dept": "국가법령정보센터", "title": "주택법", "url": "https://www.law.go.kr/법령/주택법",
                      "date_label": "공포 2026.09.08", "text": one, "license_label": "법제처 국가법령정보센터", "embargo": None},
              "source_note": "법령 출처: 국가법령정보센터(법제처)"}]
lm = build.build_news(law_items, "2026-09-18", 3, settings, kind="law",
                      cover={"tag": "법령", "lines": ("곧 시행되는", "부동산 법령"), "count_label": "법령 {n}건",
                             "title": "곧 시행되는 부동산 법령", "caption_title": "곧 시행되는 부동산 법령"})
check(lm["kind"] == "law" and len(lm["cards"]) == 2 and "국가법령정보센터" in lm["caption"], "법령 세트 카드·캡션")
el_text = chr(10).join(["공인중개사의 개념", "“공인중개사”란 「공인중개사법」에 따른 자격을 취득한 사람을 말합니다.", "공인중개사가 되려는 사람은 시험에 합격해야 합니다."])
rel_el = sources_easylaw.as_release("공인중개사", {"title": "공인중개사 개요", "url": "https://www.easylaw.go.kr/x"}, el_text, "2026-09-18")
em = build.build_policy(rel_el, "생활법령", "2026-09-18", 4, settings, kind="easylaw")
check(em["ok"] and em["kind"] == "easylaw", "생활법령 세트 만들기(기호 없는 글도 카드로)")
check(all(squash(i["text"]) in squash(el_text) for c_ in em["card_items"] for i in c_ if i["level"] != "system"), "생활법령 카드도 원문 그대로")
check("보도자료" not in (em.get("source_label") or ""), "법령·생활법령 카드에는 '보도자료' 표시 안 함")

print("10. 사용자 데이터 보호")
check(not (ROOT / "data" / "history.json").exists() or os.environ["CARDNEWS_DATA"] != str(ROOT / "data"), "검사는 임시 폴더만 사용")
req = (ROOT / "requirements.txt").read_bytes()
check(all(b < 128 for b in req), "requirements.txt 는 ASCII만")

bad = [n for ok, n in results if not ok]
print(f"\n결과: {len(results) - len(bad)}/{len(results)} 통과")
if bad:
    print("실패:\n - " + "\n - ".join(bad))
sys.exit(1 if bad else 0)
