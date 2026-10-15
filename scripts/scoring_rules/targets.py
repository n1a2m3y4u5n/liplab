"""문장 점수 규칙 후보(docs/scoring-rules-2026-10.md)의 목표 문장 만들기. 맥과 파드가 같이 쓴다(점수를 보지 않는다).

- 다른 문장 2개: 10/6·10/9와 같은 규칙(같은 세트 자기 문장 목록, 한글 음절 수 ±30%, 한글만 남긴 문자열이 같은 후보 제외, random.Random(0), 목록 순).
- 대치 목표 'min': KSC d1_minimal.candidates 규칙(scripts/dgop_adapt_pod/build.py에서 그대로 옮김). 마지막 음절 제외, 발음형 초성 한 자리만 다른 바꿈,
  기식·비음·마찰 규칙 표, 클립마다 최대 2개를 random.Random(20261007)로 고른다(클립 순서대로 한 생성기).
- 대치 목표 'min2': 고른 두 'min'을 함께 적용한 목표(초성 두 자리가 다름). 토큰 비교로 정확히 두 자리만 다를 때만 만든다.
- 범주 27 조각 고르기: scripts/newdata_c27/c27_pod.py select와 같은 규칙(20초 넘는 조각 제외, 세션마다 15개, 화자 5개 미만 제외).
"""
import random
import re

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
RULES = {
    "ㅂ": [("ㅍ", "기식"), ("ㅁ", "비음")], "ㅍ": [("ㅂ", "기식")],
    "ㄷ": [("ㅌ", "기식"), ("ㄴ", "비음"), ("ㅅ", "마찰")], "ㅌ": [("ㄷ", "기식")],
    "ㄱ": [("ㅋ", "기식")], "ㅋ": [("ㄱ", "기식")],
    "ㅈ": [("ㅊ", "기식")], "ㅊ": [("ㅈ", "기식")],
    "ㅁ": [("ㅂ", "비음")], "ㄴ": [("ㄷ", "비음")],
    "ㅅ": [("ㄷ", "마찰")],
}
MIN_SEED, MIN_K = 20261007, 2
MAX_LEN, PER_SESSION, MIN_SPK, SEL_SEED = 20.0, 15, 5, 20261009


def hangul(s):
    return re.sub(r"[^가-힣]", "", s or "")


def _is_syl(ch):
    return 0xAC00 <= ord(ch) <= 0xD7A3


