"""파드: 608 도메인 적응 학습(docs/dgop-608-adapt-2026-10.md 4절).

    python train.py --mode ctc|joint|aligner --init INT8_DIR --fold F1|F2 --lr LR [--lam L] --seed S --out OUT_DIR [--steps 2000]

- 시작점: 지금 앱 int8 폴더를 fp32로 푼 모델(Int8Linear → nn.Linear, 가중치 = qweight × scale). 앱이 쓰는 모델과 값이 같다.
- 한 단계 = Zeroth train 8발화 + 608 자료 8개(범주 28 5개 + 범주 21·24 3개). 손실 = Zeroth 손실 + 608 손실.
  ctc: 608 유라벨 조각 CTC(대본). aligner: ctc와 같고 Zeroth 쪽에 저하 강도 0~4(A-2 레시피). joint: 608 무라벨 덩어리의 wav2vec 2.0
  대조 손실 × λ(XLSR-53 양자화기·project_q 얼림, project_hid 학습).
- CNN 특징 추출부 동결, AdamW(0.9, 0.98, 감쇠 0), 10% 선형 예열 뒤 선형 감소, bf16, 기울기 1.0 자르기, 기울기 체크포인트.
끝나면 OUT_DIR에 fp32(save_pretrained)와 train_log.json을 둔다. int8 변환은 scripts/export_int8.py.
"""
import argparse
import json
import math
import os
import random
import sys
import time

import numpy as np
import soundfile as sf
import torch
from torch import nn

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("AD_ROOT", os.path.abspath(os.path.join(HERE, "..")))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import jamo_vocab as V  # noqa: E402

SR = 16000
N_Z, N_28, N_C = 8, 5, 3


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def dequant_model(int8_dir):
    import quant_int8 as Q
    m = Q.load_ctc(int8_dir)
    n = 0
    for parent_name, parent in list(m.named_modules()):
        for name, child in list(parent.named_children()):
            if isinstance(child, Q.Int8Linear):
                lin = nn.Linear(child.in_features, child.out_features, bias=child.bias is not None)
                with torch.no_grad():
                    lin.weight.copy_(child.qweight.float() * child.scale[:, None])
                    if child.bias is not None:
                        lin.bias.copy_(child.bias)
                setattr(parent, name, lin)
                n += 1
    for p in m.parameters():
        p.requires_grad_(True)
    m.liplab_quant = None
    return m, n


class WavList(torch.utils.data.Dataset):
    def __init__(self, rows, proc, labeled):
        self.rows, self.proc, self.labeled = rows, proc, labeled

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        y, sr = sf.read(os.path.join(ROOT, r["path"]), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        x = self.proc(y, sampling_rate=SR).input_values[0]
        out = {"input_values": x}
        if self.labeled:
            out["labels"] = V.text_to_ids(r["text"])
        return out


class ZerothSet(torch.utils.data.Dataset):
    def __init__(self, proc, severities, seed):
        import datasets as ds_lib
        from datasets import load_dataset
        self.ds = load_dataset("kresnik/zeroth_korean", split="train").cast_column("audio", ds_lib.Audio(sampling_rate=SR))
        self.proc, self.sevs, self.seed = proc, list(severities), seed
        self._rng = {}

    def __len__(self):
        return len(self.ds)

    def __getitem__(self, i):
        import hf_audio
        r = self.ds[int(i)]
        y = hf_audio.to_waveform(r["audio"])
        if self.sevs != [0]:
            import deaf_speech_synthesis as DSS
            pid = os.getpid()
            rng = self._rng.setdefault(pid, np.random.default_rng([self.seed, pid]))
            sev = int(rng.choice(self.sevs))
            if sev:
                try:
                    y = DSS.simulate_deaf_speech(y, SR, sev, rng=rng)
                except Exception:
                    pass
        return {"input_values": self.proc(y, sampling_rate=SR).input_values[0], "labels": V.text_to_ids(r["text"])}


def collate_fn(proc, labeled):
    def f(feats):
        b = proc.pad([{"input_values": x["input_values"]} for x in feats], padding=True, return_tensors="pt", return_attention_mask=True)
        if labeled:
            lab = proc.pad(labels=[{"input_ids": x["labels"]} for x in feats], padding=True, return_tensors="pt")
            b["labels"] = lab["input_ids"].masked_fill(lab.attention_mask.ne(1), -100)
        return dict(b)
    return f


def forever(ds, bs, proc, labeled, seed, workers):
    g = torch.Generator()
    g.manual_seed(seed)
    ep = 0
    while True:
        dl = torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=True, generator=g, num_workers=workers, drop_last=True,
                                         collate_fn=collate_fn(proc, labeled), persistent_workers=False, prefetch_factor=4 if workers else None)
        for b in dl:
            yield b
        ep += 1


