"""개인 혼동 짝(자모 수준)과 짝 탐색 문항(docs/confusion-pair-serving.md).

혼동 짝은 (자리, target 자모, read 자모), 예를 들어 (중성, ㅗ, ㅓ)다. 입모양이 같거나 둘 다 입 안쪽 무리인 짝은 눈으로 가를 수
없어 대상이 아니다(visible_jamo_pair). 대비 단어는 단어의 target 자모를 같은 자리에서 read 자모로 바꾼 실재 단어다(서빙 풀 안,
동구형이음·준동구형 아님).

탐색 문항(5.4-2): 2단계 레슨 12문항 가운데 선다형 1문항을, 후보 짝의 target 자모가 든 단어 + 그 대비 단어가 든 보기로 낸다.
후보 짝이 아직 없으면 풀에서 탐색할 수 있는 짝을 무작위로 골라 기록이 쌓이게 한다. 탐색 문항도 보통 단어 문항이라 숙달에 똑같이
들어간다(보기만 정해져 있다).

DB·네트워크 의존 없는 순수 함수. scripts/confusion_pair_sim.py도 이 규칙을 그대로 쓴다.
"""
import collections
import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import visual_difficulty as V

JAMO_POS = ("초성", "중성", "종성")   # scoring.viseme_confusions의 position 값
_JAMO_LISTS = (tuple("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"),
               tuple("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"),
               ("",) + tuple("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"))
CONFUSION_TOP = 3        # 겨냥할 짝 수
CONFUSION_MIN_COUNT = 2  # 이만큼 나온 짝만
CONFUSION_ROWS = 200     # 최근 오답 행 수
PAIR_MIN_FREQ = 10       # 후보 짝: target·read 자모가 그 자리에서 풀의 이만큼 단어에 나와야 한다
PROBE_OFFER = 3          # 한 번에 내려주는 탐색 문항 수(같은 짝, 다른 단어)

Pair = Tuple[str, str, str]   # (자리, target, read)


