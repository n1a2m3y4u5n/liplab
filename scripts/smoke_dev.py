"""배포 직후 스모크(11/03 검토 O3, O26). liplab-dev에 대해서만 돈다.

- /health, /health/ready, 첫 화면 경로, CSP 헤더(수어 영상 출처 포함)
- 고정 스모크 계정(smoke-dev@example.com)으로 로그인(없으면 한 번 가입). 배포마다 계정을 새로 만들지 않는다.
- 말하기 채점 경로: 합성 모음 소리를 /api/speak/assess에 보내 점수가 오는지 확인한다(스트리밍이 켜져 있으면 조각 경로까지).
- 소리를 재생하지 않고 실제 사용자 자료를 쓰지 않는다. 비밀번호는 LIPLAB_SMOKE_PASSWORD 또는 로컬 파일에서 읽고 출력하지 않는다.

  python scripts/smoke_dev.py --base https://liplab-dev.fly.dev --out 결과폴더
"""
import argparse
import io
import json
import os
import secrets
import sys
import time
import wave
from pathlib import Path

import numpy as np
import requests

SMOKE_EMAIL = "smoke-dev@example.com"
ALLOWED_BASES = {"https://liplab-dev.fly.dev"}   # 전시앱(liplab.fly.dev)에는 돌리지 않는다
ROOT = Path(__file__).resolve().parents[1]


def smoke_password() -> str:
    env = os.environ.get("LIPLAB_SMOKE_PASSWORD")
    if env:
        return env
    path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "liplab" / "smoke-dev.pass"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(24)
    path.write_text(value, encoding="utf-8")
    return value


def synthetic_pcm(seconds: float = 6.5) -> bytes:
    """저장소의 합성 모음 'a'를 16 kHz로 맞춰 이어 붙인다(없으면 단순한 모음 비슷한 소리)."""
    wav = ROOT / "frontend" / "public" / "vtl" / "vowels" / "a.wav"
    n = int(seconds * 16000)
    if wav.is_file():
        with wave.open(str(wav), "rb") as w:
            rate, ch = w.getframerate(), w.getnchannels()
            y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, ch).mean(axis=1)
        y = np.interp(np.arange(round(len(y) * 16000 / rate)) * rate / 16000, np.arange(len(y)), y)
        y = np.tile(y, int(np.ceil(n / len(y))))[:n]
    else:
        t = np.arange(n) / 16000
        y = 6000 * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 660 * t))
    return y.astype("<i2").tobytes()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://liplab-dev.fly.dev")
    ap.add_argument("--out", default=".")
    ap.add_argument("--allow-other-base", action="store_true", help="로컬 서버(127.0.0.1) 시험용")
    a = ap.parse_args(argv)
    base = a.base.rstrip("/")
    local = base.startswith("http://127.0.0.1") or base.startswith("http://localhost")
    if base not in ALLOWED_BASES and not (local and a.allow_other_base):
        print(f"SMOKE_ABORT: {base}에는 돌리지 않는다(허용: {sorted(ALLOWED_BASES)})")
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {"base": base}
    s = requests.Session()
    s.headers["Origin"] = base

    def request(method, path, **kw):
        t = time.monotonic()
        r = s.request(method, base + path, timeout=180, **kw)
        results[path] = {"status": r.status_code, "seconds": round(time.monotonic() - t, 3)}
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r

    try:
        assert request("GET", "/health").json()["status"] == "healthy"
        ready = request("GET", "/health/ready").json()
        results["ready"] = {"status": ready["status"], "schema_warnings": ready.get("schema_warnings")}
        assert ready["status"] in ("ready", "degraded")
        r = request("GET", "/learn/path")
        assert "<html" in r.text.lower()
        csp = r.headers.get("Content-Security-Policy", "")
        assert "https://sldict.korean.go.kr" in csp, "CSP media-src에 수어 영상 출처가 없다"
        # 고정 스모크 계정: 로그인, 없으면 한 번 가입
        pw = smoke_password()
        lr = s.post(base + "/api/auth/login", json={"email": SMOKE_EMAIL, "password": pw}, timeout=90)
        if lr.status_code != 200:
            lr = s.post(base + "/api/auth/register", json={"email": SMOKE_EMAIL, "username": "배포검증고정", "password": pw,
                                                          "agree_terms": True, "age_confirmed": True}, timeout=90)
            results["smoke_account"] = "created"
        else:
            results["smoke_account"] = "reused"
        assert lr.status_code in (200, 201), f"smoke account: {lr.status_code}"
        s.headers["Authorization"] = "Bearer " + lr.json()["access_token"]
        for path in ["/api/curriculum/stages", "/api/speak/curriculum", "/api/speak/stage/2", "/api/listen/curriculum"]:
            assert request("GET", path).json()
        vf = request("GET", "/api/viseme", params={"text": "안녕"}).json()
        assert isinstance(vf, list) and vf
        # 말하기 채점 경로
        pcm = synthetic_pcm()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
        form = {"target": "아", "stage": "2", "review": "1", "duration": "6.5", "loudness": "60"}
        r = request("POST", "/api/speak/assess", data=form, files={"audio": ("smoke-a.wav", buf.getvalue(), "audio/wav")})
        assessment = r.json()
        assert isinstance(assessment.get("score"), (int, float)), "말하기 채점 점수가 없다"
        results["assessment"] = {"score_type": type(assessment["score"]).__name__, "method": assessment.get("assessment_method")}
        results["server_timing"] = r.headers.get("Server-Timing")
        results["outcome"] = "passed"
    except Exception as e:
        results["outcome"] = "failed"
        results["error"] = str(e)[:300]
    finally:
        (out / "smoke-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: results.get(k) for k in ("outcome", "error", "smoke_account", "ready")}, ensure_ascii=False))
    return 0 if results.get("outcome") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
