"""서버에서 바로 합성한 소리의 실행 중 품질 게이트(docs/listen-convo-tts-2026-10.md 4절).

미리 합성한 클립은 10/7 품질 점검(docs/sound-qa-2026-10.md)으로 골랐다. 서버 합성은 전사 모델(large-v3)을 올릴 수 없으므로 그 판정 규칙 가운데
전사 없이 계산되는 부분(D-GOP 표시 점수, 신호, 음절 시각)만 쓴다. 측정·판정 함수는 scripts/sound_pod/qa_rules.py와 같은 값을 내야 한다
(test_sound_gate.py가 확인한다). 배포 이미지에는 scripts/가 없어 여기에 옮겨 두었다. scipy 없이 numpy만 쓴다.
"""
import json
import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SPEECH_REL_DB = -35.0
CLIP_ABS = 0.99
BURST_REL_DB = 15.0
VOWEL_DROP_REL_DB = -30.0
PAD_MS = 150
FADE_MS = 10
TARGET_DBFS = -24.0
PEAK_CEIL_DBFS = -1.0
TAIL_STUCK_MS = 60
RANK = {"pass": 0, "suspect": 1, "fail": 2}
# 발음 문턱(전사 없음): 10/7 표에서 전사가 틀렸을 때 D-GOP만으로 '의심'에 머무는 값. 이보다 낮으면 실패로 본다
DGOP_MIN = {"sent": 80.0, "word": 70.0, "one": 60.0}
# 두 후보: 10/7 점검 1단계 c0·c1과 같다(total_steps, speed, 시드)
CANDIDATES = ((8, 1.05, 0), (16, 1.05, 1))

_REF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sound_gate_ref.json")
_REF: Dict[str, object] = {}


def ref() -> Dict:
    """목소리 × 길이 묶음 빠르기 기준(중앙값, MAD)과 목소리 레벨 중앙값(scripts/sound_pod/qa_ref.json과 같은 값)."""
    if not _REF:
        try:
            with open(_REF_PATH, encoding="utf-8") as f:
                _REF.update(json.load(f))
        except (OSError, ValueError):
            _REF.update({"rate": {}, "level": {}})
    return _REF


# ── 활성 레벨(ITU-T P.56 방법 B) ─────────────────────────────────────────

def _onepole(x: np.ndarray, g: float, block: int = 2048) -> np.ndarray:
    """y[n] = (1 − g)·x[n] + g·y[n−1] (scipy.signal.lfilter([1−g], [1, −g], x)와 같다). 블록마다 닫힌 꼴(누적합)로 계산한다."""
    n = x.size
    y = np.empty(n, dtype=np.float64)
    k = np.arange(block, dtype=np.float64)
    gk = g ** k                     # g^k
    ginv = g ** (-k)                # g^-k (블록 길이 안에서는 넘치지 않는다)
    prev = 0.0
    for s in range(0, n, block):
        seg = x[s:s + block]
        m = seg.size
        acc = np.cumsum(seg * ginv[:m]) * gk[:m] * (1 - g)
        y[s:s + m] = acc + prev * gk[:m] * g
        prev = y[s + m - 1]
    return y


