"""S4 청크 주의 학생(docs/scorer-stream-chunk-2026-10.md), 데스크탑(Windows, RTX 3060) 쪽: 자료·교사·학습·내보내기.

    set S4_W=D:/liplab/s4
    python s4c_desk.py data            원 등록 코드(s4_distill_pod.cmd_data) 그대로: Zeroth·YODAS → 풀·개발 자료
    python s4c_desk.py teacher         교사 int8 로짓(GPU fp16 자동 혼합 정밀도) → data/{pool,dev}/t_al.npy·t_sc.npy
    python s4c_desk.py train [--steps N]   청크 주의 학생 HC(H 초기값) 학습, 250단계·패스마다 체크포인트, 이어 하기
    python s4c_desk.py export          runs/HC/final.pt → ONNX fp32·가중치 전용 int8(원 등록 cmd_export)
    python s4c_desk.py selftest        창 자르기·손실 가리개·프레임 맞춤 점검(모델 없이)

S4_W 아래에 backend(b675975, models/dgop_ours 교사 int8), tools/make_deaf_corpus.py, scripts/s4_distill_pod.py가 있어야 한다.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

W = os.environ.setdefault("S4_W", "D:/liplab/s4")
sys.path.insert(0, os.path.join(W, "scripts"))
import s4_distill_pod as S  # noqa: E402

# 10/17 데스크탑 RAM 16GB: 자료 준비 작업자 상한(원 코드는 CPU 수 12개를 모두 써 메모리가 15GB를 넘었다). YODAS 원본 셔드는 다시 시작할 때 다시 받지 않게 남긴다.
S.ncpu = lambda: int(os.environ.get("S4C_DATA_WORKERS", "5"))
os.environ.setdefault("S4_KEEP_RAW", "1")

SR, V = S.SR, S.V
HOP = 320
C_S, L_S = 4.0, 2.0            # 새 소리, 왼쪽 문맥(추론 고정값 = 앱 dgop_stream 기본, 9절)
R_RANGE = (1.0, 2.0)
P_FULL = 0.6                   # 창 길이 L + C + R 몫
SHORT_RANGE = (3.0, 8.0)
TEACHER_BATCH_S = 160.0
MICRO_S = float(os.environ.get("S4C_MICRO_S", "60"))   # 마이크로 묶음 음성 상한(메모리)
INIT = "HC"
log = S.log


# ───────────────────────── 교사(fp16) ─────────────────────────
def teacher_batch16(models, waves, device):
    import torch
    n = max(len(w) for w in waves)
    x = np.zeros((len(waves), n), dtype=np.float32)
    m = np.zeros((len(waves), n), dtype=np.int64)
    for i, w in enumerate(waves):
        x[i, :len(w)] = S._norm(w)
        m[i, :len(w)] = 1
    xt, mt = torch.from_numpy(x).to(device), torch.from_numpy(m).to(device)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        la = models[0](xt, attention_mask=mt).logits.float().cpu().numpy()
        ls = models[1](xt, attention_mask=mt).logits.float().cpu().numpy()
    out = []
    for i, w in enumerate(waves):
        nf = S.conv_len(len(w))
        out.append((la[i, :nf].astype(np.float16), ls[i, :nf].astype(np.float16)))
    return out


def cmd_teacher():
    import torch
    device = "cuda"
    models = S.load_teacher(device)
    dev = S.Pool(f"{S.DATA}/dev")
    rng = np.random.default_rng(0)
    pick = sorted(rng.choice(len(dev.idx), min(20, len(dev.idx)), replace=False).tolist(), key=lambda i: dev.idx[i]["n"])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    ref = [S.teacher_logits_batch(models, [dev.wave(i)], device)[0] for i in pick]        # fp32, TF32 끔, 하나씩
    got = teacher_batch16(models, [dev.wave(i) for i in pick], device)                    # fp16, 묶음
    dmax, pmax, dmed = 0.0, 0.0, []
    for (a1, s1), (a2, s2) in zip(ref, got):
        for u, v in ((a1, a2), (s1, s2)):
            u, v = u.astype(np.float32), v.astype(np.float32)
            d = np.abs(u - v)
            dmax = max(dmax, float(d.max()))
            dmed.append(float(np.median(d)))
            pu = np.exp(u - u.max(-1, keepdims=True)); pu /= pu.sum(-1, keepdims=True)  # noqa: E702
            pv = np.exp(v - v.max(-1, keepdims=True)); pv /= pv.sum(-1, keepdims=True)  # noqa: E702
            pmax = max(pmax, float(np.abs(pu - pv).max()))
    chk = {"logit_maxdiff": dmax, "logit_median_of_medians": float(np.median(dmed)), "prob_maxdiff": pmax, "n": len(pick),
           "ref": "fp32 TF32 끔 하나씩", "got": "fp16 autocast 묶음"}
    log("TEACHER16_CHECK", json.dumps(chk))
    json.dump(chk, open(f"{S.DATA}/teacher_batch_check.json", "w"), indent=1)
    S.teacher_logits_batch = teacher_batch16
    for root in (f"{S.DATA}/dev", f"{S.DATA}/pool"):
        if os.path.exists(f"{root}/t_done"):
            log("teacher skip", root)
            continue
        S.run_teacher_on(root, models, device, max_batch_s=TEACHER_BATCH_S)
        open(f"{root}/t_done", "w").write(time.strftime("%F %T"))
    log("TEACHER_OK")


# ───────────────────────── 창 만들기 ─────────────────────────
def pass_windows(pool_idx, pass_no, total_steps_hint=None, seed=S.SEED):
    """한 패스: 항목을 섞어 이은 흐름에서 창을 차례로 자른다. 반환 [(batch_windows, Lw)], window = [(item, s0_in_item_samples, n_samples)...]"""
    rng = np.random.default_rng(seed * 1000 + pass_no)
    order = rng.permutation(len(pool_idx))
    # 흐름: (항목, 사용 표본 수 = 320 배수)
    seg = [(int(i), (pool_idx[i]["n"] // HOP) * HOP) for i in order if pool_idx[i]["n"] >= 2 * HOP]
    starts = np.cumsum([0] + [n for _, n in seg])                     # 흐름 위 항목 시작(표본)
    total = int(starts[-1])
    batches, pos = [], 0
    while True:
        if rng.random() < P_FULL:
            R = rng.uniform(*R_RANGE)
            Lw = L_S + C_S + R
        else:
            R = 1.0
            Lw = rng.uniform(*SHORT_RANGE)
        Lw = int(round(Lw * SR / HOP)) * HOP
        Rn = int(round(R * SR / HOP)) * HOP
        k = max(1, min(S.MAX_ITEMS, int(S.BATCH_S * SR // Lw)))
        wins = []
        for _ in range(k):
            if pos + Lw > total:
                break
            wins.append((pos, Lw, Rn))
            pos += Lw - Rn
        if not wins:
            break
        batches.append(wins)
        if pos + Lw > total:
            break
    return seg, starts, batches


def window_target(seg, starts, w, pool, tal, tsc):
    """흐름 위 창 (pos, Lw, Rn) → (파형 [Lw], 교사 al·sc [nf, V], 손실 가리개 [nf])."""
    pos, Lw, Rn = w
    nf = S.conv_len(Lw)
    x = np.zeros(Lw, dtype=np.float32)
    ta = np.zeros((nf, V), dtype=np.float16)
    ts = np.zeros((nf, V), dtype=np.float16)
    mask = np.zeros(nf, dtype=np.float32)
    j = int(np.searchsorted(starts, pos, side="right") - 1)
    end = pos + Lw
    while j < len(seg) and starts[j] < end:
        it_i, n = seg[j]
        it = pool.idx[it_i]
        a, b = max(pos, int(starts[j])), min(end, int(starts[j]) + n)   # 흐름 위 겹침
        o_item = a - int(starts[j])
        x[a - pos:b - pos] = pool.audio[it["off"] + o_item:it["off"] + o_item + (b - a)].astype(np.float32) / 32767.0
        # 창 프레임 f(표본 [pos + 320f, pos + 320f + 400))가 이 항목 안에 통째로 있으면 항목 프레임 (pos + 320f - start)/320
        f_lo = (a - pos + HOP - 1) // HOP if a > pos else 0
        f_lo = max(f_lo, 0)
        for f in range(f_lo, nf):
            s = pos + HOP * f
            if s + 400 > int(starts[j]) + n:
                break
            if s < int(starts[j]):
                continue
            fi = (s - int(starts[j])) // HOP
            if fi >= it["nf"]:
                break
            ta[f] = tal[it["foff"] + fi]
            ts[f] = tsc[it["foff"] + fi]
            mask[f] = 1.0
        j += 1
    # 창 끝 R초는 빼되, 창 끝이 항목 끝과 같으면 넣는다
    jj = int(np.searchsorted(starts, end, side="left"))
    at_item_end = jj < len(starts) and int(starts[jj]) == end
    if not at_item_end:
        cut = (Lw - Rn) // HOP
        mask[max(0, cut):] = 0.0
    return x, ta, ts, mask


class WinDS:
    def __init__(self, root, plan):
        self.root, self.plan = root, plan        # plan: [(pass_no, batch_index)]
        self.pool = None
        self.cache = {}

    def __len__(self):
        return len(self.plan)

    def _pass(self, p):
        if p not in self.cache:
            self.cache.clear()
            self.cache[p] = pass_windows(self.pool.idx, p)
        return self.cache[p]

    def __getitem__(self, k):
        if self.pool is None:
            self.pool = S.Pool(self.root)
            self.tal = np.load(f"{self.root}/t_al.npy", mmap_mode="r")
            self.tsc = np.load(f"{self.root}/t_sc.npy", mmap_mode="r")
        p, b = self.plan[k]
        seg, starts, batches = self._pass(p)
        rows = [window_target(seg, starts, w, self.pool, self.tal, self.tsc) for w in batches[b]]
        return (np.stack([r[0] for r in rows]), np.stack([r[1] for r in rows]), np.stack([r[2] for r in rows]),
                np.stack([r[3] for r in rows]))


def make_plan(pool_idx, n_steps):
    plan, p = [], 0
    while len(plan) < n_steps:
        _, _, batches = pass_windows(pool_idx, p)
        plan += [(p, b) for b in range(len(batches))]
        p += 1
    return plan[:n_steps], p


def kl_masked(t16, s, mask):
    import torch
    lt = torch.log_softmax(t16.float(), -1)
    ls = torch.log_softmax(s.float(), -1)
    per = (lt.exp() * (lt - ls)).sum(-1)
    return (per * mask).sum(), mask.sum()


def cmd_train(steps_override=None):
    import torch
    from torch.utils.data import DataLoader
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    device = "cuda"
    pool = S.Pool(f"{S.DATA}/pool")
    total_s = sum(it["n"] for it in pool.idx) / SR
    n_steps = steps_override or int(math.ceil(2 * total_s / S.BATCH_S))
    out = f"{S.RUNS}/{os.environ.get('S4C_RUN_NAME', INIT)}"     # 시험 학습은 다른 폴더(S4C_RUN_NAME=HC_smoke)
    os.makedirs(out, exist_ok=True)
    plan, n_pass = make_plan(pool.idx, n_steps)
    pass_end = {i for i in range(1, len(plan)) if plan[i][0] != plan[i - 1][0]}
    torch.manual_seed(S.SEED)
    st = S.build_student("H", device)
    st.train()
    st.enc.feature_extractor.eval()
    params = [p for p in st.parameters() if p.requires_grad]
    log("TRAIN", INIT, "params_total", S.n_params(st), "trainable", sum(p.numel() for p in params), "steps", n_steps, "passes", n_pass,
        "pool_h", round(total_s / 3600, 2))
    opt = torch.optim.AdamW(params, lr=1e-4, betas=(0.9, 0.98), weight_decay=0.01, fused=True)
    warm = max(1, int(0.05 * n_steps))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) if s < warm else max(0.0, (n_steps - s) / (n_steps - warm)))
    start = 0
    ck = f"{out}/ckpt.pt"
    if os.path.exists(ck):
        sd = torch.load(ck, map_location=device)
        st.load_state_dict(sd["model"]); opt.load_state_dict(sd["opt"]); sched.load_state_dict(sd["sched"])  # noqa: E702
        start = sd["step"]
        log("resume", start)
    nw = int(os.environ.get("S4C_WORKERS", "4"))
    dl = DataLoader(WinDS(f"{S.DATA}/pool", plan[start:]), batch_size=None, shuffle=False, num_workers=nw, pin_memory=True,
                    prefetch_factor=4 if nw else None, persistent_workers=False)
    t0, hist = time.time(), []
    step = start

    def save():
        torch.save({"model": st.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "step": step}, ck + ".tmp")
        os.replace(ck + ".tmp", ck)

    for x, ta, ts, mk in dl:
        B, Lw = x.shape
        mb = max(1, int(MICRO_S * SR // Lw))
        tot = float(mk.sum())
        opt.zero_grad(set_to_none=True)
        sa_sum, ss_sum = 0.0, 0.0
        for i in range(0, B, mb):
            xi = x[i:i + mb].to(device, non_blocking=True)
            tai = ta[i:i + mb].to(device, non_blocking=True)
            tsi = ts[i:i + mb].to(device, non_blocking=True)
            mi = mk[i:i + mb].to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                a, s = st(xi)
            assert a.shape[1] == tai.shape[1], (a.shape, tai.shape)
            la, _ = kl_masked(tai, a, mi)
            ls, _ = kl_masked(tsi, s, mi)
            loss = (la + ls) / max(tot, 1.0)
            loss.backward()
            sa_sum += float(la)
            ss_sum += float(ls)
        gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sched.step()
        step += 1
        hist.append((sa_sum / max(tot, 1.0), ss_sum / max(tot, 1.0)))
        if step % 50 == 0 or step == n_steps:
            h = np.array(hist[-50:])
            log(f"step {step}/{n_steps} kl_al {h[:, 0].mean():.4f} kl_sc {h[:, 1].mean():.4f} gn {float(gn):.2f} lr {sched.get_last_lr()[0]:.2e} "
                f"wins {B} Lw {Lw / SR:.1f}s mask {tot / (B * a.shape[1]):.2f} {(time.time() - t0) / max(1, step - start):.3f}s/step "
                f"mem {torch.cuda.max_memory_allocated() / 2 ** 30:.1f}G")
        if (step % 250 == 0 or step in pass_end) and step < n_steps:
            save()
        if step >= n_steps:
            break
    torch.save({"model": st.state_dict(), "step": step, "init": INIT}, f"{out}/final.pt")
    dk = S.dev_kl(st, device)
    json.dump({"init": INIT, "steps": step, "passes": n_pass, "params": S.n_params(st), "train_sec": round(time.time() - t0), "dev_kl": dk,
               "last_kl": np.mean(hist[-200:], axis=0).tolist() if hist else None, "chunk": {"C": C_S, "L": L_S, "R": R_RANGE, "p_full": P_FULL,
               "short": SHORT_RANGE}}, open(f"{out}/train_summary.json", "w"), indent=1)
    log("TRAIN_OK", INIT, json.dumps(dk))


def cmd_export():
    orig = S.build_student
    S.build_student = lambda init, device="cpu": orig("H" if init == INIT else init, device)
    S.cmd_export(INIT)


def cmd_selftest():
    """가짜 풀(항목 길이 여러 개)로 창 자르기·프레임 맞춤·가리개 점검."""
    rng = np.random.default_rng(3)
    lens = [int(rng.integers(1, 12) * SR + rng.integers(0, 3000)) for _ in range(40)]

    class P:
        pass
    pool = P()
    pool.idx, off, foff = [], 0, 0
    for n in lens:
        nf = S.conv_len(n)
        pool.idx.append({"off": off, "n": n, "foff": foff, "nf": nf})
        off += n
        foff += nf
    pool.audio = (np.arange(off) % 30000).astype(np.int16)
    tal = np.zeros((foff, V), dtype=np.float16)
    for it_i, it in enumerate(pool.idx):                 # 목표의 0번 칸 = 항목 번호, 1번 칸 = 항목 안 프레임 번호
        tal[it["foff"]:it["foff"] + it["nf"], 0] = it_i
        tal[it["foff"]:it["foff"] + it["nf"], 1] = np.arange(it["nf"])
    seg, starts, batches = pass_windows(pool.idx, 0)
    n_win, n_masked, n_frames = 0, 0, 0
    for b in batches:
        for w in b:
            x, ta, ts, mk = window_target(seg, starts, w, pool, tal, tal)
            pos, Lw, Rn = w
            assert len(x) == Lw and ta.shape[0] == S.conv_len(Lw)
            for f in np.nonzero(mk)[0]:
                s = pos + HOP * f
                j = int(np.searchsorted(starts, s, side="right") - 1)
                it_i, n = seg[j]
                assert int(ta[f, 0]) == it_i, (f, ta[f, 0], it_i)
                assert int(ta[f, 1]) == (s - starts[j]) // HOP
                assert s + 400 <= starts[j] + n
            n_win += 1
            n_masked += int(mk.sum())
            n_frames += len(mk)
    log("S4C_SELFTEST_OK windows", n_win, "batches", len(batches), "mask_frac", round(n_masked / max(1, n_frames), 3))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    if a.cmd == "data":
        S.cmd_data(a.quick)
    elif a.cmd == "teacher":
        cmd_teacher()
    elif a.cmd == "train":
        cmd_train(a.steps)
    elif a.cmd == "export":
        cmd_export()
    elif a.cmd == "selftest":
        cmd_selftest()
    else:
        sys.exit(f"알 수 없는 명령 {a.cmd}")
