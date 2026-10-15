"""파드: 문장 점수 규칙 후보의 특성 계산(docs/scoring-rules-2026-10.md 3절). 점수를 판정하는 단계는 없다(집계·판정은 맥 analyze.py).

지금 앱 경로(이 브랜치 backend, int8, CPU 2스레드, 끝 자르기·끝 구간 다시 나누기 기본 켬)로 assess_text를 부르고, 같은 순전파에서 다음을 더 남긴다.
  - 앱 점수(score·raw)와 음소별 dgop(목표 사후확률)
  - 음소마다 같은 종류(초성·중성·종성) 안에서 목표가 아닌 토큰 가운데 구간 평균 사후확률이 가장 큰 것과 그 확률(채점기 분포)
  - 채점기·정렬기 각각: 목표 토큰열의 CTC 로그 우도(모든 정렬 합), 프레임마다 최댓값을 더한 최선 경로 로그 확률, 프레임 수
  - 클립마다 채점기·정렬기의 탐욕 해독 토큰열(빈칸·반복을 지운 것)

  python feat_pod.py feat JOBS OUT W      작업 파일(맥 build_stage.py 또는 b2jobs) → OUT(jsonl)
  python feat_pod.py b2prep               c27b2/s608 FLAC + labels → c27b2/s608/meta.json(cut_608 입력)
  python feat_pod.py b2jobs               c27b2/out/cuts608.json → 등록 2절 고르기 → jobs_b2.json
  python feat_pod.py selftest             모델 없이 순수 함수 점검
"""
import glob
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

