"""서버 실시간 합성 측정 클라이언트(docs/listen-convo-tts-2026-10.md 5절). 파드에서 서버(uvicorn, 2코어)와 다른 코어로 돈다.

    python measure.py server1 --pid PID --base http://127.0.0.1:8080 --out OUT.json --fixture fixture_items.json --sound-dir DIR
    python measure.py server2 --pid PID ...      (LIPLAB_ML_CONCURRENCY=3, 보고만)

서버 프로세스의 /proc/PID/status(VmHWM·VmRSS)를 0.2초마다 적고, 단계마다 지연과 상태 코드를 적는다. 표식 MEASURE_OK."""
import argparse
import json
import os
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

ap = argparse.ArgumentParser()
ap.add_argument("which", choices=["server1", "server2", "explore_a", "explore_b"])
ap.add_argument("--pid", type=int, required=True)
ap.add_argument("--base", default="http://127.0.0.1:8080")
ap.add_argument("--out", required=True)
ap.add_argument("--fixture", required=True)
ap.add_argument("--sound-dir", required=True)       # backend/data/sound(채점에 올릴 미리 합성한 클립)
ap.add_argument("--gen-timeout", type=float, default=2400)
ap.add_argument("--log", required=True)              # 서버 로그(예열 끝 표시를 기다린다)
ap.add_argument("--backend", required=True)
a = ap.parse_args()

FIX = json.load(open(a.fixture, encoding="utf-8"))["items"]
OUT = {"which": a.which, "phases": {}, "timeline": [], "events": []}
_phase = {"name": "start"}
_stop = threading.Event()


def proc_mem():
    d = {}
    try:
        with open(f"/proc/{a.pid}/status") as f:
            for line in f:
                k = line.split(":")[0]
                if k in ("VmRSS", "VmHWM", "RssAnon", "RssFile"):
                    d[k] = round(int(line.split()[1]) / 1024 / 1024, 4)     # GiB
    except OSError:
        pass
    return d


def sampler():
    while not _stop.is_set():
        m = proc_mem()
        if m:
            OUT["timeline"].append([round(time.time(), 2), _phase["name"], m.get("VmRSS"), m.get("VmHWM")])
        time.sleep(0.2)


def phase(name):
    _phase["name"] = name
    OUT["phases"].setdefault(name, {})["t_start"] = time.time()
    OUT["phases"][name]["mem_start"] = proc_mem()


