"""
개방형 타이핑 답의 엄격 음소 정답률(종합 계획 P20의 선행 작업, docs/pilot/typed-scoring-check.md 3절).

P3 주결과(실제 얼굴 개방형 문장 음소 정답률)와 P20(사람 채점자 2명과의 일치도)에 쓰는 **분석용** 함수다. 앱 화면 채점
(`scoring.calculate_score`)·숙달·복습에는 쓰지 않는다. main.py는 이 모듈을 가져오지 않는다(test_phoneme_accuracy가 확인한다).

정의(문서 3절을 따른다)
- 정답과 답을 '소리 나는 대로'의 자모열(`engine.to_pronounced_syllables`, 입모양 규칙: 연음·구개음화·격음화·겹받침·ㅎ 탈락)로 바꾼다.
- 음절 정렬은 문서 2.3의 `scoring.align_visual`과 같은 동적 계획법이다(음절 유사도 0.35·0.45·0.2, 같은 입모양 무리 0.8, 건너뛰기 0점,
  같은 점수면 짝짓지 않음). 아래의 '허용 변이'가 없으면 `align_visual`과 같은 짝을 낸다.
- 짝지은 음절 안에서 같은 자리(초성·중성·종성)의 자모가 같으면 맞음이다. 분모는 정답 쪽 음소만 센다. 초성(무음 ㅇ 제외), 중성(이중모음은
  한 단위), 종성(있을 때). 덧붙인 말은 감점하지 않는다(사람 채점 규칙 R6).
- 낱말 정답률은 정답 원문의 어절(띄어쓰기와 문장 부호로 나눔)마다 그 어절의 음절이 모두 짝지어지고 세 자리가 모두 맞을 때 맞음이다.
  발음 규칙은 음절 수를 바꾸지 않으므로 발음열의 음절을 원문 어절에 되돌려 붙일 수 있다. 연음으로 앞 낱말 받침이 뒤 낱말 첫소리로
  옮겨 가면 그 음소는 뒤 낱말에서 센다(발음열 기준).
- 입모양 음소 정답률(보조 지표)은 같거나 같은 입모양 무리이면 맞음으로 센다.

문서 2절의 세 동작은 이렇게 처리한다
(가) 공백·문장 부호: 답은 모든 공백(전각·줄 바꿈 없는 공백·탭·줄 바꿈)과 문장 부호를 지운 뒤 채점한다(bab5a4e의 앱 채점과 같다).
    답의 띄어쓰기는 결과에 영향을 주지 않는다(R1, R5). 정답의 띄어쓰기는 어절 경계로만 쓴다.
(나) 낱말 경계의 연음: 정답 발음열의 기준은 표준 발음법 15항이다. 앞 어절이 받침으로 끝나고 뒤 어절이 모음으로 시작하면 받침을 대표음
    (ㄱ·ㄴ·ㄷ·ㄹ·ㅁ·ㅂ)으로 바꾼 뒤 옮긴다("옷 입어" → [오디버], "닭 앞" → [다갑]). 답은 띄어쓰기를 지워 채점하므로 띄어 쓴 "옷 입어"와
    붙여 쓴 "옷입어"가 모두 [오시버]가 된다. 그래서 그 자리에는 철자대로 연음한 소리([오시버]의 ㅅ, "닭앞"의 [달갑])도 맞음으로 받는다.
    분모는 표준 발음 쪽(대표음 연음)으로 센다. ㄴ 첨가 사전에 걸려 받침이 남는 자리와 받침 ㅎ은 이 규칙을 걸지 않는다.
(다) 완성되지 않은 낱자(ㅂ, ㅅㅏ): 기본값 loose_jamo="drop"은 문서 4절 R4의 '결과 전에 정한 차이'대로 버리고 그 수만 n_loose_jamo로 알린다.
    loose_jamo="compose"는 R4(그 자리의 음소를 친 것으로 인정)를 따른다. 자음+모음(+받침)은 한 음절로 합치고("ㅅㅏ과" → 사과), 홀로 친 자음은
    모음을 모르는 음절의 첫소리로, 홀로 친 모음은 첫소리 없는 음절로 둔다. 문서 7절 2항의 '한 번만 고치는' 후보로 쓸 수 있게 둔 선택이다.

그 밖의 알려진 차이(사람 채점의 발음 열쇠와 다를 수 있는 곳)
- 비음화·경음화·평파열음화는 입모양 규칙이 아니라 엔진이 적용하지 않는다. "국물"을 "궁물"로 친 답은 받침이 틀린 것으로 센다.
  sound_rules=True면 엔진의 소리 규칙 경로(phonetic=True) 발음도 맞음으로 받는다(분모는 그대로).
- 낱말 경계의 ㄴ 첨가(표준 발음법 29항 붙임, "옷 입다"[온닙따])는 엔진 사전에 있는 말만 따른다.
- 철자대로 연음한 소리를 그대로 받아 적은 답("오시버")도 맞음으로 받는다. 엄격한 발음 열쇠로는 틀림일 수 있다.

**순수 함수**만 둔다.
"""
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from engine import VISEME_MAP, decompose_hangul, to_pronounced_syllables
from korean_numbers import normalize_numbers
from scoring import VISUAL_SAME_GROUP, VISUAL_WEIGHTS, _strip_separators

