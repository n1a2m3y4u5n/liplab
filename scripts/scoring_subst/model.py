"""발음 바꿈(대치) 잡기: 후보 학습·고르기(탐색)와 확인 판정(docs/scoring-subst-2026-10.md 4·6·7절).

  python model.py explore FEAT.jsonl [FEAT2.jsonl ...] --out DIR      탐색: 화자 5겹 교차 검증, 문턱, 고르기 → DIR/frozen.json·models.pkl
  python model.py confirm DIR FEAT.jsonl [...]                         확인: DIR의 고정 값으로 한 번 판정 → DIR/confirm.json
  python model.py selftest                                             가짜 자료로 흐름 점검(수치 의미 없음)

집합 이름(feat 행의 set): 538·c28·c27b1(탐색), f538·c27b2·c28h1·538h1(확인). 문장 판정은 지금 앱 판정(표시 점수 ≥ 65)이 합격인 시도에만
작용하는 보류다(scoring-rules 3.1절과 같다). 문장 점수 s = 자격 있는 초성 자리의 후보 값 가운데 최댓값, s ≥ τ면 보류.
"""
import json
import math
import os
import pickle
import random
import sys
import zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

PASS = 65.0
SEED = 20261019
N_BOOT = 2000
HAND = [f for f in C.FEATURES]
CANDS = ["B-sc", "B-al", "A-LR", "A-GB", "C-rel", "C-aug"]
EXPLORE_SETS = ("538", "c28", "c27b1")
AUX_KINDS = ("splice_sub", "splice_same", "tts_own", "tts_min")
SAME_PERSON = {"27-KHY-F-29": "27-KHY-F-28"}   # 첫 묶음의 같은 사람일 수 있는 두 화자(scoring-rules 2절)


def spk_key(r):
    return SAME_PERSON.get(r["spk"], r["spk"])


def load(paths):
    rows = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            j = json.loads(line)
            if j.get("rec") == "t" and "error" not in j:
                rows.append(j)
    return rows


def fold_of(spk, k=5):
    return zlib.crc32(spk.encode("utf-8")) % k


def target_weights(pos_rows):
    """y=0 자리의 목표 초성 분포를 y=1 자리의 분포에 맞추는 가중치(목표 글자만으로 맞히는 지름길을 막는다, 등록 3.4절)."""
    c1 = Counter(p["tok"] for p in pos_rows if p["y"] == 1)
    c0 = Counter(p["tok"] for p in pos_rows if p["y"] == 0)
    n1, n0 = sum(c1.values()) or 1, sum(c0.values()) or 1
    w = {t: (c1.get(t, 0) / n1) / (c0[t] / n0) for t in c0}
    return [1.0 if p["y"] == 1 else w.get(p["tok"], 0.0) for p in pos_rows]


def train_positions(rows, aux=False):
    """학습 자리: 자기 문장의 모든 자격 자리(y=0) + 바꾼 목표의 바꾼 자리(y=1). aux면 splice·tts 행도(같은 규칙)."""
    out = []
    for r in rows:
        k = r["kind"]
        if k == "own" or (aux and k in ("splice_same", "tts_own")):
            out += [(r, p) for p in r["pos"]]
        elif k in ("min", "min2") or (aux and k in ("splice_sub", "tts_min")):
            out += [(r, p) for p in r["pos"] if p["y"] == 1]
    return out


def tok_onehot(tok):
    return [1.0 if tok == o else 0.0 for o in C.ONSETS]


def hand_x(p):
    return [float(p[f]) for f in HAND]


class Hid:
    """feat.py --hid가 남긴 숨은 상태 읽기(OUT_hid/<clip>.npz, 열쇠 '<목표 번호>_<자리>')."""

    def __init__(self, dirs):
        self.dirs, self.cache = dirs, {}

    def get(self, r, p):
        import numpy as np
        clip = r["clip"].replace(":", "_")
        if clip not in self.cache:
            self.cache.clear() if len(self.cache) > 64 else None
            for d in self.dirs:
                f = os.path.join(d, clip + ".npz")
                if os.path.exists(f):
                    self.cache[clip] = dict(np.load(f))
                    break
            else:
                self.cache[clip] = {}
        v = self.cache[clip].get(f"{r['ti']}_{p['i']}")
        return None if v is None else v.astype("float32").tolist()


