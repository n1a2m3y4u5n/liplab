"""발음 바꿈(대치) 잡기 공용 함수(docs/scoring-subst-2026-10.md). 모델 없이 합성 로그확률로 시험할 수 있는 순수 함수만 둔다.

- K: 경쟁 초성 표(등록 3.1절). 9/27·10/15 대치 목표 규칙(scripts/scoring_rules/targets.py RULES)의 짝을 모두 포함하고, 된소리 짝과 ㄴ↔ㄹ을 더했다.
- eligible_positions: 채점에 쓰는 초성 자리(정렬·채점 대상, 내지 않는 ㅎ 아님, 끝 음절 앞, K에 경쟁자가 있음).
- position_features: 한 자리의 손 특성(후보 A·B). 채점기·정렬기 로그확률과 앱이 쓴 정렬 구간만 쓴다.
- ctc_ll_batch: 여러 토큰열의 CTC 로그 우도(모든 정렬 합)를 한 번에 낸다(바꿈 변형 비교, 후보 B의 ΔCTC).
"""
import math
from typing import Dict, List, Sequence

K: Dict[str, List[str]] = {
    "ㄱ": ["ㅋ", "ㄲ"], "ㄲ": ["ㄱ", "ㅋ"], "ㅋ": ["ㄱ", "ㄲ"],
    "ㄷ": ["ㅌ", "ㄸ", "ㄴ", "ㅅ"], "ㄸ": ["ㄷ", "ㅌ"], "ㅌ": ["ㄷ", "ㄸ"],
    "ㅂ": ["ㅍ", "ㅃ", "ㅁ"], "ㅃ": ["ㅂ", "ㅍ"], "ㅍ": ["ㅂ", "ㅃ"],
    "ㅈ": ["ㅊ", "ㅉ"], "ㅉ": ["ㅈ", "ㅊ"], "ㅊ": ["ㅈ", "ㅉ"],
    "ㅅ": ["ㅆ", "ㄷ"], "ㅆ": ["ㅅ"],
    "ㄴ": ["ㄷ", "ㄹ"], "ㅁ": ["ㅂ"], "ㄹ": ["ㄴ"],
}
ONSETS = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅈㅉㅊㅋㅌㅍㅎ")
CAT = {}   # 짝 → 범주(보고용)
for a, bs in K.items():
    for b in bs:
        pair = {a, b}
        if pair <= set("ㄱㄲㅋ") or pair <= set("ㄷㄸㅌ") or pair <= set("ㅂㅃㅍ") or pair <= set("ㅈㅉㅊ") or pair <= set("ㅅㅆ"):
            CAT[(a, b)] = "된소리" if ("ㄲ" in pair or "ㄸ" in pair or "ㅃ" in pair or "ㅉ" in pair or "ㅆ" in pair) else "기식"
        elif pair in ({"ㄴ", "ㄷ"}, {"ㅁ", "ㅂ"}):
            CAT[(a, b)] = "비음"
        elif pair == {"ㄷ", "ㅅ"}:
            CAT[(a, b)] = "마찰"
        elif pair == {"ㄴ", "ㄹ"}:
            CAT[(a, b)] = "유음"
FEATURES = ["lp_t", "lpr_k", "lpr_all", "fr_k", "dctc_sc", "dctc_al", "dctc_sc_all", "span", "blank", "dgop", "word_init", "rel_pos",
            "al_sc_agree"]


def final_syllable_start(tokens: Sequence[str]) -> int:
    """backend/phone_reliability.final_syllable_start와 같다(백엔드를 불러오지 않고 시험하려고 옮김)."""
    idx = [i for i, t in enumerate(tokens) if (t or "").startswith("n:")]
    if not idx:
        return len(tokens)
    i = idx[-1]
    return i - 1 if i > 0 and (tokens[i - 1] or "").startswith("o:") else i