SCORER_VERSION = "strict-v1"
LOOSE_JAMO_MODES = ("drop", "compose")

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
         "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
# 두 낱모음을 이어 친 이중모음(키보드 입력 순서)
_VOWEL_JOIN = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ",
               ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}
_PLACEHOLDER_VOWEL = "ㅡ"   # 홀로 친 자음에 잠시 붙이는 모음(연음 등 규칙을 돌린 뒤 '모음 모름'으로 지운다)

# 받침의 대표음(표준 발음법 9·10·11항). 낱말 경계 연음(15항)에서 옮겨 가는 소리
_REPRESENTATIVE = {
    "ㄱ": "ㄱ", "ㄲ": "ㄱ", "ㅋ": "ㄱ", "ㄳ": "ㄱ", "ㄺ": "ㄱ",
    "ㄴ": "ㄴ", "ㄵ": "ㄴ", "ㄶ": "ㄴ",
    "ㄷ": "ㄷ", "ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅊ": "ㄷ", "ㅌ": "ㄷ",
    "ㄹ": "ㄹ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㅀ": "ㄹ",
    "ㅁ": "ㅁ", "ㄻ": "ㅁ",
    "ㅂ": "ㅂ", "ㅍ": "ㅂ", "ㄿ": "ㅂ", "ㅄ": "ㅂ",
}
_TARGET_SPLIT = re.compile(r"[\s\W_]+")

Syl = Tuple[Optional[str], Optional[str], Optional[str]]   # (초성, 중성, 종성). 무음 초성·받침 없음은 '', 친 적 없는 자리는 None


class _TargetSyl:
    """정답 음절 하나: 기준 발음(분모를 정함)과 자리마다 맞음으로 받는 자모 집합."""
    __slots__ = ("key", "ok", "word")

    def __init__(self, key: Tuple[str, str, str], word: int):
        self.key = key
        self.ok = [{key[0]}, {key[1]}, {key[2]}]
        self.word = word

    def counted(self) -> List[int]:
        """분모에 드는 자리(0 초성, 1 중성, 2 종성)."""
        return [k for k in (0, 1, 2) if k == 1 or self.key[k]]


def _is_cons(ch: str) -> bool:
    return "ㄱ" <= ch <= "ㅎ"


def _is_vowel(ch: str) -> bool:
    return "ㅏ" <= ch <= "ㅣ"


def _compose(cho: str, jung: str, jong: str = "") -> str:
    return chr(0xAC00 + (_CHO.index(cho) * 21 + _JUNG.index(jung)) * 28 + _JONG.index(jong))


def _syl_text(s: Syl) -> str:
    """기록용 표기. 무음 초성은 ㅇ, 모음을 모르는 음절은 친 자음만."""
    o, v, c = s
    if v is None:
        return o or "ㅇ"
    try:
        return _compose(o or "ㅇ", v, c or "")
    except ValueError:
        return f"{o}{v}{c}"


