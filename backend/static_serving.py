"""프론트 빌드(frontend/dist) 서빙: 캐시 헤더, 조건부 요청(304), 미리 압축한 GLB.

- /assets/*: Vite가 파일 이름에 내용 해시를 넣으므로 1년 immutable로 캐시한다.
- 그 밖의 파일(index.html·sw.js·models/*.onnx·*.glb·아이콘): 이름이 그대로라 배포 때 내용이 바뀔 수 있으므로 no-cache(쓸 때마다
  확인)로 두고, If-None-Match·If-Modified-Since가 맞으면 본문 없이 304로 답한다. 예전 catch-all은 FileResponse만 돌려줘서
  조건부 요청에도 전체를 다시 보냈다(11MB 입모양 인식 ONNX, 2.5MB 아바타 GLB). 서비스워커가 정적 자산을 stale-while-revalidate로
  다루므로 브라우저의 추정 신선도(마지막 수정 뒤 지난 시간의 10%)가 끝나면 모델을 쓸 때마다 뒤에서 통째로 다시 받았다.
- 확장자가 있는 경로에 파일이 없으면 404다. 예전에는 index.html을 200으로 돌려줘서 서비스워커가 그 HTML을 모델 주소로 캐시할 수 있었다.
- *.glb는 빌드할 때 만든 .gz를 Accept-Encoding: gzip 요청에 Content-Encoding: gzip으로 보낸다(2.5MB → 1.5MB). fly 프록시는
  JS·CSS·wasm은 스스로 압축하지만 application/octet-stream인 GLB는 압축하지 않는다. ONNX는 gzip으로 7%만 줄어 뺀다.

    python static_serving.py precompress frontend/dist
"""
import gzip
import mimetypes
import os
import sys
from email.utils import parsedate

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "no-cache"
PRECOMPRESS_EXT = (".glb",)
_KEEP_ON_304 = ("cache-control", "content-location", "date", "etag", "expires", "vary")


def accepts_gzip(header: str) -> bool:
    """Accept-Encoding에 gzip이 q>0으로 있으면 True."""
    for part in (header or "").split(","):
        token, _, params = part.partition(";")
        if token.strip().lower() not in ("gzip", "x-gzip"):
            continue
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.partition("=")
            if k.strip().lower() == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        if q > 0:
            return True
    return False


def not_modified(response_headers, request_headers) -> bool:
    """조건부 요청이 지금 파일과 맞으면 True. If-None-Match가 있으면 그것만 본다(RFC 9110 13.2.2)."""
    inm = request_headers.get("if-none-match")
    if inm:
        tags = [t.strip().removeprefix("W/") for t in inm.split(",")]
        return "*" in tags or response_headers.get("etag") in tags
    ims, lm = request_headers.get("if-modified-since"), response_headers.get("last-modified")
    if ims and lm:
        a, b = parsedate(ims), parsedate(lm)
        return a is not None and b is not None and a >= b
    return False


def file_response(request: Request, path: str, cache_control: str) -> Response:
    """path를 캐시 헤더와 함께 보낸다. 원본보다 새 path.gz가 있고 gzip을 받으면 그것을 보낸다. 조건부 요청이 맞으면 304."""
    headers = {"Cache-Control": cache_control}
    send_path, media_type = path, None
    gz = path + ".gz"
    if path.endswith(PRECOMPRESS_EXT) and os.path.isfile(gz) and os.path.getmtime(gz) >= os.path.getmtime(path):
        headers["Vary"] = "Accept-Encoding"
        if accepts_gzip(request.headers.get("accept-encoding", "")):
            send_path = gz
            headers["Content-Encoding"] = "gzip"
            media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    resp = FileResponse(send_path, headers=headers, media_type=media_type, stat_result=os.stat(send_path))
    if not_modified(resp.headers, request.headers):
        return Response(status_code=304, headers={k: v for k, v in resp.headers.items() if k in _KEEP_ON_304})
    return resp


class ImmutableStaticFiles(StaticFiles):
    """/assets: 파일 이름에 내용 해시가 있어 내용이 바뀌면 이름도 바뀐다. 304 처리는 StaticFiles가 한다."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = CACHE_IMMUTABLE
        return resp


def mount_frontend(app, dist: str) -> None:
    """dist의 정적 파일과 SPA 라우팅을 app에 붙인다. catch-all이 API 라우트를 가리지 않게 모든 라우트를 등록한 뒤 부른다."""
    assets = os.path.join(dist, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", ImmutableStaticFiles(directory=assets), name="assets")
    dist_real = os.path.realpath(dist)

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_react_app(full_path: str, request: Request):
        """API가 아닌 경로: dist의 파일, 없으면 SPA 라우팅용 index.html."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        # full_path는 사용자 제어이므로 dist 밖으로 벗어나는 경로(../ 등)는 막는다(dist 밖 .env·DB 노출 방지).
        file_path = os.path.realpath(os.path.join(dist, full_path))
        if os.path.commonpath([file_path, dist_real]) == dist_real and os.path.isfile(file_path):
            return file_response(request, file_path, CACHE_REVALIDATE)
        if os.path.splitext(full_path)[1]:
            raise HTTPException(status_code=404, detail="File not found")
        index_path = os.path.join(dist, "index.html")
        if os.path.isfile(index_path):
            return file_response(request, index_path, CACHE_REVALIDATE)
        raise HTTPException(status_code=404, detail="File not found")


def precompress(dist: str, exts=PRECOMPRESS_EXT, level: int = 9) -> list:
    """dist 아래 exts 파일마다 path.gz를 만든다(10% 넘게 줄 때만). 이미지를 빌드할 때 한 번 부른다."""
    made = []
    for root, _, files in os.walk(dist):
        for name in sorted(files):
            if not name.endswith(exts):
                continue
            src = os.path.join(root, name)
            with open(src, "rb") as f:
                raw = f.read()
            data = gzip.compress(raw, compresslevel=level, mtime=0)
            if len(data) < 0.9 * len(raw):
                with open(src + ".gz", "wb") as f:
                    f.write(data)
                made.append((os.path.relpath(src, dist), len(raw), len(data)))
    return made


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "precompress":
        sys.exit("사용법: python static_serving.py precompress <dist>")
    for rel, a, b in precompress(sys.argv[2]):
        print(f"gzip {rel}: {a} -> {b} bytes")
