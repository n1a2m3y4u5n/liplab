"""
소리 듣기(청능훈련) 커리큘럼. 보청기·인공와우를 쓰는 학습자가 남은 청력으로 말소리를 알아듣는 연습(docs/auditory-training-design.md).

독화(보기)·발화(말하기)에 이은 세 번째 트랙이다. 청각 기술 위계(감지 → 구별 → 확인 → 이해)를 따라 6단계로 올라간다.
  0 소리 확인   Ling 6소리(음·우·아·이·쉬·스) 감지. 기기 점검을 겸하며 한 번 마치면 다음 단계가 열린다
  1 소리 구별   두 소리가 같은지 다른지(길이·억양 → 모음 → 자음 방식·세기 → 자리·마찰음·받침), 수준이 저절로 오르내린다
  2 낱말 고르기 소리만 듣고 보기에서 고르기(2지 → 4지 → 한 소리만 다른 4지)
  3 문장 알아듣기 조용한 곳에서 문장을 듣고 그대로 입력(개방형)
  4 소음 속 듣기 잡담 잡음 속 문장. 소음 크기를 계단식으로 맞추고(1-up-1-down, 낱말 절반 이상이면 맞음), 소리만·소리+입모양을 번갈아 낸다
  5 대화 듣기   생활 장면의 말을 듣고 내용 고르기. 다시 듣기·천천히·다른 말로 되묻기를 쓸 수 있다

**순수 데이터와 순수 함수**만 둔다(DB·네트워크 없음). 소리 파일은 소리 조건(C17)의 미리 합성한 서버 음성(sound_clips 목록)을
쓰고, 이 모듈의 inventory_texts()가 합성할 글을 모은다. Ling 소리는 화면이 직접 합성한다(주파수 대역을 정확히 맞추려고).

검사와 훈련을 나눈다. 소음 속 문장 인식 역치(SRT) 검사 문장(TEST_FORMS)은 훈련 문장(TRAIN_SENTENCES)·대화와 겹치지 않고,
예비 파일럿(P3) 문장과도 겹치지 않는다(test_listen_curriculum이 확인한다).
"""
import hashlib
import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

# ── 단계 ─────────────────────────────────────────────────────────────

STAGES: List[Dict] = [
    {"stage": 0, "key": "ling", "title": "소리 확인", "mode": "ling", "icon": "🔔",
     "desc": "여섯 가지 소리가 들리는지 확인해요. 보청기·인공와우가 잘 작동하는지 매일 점검하는 데도 써요.",
     "guide": "소리가 들리면 '들렸어요'를 눌러요. 아무 소리가 없을 때도 있어요. 들리지 않으면 '안 들렸어요'를 눌러요."},
    {"stage": 1, "key": "ax", "title": "소리 구별", "mode": "ax", "icon": "👂",
     "desc": "두 소리를 듣고 같은지 다른지 골라요. 쉬운 차이에서 시작해 점점 비슷한 소리로 넘어가요.",
     "guide": "두 소리를 차례로 들려줘요. 같은 소리면 '같아요', 다르면 '달라요'를 눌러요."},
    {"stage": 2, "key": "word_id", "title": "낱말 고르기", "mode": "word_id", "icon": "🔤",
     "desc": "소리만 듣고 어떤 낱말인지 보기에서 골라요.",
     "guide": "낱말 하나를 들려줘요. 들은 낱말을 보기에서 골라요. 다시 들을 수 있어요."},
    {"stage": 3, "key": "sentence", "title": "문장 알아듣기", "mode": "sentence", "icon": "💬",
     "desc": "조용한 곳에서 문장을 듣고 들은 대로 입력해요.",
     "guide": "문장을 들려줘요. 들은 대로 써요. 틀린 낱말은 첫소리 자음만 보여 주니 한 번 더 들어 보고 고쳐 써요."},
    {"stage": 4, "key": "noise", "title": "소음 속 듣기", "mode": "noise", "icon": "🎧",
     "desc": "여러 사람이 떠드는 소리 속에서 문장을 알아들어요. 맞히면 소음이 커지고, 놓치면 작아져요.",
     "guide": "문장을 듣고 들은 대로 써요. 네 번에 한 번은 입모양이 함께 나와요. 전체 소리 크기는 그대로이고 말과 소음의 비율만 바뀌어요."},
    {"stage": 5, "key": "convo", "title": "대화 듣기", "mode": "convo", "icon": "🗣️",
     "desc": "병원·가게·안내 방송 같은 생활 속 말을 듣고 내용을 골라요.",
     "guide": "말을 듣고 질문의 답을 골라요. 못 알아들으면 '다시', '천천히', '다른 말로'를 눌러 되물어요."},
]

# 숙달 기준. 수준이 있는 단계(1·2)는 맨 위 수준에서 최근 10번 중 기준 이상을 맞히면 숙달이다(우연 수준에서 닿기 어려운 값:
# 2지 9/10은 우연 1.1%, 4지 8/10은 우연 0.04%). 3·5단계는 이동 평균(main._ewma_mastery) 문턱, 4단계는 역치(SRT) 기준이다.
LEVELED = {
    1: {"levels": 4, "promote": (9, 10), "demote": (3, 6), "master": (9, 10)},
    2: {"levels": 3, "promote": (8, 10), "demote": (3, 6), "master": (8, 10)},
}
EWMA_STAGES = {
    3: {"min_attempts": 10, "mastery": 80.0},
    5: {"min_attempts": 12, "mastery": 70.0},
}
# 4단계: 소리만 조건의 역치 추정값이 이 값(dB) 이하이거나, 처음 20번의 역치보다 최근 20번의 역치가 GAIN_DB 이상 내려가면 숙달
NOISE_MASTER = {"min_trials": 20, "srt_db": 0.0, "gain_db": 3.0, "window": 20}


def stages_overview() -> List[Dict]:
    return [dict(s) for s in STAGES]


def get_stage(n: int) -> Optional[Dict]:
    return next((dict(s) for s in STAGES if s["stage"] == n), None)


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12], 16))


# ── 1단계: 소리 구별(같다·다르다) ───────────────────────────────────────
# 수준 1 큰 차이(길이·억양), 2 모음, 3 자음 방식·세기(예사·된·거센소리), 4 자리·마찰음·받침.
# 보청기·인공와우 사용자는 방식·유무성 단서보다 자리(ㅂ·ㄷ·ㄱ)와 높은 주파수 마찰음(ㅅ·ㅈ·ㅊ·ㅎ), 받침을 더 놓친다.

AX_PAIRS: List[Dict] = (
    [{"a": a, "b": b, "kind": "length", "level": 1} for a, b in [
        ("바", "바다"), ("나", "나무"), ("가", "가방"), ("사", "사과"), ("모", "모자"), ("구", "구름")]]
    + [{"a": a, "b": b, "kind": "intonation", "level": 1} for a, b in [
        ("가요.", "가요?"), ("밥 먹어요.", "밥 먹어요?"), ("비 와요.", "비 와요?"), ("괜찮아요.", "괜찮아요?"),
        ("집에 가요.", "집에 가요?"), ("배고파요.", "배고파요?")]]
    + [{"a": a, "b": b, "kind": "vowel", "level": 2} for a, b in [
        ("바", "비"), ("바", "부"), ("비", "부"), ("보", "부"), ("버", "보"), ("베", "비"), ("브", "부"), ("바", "버"),
        ("마", "미"), ("무", "모"), ("가", "기"), ("구", "고")]]
    + [{"a": a, "b": b, "kind": "manner", "level": 3} for a, b in [
        ("마", "바"), ("나", "다"), ("라", "다"), ("나", "라"), ("사", "다")]]
    + [{"a": a, "b": b, "kind": "laryngeal", "level": 3} for a, b in [
        ("바", "파"), ("바", "빠"), ("다", "타"), ("다", "따"), ("가", "카"), ("가", "까"), ("자", "차"), ("자", "짜"),
        ("사", "싸")]]
    + [{"a": a, "b": b, "kind": "place", "level": 4} for a, b in [
        ("바", "다"), ("다", "가"), ("바", "가"), ("마", "나"), ("파", "타"), ("타", "카")]]
    + [{"a": a, "b": b, "kind": "fricative", "level": 4} for a, b in [
        ("사", "자"), ("사", "차"), ("사", "하"), ("시", "히")]]
    + [{"a": a, "b": b, "kind": "coda", "level": 4} for a, b in [
        ("각", "갑"), ("간", "감"), ("반", "방"), ("산", "상"), ("닥", "답"), ("밤", "반")]]
)
AX_KIND_LABEL = {"length": "길이", "intonation": "억양", "vowel": "모음", "manner": "자음 방식", "laryngeal": "소리 세기",
                 "place": "소리 자리", "fricative": "마찰음", "coda": "받침"}