def decompose_syllable(ch: str) -> Optional[Tuple[str, str, str]]:
    """한글 음절 → (초성, 중성, 종성). 받침 없으면 종성은 ''. 음절이 아니면 None."""
    if not V._is_syllable(ch):
        return None
    c = ord(ch) - 0xAC00
    return _JAMO_LISTS[0][c // 588], _JAMO_LISTS[1][(c % 588) // 28], _JAMO_LISTS[2][c % 28]


def jamo_slots(word: str) -> List[Tuple[int, str, str]]:
    """단어의 자모 자리 목록 [(음절 번호, 자리 이름, 자모)]. 받침 없는 종성은 넣지 않는다."""
    out = []
    for i, ch in enumerate(V._nfc(word)):
        d = decompose_syllable(ch)
        if d:
            out += [(i, JAMO_POS[j], d[j]) for j in range(3) if d[j]]
    return out


def jamo_viseme(jamo: str, j: int) -> Optional[int]:
    """자모의 입모양 번호(scoring.viseme_confusions와 같은 규칙). 없음(∅)·소리 없는 초성 ㅇ은 None."""
    from engine import DOUBLE_FINAL, VISEME_MAP
    if not jamo or jamo == "∅" or (j == 0 and jamo == "ㅇ"):
        return None
    return VISEME_MAP.get(DOUBLE_FINAL.get(jamo, jamo) if j == 2 else jamo, 15)


def visible_jamo_pair(position: str, target: str, read: str) -> bool:
    """두 자모를 눈으로 가를 수 있나. 입모양이 같거나 둘 다 입 안쪽 무리면 False(same_viseme와 같은 판정).
    기록된 same_viseme는 규칙이 바뀌기 전 값일 수 있어 지금 규칙으로 다시 본다."""
    if position not in JAMO_POS or not target or target == read:
        return False
    j = JAMO_POS.index(position)
    vt, vr = jamo_viseme(target, j), jamo_viseme(read, j)
    if vt == vr:
        return False
    return not (vt in V.INSIDE_CLUSTER and vr in V.INSIDE_CLUSTER)


def jamo_diffs(target: str, other: str) -> List[Pair]:
    """두 말을 음절 번호로 맞대어 target 자모가 다른 자리 [(자리, target 자모, other 자모 또는 ∅)].
    scoring.viseme_confusions와 같은 정렬이다(짧은 쪽 길이까지, target 받침이 없으면 종성은 보지 않는다)."""
    target, other = V._nfc(target or ""), V._nfc(other or "")
    out: List[Pair] = []
    for i in range(min(len(target), len(other))):
        t, o = decompose_syllable(target[i]), decompose_syllable(other[i])
        if t is None:
            continue
        for j in range(3):
            tj = t[j]
            oj = o[j] if o else None
            if tj and tj != oj:
                out.append((JAMO_POS[j], tj, oj or "∅"))
    return out


def confusion_pairs(rows: Iterable, top: int = CONFUSION_TOP, min_count: int = CONFUSION_MIN_COUNT,
                    trial_targets: Optional[Sequence[str]] = None) -> List[Dict]:
    """오답 행들의 confusions(최신순)에서 눈으로 가를 수 있는 (자리, target, read) 짝을 세어 min_count번 이상인 상위 top개.
    기본은 횟수순(같으면 먼저, 즉 최근에 나온 짝이 앞). trial_targets(같은 기간 전체 시행의 정답 단어)를 주면
    횟수 / 그 자리에 target 자모가 든 시행 수(비율)순으로 고른다. 반환: [{position, target, read, count}]
    보기를 모르고 세는 규칙이라 재현율이 5~8%였다(5.3절). 보기 기록이 있으면 opportunity_pairs를 쓴다."""
    cnt: Dict[Pair, int] = {}
    for confusions in rows:
        for cf in (confusions or []):
            if not isinstance(cf, dict) or cf.get("same_viseme"):
                continue
            key = (cf.get("position"), cf.get("target"), cf.get("read"))
            if visible_jamo_pair(*key):
                cnt[key] = cnt.get(key, 0) + 1
    order = {k: i for i, k in enumerate(cnt)}
    keys = [k for k, c in cnt.items() if c >= min_count]
    if trial_targets is not None:
        seen: Dict[Tuple[str, str], int] = {}
        for w in trial_targets:
            for pt in {(p, j) for _, p, j in jamo_slots(w or "")}:
                seen[pt] = seen.get(pt, 0) + 1
        rate = {k: cnt[k] / max(1, seen.get(k[:2], 0), cnt[k]) for k in keys}
        best = sorted(keys, key=lambda k: (-rate[k], -cnt[k], order[k]))[:top]
    else:
        best = sorted(keys, key=lambda k: (-cnt[k], order[k]))[:top]
    return [{"position": p, "target": t, "read": r, "count": cnt[(p, t, r)]} for p, t, r in best]


def swap_jamo(word: str, i: int, position: str, read: str) -> Optional[str]:
    """word의 i번째 음절 position 자리를 read 자모로 바꾼 말. 받침 '∅'은 받침을 뺀다. 만들 수 없으면 None."""
    word = V._nfc(word)
    j = JAMO_POS.index(position) if position in JAMO_POS else -1
    d = decompose_syllable(word[i]) if 0 <= i < len(word) else None
    r = "" if read == "∅" else read
    if j < 0 or d is None or r not in _JAMO_LISTS[j] or (j < 2 and not r):
        return None
    parts = list(d)
    parts[j] = r
    code = (_JAMO_LISTS[0].index(parts[0]) * 588 + _JAMO_LISTS[1].index(parts[1]) * 28
            + _JAMO_LISTS[2].index(parts[2]))
    return word[:i] + chr(0xAC00 + code) + word[i + 1:]


def contrast_words(word: str, position: str, target: str, read: str, index: "V.VocabIndex") -> List[str]:
    """대비 단어: word의 target 자모(같은 자리)를 read 자모로 바꾼 실재 단어(index 안). 동구형이음·준동구형은 뺀다."""
    out: List[str] = []
    for i, p, jm in jamo_slots(word):
        if p != position or jm != target:
            continue
        nw = swap_jamo(word, i, position, read)
        if nw and nw != word and nw in index and nw not in out \
                and V.distractor_kind(index._seq_of(word), index._seq_of(nw)) not in ("homophene", "near_homophene"):
            out.append(nw)
    return out


def place_contrast(word: str, distractors: List[str], focus: Sequence[Dict], index: "V.VocabIndex",
                   rng=None, contrast_fn=None) -> List[str]:
    """보기 한 자리를 대비 단어로 둔다. focus 순서대로 word에 대비 단어가 있는 첫 짝을 쓴다. 이미 보기에 있으면 그대로,
    없으면 마지막 자리(숙달 전에는 뚜렷이 다른 단어 자리)를 바꾼다. 대비 단어가 없으면 보기를 바꾸지 않는다."""
    rng = rng or random.Random()
    fn = contrast_fn or (lambda w, p, t, r: contrast_words(w, p, t, r, index))
    for f in focus or ():
        cands = [c for c in fn(word, f["position"], f["target"], f["read"]) if c != word]
        if not cands:
            continue
        if set(cands) & set(distractors):
            return list(distractors)
        out = list(distractors)
        pick = rng.choice(cands)
        if out:
            out[-1] = pick
        else:
            out.append(pick)
        return out
    return list(distractors)


class PairIndex:
    """서빙 풀의 짝별 대비 단어 표. 풀(Stage2Table)이 같으면 한 번만 만든다(430단어에 약 0.3초).
      contrast[(자리, target, read)] = {단어: [대비 단어…]}
      candidates  후보 짝: 같은 자리, 눈으로 가를 수 있음, target·read 자모가 그 자리에서 풀의 PAIR_MIN_FREQ 단어 이상에 나옴
                  (받침 없음 ∅은 받침 없는 음절이 있는 단어 수). read 자모가 드물면 4지선다 보기에 거의 안 나와 기록으로 드러날 수 없다.
      probe_pairs 후보 가운데 풀에 대비 단어가 하나라도 있는 짝(탐색 문항을 낼 수 있는 짝)"""

    def __init__(self, table: "V.Stage2Table", min_freq: int = PAIR_MIN_FREQ):
        self.index = table.index
        self.words = list(table.words)
        freq: collections.Counter = collections.Counter()
        for w in self.words:
            s = {(p, j) for _, p, j in jamo_slots(w)}
            if any(decompose_syllable(ch) and not decompose_syllable(ch)[2] for ch in w):
                s.add(("종성", "∅"))
            freq.update(s)
        common = {k for k, c in freq.items() if c >= min_freq}
        self.candidates: List[Pair] = sorted(
            (p, t, r) for (p, t) in common if t != "∅"
            for (p2, r) in common if p2 == p and r != t and visible_jamo_pair(p, t, r))
        cand = set(self.candidates)
        self.contrast: Dict[Pair, Dict[str, List[str]]] = collections.defaultdict(dict)
        for w in self.words:
            for i, p, jm in jamo_slots(w):
                j = JAMO_POS.index(p)
                for r in _JAMO_LISTS[j]:
                    r = r or "∅"
                    if (p, jm, r) not in cand:
                        continue
                    nw = swap_jamo(w, i, p, r)
                    if not nw or nw == w or nw not in self.index:
                        continue
                    if V.distractor_kind(self.index._seq_of(w), self.index._seq_of(nw)) in ("homophene", "near_homophene"):
                        continue
                    lst = self.contrast[(p, jm, r)].setdefault(w, [])
                    if nw not in lst:
                        lst.append(nw)
        self.probe_pairs: List[Pair] = [k for k in self.candidates if self.contrast.get(k)]

    def contrasts(self, word: str, position: str, target: str, read: str) -> List[str]:
        return list(self.contrast.get((position, target, read), {}).get(word, ()))

    def has_contrast(self, word: str, pair: Pair) -> bool:
        return bool(self.contrast.get(pair, {}).get(word))


def probe_items(pidx: PairIndex, focus: Sequence[Dict], priority: Dict[str, float], level: int,
                classes_fn, rng: Optional[random.Random] = None, k: int = PROBE_OFFER) -> List[Dict]:
    """탐색 문항 후보 k개(같은 짝, 서로 다른 단어). focus(후보 짝, 앞이 우선) 가운데 탐색할 수 있는 첫 짝을 쓰고,
    없으면 pidx.probe_pairs에서 무작위로 고른다(후보가 아직 없을 때도 기록이 쌓이게).
    단어는 그 짝의 target 자모가 대비 단어가 있는 자리에 든 단어에서 priority(레슨 출제 가중)로 뽑고, 보기는 보통 규칙
    (pick_distractors, 같은 보기 단계)으로 고른 뒤 한 자리를 대비 단어로 둔다(place_contrast).
    반환: [{word, distractors, probe: {position, target, read, contrast, source}}], source는 'candidate' 또는 'random'."""
    rng = rng or random.Random()
    pair, source = None, "random"
    for f in focus or ():
        key = (f.get("position"), f.get("target"), f.get("read"))
        if pidx.contrast.get(key):
            pair, source = key, "candidate"
            break
    if pair is None:
        if not pidx.probe_pairs:
            return []
        pair = rng.choice(pidx.probe_pairs)
    words = list(pidx.contrast[pair])
    weights = [max(1.0, float(priority.get(w, 1))) for w in words]
    picked: List[str] = []
    while words and len(picked) < k:
        w = rng.choices(words, weights=weights)[0]
        i = words.index(w)
        words.pop(i)
        weights.pop(i)
        picked.append(w)
    fdict = [{"position": pair[0], "target": pair[1], "read": pair[2]}]
    out = []
    for w in picked:
        dis = V.pick_distractors(w, pidx.index, level, rng, classes=classes_fn(w))
        dis = place_contrast(w, dis, fdict, pidx.index, rng, contrast_fn=pidx.contrasts)
        contrast = next((d for d in dis if d in pidx.contrasts(w, *pair)), None)
        if contrast is None:
            continue
        out.append({"word": w, "distractors": dis,
                    "probe": {"position": pair[0], "target": pair[1], "read": pair[2], "contrast": contrast,
                              "source": source}})
    return out


def valid_probe(probe, word: str, options: Optional[Sequence[str]]) -> Optional[Dict]:
    """화면이 돌려준 탐색 표시를 확인해 기록할 모양으로 돌려준다. 눈으로 가를 수 있는 짝이고, 대비 단어가 보기에 있고,
    정답과 대비 단어가 그 짝 자리 하나에서만 갈리면 {position, target, read, contrast, source}, 아니면 None(보통 문항으로 기록)."""
    if not isinstance(probe, dict) or not options:
        return None
    p, t, r, c = (str(probe.get(k) or "") for k in ("position", "target", "read", "contrast"))
    if not visible_jamo_pair(p, t, r) or not c or c == word or c not in options:
        return None
    if jamo_diffs(word, c) != [(p, t, r)]:
        return None
    src = probe.get("source")
    return {"position": p, "target": t, "read": r, "contrast": c,
            "source": src if src in ("candidate", "random") else None}