W = os.environ.get("SR_W", "/workspace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BK = os.environ.get("SR_BACKEND", f"{W}/backend")
_S = {}


def greedy(ids, blank=0):
    """프레임별 최댓값 id열 → 반복을 합치고 빈칸을 지운 id열(CTC 탐욕 해독)."""
    out, prev = [], None
    for i in ids:
        if i != prev and i != blank:
            out.append(i)
        prev = i
    return out


def best_other(dist, token, vocab):
    """같은 종류(접두 o:·n:·c:) 안에서 목표가 아닌 토큰 가운데 확률이 가장 큰 것."""
    pre = token[:2]
    best, bp = None, -1.0
    for t, i in vocab.items():
        if t != token and t.startswith(pre) and dist[i] > bp:
            best, bp = t, dist[i]
    return best, bp


def _setup():
    if "D" in _S:
        return _S["D"]
    os.environ.update(DGOP_ALIGNER_ID=f"{BK}/models/dgop_ours/aligner", DGOP_SCORER_ID=f"{BK}/models/dgop_ours/scorer",
                      DGOP_CALIBRATION=f"{BK}/data/dgop_calibration_ours.json", BACKBONE_QUANT="int8", HF_HUB_OFFLINE="1",
                      CUDA_VISIBLE_DEVICES="", LIPLAB_CONTENT_WARMUP="0", DGOP_DEVICE="cpu")
    for k in ("DGOP_TAIL_TRIM", "DGOP_TAIL_RESEG"):
        os.environ.pop(k, None)                      # 앱 기본값(둘 다 켬)
    sys.path.insert(0, BK)
    import numpy as np
    import torch
    torch.set_num_threads(2)
    import dgop_acoustic as D
    orig = D.ctc_outputs
    memo = {}

    def memo_outputs(waveform, sample_rate, model_id=D.DEFAULT_MODEL_ID):
        key = (model_id, int(sample_rate), hashlib.sha1(np.ascontiguousarray(waveform).tobytes()).hexdigest())
        if key not in memo:
            memo[key] = orig(waveform, sample_rate, model_id)
        return memo[key]
    D.ctc_outputs = memo_outputs                     # 클립마다 순전파 한 번(채점 함수는 그대로)
    orig_align = D.align_targets
    last = {}

    def align_capture(log_probs, vocab, target_tokens, blank_token=None):
        sp = orig_align(log_probs, vocab, target_tokens, blank_token)
        last["spans"] = sp
        return sp
    D.align_targets = align_capture                  # 앱이 채점에 쓴 정렬 구간을 그대로 받는다
    _S.update(D=D, memo=memo, last=last, torch=torch)
    return D


def _lp_of(model_id):
    hits = [v for k, v in _S["memo"].items() if k[0] == model_id]
    assert len(hits) == 1, (model_id, len(hits))
    return hits[0]


def _ll(lp, ids, torch):
    T = int(lp.shape[0])
    best = float(lp.max(dim=-1).values.sum())
    if not ids:
        return None, best
    loss = torch.nn.functional.ctc_loss(lp.unsqueeze(1).float(), torch.tensor([ids], dtype=torch.long), torch.tensor([T]),
                                        torch.tensor([len(ids)]), blank=0, reduction="sum", zero_infinity=False)
    v = float(loss)
    return (None if v != v or v == float("inf") else -v), best


def _job(task):
    root, job = task
    D = _setup()
    torch = _S["torch"]
    _S["memo"].clear()
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    path = job["path"] if job["path"].startswith("/") else f"{root}/{job['path']}"
    data = open(path, "rb").read()
    meta = {k: job[k] for k in ("set", "spk", "clip")}
    rows, clip_rec = [], None
    for t in job["targets"]:
        extra = {k: t[k] for k in ("tok_idx", "cat") if k in t}
        try:
            r = D.assess_text(data, t["text"], aligner_id=al, scorer_id=sc)
            spans = _S["last"]["spans"]
            lp_al, _, voc_al = _lp_of(al)
            lp_sc, _, voc_sc = _lp_of(sc)
            toks = [s["token"] for s in spans]
            ph = []
            for p, s in zip(r.get("phones") or [], spans):
                assert p["token"] == s["token"]
                q = {k: p.get(k) for k in ("token", "aligned", "scorable", "silent_h", "dgop") if k in p}
                if p.get("aligned") and p.get("scorable") and s["token"] in voc_sc:
                    dist = D.span_distribution(lp_sc, s["start"], s["end"])
                    bt, bp = best_other(dist, s["token"], voc_sc)
                    q["cmp"] = [bt, round(bp, 4)]
                ph.append(q)
            ll = {}
            for name, lp, voc in (("sc", lp_sc, voc_sc), ("al", lp_al, voc_al)):
                ids = [voc[x] for x in toks if x in voc]
                c, b = _ll(lp, ids, torch)
                ll[name] = [None if c is None else round(c, 3), round(b, 3)]
            rows.append({"rec": "t", **meta, "target": t["text"], "kind": t["kind"], **extra, "score": r.get("score"),
                         "raw": r.get("raw_score"), "T": int(lp_sc.shape[0]), "ll": ll, "phones": ph})
            if clip_rec is None:
                inv_sc = {v: k for k, v in voc_sc.items()}
                inv_al = {v: k for k, v in voc_al.items()}
                clip_rec = {"rec": "clip", **meta, "T": int(lp_sc.shape[0]),
                            "g_sc": " ".join(inv_sc[i] for i in greedy(lp_sc.argmax(dim=-1).tolist(), D.blank_id_for(voc_sc))),
                            "g_al": " ".join(inv_al[i] for i in greedy(lp_al.argmax(dim=-1).tolist(), D.blank_id_for(voc_al)))}
        except Exception as e:
            rows.append({"rec": "t", **meta, "target": t["text"], "kind": t["kind"], **extra, "error": f"{type(e).__name__}: {e}"})
    if clip_rec:
        rows.append(clip_rec)
    return rows


def cmd_feat(jobs_path, out, workers):
    root = os.path.dirname(os.path.abspath(jobs_path))
    jobs = json.load(open(jobs_path, encoding="utf-8"))
    done = set()
    if os.path.exists(out):                          # 이어서(끊겼을 때)
        for l in open(out, encoding="utf-8"):
            j = json.loads(l)
            if j.get("rec") == "clip" or j.get("rec") == "end":
                done.add(j["clip"])
    todo = [j for j in jobs if j["clip"] not in done]
    t0 = time.time()
    with open(out, "a") as fo, ProcessPoolExecutor(workers) as ex:
        for k, rows in enumerate(ex.map(_job, [(root, j) for j in todo], chunksize=1), 1):
            for x in rows:
                fo.write(json.dumps(x, ensure_ascii=False) + "\n")
            if not any(x.get("rec") == "clip" for x in rows):
                fo.write(json.dumps({"rec": "end", "clip": rows[0]["clip"] if rows else None}, ensure_ascii=False) + "\n")
            fo.flush()
            if k % 50 == 0:
                print(f"FEAT {os.path.basename(jobs_path)} {k}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"FEAT_DONE {os.path.basename(jobs_path)} clips={len(jobs)} new={len(todo)} {time.time() - t0:.0f}s", flush=True)


def cmd_b2prep():
    d = f"{W}/c27b2"
    meta = []
    for f in sorted(glob.glob(f"{d}/s608/*.flac")):
        b = os.path.basename(f)[:-5]
        t = json.load(open(f"{d}/labels/{b}.json", encoding="utf-8"))["Transcript"]
        meta.append({"file": f"{b}.flac", "transcript": t})
    json.dump(meta, open(f"{d}/s608/meta.json", "w"), ensure_ascii=False)
    print("B2PREP_OK", len(meta), flush=True)


def cmd_b2jobs():
    import targets as TG
    sys.path.insert(0, BK)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import jamo_vocab as JV
    d = f"{W}/c27b2"
    cuts = json.load(open(f"{d}/out/cuts608.json", encoding="utf-8"))
    kept, info = TG.select_c27(cuts)
    jobs = TG.c27_jobs(kept, JV, lambda c: c["cut"], "c27b2")
    json.dump(jobs, open(f"{W}/jobs_b2.json", "w"), ensure_ascii=False)
    from collections import Counter
    print("B2_SELECT", json.dumps(info, ensure_ascii=False), flush=True)
    print("B2_JOBS", len(jobs), dict(Counter(t["kind"] for j in jobs for t in j["targets"])), flush=True)
    print("B2JOBS_OK", flush=True)


def cmd_selftest():
    assert greedy([0, 3, 3, 0, 3, 5, 5, 0, 0, 2]) == [3, 3, 5, 2]
    voc = {"<pad>": 0, "o:ㄱ": 1, "o:ㄴ": 2, "n:ㅏ": 3, "n:ㅓ": 4}
    assert best_other([0.1, 0.2, 0.5, 0.15, 0.05], "o:ㄱ", voc) == ("o:ㄴ", 0.5)
    assert best_other([0.1, 0.2, 0.5, 0.15, 0.05], "n:ㅏ", voc) == ("n:ㅓ", 0.05)
    try:
        import torch
        lp = torch.log_softmax(torch.randn(20, 5), dim=-1)
        c, b = _ll(lp, [1, 3, 2], torch)
        assert c is not None and c <= 0 and b <= 0
        lp2 = torch.full((6, 5), -20.0)
        for f, i in enumerate([1, 1, 0, 3, 3, 2]):
            lp2[f, i] = 0.0
        c2, b2 = _ll(torch.log_softmax(lp2, -1), [1, 3, 2], torch)
        assert abs(c2 - b2) < 1e-3, (c2, b2)
    except ImportError:
        pass
    print("SR_SELFTEST_OK", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "feat":
        cmd_feat(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 2)
    else:
        {"b2prep": cmd_b2prep, "b2jobs": cmd_b2jobs, "selftest": cmd_selftest}[cmd]()