def _pronounce(text: str, phonetic: bool = False) -> List[Tuple[str, str, str]]:
    """한글 음절만 (초성, 중성, 종성) 튜플로. 한글이 아닌 토큰은 버린다(scoring.to_pronounced_jamos와 같다)."""
    return [tuple(s) for s in to_pronounced_syllables(text, phonetic=phonetic) if isinstance(s, (list, tuple)) and len(s) == 3]


def _n_hangul(text: str) -> int:
    return sum(1 for ch in text if "가" <= ch <= "힣")


# ── 정답 쪽 ─────────────────────────────────────────────────────────

def target_syllables(target: str, sound_rules: bool = False) -> Tuple[List[str], List[_TargetSyl]]:
    """정답 → (어절 목록, 정답 음절 목록). 어절은 공백과 문장 부호로 나누고, 숫자는 먼저 한국어 읽기로 바꾼다."""
    text = normalize_numbers(unicodedata.normalize("NFC", target or ""))
    words = [w for w in _TARGET_SPLIT.split(text) if _n_hangul(w)]
    joined = "".join(words)
    base = _pronounce(joined)
    if len(base) != _n_hangul(joined):   # 발음 규칙은 음절 수를 바꾸지 않는다. 바뀌면 어절 대응을 믿을 수 없다
        raise ValueError(f"발음열 음절 수가 원문과 다름: {target!r}")
    sylls: List[_TargetSyl] = []
    first_idx: List[int] = []
    for wi, w in enumerate(words):
        first_idx.append(len(sylls))
        sylls.extend(_TargetSyl(base[len(sylls)], wi) for _ in range(_n_hangul(w)))

    # (나) 낱말 경계 연음: 표준 발음(대표음 연음)을 기준으로, 철자대로 연음한 소리도 받는다
    for wi in range(1, len(words)):
        prev_word, next_word = words[wi - 1], words[wi]
        last_ch = next((ch for ch in reversed(prev_word) if "가" <= ch <= "힣"), None)
        if not ("가" <= prev_word[-1] <= "힣") or not ("가" <= next_word[0] <= "힣"):
            continue   # 한글 사이가 아니면(영문 등) 엔진도 연음하지 않는다
        _, _, coda = decompose_hangul(last_ch)
        onset, _, _ = decompose_hangul(next_word[0])
        if onset != "ㅇ" or coda in ("", "ㅇ", "ㅎ") or coda not in _REPRESENTATIVE:
            continue
        p, n = sylls[first_idx[wi] - 1], sylls[first_idx[wi]]
        if p.key[2] == coda or not n.key[0]:
            continue   # 엔진이 연음하지 않은 자리(ㄴ 첨가 사전 등)
        rep = _REPRESENTATIVE[coda]
        p.key = (p.key[0], p.key[1], "")
        n.key = (rep, n.key[1], n.key[2])
        p.ok[2].add("")
        n.ok[0].add(rep)

    if sound_rules:
        phon = _pronounce(joined, phonetic=True)
        if len(phon) == len(sylls):
            for s, ph in zip(sylls, phon):
                for k in (0, 2):
                    if ph[k] and s.key[k]:   # 자리의 있고 없음은 바꾸지 않는다(분모 고정)
                        s.ok[k].add(ph[k])
                if ph[1]:
                    s.ok[1].add(ph[1])
    return words, sylls


# ── 답 쪽 ───────────────────────────────────────────────────────────

