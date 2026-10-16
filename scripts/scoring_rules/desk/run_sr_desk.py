"""데스크탑(Windows, RTX 3060) 확인 단계: run_sr.sh confirm을 같은 순서로 옮긴 것(docs/scoring-rules-2026-10.md 9.2절, 10절).

    D:\\liplab\\venv\\Scripts\\python.exe run_sr_desk.py      (환경 변수로 경로를 바꿀 수 있다: SR_W, LIPLAB_LAB, SR_PY, SR_SEG_PY)

순서: 점검 → selftest → 범주 27 두 번째 묶음 FLAC·라벨 넣기(build_stage.stage_c27b2와 같음) → b2prep → 자르기(GPU, seg_desk.py)
→ b2jobs → 경로 보정(relpath_jobs.py) → 특성(b2, 538·범주 28 절반 1) → 집계(analyze.py confirm).
파드판과 같은 것: backend(탐색과 같은 4c10d9b5판), int8 가중치(sha256 확인), CPU 2스레드 작업자, faster-whisper 0.10.1 large-v3 fp16.
다른 것: 작업자 수(코어·메모리 기준 같은 식), Windows 경로, PYTHONUTF8=1(기본 인코딩이 cp949라서), DLL 경로.
표식(로그): SR_SETUP_OK SEG_OK B2JOBS_OK FEAT_DONE… SR_OK / SR_FAIL
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.environ.get("SR_W", "D:/liplab/sr/confirm").replace("\\", "/")
LAB = os.environ.get("LIPLAB_LAB", "D:/liplab/lab").replace("\\", "/")
PY = os.environ.get("SR_PY", "D:/liplab/venv/Scripts/python.exe")
SEG = os.environ.get("SR_SEG_PY", "D:/liplab/vseg/Scripts/python.exe")
B2F = f"{LAB}/data/hi608/c27/b2/flac16"
LABELS = f"{LAB}/data/hi608/labels"
SHA = {"aligner": "18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66",
       "scorer": "e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4"}
CACHE = {"PIP_CACHE_DIR": "D:/liplab/cache/pip", "HF_HOME": "D:/liplab/cache/hf", "XDG_CACHE_HOME": "D:/liplab/cache", "TORCH_HOME": "D:/liplab/cache/torch"}
ENV = dict(os.environ, **CACHE, SR_W=W, SR_BACKEND=f"{W}/backend", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
           PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TOKENIZERS_PARALLELISM="false", LIPLAB_LAB=LAB)


def say(*a):
    print(time.strftime("%F %T"), *a, flush=True)


def fail(msg):
    print("SR_FAIL", msg, flush=True)
    sys.exit(1)


def run(args, cwd, env=None, ok=None):
    say("RUN", " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args)), "@", cwd)
    p = subprocess.run(args, cwd=cwd, env=env or ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       encoding="utf-8", errors="replace")
    sys.stdout.write(p.stdout)
    sys.stdout.flush()
    if p.returncode != 0 or (ok and ok not in p.stdout):
        fail(f"{os.path.basename(args[1]) if len(args) > 1 else args[0]} rc={p.returncode}")
    return p.stdout


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def workers():
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tot", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                    ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("avv", ctypes.c_ulonglong),
                    ("x", ctypes.c_ulonglong)]
    m = MS()
    m.l = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    memg = int(m.tot / 2 ** 30)
    wk = max(1, (os.cpu_count() or 2) // 2)          # run_sr.sh와 같은 식: 코어/2, 메모리 GB/3 이하
    if memg // 3 >= 1:
        wk = min(wk, memg // 3)
    return wk, memg


def stage_b2():
    os.makedirs(f"{W}/c27b2/s608", exist_ok=True)
    os.makedirs(f"{W}/c27b2/labels", exist_ok=True)
    n = 0
    for f in sorted(glob.glob(f"{B2F}/*.flac")):
        b = os.path.basename(f)[:-5]
        src = glob.glob(f"{LABELS}/*/{b}.json")
        assert src, b
        for s, d in ((f, f"{W}/c27b2/s608/{b}.flac"), (src[0], f"{W}/c27b2/labels/{b}.json")):
            if not os.path.exists(d):
                shutil.copyfile(s, d)
        n += 1
    return n


def main():
    wk, memg = workers()
    wk = int(os.environ.get("SR_WORKERS", wk))       # 10/17: S4 교사 계산과 함께 돌 때 RAM 16GB에서 작업자 하나가 죽어 3으로 줄임
    os.makedirs(f"{W}/out", exist_ok=True)
    say(f"=== [sr confirm desk] start cpus={os.cpu_count()} mem={memg}G workers={wk}")
    for f in ("backend/dgop_acoustic.py", "backend/data/dgop_calibration_ours.json", "tools/feat_pod.py", "tools/targets.py", "jobs.json"):
        if not os.path.exists(f"{W}/{f}"):
            fail(f"없음: {f}")
    for m, h in SHA.items():
        if os.path.exists(f"{W}/backend/models/dgop_ours/{m}/model.safetensors"):
            fail(f"fp32 가중치가 있음({m})")
        if sha256(f"{W}/backend/models/dgop_ours/{m}/model.int8.safetensors") != h:
            fail(f"{m} sha256")
    run([PY, "-c", "import torch, transformers, faster_whisper, numpy, soundfile; print('ENVAPP torch', torch.__version__, 'tf', "
         "transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())"], W)
    run([PY, "-c", "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC and hasattr(DA, 'retime_tail'); print('ACOUSTIC_OK')"],
        f"{W}/backend", ok="ACOUSTIC_OK")
    run([PY, "feat_pod.py", "selftest"], f"{W}/tools", ok="SR_SELFTEST_OK")
    print("SR_SETUP_OK", flush=True)
    n = stage_b2()
    say("B2_STAGE sessions", n)
    if n == 0:
        fail("범주 27 두 번째 묶음 FLAC 없음")
    run([PY, "feat_pod.py", "b2prep"], f"{W}/tools", ok="B2PREP_OK")
    if not os.path.exists(f"{W}/c27b2/out/cuts608.json") or os.path.getsize(f"{W}/c27b2/out/cuts608.json") == 0:
        run([SEG, "-c", "import ctranslate2, faster_whisper; print('ENVSEG ct2', ctranslate2.__version__, 'fw', faster_whisper.__version__)"], W)
        run([SEG, f"{HERE}/seg_desk.py", f"{W}/c27b2", f"{W}/scripts"], W, ok="SEG DONE")
    c = json.load(open(f"{W}/c27b2/out/cuts608.json", encoding="utf-8"))
    print("SEG_OK", len(c), sum(1 for x in c if x["cut"]), len({x["file"] for x in c if x["cut"]}), flush=True)
    run([PY, "feat_pod.py", "b2jobs"], f"{W}/tools", ok="B2JOBS_OK")
    run([PY, f"{HERE}/relpath_jobs.py", f"{W}/jobs_b2.json"], W, ok="RELPATH_OK")
    fenv = dict(ENV, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    run([PY, "feat_pod.py", "feat", f"{W}/jobs_b2.json", f"{W}/out/feat_b2.jsonl", str(wk)], f"{W}/tools", env=fenv, ok="FEAT_DONE")
    run([PY, "feat_pod.py", "feat", f"{W}/jobs.json", f"{W}/out/feat_confirm.jsonl", str(wk)], f"{W}/tools", env=fenv, ok="FEAT_DONE")
    errs = {os.path.basename(p): sum(1 for l in open(p, encoding="utf-8") if '"error"' in l) for p in glob.glob(f"{W}/out/feat_*.jsonl")}
    print("ERRORS", errs, flush=True)
    an = os.environ.get("SR_ANALYZE", os.path.join(os.path.dirname(HERE), "analyze.py"))
    run([PY, an, "confirm", f"{W}/out/feat_confirm.jsonl", f"{W}/out/feat_b2.jsonl", f"{W}/out/confirm.json"], W)
    print("SR_OK", flush=True)


if __name__ == "__main__":
    main()