def make_model(name):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    if name == "A-LR":
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
    if name == "A-GB":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, random_state=SEED)
    if name in ("C-rel", "C-aug"):
        return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(256,), alpha=1e-3, max_iter=60, early_stopping=True,
                                                             random_state=SEED))
    raise KeyError(name)


def feats_for(name, r, p, hid):
    if name in ("A-LR", "A-GB"):
        return hand_x(p)
    v = hid.get(r, p) if hid else None
    return None if v is None else v + tok_onehot(p["tok"])


def fit(name, pairs, hid):
    X, y, keep = [], [], []
    for r, p in pairs:
        x = feats_for(name, r, p, hid)
        if x is not None:
            X.append(x)
            y.append(p["y"])
            keep.append(p)
    w = target_weights(keep)
    m = make_model(name)
    try:
        m.fit(X, y, **({"logisticregression__sample_weight": w} if name == "A-LR" else
                       {"sample_weight": w} if name == "A-GB" else {}))
    except TypeError:
        m.fit(X, y)
    return m


def pos_values(name, rows, models_for_row, hid):
    """행마다 자리 값 목록. B는 손 특성 그대로, A·C는 그 행의 화자가 빠진 접힘 모델(탐색) 또는 다섯 모델 평균(확인)."""
    out = {}
    if name in ("B-sc", "B-al"):
        key = "dctc_sc" if name == "B-sc" else "dctc_al"
        return {idx: [p[key] for p in r["pos"]] for idx, r in enumerate(rows)}
    # 같은 모델 묶음을 쓰는 행끼리 모아 한 번에 예측한다
    groups = defaultdict(list)
    for idx, r in enumerate(rows):
        ms = models_for_row(r)
        groups[tuple(id(m) for m in ms)].append((idx, ms))
    for items in groups.values():
        ms = items[0][1]
        X, owner = [], []
        for idx, _ms in items:
            out[idx] = []
            for p in rows[idx]["pos"]:
                x = feats_for(name, rows[idx], p, hid)
                if x is not None:
                    X.append(x)
                    owner.append(idx)
        if not X:
            continue
        prob = [0.0] * len(X)
        for m in ms:
            for k, v in enumerate(m.predict_proba(X)[:, 1]):
                prob[k] += float(v) / len(ms)
        for idx, v in zip(owner, prob):
            out[idx].append(v)
    return out


def sentence_scores(rows, pv):
    return [max(pv[i]) if pv[i] else -math.inf for i in range(len(rows))]


def is_pass(r):
    return r.get("score") is not None and r["score"] >= PASS


def group_of(r):
    s = r["set"]
    return "608" if s in ("c28", "c27b1") else s


def metrics(rows, s, tau, idx=None):
    """FH(자기 문장 합격 가운데 보류), CS(바꾼 목표 합격 가운데 보류), SP(바꾼 목표 전체 가운데 합격이고 보류 아님), NG = CS − FH. %."""
    idx = range(len(rows)) if idx is None else idx
    own_p = own_h = sw_p = sw_h = sw_n = 0
    for i in idx:
        r = rows[i]
        held = s[i] >= tau
        if r["kind"] == "own" and is_pass(r):
            own_p += 1
            own_h += held
        elif r["kind"] in ("min", "min2", "splice_sub", "tts_min"):
            sw_n += 1
            if is_pass(r):
                sw_p += 1
                sw_h += held
    fh = 100.0 * own_h / own_p if own_p else float("nan")
    cs = 100.0 * sw_h / sw_p if sw_p else float("nan")
    sp = 100.0 * (sw_p - sw_h) / sw_n if sw_n else float("nan")
    return {"FH": fh, "CS": cs, "SP": sp, "NG": cs - fh, "n_own_pass": own_p, "n_sw": sw_n, "n_sw_pass": sw_p}