def _onset(ch):
    return CHO[(ord(ch) - 0xAC00) // 588]


def _with_onset(ch, new):
    code = ord(ch) - 0xAC00
    return chr(0xAC00 + CHO.index(new) * 588 + code % 588)


def min_candidates(text, jv):
    base = jv.text_to_tokens(text)
    pos = [i for i, ch in enumerate(text) if _is_syl(ch)]
    out = []
    for i in pos[:-1]:
        for new, cat in RULES.get(_onset(text[i]), []):
            t2 = text[:i] + _with_onset(text[i], new) + text[i + 1:]
            tok = jv.text_to_tokens(t2)
            diff = [k for k, (a, b) in enumerate(zip(base, tok)) if a != b]
            if len(tok) == len(base) and len(diff) == 1 and tok[diff[0]].startswith("o:"):
                out.append({"char_idx": i, "orig": _onset(text[i]), "new": new, "cat": cat, "target": t2, "tok_idx": diff[0]})
    return out


def pick_min(rng, text, jv):
    cands = min_candidates(text, jv)
    if not cands:
        return []
    first = rng.choice(cands)
    pick = [first]
    rest = [c for c in cands if c["char_idx"] != first["char_idx"]]
    if MIN_K > 1 and rest:
        pick.append(rng.choice(rest))
    return pick


def min2_of(text, mins, jv):
    """두 'min'(서로 다른 음절)을 함께 적용. 토큰이 정확히 그 두 자리만 다를 때만 돌려준다."""
    if len(mins) < 2 or mins[0]["char_idx"] == mins[1]["char_idx"]:
        return None
    t = list(text)
    for m in mins[:2]:
        t[m["char_idx"]] = _with_onset(text[m["char_idx"]], m["new"])
    t2 = "".join(t)
    base, tok = jv.text_to_tokens(text), jv.text_to_tokens(t2)
    if len(tok) != len(base):
        return None
    diff = [k for k, (a, b) in enumerate(zip(base, tok)) if a != b]
    want = sorted(m["tok_idx"] for m in mins[:2])
    if diff != want:
        return None
    return {"text": t2, "kind": "min2", "tok_idx": want, "cat": "+".join(m["cat"] for m in mins[:2])}


def min_targets(rng, text, jv):
    mins = pick_min(rng, text, jv)
    out = [{"text": m["target"], "kind": "min", "tok_idx": m["tok_idx"], "cat": m["cat"]} for m in mins]
    m2 = min2_of(text, mins, jv)
    if m2:
        out.append(m2)
    return out


def others_for(own, pool, rng):
    n = len(hangul(own))
    cand = [x for x in pool if x != own and hangul(x) != hangul(own) and 0.7 * n <= len(hangul(x)) <= 1.3 * n]
    return rng.sample(cand, min(2, len(cand)))


def spk608(stem):
    """608 화자 ID: 범주-이니셜-성별-나이(s13_newspk.spk_of와 같다)."""
    p = stem.split("-")
    cat, ini = p[2], p[4]
    sx = next((i for i in range(5, len(p)) if p[i] in ("M", "F")), None)
    return f"{cat}-{ini}-{p[sx]}-{p[sx + 1]}" if sx is not None and sx + 1 < len(p) else f"{cat}-{ini}"


def clip_id(c):
    return f"{c['file'][:-5]}:{c['si']:03d}"


def select_c27(cuts):
    """c27_pod.select와 같은 규칙. 돌려주는 순서는 cuts608.json 순서."""
    ok = [c for c in cuts if c.get("cut") and c["end"] - c["start"] <= MAX_LEN]
    by = {}
    for c in ok:
        by.setdefault(c["file"], []).append(c)
    keep = set()
    for f, cs in by.items():
        ids = sorted(clip_id(c) for c in cs)
        if len(ids) > PER_SESSION:
            ids = random.Random(SEL_SEED).sample(ids, PER_SESSION)
        keep |= set(ids)
    spk_n = {}
    for c in ok:
        if clip_id(c) in keep:
            s = spk608(c["file"][:-5])
            spk_n[s] = spk_n.get(s, 0) + 1
    drop = {s for s, n in spk_n.items() if n < MIN_SPK}
    out = [c for c in ok if clip_id(c) in keep and spk608(c["file"][:-5]) not in drop]
    info = {"cut": sum(1 for c in cuts if c.get("cut")), "le20": len(ok), "kept": len(out), "speakers": len(spk_n) - len(drop),
            "dropped_speakers": sorted(drop), "sessions": len({c["file"] for c in out})}
    return out, info


def c27_jobs(kept, jv, path_of, set_name):
    """범주 27 조각 → 작업(자기 1 + 다른 2 + min ≤2 + min2). 다른 문장은 10/9 pairs_for 규칙(같은 생성기 Random(0), 조각 순서)."""
    pool = [c["target"] for c in kept]
    rng_o, rng_m = random.Random(0), random.Random(MIN_SEED)
    jobs = []
    for c in kept:
        own = c["target"]
        n = len(hangul(own))
        cand = [x for x in pool if x != own and hangul(x) != hangul(own) and 0.7 * n <= len(hangul(x)) <= 1.3 * n]
        others = rng_o.sample(cand, min(2, len(cand)))
        tg = [{"text": own, "kind": "own"}] + [{"text": t, "kind": "other"} for t in others] + min_targets(rng_m, own, jv)
        jobs.append({"set": set_name, "spk": spk608(c["file"][:-5]), "clip": clip_id(c), "path": path_of(c), "targets": tg})
    return jobs