def eligible_positions(tokens: Sequence[str], phones: Sequence[Dict]) -> List[int]:
    cut = final_syllable_start(tokens)
    out = []
    for i, (t, p) in enumerate(zip(tokens, phones)):
        if i >= cut or not t.startswith("o:") or t[2:] not in K:
            continue
        if not (p.get("aligned") and p.get("scorable")) or p.get("silent_h"):
            continue
        out.append(i)
    return out


def _lse(xs):
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


def span_mean_logp(lp, start, end, tok_id):
    """구간 평균 확률의 로그(앱의 span_distribution과 같은 평균)."""
    import torch
    seg = lp[start:end + 1, tok_id]
    return float(torch.logsumexp(seg, dim=0) - math.log(seg.shape[0]))


def ctc_ll_batch(lp, seqs: List[List[int]], blank: int = 0, torch=None):
    """lp(T, C) 로그확률에서 토큰 id열 여러 개의 CTC 로그 우도. 정렬이 불가능하면 -inf."""
    if torch is None:
        import torch
    if not seqs:
        return []
    T = int(lp.shape[0])
    n = len(seqs)
    L = max(len(s) for s in seqs)
    tgt = torch.zeros((n, max(L, 1)), dtype=torch.long)
    for k, s in enumerate(seqs):
        if s:
            tgt[k, :len(s)] = torch.tensor(s)
    x = lp.unsqueeze(1).expand(T, n, lp.shape[1]).float()
    loss = torch.nn.functional.ctc_loss(x, tgt, torch.full((n,), T, dtype=torch.long), torch.tensor([len(s) for s in seqs]),
                                        blank=blank, reduction="none", zero_infinity=False)
    return [(-float(v) if math.isfinite(float(v)) else float("-inf")) for v in loss]


def position_features(i: int, tokens: Sequence[str], spans: Sequence[Dict], phones: Sequence[Dict], lp_sc, voc_sc, lp_al, voc_al,
                      base_ll: Dict[str, float], ll_cache: Dict, blank_sc: int = 0, blank_al: int = 0, torch=None) -> Dict:
    """자리 i의 특성. base_ll은 목표 토큰열 전체의 CTC 로그 우도({'sc','al'}), ll_cache는 (모델, 자리, 경쟁자) → 로그 우도 메모."""
    if torch is None:
        import torch
    t = tokens[i]
    s, e = spans[i]["start"], spans[i]["end"]
    tid = voc_sc[t]
    lp_t = span_mean_logp(lp_sc, s, e, tid)
    comps = ["o:" + c for c in K[t[2:]]]
    others = ["o:" + c for c in ONSETS if "o:" + c != t]
    lpr = {c: span_mean_logp(lp_sc, s, e, voc_sc[c]) - lp_t for c in others}
    lpr_k = max(lpr[c] for c in comps)
    best_k = max(comps, key=lambda c: lpr[c])
    lpr_all = max(lpr.values())
    lo, hi = max(0, s - 1), min(int(lp_sc.shape[0]) - 1, e + 1)
    seg = lp_sc[lo:hi + 1]
    fr_k = float((seg[:, [voc_sc[c] for c in comps]].max(dim=1).values - seg[:, tid]).max())
    blank = float(torch.exp(lp_sc[s:e + 1, blank_sc]).mean())
    # ΔCTC: 자리 i만 경쟁자로 바꾼 토큰열의 로그 우도 − 목표 토큰열의 로그 우도(모든 정렬 합, 문장 전체)
    dctc = {}
    for name, lp, voc, bl, cset in (("sc", lp_sc, voc_sc, blank_sc, others), ("al", lp_al, voc_al, blank_al, comps)):
        need = [c for c in cset if (name, i, c) not in ll_cache]
        if need:
            base = [voc[x] for x in tokens]
            seqs = []
            for c in need:
                q = list(base)
                q[i] = voc[c]
                seqs.append(q)
            for c, v in zip(need, ctc_ll_batch(lp, seqs, bl, torch)):
                ll_cache[(name, i, c)] = v
        dctc[name] = {c: ll_cache[(name, i, c)] - base_ll[name] for c in cset}
    # 정렬기 구간 평균에서 목표가 경쟁자보다 큰가(정렬기와 채점기의 일치)
    al_t = span_mean_logp(lp_al, s, e, voc_al[t])
    al_c = max(span_mean_logp(lp_al, s, e, voc_al[c]) for c in comps)
    word_init = 1.0 if i == 0 or tokens[i - 1] == "|" else 0.0
    return {
        "lp_t": round(lp_t, 4), "lpr_k": round(lpr_k, 4), "lpr_all": round(lpr_all, 4), "fr_k": round(fr_k, 4),
        "dctc_sc": round(max(dctc["sc"][c] for c in comps), 4), "dctc_al": round(max(dctc["al"].values()), 4),
        "dctc_sc_all": round(max(dctc["sc"].values()), 4), "span": e - s + 1, "blank": round(blank, 4),
        "dgop": round(float(phones[i].get("dgop") or 0.0), 4), "word_init": word_init, "rel_pos": round(i / max(1, len(tokens) - 1), 4),
        "al_sc_agree": 1.0 if (al_t >= al_c) == (lpr_k <= 0) else 0.0, "best_k": best_k[2:],
    }


