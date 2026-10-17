"""V1 데스크탑(Windows, RTX 3060 12GB) 실행기(2026-10-17). 사전등록 docs/lipread-v1-prereg-2026-10.md(ea1c7af9)의 파드 경로
(v1_session.sh 묶음 → remote.sh extract·align → v1_remote.sh)를 같은 순서·같은 도구로 옮긴 것이다. 판정 코드와 기준은 그대로다.

    D:\\liplab\\vlip\\Scripts\\python.exe v1_desk.py stage|extract|align|v1|all      (실제 판정, 받기가 끝난 뒤)
    D:\\liplab\\vlip\\Scripts\\python.exe v1_desk.py smoke                           (받기 없이: 기존 68명 bs·정렬만으로 전 과정을 작게)

경로: LAB=D:/liplab/lab(받은 클립 data/v1_538r, 기존 화자 data/pod_runs, 도구 tools), DAX=D:/liplab/v1/dax(smoke는 D:/liplab/v1/smoke).
파드와 다른 점(문서 lipread-v1-2026-10.md 6절): torch 2.8.0 cu128·py3.12(파드 2.1.0 cu118·py3.10), 나머지 고정 판은 같음
(numpy 1.26.4, mediapipe 0.10.14, transformers 4.40.0 …). 동시 학습 수 V1_PAR(기본 6, 파드와 같음), 추출 작업자 V1_EXTRACT_W(기본 6).
표식: V1D_STAGE_OK EXTRACT_OK ALIGN_OK V1_BUILD_OK V1_SPLIT_OK V1_TRAIN_OK V1_SELECT_OK V1_P4_OK V1_GATE … V1_ALL_OK / V1D_FAIL
"""
import glob
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time

LAB = os.environ.get("LIPLAB_LAB", "D:/liplab/lab").replace("\\", "/")
PR = f"{LAB}/data/pod_runs"
R = f"{LAB}/data/v1_538r"
PY = sys.executable
CACHE = {"PIP_CACHE_DIR": "D:/liplab/cache/pip", "HF_HOME": "D:/liplab/cache/hf", "XDG_CACHE_HOME": "D:/liplab/cache",
         "TORCH_HOME": "D:/liplab/cache/torch"}
