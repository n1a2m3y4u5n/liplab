"""
LIPLAB 콘텐츠 규칙 검사 게이트 — LLM 대량 생성물의 '자동 1차 검수'.

고도화 축 G(콘텐츠 대량화)의 핵심은 "LLM 생성 + 규칙 검사 + 사람 검수"의
이중 게이트다. 이 모듈은 그중 **규칙 검사**를 담당한다. 비심(viseme) 엔진을
그대로 재사용하므로, 채점·애니메이션이 쓰는 것과 동일한 음운 근거로 콘텐츠의
'독화 타당성'을 판정한다. LLM이 낸 라벨(예: same_looking)을 믿지 않고 규칙으로
다시 계산해 덮어쓴다 — 생성기의 환각을 결정론적 근거로 거르는 것이 목적이다.

순수 함수(DB·네트워크 의존 없음) → 결정론적으로 테스트 가능.

핵심 개념
  · viseme 시그니처: 단어에서 '실제로 보이는 입모양'만 뽑은 순열. 두 단어의
    시그니처가 같으면 눈으로는 구별 불가(동구형이음).
  · 최소대립쌍: 자모 한 자리만 다른 두 단어. 그 자리의 두 음소가 같은 입모양
    무리면 same_looking(구별 불가), 다르면 구별 가능.
"""
import math
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from engine import VISEME_MAP, decompose_hangul, to_pronounced_syllables

# 단어 빈도 사전(wordfreq) — 콘텐츠 생성 시 희귀어·비단어를 결정론적으로 거르는 용도.
# 형태소 분석(MeCab) 없이 토큰 빈도 사전만 직접 조회한다. 설치돼 있지 않으면
# HAS_FREQUENCY=False로 두고 빈도 게이트를 건너뛴다(앱 런타임에는 불필요한 선택 의존).
try:
    from wordfreq import get_frequency_dict as _get_freq_dict

    _KO_FREQ: Optional[dict] = None

    def _ko_freq() -> dict:
        global _KO_FREQ
        if _KO_FREQ is None:
            _KO_FREQ = _get_freq_dict("ko")
        return _KO_FREQ

    HAS_FREQUENCY = True
except Exception:  # wordfreq 미설치 등
    HAS_FREQUENCY = False

    def _ko_freq() -> dict:
        return {}


def word_zipf(word: str) -> Optional[float]:
    """단어의 Zipf 빈도(약 1~7, 클수록 흔함). 사전 없으면 None, 미등재면 0.0."""
    if not HAS_FREQUENCY:
        return None
    f = _ko_freq().get(word, 0)
    return round(math.log10(f * 1e9), 2) if f > 0 else 0.0


def is_common_word(word: str, min_zipf: float = 2.5) -> Optional[bool]:
    """단어가 빈도 사전상 일정 이상 흔한지. 사전이 없으면 None(판정 불가 → 통과 취급)."""
    z = word_zipf(word)
    return None if z is None else z >= min_zipf


def tier_of(word: str) -> int:
    """단어 빈도로 학습 난이도 tier를 매긴다(1 쉬움 ~ 3 어려움).
    빈도 사전이 없으면 tier 1로 둔다. 어려운 단어가 섞여도 이 태깅으로 초급자에게
    노출되지 않게 계층화된다(난이도 개인화의 토대)."""
    z = word_zipf(word)
    if z is None:
        return 1
    if z >= 4.5:
        return 1
    if z >= 3.5:
        return 2
    return 3

# 입 안쪽에서 조음되어 서로 거의 구별되지 않는 viseme 무리(동구형이음).
# curriculum.HOMOPHENE_CLUSTERS와 같은 근거지만, 순환 import를 피하려 여기 상수로 둔다.
#   입술 닫힘(1) 안의 ㅂ/ㅃ/ㅍ/ㅁ은 애초에 같은 viseme라 별도 무리가 필요 없다.
#   입 안쪽 자음(6 치경·7 연구개·8 성문·10 경구개)은 viseme는 다르지만
#   겉모습이 거의 같아 하나의 '혼동 무리'로 본다.
_INSIDE_CLUSTER = {6, 7, 8, 10}

# 보이지 않는(휴지·전환·중립) viseme — 시그니처에서 제외
_INVISIBLE_VISEMES = {14, 15}

