"""S4 채점 모델 증류(docs/scorer-distill-2026-10.md), 파드 쪽: 자료 준비, 교사 목표, 학생 학습, ONNX 내보내기.

  python s4_distill_pod.py data [--quick]      Zeroth·YODAS 받기 → 덩어리 → 저하 사본 → 풀(memmap), 개발 자료(Zeroth 시험 × 4조건)
  python s4_distill_pod.py teacher             교사 int8 정렬기·채점기 로짓(float16)을 풀과 개발 자료에 대해 미리 계산
  python s4_distill_pod.py train H|X           학생 학습(두 초기값에 같은 묶음·같은 단계 수)
  python s4_distill_pod.py export H|X          ONNX fp32 → 가중치 전용 int8(주 산출물), 동적 int8(보고만)
  python s4_distill_pod.py selftest            작은 무작위 자료로 배관만 점검(GPU 있으면 GPU)

자료와 결과는 /workspace/data, /workspace/runs 아래. 앱 저장소에는 이 파일만 둔다. 538·608 음성은 여기서 쓰지 않는다.
"""
import argparse
import io
import json
import math
import os
import sys
import tarfile
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np

W = os.environ.get("S4_W", "/workspace")
DATA = f"{W}/data"
RUNS = f"{W}/runs"
BK = f"{W}/backend"
AL_DIR = f"{BK}/models/dgop_ours/aligner"
SC_DIR = f"{BK}/models/dgop_ours/scorer"
SR = 16000
V = 49                       # 자모 어휘(교사 로짓 차원)
MAX_CHUNK_S = 10.0           # YODAS 덩어리 상한, 학습 자르기 상한
BATCH_S = 240.0              # 묶음당 음성 합계 상한(초)
MAX_ITEMS = 64
MIN_ITEM_S = 1.0
YODAS_SHARDS = [0, 35, 70, 105, 140, 175, 210, 245]
YODAS_CLEAN_CAP_H = 80.0
X_KEEP = [0, 5, 9, 14, 18, 23]   # 축소 XLS-R이 교사 채점기에서 가져올 층
H_ID = "team-lucid/hubert-base-korean"
SEED = 0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def conv_len(n):
    """wav2vec2·HuBERT 합성곱 7층(커널 10,3,3,3,3,2,2 / 보폭 5,2,2,2,2,2,2)의 출력 프레임 수."""
    for k, s in zip((10, 3, 3, 3, 3, 2, 2), (5, 2, 2, 2, 2, 2, 2)):
        n = (n - k) // s + 1
    return max(0, int(n))


def crc(s):
    return zlib.crc32(s.encode())


def ncpu():
    q = None
    try:
        a, b = open("/sys/fs/cgroup/cpu.max").read().split()
        if a != "max":
            q = int(int(a) / int(b))
    except Exception:
        try:      # cgroup v1(RunPod 호스트 일부): cfs 할당
            a = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
            b = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
            if a > 0:
                q = int(a / b)
        except Exception:
            pass
    n = os.cpu_count() or 4
    return max(1, min(n, q) if q else n)