def to_dev(b, dev):
    return {k: v.to(dev) for k, v in b.items()}


def cat_batches(a, b, proc, labeled):
    """두 묶음(범주 28, 범주 21·24)을 한 묶음으로(가장 긴 것에 맞춰 다시 덧댄다)."""
    L = max(a["input_values"].shape[1], b["input_values"].shape[1])

    def padto(t, n, v):
        return torch.nn.functional.pad(t, (0, n - t.shape[1]), value=v)
    out = {"input_values": torch.cat([padto(a["input_values"], L, 0.0), padto(b["input_values"], L, 0.0)]),
           "attention_mask": torch.cat([padto(a["attention_mask"], L, 0), padto(b["attention_mask"], L, 0)])}
    if labeled:
        M = max(a["labels"].shape[1], b["labels"].shape[1])
        out["labels"] = torch.cat([padto(a["labels"], M, -100), padto(b["labels"], M, -100)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["ctc", "joint", "aligner"])
    ap.add_argument("--init", required=True)
    ap.add_argument("--fold", required=True)
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--lam", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--warmup-frac", type=float, default=0.10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--xlsr", default="facebook/wav2vec2-large-xlsr-53")
    a = ap.parse_args()
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    dev = "cuda"
    from transformers import Wav2Vec2Processor, get_linear_schedule_with_warmup
    proc = Wav2Vec2Processor.from_pretrained(a.init)
    model, n_lin = dequant_model(a.init)
    model.config.ctc_zero_infinity = True
    model.freeze_feature_encoder()
    model.gradient_checkpointing_enable()
    model.to(dev).train()
    log(f"init {a.init} (int8 → fp32 선형층 {n_lin}개), mode {a.mode}, fold {a.fold}, lr {a.lr}, lam {a.lam}, seed {a.seed}, steps {a.steps}")

    kind = "unl" if a.mode == "joint" else "lab"
    rows = [json.loads(l) for l in open(f"{ROOT}/data/train/{a.fold}_{kind}.jsonl", encoding="utf-8")]
    r28 = [r for r in rows if r["cat"] == 28]
    rc = [r for r in rows if r["cat"] != 28]
    log(f"608 {kind}: 범주 28 {len(r28)}개 {sum(r['dur'] for r in r28) / 3600:.2f}시간, 범주 21·24 {len(rc)}개 {sum(r['dur'] for r in rc) / 3600:.2f}시간")
    labeled = kind == "lab"
    w = max(1, a.workers)
    it28 = forever(WavList(r28, proc, labeled), N_28, proc, labeled, a.seed * 1000 + 1, w)
    itc = forever(WavList(rc, proc, labeled), N_C, proc, labeled, a.seed * 1000 + 2, w)
    sevs = [0, 1, 2, 3, 4] if a.mode == "aligner" else [0]
    itz = forever(ZerothSet(proc, sevs, a.seed), N_Z, proc, True, a.seed * 1000 + 3, w * 2)

    params = [p for p in model.parameters() if p.requires_grad]
    pt = None
    if a.mode == "joint":
        from transformers import Wav2Vec2ForPreTraining
        from transformers.models.wav2vec2.modeling_wav2vec2 import _compute_mask_indices, _sample_negative_indices
        pt = Wav2Vec2ForPreTraining.from_pretrained(a.xlsr)
        fe_same = all(torch.equal(p.detach().cpu(), q.detach().cpu()) for p, q in
                      zip(pt.wav2vec2.feature_extractor.parameters(), model.wav2vec2.feature_extractor.parameters()))
        log(f"XLSR-53 CNN 특징 추출부와 채점기 특징 추출부 같음: {fe_same}")
        pt.wav2vec2 = model.wav2vec2
        pt.to(dev)
        for m in (pt.quantizer, pt.project_q):
            m.eval()
            for p in m.parameters():
                p.requires_grad_(False)
        pt.project_hid.train()
        params += list(pt.project_hid.parameters())
        cfg = pt.config
        log(f"대조: 음성 표본 {cfg.num_negatives}, 온도 {cfg.contrastive_logits_temperature}, 가리기 0.65·10")
    opt = torch.optim.AdamW(params, lr=a.lr, betas=(0.9, 0.98), eps=1e-8, weight_decay=0.0)
    sch = get_linear_schedule_with_warmup(opt, int(a.steps * a.warmup_frac), a.steps)
    hist, t0 = [], time.time()
    acc = {"z": 0.0, "l": 0.0, "n": 0, "skip": 0}
    for step in range(1, a.steps + 1):
        zb = to_dev(next(itz), dev)
        lb = to_dev(cat_batches(next(it28), next(itc), proc, labeled), dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            lz = model(**zb).loss
            if a.mode == "joint":
                B, L = lb["input_values"].shape
                T = int(model.wav2vec2._get_feat_extract_output_lengths(L))
                sub = model.wav2vec2._get_feature_vector_attention_mask(T, lb["attention_mask"])
                mask = _compute_mask_indices((B, T), mask_prob=0.65, mask_length=10, attention_mask=sub.cpu(), min_masks=2)
                neg = _sample_negative_indices((B, T), cfg.num_negatives, mask_time_indices=mask)
                mt = torch.tensor(mask, device=dev, dtype=torch.bool)
                out = pt(lb["input_values"], attention_mask=lb["attention_mask"], mask_time_indices=mt,
                         sampled_negative_indices=torch.tensor(neg, device=dev, dtype=torch.long))
                ll = out.contrastive_loss / mt.sum().clamp(min=1)
                loss = lz + a.lam * ll
            else:
                ll = model(**lb).loss
                loss = lz + ll
        if not torch.isfinite(loss):
            acc["skip"] += 1
            opt.zero_grad(set_to_none=True)
            sch.step()
            continue
        loss.backward()
        gn = torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        sch.step()
        opt.zero_grad(set_to_none=True)
        acc["z"] += float(lz)
        acc["l"] += float(ll)
        acc["n"] += 1
        if step % 25 == 0 or step == a.steps:
            n = max(1, acc["n"])
            h = {"step": step, "loss_zeroth": round(acc["z"] / n, 4), "loss_608": round(acc["l"] / n, 4), "lr": sch.get_last_lr()[0],
                 "grad_norm": round(float(gn), 3), "skipped": acc["skip"], "sec": round(time.time() - t0, 1)}
            hist.append(h)
            log(json.dumps(h))
            acc = {"z": 0.0, "l": 0.0, "n": 0, "skip": acc["skip"]}
    model.eval()
    os.makedirs(a.out, exist_ok=True)
    model.config.ctc_zero_infinity = False      # 앱 설정 그대로 저장(추론에는 영향 없음)
    model.save_pretrained(a.out)
    proc.save_pretrained(a.out)
    json.dump({"args": vars(a), "n_rows_28": len(r28), "n_rows_c": len(rc), "hist": hist, "sec": round(time.time() - t0, 1)},
              open(f"{a.out}/train_log.json", "w"), indent=1)
    log(f"TRAIN_OK {a.out} {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