# 한글 자모 조합용 표(engine.decompose_hangul과 동일 순서) — 자모↔음절 합성에 사용
_INITIALS = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
             "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_MEDIALS = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
            "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"]
_FINALS = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ",
           "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ",
           "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_INI_IDX = {j: i for i, j in enumerate(_INITIALS)}
_MED_IDX = {j: i for i, j in enumerate(_MEDIALS)}
_FIN_IDX = {j: i for i, j in enumerate(_FINALS)}

# viseme id → 같은 그룹 자음들(초성/종성 치환 후보). 동구형이음 파트너 생성에 쓴다.
#   자음 viseme(1 양순·6 치경·7 연구개·8 성문·10 경구개)만 대상으로 한다.
_GROUP_CONSONANTS = {
    1: ["ㅂ", "ㅃ", "ㅍ", "ㅁ"],
    6: ["ㄷ", "ㄸ", "ㅌ", "ㄴ", "ㄹ", "ㅅ", "ㅆ"],
    7: ["ㄱ", "ㄲ", "ㅋ", "ㅇ"],
    8: ["ㅎ"],
    10: ["ㅈ", "ㅉ", "ㅊ"],
}


def compose_syllable(ini: str, med: str, fin: str = "") -> Optional[str]:
    """초성·중성·종성 자모를 완성형 한글 음절 한 글자로 합성. 불가하면 None."""
    if ini not in _INI_IDX or med not in _MED_IDX or (fin or "") not in _FIN_IDX:
        return None
    code = 0xAC00 + (_INI_IDX[ini] * 21 + _MED_IDX[med]) * 28 + _FIN_IDX[fin or ""]
    return chr(code)


def _is_hangul(ch: str) -> bool:
    return "가" <= ch <= "힣"


def is_hangul_word(word: str) -> bool:
    """공백 없는 순수 한글 단어인지."""
    word = word.strip()
    return bool(word) and all(_is_hangul(ch) for ch in word)


def syllable_count(word: str) -> int:
    return sum(1 for ch in word if _is_hangul(ch))


def word_visemes(word: str) -> List[int]:
    """
    단어를 '소리 나는 대로' 변환한 뒤, 실제로 보이는 입모양(viseme id)만 순서대로.

    무음 초성 ㅇ('')과 휴지·중립은 제외한다. 이 순열이 곧 '눈에 보이는 입모양'이며,
    독화 난이도와 동구형이음 판정의 기반이 된다.
    """
    visemes: List[int] = []
    for tok in to_pronounced_syllables(word):
        if not isinstance(tok, list):  # 한글 아님(구두점 등)
            continue
        for jamo in tok:  # [초성, 중성, 종성]
            if not jamo:  # 무음 초성 '' 등
                continue
            vid = VISEME_MAP.get(jamo)
            if vid is None or vid in _INVISIBLE_VISEMES:
                continue
            visemes.append(vid)
    return visemes


def viseme_signature(word: str) -> Tuple[int, ...]:
    """단어의 보이는 입모양 순열(동구형이음 비교용). 같으면 눈으로 구별 불가."""
    return tuple(word_visemes(word))


def looks_identical(a: str, b: str) -> bool:
    """두 단어가 입모양만으로는 완전히 같아 보이는가(동구형이음)."""
    return a != b and viseme_signature(a) == viseme_signature(b)


def _jamo_seq(word: str) -> List[str]:
    """단어를 표기 그대로 자모 순열로 분해([초,중,종] 평탄화, 종성 '' 포함)."""
    seq: List[str] = []
    for ch in word:
        if not _is_hangul(ch):
            return []  # 한글 아닌 문자 있으면 최소대립 판정 대상 아님
        ini, med, fin = decompose_hangul(ch)
        seq.extend([ini, med, fin])
    return seq


def same_viseme_group(p: str, q: str) -> bool:
    """두 음소가 같은 입모양(또는 같은 혼동 무리)이라 구별 불가인가."""
    if p == q:
        return True
    vp, vq = VISEME_MAP.get(p), VISEME_MAP.get(q)
    if vp is None or vq is None:
        return False
    if vp == vq:
        return True  # 같은 viseme (예: ㅂ↔ㅁ 둘 다 1)
    return vp in _INSIDE_CLUSTER and vq in _INSIDE_CLUSTER  # 입 안쪽 혼동 무리


