"""
뜻 없는 말 짝 맞추기(종합 계획 C10의 나머지, idea-sweep 다2). 무의미 낱말 생성기와 회차 규칙.

아바타가 CVCVC 무의미 낱말(예: 바록)을 말하고, 학습자는 그 낱말을 추상 도형과 짝지어 익힌다. 시행 전에는 철자 전체가 아니라
자음 골격(ㅂ_ㄹ_ㄱ)만 보여 준다. 어휘 지식이 끼어들지 않아 시각 음성 지각만 훈련하고, 어휘가 적은 학습자에게도 공정하다.
근거: Bernstein, Auer, Eberhardt 2023 Brain Sci 13(7):1008(자음만 미리 본 집단만 음소 식별과 개방형 문장 독화가 향상)
https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10377548/ , Eberhardt, Auer, Bernstein 2014(무의미 낱말 짝 학습이 자음 식별로 전이)
https://pmc.ncbi.nlm.nih.gov/articles/PMC4215828/ . 설계와 기록은 docs/nonsense-pairing.md.

생성 규칙(결정론, 시드 SEED)
- 모양: CV + CVC 두 음절. 첫소리는 _ONSETS 13개(ㅇ·된소리 제외), 모음은 _VOWELS 7개(홑모음, ㅐ는 ㅔ와 같아 뺌),
  받침은 _CODAS 6개(대표음 ㄱ·ㄴ·ㄹ·ㅁ·ㅂ·ㅇ. ㄷ 계열 받침은 철자와 소리가 달라 뺌). 첫 음절에 받침이 없어 두 음절 사이에
  발음 규칙이 걸리지 않으므로, 아바타는 적힌 그대로 말한다. 모든 낱말은 표준 한글 음절이다.
- 실제 낱말 빼기: 저장소의 낱말 자료(curriculum 단어 은행·최소대립쌍·문맥 문항, backend/data 아래 JSON의 모든 한글 덩어리,
  표준검사 단어)와 wordfreq 한국어 빈도 사전(약 3만 낱말)에 있는 말, 사람이 보고 뺀 MANUAL_EXCLUDED를 뺀다. wordfreq는 앱
  실행에 필요 없게, 후보 공간에서 사전에 걸린 낱말 목록을 생성 결과 JSON(excluded_by_wordfreq)에 함께 얼려 둔다.
- 학습 목록: SET_COUNT개, 목록마다 SET_SIZE개. 한 목록은 모음 틀(V1, V2)이 같아 낱말이 자음으로만 갈린다(자음 지각 훈련).
  목록 안에서 첫소리 C1끼리, C2끼리 겹치지 않고, 세 자음의 입모양 무리(engine.VISEME_MAP)가 두 자리 이상 다르다
  (아바타는 같은 무리 자음을 같은 입모양으로 그리므로, 무리가 한 자리만 다르면 구별 단서가 하나뿐이다). 자음 골격은 목록끼리도
  겹치지 않는다. 자음은 쓰인 횟수가 적은 것부터 고른다(목록 전체에 고르게).
- 남겨 둔 목록: HELDOUT_LISTS × HELDOUT_SIZE개. 학습 목록에 없는 자음 골격으로 만들고 학습에 쓰지 않는다. 사전·사후
  '학습하지 않은 무의미 낱말 자음 식별'(가1 첫째 층) 문항 후보다. 실제 검사 문항은 P2 촬영 목록 동결 때 정한다.

회차 규칙
- 목록 하나를 기준까지 반복한다. 블록 1·3·5…는 '골격 보고' 블록(시행마다 자음 골격을 먼저 보임), 2·4·6…은 '확인' 블록(골격 없음).
  확인 블록 정답률이 CRITERION 이상이면 그 목록을 마친다. 화면은 목록을 마치면 그날 회차를 끝내 다음 목록은 다음 날 시작한다(서버는 막지 않는다).
- 하루 DAILY_TRIAL_CAP 시행(시행당 약 10초, 10분 안). 화면도 DAILY_MINUTES분이 지나면 그 시행 뒤에 멈춘다.
- 시행 기록은 trial_attempts(item_type 'nonsense', stage NULL, item_id '목록:b블록:h|c')에만 남는다. 단계 숙달·복습·XP에는 넣지 않는다.

**순수 함수**만 둔다(JSON 읽기 제외).
"""
import json
import os
import random
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from engine import VISEME_MAP

