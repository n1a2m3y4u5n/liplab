"""음소 칩 값의 후보 변환(맥, 모델 추론 없음). docs/phone-tail-2026-10.md 3절.

정렬기·채점기 로그확률(프레임 × 49)과 목표 토큰열에서 토큰마다 칩 값(0~1)을 낸다. 문장 점수는 바꾸지 않고 칩 값만 바꾸는 후보다.
    K    지금 앱: 정렬기 CTC 구간의 채점기 분포 평균에서 목표 확률
    W3   구간 폭 최소 3프레임: 폭이 3보다 작으면 [시작 − 1, 끝 + 1] 평균
    BN   빈칸 비중 보정: 구간 평균에서 목표 확률 / (1 − 빈칸 확률)
    E1   이웃 프레임 확장: max(K, [시작 − 1, 끝 + 1] 프레임의 목표 확률 최댓값)
    EL   지역 창 확장: max(K, 앞 토큰 구간 끝 다음 ~ 뒤 토큰 구간 시작 전(자기 구간 포함) 프레임의 목표 확률 최댓값)
    V    같은 소리 묶음: 표준 발음상 같은 소리(ㅐ=ㅔ 등, S2 4절의 빼는 대치)의 확률을 목표 확률에 더함
    EV   EL과 V를 함께(지역 창에서 묶음 확률의 최댓값)
    EVG  EV + 경쟁 증거 관문: 지역 창에서 다른 소리(목표·묶음·빈칸·어절 경계·앞뒤 토큰 제외)가 0.5를 넘지 않으면 칩 값을 0.45 아래로 내리지 않음
"""
import numpy as np

CANDIDATES = ("K", "W3", "BN", "E1", "EL", "V", "EV", "EVG")

_EQ_PAIRS = "ㅐ-ㅔ ㅒ-ㅖ ㅖ-ㅔ ㅙ-ㅚ ㅙ-ㅞ ㅚ-ㅞ ㅢ-ㅣ ㅢ-ㅔ"
_Y_GLIDE = "ㅑ-ㅏ ㅕ-ㅓ ㅛ-ㅗ ㅠ-ㅜ ㅒ-ㅐ"
PALATAL = {"o:ㅈ", "o:ㅉ", "o:ㅊ"}
RED = 0.45
ALT_P = 0.5


def _pairs(spec):
    out = {}
    for a, b in (p.split("-") for p in spec.split()):
        out.setdefault("n:" + a, set()).add("n:" + b)
        out.setdefault("n:" + b, set()).add("n:" + a)
    return out


EQ = _pairs(_EQ_PAIRS)
EQ_Y = _pairs(_Y_GLIDE)


def softmax(x):
    x = np.asarray(x, dtype=np.float64)
    e = np.exp(x - x.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


def eq_set(toks, i):
    """토큰 i와 같은 소리로 치는 토큰 묶음(자기 포함). 초성 ㅈ·ㅉ·ㅊ 뒤 y계 반모음 있음·없음도 같다(표준 발음법 5항 다만 1)."""
    t = toks[i]
    s = {t} | EQ.get(t, set())
    if i > 0 and toks[i - 1] in PALATAL:
        s |= EQ_Y.get(t, set())
    return s


def local_window(spans, i, T):
    s, e = spans[i]["start"], spans[i]["end"]
    lo = spans[i - 1]["end"] + 1 if i > 0 else max(0, s - 3)
    hi = spans[i + 1]["start"] - 1 if i + 1 < len(spans) else min(T - 1, e + 3)
    return min(lo, s), max(hi, e)


def chip_values(sp, spans, toks, vocab, scorable, cand):
    """sp: 채점기 softmax(프레임 × V), spans: align_targets 결과, scorable: 토큰마다 칩 대상인지. 반환: 토큰마다 값 또는 None."""
    T = sp.shape[0]
    B = vocab["<pad>"]
    WB = vocab.get("|", -1)
    out = []
    for i, (tk, span) in enumerate(zip(toks, spans)):
        if not scorable[i] or span.get("start") is None:
            out.append(None)
            continue
        s, e = span["start"], span["end"]
        v = vocab[tk]
        mean = sp[s:e + 1].mean(0)
        k = float(mean[v])
        if cand == "K":
            out.append(k)
            continue
        if cand == "W3":
            if e - s + 1 < 3:
                a, b = max(0, s - 1), min(T - 1, e + 1)
                out.append(float(sp[a:b + 1, v].mean()))
            else:
                out.append(k)
            continue
        if cand == "BN":
            den = 1.0 - float(mean[B])
            out.append(k if den < 1e-3 else min(1.0, k / den))
            continue
        if cand == "E1":
            a, b = max(0, s - 1), min(T - 1, e + 1)
            out.append(max(k, float(sp[a:b + 1, v].max())))
            continue
        ids = [v]
        if cand in ("V", "EV", "EVG"):
            ids = sorted({vocab[x] for x in eq_set(toks, i) if x in vocab})
        if cand == "V":
            out.append(min(1.0, float(mean[ids].sum())))
            continue
        lo, hi = local_window(spans, i, T)
        W = sp[lo:hi + 1]
        val = max(min(1.0, float(mean[ids].sum())), float(W[:, ids].sum(1).max()))
        if cand == "EVG" and val < RED:
            excl = set(ids) | {B, WB}
            if i > 0:
                excl.add(vocab.get(toks[i - 1], -1))
            if i + 1 < len(toks):
                excl.add(vocab.get(toks[i + 1], -1))
            m = W.max(0).copy()
            m[[x for x in excl if x >= 0]] = -1.0
            if float(m.max()) <= ALT_P:
                val = RED
        out.append(min(1.0, val))
    return out
