"""소리 자극 품질 점검(docs/sound-qa-2026-10.md)의 측정·판정 순수 함수. numpy(+scipy)와 앱 백엔드 모듈만 쓴다.

    python qa_rules.py selftest        규칙 자체 시험(합성 신호·표 예시, 모델 없음)

백엔드 경로는 LIPLAB_BACKEND(기본: 이 파일 기준 ../../backend, 파드에서는 /workspace/sqa/backend).
"""
import math
import os
import re
import sys
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.environ.get("LIPLAB_BACKEND") or os.path.normpath(os.path.join(_HERE, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ── 사전 기준 값(문서 1~5절). 바꾸면 문서와 같이 바꾸고 '사후 변경'으로 적는다 ──────────────────────
SPEECH_REL_DB = -35.0        # 말소리 구간: 10 ms 창 RMS > L − 35 dB
CLIP_ABS = 0.99              # 잘림 표본
BURST_REL_DB = 15.0          # 5 ms 창 RMS > L + 15 dB
VOWEL_DROP_REL_DB = -30.0    # 중성 구간 RMS < L − 30 dB
PAD_MS = 150                 # 정리: 말소리 구간 앞뒤 무음
FADE_MS = 10
TARGET_DBFS = -24.0          # 정리: 활성 레벨
PEAK_CEIL_DBFS = -1.0
RANK = {"pass": 0, "suspect": 1, "fail": 2}


# ── 활성 레벨(ITU-T P.56 방법 B, listenMix.activeLevel과 같은 알고리즘) ─────────────────────────────

def active_level(x: np.ndarray, sr: int) -> float:
    """선형 RMS 등가값. listenMix.js activeLevel을 벡터로 옮겼다(포락선 0.03 s 지수 평활 두 번, 유지 0.2 s,
    문턱 2^-15 … 2^-1, 활성 평균 제곱 레벨과 문턱의 차가 15.9 dB가 되는 점을 보간). 활성 구간이 없으면 전체 RMS."""
    from scipy.signal import lfilter
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = x.size
    if not n or sr <= 0:
        return 0.0
    total = float(np.sum(x * x))
    if total == 0:
        return 0.0
    g = math.exp(-1.0 / (sr * 0.03))
    p = lfilter([1 - g], [1, -g], np.abs(x))
    q = lfilter([1 - g], [1, -g], p)
    hang = int(math.ceil(0.2 * sr))
    x2 = x * x
    M = 15.9
    prev = None
    for j in range(15):
        thr = 2.0 ** (j - 15)
        above = (q >= thr).astype(np.int64)
        cs = np.concatenate([[0], np.cumsum(above)])
        idx = np.arange(n)
        lo = np.maximum(0, idx - hang)
        act = (cs[idx + 1] - cs[lo]) > 0          # [i-hang, i] 안에 문턱을 넘은 표본이 있으면 활성
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
    """(시작 ms, 끝 ms). 10 ms 창 RMS > L − 35 dB인 첫 창 시작과 마지막 창 끝. 없으면 None."""
    if level_db is None:
        level_db = db(active_level(x, sr))
    e = frame_db(x, sr, 10)
    on = np.where(e > level_db + SPEECH_REL_DB)[0]
    if not on.size:
        return None
    return float(on[0] * 10), float((on[-1] + 1) * 10)


# ── 신호 측정 ──────────────────────────────────────────────────────────────

def _token_word_index(tokens: Sequence[str]) -> List[int]:
    """자모 토큰마다 어절 번호('|'에서 늘어난다)."""
    out, w = [], 0
    for t in tokens:
        if t == "|":
            w += 1
        out.append(w)
    return out


def signal_metrics(x: np.ndarray, sr: int, phones: Optional[Sequence[Dict]] = None,
                   tokens: Optional[Sequence[str]] = None) -> Dict:
    """문서 1.3절 신호 측정. phones·tokens(정렬 결과, 같은 순서)가 있으면 모음 끊김·쉼·꼬리·빠르기 구간도 잰다."""
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
        widx = _token_word_index(tokens)
        # 음절 = 중성 하나. group_jamo_by_syllable과 같은 묶음으로 음절의 첫 자모 시작·마지막 자모 끝을 구한다
        import sound_clips as S
        groups = S.group_jamo_by_syllable(list(tokens))
        spans = []
        for g in groups:
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
                out["sps"] = round(n / max(1e-3, (last - first) / 1000.0), 3)       # 음절/초(문장 묶음)
                out["ms_per_syl"] = round((last - first) / n, 1)                    # 음절당 ms(낱말 묶음)
    return out


def length_group(n_syl: int, key: str) -> str:
    if n_syl >= 5 or " " in key.strip():
        return "sent"
    return "one" if n_syl <= 1 else "word"


def rate_value(m: Dict, group: str) -> Optional[float]:
    """길이 묶음의 빠르기 값(문장 음절/초, 낱말 음절당 ms, 한 음절 말소리 구간 ms)."""
    if group == "one":
        return m.get("speech_ms")
    return m.get("sps") if group == "sent" else m.get("ms_per_syl")


def robust_ref(values: Sequence[float]) -> Optional[Tuple[float, float]]:
    v = np.asarray([x for x in values if x is not None], dtype=np.float64)
    if v.size < 5:
        return None
    med = float(np.median(v))
    mad = float(np.median(np.abs(v - med)))
    return med, max(mad, 1e-6)


def robust_z(x: Optional[float], ref: Optional[Tuple[float, float]]) -> Optional[float]:
    if x is None or ref is None:
        return None
    return 0.6745 * (x - ref[0]) / ref[1]


# ── 발음 비교 ─────────────────────────────────────────────────────────────
_MERGE = {"ㅐ": "ㅔ", "ㅒ": "ㅖ", "ㅙ": "ㅚ", "ㅞ": "ㅚ"}


def pron_seq(text: str) -> List[str]:
    """숫자 읽기 → 한글만 → 띄어쓰기 없앰 → 소리 나는 대로 자모열(모음 합류는 같은 자모)."""
    from korean_numbers import normalize_numbers
    from scoring import to_pronounced_jamos
    t = unicodedata.normalize("NFC", text or "")
    try:
        t = normalize_numbers(t)
    except Exception:
        pass
    t = re.sub(r"[^가-힣]", "", t)
    if not t:
        return []
    out = []
    for i, m, f in to_pronounced_jamos(t):
        out += [i or "∅", _MERGE.get(m, m), f or "·"]
    return out


def edit_distance(a: Sequence, b: Sequence) -> int:
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
            prev = cur
    return d[len(b)]


def per(target: str, hyp: str) -> Optional[float]:
    r = pron_seq(target)
    if not r:
        return None
    return edit_distance(r, pron_seq(hyp)) / len(r)


def hangul_count(t: str) -> int:
    return len(re.findall(r"[가-힣]", t or ""))


def has_non_hangul_word(t: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", t or ""))


# ── 판정(문서 2절) ────────────────────────────────────────────────────────

def judge_pron(group: str, per_v: Optional[float], S: Optional[float], hyp: str) -> Tuple[str, str]:
    """(등급, 사유)."""
    if S is None:
        return "fail", "dgop_none"
    if group == "sent":
        if per_v is None:
            return "fail", "per_none"
        if per_v == 0:
            return "pass", ""
        if per_v >= 0.15 or S < 80:
            return "fail", "asr_mismatch"
        return "suspect", "asr_minor"
    if group == "word":
        if per_v == 0:
            return ("pass", "") if S >= 45 else ("suspect", "dgop_low")
        return ("fail", "asr_mismatch") if S < 70 else ("suspect", "asr_mismatch_dgop_ok")
    # 한 음절
    usable = hangul_count(hyp) == 1 and not has_non_hangul_word(hyp)
    if usable:
        if per_v == 0:
            return ("pass", "") if S >= 30 else ("suspect", "dgop_low")
        return ("fail", "asr_mismatch") if S < 60 else ("suspect", "asr_mismatch_dgop_ok")
    if S >= 60:
        return "pass", ""
    return ("suspect", "dgop_mid_asr_unusable") if S >= 40 else ("fail", "dgop_low_asr_unusable")


def judge_signal(m: Dict, group: str, rate_z: Optional[float], level_dev: Optional[float], check_pad: bool) -> List[Tuple[str, str]]:
    """[(등급, 항목)] — 의심·실패만."""
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


def combine(pron: Tuple[str, str], sig: List[Tuple[str, str]], syl_ok: Tuple[bool, str]) -> Dict:
    flags = []
    tier = pron[0]
    if pron[0] != "pass":
        flags.append((pron[0], "pron:" + pron[1]))
    for t, f in sig:
        flags.append((t, f))
        if RANK[t] > RANK[tier]:
            tier = t
    if not syl_ok[0]:
        flags.append(("fail", syl_ok[1]))
        tier = "fail"
    return {"tier": tier, "n_suspect": sum(1 for t, _ in flags if t == "suspect"),
            "flags": [f"{t}:{f}" for t, f in flags]}


def select_key(r: Dict) -> Tuple:
    """문서 3.1 선택 키(작을수록 좋다)."""
    return (RANK[r["tier"]], r["n_suspect"], r.get("per") if r.get("per") is not None else 9.0,
            -(r.get("dgop") if r.get("dgop") is not None else -1.0),
            abs(r["rate_z"]) if r.get("rate_z") is not None else 0.0)


# ── 정리(문서 5절) ───────────────────────────────────────────────────────

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
    info.update({"gain_db": round(gain_db, 2), "peak_limited_db": round(limited, 2), "pad_pre": pre, "pad_post": post})
    return y.astype(np.float32), info


# ── 점검 대상 목록 ───────────────────────────────────────────────────────

def load_targets(path: str) -> List[Dict]:
    import json
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def iter_items(targets: Sequence[Dict], cands: Sequence[str], clips_dir: str, cand_root: str):
    """(uid, 후보, 소리 경로). 후보 'orig'는 저장소 클립(clips_dir/<orig_id>.ogg), 나머지는 cand_root/<후보>/<uid>.wav.
    파일이 없는 것은 건너뛴다."""
    for c in cands:
        for t in targets:
            if c == "orig":
                if not t.get("orig_id"):
                    continue
                p = os.path.join(clips_dir, t["orig_id"] + ".ogg")
            else:
                p = os.path.join(cand_root, c, t["uid"] + ".wav")
            if os.path.exists(p):
                yield t["uid"], c, p


def read_jsonl(paths) -> List[Dict]:
    import json
    out = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out


# ── 자체 시험 ─────────────────────────────────────────────────────────────

def selftest():
    sr = 16000
    rng = np.random.default_rng(0)
    t = np.arange(int(0.5 * sr)) / sr
    tone = 0.1 * np.sin(2 * np.pi * 200 * t)
    x = np.concatenate([np.zeros(int(0.3 * sr)), tone, np.zeros(int(0.05 * sr)), tone, np.zeros(int(0.2 * sr))])
    L = db(active_level(x, sr))
    plain = db(float(np.sqrt(np.mean(x ** 2))))
    rms_tone = db(0.1 / math.sqrt(2))
    assert abs(L - rms_tone) < 1.5, (L, rms_tone)
    assert L > plain + 0.5, (L, plain)         # 무음을 빼므로 전체 RMS보다 크다
    sp = speech_span(x, sr, L)
    assert abs(sp[0] - 300) <= 10 and abs((len(x) / sr * 1000 - sp[1]) - 200) <= 10, sp
    y, info = postprocess(x + 1e-5 * rng.standard_normal(len(x)), sr)
    m = signal_metrics(y, sr)
    assert abs(m["lead_ms"] - PAD_MS) <= 10 and abs(m["tail_ms"] - PAD_MS) <= 10, m
    assert abs(m["level_db"] - TARGET_DBFS) < 0.3, m
    loud, _ = postprocess(np.concatenate([np.zeros(800), 0.9 * np.sign(tone), np.zeros(800)]), sr)
    assert np.max(np.abs(loud)) <= 10 ** (PEAK_CEIL_DBFS / 20) + 1e-6
    # 발음 비교: 표기만 다른 같은 소리, 띄어쓰기, 모음 합류, 숫자
    assert per("가방에 지퍼가 고장 났어", "가방에 지퍼가 고장났어.") == 0
    assert per("달이 밝아요", "다리 밝아요") == 0
    assert per("굳이", "구지") == 0
    assert per("애", "에") == 0
    assert per("사과 3개", "사과 세 개") == 0
    assert per("고", "코") > 0
    assert per("점심 뭐 먹지?", "잠시만 먹지?") > 0.15
    # 판정 표
    assert judge_pron("sent", 0.0, 50, "")[0] == "pass"
    assert judge_pron("sent", 0.05, 85, "")[0] == "suspect"
    assert judge_pron("sent", 0.05, 70, "")[0] == "fail"
    assert judge_pron("sent", 0.2, 95, "")[0] == "fail"
    assert judge_pron("word", 0.0, 50, "")[0] == "pass"
    assert judge_pron("word", 0.0, 40, "")[0] == "suspect"
    assert judge_pron("word", 0.3, 69, "")[0] == "fail"
    assert judge_pron("word", 0.3, 75, "")[0] == "suspect"
    assert judge_pron("one", 0.0, 23.9, "아")[0] == "suspect"
    assert judge_pron("one", 0.0, 31, "아.")[0] == "pass"
    assert judge_pron("one", 0.4, 36, "코")[0] == "fail"
    assert judge_pron("one", 0.4, 65, "코")[0] == "suspect"
    assert judge_pron("one", 0.4, 65, "poor")[0] == "pass"
    assert judge_pron("one", 0.4, 45, "그럼")[0] == "suspect"
    assert judge_pron("one", 0.4, 35, "")[0] == "fail"
    assert judge_pron("sent", 0.0, None, "")[0] == "fail"
    assert syl_valid([[100, 200], [200, 300]], 2, 400)[0]
    assert not syl_valid([[100, 200]], 2, 400)[0]
    assert not syl_valid([[100, 200], [90, 300]], 2, 400)[0]
    assert not syl_valid([[100, 200], [200, 500]], 2, 400)[0]
    c = combine(("pass", ""), [("suspect", "burst")], (True, ""))
    assert c["tier"] == "suspect" and c["n_suspect"] == 1
    a = {"tier": "pass", "n_suspect": 0, "per": 0.0, "dgop": 90, "rate_z": 0.5}
    b = {"tier": "pass", "n_suspect": 0, "per": 0.0, "dgop": 85, "rate_z": 0.1}
    assert select_key(a) < select_key(b)
    print("QA_RULES_SELFTEST_OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