SEED = 20261006
SET_COUNT = 8
SET_SIZE = 6
HELDOUT_LISTS = 2
HELDOUT_SIZE = 16
MIN_GROUP_DISTANCE = 2
CRITERION = 0.9
DAILY_TRIAL_CAP = 60
DAILY_MINUTES = 10
ITEM_TYPE = "nonsense"

_ONSETS = "ㅂㅍㅁㄷㅌㄴㄹㅅㄱㅋㅎㅈㅊ"
_VOWELS = "ㅏㅓㅗㅜㅡㅣㅔ"
_CODAS = "ㄱㄴㄹㅁㅂㅇ"
# 화면 도형 이름(frontend/src/lib/nonsenseShapes.js SHAPES와 같아야 한다, nonsensePairing.test.mjs가 확인)
SHAPES = ("circle", "triangle", "square", "diamond", "star", "cross", "hexagon", "ring", "arch", "bolt", "drop", "bars")
# 사람이 보고 뺀 말(사전에 없지만 실제로 쓰이는 말, 이름·상표·비속어 등). 생성 결과를 사람이 읽은 뒤 더한다
MANUAL_EXCLUDED = frozenset({"고락", "저몸", "구김", "파닥"})   # 고락(苦樂), 저 몸(두 낱말), 구김, 파닥(흉내말)

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
         "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(_HERE, "data", "nonsense_words.json")
_HANGUL_RUN = re.compile(r"[가-힣]+")


def compose(c1: str, v1: str, c2: str, v2: str, c3: str) -> str:
    syl = lambda c, v, j="": chr(0xAC00 + (_CHO.index(c) * 21 + _JUNG.index(v)) * 28 + _JONG.index(j))
    return syl(c1, v1) + syl(c2, v2, c3)


