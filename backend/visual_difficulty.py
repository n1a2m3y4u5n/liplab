"""
시각 난이도(독화 난이도) 계산. 단어나 문장이 입모양만으로 얼마나 읽기 어려운지를 규칙으로 잰다.

쓰임
  · 2단계 단어 문항: 쉬운 단어부터 내고, 오답 보기에서 동구형이음(입모양이 완전히 같은 단어)을 뺀다.
  · 상황별 시나리오 문장: LLM이 만든 문장을 난이도 단계별 허용 구간으로 거르고 순위를 매긴다.

순수 함수와 데이터만 둔다(DB·네트워크 없음). 입모양은 앱과 같은 경로로 뽑는다.
engine.to_pronounced_syllables(소리 나는 대로, 기본 viseme 모드)를 거친 content_rules.word_visemes를
그대로 쓰므로, 채점·게이트·아바타와 같은 음운 근거를 공유한다. AI Hub 데이터에서 계산한 값
(자모 시각유사도, c_jamo_similarity.json, c4_data_derived.json)은 쓰지 않는다. 규칙과 커리큘럼 라벨만 쓴다.

1. 가시성 등급. curriculum.VISEME_LESSONS의 visibility 라벨을 읽어 만든다(아래는 현재 값).
     high   (잘 보임, 가중 0)       1 양순음 ㅂㅃㅍㅁ · 2 개방모음 ㅏㅐㅑㅒ · 3 전설모음 ㅣㅔㅖ · 4 원순모음 ㅗㅛㅜㅠ
     medium (어느 정도 보임, 0.5)   5 중설모음 ㅓㅕㅡ · 9 이중모음 ㅘㅙㅚㅝㅞㅟㅢ
     low    (거의 안 보임, 1)       6 치경음 ㄷㄸㅌㄴㄹㅅㅆ · 7 연구개음 ㄱㄲㅋ(받침 ㅇ 포함) · 8 성문음 ㅎ · 10 경구개음 ㅈㅉㅊ
   가중 (0, 0.5, 1)은 perceptual._VIS_WEIGHT와 같다. 무음 초성 ㅇ과 휴지·전환 프레임(11~15)은 세지 않는다.

2. 이웃(주어진 어휘 안에서 센다).
     동구형이음(homophene)   보이는 입모양 순열이 완전히 같은 다른 단어. 입만 보고는 원리적으로 못 가른다.
     준동구형(near)          입 안쪽 무리(curriculum.HOMOPHENE_CLUSTERS의 inside: 6·7·8·10)를 한 부류로 합치면
                             같아지는 단어. 앱이 '서로 거의 구별 불가'로 가르치는 차이만 있는 경우다.
     최소대립(minimal pair)  입모양 순열의 길이가 같고 정확히 한 자리만 다른 단어(삽입·삭제는 세지 않는다).
     보이는 최소대립         최소대립 중 그 한 자리가 입 안쪽 무리끼리의 차이가 아닌 것. 눈으로 가를 수 있다.

3. 점수(0 쉬움 ~ 1 어려움). 네 성분을 0~1로 맞춘 뒤 가중합한다.
     D = 0.35·I + 0.30·H + 0.20·M + 0.15·B
       I = 안 보이는 정도: 보이는 입모양 토큰의 가시성 가중 평균(low 비중 + 0.5 × medium 비중)
       H = h / (h + 1): h는 동구형이음 수. 첫 번째 동구형이음이 생기는 순간 단독 식별이 불가능해지므로
           반포화점을 1로 둔다(1개면 0.5, 3개면 0.75).
       M = m / (m + 3): m은 최소대립 수. 한 자리 차이는 그 자리가 잘 보이면 가를 수 있어 H보다 약하게 본다.
           최소대립은 동구형이음보다 흔해 반포화점을 3으로 둔다.
       B = 1 / 음절 수: 음절이 적을수록 보이는 단서(입모양 수)가 적다. 짧은 단어는 이미 H·M이 크게
           잡히므로 가중을 가장 작게 둔다.
   가중의 근거: 단어를 눈으로 식별하지 못하게 만드는 가장 직접적인 원인은 같은 모양의 다른 단어(H)이고,
   그다음이 토큰 단위의 가시성(I)이다. I는 모든 단어에서 계산되고 어휘와 무관해 가장 크게 두었다.
   가중 합은 1이고 각 성분이 0~1이라 D도 0~1이다. D는 I·h·m에 대해 증가, 음절 수에 대해 감소한다(단조).
   어휘를 주지 않으면 h = m = 0으로 계산한다(가시성과 길이만 반영).

   문장은 같은 식을 문장 단위로 모아 쓴다. I는 문장 전체 토큰에 대해, H·M·B는 어절별 값을 평균한다.
   어절의 이웃은 어휘에 어절이 없고 조사를 뗀 어간이 있으면 어간으로 찾는다(밥을 → 밥).
   문장의 길이(어절 수)는 점수에 넣지 않고 단계별 허용 구간(SCENARIO_BANDS)에서 따로 본다.
   점수는 밀도(길이와 무관한 평균)라서, 긴 문장일수록 평균에 모여 분산이 줄어든다는 점을 구간 설계에 반영했다.
"""
import math
import random
import unicodedata
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import curriculum as _cur
from content_rules import is_hangul_word, word_visemes