def boot(rows, s, tau, sel, seed=SEED, n=N_BOOT):
    """화자 부트스트랩 95% 백분위 구간(FH·CS·SP·NG). sel: 행 번호 목록(한 집합)."""
    by = defaultdict(list)
    for i in sel:
        by[spk_key(rows[i])].append(i)
    spks = sorted(by)
    rng = random.Random(seed)
    acc = defaultdict(list)
    for _ in range(n):
        idx = [i for k in (rng.choice(spks) for _ in spks) for i in by[k]]
        m = metrics(rows, s, tau, idx)
        for key in ("FH", "CS", "SP", "NG"):
            if m[key] == m[key]:
                acc[key].append(m[key])
    ci = {}
    for key, v in acc.items():
        v.sort()
        ci[key] = [round(v[int(0.025 * (len(v) - 1))], 2), round(v[int(0.975 * (len(v) - 1))], 2)]
    return ci


def pick_tau(rows, s, sets):
    """탐색 문턱: FH(538) ≤ 2%이고 FH(608 = c28 ∪ c27b1) ≤ 5%를 함께 지키는 가장 작은 τ(보류가 가장 많은 값). 등록 4.3절."""
    own = [i for i, r in enumerate(rows) if r["kind"] == "own" and is_pass(r)]
    cand = sorted({s[i] for i in own if s[i] > -math.inf}) + [math.inf]
    i538 = [i for i in range(len(rows)) if rows[i]["set"] == "538"]
    i608 = [i for i in range(len(rows)) if rows[i]["set"] in ("c28", "c27b1")]
    for tau in cand:
        nxt = math.nextafter(tau, math.inf) if tau < math.inf else tau
        if metrics(rows, s, nxt, i538)["FH"] <= 2.0 and metrics(rows, s, nxt, i608)["FH"] <= 5.0:
            return nxt
    return math.inf