def selftest():
    import torch
    assert final_syllable_start(["o:ㄱ", "n:ㅏ", "|", "o:ㄴ", "n:ㅏ"]) == 3
    toks = ["o:ㄷ", "n:ㅏ", "o:ㄱ", "n:ㅏ"]
    ph = [{"aligned": True, "scorable": True}] * 4
    assert eligible_positions(toks, ph) == [0]
    voc = {"<pad>": 0, "|": 1, "n:ㅏ": 2}
    for c in ONSETS:
        voc["o:" + c] = len(voc)
    # 소리는 '나가'인데 목표는 '다가': 자리 0에서 ㄴ이 이긴다
    T = 8
    lp = torch.full((T, len(voc)), -12.0)
    path = ["o:ㄴ", "o:ㄴ", "n:ㅏ", "n:ㅏ", "<pad>", "o:ㄱ", "n:ㅏ", "n:ㅏ"]
    for f, t in enumerate(path):
        lp[f, voc[t]] = 0.0
    lp = torch.log_softmax(lp, dim=-1)
    tid = [voc[t] for t in toks]
    base = ctc_ll_batch(lp, [tid])[0]
    spans = [{"start": 0, "end": 1}, {"start": 2, "end": 3}, {"start": 5, "end": 5}, {"start": 6, "end": 7}]
    f = position_features(0, toks, spans, ph, lp, voc, lp, voc, {"sc": base, "al": base}, {})
    assert f["best_k"] == "ㄴ" and f["lpr_k"] > 5 and f["dctc_sc"] > 5 and f["dctc_al"] > 5, f
    # 맞게 말한 경우(목표 '나가')에는 경쟁자 증거가 음수
    toks2 = ["o:ㄴ", "n:ㅏ", "o:ㄱ", "n:ㅏ"]
    base2 = ctc_ll_batch(lp, [[voc[t] for t in toks2]])[0]
    g = position_features(0, toks2, spans, ph, lp, voc, lp, voc, {"sc": base2, "al": base2}, {})
    assert g["lpr_k"] < -5 and g["dctc_sc"] < -5, g
    assert set(CAT.values()) == {"기식", "된소리", "비음", "마찰", "유음"}
    # 10/15 대치 규칙의 짝은 모두 K에 있다
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoring_rules"))
    import targets as TG
    for a, lst in TG.RULES.items():
        for b, _cat in lst:
            assert b in K[a], (a, b)
    print("COMMON_SELFTEST_OK")


if __name__ == "__main__":
    selftest()