def minimal_pair_diff(a: str, b: str) -> Optional[Tuple[str, str, List[int]]]:
    """
    두 단어가 자모 한 자리만 다른 최소대립쌍이면 (음소a, 음소b, 관련 viseme들) 반환.
    아니면 None. 음절수·자모 길이가 같아야 하고 정확히 한 자리만 달라야 한다.
    """
    sa, sb = _jamo_seq(a), _jamo_seq(b)
    if not sa or not sb or len(sa) != len(sb):
        return None
    diffs = [(i, sa[i], sb[i]) for i in range(len(sa)) if sa[i] != sb[i]]
    if len(diffs) != 1:
        return None
    _, pa, pb = diffs[0]
    if not pa or not pb:  # 종성 유무 차이(밥/바)는 최소대립으로 보지 않음
        return None
    vis = sorted({v for v in (VISEME_MAP.get(pa), VISEME_MAP.get(pb)) if v is not None})
    return (pa, pb, vis)


# ── 게이트: 각 콘텐츠 유형을 검사해 (통과여부, 정규화된 항목, 사유) 반환 ──────────

def check_word(word: str, min_syllable: int = 1, max_syllable: int = 3) -> Tuple[bool, Optional[Dict], str]:
    """단어 후보 1건 검사. tier(시각 난이도)는 규칙으로 자동 판정한다."""
    word = (word or "").strip()
    if not is_hangul_word(word):
        return False, None, "한글이 아닌 문자 포함"
    n = syllable_count(word)
    if not (min_syllable <= n <= max_syllable):
        return False, None, f"음절수 {n} 범위 밖({min_syllable}~{max_syllable})"
    vis = word_visemes(word)
    if not vis:
        return False, None, "보이는 입모양이 없음(전부 무음/휴지)"
    # tier는 단어 빈도로 자동 산정한다(1 쉬움 ~ 3 어려움). 빈도 사전이 없으면 1.
    return True, {"word": word, "tier": tier_of(word)}, "ok"


def check_lookalike_pair(a: str, b: str, claimed_same_looking: Optional[bool] = None
                         ) -> Tuple[bool, Optional[Dict], str]:
    """
    교육용 단어쌍 후보 검사. 독화 교육에서 유효한 쌍은 두 종류다.
      · 동구형이음 쌍(relation="homophene"): 보이는 입모양 순열이 완전히 같아
        눈으로는 구별 불가(밥/맘 [1,2,1]). same_looking=True.
      · 최소대립쌍(relation="minimal_pair"): 자모 한 자리만 다름. 그 자리의 두
        음소가 같은 입모양 무리면 same_looking=True(달/탈), 아니면 False(우유/이유).
    둘 다 아니면(부분만 겹치거나 완전히 다름) 교육쌍으로 부적합해 탈락시킨다.

    same_looking은 LLM 주장을 믿지 않고 규칙으로 재계산한다. claimed_same_looking을
    주면 규칙 판정과 어긋나는 경우를 사유에 함께 기록한다.
    """
    a, b = (a or "").strip(), (b or "").strip()
    if not (is_hangul_word(a) and is_hangul_word(b)):
        return False, None, "한글이 아닌 단어"
    if a == b:
        return False, None, "두 단어가 동일"

    diff = minimal_pair_diff(a, b)
    if looks_identical(a, b):
        relation = "homophene"
        same_look = True
        vis = sorted(set(word_visemes(a)))
        note = "입모양 순열이 완전히 같아 구별 불가(동구형이음)"
    elif diff is not None:
        pa, pb, vis = diff
        relation = "minimal_pair"
        same_look = same_viseme_group(pa, pb)
        note = f"{pa}↔{pb} " + ("입모양 동일(구별 불가)" if same_look else "입모양 다름(구별 가능)")
    else:
        return False, None, "동구형이음도 최소대립쌍도 아님(교육쌍으로 부적합)"

    item = {"a": a, "b": b, "visemes": vis, "same_looking": same_look,
            "relation": relation, "note": note}
    if claimed_same_looking is not None and claimed_same_looking != same_look:
        return True, item, f"통과(단, LLM 주장 same_looking={claimed_same_looking}을 규칙값 {same_look}로 교정)"
    return True, item, "ok"


