"""목소리별 대조 측정(docs/listen-voice-contrast-2026-10.md 2절): wav2vec2 한국어 CTC(kresnik, 음절 vocab)로 같은 클립을
의도한 글과 경쟁 글로 각각 CTC 점수(모든 정렬을 더한 로그우도, log P(글 | 소리))를 매긴다. 파드(GPU)에서 돈다.

    python contrast_score.py TARGETS.jsonl OUT.jsonl --clips DIR [--wav-map MAP.json] [--selftest]

TARGETS는 scripts/listen_contrast_targets.py 결과(줄마다 {uid, voice, text, clip, comps}). 소리는 DIR/<clip>.ogg를 읽는다.
--wav-map이 있으면 {uid: [[후보 이름, 소리 경로], …]}의 소리를 대신 매긴다(다시 합성한 후보).
줄마다 {uid, cand, voice, key, set, T, ll, greedy, comps: [{text, ll, margin, margin_pf, status}]}.
status: ok | unk(의도 글이나 경쟁 글에 vocab 밖 음절) | same_tokens(두 글의 토큰열이 같음, 예: 억양 짝) | inf(정렬 불가).
margin = ll(의도) − ll(경쟁), margin_pf = margin / T(같은 클립이라 T가 같아 부호는 같다). 표식 VC_SCORE_OK.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

MODEL_ID = "kresnik/wav2vec2-large-xlsr-korean"
SR = 16000


def norm_text(text):
    """앱 dgop_acoustic.normalize_syllable_text와 같다: 한글 음절과 공백만."""
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]", " ", text or "")).strip()


def decode(path):
    """ffmpeg로 16 kHz 모노 float32."""
    p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


class Judge:
    def __init__(self, device, load_model=True):
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        self.torch = torch
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        self.proc = Wav2Vec2Processor.from_pretrained(MODEL_ID)
        # load_model=False는 토크나이저·점수 함수만 시험할 때(맥에서 모델 추론을 하지 않는다)
        self.model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID).to(device).eval() if load_model else None
        self.device = device
        self.vocab = self.proc.tokenizer.get_vocab()
        self.id2tok = {v: k for k, v in self.vocab.items()}
        self.blank = self.vocab["[PAD]"]          # 앱 dgop_acoustic.blank_id_for와 같은 blank
        self.unk = self.vocab.get("[UNK]")

    def ids(self, text):
        t = norm_text(text)
        if not t:
            return None
        ids = self.proc.tokenizer(t).input_ids
        if not ids or (self.unk is not None and self.unk in ids):
            return None
        return ids

    def log_probs(self, wav):
        torch = self.torch
        with torch.no_grad():
            x = self.proc(wav, sampling_rate=SR, return_tensors="pt").input_values.to(self.device)
            logits = self.model(x).logits[0].float().cpu()
        return torch.log_softmax(logits.double(), dim=-1)

    def ll(self, lp, ids):
        """log P(ids | 소리), CTC 순방향(모든 정렬의 합). 정렬할 수 없으면 -inf."""
        torch = self.torch
        T = lp.shape[0]
        nll = torch.nn.functional.ctc_loss(lp.unsqueeze(1), torch.tensor([ids], dtype=torch.long), [T], [len(ids)],
                                           blank=self.blank, reduction="sum", zero_infinity=False)
        v = -float(nll)
        return v if math.isfinite(v) else float("-inf")

    def greedy(self, lp):
        best = lp.argmax(-1).tolist()
        out, prev = [], None
        for i in best:
            if i != prev and i != self.blank:
                out.append(self.id2tok.get(i, ""))
            prev = i
        return "".join(out).replace("|", " ").strip()

    def score(self, wav, text, comps):
        lp = self.log_probs(wav)
        T = int(lp.shape[0])
        mine = self.ids(text)
        ll0 = self.ll(lp, mine) if mine else None
        rows = []
        for c in comps:
            other = self.ids(c["text"])
            r = {"text": c["text"]}
            if mine is None or other is None:
                r["status"] = "unk"
            elif other == mine:
                r["status"] = "same_tokens"
            else:
                l1 = self.ll(lp, other)
                r["ll"] = round(l1, 4) if math.isfinite(l1) else None
                if ll0 is None or not math.isfinite(ll0) or not math.isfinite(l1):
                    r["status"] = "inf"
                else:
                    r.update(status="ok", margin=round(ll0 - l1, 4), margin_pf=round((ll0 - l1) / T, 6))
            rows.append(r)
        return {"T": T, "ll": None if ll0 is None or not math.isfinite(ll0) else round(ll0, 4), "greedy": self.greedy(lp),
                "comps": rows}


def selftest(j):
    """합성 로그확률로 점수 함수 확인: 토큰 'A'를 강하게 내는 프레임이면 ll(A) > ll(B)."""
    torch = j.torch
    a, b = j.ids("가"), j.ids("카")
    assert a and b and a != b, (a, b)
    C = len(j.vocab)
    lp = torch.full((20, C), -20.0, dtype=torch.double)
    lp[:, j.blank] = 0.0
    lp[8:12, a[0]] = 0.0
    lp = torch.log_softmax(lp, dim=-1)
    la, lb = j.ll(lp, a), j.ll(lp, b)
    assert la > lb + 10, (la, lb)
    assert j.ids("괜") is None                 # vocab 밖 음절은 판정 불가
    assert j.ids("가요.") == j.ids("가요?")       # 억양 짝은 토큰열이 같다
    print("SELFTEST_OK", round(la, 3), round(lb, 3), "vocab", C, "blank", j.blank, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets"); ap.add_argument("out")
    ap.add_argument("--clips", required=True)
    ap.add_argument("--wav-map", default="")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-model", action="store_true", help="모델 없이 자체 시험만(맥)")
    a = ap.parse_args()
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    j = Judge(dev, load_model=not a.no_model)
    selftest(j)
    if a.selftest or a.no_model:
        return
    targets = [json.loads(l) for l in open(a.targets, encoding="utf-8") if l.strip()]
    wmap = json.load(open(a.wav_map, encoding="utf-8")) if a.wav_map else None
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                done.add((r["uid"], r["cand"]))
    out = open(a.out, "a", encoding="utf-8")
    cache = {}
    n = 0
    for t in targets:
        srcs = wmap.get(t["uid"], []) if wmap is not None else [["orig", os.path.join(a.clips, t["clip"] + ".ogg")]]
        for cand, path in srcs:
            if (t["uid"], cand) in done:
                continue
            try:
                if path not in cache:
                    cache.clear()
                    cache[path] = decode(path)
                res = j.score(cache[path], t["text"], t["comps"])
                rec = {"uid": t["uid"], "cand": cand, "voice": t["voice"], "key": t["key"], "set": t["set"], **res}
            except Exception as ex:
                rec = {"uid": t["uid"], "cand": cand, "voice": t["voice"], "key": t["key"], "set": t["set"],
                       "err": f"{type(ex).__name__}: {ex}"[:300]}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            n += 1
    print(f"VC_SCORE_OK n={n} device={dev}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