# ── 1. 가시성 등급: 커리큘럼 라벨에서 읽는다 ─────────────────────────────────────
VISIBILITY_CLASS: Dict[int, str] = {l["viseme_id"]: l["visibility"] for l in _cur.VISEME_LESSONS}
VISIBILITY_WEIGHT: Dict[str, float] = {"high": 0.0, "medium": 0.5, "low": 1.0}

# 입 안쪽 자음 무리(치경·연구개·성문·경구개). 준동구형과 '보이는 최소대립' 판정에 쓴다.
INSIDE_CLUSTER = frozenset(
    next(c["viseme_ids"] for c in _cur.HOMOPHENE_CLUSTERS if c["id"] == "inside"))
_INSIDE_REP = min(INSIDE_CLUSTER)   # 무리를 합칠 때 대표 번호(6)

# ── 3. 점수 가중 ─────────────────────────────────────────────────────────────
W_INVISIBILITY = 0.35
W_HOMOPHENE = 0.30
W_MINIMAL = 0.20
W_BREVITY = 0.15
HOMOPHENE_HALF = 1.0   # H = h / (h + 1)
MINIMAL_HALF = 3.0     # M = m / (m + 3)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _is_syllable(ch: str) -> bool:
    return "가" <= ch <= "힣"


def syllable_count(text: str) -> int:
    """한글 음절 수(공백·기호·숫자 제외)."""
    return sum(1 for ch in _nfc(text) if _is_syllable(ch))


def eojeols(text: str) -> List[str]:
    """문장을 어절로 나눈다. 어절 안의 한글 음절만 남기고, 한글이 없는 토큰은 버린다."""
    out = []
    for tok in _nfc(text).split():
        t = "".join(ch for ch in tok if _is_syllable(ch))
        if t:
            out.append(t)
    return out


def viseme_sequence(text: str) -> Tuple[int, ...]:
    """소리 나는 대로 바꾼 뒤 보이는 입모양(viseme 1~10) 순열. 앱의 word_visemes와 같다.
    공백은 연음을 끊으므로(엔진 규칙) 문장을 통째로 넣어도 어절별 결과를 이은 것과 같다."""
    return tuple(word_visemes(_nfc(text)))


def cluster_sequence(seq: Sequence[int]) -> Tuple[int, ...]:
    """입 안쪽 무리(6·7·8·10)를 한 부류(6)로 합친 순열. 같으면 준동구형이다."""
    return tuple(_INSIDE_REP if v in INSIDE_CLUSTER else v for v in seq)


def visibility_profile(seq: Sequence[int]) -> Dict[str, float]:
    """입모양 순열의 가시성 구성. high/medium/low 비중과 안 보이는 정도(invisibility)."""
    n = len(seq)
    if n == 0:
        return {"high": 0.0, "medium": 0.0, "low": 0.0, "invisibility": 0.0}
    cnt = {"high": 0, "medium": 0, "low": 0}
    for v in seq:
        cnt[VISIBILITY_CLASS.get(v, "medium")] += 1
    inv = sum(VISIBILITY_WEIGHT[k] * c for k, c in cnt.items()) / n
    return {"high": round(cnt["high"] / n, 4), "medium": round(cnt["medium"] / n, 4),
            "low": round(cnt["low"] / n, 4), "invisibility": round(inv, 4)}


def low_visibility_share(text: str) -> float:
    """보이는 입모양 토큰 중 low 등급(입 안쪽 자음) 비중."""
    return visibility_profile(viseme_sequence(text))["low"]