def phase_end(name, **kw):
    OUT["phases"][name].update(kw)
    OUT["phases"][name]["t_end"] = time.time()
    OUT["phases"][name]["mem_end"] = proc_mem()
    json.dump(OUT, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("PHASE", name, json.dumps({k: v for k, v in kw.items() if not isinstance(v, list) or len(v) < 30}, ensure_ascii=False)[:600],
          OUT["phases"][name]["mem_end"], flush=True)


S = requests.Session()


def get(path, h=None, **params):
    t = time.time()
    r = S.get(a.base + path, params=params, headers=h, timeout=600)
    return r, round(time.time() - t, 3)


def sound(text, voice, h):
    t = time.time()
    r = requests.get(a.base + "/api/sound", params={"text": text, "voice": voice}, headers=h, timeout=600)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return {"text": text, "voice": voice, "status": r.status_code, "s": round(time.time() - t, 3), "source": body.get("source"),
            "ms": body.get("duration_ms"), "syl": bool(body.get("syllables")), "t0": round(t, 2), "t1": round(time.time(), 2)}


# 채점 음성: 미리 합성한 m1 클립 가운데 8음절 이상 문장 셋(목록 순서)
man = json.load(open(os.path.join(a.sound_dir, "manifest.json"), encoding="utf-8"))
m1 = man["clips"]["m1"]
CASES = []
for key, c in m1.items():
    t = c.get("text") or key
    if len([ch for ch in t if "가" <= ch <= "힣"]) >= 8 and " " in t:
        CASES.append((t, os.path.join(a.sound_dir, "clips", c["id"] + ".ogg")))
    if len(CASES) == 3:
        break


def assess(i, h):
    t, p = CASES[i % len(CASES)]
    st = time.time()
    with open(p, "rb") as f:
        r = requests.post(a.base + "/api/speak/assess", data={"target": t}, files={"audio": ("a.ogg", f.read(), "audio/ogg")},
                          headers=h, timeout=600)
    b = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return {"kind": "assess", "status": r.status_code, "s": round(time.time() - st, 3), "method": b.get("assessment_method"),
            "score": b.get("score"), "t0": round(st, 2), "t1": round(time.time(), 2)}


def avatar(i, h):
    t, p = CASES[i % len(CASES)]
    st = time.time()
    with open(p, "rb") as f:
        r = requests.post(a.base + "/api/avatar/audio2face", files={"audio": ("a.ogg", f.read(), "audio/ogg")}, headers=h, timeout=600)
    return {"kind": "avatar", "status": r.status_code, "s": round(time.time() - st, 3), "t0": round(st, 2), "t1": round(time.time(), 2)}


threading.Thread(target=sampler, daemon=True).start()

# ── P0 예열 ──
phase("P0_warmup")
t0 = time.time()
while True:
    try:
        r = S.get(a.base + "/health", timeout=5)
        if r.status_code == 200:
            break
    except requests.RequestException:
        pass
    time.sleep(0.5)
t_http = round(time.time() - t0, 1)
loaded = []
warm_ok = False
while time.time() - t0 < 900:
    try:
        warm_ok = "서버 추론 모델 예열 끝" in open(a.log, encoding="utf-8", errors="replace").read()
    except OSError:
        pass
    if warm_ok:
        break
    time.sleep(0.5)
try:
    st = S.get(a.base + "/api/backbone/status", timeout=10).json()
    loaded = [(x.get("model_id"), x.get("kind"), x.get("load_seconds"), x.get("quant"), x.get("quant_from")) for x in st.get("loaded") or []]
except Exception:
    pass
r = S.post(a.base + "/api/auth/register", json={"email": f"m{int(time.time())}@example.com", "username": "측정", "password": "pw-123456",
                                                "agree_terms": True, "age_confirmed": True})
H = {"Authorization": "Bearer " + r.json()["access_token"]}
phase_end("P0_warmup", http_s=t_http, total_s=round(time.time() - t0, 1), loaded=loaded, warm_ok=warm_ok)

# ── P1 기준(채점·아바타) ──
phase("P1_base")
p1 = [assess(i, H) for i in range(3)] + [avatar(i, H) for i in range(3)]
phase_end("P1_base", rows=p1, cases=[c[0] for c in CASES])

if a.which.startswith("explore"):
    # 사후 탐색(보고만, docs/listen-convo-tts-2026-10.md 8절): 생성 흐름(P5와 같음) 뒤에 클립을 더 만들어 메모리가 멈추는지 본다
    import sys
    sys.path.insert(0, a.backend)
    import listen_curriculum as LC
    S.post(a.base + "/api/listen/ling", json={"results": {k: True for k in LC.LING_KEYS}, "false_alarms": 0}, headers=H)
    phase("X1_gen")
    t5 = time.time()
    for sc in sorted({it["scene"] for it in FIX}):
        get("/api/listen/practice/scenario", H, place=sc)
    while time.time() - t5 < a.gen_timeout:
        st = S.get(a.base + "/api/listen/convo-gen/status", headers=H, timeout=30).json()
        if sum(v.get("ready", 0) + v.get("rejected", 0) for v in (st.get("scenes") or {}).values()) >= len(FIX) and not st.get("running"):
            break
        time.sleep(3)
    phase_end("X1_gen", gen_s=round(time.time() - t5, 1))
    phase("X2_more")
    more = [sound(it["question"], v, H) for v in ("m1", "f1", "m2", "f2") for it in FIX] + [sound(it["line"], "m3", H) for it in FIX]
    phase_end("X2_more", rows=more)
elif a.which == "server1":
    # ── P2 첫 합성 ──
    phase("P2_first")
    first = sound(FIX[0]["line"], "m1", H)
    phase_end("P2_first", rows=[first])
    # ── P3 문장당 ──
    phase("P3_seq")
    seq = [sound(FIX[i]["line"], "m1", H) for i in range(1, 20)]
    phase_end("P3_seq", rows=seq)
    # ── P4 동시 ──
    phase("P4_conc")
    rows = {}
    with ThreadPoolExecutor(4) as ex:
        rows["two"] = list(ex.map(lambda i: sound(FIX[i]["paraphrase"], "f1", H), [0, 1]))
        rows["three"] = list(ex.map(lambda i: sound(FIX[i]["paraphrase"], "f1", H), [2, 3, 4]))
        fs = [ex.submit(sound, FIX[5]["paraphrase"], "f1", H), ex.submit(sound, FIX[6]["paraphrase"], "f1", H), ex.submit(assess, 0, H)]
        rows["mixed"] = [f.result() for f in fs]
    phase_end("P4_conc", **rows)
    # ── P5 생성 흐름 ──
    phase("P5_gen")
    import sys
    sys.path.insert(0, a.backend)
    import listen_curriculum as LC
    rl = S.post(a.base + "/api/listen/ling", json={"results": {k: True for k in LC.LING_KEYS}, "false_alarms": 0}, headers=H)
    kicks = []
    t5 = time.time()
    scenes = sorted({it["scene"] for it in FIX}, key=lambda s: [it["scene"] for it in FIX].index(s))
    for sc in scenes:
        r, s = get("/api/listen/practice/scenario", H, place=sc)
        kicks.append({"scene": sc, "status": r.status_code, "s": s, "n": len((r.json() or {}).get("items") or []) if r.ok else None})
    time.sleep(20)
    during = []
    for i in range(3):
        during.append(assess(i, H))
        time.sleep(2)
    done = None
    while time.time() - t5 < a.gen_timeout:
        st = S.get(a.base + "/api/listen/convo-gen/status", headers=H, timeout=30).json()
        tot = sum(v.get("ready", 0) + v.get("rejected", 0) for v in (st.get("scenes") or {}).values())
        if tot >= len(FIX) and not st.get("running"):
            done = st
            break
        time.sleep(3)
    gen_s = round(time.time() - t5, 1)
    st = done or S.get(a.base + "/api/listen/convo-gen/status", headers=H, timeout=30).json()
    phase_end("P5_gen", ling=rl.status_code, kicks=kicks, during=during, gen_s=gen_s, status=st, finished=done is not None)
    # ── P6 끝 ──
    phase("P6_end")
    after = {}
    for sc in scenes:
        r, s = get("/api/listen/practice/scenario", H, place=sc)
        its = (r.json() or {}).get("items") or [] if r.ok else []
        after[sc] = {"n": len(its), "gen": sum(1 for i in its if i.get("generated")), "s": s,
                     "avoid": [i.get("avoid_voices") for i in its if i.get("generated")]}
    r5, s5 = get("/api/listen/stage/5", H)
    g5 = [i for i in (r5.json() or {}).get("items") or [] if i.get("generated")] if r5.ok else []
    phase_end("P6_end", after=after, stage5={"status": r5.status_code, "n_gen": len(g5)})
else:
    # ── 서버 2: 동시 3(LIPLAB_ML_CONCURRENCY=3) ──
    phase("Q1_conc3")
    with ThreadPoolExecutor(4) as ex:
        three = list(ex.map(lambda i: sound(FIX[i]["line"], "f1", H), [20, 21, 22]))
    phase_end("Q1_conc3", rows=three)
    phase("Q2_mixed3")
    rows = []
    with ThreadPoolExecutor(4) as ex:
        for k, i in enumerate([23, 7]):
            fs = [ex.submit(sound, FIX[i]["paraphrase"], "m2", H), ex.submit(assess, k, H), ex.submit(avatar, k, H)]
            rows += [f.result() for f in fs]
    phase_end("Q2_mixed3", rows=rows)

_stop.set()
time.sleep(0.3)
OUT["final_mem"] = proc_mem()
OUT["peak_vmhwm_gib"] = max([r[3] for r in OUT["timeline"] if r[3] is not None] or [None] if OUT["timeline"] else [None])
json.dump(OUT, open(a.out, "w"), ensure_ascii=False, indent=1)
print("MEASURE_OK", a.which, OUT["final_mem"], flush=True)