def _compose_loose(text: str) -> Tuple[str, List[int], int]:
    """완성되지 않은 낱자를 음절로 합친다(loose_jamo='compose'). (새 글, 모음을 모르는 음절의 한글 순번, 버린 낱자 수)."""
    out: List[str] = []
    unknown_vowel: List[int] = []
    dropped = 0
    n_syl = 0
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if _is_cons(ch) and ch in _CHO:
            if i + 1 < n and _is_vowel(text[i + 1]):
                v, j = text[i + 1], i + 2
                if j < n and (v, text[j]) in _VOWEL_JOIN:
                    v, j = _VOWEL_JOIN[(v, text[j])], j + 1
                coda = ""
                if j < n and _is_cons(text[j]) and text[j] in _JONG and not (j + 1 < n and _is_vowel(text[j + 1])):
                    coda, j = text[j], j + 1
                out.append(_compose(ch, v, coda))
                i = j
            else:
                unknown_vowel.append(n_syl)
                out.append(_compose(ch, _PLACEHOLDER_VOWEL))
                i += 1
            n_syl += 1
        elif _is_vowel(ch):
            v, j = ch, i + 1
            if j < n and (v, text[j]) in _VOWEL_JOIN:
                v, j = _VOWEL_JOIN[(v, text[j])], j + 1
            out.append(_compose("ㅇ", v))
            n_syl += 1
            i = j
        else:
            if _is_cons(ch):   # 겹자음 낱자(ㄳ 등)는 첫소리가 될 수 없어 버린다
                dropped += 1
            elif "가" <= ch <= "힣":
                n_syl += 1
            out.append(ch)
            i += 1
    return "".join(out), unknown_vowel, dropped


def answer_syllables(answer: str, loose_jamo: str = "drop") -> Tuple[List[Syl], int]:
    """답 → (답 음절 목록, 버리거나 합친 낱자 수). 공백과 문장 부호는 모두 지운다."""
    if loose_jamo not in LOOSE_JAMO_MODES:
        raise ValueError(f"loose_jamo는 {LOOSE_JAMO_MODES} 중 하나")
    text = normalize_numbers(_strip_separators(unicodedata.normalize("NFC", answer or "")))
    n_loose = sum(1 for ch in text if _is_cons(ch) or _is_vowel(ch))
    if loose_jamo == "drop" or not n_loose:
        return [tuple(s) for s in _pronounce(text)], n_loose
    composed, unknown_vowel, _ = _compose_loose(text)
    sylls: List[Syl] = [tuple(s) for s in _pronounce(composed)]
    for k in unknown_vowel:
        if k < len(sylls):
            o, _, c = sylls[k]
            sylls[k] = (o, None, c)
    return sylls, n_loose


# ── 정렬과 셈 ───────────────────────────────────────────────────────

def _jamo_sim(a: Optional[str], ok: set, key: str) -> float:
    """scoring._visual_jamo_sim을 허용 집합으로 넓힌 것. 집합이 {key} 하나면 같은 값을 낸다."""
    if a is None:
        return 0.0
    if a in ok:
        return 1.0
    if not a or not key:
        return 0.0
    va = VISEME_MAP.get(a)
    return VISUAL_SAME_GROUP if va is not None and any(m and VISEME_MAP.get(m) == va for m in ok) else 0.0


def _coda_sim(a: Optional[str], ok: set) -> float:
    if a is None:
        return 0.0
    if a in ok:
        return 1.0   # 둘 다 받침 없음도 여기
    if not a:
        return 0.0
    va = VISEME_MAP.get(a)
    return VISUAL_SAME_GROUP if va is not None and any(m and VISEME_MAP.get(m) == va for m in ok) else 0.0


def _syl_sim(t: _TargetSyl, u: Syl) -> float:
    wi, wm, wf = VISUAL_WEIGHTS
    return wi * _jamo_sim(u[0], t.ok[0], t.key[0]) + wm * _jamo_sim(u[1], t.ok[1], t.key[1]) + wf * _coda_sim(u[2], t.ok[2])


def _align(target: Sequence[_TargetSyl], user: Sequence[Syl]) -> List[Tuple[Optional[int], Optional[int]]]:
    """scoring.align_visual(chance 0)과 같은 단조 정렬. (정답 순번, 답 순번) 짝 목록."""
    n, m = len(target), len(user)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    bt = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        bt[i][0] = "C"
    for j in range(1, m + 1):
        bt[0][j] = "U"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = dp[i - 1][j - 1] + _syl_sim(target[i - 1], user[j - 1])
            skip_c, skip_u = dp[i - 1][j], dp[i][j - 1]
            if match > skip_c and match > skip_u:
                dp[i][j], bt[i][j] = match, "M"
            elif skip_c >= skip_u:
                dp[i][j], bt[i][j] = skip_c, "C"
            else:
                dp[i][j], bt[i][j] = skip_u, "U"
    pairs: List[Tuple[Optional[int], Optional[int]]] = []
    i, j = n, m
    while i > 0 or j > 0:
        mv = bt[i][j]
        if mv == "M":
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif mv == "C":
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    pairs.reverse()
    return pairs


