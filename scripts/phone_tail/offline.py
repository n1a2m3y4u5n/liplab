"""저장된 로그확률로 후보 칩 값을 다시 계산한다(맥, 모델 추론 없음). docs/phone-tail-2026-10.md 4절.

    python offline.py s2   LP_DIR JOBS SET OUT_DIR [--prefix 538_] [--cands K,W3,...]
        S2 작업 목록(jobs.jsonl)의 SET(A0|A1) 클립마다 원래 목표 + 대치 목표 + 생략 모사 목표를 채점해, 후보마다
        OUT_DIR/<후보>/run.0.jsonl(S2 measure.py와 같은 형식, 생략 모사는 "ins" 키)을 쓴다.
    python offline.py dgop LP_DIR DGOP_FULL OUT_DIR [--cands ...]
        10/6 dgop_full.jsonl의 608 자기 문장·짝 세션(pair) 줄을 후보 칩 값으로 바꿔 OUT_DIR/<후보>/dgop.jsonl에 쓴다(재검사 카파·608 빨강용).

LP_DIR의 npz는 키 al(정렬기)·sc(채점기) 로그확률(float16)이다. 10/6 CPU int8(scores_1006.py)과 이번 파드(measure_lp.py)가 같은 형식이다.
"""
import argparse
import json
import os
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(APP, "backend"))
sys.path.insert(0, HERE)
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
import torch  # noqa: E402

import dgop_acoustic as DA  # noqa: E402
import jamo_vocab as JV  # noqa: E402
import chipval as CV  # noqa: E402

VOCAB_PATH = os.path.expanduser("~/Downloads/LIPLAB_ALL/liplab-lab/models/dgop_ours_2026-09-25_int8/aligner/vocab.json")
VOCAB = json.load(open(VOCAB_PATH, encoding="utf-8"))
INS_ONSETS = "ㄱㄴㄷㅁㅂㅅㅈ"
INS_NUCLEI = "ㅏㅓㅗㅜㅣ"
K_INS = 2


def disp(x):
    return None if x is None else int(np.floor(100.0 * x + 0.5))


def load_lp(path):
    z = np.load(path)
    return z["al"].astype(np.float32), z["sc"].astype(np.float32)


def score_all(lp, sp, toks, cands, silent=()):
    spans = DA.align_targets(torch.from_numpy(lp), VOCAB, toks)
    scorable = [DA._is_scorable(t) for t in toks]
    return {c: CV.chip_values(sp, spans, toks, VOCAB, scorable, c) for c in cands}


def syllable_starts(toks):
    out = []
    for i, t in enumerate(toks):
        if t.startswith("o:") or (t.startswith("n:") and (i == 0 or not toks[i - 1].startswith("o:"))):
            out.append(i)
    return out


def insertions(clip, toks, fs):
    """생략 모사: 화자가 내지 않은 CV 음절 하나를 목표에 끼운다(음절 경계, 첫 음절 뒤 ~ 끝 음절 앞). 난수 시드 crc32('ins|' + 클립)."""
    pos = [i for i in syllable_starts(toks) if 0 < i < fs]
    rng = np.random.default_rng(zlib.crc32(("ins|" + clip).encode()))
    if not pos:
        return []
    pick = rng.choice(pos, size=min(K_INS, len(pos)), replace=False)
    out = []
    for i in sorted(int(x) for x in pick):
        on = "o:" + INS_ONSETS[int(rng.integers(len(INS_ONSETS)))]
        nu = "n:" + INS_NUCLEI[int(rng.integers(len(INS_NUCLEI)))]
        out.append((i, toks[:i] + [on, nu] + toks[i:]))
    return out


