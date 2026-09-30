"""상용 발음평가(SpeechSuper)와 자체 D-GOP의 대조군 비교(계획서 4.2-15, 표 8-⑤).

같은 녹음·같은 목표 문장을 SpeechSuper 한국어 스크립트 기반 평가(sent.eval.kr, 단어는 word.eval.kr)에 보내 점수를 받아 둔다.
키는 환경 변수에서만 읽는다(SPEECHSUPER_APP_KEY, SPEECHSUPER_SECRET_KEY). 코드·파일·로그에 남기지 않는다.
보내는 음성은 해외 서버로 나간다. AI Hub 538·608은 국외 반출 확인 전에는 보내지 않는다(팀 녹음·공개 코퍼스만).

    python scripts/speechsuper_compare.py <목록.tsv> <결과.jsonl> [--core sent.eval.kr] [--limit N]

목록.tsv: 음성 경로<TAB>목표 문장(또는 단어). 결과는 저장소 밖 경로에 둔다(한 줄에 {path, text, core, status, result}).
이미 결과에 있는 경로는 건너뛴다(이어 돌리기). 호출 사이 0.3초 쉰다.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = "https://api.speechsuper.com/"


def _sig(*parts: str) -> str:
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def _multipart(fields: dict, audio: bytes, audio_name: str):
    boundary = "----liplab" + uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode("utf-8")
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{audio_name}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8") + audio + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def assess(path: str, text: str, core: str, app_key: str, secret: str, user: str = "liplab") -> dict:
    ts = str(int(time.time()))
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "wav"
    params = {
        "connect": {"cmd": "connect", "param": {
            "sdk": {"version": 16777472, "source": 9, "protocol": 2},
            "app": {"applicationId": app_key, "sig": _sig(app_key, ts, secret), "timestamp": ts}}},
        "start": {"cmd": "start", "param": {
            "app": {"userId": user, "applicationId": app_key, "timestamp": ts, "sig": _sig(app_key, ts, user, secret)},
            "audio": {"audioType": ext, "channel": 1, "sampleBytes": 2, "sampleRate": 16000},
            "request": {"coreType": core, "refText": text, "tokenId": uuid.uuid4().hex}}},
    }
    body, ctype = _multipart({"text": json.dumps(params, ensure_ascii=False)}, open(path, "rb").read(), os.path.basename(path))
    req = urllib.request.Request(BASE + core, data=body, headers={"Content-Type": ctype, "Request-Index": "0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("out")
    ap.add_argument("--core", default="sent.eval.kr")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    app_key, secret = os.environ.get("SPEECHSUPER_APP_KEY"), os.environ.get("SPEECHSUPER_SECRET_KEY")
    if not app_key or not secret:
        sys.exit("SPEECHSUPER_APP_KEY·SPEECHSUPER_SECRET_KEY 환경 변수가 없습니다.")
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["path"] for l in open(a.out, encoding="utf-8") if l.strip()}
    rows = [l.rstrip("\n").split("\t") for l in open(a.tsv, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if len(r) >= 2 and r[0] not in done]
    if a.limit:
        rows = rows[:a.limit]
    with open(a.out, "a", encoding="utf-8") as f:
        for i, (path, text, *_) in enumerate(rows):
            try:
                res = assess(path, text, a.core, app_key, secret)
                rec = {"path": path, "text": text, "core": a.core, "status": "ok", "result": res}
            except Exception as e:   # 한 건 실패로 전체를 멈추지 않는다. 키가 섞이지 않게 예외 종류만 남긴다
                rec = {"path": path, "text": text, "core": a.core, "status": "error", "error": type(e).__name__}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(i + 1, len(rows), rec["status"], flush=True)
            time.sleep(0.3)


if __name__ == "__main__":
    main()