ENV = dict(os.environ, **CACHE, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
TOOLS = ["v1_train.py", "v1_judge.py", "d_bench.py", "train_lipread.py", "folds.py", "extract_blendshapes.py", "build_cd.py",
         "lip_roi_extract.py", "export_lipread_onnx.py", "face_landmarker.task"]
OLD_SPANS = [f"{PR}/20260924_k74l2l74024fsz/d/spans.jsonl", f"{PR}/20260925_4aol7xkyf762yh/dax/d/spans.jsonl",
             f"{PR}/20260925_nwcqu40di2ct11/dax/d/spans.jsonl"]
OLD_BS = [f"{PR}/20260924_k74l2l74024fsz/bs", f"{PR}/20260925_nwcqu40di2ct11/dax/bs"]
OLD_BS_TGZ = f"{PR}/20260925_4aol7xkyf762yh/dax/bs_new12.tgz"


def say(*a):
    print(time.strftime("%F %T"), *a, flush=True)


def fail(msg):
    print("V1D_FAIL", msg, flush=True)
    sys.exit(1)


def run(args, cwd, log=None, env=None, ok=None):
    say("RUN", " ".join(str(x) for x in args[1:6]), "…" if len(args) > 6 else "", f"> {os.path.basename(log)}" if log else "")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            p = subprocess.run(args, cwd=cwd, env=env or ENV, stdout=f, stderr=subprocess.STDOUT)
        tail = open(log, encoding="utf-8", errors="replace").read().splitlines()[-3:]
        for t in tail:
            print("  |", t, flush=True)
        text = "\n".join(tail)
    else:
        p = subprocess.run(args, cwd=cwd, env=env or ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           encoding="utf-8", errors="replace")
        sys.stdout.write(p.stdout)
        text = p.stdout
    if p.returncode != 0 or (ok and ok not in (open(log, encoding="utf-8", errors="replace").read() if log else text)):
        fail(f"{os.path.basename(str(args[1]))} rc={p.returncode}")


def popen(args, cwd, log, env=None):
    f = open(log, "a", encoding="utf-8")
    return subprocess.Popen(args, cwd=cwd, env=env or ENV, stdout=f, stderr=subprocess.STDOUT), f


def wait_all(procs, tag):
    t0 = time.time()
    while any(p.poll() is None for p, _, _ in procs):
        time.sleep(30)
        if time.time() - t0 > 300:
            t0 = time.time()
            bits = []
            for p, f, name in procs:
                try:
                    last = open(f.name, encoding="utf-8", errors="replace").read().splitlines()[-1][:60]
                except (IndexError, OSError):
                    last = ""
                bits.append(f"{name}: {last}")
            say(f"[{tag}]", " | ".join(bits))
    rc = 0
    for p, f, _ in procs:
        f.close()
        rc |= p.returncode != 0
    return rc


# ───────────────────────────── 묶음(v1_session.sh 묶음과 같다) ─────────────────────────────
def stage(dax, smoke=False):
    os.makedirs(f"{dax}/logs", exist_ok=True)
    os.makedirs(f"{dax}/v1", exist_ok=True)
    os.makedirs(f"{dax}/old", exist_ok=True)
    for t in TOOLS:
        shutil.copyfile(f"{LAB}/tools/{t}", f"{dax}/{t}")
    shutil.copyfile(f"{LAB}/models/kr_d_lipread_1120.pt", f"{dax}/kr_d_lipread_1120.pt")
    with open(f"{dax}/old/spans.jsonl", "w", encoding="utf-8") as fo:
        for p in OLD_SPANS:
            fo.write(open(p, encoding="utf-8").read())
    ob = f"{dax}/old/bs"
    if not os.path.isdir(ob) or len(os.listdir(ob)) < 1700:
        os.makedirs(ob, exist_ok=True)
        for d in OLD_BS:
            for f in glob.glob(f"{d}/*.json"):
                dst = f"{ob}/{os.path.basename(f)}"
                if not os.path.exists(dst):
                    shutil.copyfile(f, dst)
        with tarfile.open(OLD_BS_TGZ) as t:
            t.extractall(f"{dax}/old", filter="data")
    say("old bs", len(os.listdir(ob)), "spans", sum(1 for _ in open(f"{dax}/old/spans.jsonl", encoding="utf-8")))
    if smoke:
        print("V1D_STAGE_OK smoke", flush=True)
        return
    if "V1R_DL end" not in open(f"{R}/v1r_dl.out", encoding="utf-8", errors="replace").read():
        fail("받기가 아직 안 끝남(data/v1_538r/v1r_dl.out)")
    ev = f"{R}/eval40.txt"
    if not os.path.exists(ev):
        fail("eval40.txt 없음(v1_pick_eval.py)")
    repo_ev = os.environ.get("V1_EVAL_COMMITTED", "D:/liplab/repo/scripts/lipread_v1/eval40.txt")
    if not os.path.exists(repo_ev) or open(repo_ev, "rb").read().replace(b"\r\n", b"\n") != open(ev, "rb").read().replace(b"\r\n", b"\n"):
        fail("평가 화자 목록이 커밋된 판(scripts/lipread_v1/eval40.txt)과 다름 — 먼저 커밋·pull")
    shutil.copyfile(ev, f"{dax}/v1/eval40.txt")
    os.makedirs(f"{dax}/more/clips", exist_ok=True)
    shutil.copyfile(f"{R}/manifest.tsv", f"{dax}/more/manifest.tsv")
    n = 0
    for line in open(f"{R}/manifest.tsv", encoding="utf-8"):
        t = line.rstrip("\n").split("\t")
        if len(t) < 3:
            continue
        b = t[0][:-4] if t[0].endswith(".mp4") else t[0]
        for ext in (".mp4", ".wav"):
            dst = f"{dax}/more/clips/{b}{ext}"
            if not os.path.exists(dst):
                shutil.copyfile(f"{R}/clips/{b}{ext}", dst)
        n += 1
    spk = {l.split("\t")[1] for l in open(f"{R}/manifest.tsv", encoding="utf-8") if "\t" in l}
    say(f"새 화자 클립 {n}개, 화자 {len(spk)}명")
    print("V1D_STAGE_OK", flush=True)


# ───────────────────────────── extract(remote.sh st_extract와 같다) ─────────────────────────────
def mkmanifest(dax):
    seen, rows, conflict = {}, [], []
    for p in ("manifest.tsv", "more/manifest.tsv"):
        if not os.path.exists(f"{dax}/{p}"):
            continue
        for line in open(f"{dax}/{p}", encoding="utf-8"):
            t = line.rstrip("\n").split("\t")
            if len(t) < 3 or not t[0].strip() or t[0].startswith("#"):
                continue
            base = t[0][:-4] if t[0].endswith(".mp4") else t[0]
            if base in seen:
                if seen[base] != (t[1], t[2]):
                    conflict.append(base)
                continue
            seen[base] = (t[1], t[2])
            rows.append("\t".join(t[:3]))
    open(f"{dax}/manifest_all.tsv", "w", encoding="utf-8").write("\n".join(rows) + "\n")
    say("MKMANIFEST rows", len(rows), "conflict", len(conflict))
    if conflict:
        fail("manifest 충돌")


def extract(dax):
    mkmanifest(dax)
    W = int(os.environ.get("V1_EXTRACT_W", "6"))
    os.makedirs(f"{dax}/bs", exist_ok=True)
    os.makedirs(f"{dax}/lists", exist_ok=True)
    allm = sorted(glob.glob(f"{dax}/more/clips/*.mp4"))
    if not allm:
        fail("mp4 없음")
    env = dict(ENV, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    for tag in ("p1", "p2"):
        def _need(m):
            p = f"{dax}/bs/{os.path.basename(m)[:-4]}.json"
            return not os.path.exists(p) or os.path.getsize(p) == 0
        todo = [m for m in allm if _need(m)]
        say(f"[extract {tag}] mp4={len(allm)} 남음={len(todo)} W={W}")
        if not todo:
            break
        procs = []
        for w in range(min(W, len(todo))):
            lst = f"{dax}/lists/extract.{tag}.{w}.tsv"
            with open(lst, "w", encoding="utf-8") as f:
                for m in todo[w::W]:
                    b = os.path.basename(m)[:-4]
                    f.write(f"{m}\t{dax}/bs/{b}.json\n")
            p, fh = popen([PY, "extract_blendshapes.py", "--list", lst, "--lips", "--no-audio"], dax,
                          f"{dax}/logs/extract.{tag}.{w}.log", env)
            procs.append((p, fh, f"w{w}"))
        wait_all(procs, f"extract {tag}")
    st = dict(clips=len(allm), ok=0, missing=0, short=0, names_bad=0, fps_bad=0, nolm=0, gapdrop=0, leaddrop=0, interp=0)
    bad = []
    for m in allm:
        b = os.path.basename(m)[:-4]
        p = f"{dax}/bs/{b}.json"
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            st["missing"] += 1
            bad.append([b, "missing"])
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st["missing"] += 1
            bad.append([b, "unreadable"])
            continue
        fr = d.get("frames") or []
        names = d.get("bs_names") or []
        good = True
        if len(fr) < 20:
            st["short"] += 1; good = False; bad.append([b, "short:%d" % len(fr)])  # noqa: E702
        if len(names) != 52:
            st["names_bad"] += 1; good = False; bad.append([b, "names:%d" % len(names)])  # noqa: E702
        if abs(float(d.get("fps") or 0.0) - 30.0) > 0.5:
            st["fps_bad"] += 1
        if fr and sum(1 for f in fr if f.get("lm")) < 0.5 * len(fr):
            st["nolm"] += 1
        ks = [int(round(f["t_ms"] * 30.0 / 1000.0)) for f in fr if "t_ms" in f]
        if ks:
            gaps = [k2 - k1 - 1 for k1, k2 in zip(ks, ks[1:])]
            if gaps and max(gaps) > 3:
                st["gapdrop"] += 1
            if ks[0] > 3:
                st["leaddrop"] += 1
            if any(0 < g <= 3 for g in gaps):
                st["interp"] += 1
        if good:
            st["ok"] += 1
    need = int(math.ceil(float(os.environ.get("EXTRACT_MIN_FRAC", "0.9")) * st["clips"]))
    json.dump({"stats": st, "need_ok": need, "bad": bad[:500]}, open(f"{dax}/logs/extract_stats.json", "w"), indent=1)
    print("EXTRACT_STATS " + " ".join("%s=%d" % kv for kv in st.items()) + " need_ok=%d" % need, flush=True)
    if st["ok"] < need:
        fail("추출 품질 관문 미달(logs/extract_stats.json)")
    print(f"EXTRACT_OK ok={st['ok']}/{st['clips']} gapdrop={st['gapdrop']}", flush=True)


# ───────────────────────────── align(remote.sh st_align과 같다) ─────────────────────────────
def align(dax):
    mkmanifest(dax)
    rows = n = 0
    with open(f"{dax}/manifest_c.tsv", "w", encoding="utf-8") as f:
        for line in open(f"{dax}/manifest_all.tsv", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            n += 1
            if os.path.exists(f"{dax}/bs/{os.path.splitext(p[0])[0]}.json"):
                f.write("%s\t%s\t%s\n" % (p[0], p[1], p[2]))
                rows += 1
    say("manifest_c rows", rows, "/", n)
    for x in ("spans.jsonl", "d_word_data.json", "d_word_merged.json", "build_cd_stats.json", "c_jamo_similarity.json"):
        if os.path.exists(f"{dax}/d/{x}"):
            os.remove(f"{dax}/d/{x}")
    env = dict(ENV, OMP_NUM_THREADS="4", MKL_NUM_THREADS="4")
    run([PY, "build_cd.py", "--data", dax, "--out", "d", "--manifest", "manifest_all.tsv", "--bs", "bs", "--clips", "more/clips"],
        dax, f"{dax}/logs/align.log", env)
    s = json.load(open(f"{dax}/d/build_cd_stats.json", encoding="utf-8"))
    ok, el = int(s.get("ok", 0)), int(s.get("eligible", 0))
    ratio = ok / float(el) if el else 0.0
    res = "n=%d eligible=%d rows=%s ratio=%.3f flagged=%s asr_cer_median=%s" % (ok, el, s.get("rows"), ratio, s.get("flagged"),
                                                                               s.get("asr_cer_median"))
    if not (ok > 0 and ratio >= float(os.environ.get("ALIGN_MIN_RATIO", "0.9"))):
        fail("정렬 비율 미달: " + res)
    print("ALIGN_OK " + res, flush=True)


# ───────────────────────────── v1(v1_remote.sh와 같다) ─────────────────────────────
def v1(dax, smoke=False):
    lg = f"{dax}/logs"
    extra = ["--epochs", "1", "--max-items", "200", "--max-val", "100"] if smoke else []
    ev = ",".join(l.strip() for l in open(f"{dax}/v1/eval40.txt", encoding="utf-8") if l.strip() and not l.startswith("#"))
    if not ev:
        fail("v1/eval40.txt 없음")
    if not os.path.exists(f"{dax}/v1/bench_v1.pkl"):
        args = [PY, "d_bench.py", "build", "--spans", "old/spans.jsonl", "--bs", "old/bs"]
        if not smoke:
            args += ["--spans", "d/spans.jsonl", "--bs", "bs"]
        run(args + ["--rule", "3,3", "--out", "v1/bench_v1.pkl"], dax, f"{lg}/v1_build.log")
    print("V1_BUILD_OK", flush=True)
    run([PY, "v1_train.py", "split", "--bench", "v1/bench_v1.pkl", "--eval-list", "v1/eval40.txt", "--val-n",
         os.environ.get("V1_VAL_N", "12"), "--out", "v1/split.json"], dax)
    print("V1_SPLIT_OK", flush=True)
    roi = None
    if not smoke and os.environ.get("V1_SKIP_ROI") != "1" and not os.path.exists(f"{dax}/roi/_extract_stats.json"):
        roi = popen([PY, "lip_roi_extract.py", "--clips", "more/clips", "--out", "roi", "--workers", os.environ.get("V1_ROI_W", "3"),
                     "--preview", "4"], dax, f"{lg}/roi_extract.log", dict(ENV, OMP_NUM_THREADS="1"))
    par = int(os.environ.get("V1_PAR", "6"))
    runs = [(c, s) for c in "AB" for s in (0, 1, 2)]
    todo = [(c, s) for c, s in runs if not (os.path.exists(f"{dax}/v1/run_{c}{s}/train_summary.json") and
                                            "V1_TRAIN_DONE" in open(f"{lg}/v1_train_{c}{s}.log", encoding="utf-8", errors="replace").read())]
    tenv = dict(ENV, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    rc = 0
    for i in range(0, len(todo), par):
        procs = []
        for c, s in todo[i:i + par]:
            p, fh = popen([PY, "v1_train.py", "train", "--bench", "v1/bench_v1.pkl", "--split", "v1/split.json", "--cand", c, "--seed",
                           str(s), "--out", f"v1/run_{c}{s}", "--threads", "2"] + extra, dax, f"{lg}/v1_train_{c}{s}.log", tenv)
            procs.append((p, fh, f"{c}{s}"))
        rc |= wait_all(procs, "train")
    for c, s in runs:
        txt = open(f"{lg}/v1_train_{c}{s}.log", encoding="utf-8", errors="replace").read()
        if "V1_TRAIN_DONE" not in txt:
            rc = 1
        for l in txt.splitlines():
            if l.startswith("[data]") or l.startswith("V1_TRAIN"):
                print(f"[{c}{s}] {l}", flush=True)
    if rc:
        fail("train(logs/v1_train_*.log)")
    print("V1_TRAIN_OK", flush=True)
    rl = ",".join(f"v1/run_{c}{s}" for c, s in runs)
    run([PY, "v1_train.py", "select", "--runs", rl, "--out", "v1/sel.json"], dax)
    sel = json.load(open(f"{dax}/v1/sel.json", encoding="utf-8"))["selected"]["run"]
    print("V1_SELECT_OK sel=" + sel, flush=True)
    p4 = ["--scoring", "greedy_lev,ctc_ll", "--alpha", "1", "--pad", "idle75", "--dup", "1,2", "--speakers", ev, "--boot",
          "200" if smoke else "10000"]
    penv = dict(ENV, OMP_NUM_THREADS="2")
    jobs = [("base", "kr_d_lipread_1120.pt")] + [(f"{c}{s}", f"v1/run_{c}{s}/model.pt") for c, s in runs]
    procs = []
    for name, ck in jobs:
        p, fh = popen([PY, "d_bench.py", "product4way", "--bench", "v1/bench_v1.pkl", "--ctc", ck] + p4 + ["--out", f"v1/p4_{name}.json"],
                      dax, f"{lg}/v1_p4_{name}.log", penv)
        procs.append((p, fh, name))
    rc = wait_all(procs, "p4")
    for name, _ in jobs:
        if "P4_DONE" not in open(f"{lg}/v1_p4_{name}.log", encoding="utf-8", errors="replace").read():
            rc = 1
    if rc:
        fail("product4way(logs/v1_p4_*.log)")
    print("V1_P4_OK", flush=True)
    S = sel.split("_")[-1]
    oth = ",".join(f"v1/p4_{c}{s}.json" for c, s in runs if f"{c}{s}" != S)
    run([PY, "v1_judge.py", "--sel", "v1/sel.json", "--p4", f"v1/p4_{S}.json", "--base", "v1/p4_base.json", "--others", oth,
         "--out", "v1/v1_verdict.json"], dax, f"{lg}/v1_judge.log")
    try:
        run([PY, "export_lipread_onnx.py", f"{sel}/model.pt", "v1/kr_d_lipread_v1.onnx"], dax, f"{lg}/v1_onnx.log")
    except SystemExit:
        say("[v1] ONNX 내보내기 실패(판정과 무관, logs/v1_onnx.log)")
    if roi:
        roi[0].wait()
        roi[1].close()
    gate = [l for l in open(f"{lg}/v1_judge.log", encoding="utf-8", errors="replace").read().splitlines() if l.startswith("V1_GATE")]
    print("V1_ALL_OK", gate[-1] if gate else "", flush=True)


def smoke_eval(dax):
    """smoke: 기존 화자 가운데 sha256 순 10명을 가짜 평가 화자로(판정용 아님)."""
    spk = sorted({json.loads(l)["spk"] for l in open(f"{dax}/old/spans.jsonl", encoding="utf-8")})
    ev = sorted(spk, key=lambda s: hashlib.sha256(f"liplab-v1-eval:{s}".encode()).hexdigest())[:10]
    open(f"{dax}/v1/eval40.txt", "w", encoding="utf-8").write("# smoke(판정용 아님)\n" + "\n".join(ev) + "\n")


def main():
    cmd = sys.argv[1]
    if cmd == "smoke":
        dax = os.environ.get("V1_DAX", "D:/liplab/v1/smoke")
        os.environ.setdefault("V1_VAL_N", "4")
        stage(dax, smoke=True)
        smoke_eval(dax)
        v1(dax, smoke=True)
        print("V1D_SMOKE_OK", flush=True)
        return
    dax = os.environ.get("V1_DAX", "D:/liplab/v1/dax")
    for c in (["stage", "extract", "align", "v1"] if cmd == "all" else [cmd]):
        {"stage": stage, "extract": extract, "align": align, "v1": v1}[c](dax)


if __name__ == "__main__":
    main()