def _slot_ok(t: _TargetSyl, u: Syl, k: int) -> bool:
    return u[k] is not None and u[k] in t.ok[k]


def _slot_visual(t: _TargetSyl, u: Syl, k: int) -> bool:
    if _slot_ok(t, u, k):
        return True
    a = u[k]
    if not a:
        return False
    va = VISEME_MAP.get(a)
    return va is not None and any(m and VISEME_MAP.get(m) == va for m in t.ok[k])


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 4) if b else None


def strict_phoneme_accuracy(target: str, answer: str, *, loose_jamo: str = "drop", sound_rules: bool = False) -> Dict:
    """정답 문장과 타이핑한 답의 엄격 음소 정답률과 낱말 정답률(docs/pilot/typed-scoring-check.md 3절, 9절).

    반환(비율은 0~1, 분모가 0이면 None)
    - phoneme_accuracy: 맞은 정답 음소 / 정답 음소(n_matched_phonemes / n_target_phonemes)
    - word_accuracy: 맞은 어절 / 어절(n_words_correct / n_words)
    - visual_phoneme_accuracy: 같거나 같은 입모양 무리인 정답 음소 / 정답 음소(보조)
    - n_extra_syllables: 정답과 짝짓지 못한 답 음절 수(덧붙인 말, 감점하지 않음)
    - n_loose_jamo: 답에 있던 완성되지 않은 낱자 수(drop이면 버림, compose면 합침)
    - alignment: 어절마다 {word, key(정답 발음열), answer(짝지은 답 음절, 못 짝지은 자리는 '-'), n, matched, correct}
    회차 점수는 문장 비율의 평균이 아니라 n_matched_phonemes 합 / n_target_phonemes 합으로 낸다(문서 3절).
    """
    words, tsyl = target_syllables(target, sound_rules=sound_rules)
    usyl, n_loose = answer_syllables(answer, loose_jamo=loose_jamo)
    pairs = _align(tsyl, usyl) if usyl else [(i, None) for i in range(len(tsyl))]

    per_word = [{"word": w, "key": "", "answer": "", "n": 0, "matched": 0, "visual": 0, "correct": True} for w in words]
    n_extra = 0
    for ti, ui in pairs:
        if ti is None:
            n_extra += 1
            continue
        t = tsyl[ti]
        row = per_word[t.word]
        row["key"] += _syl_text(t.key)
        counted = t.counted()
        row["n"] += len(counted)
        if ui is None:
            row["answer"] += "-"
            row["correct"] = False
            continue
        u = usyl[ui]
        row["answer"] += _syl_text(u)
        row["matched"] += sum(1 for k in counted if _slot_ok(t, u, k))
        row["visual"] += sum(1 for k in counted if _slot_visual(t, u, k))
        if not all(_slot_ok(t, u, k) for k in (0, 1, 2)):
            row["correct"] = False

    n_t = sum(r["n"] for r in per_word)
    n_m = sum(r["matched"] for r in per_word)
    n_v = sum(r["visual"] for r in per_word)
    n_wc = sum(1 for r in per_word if r["correct"])
    return {
        "phoneme_accuracy": _ratio(n_m, n_t),
        "word_accuracy": _ratio(n_wc, len(words)),
        "visual_phoneme_accuracy": _ratio(n_v, n_t),
        "n_target_phonemes": n_t,
        "n_matched_phonemes": n_m,
        "n_visual_matched": n_v,
        "n_words": len(words),
        "n_words_correct": n_wc,
        "n_extra_syllables": n_extra,
        "n_loose_jamo": n_loose,
        "loose_jamo": loose_jamo,
        "sound_rules": bool(sound_rules),
        "scorer_version": SCORER_VERSION,
        "alignment": [{k: r[k] for k in ("word", "key", "answer", "n", "matched", "correct")} for r in per_word],
    }