def viseme_distance(a, b) -> float:
    """두 입모양 순열(또는 텍스트) 사이의 가중 편집거리. assessment.viseme_distance와 같은 비용이다.
    치환: 같은 입모양 0, 둘 다 입 안쪽 무리 0.5, 그 외 1. 삽입·삭제 1."""
    sa = viseme_sequence(a) if isinstance(a, str) else tuple(a)
    sb = viseme_sequence(b) if isinstance(b, str) else tuple(b)
    prev = [float(j) for j in range(len(sb) + 1)]
    for i in range(1, len(sa) + 1):
        cur = [float(i)] + [0.0] * len(sb)
        for j in range(1, len(sb) + 1):
            x, y = sa[i - 1], sb[j - 1]
            sub = 0.0 if x == y else (0.5 if (x in INSIDE_CLUSTER and y in INSIDE_CLUSTER) else 1.0)
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + sub)
        prev = cur
    return prev[-1]


# ── 2. 어휘 색인: 동구형이음·최소대립 이웃을 바로 찾는다 ─────────────────────────
class VocabIndex:
    """어휘 목록의 입모양 색인. 한 번 만들어 두고 여러 단어·문장에 재사용한다.

    순열 → 단어, 합친 순열 → 단어, (자리, 앞, 뒤) → 단어 세 가지 버킷을 둔다.
    마지막 버킷은 한 자리를 비운 열쇠라서 최소대립 이웃을 전수 비교 없이 찾는다."""

    def __init__(self, vocab: Iterable[str]):
        words: List[str] = []
        seen = set()
        for w in vocab:
            w = _nfc((w or "").strip())
            if w and w not in seen and is_hangul_word(w):
                seen.add(w)
                words.append(w)
        self.words = words
        self._set = set(words)
        self.seq: Dict[str, Tuple[int, ...]] = {}
        self.syl: Dict[str, int] = {}
        self._by_seq: Dict[Tuple[int, ...], List[str]] = defaultdict(list)
        self._by_cluster: Dict[Tuple[int, ...], List[str]] = defaultdict(list)
        self._by_slot: Dict[tuple, List[str]] = defaultdict(list)
        for w in words:
            s = viseme_sequence(w)
            self.seq[w] = s
            self.syl[w] = syllable_count(w)
            if not s:
                continue
            self._by_seq[s].append(w)
            self._by_cluster[cluster_sequence(s)].append(w)
            for i in range(len(s)):
                self._by_slot[(i, s[:i], s[i + 1:])].append(w)

    def __contains__(self, word: str) -> bool:
        return word in self._set

    def __len__(self) -> int:
        return len(self.words)

    def _seq_of(self, word: str) -> Tuple[int, ...]:
        return self.seq[word] if word in self.seq else viseme_sequence(word)

    def homophenes(self, word: str) -> List[str]:
        """입모양 순열이 완전히 같은 다른 단어."""
        s = self._seq_of(word)
        return [w for w in self._by_seq.get(s, ()) if w != word] if s else []

    def near_homophenes(self, word: str) -> List[str]:
        """입 안쪽 무리 안의 차이만 있는 단어(동구형이음은 제외)."""
        s = self._seq_of(word)
        if not s:
            return []
        return [w for w in self._by_cluster.get(cluster_sequence(s), ())
                if w != word and self.seq[w] != s]

    def minimal_pairs(self, word: str) -> List[str]:
        """입모양 순열이 한 자리만 다른 단어(길이 같음)."""
        s = self._seq_of(word)
        out: List[str] = []
        seen = set()
        for i in range(len(s)):
            for w in self._by_slot.get((i, s[:i], s[i + 1:]), ()):
                if w != word and w not in seen and self.seq[w] != s:
                    seen.add(w)
                    out.append(w)
        return out

    def visible_minimal_pairs(self, word: str) -> List[str]:
        """최소대립 중 차이 나는 자리가 눈으로 보이는 것(입 안쪽 무리끼리의 차이가 아님)."""
        cs = cluster_sequence(self._seq_of(word))
        return [w for w in self.minimal_pairs(word) if cluster_sequence(self.seq[w]) != cs]


def _as_index(vocab) -> Optional[VocabIndex]:
    if vocab is None or isinstance(vocab, VocabIndex):
        return vocab
    return VocabIndex(vocab)