def text_only_auc(rows):
    """목표 글자만(초성 종류·자리 위치·어절 첫머리)으로 바꾼 자리를 맞히는 접힘 밖 AUC. 0.60을 넘으면 C 후보는 자격을 잃는다(등록 3.4절)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    pairs = train_positions([r for r in rows if r["set"] in EXPLORE_SETS])
    ys, ps = [], []
    for f in range(5):
        tr = [(r, p) for r, p in pairs if fold_of(spk_key(r)) != f]
        te = [(r, p) for r, p in pairs if fold_of(spk_key(r)) == f]
        if not tr or not te:
            continue
        X = [tok_onehot(p["tok"]) + [p["rel_pos"], p["word_init"]] for _r, p in tr]
        w = target_weights([p for _r, p in tr])
        m = LogisticRegression(max_iter=2000).fit(X, [p["y"] for _r, p in tr], sample_weight=w)
        ys += [p["y"] for _r, p in te]
        ps += list(m.predict_proba([tok_onehot(p["tok"]) + [p["rel_pos"], p["word_init"]] for _r, p in te])[:, 1])
    return float(roc_auc_score(ys, ps)) if len(set(ys)) == 2 else float("nan")


def cmd_explore(paths, out, hid_dirs):
    rows_all = load(paths)
    rows = [r for r in rows_all if r["set"] in EXPLORE_SETS and r["kind"] in ("own", "min", "min2")]
    aux = [r for r in rows_all if r["kind"] in AUX_KINDS]
    hid = Hid(hid_dirs) if hid_dirs else None
    res = {"n_rows": len(rows), "n_aux": len(aux), "sets": dict(Counter(r["set"] for r in rows)),
           "speakers": {s: len({spk_key(r) for r in rows if r["set"] == s}) for s in EXPLORE_SETS}}
    res["text_only_auc"] = text_only_auc(rows)
    models, cands = {}, {}
    for name in CANDS:
        if name.startswith("C") and hid is None:
            cands[name] = {"skipped": "숨은 상태 없음"}
            continue
        fold_models = {}
        if not name.startswith("B"):
            base = train_positions(rows)
            for f in range(5):
                tr = [(r, p) for r, p in base if fold_of(spk_key(r)) != f]
                if name == "C-aug":   # 잇기 행은 원래 화자의 접힘을 따른다(같은 화자가 학습·평가에 함께 들지 않게), 합성 목소리는 늘 학습
                    tr += [(r, p) for r, p in train_positions(aux, aux=True)
                           if r["spk"].startswith("tts-") or fold_of(spk_key(r)) != f]
                fold_models[f] = fit(name, tr, hid)
        pv = pos_values(name, rows, lambda r: [fold_models[fold_of(spk_key(r))]], hid)
        s = sentence_scores(rows, pv)
        tau = pick_tau(rows, s, EXPLORE_SETS)
        per = {g: metrics(rows, s, tau, [i for i, r in enumerate(rows) if r["set"] == g]) for g in EXPLORE_SETS}
        per["608"] = metrics(rows, s, tau, [i for i, r in enumerate(rows) if r["set"] in ("c28", "c27b1")])
        ok = (per["538"]["CS"] >= 30.0 and per["c28"]["NG"] >= 0 and per["c27b1"]["NG"] >= 0
              and (not name.startswith("C") or res["text_only_auc"] <= 0.60))
        cands[name] = {"tau": tau, "metrics": per, "eligible": ok}
        models[name] = fold_models
    elig = [n for n in CANDS if cands.get(n, {}).get("eligible")]
    chosen = max(elig, key=lambda n: (cands[n]["metrics"]["538"]["CS"], -cands[n]["metrics"]["608"]["FH"])) if elig else None
    res.update(candidates=cands, chosen=chosen, verdict="선택" if chosen else "실패(탐색)")
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, "explore.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    frozen = {"chosen": chosen, "tau": cands[chosen]["tau"] if chosen else None, "pass": PASS, "K": C.K, "features": HAND,
              "registered_doc": "docs/scoring-subst-2026-10.md"}
    json.dump(frozen, open(os.path.join(out, "frozen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(out, "models.pkl"), "wb") as fo:
        pickle.dump({n: models[n] for n in models}, fo)
    print("SUB_EXPLORE", json.dumps({"chosen": chosen, "text_only_auc": round(res["text_only_auc"], 3),
                                     **{n: {"tau": c.get("tau"), "538": c.get("metrics", {}).get("538"), "608": c.get("metrics", {}).get("608")}
                                        for n, c in cands.items()}}, ensure_ascii=False, default=str), flush=True)


CONFIRM = {"f538": "538 새 화자", "c27b2": "범주 27 두 번째 묶음", "c28h1": "범주 28 확인 절반", "538h1": "538 확인 절반(보고만)"}


def cmd_confirm(out, paths, hid_dirs):
    frozen = json.load(open(os.path.join(out, "frozen.json"), encoding="utf-8"))
    name, tau = frozen["chosen"], frozen["tau"]
    assert name, "탐색에서 고른 후보가 없으면 확인을 돌리지 않는다(등록 7절)"
    models = pickle.load(open(os.path.join(out, "models.pkl"), "rb")).get(name, {})
    rows_all = load(paths)
    rows = [r for r in rows_all if r["set"] in CONFIRM and r["kind"] in ("own", "min", "min2")]
    report = [r for r in rows_all if r["set"] in CONFIRM and r["kind"] in AUX_KINDS]
    hid = Hid(hid_dirs) if hid_dirs else None
    ms = [models[f] for f in sorted(models)]
    pv = pos_values(name, rows, lambda r: ms, hid)
    s = sentence_scores(rows, pv)
    res = {"chosen": name, "tau": tau, "sets": {}}
    for g in CONFIRM:
        sel = [i for i, r in enumerate(rows) if r["set"] == g]
        if not sel:
            continue
        m = metrics(rows, s, tau, sel)
        m["ci"] = boot(rows, s, tau, sel)
        m["speakers"] = len({spk_key(rows[i]) for i in sel})
        m["sp_now"] = metrics(rows, [-math.inf] * len(rows), math.inf, sel)["SP"]
        res["sets"][g] = m
    tf = sorted(r["t_feat"] for r in rows if r["kind"] == "own" and "t_feat" in r)
    res["t_feat_p50"] = tf[len(tf) // 2] if tf else None
    res["t_feat_p95"] = tf[int(0.95 * (len(tf) - 1))] if tf else None
    S = res["sets"]
    f, b, h = S.get("f538", {}), S.get("c27b2", {}), S.get("c28h1", {})
    crit = {
        "SK1": bool(f) and f["FH"] <= 3.0 and f["ci"].get("FH", [0, 99])[1] <= 5.0,
        "SK2": bool(b) and b["FH"] <= 8.0 and b["ci"].get("FH", [0, 99])[1] <= 12.0 and bool(h) and h["FH"] <= 8.0,
        "SK3": bool(f) and f["SP"] <= 70.0 and f["ci"].get("SP", [0, 100])[1] <= 80.0 and f["ci"].get("NG", [-1, 0])[0] > 0,
        "SK4": bool(b) and b["NG"] >= 0 and bool(h) and h["NG"] >= 0,
        "SK5": res["t_feat_p95"] is not None and res["t_feat_p95"] <= 0.15,
    }
    valid = bool(f) and f["speakers"] >= 20 and f["n_own_pass"] >= 300 and bool(b) and b["speakers"] >= 20
    res.update(criteria=crit, valid=valid, verdict=("판정 불가" if not valid else "통과" if all(crit.values()) else "실패"))
    if report:
        rv = pos_values(name, report, lambda r: ms, hid)
        rs = sentence_scores(report, rv)
        res["report_aux"] = {k: metrics(report, rs, tau, [i for i, r in enumerate(report) if r["kind"] in k])
                             for k in (("splice_sub", "splice_same"), ("tts_min", "tts_own"))}
    json.dump(res, open(os.path.join(out, "confirm.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("SUB_CONFIRM", json.dumps({"verdict": res["verdict"], "criteria": crit, **{g: {k: v for k, v in m.items() if k != "ci"}
                                                                                   for g, m in S.items()}}, ensure_ascii=False), flush=True)


def selftest():
    """가짜 행으로 흐름만 점검한다(바꾼 자리의 dctc를 크게 둔 장난감 자료)."""
    import tempfile
    rng = random.Random(1)
    rows = []
    sets = [("538", "spk%03d"), ("c28", "28-A%02d-F-50"), ("c27b1", "27-B%02d-M-40")]
    for st, fmt in sets:
        for k in range(10):
            spk = fmt % k
            for c in range(6):
                for kind in ("own", "min", "min2"):
                    pos = []
                    for i in range(8):
                        y = 1 if (kind != "own" and i in (2, 5)[: (1 if kind == "min" else 2)]) else 0
                        base = {f: rng.gauss(0, 1) for f in HAND}
                        base["dctc_sc"] = rng.gauss(4 if y else -6, 2)
                        base["dctc_al"] = base["dctc_sc"] + rng.gauss(0, 1)
                        pos.append({"i": i * 3, "tok": rng.choice(["ㄱ", "ㄷ", "ㅂ", "ㅈ"]), "y": y, **base})
                    rows.append({"rec": "t", "set": st, "spk": spk, "clip": f"{spk}_{c}", "ti": 0, "kind": kind,
                                 "score": 80 + rng.random() * 10, "pos": pos, "t_feat": 0.02})
    d = tempfile.mkdtemp()
    p = os.path.join(d, "f.jsonl")
    with open(p, "w", encoding="utf-8") as fo:
        for r in rows:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    cmd_explore([p], d, None)
    fz = json.load(open(os.path.join(d, "frozen.json"), encoding="utf-8"))
    assert fz["chosen"] in CANDS, fz
    # 확인: 같은 장난감 자료를 확인 집합 이름으로
    rows2 = []
    for r in rows:
        r = dict(r)
        r["set"] = {"538": "f538", "c28": "c28h1", "c27b1": "c27b2"}[r["set"]]
        rows2.append(r)
    p2 = os.path.join(d, "g.jsonl")
    with open(p2, "w", encoding="utf-8") as fo:
        for r in rows2:
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
    cmd_confirm(d, [p2], None)
    print("MODEL_SELFTEST_OK", d)


if __name__ == "__main__":
    a = sys.argv[1:]
    hid_dirs = [x[len("--hid="):] for x in a if x.startswith("--hid=")]
    a = [x for x in a if not x.startswith("--hid=")]
    if a and a[0] == "explore":
        out = a[a.index("--out") + 1]
        cmd_explore([x for x in a[1:a.index("--out")]], out, hid_dirs)
    elif a and a[0] == "confirm":
        cmd_confirm(a[1], a[2:], hid_dirs)
    elif a and a[0] == "selftest":
        selftest()
    else:
        print(__doc__)
        sys.exit(2)