def parts(word: str) -> Tuple[str, str, str, str, str]:
    """CVCVC 낱말 → (C1, V1, C2, V2, C3)."""
    out = []
    for ch in word:
        k = ord(ch) - 0xAC00
        out.append((_CHO[k // 588], _JUNG[(k % 588) // 28], _JONG[k % 28]))
    (c1, v1, _), (c2, v2, c3) = out
    return c1, v1, c2, v2, c3


def skeleton(word: str) -> str:
    """자음 골격: 모음 자리를 '_'로(바록 → ㅂ_ㄹ_ㄱ). frontend/src/lib/consonantSkeleton.js consonantFrame과 같은 규칙."""
    out = []
    for ch in word:
        if not ("가" <= ch <= "힣"):
            continue
        k = ord(ch) - 0xAC00
        cho, jong = _CHO[k // 588], _JONG[k % 28]
        out.append(("" if cho == "ㅇ" else cho) + "_" + jong)
    return "".join(out)


def _groups(word: str) -> Tuple[int, int, int]:
    c1, _, c2, _, c3 = parts(word)
    return VISEME_MAP[c1], VISEME_MAP[c2], VISEME_MAP[c3]


def group_distance(a: str, b: str) -> int:
    """세 자음 자리 가운데 입모양 무리가 다른 자리 수."""
    return sum(1 for x, y in zip(_groups(a), _groups(b)) if x != y)


def candidates() -> List[str]:
    """후보 공간 전체(정해진 순서)."""
    return [compose(c1, v1, c2, v2, c3) for c1 in _ONSETS for v1 in _VOWELS for c2 in _ONSETS for v2 in _VOWELS for c3 in _CODAS]


# ── 실제 낱말 ───────────────────────────────────────────────────────

def _runs(obj) -> Iterable[str]:
    if isinstance(obj, str):
        yield from _HANGUL_RUN.findall(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _runs(k)
            yield from _runs(v)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            yield from _runs(v)


def repo_real_words() -> Set[str]:
    """저장소 자료에 나오는 한글 덩어리 전부(낱말·문장 속 어절). 무의미 낱말이 이 가운데 하나와 같으면 뺀다."""
    import curriculum as _cur
    import assessment as _asmt
    out: Set[str] = set()
    out.update(_runs([w["word"] for w in _cur.WORD_BANK]))
    out.update(_runs(getattr(_cur, "MINIMAL_PAIRS", [])))
    out.update(_runs(getattr(_cur, "CLOSURE_ITEMS", [])))
    out.update(_runs(list(_asmt.test_only_words())))
    data_dir = os.path.join(_HERE, "data")
    for root, _, files in os.walk(data_dir):
        # P3 검사 목록(data/pilot)은 이 모듈이 만든 무의미 낱말을 옮겨 담은 것이라 실제 낱말 자료가 아니다. 넣으면 다시 만들 때
        # 남겨 둔 목록이 자기 자신을 실제 낱말로 보고 빠진다
        if os.path.relpath(root, data_dir).split(os.sep)[0] == "pilot":
            continue
        for name in sorted(files):
            if not name.endswith(".json") or name == os.path.basename(DATA_PATH):
                continue
            try:
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    out.update(_runs(json.load(f)))
            except (OSError, ValueError):
                continue
    return out


def wordfreq_hits(words: Sequence[str]) -> Optional[List[str]]:
    """wordfreq 한국어 사전에 있는 후보(정렬). wordfreq가 없으면 None."""
    try:
        from wordfreq import get_frequency_dict
    except Exception:
        return None
    d = get_frequency_dict("ko")
    return sorted(w for w in words if w in d)


# ── 생성 ─────────────────────────────────────────────────────────────

def generate(excluded: Set[str], seed: int = SEED) -> Dict:
    """학습 목록과 남겨 둔 목록을 만든다. excluded = 실제 낱말(저장소 + wordfreq + 사람이 뺀 말)."""
    rng = random.Random(seed)
    bad = set(excluded) | set(MANUAL_EXCLUDED)
    used_skel: Set[str] = set()
    usage = {c: 0 for c in _ONSETS}

    # 모음 틀: 두 모음의 입모양 무리가 다른 순서쌍
    frames = [(a, b) for a in _VOWELS for b in _VOWELS if VISEME_MAP[a] != VISEME_MAP[b]]
    rng.shuffle(frames)
    frames = frames[:SET_COUNT]

    sets = []
    for si, (v1, v2) in enumerate(frames):
        pool = [(c1, c2, c3) for c1 in _ONSETS for c2 in _ONSETS for c3 in _CODAS]
        rng.shuffle(pool)
        picked: List[str] = []
        c1s, c2s, c3s = set(), set(), {}
        # 쓰인 횟수가 적은 자음부터. 정렬은 안정적이라 같은 횟수 안에서는 섞은 순서를 따른다
        for c1, c2, c3 in sorted(pool, key=lambda t: usage[t[0]] + usage[t[1]]):
            w = compose(c1, v1, c2, v2, c3)
            if w in bad or skeleton(w) in used_skel or c1 in c1s or c2 in c2s or c3s.get(c3, 0) >= 2:
                continue
            if any(group_distance(w, p) < MIN_GROUP_DISTANCE for p in picked):
                continue
            picked.append(w)
            c1s.add(c1); c2s.add(c2); c3s[c3] = c3s.get(c3, 0) + 1
            if len(picked) == SET_SIZE:
                break
        if len(picked) < SET_SIZE:
            raise RuntimeError(f"목록 {si + 1}을 채우지 못함")
        for w in picked:
            c1, _, c2, _, _ = parts(w)
            usage[c1] += 1
            usage[c2] += 1
            used_skel.add(skeleton(w))
        shapes = rng.sample(SHAPES, SET_SIZE)
        sets.append({"id": f"ns{si + 1:02d}", "vowels": [v1, v2],
                     "words": [{"word": w, "skeleton": skeleton(w), "shape": s} for w, s in zip(picked, shapes)]})

    # 남겨 둔 목록: 첫소리·둘째 첫소리·받침을 차례로 돌려 고르게, 모음은 무작위
    heldout = []
    taken: Set[str] = set()
    for _ in range(HELDOUT_LISTS):
        o1, o2, cd = list(_ONSETS), list(_ONSETS), list(_CODAS)
        rng.shuffle(o1); rng.shuffle(o2); rng.shuffle(cd)
        lst: List[str] = []
        k = 0
        while len(lst) < HELDOUT_SIZE:
            c1, c2, c3 = o1[k % len(o1)], o2[(k + k // len(o2)) % len(o2)], cd[k % len(cd)]
            k += 1
            vowels = [(a, b) for a in _VOWELS for b in _VOWELS]
            rng.shuffle(vowels)
            for v1, v2 in vowels:
                w = compose(c1, v1, c2, v2, c3)
                if w not in bad and w not in taken and skeleton(w) not in used_skel:
                    lst.append(w)
                    taken.add(w)
                    break
        heldout.append(lst)
    return {"sets": sets, "heldout": heldout}


def build(seed: int = SEED, wordfreq_excluded: Optional[Sequence[str]] = None) -> Dict:
    """생성 결과 JSON 전체. wordfreq_excluded를 주지 않으면 지금 설치된 wordfreq로 다시 찾는다."""
    cands = candidates()
    if wordfreq_excluded is None:
        hits = wordfreq_hits(cands)
        if hits is None:
            raise RuntimeError("wordfreq가 없어 실제 낱말을 다 뺄 수 없다(pip install wordfreq)")
        wordfreq_excluded = hits
    real = repo_real_words()
    out = generate(real | set(wordfreq_excluded), seed)
    return {
        "version": 1, "seed": seed,
        "rule": "CV+CVC, 첫소리 " + _ONSETS + ", 모음 " + _VOWELS + ", 받침 " + _CODAS
                + ". 저장소 낱말·wordfreq 한국어 사전·MANUAL_EXCLUDED에 있는 말 제외(backend/nonsense_words.py 머리말)",
        "set_size": SET_SIZE, "criterion": CRITERION,
        **out,
        "excluded_by_wordfreq": list(wordfreq_excluded),
    }


_DATA: Optional[Dict] = None


def load() -> Dict:
    """얼려 둔 생성 결과(backend/data/nonsense_words.json)."""
    global _DATA
    if _DATA is None:
        with open(DATA_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA


def training_sets() -> List[Dict]:
    return load()["sets"]


# ── 회차 규칙 ────────────────────────────────────────────────────────

def block_is_hint(block: int) -> bool:
    return block % 2 == 1


def item_id(set_id: str, block: int) -> str:
    return f"{set_id}:b{block}:{'h' if block_is_hint(block) else 'c'}"


def parse_item_id(s: Optional[str]) -> Optional[Tuple[str, int]]:
    m = re.fullmatch(r"(ns\d{2}):b(\d{1,4}):[hc]", s or "")
    return (m.group(1), int(m.group(2))) if m else None


def set_progress(set_def: Dict, rows: Sequence[Tuple[str, str, bool]]) -> Dict:
    """한 목록의 진행. rows = 이 학습자의 nonsense 시행 (item_id, target, correct), 시간순(다른 목록 행이 섞여도 된다).
    반환: met(기준 도달), next_block, remaining(이번 블록에서 아직 안 본 낱말, 목록 순서), blocks{번호: [본 수, 맞힌 수]}, n."""
    words = [w["word"] for w in set_def["words"]]
    seen: Dict[int, List[str]] = {}
    right: Dict[int, int] = {}
    met = False
    n = 0
    for iid, target, correct in rows:
        p = parse_item_id(iid)
        if not p or p[0] != set_def["id"] or target not in words:
            continue
        b = p[1]
        if target in seen.setdefault(b, []):
            continue   # 같은 블록에 같은 낱말이 두 번 들어온 행(중복 제출)은 처음 것만
        seen[b].append(target)
        right[b] = right.get(b, 0) + (1 if correct else 0)
        n += 1
        if not block_is_hint(b) and len(seen[b]) == len(words) and right[b] / len(words) >= CRITERION:
            met = True
    if not seen:
        nb, remaining = 1, list(words)
    else:
        last = max(seen)
        if len(seen[last]) < len(words):
            nb, remaining = last, [w for w in words if w not in seen[last]]
        else:
            nb, remaining = last + 1, list(words)
    return {"met": met, "next_block": nb, "hint": block_is_hint(nb), "remaining": remaining,
            "blocks": {b: [len(v), right.get(b, 0)] for b, v in sorted(seen.items())}, "n": n}


def session_state(sets: Sequence[Dict], rows: Sequence[Tuple[str, str, bool]], today_n: int) -> Dict:
    """지금 학습할 목록과 블록. 모든 목록을 마쳤으면 finished."""
    done = 0
    for i, s in enumerate(sets):
        prog = set_progress(s, rows)
        if not prog["met"]:
            return {"finished": False, "set_index": i, "set": s, "progress": prog, "sets_done": done,
                    "n_sets": len(sets), "today": today_info(today_n)}
        done += 1
    return {"finished": True, "set_index": None, "set": None, "progress": None, "sets_done": done,
            "n_sets": len(sets), "today": today_info(today_n)}


def today_info(today_n: int) -> Dict:
    return {"n": int(today_n), "cap": DAILY_TRIAL_CAP, "minutes": DAILY_MINUTES, "done": today_n >= DAILY_TRIAL_CAP}


if __name__ == "__main__":   # backend/에서: python -m nonsense_words --write
    import sys
    data = build()
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if "--write" in sys.argv:
        with open(DATA_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"wrote {DATA_PATH}")
    for s in data["sets"]:
        print(s["id"], "".join(s["vowels"]), " ".join(f"{w['word']}({w['skeleton']},{w['shape']})" for w in s["words"]))
    for i, lst in enumerate(data["heldout"]):
        print("heldout", i + 1, " ".join(lst))