def homophene_neighbors(word: str, vocab) -> List[str]:
    """어휘(list 또는 VocabIndex) 안의 동구형이음."""
    idx = _as_index(vocab)
    return idx.homophenes(_nfc(word)) if idx else []


def minimal_pair_neighbors(word: str, vocab) -> List[str]:
    """어휘(list 또는 VocabIndex) 안의 최소대립(입모양 한 자리 차이)."""
    idx = _as_index(vocab)
    return idx.minimal_pairs(_nfc(word)) if idx else []


# ── 3. 점수 ─────────────────────────────────────────────────────────────────
def combine_score(invisibility: float, homophene_term: float, minimal_term: float,
                  brevity: float) -> float:
    """성분(각 0~1)을 가중합한 난이도. 모듈 설명의 식 그대로다."""
    d = (W_INVISIBILITY * invisibility + W_HOMOPHENE * homophene_term
         + W_MINIMAL * minimal_term + W_BREVITY * brevity)
    return round(max(0.0, min(1.0, d)), 4)


def homophene_term(n_homophenes: int) -> float:
    return n_homophenes / (n_homophenes + HOMOPHENE_HALF)


def minimal_term(n_minimal: int) -> float:
    return n_minimal / (n_minimal + MINIMAL_HALF)


def brevity_term(n_syllables: int) -> float:
    return 1.0 / n_syllables if n_syllables > 0 else 1.0


def score_from_features(invisibility: float, n_homophenes: int, n_minimal: int,
                        n_syllables: int) -> float:
    """원 특징(안 보이는 정도, 동구형이음 수, 최소대립 수, 음절 수)에서 바로 점수."""
    return combine_score(invisibility, homophene_term(n_homophenes),
                         minimal_term(n_minimal), brevity_term(n_syllables))


def word_difficulty(word: str, vocab=None) -> Optional[Dict]:
    """단어 하나의 특징과 점수. vocab은 단어 목록이나 VocabIndex(없으면 이웃 0).
    한글 단어가 아니거나 보이는 입모양이 없으면 None."""
    word = _nfc((word or "").strip())
    if not is_hangul_word(word):
        return None
    seq = viseme_sequence(word)
    if not seq:
        return None
    idx = _as_index(vocab)
    prof = visibility_profile(seq)
    homs = idx.homophenes(word) if idx else []
    mins = idx.minimal_pairs(word) if idx else []
    n_syl = syllable_count(word)
    return {
        "word": word,
        "visemes": list(seq),
        "syllables": n_syl,
        "low_share": prof["low"],
        "medium_share": prof["medium"],
        "invisibility": prof["invisibility"],
        "homophenes": homs,
        "n_homophenes": len(homs),
        "near_homophenes": idx.near_homophenes(word) if idx else [],
        "minimal_pairs": mins,
        "n_minimal_pairs": len(mins),
        "visible_minimal_pairs": idx.visible_minimal_pairs(word) if idx else [],
        "score": score_from_features(prof["invisibility"], len(homs), len(mins), n_syl),
    }


# 어절에서 뗄 조사·어미(긴 것부터). 어휘에 어간이 있을 때만 뗀다(아이 → 아 같은 오분리를 막는다).
_PARTICLES = sorted([
    "에서는", "에게서", "으로는", "이라도", "이에요", "입니다", "에서", "에게", "한테", "까지", "부터",
    "처럼", "보다", "하고", "으로", "이랑", "이나", "이야", "예요", "이고", "은요", "는요",
    "을", "를", "이", "가", "은", "는", "도", "만", "에", "의", "와", "과", "로", "랑", "요", "야",
], key=len, reverse=True)


def lookup_key(eojeol: str, index: Optional[VocabIndex]) -> str:
    """이웃을 찾을 열쇠. 어절이 어휘에 없고 조사를 뗀 어간이 있으면 어간, 아니면 어절 그대로."""
    if index is None or eojeol in index:
        return eojeol
    for p in _PARTICLES:
        if eojeol.endswith(p) and len(eojeol) > len(p):
            stem = eojeol[: -len(p)]
            if stem in index:
                return stem
    return eojeol


