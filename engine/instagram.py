"""Instagram 공식 API(콘텐츠 게시). 확인한 문서(2026-09-17):

- Instagram 로그인 방식 호스트: graph.instagram.com / 페이스북 로그인 방식: graph.facebook.com (예시 v25.0)
- 캐러셀: 사진마다 POST /{IG_ID}/media (image_url, is_carousel_item=true)
          → POST /{IG_ID}/media (media_type=CAROUSEL, children, caption)
          → GET /{container}?fields=status_code 가 FINISHED 될 때까지 대기
          → POST /{IG_ID}/media_publish (creation_id)
- 사진: JPEG만, 8MB 이하, 비율 4:5~1.91:1, 공개 주소 필요. 캐러셀 최대 10장
- 게시 한도: 24시간에 100건, GET /{IG_ID}/content_publishing_limit
- 토큰 갱신: GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token (발급 24시간 이후, 만료 전, 새 토큰 60일)
"""
from __future__ import annotations

import time

import httpx

from .common import log, redact, register_secret


class IGError(RuntimeError):
    pass


class Instagram:
    def __init__(self, user_id: str, token: str, host: str = "graph.instagram.com", version: str = "v25.0"):
        if not token:
            raise IGError("인스타 열쇠(IG_ACCESS_TOKEN)가 GitHub 비밀 보관함에 없어요")
        register_secret(token)
        self.user_id = (user_id or "").strip()
        self.token = token
        self.host = host
        self.base = f"https://{host}/{version}"
        self.c = httpx.Client(timeout=60)

    def _ensure_user(self) -> None:
        """사용자 ID(숫자)를 안 넣었으면 토큰으로 알아낸다(GET /me?fields=user_id)."""
        if self.user_id:
            return
        body = self._req("GET", "me", fields="user_id,username")
        self.user_id = str(body.get("user_id") or body.get("id") or "")
        if not self.user_id:
            raise IGError("토큰으로 인스타 계정을 찾지 못했어요. 토큰을 다시 받아 주세요")

    def _req(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        for attempt in range(3):
            try:
                if method == "GET":
                    r = self.c.get(url, params=params)
                else:
                    r = self.c.post(url, data=params)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise IGError(f"인스타 서버에 연결하지 못했어요({type(e).__name__})")
                time.sleep(3 * (attempt + 1))
                continue
            try:
                body = r.json()
            except ValueError:
                body = {}
            if r.status_code == 200 and "error" not in body:
                return body
            err = body.get("error", {}) if isinstance(body, dict) else {}
            msg = err.get("error_user_msg") or err.get("message") or f"HTTP {r.status_code}"
            code = err.get("code")
            if code in (1, 2, 4, 17, 32, 613) and attempt < 2:   # 일시적 오류·호출 한도
                time.sleep(10 * (attempt + 1))
                continue
            if code == 190:
                raise IGError("인스타 열쇠(토큰)가 만료됐거나 잘못됐어요. 새 토큰을 받아 비밀 보관함에 넣어 주세요")
            raise IGError(redact(f"인스타가 거절했어요: {msg}"))
        raise IGError("인스타 요청이 계속 실패했어요")

    # -------------------------------------------------- 읽기
    def check(self) -> dict:
        self._ensure_user()
        return self._req("GET", self.user_id, fields="username")

    def quota(self) -> dict:
        self._ensure_user()
        body = self._req("GET", f"{self.user_id}/content_publishing_limit", fields="quota_usage,config")
        data = (body.get("data") or [{}])[0]
        usage = data.get("quota_usage", 0)
        total = (data.get("config") or {}).get("quota_total", 100)
        return {"usage": usage, "total": total}

    # -------------------------------------------------- 게시
    def _wait(self, container_id: str, limit_s: int = 300) -> None:
        start = time.time()
        while True:
            st = self._req("GET", container_id, fields="status_code").get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise IGError(f"인스타가 사진을 처리하지 못했어요(상태: {st})")
            if time.time() - start > limit_s:
                raise IGError("인스타 사진 처리가 너무 오래 걸려요. 잠시 뒤 다시 올려 주세요")
            time.sleep(5)

    def publish_carousel(self, image_urls: list[str], caption: str) -> dict:
        if not 2 <= len(image_urls) <= 10:
            raise IGError("캐러셀은 사진 2~10장이어야 해요")
        self._ensure_user()
        children = []
        for i, u in enumerate(image_urls, 1):
            body = self._req("POST", f"{self.user_id}/media", image_url=u, is_carousel_item="true")
            children.append(body["id"])
            log(f"사진 {i}/{len(image_urls)} 준비")
        for cid in children:
            self._wait(cid)
        carousel = self._req("POST", f"{self.user_id}/media", media_type="CAROUSEL",
                             children=",".join(children), caption=caption)
        self._wait(carousel["id"])
        pub = self._req("POST", f"{self.user_id}/media_publish", creation_id=carousel["id"])
        media_id = pub["id"]
        permalink = ""
        try:
            permalink = self._req("GET", media_id, fields="permalink").get("permalink", "")
        except IGError:
            pass
        return {"media_id": media_id, "permalink": permalink}


def refresh_token(token: str) -> dict:
    """Instagram 로그인 방식 장기 토큰 갱신. 반환: {access_token, expires_in}"""
    register_secret(token)
    r = httpx.get("https://graph.instagram.com/refresh_access_token",
                  params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or "access_token" not in body:
        msg = (body.get("error") or {}).get("message", f"HTTP {r.status_code}")
        raise IGError(redact(f"토큰 갱신 실패: {msg}"))
    register_secret(body["access_token"])
    return body