# ───────────────────────── data ─────────────────────────
def _decode(b):
    import soundfile as sf
    y, sr = sf.read(io.BytesIO(b), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != SR:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    return np.asarray(y, dtype=np.float32)


def _degrade(args):
    """(이름, 파형, 방식) → 저하 파형. 방식 'stretch'는 학습 증강(sample_aug), 'mild|mod|sev'는 PRESETS(개발 자료)."""
    name, y, how = args
    sys.path.insert(0, f"{W}/tools")
    import make_deaf_corpus as M
    rng = np.random.default_rng(crc(name))
    if how == "stretch":
        p = M.sample_aug(rng, "stretch")
        p["seed"] = crc(name)
    else:
        p = dict(M.PRESETS[how], seed=crc(name))
    out = M.perturb_safe(y, SR, **p)
    return name, np.asarray(out, dtype=np.float32)


def _zeroth_files(split):
    return ["data/test-00000-of-00001.parquet"] if split == "test" else [f"data/train-0000{i}-of-00006.parquet" for i in range(6)]


def _zeroth_iter(split, limit=None):
    """Zeroth 발화를 파일 단위로 내준다(메모리를 아끼려고 한 번에 다 올리지 않는다)."""
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq
    n = 0
    for fn in _zeroth_files(split):
        p = hf_hub_download("kresnik/zeroth_korean", fn, repo_type="dataset", cache_dir=f"{DATA}/hf")
        t = pq.read_table(p)
        log("zeroth", split, fn, "rows", t.num_rows, "cols", t.column_names)
        group = []
        for row in t.to_pylist():
            a = row["audio"]
            uid = str(row.get("id") or row.get("path") or a.get("path"))
            group.append({"name": f"z:{uid}", "text": row.get("text", ""), "spk": str(row.get("speaker_id", "")),
                          "corpus": "zeroth", "y": _decode(a["bytes"])})
            n += 1
            if limit and n >= limit:
                break
        yield group
        if limit and n >= limit:
            return


def _yodas_iter(cap_h, shards):
    """YODAS ko000 셔드마다 (이어진 구간을 10초 이하로 이은) 덩어리 목록을 내준다. 깨끗한 덩어리 합이 cap_h에 닿으면 멈춘다."""
    from huggingface_hub import hf_hub_download
    import soundfile as sf
    total = 0.0
    for k in shards:
        p = hf_hub_download("espnet/yodas", f"data/ko000/audio/{k:08d}.tar.gz", repo_type="dataset", cache_dir=f"{DATA}/hf")
        segs = {}
        with tarfile.open(p, "r:gz") as tf:
            for m in tf:
                if not m.isfile() or not m.name.endswith(".wav"):
                    continue
                parts = os.path.basename(m.name)[:-4].rsplit("-", 3)
                if len(parts) != 4:
                    continue
                y, sr = sf.read(io.BytesIO(tf.extractfile(m).read()), dtype="int16", always_2d=False)
                if y.ndim > 1:
                    y = y.mean(axis=1).astype(np.int16)
                if sr != SR:
                    import librosa
                    y = np.round(librosa.resample(y.astype(np.float32) / 32767, orig_sr=sr, target_sr=SR) * 32767).astype(np.int16)
                segs.setdefault(parts[0], []).append((int(parts[1]), y))
        if os.environ.get("S4_KEEP_RAW") != "1":
            os.remove(os.path.realpath(p))
        out = []
        for vid in sorted(segs):
            cur, cur_n, last = [], 0, None
            for idx, y in sorted(segs[vid], key=lambda t: t[0]):
                if cur and (idx != last + 1 or (cur_n + len(y)) / SR > MAX_CHUNK_S):
                    out.append({"name": f"y:{vid}:{cur[0][0]:05d}", "corpus": "yodas", "y": np.concatenate([c[1] for c in cur])})
                    cur, cur_n = [], 0
                cur.append((idx, y))
                cur_n += len(y)
                last = idx
            if cur:
                out.append({"name": f"y:{vid}:{cur[0][0]:05d}", "corpus": "yodas", "y": np.concatenate([c[1] for c in cur])})
        keep = []
        for c in out:
            if total / 3600 >= cap_h:
                break
            keep.append(c)
            total += len(c["y"]) / SR
        log("yodas shard", k, "chunks", len(keep), "clean_total_h", round(total / 3600, 2))
        yield keep
        if total / 3600 >= cap_h:
            return


class Pool:
    """음성 int16 memmap + 색인. 교사 로짓은 frames 기준 오프셋으로 따로 둔다."""

    def __init__(self, root):
        self.root = root
        self.idx = json.load(open(f"{root}/index.json"))
        self.audio = np.memmap(f"{root}/audio.i16", dtype=np.int16, mode="r")

    def wave(self, i):
        it = self.idx[i]
        return self.audio[it["off"]:it["off"] + it["n"]].astype(np.float32) / 32767.0


class PoolWriter:
    def __init__(self, root):
        os.makedirs(root, exist_ok=True)
        self.root, self.idx, self.off, self.foff = root, [], 0, 0
        self.f = open(f"{root}/audio.i16", "wb")

    def add(self, it):
        y = it["y"]
        q = y if y.dtype == np.int16 else np.round(np.clip(y, -1, 1) * 32767).astype(np.int16)
        self.f.write(q.tobytes())
        nf = conv_len(len(q))
        self.idx.append({k: v for k, v in it.items() if k != "y"} | {"off": self.off, "n": int(len(q)), "foff": self.foff, "nf": nf})
        self.off += len(q)
        self.foff += nf

    def close(self):
        self.f.close()
        json.dump(self.idx, open(f"{self.root}/index.json", "w"), ensure_ascii=False)
        log("pool", self.root, "items", len(self.idx), "hours", round(self.off / SR / 3600, 2), "frames", self.foff)


def _f32(y):
    return y.astype(np.float32) / 32767.0 if y.dtype == np.int16 else y


def cmd_data(quick=False):
    os.makedirs(DATA, exist_ok=True)
    nw = ncpu()
    log("cpus", nw)
    t0 = time.time()
    import soundfile as sf
    dev = PoolWriter(f"{DATA}/dev")
    pool = PoolWriter(f"{DATA}/pool")
    os.makedirs(f"{DATA}/devwav", exist_ok=True)
    rows = []
    hours = {}

    def note(it):
        k = f"{it['corpus']}:{it['cond']}"
        hours[k] = hours.get(k, 0) + len(it["y"]) / SR / 3600

    with ProcessPoolExecutor(nw) as ex:
        # 개발 자료: Zeroth 시험 × (원본, mild, mod, sev). 평가(6.3)용 wav도 쓴다
        test = [t for g in _zeroth_iter("test", 12 if quick else None) for t in g]
        for cond in ("clean", "mild", "mod", "sev"):
            if cond == "clean":
                res = {t["name"]: t["y"] for t in test}
            else:
                res = dict(ex.map(_degrade, [(t["name"], _f32(t["y"]), cond) for t in test], chunksize=4))
            for t in test:
                name = t["name"] if cond == "clean" else f"{t['name']}|{cond}"
                it = {"name": name, "src": t["name"], "text": t["text"], "spk": t["spk"], "corpus": "zeroth_test", "cond": cond,
                      "y": res[t["name"]]}
                dev.add(it)
                fn = f"{DATA}/devwav/{crc(name):08x}.wav"
                sf.write(fn, np.clip(_f32(it["y"]), -1, 1), SR, subtype="PCM_16")
                rows.append({"name": name, "src": t["name"], "cond": cond, "text": t["text"], "spk": t["spk"], "path": fn})
        json.dump(rows, open(f"{DATA}/devwav/dev.json", "w"), ensure_ascii=False)
        log("dev zeroth", len(rows), round(time.time() - t0), "s")
        del test

        def feed(group):
            clean = [t for t in group if len(t["y"]) >= MIN_ITEM_S * SR]
            for t in clean:
                it = {"name": t["name"], "corpus": t["corpus"], "cond": "clean", "y": t["y"]}
                pool.add(it)
                note(it)
            todo = [t for t in clean if t["corpus"] == "zeroth" or crc(t["name"]) % 2 == 0]
            for name, y in ex.map(_degrade, [(t["name"], _f32(t["y"]), "stretch") for t in todo], chunksize=8):
                if len(y) >= MIN_ITEM_S * SR:
                    it = {"name": f"{name}|deg", "corpus": "zeroth" if name.startswith("z:") else "yodas", "cond": "deg", "y": y}
                    pool.add(it)
                    note(it)
            log("fed", len(clean), "degraded", len(todo), "pool_items", len(pool.idx), round(time.time() - t0), "s")

        for group in _zeroth_iter("train", 200 if quick else None):
            feed(group)
        for group in _yodas_iter(0.3 if quick else YODAS_CLEAN_CAP_H, YODAS_SHARDS[:1] if quick else YODAS_SHARDS):
            dv = [c for c in group if crc(c["name"]) % 100 == 0]
            for c in dv:
                dev.add({"name": c["name"], "src": c["name"], "text": "", "spk": "", "corpus": "yodas", "cond": "yodas", "y": c["y"]})
            feed([c for c in group if crc(c["name"]) % 100 != 0])
    pool.close()
    dev.close()
    json.dump({"hours": hours, "n_items": len(pool.idx), "n_dev": len(dev.idx), "yodas_shards": YODAS_SHARDS,
               "sec": round(time.time() - t0)}, open(f"{DATA}/data_summary.json", "w"), indent=1)
    log("DATA_OK", json.dumps({k: round(v, 2) for k, v in hours.items()}))


# ───────────────────────── teacher ─────────────────────────
def load_teacher(device):
    sys.path.insert(0, BK)
    import torch
    import quant_int8 as Q
    al = Q.load_ctc(AL_DIR).to(device).eval()
    sc = Q.load_ctc(SC_DIR).to(device).eval()
    return al, sc


def _norm(y):
    y = np.asarray(y, dtype=np.float32)
    return (y - y.mean()) / np.sqrt(y.var() + 1e-7)


def teacher_logits_batch(models, waves, device):
    """waves: 파형 리스트 → [(al [F,V] f16, sc [F,V] f16)]. 길이를 맞춰 덧대고 attention mask를 준다."""
    import torch
    n = max(len(w) for w in waves)
    x = np.zeros((len(waves), n), dtype=np.float32)
    m = np.zeros((len(waves), n), dtype=np.int64)
    for i, w in enumerate(waves):
        x[i, :len(w)] = _norm(w)
        m[i, :len(w)] = 1
    xt, mt = torch.from_numpy(x).to(device), torch.from_numpy(m).to(device)
    out = []
    with torch.no_grad():
        la = models[0](xt, attention_mask=mt).logits.float().cpu().numpy()
        ls = models[1](xt, attention_mask=mt).logits.float().cpu().numpy()
    for i, w in enumerate(waves):
        nf = conv_len(len(w))
        out.append((la[i, :nf].astype(np.float16), ls[i, :nf].astype(np.float16)))
    return out


def run_teacher_on(root, models, device, max_batch_s=320.0):
    pool = Pool(root)
    tot = pool.idx[-1]["foff"] + pool.idx[-1]["nf"] if pool.idx else 0
    al = np.lib.format.open_memmap(f"{root}/t_al.npy", mode="w+", dtype=np.float16, shape=(tot, V))
    sc = np.lib.format.open_memmap(f"{root}/t_sc.npy", mode="w+", dtype=np.float16, shape=(tot, V))
    order = sorted(range(len(pool.idx)), key=lambda i: pool.idx[i]["n"])
    t0, done, b = time.time(), 0, []

    def flush(b):
        res = teacher_logits_batch(models, [pool.wave(i) for i in b], device)
        for i, (a, s) in zip(b, res):
            it = pool.idx[i]
            assert a.shape[0] == it["nf"], (a.shape, it["nf"])
            al[it["foff"]:it["foff"] + it["nf"]] = a
            sc[it["foff"]:it["foff"] + it["nf"]] = s

    for i in order:
        n = pool.idx[i]["n"]
        if b and ((len(b) + 1) * n > max_batch_s * SR or len(b) >= MAX_ITEMS):
            flush(b)
            done += len(b)
            b = []
            if done % 2000 < MAX_ITEMS:
                log("teacher", root, done, len(order), round(time.time() - t0), "s")
        b.append(i)
    if b:
        flush(b)
    al.flush()
    sc.flush()
    log("teacher done", root, len(order), round(time.time() - t0), "s")


def cmd_teacher():
    import torch
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    device = "cuda"
    models = load_teacher(device)
    # 묶음 대 하나씩 점검(표본 20개, 개발 자료)
    dev = Pool(f"{DATA}/dev")
    rng = np.random.default_rng(0)
    pick = sorted(rng.choice(len(dev.idx), min(20, len(dev.idx)), replace=False).tolist(), key=lambda i: dev.idx[i]["n"])
    single = [teacher_logits_batch(models, [dev.wave(i)], device)[0] for i in pick]
    batched = teacher_logits_batch(models, [dev.wave(i) for i in pick], device)
    dmax, pmax = 0.0, 0.0
    for (a1, s1), (a2, s2) in zip(single, batched):
        for u, v in ((a1, a2), (s1, s2)):
            u, v = u.astype(np.float32), v.astype(np.float32)
            dmax = max(dmax, float(np.abs(u - v).max()))
            pu = np.exp(u - u.max(-1, keepdims=True)); pu /= pu.sum(-1, keepdims=True)
            pv = np.exp(v - v.max(-1, keepdims=True)); pv /= pv.sum(-1, keepdims=True)
            pmax = max(pmax, float(np.abs(pu - pv).max()))
    log("TEACHER_BATCH_CHECK logit_maxdiff", round(dmax, 4), "prob_maxdiff", round(pmax, 5))
    json.dump({"logit_maxdiff": dmax, "prob_maxdiff": pmax, "n": len(pick)}, open(f"{DATA}/teacher_batch_check.json", "w"))
    run_teacher_on(f"{DATA}/dev", models, device)
    run_teacher_on(f"{DATA}/pool", models, device)
    log("TEACHER_OK")


# ───────────────────────── student ─────────────────────────
_SCLS = []


def student_class():
    """학생 = 인코더 + CTC 출력층 둘(정렬 al, 채점 sc). normalize면 입력을 평균 0·분산 1로(교사 전처리와 같은 식)."""
    if _SCLS:
        return _SCLS[0]
    import torch
    from torch import nn

    class Student(nn.Module):
        def __init__(self, enc, hid, normalize):
            super().__init__()
            self.enc = enc
            self.normalize = normalize
            self.head_al = nn.Linear(hid, V)
            self.head_sc = nn.Linear(hid, V)

        def forward(self, wav):
            x = wav
            if self.normalize:
                m = x.mean(-1, keepdim=True)
                v = ((x - m) ** 2).mean(-1, keepdim=True)
                x = (x - m) / torch.sqrt(v + 1e-7)
            h = self.enc(x).last_hidden_state
            return self.head_al(h), self.head_sc(h)
    _SCLS.append(Student)
    return Student


def build_student(init, device="cpu"):
    import torch
    from torch import nn
    from transformers import AutoConfig, HubertModel, Wav2Vec2Config, Wav2Vec2Model
    Student = student_class()

    drop = dict(hidden_dropout=0.05, attention_dropout=0.05, activation_dropout=0.0, feat_proj_dropout=0.05, layerdrop=0.0,
                apply_spec_augment=False, mask_time_prob=0.0)
    if init == "H":
        cfg = AutoConfig.from_pretrained(H_ID, **drop)
        cfg._attn_implementation = "eager"
        enc = HubertModel.from_pretrained(H_ID, config=cfg)
        st = Student(enc, cfg.hidden_size, normalize=False)
        nn.init.normal_(st.head_al.weight, std=0.02); nn.init.zeros_(st.head_al.bias)
        nn.init.normal_(st.head_sc.weight, std=0.02); nn.init.zeros_(st.head_sc.bias)
    elif init == "X":
        sys.path.insert(0, BK)
        import quant_int8 as Q
        full = {}
        for tag, d in (("sc", SC_DIR), ("al", AL_DIR)):
            m = Q.load_ctc(d)
            sd = {}
            for k, v in m.state_dict().items():
                sd[k] = v
            # Int8Linear(qweight, scale) → fp32 weight
            fp = {}
            for k in list(sd):
                if k.endswith(".qweight"):
                    base = k[:-len(".qweight")]
                    fp[base + ".weight"] = sd[k].float() * sd[base + ".scale"].float()[:, None]
                elif k.endswith(".scale"):
                    continue
                else:
                    fp[k] = sd[k].float() if sd[k].is_floating_point() else sd[k]
            full[tag] = fp
        tcfg = Wav2Vec2Config.from_pretrained(SC_DIR)
        cfg = Wav2Vec2Config.from_pretrained(SC_DIR, num_hidden_layers=len(X_KEEP), **drop)
        cfg._attn_implementation = "eager"
        enc = Wav2Vec2Model(cfg)
        src = full["sc"]
        new = {}
        for k in enc.state_dict():
            if k.startswith("encoder.layers."):
                j = int(k.split(".")[2])
                sk = "wav2vec2." + k.replace(f"encoder.layers.{j}.", f"encoder.layers.{X_KEEP[j]}.", 1)
            else:
                sk = "wav2vec2." + k
            if sk not in src:
                raise KeyError(f"교사에 없는 키 {sk}")
            new[k] = src[sk]
        missing = enc.load_state_dict(new, strict=True)
        st = Student(enc, cfg.hidden_size, normalize=True)
        with torch.no_grad():
            st.head_sc.weight.copy_(full["sc"]["lm_head.weight"]); st.head_sc.bias.copy_(full["sc"]["lm_head.bias"])
            st.head_al.weight.copy_(full["al"]["lm_head.weight"]); st.head_al.bias.copy_(full["al"]["lm_head.bias"])
        assert tcfg.num_hidden_layers == 24
    else:
        raise ValueError(init)
    for p in st.enc.feature_extractor.parameters():
        p.requires_grad_(False)
    return st.to(device)


def n_params(m):
    return sum(p.numel() for p in m.parameters())


def make_batches(pool, n_steps, seed=SEED):
    """같은 시드면 같은 묶음 순서. 한 번 돌 때마다 길이 정렬(작은 잡음) → 묶기 → 묶음 순서 섞기. (항목, 자르기 시작) 목록."""
    items = [i for i, it in enumerate(pool.idx)]
    lens = np.array([pool.idx[i]["n"] for i in items], dtype=np.int64)
    cap = int(MAX_CHUNK_S * SR)
    out, ep = [], 0
    while len(out) < n_steps:
        rng = np.random.default_rng(seed * 1000 + ep)
        key = lens * (1.0 + rng.uniform(-0.05, 0.05, len(lens)))
        order = np.argsort(key, kind="stable")
        batches, cur, L = [], [], None
        for j in order:
            n = min(int(lens[j]), cap)
            if cur and ((len(cur) + 1) * min(L, n) > BATCH_S * SR or len(cur) >= MAX_ITEMS):
                batches.append((cur, L))
                cur, L = [], None
            cur.append(int(items[j]))
            L = n if L is None else min(L, n)
        if cur:
            batches.append((cur, L))
        perm = rng.permutation(len(batches))
        for b in perm:
            idxs, L = batches[b]
            L = (L // 320) * 320
            offs = []
            for i in idxs:
                room = (pool.idx[i]["n"] - L) // 320
                offs.append(int(rng.integers(0, room + 1)) * 320 if room > 0 else 0)
            out.append((idxs, L, offs))
        ep += 1
    return out[:n_steps]


class BatchDS:
    def __init__(self, root, batches):
        self.root, self.batches = root, batches
        self.pool = None

    def __len__(self):
        return len(self.batches)

    def __getitem__(self, k):
        if self.pool is None:
            self.pool = Pool(self.root)
            self.tal = np.load(f"{self.root}/t_al.npy", mmap_mode="r")
            self.tsc = np.load(f"{self.root}/t_sc.npy", mmap_mode="r")
        idxs, L, offs = self.batches[k]
        nf = conv_len(L)
        x = np.zeros((len(idxs), L), dtype=np.float32)
        ta = np.zeros((len(idxs), nf, V), dtype=np.float16)
        ts = np.zeros((len(idxs), nf, V), dtype=np.float16)
        for r, (i, o) in enumerate(zip(idxs, offs)):
            it = self.pool.idx[i]
            x[r] = self.pool.audio[it["off"] + o:it["off"] + o + L].astype(np.float32) / 32767.0
            f0 = it["foff"] + o // 320
            assert o // 320 + nf <= it["nf"], (o, L, it["nf"])
            ta[r] = self.tal[f0:f0 + nf]
            ts[r] = self.tsc[f0:f0 + nf]
        return x, ta, ts


def kl(t16, s):
    import torch
    lt = torch.log_softmax(t16.float(), -1)
    ls = torch.log_softmax(s.float(), -1)
    return (lt.exp() * (lt - ls)).sum(-1).mean()


def dev_kl(st, device, max_items=None):
    import torch
    dev = Pool(f"{DATA}/dev")
    tal = np.load(f"{DATA}/dev/t_al.npy", mmap_mode="r")
    tsc = np.load(f"{DATA}/dev/t_sc.npy", mmap_mode="r")
    res = {}
    st.eval()
    with torch.no_grad():
        for i, it in enumerate(dev.idx[:max_items] if max_items else dev.idx):
            y = dev.wave(i)[:int(MAX_CHUNK_S * SR)]
            nf = conv_len(len(y))
            a, s = st(torch.from_numpy(y)[None].to(device))
            ka = kl(torch.from_numpy(np.asarray(tal[it["foff"]:it["foff"] + nf]))[None].to(device), a.float())
            ks = kl(torch.from_numpy(np.asarray(tsc[it["foff"]:it["foff"] + nf]))[None].to(device), s.float())
            res.setdefault(it["cond"], []).append((float(ka), float(ks)))
    st.train()
    return {c: {"kl_al": float(np.mean([v[0] for v in r])), "kl_sc": float(np.mean([v[1] for v in r])), "n": len(r)}
            for c, r in res.items()}


def cmd_train(init, steps_override=None):
    import torch
    from torch.utils.data import DataLoader
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    device = "cuda"
    pool = Pool(f"{DATA}/pool")
    total_s = sum(it["n"] for it in pool.idx) / SR
    n_steps = steps_override or int(math.ceil(2 * total_s / BATCH_S))
    out = f"{RUNS}/{init}"
    os.makedirs(out, exist_ok=True)
    batches = make_batches(pool, n_steps)
    torch.manual_seed(SEED)
    st = build_student(init, device)
    st.train()
    st.enc.feature_extractor.eval()
    params = [p for p in st.parameters() if p.requires_grad]
    log("TRAIN", init, "params_total", n_params(st), "trainable", sum(p.numel() for p in params), "steps", n_steps,
        "pool_h", round(total_s / 3600, 2))
    opt = torch.optim.AdamW(params, lr=1e-4, betas=(0.9, 0.98), weight_decay=0.01, fused=True)
    warm = max(1, int(0.05 * n_steps))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) if s < warm else max(0.0, (n_steps - s) / (n_steps - warm)))
    start = 0
    ck = f"{out}/ckpt.pt"
    if os.path.exists(ck):
        sd = torch.load(ck, map_location=device)
        st.load_state_dict(sd["model"]); opt.load_state_dict(sd["opt"]); sched.load_state_dict(sd["sched"])
        start = sd["step"]
        log("resume", start)
    dl = DataLoader(BatchDS(f"{DATA}/pool", batches[start:]), batch_size=None, shuffle=False, num_workers=min(8, ncpu()),
                    pin_memory=True, prefetch_factor=4, persistent_workers=False)
    t0, hist = time.time(), []
    step = start
    for x, ta, ts in dl:
        x = x.to(device, non_blocking=True)
        ta = ta.to(device, non_blocking=True)
        ts = ts.to(device, non_blocking=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            a, s = st(x)
        assert a.shape[1] == ta.shape[1], (a.shape, ta.shape)
        la, ls = kl(ta, a), kl(ts, s)
        loss = la + ls
        opt.zero_grad(set_to_none=True)
        loss.backward()
        gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sched.step()
        step += 1
        hist.append((float(la), float(ls)))
        if step % 50 == 0 or step == n_steps:
            h = np.array(hist[-50:])
            log(f"step {step}/{n_steps} kl_al {h[:, 0].mean():.4f} kl_sc {h[:, 1].mean():.4f} gn {float(gn):.2f} "
                f"lr {sched.get_last_lr()[0]:.2e} items {x.shape[0]} L {x.shape[1] / SR:.1f}s {(time.time() - t0) / max(1, step - start):.3f}s/step")
        if step % 1000 == 0 and step < n_steps:
            torch.save({"model": st.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "step": step}, ck + ".tmp")
            os.replace(ck + ".tmp", ck)
        if step >= n_steps:
            break
    torch.save({"model": st.state_dict(), "step": step, "init": init}, f"{out}/final.pt")
    dk = dev_kl(st, device)
    json.dump({"init": init, "steps": step, "params": n_params(st), "train_sec": round(time.time() - t0), "dev_kl": dk,
               "last_kl": np.mean(hist[-200:], axis=0).tolist()}, open(f"{out}/train_summary.json", "w"), indent=1)
    log("TRAIN_OK", init, json.dumps(dk))


# ───────────────────────── export ─────────────────────────
def fold_weight_norm(model):
    import torch
    from torch.nn.utils import parametrize
    n = 0
    for m in model.modules():
        if parametrize.is_parametrized(m, "weight"):
            parametrize.remove_parametrizations(m, "weight", leave_parametrized=True)
            n += 1
        elif hasattr(m, "weight_g") and hasattr(m, "weight_v"):
            torch.nn.utils.remove_weight_norm(m)
            n += 1
    return n


def quantize_weights_int8(src, dst, skip_out=V, conv="fp16"):
    """가중치 전용 int8: MatMul·Gemm의 상수 가중치를 출력 채널별 대칭 int8 + DequantizeLinear로 바꾼다.
    서버 quant_int8과 같은 규칙(scale = max|w|/127, round, [-127, 127]). 출력 차원이 skip_out(49, CTC 출력층)인 것은 fp32로 둔다.
    합성곱 가중치는 conv='fp16'이면 float16 + Cast(10/7 측정 전 변경: 합성곱 int8은 출력이 크게 흔들렸다, 9.3절), 'int8'이면 int8."""
    import onnx
    from onnx import helper, numpy_helper
    m = onnx.load(src)
    g = m.graph
    inits = {i.name: i for i in g.initializer}
    consumers = {}
    for n in g.node:
        for k, name in enumerate(n.input):
            consumers.setdefault(name, []).append((n, k))
    new_nodes, done, stats = [], set(), {"q": 0, "kept": 0}
    for name, init in list(inits.items()):
        uses = consumers.get(name, [])
        if not uses:
            continue
        axis = None
        for n, k in uses:
            if n.op_type == "MatMul" and k == 1:
                axis = 1
            elif n.op_type == "Gemm" and k == 1:
                tb = next((a.i for a in n.attribute if a.name == "transB"), 0)
                axis = 0 if tb else 1
            elif n.op_type == "Conv" and k == 1:
                axis = 0
            else:
                axis = None
                break
        if axis is None:
            continue
        w = numpy_helper.to_array(init).astype(np.float32)
        is_conv = all(n.op_type == "Conv" for n, _ in uses)
        if is_conv and conv == "fp16":
            g.initializer.remove(init)
            g.initializer.append(numpy_helper.from_array(w.astype(np.float16), name + "_h16"))
            new_nodes.append(helper.make_node("Cast", [name + "_h16"], [name], to=onnx.TensorProto.FLOAT, name=name + "_cast16"))
            stats["fp16"] = stats.get("fp16", 0) + 1
            continue
        if w.ndim < 2 or w.size < 4096 or w.shape[axis] == skip_out:
            stats["kept"] += 1
            continue
        red = tuple(i for i in range(w.ndim) if i != axis)
        scale = np.maximum(np.abs(w).max(axis=red), 1e-12) / 127.0
        shp = [1] * w.ndim
        shp[axis] = -1
        q = np.clip(np.round(w / scale.reshape(shp)), -127, 127).astype(np.int8)
        g.initializer.remove(init)
        g.initializer.extend([numpy_helper.from_array(q, name + "_q8"),
                              numpy_helper.from_array(scale.astype(np.float32), name + "_s8"),
                              numpy_helper.from_array(np.zeros(len(scale), dtype=np.int8), name + "_z8")])
        new_nodes.append(helper.make_node("DequantizeLinear", [name + "_q8", name + "_s8", name + "_z8"], [name], axis=axis,
                                          name=name + "_dq8"))
        stats["q"] += 1
    for n in reversed(new_nodes):
        g.node.insert(0, n)
    onnx.checker.check_model(m)
    onnx.save(m, dst)
    return stats


def cmd_export(init):
    import torch
    import onnxruntime as ort
    out = f"{RUNS}/{init}"
    st = build_student(init, "cpu")
    sd = torch.load(f"{out}/final.pt", map_location="cpu")["model"]
    st.load_state_dict(sd)
    st.eval()
    nfold = fold_weight_norm(st)
    log("weight norm folded", nfold)
    dummy = torch.zeros(1, 4 * SR)
    dummy.normal_(0, 0.05)
    fp32 = f"{out}/student_fp32.onnx"
    torch.onnx.export(st, (dummy,), fp32, input_names=["wav"], output_names=["al", "sc"], opset_version=17,
                      dynamic_axes={"wav": {1: "samples"}, "al": {1: "frames"}, "sc": {1: "frames"}}, dynamo=False,
                      do_constant_folding=True)
    w8 = f"{out}/student_w8.onnx"
    stats = quantize_weights_int8(fp32, w8)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    dyn = f"{out}/student_dyn8.onnx"
    quantize_dynamic(fp32, dyn, weight_type=QuantType.QInt8, per_channel=True, op_types_to_quantize=["MatMul"])
    # 일치 점검: 개발 자료 5개
    dev = Pool(f"{DATA}/dev")
    rng = np.random.default_rng(1)
    pick = rng.choice(len(dev.idx), min(5, len(dev.idx)), replace=False)
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    sess = {k: ort.InferenceSession(p, so, providers=["CPUExecutionProvider"]) for k, p in (("fp32", fp32), ("w8", w8), ("dyn8", dyn))}
    diffs = {k: [] for k in sess}
    with torch.no_grad():
        for i in pick:
            y = dev.wave(int(i))[:int(8 * SR)].astype(np.float32)
            ta, ts = st(torch.from_numpy(y)[None])
            ref = np.concatenate([ta.numpy(), ts.numpy()], -1)[0]
            for k, s in sess.items():
                a, b = s.run(None, {"wav": y[None]})
                o = np.concatenate([a, b], -1)[0]
                assert o.shape == ref.shape, (o.shape, ref.shape)
                pr = np.exp(ref - ref.max(-1, keepdims=True))
                po = np.exp(o - o.max(-1, keepdims=True))
                diffs[k].append(float(np.abs(o - ref).max()))
    sizes = {k: os.path.getsize(p) for k, p in (("fp32", fp32), ("w8", w8), ("dyn8", dyn))}
    info = {"init": init, "sizes": sizes, "w8_stats": stats, "logit_maxdiff_vs_torch": {k: max(v) for k, v in diffs.items()},
            "params": n_params(st), "weight_norm_folded": nfold}
    json.dump(info, open(f"{out}/export.json", "w"), indent=1)
    log("EXPORT_OK", init, json.dumps(info))


def cmd_smoke():
    """실제 두 초기값을 만들어 파라미터 수, 순전파 프레임 수, (학습 전) ONNX·int8 크기와 일치를 본다. 비싼 단계 전에 돈다."""
    import torch
    import onnxruntime as ort
    os.makedirs(RUNS, exist_ok=True)
    res = {}
    for init in ("H", "X"):
        st = build_student(init, "cpu").eval()
        x = torch.randn(1, int(2.5 * SR)) * 0.1
        with torch.no_grad():
            a, s = st(x)
        assert a.shape[1] == conv_len(x.shape[1]), (a.shape, conv_len(x.shape[1]))
        fold_weight_norm(st)
        fp = f"{RUNS}/smoke_{init}.onnx"
        torch.onnx.export(st, (x,), fp, input_names=["wav"], output_names=["al", "sc"], opset_version=17,
                          dynamic_axes={"wav": {1: "samples"}, "al": {1: "frames"}, "sc": {1: "frames"}}, dynamo=False)
        w8 = f"{RUNS}/smoke_{init}_w8.onnx"
        stats = quantize_weights_int8(fp, w8)
        sess = ort.InferenceSession(w8, providers=["CPUExecutionProvider"])
        y = torch.randn(1, int(3.1 * SR)) * 0.1
        with torch.no_grad():
            ra, rs = st(y)
        oa, os_ = sess.run(None, {"wav": y.numpy()})
        pr = torch.softmax(rs, -1).numpy()
        po = np.exp(os_ - os_.max(-1, keepdims=True)); po /= po.sum(-1, keepdims=True)
        res[init] = {"params": n_params(st), "frames_ok": True, "fp32_bytes": os.path.getsize(fp), "w8_bytes": os.path.getsize(w8),
                     "w8_stats": stats, "w8_prob_maxdiff": float(np.abs(pr - po).max())}
        log("SMOKE", init, json.dumps(res[init]))
        os.remove(fp)
    json.dump(res, open(f"{RUNS}/smoke.json", "w"), indent=1)
    log("SMOKE_OK")


# ───────────────────────── selftest ─────────────────────────
def cmd_selftest():
    """배관 점검: 프레임 수 규칙, 작은 무작위 학생(HuBERT·wav2vec2 꼴)의 ONNX 내보내기·int8 변환·ORT 일치, 묶음 만들기."""
    assert conv_len(16000) == 49, conv_len(16000)
    assert conv_len(400) == 1 and conv_len(399) == 0
    for L in (16000, 32000, 48000 + 320 * 7):
        for off in (0, 320, 3200):
            assert off // 320 + conv_len(L) <= conv_len(L + off + 640)
    import tempfile
    import torch
    import onnxruntime as ort
    from transformers import HubertConfig, HubertModel, Wav2Vec2Config, Wav2Vec2Model
    Student = student_class()
    tmp = tempfile.mkdtemp()
    for kind in ("hubert", "w2v"):
        kw = dict(hidden_size=64, num_hidden_layers=2, num_attention_heads=4, intermediate_size=128, conv_dim=[32] * 7,
                  num_conv_pos_embeddings=16, num_conv_pos_embedding_groups=4, apply_spec_augment=False)
        if kind == "hubert":
            cfg = HubertConfig(**kw, feat_extract_norm="group", conv_bias=False)
            enc = HubertModel(cfg)
        else:
            cfg = Wav2Vec2Config(**kw, feat_extract_norm="layer", conv_bias=True, do_stable_layer_norm=True)
            enc = Wav2Vec2Model(cfg)
        cfg._attn_implementation = "eager"
        st = Student(enc, 64, normalize=(kind == "w2v")).eval()
        fold_weight_norm(st)
        x = torch.randn(1, 3 * SR) * 0.1
        fp = f"{tmp}/{kind}.onnx"
        torch.onnx.export(st, (x,), fp, input_names=["wav"], output_names=["al", "sc"], opset_version=17,
                          dynamic_axes={"wav": {1: "samples"}, "al": {1: "frames"}, "sc": {1: "frames"}}, dynamo=False)
        w8 = f"{tmp}/{kind}_w8.onnx"
        stats = quantize_weights_int8(fp, w8, skip_out=V)
        y = (torch.randn(1, int(2.3 * SR)) * 0.1)
        with torch.no_grad():
            ra, rs = st(y)
        for p in (fp, w8):
            s = ort.InferenceSession(p, providers=["CPUExecutionProvider"])
            a, b = s.run(None, {"wav": y.numpy()})
            assert a.shape == tuple(ra.shape), (a.shape, ra.shape)
            d = float(max(np.abs(a - ra.numpy()).max(), np.abs(b - rs.numpy()).max()))
            log("SELFTEST", kind, os.path.basename(p), "frames", a.shape[1], "maxdiff", round(d, 5), "q", stats)
            assert a.shape[1] == conv_len(y.shape[1])
            if p == fp:
                assert d < 1e-3, d
    log("SELFTEST_OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--steps", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "data":
        cmd_data(a.quick)
    elif a.cmd == "teacher":
        cmd_teacher()
    elif a.cmd == "train":
        cmd_train(a.arg, a.steps)
    elif a.cmd == "export":
        cmd_export(a.arg)
    elif a.cmd == "selftest":
        cmd_selftest()
    elif a.cmd == "smoke":
        cmd_smoke()
    else:
        sys.exit(f"알 수 없는 명령 {a.cmd}")
