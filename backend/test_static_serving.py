"""정적 파일 서빙(static_serving.py): 해시 자산 immutable 캐시, 나머지 no-cache + 304, 미리 압축한 GLB, 없는 파일 404.

예전 catch-all은 조건부 요청에도 전체를 다시 보냈다(11MB ONNX·2.5MB GLB를 서비스워커가 재검증할 때마다 다시 받음).
"""
import gzip
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

import static_serving as S

_GLB = b"glTF" + b"\x00\x01morph-target-weights " * 2000
_ONNX = os.urandom(5000)


def _client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "models").mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "sw.js").write_text("self.x = 1", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "models" / "face.glb").write_bytes(_GLB)
    (dist / "models" / "m.onnx").write_bytes(_ONNX)
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    made = S.precompress(str(dist))
    app = FastAPI()

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    S.mount_frontend(app, str(dist))
    return TestClient(app), dist, made


def test_precompress_only_glb(tmp_path):
    _, dist, made = _client(tmp_path)
    assert [m[0] for m in made] == [os.path.join("models", "face.glb")]
    assert gzip.decompress((dist / "models" / "face.glb.gz").read_bytes()) == _GLB
    assert not (dist / "models" / "m.onnx.gz").exists()


def test_hashed_assets_are_immutable_and_revalidate(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.get("/assets/index-abc123.js")
    assert r.status_code == 200 and r.headers["cache-control"] == S.CACHE_IMMUTABLE
    r2 = c.get("/assets/index-abc123.js", headers={"If-None-Match": r.headers["etag"]})
    assert r2.status_code == 304 and r2.content == b""


def test_unhashed_files_answer_conditional_requests_with_304(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.get("/models/m.onnx")
    assert r.status_code == 200 and r.content == _ONNX
    assert r.headers["cache-control"] == S.CACHE_REVALIDATE
    etag = r.headers["etag"]
    for inm in (etag, "W/" + etag, f'"other", {etag}'):
        r2 = c.get("/models/m.onnx", headers={"If-None-Match": inm})
        assert r2.status_code == 304 and r2.content == b"", inm
        assert r2.headers["etag"] == etag and r2.headers["cache-control"] == S.CACHE_REVALIDATE
    assert c.get("/models/m.onnx", headers={"If-None-Match": '"other"'}).status_code == 200
    r3 = c.get("/models/m.onnx", headers={"If-Modified-Since": r.headers["last-modified"]})
    assert r3.status_code == 304
    h = c.head("/models/m.onnx")
    assert h.status_code == 200 and h.content == b"" and h.headers["content-length"] == str(len(_ONNX))


def test_glb_is_sent_precompressed_when_gzip_is_accepted(tmp_path):
    c, dist, _ = _client(tmp_path)
    r = c.get("/models/face.glb", headers={"Accept-Encoding": "gzip, deflate"})
    assert r.headers["content-encoding"] == "gzip" and "accept-encoding" in r.headers["vary"].lower()
    assert r.content == _GLB  # httpx가 풀어 준다
    assert int(r.headers["content-length"]) == (dist / "models" / "face.glb.gz").stat().st_size < len(_GLB)
    assert r.headers["content-type"] != "application/gzip"
    plain = c.get("/models/face.glb", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers and plain.content == _GLB
    assert plain.headers["etag"] != r.headers["etag"], "표현이 다르면 ETag도 달라야 한다"
    assert c.get("/models/face.glb", headers={"Accept-Encoding": "gzip;q=0"}).headers.get("content-encoding") is None
    # 원본이 .gz보다 새로우면(빌드 뒤 원본만 바뀜) 낡은 .gz를 보내지 않는다
    gz = dist / "models" / "face.glb.gz"
    os.utime(gz, (gz.stat().st_mtime - 100, gz.stat().st_mtime - 100))
    assert c.get("/models/face.glb", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") is None


def test_spa_routes_missing_files_and_api(tmp_path):
    c, _, _ = _client(tmp_path)
    r = c.get("/learn/path")
    assert r.status_code == 200 and r.text == "<html>app</html>"
    assert r.headers["cache-control"] == S.CACHE_REVALIDATE
    assert c.get("/sw.js").headers["cache-control"] == S.CACHE_REVALIDATE
    assert c.get("/models/missing.onnx").status_code == 404, "없는 파일에 index.html을 200으로 주면 서비스워커가 캐시한다"
    assert c.get("/api/nope").status_code == 404
    assert c.get("/api/ping").json() == {"ok": True}
    assert c.get("/%2e%2e/secret.txt").status_code == 404


def test_accepts_gzip():
    assert S.accepts_gzip("gzip, deflate, br")
    assert S.accepts_gzip("br;q=1.0, GZIP;q=0.5")
    assert not S.accepts_gzip("gzip;q=0")
    assert not S.accepts_gzip("br, identity")
    assert not S.accepts_gzip("")