def active_level(x: np.ndarray, sr: int) -> float:
    """선형 RMS 등가값(qa_rules.active_level과 같은 알고리즘). 활성 구간이 없으면 전체 RMS."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = x.size
    if not n or sr <= 0:
        return 0.0
    total = float(np.sum(x * x))
    if total == 0:
        return 0.0
    g = math.exp(-1.0 / (sr * 0.03))
    q = _onepole(_onepole(np.abs(x), g), g)
    hang = int(math.ceil(0.2 * sr))
    x2 = x * x
    M = 15.9
    prev = None
    idx = np.arange(n)
    lo = np.maximum(0, idx - hang)
    for j in range(15):
        thr = 2.0 ** (j - 15)
        cs = np.concatenate([[0], np.cumsum((q >= thr).astype(np.int64))])
        act = (cs[idx + 1] - cs[lo]) > 0
        cnt = int(act.sum())
        if cnt < sr * 0.05:
            break
        ssq = float(x2[act].sum())
        A = 10 * math.log10(ssq / cnt)
        C = 20 * math.log10(thr)
        d = A - C
        if d <= M:
            if prev is None:
                return math.sqrt(ssq / cnt)
            t = (prev[1] - M) / (prev[1] - d)
            return 10 ** ((prev[0] + t * (A - prev[0])) / 20)
        prev = (A, d)
    return math.sqrt(total / n)


def db(v: float) -> float:
    return 20 * math.log10(max(v, 1e-12))


def frame_db(x: np.ndarray, sr: int, ms: float) -> np.ndarray:
    w = max(1, int(round(sr * ms / 1000.0)))
    n = len(x) // w
    if n == 0:
        return np.array([-240.0])
    f = np.asarray(x[:n * w], dtype=np.float64).reshape(n, w)
    return 10 * np.log10(np.mean(f * f, axis=1) + 1e-24)


def speech_span(x: np.ndarray, sr: int, level_db: Optional[float] = None) -> Optional[Tuple[float, float]]:
    if level_db is None:
        level_db = db(active_level(x, sr))
    e = frame_db(x, sr, 10)
    on = np.where(e > level_db + SPEECH_REL_DB)[0]
    if not on.size:
        return None
    return float(on[0] * 10), float((on[-1] + 1) * 10)


def postprocess(x: np.ndarray, sr: int) -> Tuple[np.ndarray, Dict]:
    """말소리 구간 앞뒤 150 ms(모자라면 0으로 채움), 양 끝 10 ms 코사인 페이드, 활성 레벨 −24 dBFS(최대 표본 −1 dBFS 상한)."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    L = db(active_level(x, sr))
    span = speech_span(x, sr, L)
    info = {"raw_level_db": round(L, 2), "raw_peak_db": round(db(float(np.max(np.abs(x))) if x.size else 0.0), 2),
            "raw_clip_n": int(np.sum(np.abs(x) >= 0.999))}
    if not span:
        info["empty"] = True
        return x.astype(np.float32), info
    pad = int(round(sr * PAD_MS / 1000.0))
    a = int(round(span[0] / 1000.0 * sr)) - pad
    b = int(round(span[1] / 1000.0 * sr)) + pad
    pre = max(0, -a)
    post = max(0, b - len(x))
    y = np.concatenate([np.zeros(pre), x[max(0, a):min(len(x), b)], np.zeros(post)])
    f = int(round(sr * FADE_MS / 1000.0))
    if f > 0 and len(y) > 2 * f:
        w = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, f))
        y[:f] *= w
        y[-f:] *= w[::-1]
    gain_db = TARGET_DBFS - db(active_level(y, sr))
    peak_db = db(float(np.max(np.abs(y)))) + gain_db
    limited = 0.0
    if peak_db > PEAK_CEIL_DBFS:
        limited = peak_db - PEAK_CEIL_DBFS
        gain_db -= limited
    y = y * (10 ** (gain_db / 20))
    info.update({"gain_db": round(gain_db, 2), "peak_limited_db": round(limited, 2)})
    return y.astype(np.float32), info


# ── 신호 측정 ─────────────────────────────────────────────────────────────

def _token_word_index(tokens: Sequence[str]) -> List[int]:
    out, w = [], 0
    for t in tokens:
        if t == "|":
            w += 1
        out.append(w)
    return out


