"""소리 듣기 역치 검사 폼 C·D의 난이도 등가 측정(docs/listen-forms-cd-2026-10.md).

가상 청취자 V1(scripts/listen_virtual_listener.py, docs/listen-virtual-listener-2026-10.md)의 섞기(말소리 활성 레벨 대 소음 RMS,
소음 0.5초 먼저), 청취자 모의 셋(정상 nh, 인공와우 잡음 보코더 ci, 보청기 사용자 고주파 손실 ha), Whisper large-v3-turbo 받아쓰기,
띄어쓰기 맞춤 채점(word_score), 문장별 로지스틱 적합(SRT40)을 그대로 쓴다. 바뀐 것은 문장(네 폼 A·B·C·D와 교체 회차의 예비
문장), 목소리(검사 목소리 m3만), 소음(babble·talker2), 반복(회차마다 새 반복 번호)과 판정 규칙(문서 3절)이다.

하위 명령
  check                                        C·D와 예비 문장(RESERVE)의 구조·유사도 점검(맥, 가벼움)
  prep  --sound DIR --work W [--extra J]       목록·m3 클립·소음 둘의 float32 캐시(W/cache.npz). J = {sid: 글}(교체 회차의 새 문장)
  run   --work W --sids S|all --reps 0,1,2 [--quiet] [--procs N] [--batch 64]
                                               섞기·모의(CPU 프로세스) → 받아쓰기(GPU) → W/asr.jsonl에 덧붙임(이미 한 키는 건너뜀)
  score --work W                               W/asr.jsonl → W/scored.jsonl(V1 score와 같음)
  judge --work W --spec SPEC.json --out J.json  폼 평균 SRT40, 사전 기준 판정, 교체 계획(3절)
  report --result J.json                       문서에 붙일 표(마크다운)

SPEC: {"A": {"sids": [20개], "reps": [0, 1, 2]}, "B": …, "C": …, "D": …, "round": 0}. 오디오는 파드 작업 폴더에만 둔다.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import listen_virtual_listener as VL  # noqa: E402  (BACKEND 경로를 sys.path에 넣는다)

VOICE = "m3"
NOISES = ("babble", "talker2")
LISTENERS = VL.LISTENERS
FORMS = ("A", "B", "C", "D")
BOUND = 0.5          # 등가 경계(dB)
TARGET = 0.25        # 교체 뒤 예측 차이 목표(dB)
MAX_REPLACE = 4      # 회차마다 폼 하나에서 바꾸는 자리 수 상한(결함 문장 포함)
N_SPARE = 2          # 합성 실패에 대비해 함께 합성하는 다음 순위 자리 수
MIN_POSITIONS = 16   # 한 칸(소음 × 청취자)에서 네 폼 모두 SRT40이 정해진 자리가 이보다 적으면 그 칸은 판정 불가
ROUND_REPS = {0: (0, 1, 2), 1: (3, 4, 5), 2: (6, 7, 8)}

# 예비 문장(문서 2.3절). 자리마다 C용 하나, D용 하나. 같은 자리의 C·D 문장과 구조·어절 수가 같고, 훈련 문장·대화·앱 문장·
# P3 문장·네 폼·다른 예비 문장과 유사도 점검(build_pilot_manifest.similarity_reasons)에 걸리지 않는다. 그 폼의 다른 자리 문장과
# 내용어가 겹치지 않게 골랐다. 측정 전에 정해 커밋했고 결과를 보고 바꾸지 않는다.
RESERVE = {
    "C": ["필통 안에 지우개가 있어요.", "방금 창문을 닫고 왔어요.", "상처에 약을 발라 주세요.", "이 건물은 십 층이에요.",
          "선생님이 숙제를 내셨어요.", "요즘 감기가 많이 돌아요.", "공책을 가방에 챙겨 주세요.", "운동장을 육 분 뛰었어요.",
          "막내는 그네를 잘 타요.", "과일을 시장에서 골랐어요.", "약국 앞에서 줄을 서요.", "칼이 날카로우니 조심해서 쓰세요.",
          "소설을 앞부분만 읽었어요.", "사장님이 새 식당을 열었어요.", "방학에 캠핑하러 가요.", "다람쥐가 나무 위에 올라갔어요.",
          "아주머니는 떡을 파세요.", "피자를 세 조각 먹었어요.", "밤에는 거리가 조용해요.", "인형을 선반 위에 놓아요."],
    "D": ["가방 속에 휴지가 있어요.", "주말엔 늦잠을 자고 쉬었어요.", "국에 소금을 쳐 주세요.", "우리 강아지는 세 살이에요.",
          "아기가 장난감을 던졌어요.", "오늘따라 기침이 많이 나요.", "단추를 옷에 달아 주세요.", "음악을 구 분 들었어요.",
          "짝꿍은 한자를 잘 읽어요.", "배드민턴을 마당에서 쳤어요.", "식당 앞에서 메뉴를 봐요.", "밤이 늦었으니 얼른 주무세요.",
          "청소를 거실만 했어요.", "동네에 새 빵집이 생겼어요.", "일요일에 봉사하러 가요.", "풍선이 지붕 위에 걸렸어요.",
          "아저씨는 화분을 가꾸세요.", "양파를 두 개 썰었어요.", "아침에는 공기가 맑아요.", "사진을 액자 안에 끼워요."],
}


def base_items():
    import listen_curriculum as L
    return [{"sid": f"{f}{i + 1:02d}", "set": f, "pos": i, "text": s} for f in FORMS for i, s in enumerate(L.TEST_FORMS[f])]


def reserve_sid(form, pos, rnd):
    return f"{form}{pos + 1:02d}r{rnd}"


# ───────────────────────────── check ─────────────────────────────

def _builder():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_pilot_manifest", os.path.join(_HERE, "build_pilot_manifest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_check(a):
    import listen_curriculum as L
    B = _builder()
    here = os.path.join(VL.BACKEND, "data", "pilot", "battery_manifest.json")
    p3 = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("text"), str) and " " in x["text"].strip():
                p3.append(x["text"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(json.load(open(here, encoding="utf-8")))
    others = list(L.TRAIN_SENTENCES) + [c[k] for c in L.CONVO_ITEMS for k in ("line", "paraphrase")] + \
        list(B.training_sentences()) + p3
    sets = {f: L.TEST_FORMS[f] for f in FORMS}
    sets.update({f"{f}R": RESERVE[f] for f in RESERVE})
    names = list(sets)
    bad = []
    for f in names:
        assert len(sets[f]) == 20, f
        for i, s in enumerate(sets[f]):
            if len(s.split()) != len(L.TEST_FORMS["A"][i].split()):
                bad.append((f, i + 1, s, "어절 수"))
            if any(ch.isdigit() for ch in s):
                bad.append((f, i + 1, s, "숫자"))
            if f in ("A", "B"):
                continue
            for t in others:
                why = B.similarity_reasons(s, t)
                if why:
                    bad.append((f, i + 1, s, f"{t}: {why}"))
            for g in names:
                for j, t in enumerate(sets[g]):
                    if (g, j) == (f, i) or (names.index(g), j) < (names.index(f), i) and g not in ("A", "B"):
                        continue
                    why = B.similarity_reasons(s, t, both_ways=True)
                    if why:
                        bad.append((f, i + 1, s, f"{g}{j + 1:02d} {t}: {why}"))
    for b in bad:
        print("CHECK_BAD", *b)
    print(f"CHECK {'OK' if not bad else 'FAIL'} sets={names} problems={len(bad)}")
    return 0 if not bad else 1


# ───────────────────────────── prep / run / score ─────────────────────────────

def cmd_prep(a):
    import sound_clips as SC
    os.makedirs(a.work, exist_ok=True)
    man = json.load(open(os.path.join(a.sound, "manifest.json"), encoding="utf-8"))
    items = base_items()
    if a.extra:
        for sid, text in json.load(open(a.extra, encoding="utf-8")).items():
            items.append({"sid": sid, "set": sid[0], "pos": int(sid[1:3]) - 1, "text": text})
    clips, meta = {}, {}
    missing = []
    for it in items:
        c = man["clips"].get(VOICE, {}).get(SC.normalize_text(it["text"]))
        if not c:
            missing.append(it["sid"])
            continue
        x = VL.decode(os.path.join(a.sound, "clips", c["id"] + ".ogg"))
        k = f"{it['sid']}|{VOICE}"
        clips["c:" + k] = x.astype(np.float32)
        meta[k] = {"clip": c["id"], "ms": c["ms"], "active": VL.active_level(x, VL.SR_MIX), "rms": VL.rms(x)}
    if missing:
        sys.exit(f"PREP_FAIL m3 소리 없음: {missing}")
    for nz in NOISES:
        x = VL.decode(os.path.join(a.sound, "noise", nz + ".ogg"))
        clips["n:" + nz] = x.astype(np.float32)
        meta["noise:" + nz] = {"rms": VL.rms(x), "s": x.size / VL.SR_MIX}
    np.savez(os.path.join(a.work, "cache.npz"), **clips)
    json.dump({"items": items, "meta": meta, "engine": man.get("engine"), "voices": man.get("voices")},
              open(os.path.join(a.work, "items.json"), "w"), ensure_ascii=False, indent=0)
    print(f"PREP_OK items={len(items)}", flush=True)


def specs_for(sids, reps, quiet):
    out = []
    for s in sids:
        if quiet:
            out.append((s, VOICE, "babble", None, 0))
        for nz in NOISES:
            for r in reps:
                for x in VL.SNRS:
                    out.append((s, VOICE, nz, x, r))
    return out


def cmd_run(a):
    import multiprocessing as mp
    info = json.load(open(os.path.join(a.work, "items.json"), encoding="utf-8"))
    all_sids = [it["sid"] for it in info["items"]]
    sids = all_sids if a.sids == "all" else [s for s in a.sids.split(",") if s]
    assert set(sids) <= set(all_sids), set(sids) - set(all_sids)
    reps = [int(r) for r in a.reps.split(",")]
    outp = os.path.join(a.work, "asr.jsonl")
    done = set()
    if os.path.exists(outp):
        for line in open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(line)["key"])
            except ValueError:
                pass
    specs = [sp for sp in specs_for(sids, reps, a.quiet)
             if not all(f"{VL.mix_key(*sp)}|{ln}" in done for ln in LISTENERS)]
    print(f"RUN todo_mixes={len(specs)} done_rows={len(done)}", flush=True)
    if not specs:
        print("RUN_OK nothing", flush=True)
        return
    nproc = a.procs or max(1, (os.cpu_count() or 2) - 1)
    buf = []
    with open(outp, "a", encoding="utf-8") as fo, mp.get_context("fork").Pool(nproc, VL._winit, (a.work,)) as pool:
        asr = VL.ASR(a.model, a.batch)
        t0 = time.time()
        n_rows = 0
        nb = 0

        def flush():
            nonlocal n_rows
            keys = [k for k, _ in buf]
            txt = asr([w for _, w in buf])
            for k, t in zip(keys, txt):
                if k in done:
                    continue
                fo.write(json.dumps({"key": k, "asr": t}, ensure_ascii=False) + "\n")
                done.add(k)
                n_rows += 1
            fo.flush()
            buf.clear()
        for c0 in range(0, len(specs), 1500):
            for res in pool.imap(VL.render, specs[c0:c0 + 1500], chunksize=4):
                buf += [r for r in res if r[0] not in done]
                if len(buf) >= asr.batch:
                    flush()
                    nb += 1
                    if nb % 20 == 0:
                        el = time.time() - t0
                        print(f"PROG rows={n_rows} {n_rows / el:.1f}/s eta={(len(specs) * 3 - n_rows) / max(1e-9, n_rows / el) / 60:.1f}min",
                              flush=True)
        if buf:
            flush()
    print(f"RUN_OK rows={n_rows} {n_rows / max(1e-9, time.time() - t0):.1f}/s", flush=True)


def cmd_score(a):
    VL.cmd_score(a)


# ───────────────────────────── judge ─────────────────────────────

def _load(work):
    by, quiet = {}, {}
    for line in open(os.path.join(work, "scored.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["voice"] != VOICE:
            continue
        if r["snr"] is None:
            quiet[(r["sid"], r["listener"])] = (r["k"], r["n"], r["asr"])
        else:
            by.setdefault((r["sid"], r["noise"], r["listener"]), []).append((r["rep"], r["snr"], r["k"], r["n"]))
    return by, quiet


def _same_sign_exceed(vals):
    """vals: {청취자: 차이}. 경계를 넘은 청취자 모의가 둘 이상이고 부호가 같으면 그 부호, 아니면 0."""
    ex = [v for v in vals.values() if v is not None and abs(v) > BOUND]
    if len(ex) >= 2 and len({np.sign(v) for v in ex}) == 1:
        return int(np.sign(ex[0]))
    return 0


def judge(by, quiet, spec, B=10000):
    fits = {}

    def srt(sid, nz, ln, reps):
        key = (sid, nz, ln, tuple(reps))
        if key not in fits:
            d = [t for t in by.get((sid, nz, ln), []) if t[0] in reps]
            f = None
            if len({t[1] for t in d}) >= 10:
                f = VL.fit_curve([t[1] for t in d], [t[2] for t in d], [t[3] for t in d])
            fits[key] = f if (f and f.get("ok")) else None
        f = fits[key]
        return None if f is None else f.get("srt40")

    vals = {f: {(nz, ln): [srt(s, nz, ln, spec[f]["reps"]) for s in spec[f]["sids"]] for nz in NOISES for ln in LISTENERS}
            for f in FORMS}
    rng = np.random.default_rng(0)
    cells = {}
    for nz in NOISES:
        for ln in LISTENERS:
            v = {f: vals[f][(nz, ln)] for f in FORMS}
            P = [i for i in range(20) if all(v[f][i] is not None for f in FORMS)]
            c = {"n_positions": len(P), "excluded": [i + 1 for i in range(20) if i not in P]}
            if len(P) < MIN_POSITIONS:
                c["undecidable"] = True
                cells[f"{nz}|{ln}"] = c
                continue
            arr = {f: np.array([v[f][i] for i in P]) for f in FORMS}
            M = {f: float(arr[f].mean()) for f in FORMS}
            R = (M["A"] + M["B"]) / 2
            c.update({"mean": {f: round(M[f], 2) for f in FORMS}, "ref_ab": round(R, 2),
                      "d_C": round(M["C"] - R, 2), "d_D": round(M["D"] - R, 2),
                      "d_CD": round(M["C"] - M["D"], 2), "d_AB": round(M["A"] - M["B"], 2)})
            idx = rng.integers(0, len(P), (B, len(P)))
            ab = (arr["A"][idx].mean(1) + arr["B"][idx].mean(1)) / 2
            for nm, bs in (("d_C", arr["C"][idx].mean(1) - ab), ("d_D", arr["D"][idx].mean(1) - ab),
                           ("d_CD", arr["C"][idx].mean(1) - arr["D"][idx].mean(1)),
                           ("d_AB", arr["A"][idx].mean(1) - arr["B"][idx].mean(1))):
                c[nm + "_ci"] = [round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)]
            c["positions"] = {f: [None if x is None else round(x, 2) for x in v[f]] for f in FORMS}
            cells[f"{nz}|{ln}"] = c

    def dvals(nm, nz):
        return {ln: cells[f"{nz}|{ln}"].get(nm) for ln in LISTENERS}

    verdict = {}
    for f in ("C", "D"):
        verdict[f] = {nz: _same_sign_exceed(dvals(f"d_{f}", nz)) for nz in NOISES}
        verdict[f]["caution"] = sorted({f"{nz}|{ln}" for nz in NOISES for ln in LISTENERS
                                        if cells[f"{nz}|{ln}"].get(f"d_{f}") is not None
                                        and abs(cells[f"{nz}|{ln}"][f"d_{f}"]) > BOUND})
    verdict["CD_talker2"] = _same_sign_exceed(dvals("d_CD", "talker2"))
    verdict["AB"] = {nz: _same_sign_exceed(dvals("d_AB", nz)) for nz in NOISES}   # 보고만(A·B는 바꾸지 않는다)

    # 결함 문장: 정상 모의가 조용한 곳에서 낱말을 놓치거나, 여섯 칸 가운데 둘 이상에서 SRT40이 정해지지 않음
    defects = {}
    for f in ("C", "D"):
        for i, sid in enumerate(spec[f]["sids"]):
            why = []
            q = quiet.get((sid, "nh"))
            if q and q[0] < q[1]:
                why.append(f"정상 모의 조용한 곳 {q[0]}/{q[1]} ('{q[2]}')")
            n_none = sum(1 for nz in NOISES for ln in LISTENERS if vals[f][(nz, ln)][i] is None)
            if n_none >= 2:
                why.append(f"SRT40 없음 {n_none}칸")
            if why:
                defects[sid] = {"form": f, "pos": i + 1, "why": why}
    ok = (all(verdict[f][nz] == 0 for f in ("C", "D") for nz in NOISES) and verdict["CD_talker2"] == 0 and not defects)
    return {"cells": cells, "verdict": verdict, "defects": defects, "pass": bool(ok), "vals": vals}


def plan_replacements(res, spec, used):
    """사전 규칙(문서 3.3절)으로 교체할 자리를 고른다. used: 이미 예비 문장을 쓴 (폼, 자리) 집합."""
    cells, verdict, vals = res["cells"], res["verdict"], res["vals"]
    out = {}
    # 폼마다 고칠 칸(잡음)과 방향 s. C−D만 벗어나면 talker2에서 AB와 더 먼 폼 하나를 C−D를 줄이는 방향으로
    todo = {f: {nz: verdict[f][nz] for nz in NOISES if verdict[f][nz]} for f in ("C", "D")}
    if verdict["CD_talker2"] and not todo["C"] and not todo["D"]:
        mC = np.mean([cells[f"talker2|{ln}"]["d_C"] for ln in LISTENERS])
        mD = np.mean([cells[f"talker2|{ln}"]["d_D"] for ln in LISTENERS])
        s = verdict["CD_talker2"]
        if abs(mC) >= abs(mD):
            todo["C"] = {"talker2": s}
        else:
            todo["D"] = {"talker2": -s}
        pair_only = True
    else:
        pair_only = False
    for f in ("C", "D"):
        dfx = [d["pos"] - 1 for sid, d in res["defects"].items() if d["form"] == f]
        if not todo[f] and not dfx:
            continue
        chosen = [p for p in dfx if (f, p) not in used][:MAX_REPLACE]
        score = {}
        for p in range(20):
            terms = []
            for nz, s in todo[f].items():
                for ln in LISTENERS:
                    x, a_, b_ = vals[f][(nz, ln)][p], vals["A"][(nz, ln)][p], vals["B"][(nz, ln)][p]
                    if x is not None and a_ is not None and b_ is not None:
                        terms.append(s * (x - (a_ + b_) / 2))
            score[p] = float(np.mean(terms)) if terms else None
        ranked = [p for p in sorted(score, key=lambda p: -(score[p] if score[p] is not None else -1e9))
                  if score[p] is not None and score[p] > 0 and p not in chosen and (f, p) not in used]

        def predicted(sel):
            pr = {}
            for nz in todo[f]:
                for ln in LISTENERS:
                    c = cells[f"{nz}|{ln}"]
                    if c.get("undecidable"):
                        continue
                    P = [i for i in range(20) if (i + 1) not in c["excluded"]]
                    xs = []
                    for i in P:
                        if i in sel:
                            xs.append((vals["A"][(nz, ln)][i] + vals["B"][(nz, ln)][i]) / 2)
                        else:
                            xs.append(vals[f][(nz, ln)][i])
                    mx = float(np.mean(xs))
                    if pair_only:
                        other = "D" if f == "C" else "C"
                        mo = c["mean"][other]
                        pr[f"{nz}|{ln}"] = round(mx - mo if f == "C" else mo - mx, 2)
                    else:
                        pr[f"{nz}|{ln}"] = round(mx - c["ref_ab"], 2)
            return pr
        pred = predicted(chosen)
        while todo[f] and ranked and len(chosen) < MAX_REPLACE and any(abs(v) > TARGET for v in pred.values()):
            chosen.append(ranked.pop(0))
            pred = predicted(chosen)
        spares = ranked[:N_SPARE]
        out[f] = {"fix": todo[f], "pair_only": pair_only, "defects": [p + 1 for p in dfx],
                  "replace": [{"pos": p + 1, "old": None, "new": RESERVE[f][p], "score": score.get(p)} for p in chosen],
                  "spares": [{"pos": p + 1, "new": RESERVE[f][p], "score": score.get(p)} for p in spares],
                  "predicted": pred}
    return out


def cmd_judge(a):
    spec = json.load(open(a.spec, encoding="utf-8"))
    by, quiet = _load(a.work)
    res = judge(by, quiet, spec, B=a.boot)
    used = {tuple(u) for u in spec.get("used", [])}
    res["plan"] = None if res["pass"] else plan_replacements(res, spec, used)
    vals = res.pop("vals")
    res["spec"] = spec
    res["quiet_nh"] = {sid: list(quiet[(sid, "nh")][:2]) for f in ("C", "D") for sid in spec[f]["sids"] if (sid, "nh") in quiet}
    res["n_rows"] = sum(len(v) for v in by.values()) + len(quiet)
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    v = res["verdict"]
    print("JUDGE", "pass" if res["pass"] else "FAIL", json.dumps(v, ensure_ascii=False), "defects", list(res["defects"]), flush=True)
    for k, c in res["cells"].items():
        if not c.get("undecidable"):
            print(f"  {k:16s} A {c['mean']['A']:6.2f} B {c['mean']['B']:6.2f} C {c['mean']['C']:6.2f} D {c['mean']['D']:6.2f}"
                  f"  dC {c['d_C']:+.2f} dD {c['d_D']:+.2f} dCD {c['d_CD']:+.2f} dAB {c['d_AB']:+.2f} n={c['n_positions']}")
        else:
            print(f"  {k:16s} 판정 불가 n={c['n_positions']}")
    if res["plan"]:
        print("PLAN", json.dumps(res["plan"], ensure_ascii=False))
    _ = vals


def cmd_report(a):
    res = json.load(open(a.result, encoding="utf-8"))
    names = {"nh": "정상", "ci": "인공와우 모의", "ha": "보청기 모의"}
    print("| 소음 | 청취자 모의 | 자리 | A | B | C | D | C − AB (95% 구간) | D − AB (95% 구간) | C − D | A − B |")
    print("|---|---|--:|--:|--:|--:|--:|---|---|--:|--:|")
    for nz in NOISES:
        for ln in LISTENERS:
            c = res["cells"][f"{nz}|{ln}"]
            if c.get("undecidable"):
                print(f"| {nz} | {names[ln]} | {c['n_positions']} | 판정 불가 |")
                continue
            m = c["mean"]
            print(f"| {nz} | {names[ln]} | {c['n_positions']} | {m['A']:.2f} | {m['B']:.2f} | {m['C']:.2f} | {m['D']:.2f} | "
                  f"{c['d_C']:+.2f} ({c['d_C_ci'][0]:+.2f} ~ {c['d_C_ci'][1]:+.2f}) | {c['d_D']:+.2f} ({c['d_D_ci'][0]:+.2f} ~ {c['d_D_ci'][1]:+.2f}) | "
                  f"{c['d_CD']:+.2f} | {c['d_AB']:+.2f} |")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("prep"); p.add_argument("--sound", required=True); p.add_argument("--work", required=True)
    p.add_argument("--extra", default="")
    p = sub.add_parser("run"); p.add_argument("--work", required=True); p.add_argument("--sids", default="all")
    p.add_argument("--reps", default="0,1,2"); p.add_argument("--quiet", action="store_true")
    p.add_argument("--batch", type=int, default=64); p.add_argument("--procs", type=int, default=0)
    p.add_argument("--model", default="openai/whisper-large-v3-turbo")
    p = sub.add_parser("score"); p.add_argument("--work", required=True)
    p = sub.add_parser("judge"); p.add_argument("--work", required=True); p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True); p.add_argument("--boot", type=int, default=10000)
    p = sub.add_parser("report"); p.add_argument("--result", required=True)
    a = ap.parse_args()
    rc = {"check": cmd_check, "prep": cmd_prep, "run": cmd_run, "score": cmd_score, "judge": cmd_judge,
          "report": cmd_report}[a.cmd](a)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