def lookalike_candidates(word: str) -> List[str]:
    """
    seed 단어에서 '입모양이 같은 다른 음소'로 초성·종성 자음을 한 자리씩 치환한
    후보 음절열을 생성한다. 예: 밥 → 맙·팝(초성), 밤·밮(종성). 이 후보 중 실제
    존재하는 단어만 LLM이 걸러내면(파이프라인 몫), same_looking=True 동구형이음
    쌍이 확실히 확보된다. 중성(모음)은 입모양이 도드라져 동구형이음이 아니므로 건드리지 않는다.
    """
    if not is_hangul_word(word):
        return []
    chars = list(word)
    out = set()
    for ci, ch in enumerate(chars):
        ini, med, fin = decompose_hangul(ch)
        # 초성 치환(무음 ㅇ 제외)
        if ini and ini != "ㅇ":
            vid = VISEME_MAP.get(ini)
            for alt in _GROUP_CONSONANTS.get(vid, []):
                if alt == ini or alt == "ㅇ":
                    continue
                syl = compose_syllable(alt, med, fin)
                if syl:
                    cand = "".join(chars[:ci]) + syl + "".join(chars[ci + 1:])
                    if cand != word:
                        out.add(cand)
        # 종성 치환(받침이 있을 때만)
        if fin:
            vid = VISEME_MAP.get(fin)
            for alt in _GROUP_CONSONANTS.get(vid, []):
                if alt == fin or alt == "ㅇ":
                    continue
                syl = compose_syllable(ini, med, alt)
                if syl:
                    cand = "".join(chars[:ci]) + syl + "".join(chars[ci + 1:])
                    if cand != word:
                        out.add(cand)
    return sorted(out)


def discover_pairs(words: List[str]) -> List[Dict]:
    """
    단어 풀에서 '눈으로 헷갈리는' 교육쌍을 규칙만으로 자동 발굴한다.
    LLM은 단어를 잘 내기만 하면 되고, 쌍의 음운 관계는 여기서 결정론적으로 보증한다.

    두 종류를 캔다.
      · 동구형이음(homophene): 보이는 입모양 순열이 완전히 같은 무리(밥/맘·물/불).
      · 최소대립쌍(minimal_pair): 자모 한 자리만 다른 쌍(달/탈·우유/이유).
    한 쌍이 둘 다에 해당하면(예: 물/불) 더 강한 정보인 동구형이음으로 분류한다.

    효율을 위해 버킷팅을 쓴다. 동구형이음은 시그니처로, 최소대립은 자모열의
    한 자리를 와일드카드로 치운 키로 묶어 O(단어수)에 가깝게 후보를 모은다.
    """
    seen = set()
    uniq = []
    for w in words:
        w = (w or "").strip()
        if w and w not in seen and is_hangul_word(w):
            seen.add(w)
            uniq.append(w)

    pairs: List[Dict] = []
    paired = set()  # frozenset({a,b}) 중복 방지

    # 1) 동구형이음: 같은 시그니처 버킷
    sig_bucket: Dict[Tuple[int, ...], List[str]] = defaultdict(list)
    for w in uniq:
        sig = viseme_signature(w)
        if sig:
            sig_bucket[sig].append(w)
    for ws in sig_bucket.values():
        if len(ws) < 2:
            continue
        for a, b in combinations(ws, 2):
            key = frozenset((a, b))
            if key in paired:
                continue
            ok, item, _ = check_lookalike_pair(a, b)
            if ok and item["relation"] == "homophene":
                pairs.append(item)
                paired.add(key)

    # 2) 최소대립: 자모열 한 자리 와일드카드 버킷
    wc_bucket: Dict[tuple, List[str]] = defaultdict(list)
    for w in uniq:
        seq = _jamo_seq(w)
        if not seq:
            continue
        for k in range(len(seq)):
            key = (len(seq), k, tuple(seq[:k]) + ("*",) + tuple(seq[k + 1:]))
            wc_bucket[key].append(w)
    for ws in wc_bucket.values():
        if len(ws) < 2:
            continue
        for a, b in combinations(sorted(set(ws)), 2):
            key = frozenset((a, b))
            if key in paired:
                continue
            ok, item, _ = check_lookalike_pair(a, b)
            if ok and item["relation"] == "minimal_pair":
                pairs.append(item)
                paired.add(key)

    return pairs