def signal_metrics(x: np.ndarray, sr: int, phones: Optional[Sequence[Dict]] = None,
                   tokens: Optional[Sequence[str]] = None) -> Dict:
    """qa_rules.signal_metrics와 같다."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    dur_ms = len(x) / sr * 1000.0
    L = db(active_level(x, sr))
    span = speech_span(x, sr, L)
    out = {"dur_ms": round(dur_ms, 1), "level_db": round(L, 2), "peak_db": round(db(float(np.max(np.abs(x))) if x.size else 0.0), 2),
           "clip_n": int(np.sum(np.abs(x) >= CLIP_ABS))}
    if span:
        out["lead_ms"], out["tail_ms"] = round(span[0], 1), round(dur_ms - span[1], 1)
        out["speech_ms"] = round(span[1] - span[0], 1)
    else:
        out["lead_ms"] = out["tail_ms"] = None
        out["speech_ms"] = 0.0
    e5 = frame_db(x, sr, 5)
    out["burst_n"] = int(np.sum(e5 > L + BURST_REL_DB))
    if phones and tokens and len(phones) == len(tokens):
        import sound_clips as S
        widx = _token_word_index(tokens)
        spans = []
        for g in S.group_jamo_by_syllable(list(tokens)):
            t0s = [phones[i].get("t0") for i in g]
            t1s = [phones[i].get("t1") for i in g]
            if any(v is None for v in t0s + t1s):
                spans = None
                break
            vi = [i for i in g if tokens[i].startswith("n:")][0]
            spans.append((min(t0s) * 1000, max(t1s) * 1000, widx[vi], phones[vi]["t0"] * 1000, phones[vi]["t1"] * 1000))
        if spans:
            drop = 0
            for s in spans:
                a, b = int(s[3] / 1000 * sr), int(s[4] / 1000 * sr)
                seg = x[a:max(b, a + 1)]
                if seg.size and db(float(np.sqrt(np.mean(seg * seg)))) < L + VOWEL_DROP_REL_DB:
                    drop += 1
            out["vowel_drop_n"] = drop
            gin = [spans[k + 1][0] - spans[k][1] for k in range(len(spans) - 1) if spans[k][2] == spans[k + 1][2]]
            gbt = [spans[k + 1][0] - spans[k][1] for k in range(len(spans) - 1) if spans[k][2] != spans[k + 1][2]]
            out["gap_in_word_ms"] = round(max(gin), 1) if gin else 0.0
            out["gap_between_ms"] = round(max(gbt), 1) if gbt else 0.0
            first, last = spans[0][0], spans[-1][1]
            out["tail_babble_ms"] = round(max(0.0, (span[1] if span else last) - last), 1)
            n = len(spans)
            out["n_syl_aligned"] = n
            out["sp_ms"] = round(last - first, 1)
            if n >= 2:
                out["sps"] = round(n / max(1e-3, (last - first) / 1000.0), 3)
                out["ms_per_syl"] = round((last - first) / n, 1)
    return out


def syllable_groups_ms(phones: Sequence[Dict], tokens: Sequence[str]):
    if not phones or not tokens or len(phones) != len(tokens):
        return None
    import sound_clips as S
    widx = _token_word_index(tokens)
    out = []
    for g in S.group_jamo_by_syllable(list(tokens)):
        t0s = [phones[i].get("t0") for i in g]
        t1s = [phones[i].get("t1") for i in g]
        if any(v is None for v in t0s + t1s):
            return None
        vi = [i for i in g if tokens[i].startswith("n:")][0]
        out.append((min(t0s) * 1000, max(t1s) * 1000, widx[g[-1]], phones[vi]["t0"] * 1000))
    return out


def tail_stuck(groups, speech_end_ms: Optional[float]) -> str:
    if not groups or len(groups) < 2 or speech_end_ms is None:
        return ""
    lim = speech_end_ms - TAIL_STUCK_MS
    if groups[-1][0] >= lim:
        return "syl"
    if groups[-1][3] >= lim:
        return "vowel"
    return ""


def max_gaps(groups) -> Tuple[float, float]:
    gin = [groups[k + 1][0] - groups[k][1] for k in range(len(groups) - 1) if groups[k][2] == groups[k + 1][2]]
    gbt = [groups[k + 1][0] - groups[k][1] for k in range(len(groups) - 1) if groups[k][2] != groups[k + 1][2]]
    return (round(max(gin), 1) if gin else 0.0), (round(max(gbt), 1) if gbt else 0.0)


def fix_tail_syllables(syl, speech_end_ms: Optional[float]):
    """qa_rules.fix_tail_syllables와 같다(문장 끝 음절이 말소리 끝 근처나 뒤에 놓였을 때 시각을 고친다)."""
    if not syl or len(syl) < 2 or speech_end_ms is None:
        return syl
    out = [list(x) for x in syl]
    b = int(round(speech_end_ms))
    if syl[-1][0] >= speech_end_ms - TAIL_STUCK_MS:
        a = syl[-2][0]
        b = max(b, a + 2)
        mid = int(round((a + b) / 2))
        out[-2] = [a, mid]
        out[-1] = [mid, max(b, mid + 1)]
    elif syl[-1][1] > b + TAIL_STUCK_MS:
        out[-1] = [syl[-1][0], max(b, syl[-1][0] + 1)]
    return out


def length_group(n_syl: int, key: str) -> str:
    if n_syl >= 5 or " " in key.strip():
        return "sent"
    return "one" if n_syl <= 1 else "word"


def rate_value(m: Dict, group: str) -> Optional[float]:
    if group == "one":
        return m.get("speech_ms")
    return m.get("sps") if group == "sent" else m.get("ms_per_syl")


def robust_z(x: Optional[float], r) -> Optional[float]:
    if x is None or not r:
        return None
    return 0.6745 * (x - r[0]) / max(r[1], 1e-6)


def judge_signal(m: Dict, group: str, rate_z: Optional[float], level_dev: Optional[float], check_pad: bool) -> List[Tuple[str, str]]:
    """qa_rules.judge_signal과 같다."""
    out = []
    if (m.get("speech_ms") or 0) < 50:
        out.append(("fail", "silent"))
    c = m.get("clip_n") or 0
    if c >= 3:
        out.append(("fail", "clipping"))
    elif c >= 1:
        out.append(("suspect", "clipping_minor"))
    if (m.get("burst_n") or 0) >= 1:
        out.append(("suspect", "burst"))
    if (m.get("vowel_drop_n") or 0) >= 1:
        out.append(("suspect", "vowel_dropout"))
    if (m.get("gap_in_word_ms") or 0) > 400:
        out.append(("fail", "pause_in_word"))
    if (m.get("gap_between_ms") or 0) > 1000:
        out.append(("suspect", "pause_between"))
    if (m.get("tail_babble_ms") or 0) > 300:
        out.append(("suspect", "tail_babble"))
    r = rate_value(m, group)
    if group == "sent" and r is not None and (r > 9.0 or r < 2.5):
        out.append(("fail", "rate_extreme"))
    elif group == "one" and r is not None and (r < 120 or r > 1000):
        out.append(("suspect", "rate_outlier"))
    elif rate_z is not None and abs(rate_z) > 3.5:
        out.append(("suspect", "rate_outlier"))
    if level_dev is not None and abs(level_dev) > 6:
        out.append(("suspect", "level_dev"))
    if check_pad:
        for k in ("lead_ms", "tail_ms"):
            v = m.get(k)
            if v is not None and (v < 60 or v > 400):
                out.append(("suspect", "pad_" + k[:4]))
    return out


def syl_valid(syl, n_expected: int, dur_ms: float) -> Tuple[bool, str]:
    if not syl:
        return False, "syl_none"
    if len(syl) != n_expected:
        return False, "syl_count"
    for k, s in enumerate(syl):
        if not (s[0] < s[1]):
            return False, "syl_order"
        if k and s[0] < syl[k - 1][0]:
            return False, "syl_monotonic"
    if syl[-1][1] > dur_ms + 1:
        return False, "syl_overrun"
    return True, ""


def judge_pron_dgop(group: str, S: Optional[float]) -> Tuple[str, str]:
    """전사 없는 발음 판정: D-GOP 표시 점수가 묶음 문턱 이상이면 통과, 아니면 실패(정렬 실패도 실패)."""
    if S is None:
        return "fail", "dgop_none"
    return ("pass", "") if S >= DGOP_MIN[group] else ("fail", "dgop_low")


def judge(text: str, voice: str, y: np.ndarray, sr: int, raw_level_db: Optional[float], phones: Optional[List[Dict]],
          tokens: Sequence[str], dgop: Optional[float]) -> Dict:
    """정리한 소리 y(엔진 표본율)와 정렬 결과 → {tier, flags, dgop, syl(고친 음절 시각, ms), group, metrics 일부}."""
    import sound_clips as S
    key = S.normalize_text(text)
    n_syl = len(S.syllable_positions(text))
    group = length_group(n_syl, key)
    m = signal_metrics(y, sr, phones if phones and len(phones) == len(tokens) else None, tokens)
    groups = syllable_groups_ms(phones or [], tokens) if phones else None
    se = (m["dur_ms"] - m["tail_ms"]) if m.get("tail_ms") is not None else None
    stuck = tail_stuck(groups, se) if groups else ""
    if stuck:
        m["vowel_drop_n"] = max(0, int(m.get("vowel_drop_n") or 0) - 1)
    if stuck == "syl":
        m["gap_in_word_ms"], m["gap_between_ms"] = max_gaps(groups[:-1])
    r = ref()
    rz = robust_z(rate_value(m, group), (r.get("rate") or {}).get(f"{voice}|{group}"))
    med = (r.get("level") or {}).get(voice)
    lvl = None if (med is None or raw_level_db is None) else raw_level_db - med
    syl = None
    if phones:
        try:
            syl = S.syllable_times(phones, list(tokens), duration_ms=m["dur_ms"])
        except Exception:
            syl = None
    syl = fix_tail_syllables(syl, se) if syl else syl
    pron = judge_pron_dgop(group, dgop)
    sig = judge_signal(m, group, rz, lvl, check_pad=False)
    sv = syl_valid(syl, n_syl, m["dur_ms"])
    flags = []
    tier = pron[0]
    if pron[0] != "pass":
        flags.append(f"{pron[0]}:pron:{pron[1]}")
    for t, f in sig:
        flags.append(f"{t}:{f}")
        if RANK[t] > RANK[tier]:
            tier = t
    if not sv[0]:
        flags.append(f"fail:{sv[1]}")
        tier = "fail"
    return {"tier": tier, "flags": flags, "dgop": None if dgop is None else round(float(dgop), 1), "group": group,
            "syl": syl if sv[0] else None, "rate_z": None if rz is None else round(rz, 2),
            "level_dev": None if lvl is None else round(lvl, 2), "tail_stuck": stuck}