def cmd_s2(a):
    cands = a.cands.split(",")
    jobs = [json.loads(l) for l in open(a.jobs, encoding="utf-8")]
    jobs = [j for j in jobs if j["set"] == a.set]
    fhs = {}
    for c in cands:
        os.makedirs(f"{a.out}/{c}", exist_ok=True)
        fhs[c] = open(f"{a.out}/{c}/run.0.jsonl", "w", encoding="utf-8")
    n = 0
    for j in jobs:
        p = f"{a.lp}/{a.prefix}{j['clip']}.npz"
        recs = {c: {"set": j["set"], "clip": j["clip"], "spk": j["spk"]} for c in cands}
        if not os.path.exists(p):
            for c in cands:
                recs[c]["error"] = "no logits"
        else:
            lp, slp = load_lp(p)
            sp = CV.softmax(slp)
            base = score_all(lp, sp, j["tokens"], cands)
            for c in cands:
                recs[c]["orig"] = [None if v is None else round(v, 4) for v in base[c]]
                recs[c]["subs"] = []
                recs[c]["ins"] = []
            for s in j["subs"]:
                toks = list(j["tokens"])
                assert toks[s["i"]] == s["x"]
                toks[s["i"]] = s["y"]
                v = score_all(lp, sp, toks, cands)
                for c in cands:
                    recs[c]["subs"].append([s["kind"], s["i"], s["y"], v[c][s["i"]], [disp(x) for x in v[c]]])
            for i, toks in insertions(j["clip"], j["tokens"], j["fs"]):
                v = score_all(lp, sp, toks, cands)
                for c in cands:
                    # 끼운 두 토큰(초성·중성)의 칩 표시 값과, 원래 토큰들의 표시 값(끼운 자리를 뺀 순서)
                    rest = [disp(x) for k, x in enumerate(v[c]) if k not in (i, i + 1)]
                    recs[c]["ins"].append([i, toks[i], toks[i + 1], disp(v[c][i]), disp(v[c][i + 1]), rest])
        for c in cands:
            fhs[c].write(json.dumps(recs[c], ensure_ascii=False) + "\n")
        n += 1
        if n % 100 == 0:
            print("S2_OFFLINE", a.set, n, len(jobs), flush=True)
    for f in fhs.values():
        f.close()
    print("S2_OFFLINE_OK", a.set, n, flush=True)


def cmd_dgop(a):
    cands = a.cands.split(",")
    fhs = {}
    for c in cands:
        os.makedirs(f"{a.out}/{c}", exist_ok=True)
        fhs[c] = open(f"{a.out}/{c}/dgop.jsonl", "w", encoding="utf-8")
    n = miss = 0
    for l in open(a.jobs, encoding="utf-8"):
        r = json.loads(l)
        if "error" in r or not ((r["set"] == "608" and r["kind"] == "same") or r["set"] == "pair"):
            continue
        p = f"{a.lp}/{r['set']}_{r['clip'].replace(':', '__')}.npz"
        toks = [ph["token"] for ph in r["phones"]]
        if not os.path.exists(p) or toks != JV.text_to_tokens(r["target"]):
            miss += 1
            continue
        lp, slp = load_lp(p)
        sp = CV.softmax(slp)
        v = score_all(lp, sp, toks, cands)
        for c in cands:
            ph = []
            for k, x in enumerate(r["phones"]):
                y = dict(x)
                if y.get("aligned") and y.get("scorable") and v[c][k] is not None:
                    y["naive"] = round(v[c][k], 4)
                ph.append(y)
            fhs[c].write(json.dumps({**{k: r[k] for k in ("set", "spk", "clip", "target", "kind")}, "phones": ph}, ensure_ascii=False) + "\n")
        n += 1
    for f in fhs.values():
        f.close()
    print("DGOP_OFFLINE_OK", n, "missing", miss, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("lp")
    ap.add_argument("jobs")
    ap.add_argument("rest", nargs="+")
    ap.add_argument("--prefix", default="538_")
    ap.add_argument("--cands", default=",".join(CV.CANDIDATES))
    a = ap.parse_args()
    if a.cmd == "s2":
        a.set, a.out = a.rest
        cmd_s2(a)
    elif a.cmd == "dgop":
        (a.out,) = a.rest
        cmd_dgop(a)