def sentence_difficulty(text: str, vocab=None) -> Optional[Dict]:
    """문장의 특징과 점수. I는 문장 전체 토큰으로, H·M·B는 어절 평균으로 계산한다.
    보이는 입모양이 없으면 None."""
    text = _nfc(text or "").strip()
    words = eojeols(text)
    seq: List[int] = []
    for w in words:
        seq.extend(viseme_sequence(w))
    if not seq:
        return None
    idx = _as_index(vocab)
    prof = visibility_profile(seq)
    per = []
    for w in words:
        key = lookup_key(w, idx)
        n_h = len(idx.homophenes(key)) if idx else 0
        n_m = len(idx.minimal_pairs(key)) if idx else 0
        per.append({"eojeol": w, "key": key, "n_homophenes": n_h, "n_minimal_pairs": n_m,
                    "syllables": syllable_count(w)})
    k = len(per)
    h_mean = sum(homophene_term(p["n_homophenes"]) for p in per) / k
    m_mean = sum(minimal_term(p["n_minimal_pairs"]) for p in per) / k
    b_mean = sum(brevity_term(p["syllables"]) for p in per) / k
    return {
        "text": text,
        "n_eojeol": k,
        "syllables": sum(p["syllables"] for p in per),
        "chars": len(text),
        "visemes": seq,
        "low_share": prof["low"],
        "medium_share": prof["medium"],
        "invisibility": prof["invisibility"],
        "homophene_eojeol_share": round(sum(1 for p in per if p["n_homophenes"] > 0) / k, 4),
        "homophene_term": round(h_mean, 4),
        "minimal_term": round(m_mean, 4),
        "brevity": round(b_mean, 4),
        "score": combine_score(prof["invisibility"], h_mean, m_mean, b_mean),
        "eojeols": per,
    }


def difficulty(text: str, vocab=None) -> Optional[Dict]:
    """어절이 하나면 단어 점수, 둘 이상이면 문장 점수(같은 식, 문장 단위 집계)."""
    ws = eojeols(text)
    if len(ws) == 1 and _nfc(text).strip() == ws[0]:
        return word_difficulty(ws[0], vocab)
    return sentence_difficulty(text, vocab)


def score_vocabulary(words: Iterable[str], vocab=None) -> Dict[str, Dict]:
    """단어 목록 전체의 난이도. vocab을 안 주면 words 자신을 어휘로 쓴다."""
    words = list(dict.fromkeys(_nfc(w.strip()) for w in words if w))
    idx = _as_index(vocab) if vocab is not None else VocabIndex(words)
    out = {}
    for w in words:
        d = word_difficulty(w, idx)
        if d:
            out[w] = d
    return out