def select_personalized(words: List[Dict], pairs: List[Dict], closures: List[Dict],
                        target_visemes: List[int], level: int = 5,
                        n_words: int = 10, n_pairs: int = 8, n_closures: int = 5) -> Dict:
    """
    지식추적이 고른 표적 음소(target_visemes)와 난이도(level)에 맞춰 콘텐츠를 개인화 선별.
    표적 viseme를 많이 포함하고 tier가 난이도 이하인 것을 앞세운다(정렬만, 필터 아님 →
    콘텐츠가 적어도 항상 무언가는 돌려준다).
    """
    tv = set(target_visemes or [])

    def w_key(w: Dict):
        hits = len(set(word_visemes(w["word"])) & tv)
        over = 1 if w.get("tier", 1) > level else 0  # 난이도 초과는 뒤로
        return (-hits, over, w.get("tier", 1), w["word"])

    def p_key(p: Dict):
        hits = len(set(p.get("visemes", [])) & tv)
        return (-hits, 0 if p.get("same_looking") else 1)  # 표적 많고 '헷갈리는' 쌍 우선

    def c_key(c: Dict):
        hits = len(set(word_visemes(c.get("answer", ""))) & tv)
        return (-hits, c.get("id", ""))

    return {
        "words": sorted(words, key=w_key)[:n_words],
        "pairs": sorted(pairs, key=p_key)[:n_pairs],
        "closures": sorted(closures, key=c_key)[:n_closures],
    }


def _visually_confusable(answer: str, other: str) -> bool:
    """두 단어가 '눈으로 구별되지 않을' 만큼 시각적으로 혼동되는가.

    같은 입모양 순열(동구형이음)이거나, 한 음소만 다른 최소대립쌍이되 그 차이 나는 두 음소가
    같은 입모양이거나 둘 다 '입 안쪽 무리{6,7,8,10}'라 눈으로 못 가르는 경우만 True.
    (밥/발처럼 차이 음소가 양순1↔치경6로 눈에 뻔히 보이면 False — 문맥 문항 오답으로 부적합.)
    """
    if looks_identical(answer, other):
        return True
    mp = minimal_pair_diff(answer, other)
    if mp is None:
        return False
    _, _, vis = mp                      # (음소1, 음소2, [viseme1, viseme2])
    v1, v2 = vis[0], vis[1]
    return v1 == v2 or (v1 in _INSIDE_CLUSTER and v2 in _INSIDE_CLUSTER)


def check_closure(display: str, answer: str, options: List[str]
                  ) -> Tuple[bool, Optional[Dict], str]:
    """
    문맥 추론(closure) 문항 검사. 보기(오답)가 정답과 '비슷하게 보여야'
    문맥으로 판단하는 훈련이 성립한다. 눈으로 뻔히 구별되면 문항이 무의미하다.
    """
    answer = (answer or "").strip()
    options = [str(o).strip() for o in (options or []) if str(o).strip()]
    if "___" not in (display or ""):
        return False, None, "display에 빈칸(___) 없음"
    if not is_hangul_word(answer):
        return False, None, "정답이 한글 단어가 아님"
    if answer not in options:
        return False, None, "정답이 보기 목록에 없음"
    if len(options) < 3:
        return False, None, "보기가 3개 미만(2지선다는 추측 확률 50%로 문맥 훈련이 약함)"
    distractors = [o for o in options if o != answer and is_hangul_word(o)]
    if not distractors:
        return False, None, "유효한 오답 보기가 없음"
    # 오답 중 최소 둘은 정답과 '눈으로 구별 안 되게' 혼동되어야 한다. 하나만 헷갈리면
    # 나머지를 소거해 사실상 2지선다가 되므로 2개 이상을 요구한다.
    confusable = [o for o in distractors if _visually_confusable(answer, o)]
    if len(confusable) < 2:
        return False, None, "정답과 시각적으로 혼동되는 오답이 2개 미만(문맥 문항으로 약함)"
    item = {"display": display.strip(), "answer": answer, "options": options}
    return True, item, "ok"
