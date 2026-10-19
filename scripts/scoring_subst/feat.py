"""발음 바꿈(대치) 잡기 특성 계산(docs/scoring-subst-2026-10.md 5절). 판정·집계는 하지 않는다(model.py).

지금 앱 경로(이 브랜치 backend, int8, CPU 2스레드, 끝 자르기·끝 구간 다시 나누기 기본 켬)로 목표마다 assess_text를 부르고
(클립마다 순전파 한 번, scripts/scoring_rules/feat_pod.py의 메모 방식 그대로), 같은 순전파에서 다음을 남긴다.
  - 목표 행: 앱 점수(score·raw), 종류(own·min·min2·splice_*·tts_*), 바꾼 자리(tok_idx)
  - 자리 행(후보 A·B): common.eligible_positions의 자리마다 common.position_features, 정답 라벨 y(바꾼 자리면 1)
  - 숨은 상태(후보 C): 채점기 lm_head 입력(마지막 층)의 구간 평균과 앞뒤 3프레임을 더한 평균, float16, OUT_hid/<clip>.npz
'other' 목표는 계산하지 않는다(보류만 하는 후보는 다른 문장 합격을 늘릴 수 없다).

  python feat.py feat JOBS OUT WORKERS [--hid]   작업 파일 → OUT(jsonl), --hid면 OUT_hid/ 폴더에 숨은 상태
  python feat.py selftest                       모델 없이 점검(common.selftest)

환경: SUB_BACKEND(백엔드 폴더, 모델은 그 아래 models/dgop_ours), PYTHONUTF8=1(Windows).
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scoring_rules"))
KINDS = ("own", "min", "min2", "splice_sub", "splice_same", "tts_own", "tts_min")
_S = {}


def _setup():
    if "D" in _S:
        return _S["D"]
    os.environ["SR_BACKEND"] = os.environ.get("SUB_BACKEND") or os.path.join(HERE, "..", "..", "backend")
    import feat_pod as FP
    FP.BK = os.environ["SR_BACKEND"]
    D = FP._setup()
    import backbone_service as bb
    import torch
    sc = os.environ["DGOP_SCORER_ID"]
    _proc, model = bb.load(sc, "ctc", "cpu")
    hid = {}

    def pre_hook(_mod, inputs):
        hid["last"] = inputs[0][0].detach().float().cpu()   # (T, H)
    model.lm_head.register_forward_pre_hook(pre_hook)
    _S.update(D=D, FP=FP, hid=hid, torch=torch)
    return D


def _job(task):
    root, job, want_hid = task
    import numpy as np
    import common as C
    D = _setup()
    FP, torch = _S["FP"], _S["torch"]
    FP._S["memo"].clear()
    _S["hid"].pop("last", None)
    al, sc = os.environ["DGOP_ALIGNER_ID"], os.environ["DGOP_SCORER_ID"]
    path = job["path"] if os.path.isabs(job["path"]) else os.path.join(root, job["path"])
    data = open(path, "rb").read()
    meta = {k: job[k] for k in ("set", "spk", "clip")}
    rows, hid_out, hidden = [], {}, None
    t_clip = time.time()
    for ti, t in enumerate(job["targets"]):
        if t["kind"] not in KINDS:
            continue
        extra = {k: t[k] for k in ("tok_idx", "cat", "voice") if k in t}
        try:
            t0 = time.time()
            r = D.assess_text(data, t["text"], aligner_id=al, scorer_id=sc)
            t_app = time.time() - t0
            if hidden is None:
                hidden = _S["hid"].get("last")
            spans = FP._S["last"]["spans"]
            lp_al, _, voc_al = FP._lp_of(al)
            lp_sc, _, voc_sc = FP._lp_of(sc)
            toks = [s["token"] for s in spans]
            phones = r.get("phones") or []
            assert [p["token"] for p in phones] == toks
            t1 = time.time()
            base = {"sc": C.ctc_ll_batch(lp_sc, [[voc_sc[x] for x in toks]], D.blank_id_for(voc_sc), torch)[0],
                    "al": C.ctc_ll_batch(lp_al, [[voc_al[x] for x in toks]], D.blank_id_for(voc_al), torch)[0]}
            cache, pos = {}, []
            swapped = set(t.get("tok_idx") if isinstance(t.get("tok_idx"), list) else
                          ([t["tok_idx"]] if t.get("tok_idx") is not None else []))
            elig = C.eligible_positions(toks, phones)
            for i in elig:
                f = C.position_features(i, toks, spans, phones, lp_sc, voc_sc, lp_al, voc_al, base, cache,
                                        D.blank_id_for(voc_sc), D.blank_id_for(voc_al), torch)
                y = 1 if (i in swapped and t["kind"] in ("min", "min2", "splice_sub", "tts_min")) else 0
                pos.append({"i": i, "tok": toks[i][2:], "y": y, **f})
                if want_hid and hidden is not None:
                    s, e = spans[i]["start"], spans[i]["end"]
                    lo, hi = max(0, s - 3), min(hidden.shape[0], e + 4)
                    hid_out[f"{ti}_{i}"] = np.concatenate([hidden[s:e + 1].mean(0).numpy(), hidden[lo:hi].mean(0).numpy()]).astype(np.float16)
            rows.append({"rec": "t", **meta, "ti": ti, "target": t["text"], "kind": t["kind"], **extra, "score": r.get("score"),
                         "raw": r.get("raw_score"), "T": int(lp_sc.shape[0]), "n_tok": len(toks), "n_elig": len(elig),
                         "swapped_elig": sorted(set(swapped) & set(elig)), "t_app": round(t_app, 3), "t_feat": round(time.time() - t1, 3),
                         "pos": pos})
        except Exception as e:
            rows.append({"rec": "t", **meta, "ti": ti, "target": t["text"], "kind": t["kind"], **extra, "error": f"{type(e).__name__}: {e}"})
    rows.append({"rec": "clip", **meta, "sec": round(time.time() - t_clip, 2)})
    return rows, hid_out


def cmd_feat(jobs_path, out, workers, want_hid):
    import numpy as np
    root = os.path.dirname(os.path.abspath(jobs_path))
    jobs = json.load(open(jobs_path, encoding="utf-8"))
    done = set()
    if os.path.exists(out):
        for line in open(out, encoding="utf-8"):
            j = json.loads(line)
            if j.get("rec") == "clip":
                done.add(j["clip"])
    hdir = out + "_hid"
    if want_hid:
        os.makedirs(hdir, exist_ok=True)
    todo = [j for j in jobs if j["clip"] not in done]
    t0 = time.time()
    with open(out, "a", encoding="utf-8") as fo, ProcessPoolExecutor(workers) as ex:
        for k, (rows, hid) in enumerate(ex.map(_job, [(root, j, want_hid) for j in todo], chunksize=1), 1):
            if want_hid and hid:
                np.savez(os.path.join(hdir, rows[-1]["clip"].replace(":", "_") + ".npz"), **hid)
            for x in rows:
                fo.write(json.dumps(x, ensure_ascii=False) + "\n")
            fo.flush()
            if k % 25 == 0 or k == len(todo):
                print(f"SUBFEAT {os.path.basename(jobs_path)} {k}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    print(f"SUBFEAT_DONE {os.path.basename(jobs_path)} clips={len(jobs)} new={len(todo)} {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "feat":
        cmd_feat(a[1], a[2], int(a[3]), "--hid" in a)
    elif a and a[0] == "selftest":
        import common
        common.selftest()
    else:
        print(__doc__)
        sys.exit(2)