def quantile_ranks(scores: Dict[str, float]) -> Dict[str, float]:
    """점수를 0~1 분위 순위로(동점은 평균 순위). 적응형 출제에서 난이도 위치로 쓴다."""
    items = sorted(scores.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 0:
        return {}
    if n == 1:
        return {items[0][0]: 0.5}
    out: Dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        q = ((i + j) / 2) / (n - 1)
        for t in range(i, j + 1):
            out[items[t][0]] = round(q, 4)
        i = j + 1
    return out


# ── 2단계 문항: 오답 보기 구성과 적응형 출제 ────────────────────────────────────
def distractor_kind(target, candidate) -> str:
    """오답 후보가 정답과 어떤 관계인지.
      homophene       입모양 완전 동일(입만 보고는 못 맞힘, 보기에서 항상 뺀다)
      near_homophene  입 안쪽 무리 차이뿐(앱 스스로 '구별 불가'로 가르침, 역시 뺀다)
      minimal_pair    한 자리만 다르고 그 차이가 보인다(어려운 문항용)
      close           그 밖에 거리 2 미만(한 자리 삽입·삭제 등)
      distinct        거리 2 이상(쉬운 문항용)"""
    s = viseme_sequence(target) if isinstance(target, str) else tuple(target)
    t = viseme_sequence(candidate) if isinstance(candidate, str) else tuple(candidate)
    if s == t:
        return "homophene"
    if cluster_sequence(s) == cluster_sequence(t):
        return "near_homophene"
    if len(s) == len(t) and sum(1 for x, y in zip(s, t) if x != y) == 1:
        return "minimal_pair"
    return "close" if viseme_distance(s, t) < 2 else "distinct"


# ── 2단계 주관식(단어 입력) 채점(커리큘럼 개선 계획 1-2) ─────────────────────────
TYPED_CREDIT = {"correct": 1.0, "homophene": 0.5, "wrong": 0.0, "empty": 0.0}


def normalize_typed(text: str) -> str:
    """입력 정리: NFC로 맞추고 한글 음절만 남긴다. 띄어쓰기('바 다')와 문장부호('바다.')는 채점에서 보지 않는다."""
    return "".join(ch for ch in _nfc(text) if _is_syllable(ch))


def typed_word_verdict(target: str, typed: str) -> Dict:
    """주관식 단어 답 채점. verdict와 숙달에 넣을 성공 정도(credit)를 돌려준다.
      correct    정리한 입력이 정답과 같다(1)
      homophene  다른 말이지만 보이는 입모양 순열이 정답과 똑같다: '입모양은 맞음'(0.5). 입만 보고는 원리적으로 못 가르는
                 차이라 오답으로 보지 않는다. 받침 오타도 입모양이 같으면(값/갑, 갓/갇, 국물/궁물) 여기에 든다. 단어 은행에 있는
                 말인지는 따지지 않는다(입모양을 바르게 읽었는지를 본다).
      wrong      입모양이 다르다(받침 오타라도 밥/반처럼 입모양이 바뀌면 오답)(0)
      empty      한글 음절이 없다(0)"""
    ans = normalize_typed(typed)
    tgt = normalize_typed(target)
    if not ans:
        verdict = "empty"
    elif ans == tgt:
        verdict = "correct"
    elif viseme_sequence(ans) == viseme_sequence(tgt):
        verdict = "homophene"
    else:
        verdict = "wrong"
    return {"verdict": verdict, "credit": TYPED_CREDIT[verdict], "answer": ans}


# 보기 단계별 구성: (보이는 최소대립 수, 뚜렷이 다른 단어 수)
OPTION_MIX = {1: (0, 3), 2: (1, 2), 3: (3, 0)}


def classify_pool(target: str, index: VocabIndex) -> Dict[str, List[str]]:
    """어휘 전체를 정답 기준으로 다섯 부류로 나눈다(정답 자신은 제외)."""
    s = index._seq_of(target)
    out: Dict[str, List[str]] = {k: [] for k in
                                 ("homophene", "near_homophene", "minimal_pair", "close", "distinct")}
    for w in index.words:
        if w == target:
            continue
        out[distractor_kind(s, index.seq.get(w, ()))].append(w)
    return out


def pick_distractors(target: str, index: VocabIndex, level: int = 1,
                     rng: Optional[random.Random] = None, k: int = 3,
                     classes: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """정답에 맞는 오답 보기 k개. 동구형이음·준동구형은 어떤 단계에서도 넣지 않는다.
      level 1: 뚜렷이 다른 단어만(입모양 거리 2 이상)
      level 2: 보이는 최소대립 1 + 뚜렷이 다른 단어 2
      level 3: 보이는 최소대립 3(모자라면 close, 그다음 distinct로 채움)
    각 부류 안에서는 정답과 음절 수가 같은 단어를 먼저 써서, 길이만 보고 답을 고르지 않게 한다."""
    rng = rng or random.Random()
    cls = classes if classes is not None else classify_pool(target, index)
    n_syl = syllable_count(target)
    syl = index.syl

    def take(cands: List[str], n: int, used: List[str]) -> List[str]:
        if n <= 0:
            return []
        used_set = set(used)
        same = [w for w in cands if w not in used_set and syl.get(w) == n_syl]
        picked = rng.sample(same, min(n, len(same)))
        if len(picked) < n:
            other = [w for w in cands if w not in used_set and syl.get(w) != n_syl]
            picked += rng.sample(other, min(n - len(picked), len(other)))
        return picked

    n_min, _ = OPTION_MIX.get(level, OPTION_MIX[1])
    chosen: List[str] = []
    chosen += take(cls["minimal_pair"], n_min, chosen)
    if len(chosen) < n_min:
        chosen += take(cls["close"], n_min - len(chosen), chosen)
    for bucket in ("distinct", "close", "minimal_pair"):
        if len(chosen) >= k:
            break
        chosen += take(cls[bucket], k - len(chosen), chosen)
    return chosen[:k]


def option_level(mastered: bool) -> int:
    """보기 단계. 숙달 전에는 2(보이는 최소대립 1개 + 입모양이 다른 단어 2개), 숙달 뒤에는 3(보이는 최소대립 3개).
    2단계의 목표가 최소대립 구별이라 숙달은 최소대립이 든 보기로 판정한다. 정답률로 보기 단계를 오르내리면
    숙달 판정(최근 가중 정답률 85, main._ewma_mastery)이 흔들리거나(잘하면 어려워져 떨어지고) 쉬운 보기만으로
    숙달되는 문제가 있어, 진행 상태(숙달 여부)로만 정한다. 동구형이음은 어느 단계에도 넣지 않는다."""
    return 3 if mastered else 2


def next_target_quantile(n_answers: int, start: float = 0.15, step: float = 0.01, hi: float = 0.9) -> float:
    """다음에 낼 단어의 난이도 위치(0~1 분위). 2단계에서 답한 수에 따라 쉬운 쪽에서 어려운 쪽으로 옮긴다
    (처음 0.15, 한 문항마다 0.01, 약 75문항에 0.9). 정답률 목표(예: 75%)에 맞춰 난이도를 조절하면 정답률이 그
    목표에 묶여 숙달 문턱(85)에 닿지 못하고, 반대로 약한 학습자는 쉬운 단어로만 숙달되므로 쓰지 않는다."""
    return round(min(hi, start + step * max(0, int(n_answers or 0))), 4)


def serve_weight(q: float, target_q: float, sigma: float = 0.1, w_max: int = 29) -> int:
    """표집 가중(정수, 1 이상). 난이도 위치 q가 목표 위치에 가까울수록 크다(최대 1 + w_max).
    프론트가 priority로 가중 표집하므로(0이면 1로 취급) 최소값을 1로 둔다. w_max 29면 문항의 약 80%가
    목표 위치 ±0.15 분위 안에서 나온다(480단어 풀 기준 시뮬레이션)."""
    g = math.exp(-0.5 * ((q - target_q) / sigma) ** 2)
    return 1 + int(round(w_max * g))


class Stage2Table:
    """2단계 서빙 풀의 정적 표(점수·분위·보기 부류). 풀이 바뀌지 않으면 한 번만 만들어 재사용한다.
    보기 부류는 단어마다 풀 전체와 거리를 재야 해서(480단어 기준 약 1.5초) 처음 쓸 때 계산해 둔다."""

    def __init__(self, pool_words: Iterable[str]):
        self.index = VocabIndex(pool_words)
        self.words = [w for w in self.index.words if self.index.seq.get(w)]
        info = score_vocabulary(self.words, self.index)
        self.score = {w: info[w]["score"] for w in self.words}
        self.quantile = quantile_ranks(self.score)
        self._classes: Dict[str, Dict[str, List[str]]] = {}

    def classes(self, word: str) -> Dict[str, List[str]]:
        if word not in self._classes:
            self._classes[word] = classify_pool(word, self.index)
        return self._classes[word]


def stage2_plan(table: Stage2Table, n_answers: int = 0, mastered: bool = False,
                weak_visemes: Iterable[int] = (), rng: Optional[random.Random] = None) -> Dict:
    """2단계 한 레슨의 출제 계획. 엔드포인트가 이 결과를 그대로 내려주면 된다.
      option_level     숙달 여부로 정한 보기 단계(2 또는 3, option_level 참고)
      target_quantile  답한 수로 정한 목표 난이도 위치(next_target_quantile 참고)
      words            단어마다 priority(목표 위치에 가까울수록 큼, 약점 비심 포함 시 1.5배),
                       difficulty, quantile, distractors(동구형이음을 뺀 오답 3개)"""
    rng = rng or random.Random()
    level = option_level(mastered)
    target_q = next_target_quantile(n_answers)
    weak = set(weak_visemes or ())
    words = []
    for w in table.words:
        pri = serve_weight(table.quantile[w], target_q)
        if weak and weak & set(table.index.seq[w]):
            pri = max(pri + 1, int(round(pri * 1.5)))   # 약점 비심 포함 단어를 더 자주(바닥값 1도 2로)
        words.append({"word": w, "priority": pri, "difficulty": table.score[w],
                      "quantile": table.quantile[w],
                      "distractors": pick_distractors(w, table.index, level, rng, classes=table.classes(w))})
    return {"option_level": level, "target_quantile": target_q, "words": words}


# ── 시나리오 문장: 단계별 허용 구간 ──────────────────────────────────────────────
# 어절 수는 llm_service의 단계 지시(1: 5~8, 2: 7~10, 3: 10~13, 4: 12~15, 5: 15 이상)를 양쪽 1어절씩 넓혔다.
# 점수 구간은 저장소의 자연 문장(대체 문장·대화 대사·말하기 문장)을 이어 붙여 단계 어절 수에 맞춘 분포에서
# 단계별로 받아들일 몫을 정해 잡았다: 1 쉬운 60%, 2 쉬운 75%, 3 가운데 70%, 4 어려운 65%, 5 어려운 50%.
# 자연 문장은 길이와 상관없이 평균 점수가 약 0.30으로 거의 같고, 길수록 분산만 준다(표준편차 0.063 → 0.038).
# 그래서 시각 난이도는 자연스러운 범위 안에서만 조절할 수 있고, 단계 차이의 큰 몫은 여전히 길이와 구조가 맡는다.
# 점수는 어휘 = 커리큘럼 단어 은행(default_vocab_index)으로 잰 값이다. 은행이 크게 바뀌거나 실제 LLM 출력이
# 쌓이면 같은 몫(분위)으로 다시 잡는다(재보정 스크립트: 분석 폴더의 d_scenario_bands.py).
SCENARIO_BANDS: Dict[int, Dict[str, Tuple[float, float]]] = {
    1: {"eojeol": (4, 9), "score": (0.00, 0.32)},
    2: {"eojeol": (6, 11), "score": (0.00, 0.34)},
    3: {"eojeol": (9, 14), "score": (0.25, 0.35)},
    4: {"eojeol": (11, 16), "score": (0.28, 1.00)},
    5: {"eojeol": (14, 99), "score": (0.30, 1.00)},
}
BAND_EOJEOL_UNIT = 2.0   # 적합 거리 1 = 구간 밖 2어절
BAND_SCORE_UNIT = 0.05   # 적합 거리 1 = 구간 밖 점수 0.05(단계 길이에서 약 표준편차 하나)

_DEFAULT_INDEX: Optional[VocabIndex] = None


def default_vocab_index() -> VocabIndex:
    """커리큘럼 단어 은행 전체로 만든 색인(처음 한 번만 만든다). 시나리오 점수의 기준 어휘다."""
    global _DEFAULT_INDEX
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = VocabIndex(w["word"] for w in _cur.WORD_BANK)
    return _DEFAULT_INDEX


def band_distance(n_eojeol: int, score: float, level: int) -> float:
    """단계 구간까지의 거리(0이면 구간 안). 어절 수와 점수가 구간 밖으로 벗어난 만큼을 단위로 나눠 더한다."""
    band = SCENARIO_BANDS.get(level, SCENARIO_BANDS[3])
    e_lo, e_hi = band["eojeol"]
    s_lo, s_hi = band["score"]
    d_len = max(0.0, e_lo - n_eojeol, n_eojeol - e_hi) / BAND_EOJEOL_UNIT
    d_score = max(0.0, s_lo - score, score - s_hi) / BAND_SCORE_UNIT
    return round(d_len + d_score, 4)


def rerank_by_band(sentences: Sequence[str], level: int, vocab=None, keep: int = 5,
                   min_keep: int = 3) -> Tuple[List[str], Dict]:
    """문장 게이트를 통과한 LLM 문장을 단계 구간으로 거르고 순위를 매긴다.
      · 구간 안 문장을 최대 keep개 남긴다.
      · 구간 안 문장이 min_keep보다 적으면 구간에 가장 가까운 문장으로 min_keep개까지 채운다
        (대체 문장으로 넘어가지 않는다).
      · 입력이 min_keep보다 적으면 그대로 돌려준다(부족 판정은 호출부의 기존 규칙이 맡는다).
    고른 문장은 원래 순서를 지킨다. 두 번째 반환값은 기록용 요약이다."""
    idx = default_vocab_index() if vocab is None else _as_index(vocab)
    rows = []
    for i, s in enumerate(sentences):
        d = sentence_difficulty(s, idx)
        if d is None:
            continue
        rows.append({"i": i, "text": s, "n_eojeol": d["n_eojeol"], "score": d["score"],
                     "distance": band_distance(d["n_eojeol"], d["score"], level)})
    in_band = [r for r in rows if r["distance"] == 0]
    if len(rows) < min_keep:
        chosen = rows
    elif len(in_band) >= min_keep:
        chosen = in_band[:keep]
    else:
        rest = sorted((r for r in rows if r["distance"] > 0), key=lambda r: (r["distance"], r["i"]))
        chosen = in_band + rest[: min_keep - len(in_band)]
    chosen = sorted(chosen, key=lambda r: r["i"])
    report = {"level": level, "considered": len(rows), "in_band": len(in_band), "kept": len(chosen),
              "rows": rows}
    return [r["text"] for r in chosen], report