_AX_TEXTS = {p["a"] for p in AX_PAIRS} | {p["b"] for p in AX_PAIRS}


def ax_key(first: str, second: str, level: int) -> str:
    return f"ax:{int(level)}:{first}|{second}"


def ax_parse(key: str) -> Optional[Tuple[str, str, Dict]]:
    """'ax:3:가|카' → (첫 소리, 둘째 소리, 짝). 같음 문항('바|바')은 여러 수준의 짝에 들어 있어 수준을 키에 둔다.
    목록에 없는 짝이면 None(답을 꾸며 보내지 못하게)."""
    if not key or not key.startswith("ax:") or "|" not in key:
        return None
    lv, _, body = key[3:].partition(":")
    if not lv.isdigit() or "|" not in body:
        return None
    first, second = body.split("|", 1)
    for p in AX_PAIRS:
        if p["level"] == int(lv) and {first, second} <= {p["a"], p["b"]}:
            return first, second, p
    return None


def ax_pair_id(level: int, a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"{int(level)}:{x}|{y}"


# ── 표적 출제(고도화 방안 P1) ─────────────────────────────────────────
# 대조(소리 짝)마다 '다름' 시행의 정답률을 베타 분포(사전 1, 1)로 추정하고, 추정 정답률이 0.75 근처인 짝을 자주 낸다. 3번 미만 본 짝은
# 탐색으로 무게 1. 너무 쉬운 짝(0.95)과 아직 너무 어려운 짝(0.5)은 덜 낸다. 표적 대조 훈련은 인공와우 사용자에게 근거가 가장 좋지만
# (Fu 2005: 모음 +15.8, 자음 +13.5%p) 혼동 기록으로 문항을 고르는 방식 자체는 시험된 적이 없어, 학습자를 해시로 둘로 나눠
# 'targeted'와 'uniform'(무작위)을 비교한다(pick_mode_for, 시행 기록 pick_mode).
PICK_MODES = ("targeted", "uniform")


def pick_mode_for(user_id: int) -> str:
    """학습자의 출제 방식. 검사 폼 순서(id 홀짝)와 엇갈리지 않게 따로 해시한다."""
    h = int(hashlib.sha1(f"pick:{int(user_id)}".encode()).hexdigest()[:8], 16)
    return PICK_MODES[h % 2]


def pair_weight(n: int, c: int, target: float = 0.75, width: float = 0.15) -> float:
    if n < 3:
        return 1.0
    p = (c + 1) / (n + 2)
    return 0.15 + math.exp(-((p - target) / width) ** 2)


def ax_pair_stats(history: Sequence[Tuple[str, bool]]) -> Dict[str, Tuple[int, int]]:
    """소리 구별 시행 [(키, 정답)] → 짝 id마다 (다름 시행 수, 정답 수). 같음 시행은 어느 짝인지 정해지지 않아 세지 않는다."""
    out: Dict[str, Tuple[int, int]] = {}
    for key, ok in history:
        parsed = ax_parse(key)
        if not parsed:
            continue
        first, second, pair = parsed
        if first == second:
            continue
        pid = ax_pair_id(pair["level"], pair["a"], pair["b"])
        n, c = out.get(pid, (0, 0))
        out[pid] = (n + 1, c + (1 if ok else 0))
    return out


def ling_avoid_kinds(ling: Optional[Dict[str, bool]]) -> Dict[str, float]:
    """최근 Ling 점검 → 소리 구별 종류별 무게 배율(고도화 방안 P2). 쉬·스가 모두 안 들리면 마찰음 짝을 내지 않고(0),
    하나만 안 들리면 절반으로 줄인다. 들리지 않는 대역의 구별을 되풀이하면 좌절만 쌓인다."""
    if not ling:
        return {}
    miss = [k for k in ("sh", "s") if ling.get(k) is False]
    if len(miss) == 2:
        return {"fricative": 0.0}
    if len(miss) == 1:
        return {"fricative": 0.5}
    return {}


def ax_items(level: int, seed: str, n: int = 12, multi_voice: bool = False, pick: str = "uniform",
             stats: Optional[Dict[str, Tuple[int, int]]] = None, kind_scale: Optional[Dict[str, float]] = None) -> List[Dict]:
    """수준 level의 같다·다르다 문항 n개(같음·다름 반반, 순서 섞음). 수준 3 이상이고 목소리가 여럿이면 두 소리를 서로 다른
    목소리로 들려준다(목소리가 달라도 같은 말인지 가리는 연습). voice_pair: [첫 소리 목소리 칸, 둘째 칸](화면이 목소리에 대응).
    pick 'targeted'면 짝 무게(pair_weight)로, 'uniform'이면 고르게 뽑는다. kind_scale은 종류별 무게 배율(Ling 출발점, 두 방식 모두 적용)."""
    level = max(1, min(4, int(level)))
    scale = kind_scale or {}
    pool = [p for p in AX_PAIRS if p["level"] == level and scale.get(p["kind"], 1.0) > 0] or \
        [p for p in AX_PAIRS if p["level"] == level]
    stats = stats or {}
    weights = []
    for p in pool:
        w = scale.get(p["kind"], 1.0)
        if pick == "targeted":
            nn, cc = stats.get(ax_pair_id(level, p["a"], p["b"]), (0, 0))
            w *= pair_weight(nn, cc)
        weights.append(w)
    r = _rng(f"ax:{seed}:{level}")
    out = []
    for k in range(n):
        p = r.choices(pool, weights=weights, k=1)[0]
        same = k % 2 == 0
        a, b = (p["a"], p["b"]) if r.random() < 0.5 else (p["b"], p["a"])
        first, second = (a, a) if same else (a, b)
        vp = [0, 1] if multi_voice and level >= 3 else [0, 0]
        out.append({"key": ax_key(first, second, level), "first": first, "second": second, "kind": p["kind"],
                    "kind_label": AX_KIND_LABEL[p["kind"]], "level": level, "voice_pair": vp, "pick": pick})
    r.shuffle(out)
    return out


def ax_correct(key: str, answer_same: bool) -> Optional[bool]:
    parsed = ax_parse(key)
    if not parsed:
        return None
    first, second, _ = parsed
    return bool(answer_same) == (first == second)


def next_level(history: Sequence[Tuple[int, bool]], stage: int) -> int:
    """수준 정하기. history는 이 단계 시도의 (수준, 정답) 시간순. 지금 수준은 마지막 시도의 수준(없으면 1)이고,
    지금 수준의 최근 promote[1]번 중 promote[0]번 이상 맞으면 하나 올리고, 최근 demote[1]번 중 demote[0]번 이하면 하나 내린다."""
    cfg = LEVELED[stage]
    cur = int(history[-1][0]) if history else 1
    # 바로 앞 수준 변경 뒤의 시도만 센다(같은 수준으로 돌아온 옛 시도가 섞이지 않게)
    tail = []
    for lv, c in reversed(list(history)):
        if int(lv) != cur:
            break
        tail.append(bool(c))
    tail.reverse()
    at = tail
    pk, pn = cfg["promote"]
    dk, dn = cfg["demote"]
    if len(at) >= pn and sum(at[-pn:]) >= pk and cur < cfg["levels"]:
        return cur + 1
    if len(at) >= dn and sum(at[-dn:]) <= dk and cur > 1:
        return cur - 1
    return cur


def leveled_mastered(history: Sequence[Tuple[int, bool]], stage: int) -> bool:
    """맨 위 수준의 최근 master[1]번 중 master[0]번 이상 정답."""
    cfg = LEVELED[stage]
    top = [bool(c) for lv, c in history if int(lv) == cfg["levels"]]
    k, n = cfg["master"]
    return len(top) >= n and sum(top[-n:]) >= k


# ── 2단계: 낱말 고르기(닫힌 보기) ─────────────────────────────────────
# 보기는 '소리 거리'로 고른다. 소리 나는 대로의 자모열(scoring.to_pronounced_jamos)에서 자리마다 거리를 더한다.
# 자음은 자리·방식·세기 세 자질 중 다른 수(0~3), 모음은 높이·앞뒤·둥글림·반모음 차이, 받침은 7대표음과 없음.
# ㅐ와 ㅔ는 요즘 말에서 소리가 같아 같은 모음으로 본다(소리가 같은 말은 보기로 내지 않는다).

_C_FEAT = {
    # 자리, 방식, 세기
    "ㅂ": ("lab", "stop", "lax"), "ㅃ": ("lab", "stop", "tense"), "ㅍ": ("lab", "stop", "asp"), "ㅁ": ("lab", "nasal", "son"),
    "ㄷ": ("alv", "stop", "lax"), "ㄸ": ("alv", "stop", "tense"), "ㅌ": ("alv", "stop", "asp"), "ㄴ": ("alv", "nasal", "son"),
    "ㄹ": ("alv", "liquid", "son"), "ㅅ": ("alv", "fric", "lax"), "ㅆ": ("alv", "fric", "tense"),
    "ㅈ": ("pal", "affr", "lax"), "ㅉ": ("pal", "affr", "tense"), "ㅊ": ("pal", "affr", "asp"),
    "ㄱ": ("vel", "stop", "lax"), "ㄲ": ("vel", "stop", "tense"), "ㅋ": ("vel", "stop", "asp"), "ㅇ": ("vel", "nasal", "son"),
    "ㅎ": ("glot", "fric", "asp"), "": ("none", "none", "none"),
}
# 단모음: 높이(0 높음 ~ 2 낮음), 앞뒤(0 앞 ~ 2 뒤), 둥글림
_V_BASE = {"ㅣ": (0, 0, 0), "ㅔ": (1, 0, 0), "ㅐ": (1, 0, 0), "ㅟ": (0, 0, 1), "ㅚ": (1, 0, 1), "ㅡ": (0, 1, 0), "ㅓ": (1, 1, 0),
           "ㅏ": (2, 1, 0), "ㅜ": (0, 2, 1), "ㅗ": (1, 2, 1)}
_V_GLIDE = {"ㅑ": ("y", "ㅏ"), "ㅕ": ("y", "ㅓ"), "ㅛ": ("y", "ㅗ"), "ㅠ": ("y", "ㅜ"), "ㅒ": ("y", "ㅐ"), "ㅖ": ("y", "ㅔ"),
            "ㅘ": ("w", "ㅏ"), "ㅙ": ("w", "ㅐ"), "ㅝ": ("w", "ㅓ"), "ㅞ": ("w", "ㅔ"), "ㅢ": ("w", "ㅣ")}
_CODA_REP = {"ㄱ": "ㄱ", "ㄲ": "ㄱ", "ㅋ": "ㄱ", "ㄳ": "ㄱ", "ㄺ": "ㄱ", "ㄴ": "ㄴ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄷ": "ㄷ", "ㅅ": "ㄷ",
             "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅊ": "ㄷ", "ㅌ": "ㄷ", "ㅎ": "ㄷ", "ㄹ": "ㄹ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㅀ": "ㄹ",
             "ㅁ": "ㅁ", "ㄻ": "ㅁ", "ㅂ": "ㅂ", "ㅍ": "ㅂ", "ㅄ": "ㅂ", "ㄿ": "ㅂ", "ㅇ": "ㅇ", "": ""}


def cons_distance(a: str, b: str) -> int:
    fa, fb = _C_FEAT.get(a or "", _C_FEAT[""]), _C_FEAT.get(b or "", _C_FEAT[""])
    return sum(1 for x, y in zip(fa, fb) if x != y)


def _vowel(v: str) -> Tuple[str, Tuple[int, int, int]]:
    if v in _V_GLIDE:
        g, base = _V_GLIDE[v]
        return g, _V_BASE[base]
    return "", _V_BASE.get(v, (1, 1, 0))


def vowel_distance(a: str, b: str) -> int:
    ga, (ha, ba, ra) = _vowel(a)
    gb, (hb, bb, rb) = _vowel(b)
    return (ga != gb) + abs(ha - hb) + abs(ba - bb) + (ra != rb)


def coda_distance(a: str, b: str) -> int:
    ra, rb = _CODA_REP.get(a or "", a or ""), _CODA_REP.get(b or "", b or "")
    if ra == rb:
        return 0
    if not ra or not rb:
        return 2
    return cons_distance(ra, rb)


def _sound(word: str) -> List[Tuple[str, str, str]]:
    from scoring import to_pronounced_jamos
    out = []
    for i, m, f in to_pronounced_jamos(word):
        out.append(("" if i == "ㅇ" else i, m, f))
    return out


def sound_distance(a: str, b: str) -> int:
    """두 낱말의 소리 거리. 음절 수가 다르면 큰 값(99)이다. 0이면 소리가 같은 말(보기로 내지 않는다)."""
    sa, sb = _sound(a), _sound(b)
    if len(sa) != len(sb) or not sa:
        return 99
    d = 0
    for (i1, m1, f1), (i2, m2, f2) in zip(sa, sb):
        d += cons_distance(i1, i2) + vowel_distance(m1, m2) + coda_distance(f1, f2)
    return d


def contrast_of(a: str, b: str) -> List[Dict]:
    """같은 음절 수의 두 낱말이 어디서 다른지: [{slot: 'onset'|'vowel'|'coda', target, heard, syllable}]."""
    sa, sb = _sound(a), _sound(b)
    if len(sa) != len(sb):
        return []
    out = []
    for k, ((i1, m1, f1), (i2, m2, f2)) in enumerate(zip(sa, sb)):
        if i1 != i2:
            out.append({"slot": "onset", "target": i1 or "ㅇ", "heard": i2 or "ㅇ", "syllable": k})
        if vowel_distance(m1, m2):
            out.append({"slot": "vowel", "target": m1, "heard": m2, "syllable": k})
        if coda_distance(f1, f2):
            out.append({"slot": "coda", "target": _CODA_REP.get(f1, f1) or "-", "heard": _CODA_REP.get(f2, f2) or "-",
                        "syllable": k})
    return out


# 보기 거리 범위(수준별): 수준 1은 2지·확연히 다른 말, 2는 4지·중간, 3은 4지·한두 자질만 다른 말
WORD_LEVELS = {1: {"n": 2, "lo": 5, "hi": 99}, 2: {"n": 4, "lo": 3, "hi": 6}, 3: {"n": 4, "lo": 1, "hi": 2}}


# 낱말 일반화 검사(청인 파일럿 2절, 훈련 풀에서 뺀다). 단어 은행에서 2음절 이하, 소리 거리 3~6 이웃이 셋 이상, 소리 구별 음절·훈련
# 문장·대화·검사 문장에 나오지 않는 낱말을 시드 20261007로 고른 20개를 고정했다.
GEN_WORDS = ['겁', '곡', '기사', '껌', '남', '땀', '만두', '발등', '방지', '밭', '보드', '부두', '빨강', '뺨', '사상', '삽', '수레', '이마',
             '작문', '탈']


def word_pool(exclude: Optional[set] = None, include_gen: bool = False) -> List[str]:
    """낱말 고르기 풀: 단어 은행에서 드문 말(STAGE2_EXCLUDED)·독화 표준검사 정답·일반화 검사 낱말(GEN_WORDS)·exclude를 뺀 것.
    include_gen이면 일반화 검사 낱말을 남긴다(검사 문항의 보기를 만들 때)."""
    import curriculum as C
    skip = set(C.STAGE2_EXCLUDED) | set(exclude or ()) | (set() if include_gen else set(GEN_WORDS))
    try:
        from assessment import test_only_words
        skip |= set(test_only_words())
    except Exception:
        pass
    return [w["word"] for w in C.WORD_BANK if w["word"] not in skip]


_NEIGHBOR_CACHE: Dict[Tuple[str, ...], Dict[str, List[Tuple[int, str]]]] = {}


def _neighbors(pool: Sequence[str]) -> Dict[str, List[Tuple[int, str]]]:
    key = tuple(pool)
    if key not in _NEIGHBOR_CACHE:
        sounds = {w: _sound(w) for w in pool}
        table: Dict[str, List[Tuple[int, str]]] = {w: [] for w in pool}
        for i, a in enumerate(pool):
            for b in pool[i + 1:]:
                if len(sounds[a]) != len(sounds[b]):
                    continue
                d = sound_distance(a, b)
                if d > 0:
                    table[a].append((d, b))
                    table[b].append((d, a))
        for w in table:
            table[w].sort()
        _NEIGHBOR_CACHE.clear()
        _NEIGHBOR_CACHE[key] = table
    return _NEIGHBOR_CACHE[key]


def word_item(target: str, level: int, pool: Sequence[str], seed: str) -> Optional[Dict]:
    """정답 target의 보기. 수준 범위에 맞는 이웃이 모자라면 가까운 순으로 채운다(수준 1은 음절 수가 다른 말도 쓴다)."""
    cfg = WORD_LEVELS[max(1, min(3, int(level)))]
    r = _rng(f"w:{seed}:{target}:{level}")
    nb = _neighbors(pool).get(target, [])
    same_sound = {target} | {w for w in pool if w != target and sound_distance(target, w) == 0}
    fit = [w for d, w in nb if cfg["lo"] <= d <= cfg["hi"]]
    r.shuffle(fit)
    picks = fit[: cfg["n"] - 1]
    if len(picks) < cfg["n"] - 1:
        if level == 1:
            others = [w for w in pool if w not in same_sound and w not in picks and len(_sound(w)) != len(_sound(target))]
            r.shuffle(others)
            picks += others[: cfg["n"] - 1 - len(picks)]
        else:
            rest = [w for d, w in nb if w not in picks]
            # 수준 2는 범위 아래(더 가까운)부터, 3은 가까운 순으로
            picks += rest[: cfg["n"] - 1 - len(picks)]
    if len(picks) < cfg["n"] - 1:
        return None
    options = [target] + picks
    r.shuffle(options)
    return {"key": f"w:{target}", "target": target, "options": options, "level": int(level)}


def _matches(c: Dict, f: Dict) -> bool:
    return c["slot"] == f["slot"] and {c["target"], c["heard"]} == {f["target"], f["heard"]}


def word_items(level: int, pool: Sequence[str], seed: str, n: int = 10, weak: Sequence[str] = (), pick: str = "uniform",
               focus: Sequence[Dict] = (), review: Sequence[str] = ()) -> List[Dict]:
    """수준 level 문항 n개. 이웃이 넉넉한 낱말만 정답으로 쓴다.
    review(간격 복습이 된 낱말, 최대 3개)를 맨 앞에, weak(방금 틀린 낱말)를 그다음에 둔다.
    pick 'targeted'이고 focus(자주 헷갈린 대조 [{slot, target, heard}])가 있으면 문항의 절반까지는 그 대조로 갈리는 이웃을 보기에
    꼭 넣은 문항으로 채운다(수준 1은 음절 수가 다른 보기라 쓰지 않음)."""
    cfg = WORD_LEVELS[max(1, min(3, int(level)))]
    nb = _neighbors(pool)
    if level == 1:
        cands = list(pool)
    else:
        cands = [w for w in pool if sum(1 for d, _ in nb.get(w, []) if d <= cfg["hi"]) >= cfg["n"] - 1]
    r = _rng(f"wi:{seed}:{level}")
    r.shuffle(cands)
    cset = set(cands)
    out: List[Dict] = []
    used = set()

    def add(it):
        if it and it["target"] not in used:
            used.add(it["target"])
            out.append(it)

    for w in list(dict.fromkeys(review))[:3]:
        if w in cset:
            it = word_item(w, level, pool, seed)
            if it:
                it["review"] = True
            add(it)
    for w in weak:
        if len(out) >= n // 2:
            break
        if w in cset:
            add(word_item(w, level, pool, seed))
    if pick == "targeted" and focus and level >= 2:
        quota = n // 2
        k = 0
        for w in cands:
            if k >= quota or len(out) >= n:
                break
            if w in used:
                continue
            hit = None
            for d, o in nb.get(w, []):
                if d > cfg["hi"]:
                    break
                cs = contrast_of(w, o)
                if len(cs) == 1 and any(_matches(cs[0], f) for f in focus):
                    hit = (o, cs[0])
                    break
            if not hit:
                continue
            it = word_item(w, level, pool, seed)
            if not it:
                continue
            if hit[0] not in it["options"]:
                it["options"][next(i for i, x in enumerate(it["options"]) if x != w)] = hit[0]
            it["focus"] = {"slot": hit[1]["slot"], "target": hit[1]["target"], "heard": hit[1]["heard"]}
            add(it)
            k += 1
    for w in cands:
        if len(out) >= n:
            break
        if w not in used:
            add(word_item(w, level, pool, seed))
    for it in out:
        it["pick"] = pick
    return out[:n]


# ── 간격 복습(고도화 방안 P3) ─────────────────────────────────────────
# 틀린 문항은 같은 단계 안에서 하루 뒤, 맞히면 사흘 뒤 한 번 더 낸다. 틀린 뒤 두 번 맞히면 빠진다. 전체 복습 큐(ReviewItem)와 따로 둔다
# (소리 문항은 오늘의 복습 화면이 재생하지 못한다).
REVIEW_GAPS = (1, 3)


def due_reviews(history: Sequence[Tuple[str, bool, "object"]], today) -> List[str]:
    """[(문항, 정답, 날짜)] 시간순 → 오늘 복습할 문항(오래 기다린 순). 마지막 오답 뒤 맞힌 수 m이 0이면 마지막 시도 다음 날부터,
    1이면 사흘 뒤부터 낸다. 2 이상이면 빠진다."""
    last_wrong, after, last_seen = {}, {}, {}
    for item, ok, day in history:
        last_seen[item] = day
        if not ok:
            last_wrong[item] = day
            after[item] = 0
        elif item in last_wrong:
            after[item] = after.get(item, 0) + 1
    due = []
    for item, wd in last_wrong.items():
        m = after.get(item, 0)
        if m >= len(REVIEW_GAPS):
            continue
        gap = (today - last_seen[item]).days
        if gap >= REVIEW_GAPS[m]:
            due.append((gap, item))
    due.sort(key=lambda x: -x[0])
    return [i for _, i in due]


def gen_test_items(pool_with_gen: Sequence[str]) -> List[Dict]:
    """낱말 일반화 검사 20문항(수준 2, 4지, 고정 순서·보기). 보기는 훈련 풀 낱말을 쓴다(검사 낱말끼리는 섞지 않음)."""
    train = [w for w in pool_with_gen if w not in set(GEN_WORDS)]
    out = []
    for i, w in enumerate(GEN_WORDS):
        it = word_item(w, 2, list(train) + [w], "gen-20261007")
        if it:
            out.append({"key": f"g:{w}", "target": w, "options": it["options"], "n": i + 1})
    return out


# ── 3·4단계: 문장 ───────────────────────────────────────────────────
# 훈련 문장. 2~5어절의 생활 문장. 숫자는 한글로 적는다(합성·채점이 같은 글을 보게).

TRAIN_SENTENCES: List[str] = [
    "오늘 점심 뭐 먹을까요?", "창문 좀 열어 주세요.", "택시가 금방 올 거예요.", "저는 커피보다 차가 좋아요.", "주말에는 날씨가 춥대요.",
    "이 신발 얼마예요?", "엘리베이터는 오른쪽에 있어요.", "지갑을 집에 두고 왔어요.", "주말에 영화 보러 갈래요?", "손을 깨끗이 씻으세요.",
    "감기 때문에 목이 아파요.", "다음 역에서 내리면 돼요.", "우산 가져가는 게 좋겠어요.", "동생이 지금 학교에 있어요.", "이 길로 쭉 가세요.",
    "회의가 삼십 분 늦어졌어요.", "냉장고에 우유가 없어요.", "사진 한 장 찍어 주실래요?", "아침에 늦잠을 잤어요.", "휴대폰 충전기 있어요?",
    "오늘 저녁은 제가 살게요.", "강아지가 공원에서 뛰어놀아요.", "택배가 문 앞에 왔어요.", "잠깐만 기다려 주세요.", "이번 주 금요일에 시간 있어요?",
    "숙제를 아직 못 했어요.", "병원 예약을 바꾸고 싶어요.", "따뜻한 물 한 잔 주세요.", "삼촌 댁에서 하룻밤 잤어요.", "이 책 정말 재미있어요.",
    "계산은 카드로 할게요.", "문이 잠겨 있어요.", "생일 축하해요.", "길이 많이 막히네요.", "표를 두 장 예매했어요.",
    "오늘 너무 피곤해요.", "김치찌개가 조금 매워요.", "시험이 다음 주예요.", "불 좀 꺼 주세요.", "친구랑 도서관에서 공부했어요.",
    "아이스크림이 다 녹았어요.", "열 시까지 오시면 돼요.", "출구가 어느 쪽이에요?", "고양이가 소파 위에서 자요.", "이 옷 입어 봐도 돼요?",
    "오랜만에 운동을 했어요.", "밖에 바람이 많이 불어요.", "사과 세 개만 주세요.", "조금 더 크게 말해 주세요.", "지하철이 버스보다 빨라요.",
    "어제 산 우유가 상했어요.", "컴퓨터가 갑자기 꺼졌어요.", "우리 같이 걸어갈까요?", "저녁에 전화할게요.", "허리가 계속 아파요.",
    "비행기가 한 시간 늦게 떠요.", "벚꽃이 벌써 다 졌어요.", "텔레비전 소리 좀 줄여 주세요.", "오늘은 일찍 잘 거예요.", "약은 식사 후에 드세요.",
    "가방이 생각보다 무거워요.", "영수증 드릴까요?", "물이 너무 차가워요.", "이번 정류장은 시청입니다.", "주차장은 지하에 있어요.",
    "봄이 되면 여행 가고 싶어요.", "안경을 새로 맞췄어요.", "다음에 또 만나요.", "아직 밥을 안 먹었어요.", "이 자리 비어 있어요?",
    "공책 한 권 빌려줄래요?", "오늘 수업은 휴강이에요.", "빵이 아주 부드러워요.", "손님이 곧 오실 거예요.", "창밖에 눈이 와요.",
    "이 근처에 약국 있어요?", "기차표를 잃어버렸어요.", "천천히 드세요.", "오후에 비가 그친대요.", "수업이 몇 시에 끝나요?",
    "배가 너무 고파요.", "신호등이 초록불로 바뀌었어요.", "이 노래 정말 좋아요.", "짐 드는 거 도와드릴게요.", "어디서 내리세요?",
    "방이 너무 더워요.", "엄마가 반찬을 보내 주셨어요.", "내일 아침에 다시 올게요.", "줄이 꽤 길어요.", "이름을 여기에 써 주세요.",
    "신발 끈 좀 묶고 갈게요.", "오늘 몇 월 며칠이에요?", "비밀번호를 잊어버렸어요.", "반찬이 조금 짜요.", "자전거 타고 출근해요.",
    "이 문은 당겨서 여세요.", "다들 벌써 도착했어요.", "수박이 아주 시원해요.", "아이가 열이 나요.", "이따가 다시 전화 주세요.",
]


def sentence_id(i: int) -> str:
    return f"t{i + 1:03d}"


TRAIN_BY_ID: Dict[str, str] = {sentence_id(i): s for i, s in enumerate(TRAIN_SENTENCES)}

# 소음 속 문장 인식 역치(SRT) 검사 문장. 두 폼은 같은 꼴(같은 자리의 문장이 같은 구조·어절 수)로 짝을 맞췄다.
# 사전 검사는 한 폼, 사후는 다른 폼으로 하고 폼 순서는 학습자마다 번갈아 정한다(test_form_for).
TEST_FORMS: Dict[str, List[str]] = {
    "A": ["책상 위에 열쇠가 있어요.", "오늘은 버스를 타고 왔어요.", "냄비에 물을 끓여 주세요.", "우리 집은 삼 층이에요.",
          "친구가 선물을 줬어요.", "밤에 별이 많이 보여요.", "의자를 저쪽으로 옮겨 주세요.", "시계가 오 분 빨라요.",
          "동생은 노래를 잘 불러요.", "편지를 우체국에서 보냈어요.", "거울 앞에서 머리를 빗어요.", "바닥이 미끄러우니 조심해서 걸으세요.",
          "사탕을 하나만 먹었어요.", "형이 새 차를 샀어요.", "저녁에 산책하러 나가요.", "연필이 책상 밑에 떨어졌어요.",
          "아버지는 신문을 읽으세요.", "냉면을 두 그릇 시켰어요.", "가을에는 하늘이 높아요.", "수건을 빨래 바구니에 넣어요."],
    "B": ["침대 옆에 안경이 있어요.", "어제는 택시를 타고 갔어요.", "그릇에 밥을 담아 주세요.", "사무실은 이 층에 있어요.",
          "누나가 케이크를 만들었어요.", "아침에 새가 많이 울어요.", "상자를 현관에 놓아 주세요.", "기차가 십 분 늦었어요.",
          "언니는 피아노를 잘 쳐요.", "소포를 편의점에서 찾았어요.", "세면대 앞에서 이를 닦아요.", "계단이 높으니 천천히 오세요.",
          "과자를 반만 먹었어요.", "삼촌이 새 집으로 이사했어요.", "주말에 등산하러 가요.", "숟가락이 식탁 아래 떨어졌어요.",
          "어머니는 뉴스를 보세요.", "김밥을 세 줄 샀어요.", "겨울에는 해가 짧아요.", "양말을 서랍 안에 넣어요."],
}


def test_form_for(user_id: int, n_done: int) -> str:
    """학습자의 n_done번째(0부터) 검사 폼. 짝수 id는 A → B → A …, 홀수 id는 B → A → B …."""
    first = "A" if int(user_id) % 2 == 0 else "B"
    other = "B" if first == "A" else "A"
    return first if n_done % 2 == 0 else other


def sentence_items(seed: str, n: int = 8, recent: Sequence[str] = (), review: Sequence[str] = ()) -> List[Dict]:
    """훈련 문장 n개. 간격 복습 문장(review id, 최대 2개)을 앞에 두고, 최근에 낸 문장(recent id)은 뒤로 미룬다."""
    ids = list(TRAIN_BY_ID)
    r = _rng(f"s:{seed}")
    r.shuffle(ids)
    rv = [i for i in dict.fromkeys(review) if i in TRAIN_BY_ID][:2]
    seen = set(recent) | set(rv)
    ids = rv + [i for i in ids if i not in seen] + [i for i in ids if i in seen and i not in rv]
    return [{"key": f"s:{i}", "id": i, "text": TRAIN_BY_ID[i], **({"review": True} if i in rv else {})} for i in ids[:n]]


def word_score(target: str, answer: str) -> Dict:
    """문장 답의 낱말 정답 비율과 자음 피드백(sentence_feedback.consonant_feedback, 소리 나는 대로 비교)."""
    from sentence_feedback import consonant_feedback
    fb = consonant_feedback(target, answer)
    total = fb.get("total_words") or 0
    prop = (fb.get("correct_words") or 0) / total if total else 0.0
    return {"proportion": round(prop, 3), "feedback": fb}


# ── 4단계: 소음 크기 계단 ──────────────────────────────────────────────
# 1-up-1-down: 문장의 낱말 절반 이상을 맞히면 소음을 키우고(SNR을 낮추고), 아니면 줄인다. 4어절 문장은 2개만 맞아도 '맞음'이라
# 실제로는 낱말 약 39~40% 지점으로 모인다(SRT40 근처, 시뮬레이션 편향 −0.8 dB, docs/listen-adaptive-sim-2026-10.md). 원래 설계 의도는 낱말을 절반쯤 알아듣는
# SNR로 모인다(Levitt 1971). 처음 두 번 방향이 바뀔 때까지는 4 dB, 그 뒤 2 dB. 범위 -10 ~ +25 dB, 시작 +10 dB. 인공와우 사용자의
# 50% 문장 SNR은 3.5 ~ 20 dB 넘게 퍼지고 평균이 약 11 dB라(Gifford 2010) 위쪽을 넉넉히 둔다(docs/auditory-training-evidence-2026-10.md).
# 역치 추정은 방향이 바뀐 지점 마지막 6개의 평균(4개 미만이면 마지막 8번 SNR 평균).
# 훈련은 소리만이 기본이고 네 번에 한 번만 소리+입모양으로 낸다(AV_EVERY). 시청각 훈련 근거는 정상 청력 성인 연구뿐이고, 입모양을
# 함께 준 훈련이 소리만의 학습을 떨어뜨린 실험도 있어(Bernstein 2013) 입모양 시행은 시청각 이득을 재는 데 쓴다.

STAIR = {"start": 10.0, "big": 4.0, "small": 2.0, "big_reversals": 2, "lo": -10.0, "hi": 25.0, "criterion": 0.5}
AV_EVERY = 4


def noise_condition(n_done: int) -> str:
    """4단계 n_done번째(0부터) 시행의 조건: 네 번째마다 'av', 나머지 'ao'."""
    return "av" if n_done % AV_EVERY == AV_EVERY - 1 else "ao"


def stair_state(trials: Sequence[Tuple[float, bool]], cfg: Dict = STAIR) -> Dict:
    """trials: 같은 조건의 (그때 SNR, 맞음) 시간순. 다음 SNR·방향 전환·역치 추정을 돌려준다."""
    snr = float(cfg["start"])
    reversals: List[float] = []
    last_dir = 0
    for s, ok in trials:
        s = float(s)
        d = -1 if ok else +1          # 맞으면 SNR을 내린다(소음을 키운다)
        if last_dir and d != last_dir:
            reversals.append(s)
        last_dir = d
        step = cfg["big"] if len(reversals) < cfg["big_reversals"] else cfg["small"]
        snr = min(cfg["hi"], max(cfg["lo"], s + d * step))
    return {"next_db": round(snr, 1), "n_trials": len(trials), "n_reversals": len(reversals),
            "srt_db": srt_estimate(trials, reversals)}


def srt_estimate(trials: Sequence[Tuple[float, bool]], reversals: Optional[Sequence[float]] = None) -> Optional[float]:
    if reversals is None:
        reversals = _reversals(trials)
    if len(reversals) >= 4:
        xs = list(reversals)[-6:]
        return round(sum(xs) / len(xs), 1)
    if len(trials) >= 8:
        xs = [float(s) for s, _ in trials[-8:]]
        return round(sum(xs) / len(xs), 1)
    return None


def _reversals(trials: Sequence[Tuple[float, bool]]) -> List[float]:
    out, last = [], 0
    for s, ok in trials:
        d = -1 if ok else 1
        if last and d != last:
            out.append(float(s))
        last = d
    return out


def noise_mastered(ao_trials: Sequence[Tuple[float, bool]], cfg: Dict = NOISE_MASTER) -> bool:
    """4단계 숙달: 소리만 조건 시도가 min_trials 이상이고, 최근 window번의 역치가 srt_db 이하이거나, 시도가 2×window 이상이고
    처음 window번 역치보다 최근 window번 역치가 gain_db 이상 낮다. 역치 추정을 못 하면 숙달이 아니다."""
    n = len(ao_trials)
    if n < cfg["min_trials"]:
        return False
    w = cfg["window"]
    recent = srt_estimate(list(ao_trials[-w:]))
    if recent is not None and recent <= cfg["srt_db"]:
        return True
    if n >= 2 * w:
        first = srt_estimate(list(ao_trials[:w]))
        if first is not None and recent is not None and first - recent >= cfg["gain_db"]:
            return True
    return False


# 검사 계단(Plomp·Mimpen 1979 방식을 낱말 기준으로): 20문장, +10 dB 시작, 처음 4문장은 4 dB, 그 뒤 2 dB. 역치 = 5~20번째
# 문장 SNR과 (21번째로 냈을) 다음 SNR의 평균.
TEST_STAIR = {"start": 10.0, "big": 4.0, "small": 2.0, "big_trials": 4, "lo": -10.0, "hi": 25.0, "criterion": 0.5}


def test_next_snr(trials: Sequence[Tuple[float, bool]], cfg: Dict = TEST_STAIR) -> float:
    snr = float(cfg["start"])
    for k, (s, ok) in enumerate(trials):
        step = cfg["big"] if k < cfg["big_trials"] else cfg["small"]
        snr = min(cfg["hi"], max(cfg["lo"], float(s) + (-step if ok else step)))
    return round(snr, 1)


def test_srt(trials: Sequence[Tuple[float, bool]], cfg: Dict = TEST_STAIR) -> Optional[float]:
    """검사 역치. 20문장을 다 들어야 낸다."""
    if len(trials) < 20:
        return None
    xs = [float(s) for s, _ in trials[4:20]] + [test_next_snr(trials, cfg)]
    return round(sum(xs) / len(xs), 1)


# ── 5단계: 대화 듣기 ─────────────────────────────────────────────────
# 생활 장면의 한 마디(line)와 쉬운 말로 바꾼 말(paraphrase, '다른 말로' 되묻기), 내용 질문과 4지 보기.

CONVO_ITEMS: List[Dict] = [
    {"id": "c01", "place": "병원", "line": "진료는 두 시 반부터 다시 시작해요.", "paraphrase": "두 시 반에 진료가 다시 열려요.",
     "question": "진료가 다시 시작하는 시간은?", "options": ["두 시 반", "한 시 반", "두 시", "세 시 반"], "answer": 0},
    {"id": "c02", "place": "약국", "line": "이 약은 하루 세 번, 식사하고 삼십 분 뒤에 드세요.",
     "paraphrase": "밥 먹고 삼십 분 지나서, 하루에 세 번 드세요.",
     "question": "약은 언제 먹어요?", "options": ["밥 먹기 전", "밥 먹고 삼십 분 뒤", "잠자기 전", "아침에 한 번"], "answer": 1},
    {"id": "c03", "place": "카페", "line": "따뜻한 라떼는 지금 안 되고, 차가운 것만 돼요.", "paraphrase": "라떼는 차가운 것만 주문할 수 있어요.",
     "question": "주문할 수 있는 라떼는?", "options": ["따뜻한 라떼", "차가운 라떼", "둘 다 안 돼요", "둘 다 돼요"], "answer": 1},
    {"id": "c04", "place": "버스 안내", "line": "이번 정류장은 시청, 다음 정류장은 서울역입니다.", "paraphrase": "지금은 시청이고, 다음은 서울역이에요.",
     "question": "다음 정류장은?", "options": ["시청", "서울역", "종로", "광화문"], "answer": 1},
    {"id": "c05", "place": "식당", "line": "자리가 없어서 이십 분 정도 기다리셔야 해요.", "paraphrase": "빈자리가 없어요. 이십 분쯤 기다려 주세요.",
     "question": "얼마나 기다려야 해요?", "options": ["이 분", "십 분", "이십 분", "한 시간"], "answer": 2},
    {"id": "c06", "place": "은행", "line": "번호표를 뽑고 의자에 앉아 기다려 주세요.", "paraphrase": "먼저 번호표를 뽑으세요. 그리고 앉아서 기다리세요.",
     "question": "먼저 해야 할 일은?", "options": ["통장 내기", "번호표 뽑기", "창구로 가기", "전화하기"], "answer": 1},
    {"id": "c07", "place": "택배", "line": "택배는 경비실에 맡겨 두었습니다.", "paraphrase": "물건을 경비실에 두었어요.",
     "question": "택배는 어디에 있어요?", "options": ["문 앞", "경비실", "편의점", "우체국"], "answer": 1},
    {"id": "c08", "place": "학교", "line": "내일은 체육복을 꼭 가져오세요.", "paraphrase": "내일 체육복을 잊지 말고 챙겨 오세요.",
     "question": "내일 가져갈 것은?", "options": ["우산", "체육복", "도시락", "교과서"], "answer": 1},
    {"id": "c09", "place": "회사", "line": "회의실이 바뀌어서 삼 층 큰 방에서 해요.", "paraphrase": "회의는 삼 층 큰 방에서 해요. 장소가 바뀌었어요.",
     "question": "회의는 어디서 해요?", "options": ["이 층 작은 방", "삼 층 큰 방", "일 층 로비", "사 층 회의실"], "answer": 1},
    {"id": "c10", "place": "마트", "line": "우유는 하나 사면 하나 더 드려요.", "paraphrase": "우유 하나를 사면 하나를 공짜로 줘요.",
     "question": "우유를 하나 사면?", "options": ["반값이에요", "하나 더 줘요", "할인이 없어요", "두 개 더 줘요"], "answer": 1},
    {"id": "c11", "place": "전화", "line": "지금 통화가 어려우니 문자로 보내 주세요.", "paraphrase": "전화는 힘들어요. 문자를 보내 주세요.",
     "question": "어떻게 연락해야 해요?", "options": ["다시 전화하기", "문자 보내기", "메일 보내기", "직접 찾아가기"], "answer": 1},
    {"id": "c12", "place": "지하철", "line": "이 열차는 이번 역까지만 운행합니다. 모두 내려 주세요.", "paraphrase": "열차가 여기서 끝나요. 다 내리세요.",
     "question": "무엇을 해야 해요?", "options": ["계속 타기", "내리기", "앉아서 기다리기", "표 사기"], "answer": 1},
    {"id": "c13", "place": "날씨", "line": "오후부터 비가 오다가 저녁에는 그친대요.", "paraphrase": "비는 오후에 오고 저녁에 멈춘대요.",
     "question": "비는 언제 그쳐요?", "options": ["아침", "점심", "저녁", "밤새 와요"], "answer": 2},
    {"id": "c14", "place": "미용실", "line": "커트는 만 오천 원이고, 파마는 오만 원이에요.", "paraphrase": "머리 자르는 건 만 오천 원이에요.",
     "question": "커트 값은?", "options": ["오천 원", "만 오천 원", "오만 원", "만 원"], "answer": 1},
    {"id": "c15", "place": "친구", "line": "토요일은 안 되고 일요일 오후에 만나자.", "paraphrase": "일요일 오후에 보자. 토요일은 바빠.",
     "question": "언제 만나요?", "options": ["토요일 오전", "토요일 오후", "일요일 오후", "일요일 오전"], "answer": 2},
    {"id": "c16", "place": "병원 접수", "line": "처음 오셨으면 이 종이에 이름과 연락처를 써 주세요.",
     "paraphrase": "처음이면 여기에 이름이랑 전화번호를 적어 주세요.",
     "question": "종이에 쓸 것은?", "options": ["주소와 나이", "이름과 연락처", "아픈 곳", "생일"], "answer": 1},
    {"id": "c17", "place": "기차역", "line": "부산행 기차는 칠 번 타는 곳에서 출발합니다.", "paraphrase": "부산 가는 기차는 칠 번에서 타세요.",
     "question": "몇 번에서 타요?", "options": ["일 번", "사 번", "칠 번", "팔 번"], "answer": 2},
    {"id": "c18", "place": "도서관", "line": "책은 이 주 동안 빌릴 수 있어요.", "paraphrase": "빌린 책은 이 주 뒤에 돌려주세요.",
     "question": "책을 빌리는 기간은?", "options": ["일주일", "이 주", "한 달", "사흘"], "answer": 1},
    {"id": "c19", "place": "가게", "line": "카드는 안 되고 현금만 받아요.", "paraphrase": "현금으로만 계산할 수 있어요.",
     "question": "어떻게 계산해요?", "options": ["카드", "현금", "휴대폰", "상품권"], "answer": 1},
    {"id": "c20", "place": "건물 안내", "line": "엘리베이터 점검 중이니 계단을 이용해 주세요.", "paraphrase": "엘리베이터를 고치고 있어요. 계단으로 가세요.",
     "question": "어떻게 올라가요?", "options": ["엘리베이터", "계단", "에스컬레이터", "기다리기"], "answer": 1},
    {"id": "c21", "place": "식당 주문", "line": "비빔밥은 다 떨어졌고 김치찌개는 돼요.", "paraphrase": "비빔밥은 없어요. 김치찌개는 있어요.",
     "question": "주문할 수 있는 것은?", "options": ["비빔밥", "김치찌개", "둘 다", "둘 다 안 돼요"], "answer": 1},
    {"id": "c22", "place": "약속", "line": "길이 막혀서 십 분쯤 늦을 것 같아요.", "paraphrase": "차가 막혀요. 십 분 정도 늦어요.",
     "question": "왜 늦어요?", "options": ["늦잠을 자서", "길이 막혀서", "길을 잃어서", "버스를 놓쳐서"], "answer": 1},
    {"id": "c23", "place": "안내 방송", "line": "매장은 십 분 뒤에 문을 닫습니다.", "paraphrase": "가게가 십 분 있으면 닫아요.",
     "question": "가게는 언제 닫아요?", "options": ["지금", "십 분 뒤", "한 시간 뒤", "내일"], "answer": 1},
    {"id": "c24", "place": "집", "line": "냉장고에 반찬 있으니까 데워 먹어.", "paraphrase": "반찬은 냉장고에 있어. 따뜻하게 해서 먹어.",
     "question": "반찬은 어디에 있어요?", "options": ["식탁", "냉장고", "전자레인지", "찬장"], "answer": 1},
    {"id": "c25", "place": "수업", "line": "숙제는 금요일까지 메일로 보내세요.", "paraphrase": "금요일이 되기 전에 메일로 숙제를 내세요.",
     "question": "숙제는 언제까지?", "options": ["월요일", "수요일", "금요일", "일요일"], "answer": 2},
    {"id": "c26", "place": "택시", "line": "여기서 내려 드릴까요, 건물 앞까지 갈까요?", "paraphrase": "지금 내릴래요, 아니면 건물 앞에서 내릴래요?",
     "question": "기사님이 묻는 것은?", "options": ["요금", "내릴 곳", "가는 곳 주소", "계산 방법"], "answer": 1},
    {"id": "c27", "place": "병원", "line": "검사 결과는 다음 주 화요일에 나와요.", "paraphrase": "결과는 다음 주 화요일에 알 수 있어요.",
     "question": "결과는 언제 나와요?", "options": ["내일", "이번 주 금요일", "다음 주 화요일", "다음 달"], "answer": 2},
    {"id": "c28", "place": "카페", "line": "주문하신 음료는 진동벨이 울리면 가져가세요.", "paraphrase": "벨이 울리면 음료를 받으러 오세요.",
     "question": "언제 음료를 가져가요?", "options": ["바로", "벨이 울리면", "이름을 부르면", "십 분 뒤"], "answer": 1},
    {"id": "c29", "place": "우체국", "line": "등기는 내일 도착하고, 일반 우편은 사흘 걸려요.", "paraphrase": "등기로 보내면 내일 가요.",
     "question": "등기는 언제 도착해요?", "options": ["오늘", "내일", "사흘 뒤", "일주일 뒤"], "answer": 1},
    {"id": "c30", "place": "이웃", "line": "내일 아침 아홉 시부터 물이 안 나온대요.", "paraphrase": "내일 아침 아홉 시에 물이 끊긴대요.",
     "question": "무엇이 안 나와요?", "options": ["전기", "물", "가스", "인터넷"], "answer": 1},
]
CONVO_BY_ID = {c["id"]: c for c in CONVO_ITEMS}
# 듣기 조건(5단계 선택): 조용함, 잡음(학습자의 4단계 역치 + 5 dB), 전화(300~3400 Hz 대역), 울리는 방(잔향).
# 잔향은 인공와우 사용자의 문장 인식을 꾸준히 떨어뜨린다(RT60 0.3초 약 60%, 1.0초 약 20%, Kokkinakis 2011). 방을 한 곳으로 고정하지
# 않고 여러 잔향 시간을 돌려 가며 낸다(여러 방에서 훈련할 때만 새 방으로 옮겨 갔다, Vlahou 2019). 화면이 ConvolverNode로 입힌다.
CONVO_CONDITIONS = ("quiet", "noise", "phone", "room")
ROOM_RT60 = (0.3, 0.5, 0.8)
# 잡음 종류(서버 음성 C17의 noise/). 4단계 계단·검사는 babble 하나로 고정하고(계단이 잡음 종류에 따라 흔들리지 않게), 5단계 소음 조건은
# 문항마다 종류를 돌린다. talker2(두 사람)는 훈련에 쓰지 않고 일반화 확인용으로 남긴다(docs/listen-advance-plan-2026-10.md S1).
TRAIN_NOISES = ("talker1_f", "talker1_m", "ssn", "babble")
HELDOUT_NOISE = "talker2"
TEST_NOISES = ("babble", HELDOUT_NOISE)   # 역치 검사 잡음: 주 결과 babble, 일반화 talker2


def convo_items(seed: str, n: int = 8, recent: Sequence[str] = ()) -> List[Dict]:
    ids = list(CONVO_BY_ID)
    r = _rng(f"c:{seed}")
    r.shuffle(ids)
    seen = set(recent)
    ids = [i for i in ids if i not in seen] + [i for i in ids if i in seen]
    out = []
    for i in ids[:n]:
        c = CONVO_BY_ID[i]
        # 정답 번호는 응답에서 뺀다(채점은 서버)
        out.append({"key": f"c:{i}", "id": i, "place": c["place"], "line": c["line"], "paraphrase": c["paraphrase"],
                    "question": c["question"], "options": list(c["options"])})
    return out


def convo_correct(key: str, choice: int) -> Optional[bool]:
    c = CONVO_BY_ID.get((key or "")[2:]) if (key or "").startswith("c:") else None
    if not c:
        return None
    return int(choice) == int(c["answer"])


# ── 0단계: Ling 6소리 ───────────────────────────────────────────────
# 화면이 Web Audio로 합성한다: 음(m, 낮은 콧소리), 우(u), 아(a), 이(i, 낮은 F1과 높은 F2), 쉬(ʃ, 2~5 kHz 잡음), 스(s, 4~8 kHz 잡음).
# 저주파 → 고주파를 고르게 덮어 어느 대역이 안 들리는지 알 수 있다(Ling 1976). 소리 없는 시행 2개를 섞어 '들렸어요'를 습관적으로
# 누르는지 본다.

LING_SOUNDS = [
    {"key": "m", "label": "음", "band": "낮은 소리"}, {"key": "u", "label": "우", "band": "낮은 소리"},
    {"key": "a", "label": "아", "band": "가운데 소리"}, {"key": "i", "label": "이", "band": "낮은·높은 소리"},
    {"key": "sh", "label": "쉬", "band": "높은 소리"}, {"key": "s", "label": "스", "band": "아주 높은 소리"},
]
LING_KEYS = [s["key"] for s in LING_SOUNDS]


def ling_sequence(seed: str) -> List[str]:
    """여섯 소리 + 소리 없는 시행 2개('silent')를 섞은 순서."""
    seq = LING_KEYS + ["silent", "silent"]
    _rng(f"ling:{seed}").shuffle(seq)
    return seq


def ling_summary(results: Dict[str, bool], previous: Optional[Dict[str, bool]] = None) -> Dict:
    """오늘 점검 결과 정리. results는 {소리: 들렸는가}와 'silent_false_alarms'(소리 없을 때 들렸다고 한 수).
    지난번에 들렸는데 오늘 안 들린 소리는 dropped로 알린다(기기 점검 권유)."""
    heard = [k for k in LING_KEYS if results.get(k)]
    missed = [k for k in LING_KEYS if k in results and not results.get(k)]
    dropped = [k for k in missed if previous and previous.get(k)]
    fa = int(results.get("silent_false_alarms") or 0)
    return {"heard": heard, "missed": missed, "dropped": dropped, "false_alarms": fa, "reliable": fa == 0}


# ── 독화·발화와 잇기 ──────────────────────────────────────────────────

def recommendations(confusions: Sequence[Dict], k: int = 3) -> List[Dict]:
    """낱말 고르기에서 자주 헷갈린 소리 짝 → 다음 연습 제안. confusions: [{slot, target, heard, n}] 많은 순.
    입모양 무리가 다른 자음 짝은 입모양이 보완해 주므로 독화 레슨을, 같은 무리(ㅂ·ㅁ 등)는 소리로만 가를 수 있으므로 소리 구별을
    권한다. 자음 짝은 말하기 자음 단계도 함께 권한다."""
    from engine import VISEME_MAP
    out = []
    for c in list(confusions)[:k]:
        t, h = c.get("target"), c.get("heard")
        if c.get("slot") == "vowel":
            vt, vh = VISEME_MAP.get(t), VISEME_MAP.get(h)
            lip = vt is not None and vh is not None and vt != vh
            out.append({"pair": [t, h], "slot": "vowel", "lip_differs": lip,
                        "text": f"모음 {t}와 {h}를 자주 헷갈려요." + (" 입모양은 달라서 입을 함께 보면 도움이 돼요." if lip
                                                                  else " 입모양도 비슷해서 소리 구별 연습이 필요해요."),
                        "routes": [{"label": "입모양 레슨" if lip else "소리 구별", "to": "/learn/viseme" if lip else "/learn/listening?stage=1"}]})
            continue
        vt = VISEME_MAP.get(t) if t not in ("-", "ㅇ") else None
        vh = VISEME_MAP.get(h) if h not in ("-", "ㅇ") else None
        lip = vt is not None and vh is not None and vt != vh
        where = "받침" if c.get("slot") == "coda" else "첫소리"
        text = (f"{where} {t}와 {h}를 자주 헷갈려요. 입모양은 달라서 입을 함께 보면 구별할 수 있어요." if lip
                else f"{where} {t}와 {h}를 자주 헷갈려요. 입모양이 같거나 잘 안 보여서 소리로 가려야 해요.")
        routes = [{"label": "입모양 레슨", "to": "/learn/viseme"}] if lip else [{"label": "소리 구별", "to": "/learn/listening?stage=1"}]
        routes.append({"label": "말하기 자음", "to": "/learn/speaking?stage=3"})
        out.append({"pair": [t, h], "slot": c.get("slot"), "lip_differs": lip, "text": text, "routes": routes})
    return out


def tally_confusions(pairs: Sequence[Tuple[str, str]]) -> List[Dict]:
    """(정답 낱말, 고른 낱말) 오답 목록 → 자리별 소리 짝 빈도(많은 순)."""
    counts: Dict[Tuple[str, str, str], int] = {}
    for target, heard in pairs:
        for c in contrast_of(target, heard):
            key = (c["slot"], c["target"], c["heard"])
            counts[key] = counts.get(key, 0) + 1
    rows = [{"slot": s, "target": t, "heard": h, "n": n} for (s, t, h), n in counts.items()]
    rows.sort(key=lambda r: (-r["n"], r["slot"], r["target"]))
    return rows


# ── 합성할 글 ─────────────────────────────────────────────────────────
# 소리 크기 맞추기 화면의 예시 문장(편안한 크기를 고를 때 듣는다)
CALIBRATION_TEXT = "안녕하세요. 이 정도 크기가 편안한가요?"

def inventory_texts() -> List[str]:
    """소리 조건(C17)이 듣기 목소리 전부로 미리 합성할 글(scripts/sound_inventory.py의 source 'listen')."""
    texts: List[str] = [CALIBRATION_TEXT]
    texts += sorted(_AX_TEXTS)
    texts += word_pool(include_gen=True)
    texts += TRAIN_SENTENCES
    texts += [s for f in sorted(TEST_FORMS) for s in TEST_FORMS[f]]
    for c in CONVO_ITEMS:
        texts += [c["line"], c["paraphrase"]]
    return list(dict.fromkeys(texts))
