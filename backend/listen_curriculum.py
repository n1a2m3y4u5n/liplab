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
import functools
import hashlib
import json
import math
import os
import random
from typing import Dict, List, Optional, Sequence, Tuple

# ── 단계 ─────────────────────────────────────────────────────────────

STAGES: List[Dict] = [
    {"stage": 0, "key": "ling", "title": "소리 확인", "mode": "ling", "icon": "🔔",
     "desc": "여섯 가지 소리가 들리는지 확인해요. 날마다 하면 보청기나 인공와우에 문제가 없는지도 알 수 있어요.",
     "guide": "소리가 들리면 '들렸어요'를 눌러요. 들리지 않으면 '안 들렸어요'를 눌러요. 아무 소리도 나지 않을 때도 있어요."},
    {"stage": 1, "key": "ax", "title": "소리 구별", "mode": "ax", "icon": "👂",
     "desc": "두 소리를 듣고 같은지 다른지 골라요. 많이 다른 소리부터 시작해서 점점 비슷한 소리로 넘어가요.",
     "guide": "두 소리를 차례로 들려줘요. 같은 소리면 '같아요', 다르면 '달라요'를 눌러요."},
    {"stage": 2, "key": "word_id", "title": "낱말 고르기", "mode": "word_id", "icon": "🔤",
     "desc": "소리만 듣고 어떤 낱말인지 보기에서 골라요.",
     "guide": "낱말 하나를 들려줘요. 들은 낱말을 보기에서 골라요. 다시 들을 수 있어요."},
    {"stage": 3, "key": "sentence", "title": "문장 알아듣기", "mode": "sentence", "icon": "💬",
     "desc": "조용한 곳에서 문장을 듣고 들은 대로 입력해요.",
     "guide": "문장을 들려줘요. 들은 대로 써요. 틀린 낱말은 글자마다 첫 자음만 보여 줘요. 한 번 더 듣고 고쳐 써요."},
    {"stage": 4, "key": "noise", "title": "소음 속 듣기", "mode": "noise", "icon": "🎧",
     "desc": "여러 사람이 떠드는 소리 속에서 문장을 알아들어요. 맞히면 소음이 커지고, 놓치면 작아져요.",
     "guide": "문장을 듣고 들은 대로 써요. 네 번에 한 번은 입모양도 함께 나와요. 전체 소리 크기는 그대로예요. 말소리와 소음의 크기 차이만 바뀌어요."},
    {"stage": 5, "key": "convo", "title": "대화 듣기", "mode": "convo", "icon": "🗣️",
     "desc": "병원·가게·안내 방송 같은 생활 속 말을 듣고 내용을 골라요.",
     "guide": "말을 듣고 질문에 맞는 답을 골라요. 못 알아들으면 '다시', '천천히', '다른 말로'를 눌러 다시 들어요."},
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
    # 10/7 콘텐츠 검토(docs/review/listen-content-review-2026-10.md 4절): 방식 짝이 모음 ㅏ에만 있어 ㅜ 짝 둘(무·부, 누·두)을,
    # 마찰음 짝에 ㅜ·ㅓ 짝 둘(수·후, 서·저)을, 받침 짝에 ㄹ·ㄴ(달·단)과 같은 자리의 막음·콧소리(박·방)를 더했다.
    + [{"a": a, "b": b, "kind": "manner", "level": 3} for a, b in [
        ("마", "바"), ("나", "다"), ("라", "다"), ("나", "라"), ("사", "다"), ("무", "부"), ("누", "두")]]
    + [{"a": a, "b": b, "kind": "laryngeal", "level": 3} for a, b in [
        ("바", "파"), ("바", "빠"), ("다", "타"), ("다", "따"), ("가", "카"), ("가", "까"), ("자", "차"), ("자", "짜"),
        ("사", "싸")]]
    + [{"a": a, "b": b, "kind": "place", "level": 4} for a, b in [
        ("바", "다"), ("다", "가"), ("바", "가"), ("마", "나"), ("파", "타"), ("타", "카")]]
    + [{"a": a, "b": b, "kind": "fricative", "level": 4} for a, b in [
        ("사", "자"), ("사", "차"), ("사", "하"), ("시", "히"), ("수", "후"), ("서", "저")]]
    + [{"a": a, "b": b, "kind": "coda", "level": 4} for a, b in [
        ("각", "갑"), ("간", "감"), ("반", "방"), ("산", "상"), ("닥", "답"), ("밤", "반"), ("달", "단"), ("박", "방")]]
)
AX_KIND_LABEL = {"length": "길이", "intonation": "억양", "vowel": "모음", "manner": "자음 방식", "laryngeal": "소리 세기",
                 "place": "소리 자리", "fricative": "마찰음", "coda": "받침"}
_AX_TEXTS = {p["a"] for p in AX_PAIRS} | {p["b"] for p in AX_PAIRS}


# ── 목소리별 피할 문항(docs/listen-voice-contrast-2026-10.md) ──────────────────────────
# 미리 합성한 훈련 목소리(m1·f1·m2·f2) 가운데 어떤 글을 그 짝·보기와 구별되게 내지 못하는 목소리가 있다(예: 한 음절 예사소리가
# 거센소리처럼 들림). 판정자(kresnik CTC)로 측정한 실패를 data/listen_voice_avoid.json에 두고, 문항에 avoid_voices(피할 목소리 id,
# 정렬)를 붙인다. 화면(lib/listenMix.voiceFor)이 그 목소리를 건너뛰고 다음 목소리를 고른다(모두 걸리면 원래 목소리).
# 파일 꼴: {"voices": {목소리: {글: [{"against": 경쟁 글, "margin": …, "set": "ax"|"word", …}]}}, "test_voice_report": {…}}
# test_voice_report(검사 목소리 m3)는 피할 수 없어 보고만 하고 여기서 읽지 않는다. 파일이 없거나 깨졌으면 빈 목록(문항은 그대로).
VOICE_AVOID_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "listen_voice_avoid.json")
_VOICE_AVOID: Dict[str, object] = {"path": None, "data": {}}


def _avoid_key(text: str) -> str:
    from sound_clips import normalize_text
    return normalize_text(text)


def voice_avoid(path: Optional[str] = None) -> Dict[str, Dict[str, List[Dict]]]:
    """{목소리: {찾기 키: [{against(찾기 키), …}]}}. 경로가 같으면 한 번만 읽는다(LISTEN_VOICE_AVOID 환경변수로 바꿀 수 있다)."""
    p = path or os.getenv("LISTEN_VOICE_AVOID") or VOICE_AVOID_PATH
    if _VOICE_AVOID["path"] != p:
        data: Dict[str, Dict[str, List[Dict]]] = {}
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
            for v, texts in ((raw or {}).get("voices") or {}).items():
                if not isinstance(texts, dict):
                    continue
                d = data.setdefault(str(v), {})
                for t, ents in texts.items():
                    if isinstance(ents, list):
                        d[_avoid_key(t)] = [{**e, "against": _avoid_key(e.get("against", ""))} for e in ents if isinstance(e, dict)]
        except (OSError, ValueError, AttributeError, TypeError):
            data = {}
        _VOICE_AVOID.update(path=p, data=data)
    return _VOICE_AVOID["data"]  # type: ignore[return-value]


def avoid_voices_ax(a: str, b: str) -> List[str]:
    """소리 구별 짝 (a, b)에서 피할 목소리: a 클립이 b에 대해, 또는 b 클립이 a에 대해 구별되지 않은 목소리.
    같음 문항('a|a')도 그 짝에서 나왔으면 같은 목록을 쓴다(목소리를 바꿔 들려줄 때 다른 소리로 들리지 않게)."""
    ka, kb = _avoid_key(a), _avoid_key(b)
    out = []
    for v, d in voice_avoid().items():
        if any(e.get("against") == kb for e in d.get(ka, ())) or any(e.get("against") == ka for e in d.get(kb, ())):
            out.append(v)
    return sorted(out)


def avoid_voices_word(target: str) -> List[str]:
    """낱말 고르기에서 피할 목소리: 정답 글을 어느 경쟁 글과든 구별되게 내지 못한 목소리."""
    k = _avoid_key(target)
    return sorted(v for v, d in voice_avoid().items() if d.get(k))


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
                    "kind_label": AX_KIND_LABEL[p["kind"]], "level": level, "voice_pair": vp, "pick": pick,
                    "avoid_voices": avoid_voices_ax(p["a"], p["b"])})
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


@functools.lru_cache(maxsize=8192)
def _sound(word: str) -> Tuple[Tuple[str, str, str], ...]:
    """소리 나는 대로의 (첫소리, 모음, 받침) 음절열. 같은 낱말을 보기 고르기·이웃 표에서 수만 번 부르므로 기억해 둔다
    (예전에는 이웃 표 한 번에 약 0.7초, 일반화 검사 시작에 약 12초가 걸려 그동안 서버가 다른 요청을 받지 못했다)."""
    from scoring import to_pronounced_jamos
    return tuple(("" if i == "ㅇ" else i, m, f) for i, m, f in to_pronounced_jamos(word))


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


# 낱말 일반화 검사(청인 파일럿 2절, 훈련 풀에서 뺀다). 10/7 콘텐츠 검토에서 친숙한 구체어로 다시 골랐다(이전 목록의 사상·방지·작문·
# 보드 등은 드물거나 추상적이었다, docs/review/listen-content-review-2026-10.md 3.3절). 규칙:
#   후보 = 단어 은행에서 STAGE2_EXCLUDED·LISTEN_EXCLUDED·독화 표준검사 정답을 뺀 것 가운데, 국립국어원 학습용 어휘 A·B 등급 명사,
#          2음절 이하, 추상어·시간어와 뜻이 여럿인 한 음절(사랑·날·눈·배 등, 검토 문서에 목록)이 아님, 소리 구별 음절과 같지 않음,
#          훈련 문장·대화(대사·바꾼 말·질문·보기)·검사 문장에 글자로 들어 있지 않음, P3 파일럿 낱말이 아님
#   순서 = 후보를 가나다순으로 놓고 random.Random(20261007)로 섞은 순서
#   채택 = 앞에서부터 하나씩 넣되, 넣은 뒤 남은 훈련 풀에서 고른 낱말 모두가 소리 거리 3~6 이웃을 셋 이상 가질 때만 넣는다(20개까지)
GEN_WORDS = ['공항', '귀', '기자', '나물', '당근', '된장', '마늘', '몸', '무릎', '바늘', '아들', '양파', '어깨', '오빠', '의사', '이마', '이모',
             '컵', '포도', '호수']
# 일반화 검사 낱말 교체 후보((B′), docs/listen-gen-replace-2026-10.md 6.3절). GEN_WORDS를 바꿀지는 사람이 정하지만, 어느 쪽으로 정해도
# 검사 문장이 검사 낱말을 미리 들려주지 않도록 검사 문장 점검(gen_words_in)은 후보까지 본다(docs/listen-forms-clean-2026-10.md 2절).
GEN_REPLACE_CANDIDATES = ('손목', '경찰', '고기', '오이')


def gen_words_in(text: str) -> List[str]:
    """글에 글자로 들어 있는 일반화 검사 낱말(GEN_WORDS와 교체 후보). 낱말을 고를 때의 규칙('검사 문장에 글자로 들어 있지 않음')과
    같은 부분 문자열 비교라 '고기'는 '물고기'에도 걸린다(보수적으로 둔다)."""
    return [w for w in list(GEN_WORDS) + [w for w in GEN_REPLACE_CANDIDATES if w not in GEN_WORDS] if w in (text or "")]


# 낱말 고르기에서 쓰지 않는 말(10/7 콘텐츠 검토, docs/review/listen-content-review-2026-10.md 3절). 단어 은행(STAGE2_EXCLUDED를 뺀
# 400개)을 국립국어원 「한국어 학습용 어휘 목록」(2003, scripts/data/nikl_learner_vocab.tsv) 등급과 wordfreq 빈도(zipf)로 한 줄씩 봤다.
# 소리만 듣고 고르는 과제라 학습자가 모르는 말은 소리를 들어도 고를 수 없고, 보기로 나오면 어휘 지식만으로 지워진다. 독화 2단계는
# 이 말들을 그대로 쓴다(단어 은행·STAGE2_EXCLUDED는 바꾸지 않음).
LISTEN_EXCLUDED: Dict[str, str] = {
    # 규칙 1. 문법 기능이 주된 말: 의존 명사·관형사·부사로 더 많이 쓰여 홀로 들으면 낱말로 떠올리기 어렵다
    **{w: "의존 명사·관형사·부사로 주로 쓰임" for w in ("분", "만", "톤", "막", "도")},
    # 규칙 2. 뜻이 여럿이고 어느 하나가 두드러지지 않는 말. 홀로 들으면 무엇인지 정해지지 않는다
    **{w: "뜻이 여럿이라 홀로 들으면 정해지지 않음" for w in (
        "매", "판", "담", "남", "폭", "탈", "보도", "동부", "사리", "칩", "갓", "타자", "보드", "검", "낫", "자라", "복수")},
    # 규칙 3. 추상 명사로 학습용 어휘 A·B 등급이 아니고 빈도가 낮은 말(zipf 5.0 미만). A·B 등급인 사랑·행복·슬픔·겁·사물과
    # 빈도가 높은 답·맘은 남겼다
    **{w: "추상 명사(학습용 어휘 C 등급·목록 밖, zipf 5.0 미만)" for w in (
        "사상", "방지", "작문", "방치", "폭로", "선발", "반복", "공학", "가망", "가늠", "불통", "소란", "금식", "덕", "탓",
        "물체", "공포", "분노", "두려움", "무서움", "설렘", "부끄럼")},
    # 규칙 4. 학습용 어휘 목록에 없고 생활에서 드문 말(옛 생활·농사·전문 분야·격식어)
    **{w: "생활에서 드문 말(목록 밖, 옛 생활·전문 분야·격식어)" for w in (
        "다과", "호미", "도랑", "토기", "대양", "평원", "작물", "사비", "부두", "납", "짚", "도서", "포로", "보스")},
}


def word_pool(exclude: Optional[set] = None, include_gen: bool = False) -> List[str]:
    """낱말 고르기 풀: 단어 은행에서 드문 말(STAGE2_EXCLUDED)·듣기에서 쓰지 않는 말(LISTEN_EXCLUDED)·독화 표준검사 정답·일반화 검사
    낱말(GEN_WORDS)·exclude를 뺀 것. include_gen이면 일반화 검사 낱말을 남긴다(검사 문항의 보기를 만들 때)."""
    import curriculum as C
    skip = set(C.STAGE2_EXCLUDED) | set(LISTEN_EXCLUDED) | set(exclude or ()) | (set() if include_gen else set(GEN_WORDS))
    try:
        from assessment import test_only_words
        skip |= set(test_only_words())
    except Exception:
        pass
    return [w["word"] for w in C.WORD_BANK if w["word"] not in skip]


_NEIGHBOR_CACHE: Dict[Tuple[str, ...], Dict[str, List[Tuple[int, str]]]] = {}
# 풀 몇 개(훈련 풀, 일반화 검사 보기용 풀)를 함께 둔다. 예전에는 하나만 두어 두 풀을 번갈아 쓰면 매번 표를 새로 만들었다
_NEIGHBOR_CACHE_MAX = 4


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
        while len(_NEIGHBOR_CACHE) >= _NEIGHBOR_CACHE_MAX:
            _NEIGHBOR_CACHE.pop(next(iter(_NEIGHBOR_CACHE)))
        _NEIGHBOR_CACHE[key] = table
    return _NEIGHBOR_CACHE[key]


def word_item(target: str, level: int, pool: Sequence[str], seed: str,
              nb: Optional[Sequence[Tuple[int, str]]] = None) -> Optional[Dict]:
    """정답 target의 보기. 수준 범위에 맞는 이웃이 모자라면 가까운 순으로 채운다(수준 1은 음절 수가 다른 말도 쓴다).
    nb는 pool 안의 target 이웃 [(거리, 낱말)] 가까운 순(이미 있으면 넘겨 표를 다시 만들지 않는다)."""
    cfg = WORD_LEVELS[max(1, min(3, int(level)))]
    r = _rng(f"w:{seed}:{target}:{level}")
    nb = list(nb) if nb is not None else _neighbors(pool).get(target, [])
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
    return {"key": f"w:{target}", "target": target, "options": options, "level": int(level),
            "avoid_voices": avoid_voices_word(target)}


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

    # 이 수준의 정답 후보인 복습 낱말만 고른 뒤 3개를 자른다. 예전에는 먼저 3개를 자르고 후보인지 보았는데, due_reviews는 오래
    # 기다린 순이라 수준 1에서 틀린(수준 3 후보가 아닌) 낱말 3개가 앞을 영영 차지해 그 뒤 복습이 하나도 나오지 않았다
    for w in [w for w in dict.fromkeys(review) if w in cset][:3]:
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
    gen = set(GEN_WORDS)
    train = [w for w in pool_with_gen if w not in gen]
    # 보기 풀은 낱말마다 '훈련 풀 + 그 낱말'이다. 그 풀의 이웃은 '훈련 풀 + 검사 낱말 전부'의 이웃 표에서 검사 낱말을 뺀 것과 같으므로
    # 표를 한 번만 만든다(예전에는 낱말마다 새 표를 만들어 검사 시작에 약 12초, 문항은 그대로다: test_listen_curriculum이 해시로 고정)
    full = _neighbors(list(train) + [w for w in GEN_WORDS if w not in set(train)])
    out = []
    for i, w in enumerate(GEN_WORDS):
        nb = [(d, b) for d, b in full.get(w, []) if b not in gen]
        it = word_item(w, 2, list(train) + [w], "gen-20261007", nb=nb)
        if it:
            out.append({"key": f"g:{w}", "target": w, "options": it["options"], "n": i + 1})
    return out


# ── 3·4단계: 문장 ───────────────────────────────────────────────────
# 훈련 문장. 2~5어절의 생활 문장. 숫자는 한글로 적는다(합성·채점이 같은 글을 보게).

TRAIN_SENTENCES: List[str] = [
    "점심은 김밥이랑 떡볶이 어때요?", "창문 좀 열어 주세요.", "택시가 금방 올 거예요.",
    "저는 커피보다 차가 좋아요.", "주말에는 날씨가 춥대요.", "이 신발 얼마예요?",
    "엘리베이터는 오른쪽에 있어요.", "교통카드를 깜빡하고 안 가져왔어요.", "주말에 영화 보러 갈래요?",
    "손을 깨끗이 씻으세요.", "감기 때문에 목이 아파요.", "다음 역에서 내리면 돼요.",
    "우산 가져가는 게 좋겠어요.", "동생이 지금 학교에 있어요.", "이 길로 쭉 가세요.",
    "회의가 다음 주로 미뤄졌어요.", "냉장고에 우유가 없어요.", "사진 한 장 찍어 주실래요?",
    "아침에 늦잠을 잤어요.", "휴대폰 충전기 있어요?", "커피는 제가 살게요.",
    "강아지가 공원에서 뛰어놀아요.", "택배가 문 앞에 왔어요.", "잠깐만 기다려 주세요.",
    "금요일 저녁에 같이 밥 먹을래요?", "숙제를 아직 못 했어요.", "치과에 가려고 일찍 나왔어요.",
    "따뜻한 물 한 잔 주세요.", "삼촌 댁에서 하룻밤 잤어요.", "이 책 정말 재미있어요.",
    "계산은 카드로 할게요.", "문이 잠겨 있어요.", "합격 축하해요.", "퇴근 시간이라 차가 꽉 막혀요.",
    "표를 두 장 예매했어요.", "어젯밤에 잠을 거의 못 잤어요.", "김치찌개가 조금 매워요.",
    "시험이 다음 주예요.", "선풍기 좀 꺼 줄래요?", "친구랑 도서관에서 공부했어요.",
    "햇볕이 뜨거워서 초콜릿이 녹았어요.", "열 시까지 오시면 돼요.", "출구가 어느 쪽이에요?",
    "고양이가 소파 위에서 자요.", "이 옷 입어 봐도 돼요?", "오랜만에 운동을 했어요.",
    "바람이 세서 우산이 뒤집혔어요.", "사과 세 개만 주세요.", "조금 더 크게 말해 주세요.",
    "지하철이 버스보다 빨라요.", "어제 산 우유가 상했어요.", "컴퓨터가 갑자기 꺼졌어요.",
    "우리 같이 걸어갈까요?", "저녁에 전화할게요.", "허리가 계속 아파요.",
    "비행기 출발이 한 시간 늦어졌어요.", "벚꽃이 벌써 다 졌어요.", "음악 소리가 커서 대화하기 힘들어요.",
    "내일 시험이라 일찍 자야 해요.", "약은 식사 후에 드세요.", "짐이 많아서 택시를 탔어요.",
    "영수증 드릴까요?", "국이 식어서 다시 데웠어요.", "출입문이 닫힙니다.", "주차장은 지하에 있어요.",
    "여름 방학에 제주도에 가기로 했어요.", "안경을 새로 맞췄어요.", "주말 잘 보내세요.",
    "아직 밥을 안 먹었어요.", "이 자리 비어 있어요?", "공책 한 권 빌려줄래요?",
    "오늘 수업은 휴강이에요.", "빵이 아주 부드러워요.", "손님이 곧 오실 거예요.", "밤새 눈이 쌓였어요.",
    "이 근처에 약국 있어요?", "기차표를 잃어버렸어요.", "천천히 드세요.", "소나기가 금방 그쳤어요.",
    "수업이 몇 시에 끝나요?", "배가 너무 고파요.", "횡단보도에서는 뛰지 마세요.",
    "이 가수 목소리가 참 좋아요.", "짐 드는 거 도와드릴게요.", "어디서 내리세요?",
    "에어컨을 켜도 될까요?", "엄마가 반찬을 보내 주셨어요.", "내일 아침에 다시 올게요.",
    "줄이 꽤 길어요.", "여기에 서명해 주시겠어요?", "신발 끈 좀 묶고 갈게요.", "오늘 몇 월 며칠이에요?",
    "비밀번호가 틀렸다고 나와요.", "반찬이 조금 짜요.", "자전거 타고 출근해요.", "이 문은 당겨서 여세요.",
    "다들 벌써 도착했어요.", "수박이 아주 시원해요.", "아이가 열이 나요.", "이따가 다시 전화 주세요.",
    "할아버지께서 산책하러 나가셨어요.", "라면 끓여 줄까?", "깻잎은 씻어서 바구니에 담아 줘.",
    "트렁크에 짐을 싣고 출발했어요.", "쓰레기는 아침에 내놓으세요.", "팥빙수는 포장해 갈게요.",
    "아까 문자 보냈는데 확인했어요?", "축구 경기가 비 때문에 취소됐대요.", "숟가락 하나만 더 주실래요?",
    "편의점은 길 건너 바로 앞이에요.", "요즘 일이 너무 바빠요.", "엄마는 지금 통화 중이세요.",
    "어제 본 영화 진짜 웃겼어.", "걸어서 십 분이면 충분해요.", "손 씻고 와서 밥 먹자.",
    "콧물이 나고 목이 따끔해요.", "짜장면 곱빼기 하나요.", "택배 상자가 찌그러져서 왔어요.",
    "깜짝 놀랐어요.", "처음 뵙겠습니다.",
]


def sentence_id(i: int) -> str:
    return f"t{i + 1:03d}"


TRAIN_BY_ID: Dict[str, str] = {sentence_id(i): s for i, s in enumerate(TRAIN_SENTENCES)}

# 소음 속 문장 인식 역치(SRT) 검사 문장. 네 폼은 같은 꼴(같은 자리의 문장이 같은 구조·어절 수)로 짝을 맞췄다.
# 잡담 잡음(babble) 검사는 A·B, 훈련에 안 쓴 잡음(talker2) 검사는 C·D를 쓴다(TEST_FORM_PAIRS). 사전·사후 검사에서 두 잡음을
# 모두 하면 한 회기에 같은 문장을 두 번 듣지 않는다. 잡음마다 사전은 한 폼, 사후는 다른 폼이고 폼 순서는 학습자 id 홀짝으로
# 번갈아 정한다(test_form_for). C·D는 2026-10에 더했고 A·B와의 난이도 등가는 docs/listen-forms-cd-2026-10.md에 있다.
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
    "C": ["지갑 안에 카드가 있어요.", "아까는 불을 끄고 나갔어요.", "컵에 우유를 따라 주세요.", "우리 반은 스무 명이에요.",
          "아빠가 생선을 구웠어요.", "점심에 손님이 많이 와요.", "책을 이쪽으로 가져와 주세요.", "전철을 칠 분 기다렸어요.",
          "이모는 그림을 잘 그려요.", "운동화를 백화점에서 샀어요.", "마트 앞에서 자전거를 세워요.", "날이 추우니 따뜻하게 입으세요.",
          "주스를 조금만 마셨어요.", "사촌이 새 학교로 전학했어요.", "오후에 공부하러 가요.", "강아지가 이불 속에 숨었어요.",
          "할아버지는 바둑을 두세요.", "귤을 여섯 개 먹었어요.", "여름에는 모기가 많아요.", "겉옷을 옷장 안에 걸어요."],
    "D": ["가방 속에 휴지가 있어요.", "주말엔 늦잠을 자고 쉬었어요.", "벽에 달력을 붙여 주세요.", "우리 강아지는 세 살이에요.",
          "엄마가 국수를 삶았어요.", "새벽에 비가 많이 왔어요.", "쓰레기를 밖에 버려 주세요.", "공원까지 팔 분 걸려요.",
          "오빠는 글씨를 잘 써요.", "배드민턴을 마당에서 쳤어요.", "가게 앞에서 우산을 접어요.", "밤이 늦었으니 얼른 주무세요.",
          "용돈을 절반만 남겼어요.", "고모가 새 회사로 옮겼어요.", "일요일에 봉사하러 가요.", "동전이 소파 밑으로 굴러갔어요.",
          "할머니는 꽃을 기르세요.", "복숭아를 네 개 샀어요.", "봄에는 바람이 따뜻해요.", "접시를 쟁반 위에 올려요."],
}
# 잡음마다 쓰는 폼 짝(앞이 짝수 id의 첫 폼). talker2의 C·D는 검사 목소리 소리가 모두 있을 때만 쓴다(heldout_forms_ready).
TEST_FORM_PAIRS: Dict[str, Tuple[str, str]] = {"babble": ("A", "B"), "talker2": ("C", "D")}


def test_form_for(user_id: int, n_done: int, noise: str = "babble", heldout_ready: bool = True) -> str:
    """학습자가 잡음 noise로 하는 n_done번째(0부터) 검사의 폼. n_done은 그 잡음의 회차만 센다.
    babble: 짝수 id는 A → B → A …, 홀수 id는 B → A → B …. talker2: 짝수 id는 C → D …, 홀수 id는 D → C ….
    heldout_ready가 거짓이면(C·D 검사 목소리 소리가 아직 없음) talker2는 같은 회차의 babble 폼과 반대 폼(A·B 가운데)을 쓴다.
    그래도 한 회기의 두 검사는 서로 다른 문장이다."""
    pair = TEST_FORM_PAIRS.get(noise, TEST_FORM_PAIRS["babble"])
    if noise != "babble" and not heldout_ready:
        a, b = TEST_FORM_PAIRS["babble"]
        return b if test_form_for(user_id, n_done) == a else a
    first, other = pair if int(user_id) % 2 == 0 else pair[::-1]
    return first if n_done % 2 == 0 else other


def heldout_forms_ready(has_clip) -> bool:
    """talker2 폼(C·D) 문장이 모두 검사 목소리 소리를 가졌는가. has_clip(글) → bool(서버 음성 목록 조회)."""
    return all(has_clip(s) for f in TEST_FORM_PAIRS["talker2"] for s in TEST_FORMS[f])


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


# 검사 계단(Plomp·Mimpen 1979 방식을 낱말 기준으로): 20문장, +10 dB 시작, 역치 = 5~20번째 문장 SNR과 (21번째로 냈을) 다음 SNR의 평균.
# 10/7부터 검사 앞에 연습 문장 5개(훈련 문장, 역치에 넣지 않음)를 4 dB 걸음으로 내고, 그 마지막 다음 SNR에서 검사 문장을 처음부터 2 dB 걸음으로
# 낸다. 시작점이 역치에 가까워져 재검사 SD가 5~10% 줄고 편향·천장 막힘은 그대로였으며(가상 청취자 확인 시드, docs/listen-mastery-sim-2026-10.md
# 7.4·8절), 첫 리스트의 연습 효과(1~2 dB, Jansen 2012)를 검사 밖으로 빼는 몫은 문헌 근거다. 연습 없이 시작한 회차(이전 기록)는 처음 4문장
# 4 dB의 옛 규칙으로 계산한다(n_practice = 0).
TEST_STAIR = {"start": 10.0, "big": 4.0, "small": 2.0, "big_trials": 4, "lo": -10.0, "hi": 25.0, "criterion": 0.5,
              "practice": 5, "n_test": 20}

# 10/9부터 새로 시작한 회차(id가 TEST_HALF_PREFIX로 시작)는 문장 낱말 비율이 정확히 0.5면 SNR을 그대로 둔다('절반 규칙', 연습·검사 모두).
# 옛 규칙은 4어절 문장의 '두 개 맞음'을 맞음으로 세어 낱말 약 40% 지점으로 모였다(편향 −0.75 dB, 인공와우 −1 dB). 절반 규칙은 맞음과
# 틀림이 같은 확률이 되는 낱말 50% 지점으로 모이고, 가상 청취자 확인 시드에서 편향 ±0.04 dB, 재검사 SD 3~14% 감소, 막힘 +0.5%p 안이었다
# (docs/listen-stair-target-sim-2026-10.md Tt). 이미 있는 회차는 옛 규칙으로 계산해 기록이 바뀌지 않는다.
TEST_HALF_PREFIX = "test:v2-"


def test_rule(session: Optional[str]) -> str:
    """회차의 계단 규칙: 'half'(절반 규칙, 10/9부터) 또는 'forty'(옛 규칙)."""
    return "half" if (session or "").startswith(TEST_HALF_PREFIX) else "forty"


def test_trial_ok(score: Optional[float], correct: Optional[bool], rule: str) -> Optional[bool]:
    """한 문장의 계단 판정. 옛 규칙은 저장된 맞음(비율 ≥ 0.5). 절반 규칙은 비율 > 0.5면 맞음, < 0.5면 틀림, 정확히 0.5면 None(그대로)."""
    if rule != "half" or score is None:
        return bool(correct)
    if abs(float(score) - 0.5) < 1e-9:
        return None
    return float(score) > 0.5


def test_practice_items(seed: str, n: Optional[int] = None) -> List[Dict]:
    """검사 앞 연습 문장(훈련 문장에서, 회차 seed로 고름). 키는 'testp:<훈련 문장 id>'."""
    n = TEST_STAIR["practice"] if n is None else n
    return [{"key": f"testp:{it['id']}", "id": it["id"], "text": it["text"], "practice": True}
            for it in sentence_items(f"tp:{seed}", n=n)]


def test_next_snr(trials: Sequence[Tuple[float, bool]], cfg: Dict = TEST_STAIR, n_practice: int = 0) -> float:
    """trials: 회차의 (SNR, 맞음) 시간순. 맞음이 None이면(절반 규칙의 정확히 절반) SNR을 그대로 둔다. 앞의 n_practice개가 연습 문장이다. 연습은 4 dB, 검사 문장은 2 dB.
    n_practice가 0이면 옛 규칙(처음 big_trials문장 4 dB)."""
    snr = float(cfg["start"])
    for k, (s, ok) in enumerate(trials):
        if n_practice:
            step = cfg["big"] if k < n_practice else cfg["small"]
        else:
            step = cfg["big"] if k < cfg["big_trials"] else cfg["small"]
        if ok is None:   # 절반 규칙에서 정확히 절반: 그대로
            snr = float(s)
            continue
        snr = min(cfg["hi"], max(cfg["lo"], float(s) + (-step if ok else step)))
    return round(snr, 1)


def test_srt(trials: Sequence[Tuple[float, bool]], cfg: Dict = TEST_STAIR, n_practice: int = 0) -> Optional[float]:
    """검사 역치. 연습 뒤 검사 문장 20개를 다 들어야 낸다."""
    test = list(trials)[n_practice:]
    if len(test) < cfg["n_test"]:
        return None
    xs = [float(s) for s, _ in test[4:cfg["n_test"]]] + [test_next_snr(list(trials)[:n_practice + cfg["n_test"]], cfg, n_practice)]
    return round(sum(xs) / len(xs), 1)


# ── 5단계: 대화 듣기 ─────────────────────────────────────────────────
# 생활 장면의 한 마디(line)와 쉬운 말로 바꾼 말(paraphrase, '다른 말로' 되묻기), 내용 질문과 4지 보기.

CONVO_ITEMS: List[Dict] = [
    {"id": "c01", "place": "병원", "line": "점심시간이라 진료는 두 시 반부터 다시 해요.",
     "paraphrase": "지금은 점심시간이에요. 두 시 반에 다시 진료해요.",
     "question": "진료는 몇 시에 다시 시작해요?", "options": ["두 시 반", "한 시 반", "두 시", "세 시 반"], "answer": 0},
    {"id": "c02", "place": "약국", "line": "이 약은 하루 세 번, 식사하기 삼십 분 전에 드세요.",
     "paraphrase": "밥 먹기 삼십 분 전에 드세요. 하루에 세 번이에요.",
     "question": "약은 언제 먹어요?", "options": ["밥 먹은 뒤", "밥 먹기 전", "밥 먹는 중", "잠자기 전"], "answer": 1},
    {"id": "c03", "place": "카페", "line": "따뜻한 라테는 지금 안 되고, 차가운 것만 돼요.",
     "paraphrase": "라테는 차가운 것만 주문할 수 있어요.",
     "question": "어떤 라테를 주문할 수 있어요?", "options": ["차가운 라테", "따뜻한 라테", "둘 다 돼요", "둘 다 안 돼요"], "answer": 0},
    {"id": "c04", "place": "버스 안내", "line": "이번 정류장은 시청, 다음 정류장은 서울역입니다.",
     "paraphrase": "지금은 시청이고, 다음은 서울역이에요.",
     "question": "다음 정류장은 어디예요?", "options": ["시청", "서울역", "종로", "광화문"], "answer": 1},
    {"id": "c05", "place": "식당", "line": "자리가 없어서 이십 분 정도 기다리셔야 해요.",
     "paraphrase": "빈자리가 없어요. 이십 분쯤 있어야 앉을 수 있어요.",
     "question": "얼마나 기다려야 해요?", "options": ["이 분", "십 분", "이십 분", "한 시간"], "answer": 2},
    {"id": "c06", "place": "은행", "line": "번호표 기계가 고장 났어요. 여기에 이름을 적고 앉아 계세요.",
     "paraphrase": "번호표가 안 나와요. 종이에 이름을 쓰고 앉으세요.",
     "question": "먼저 무엇을 해야 해요?", "options": ["번호표 뽑기", "이름 적기", "창구로 가기", "기계 고치기"], "answer": 1},
    {"id": "c07", "place": "아파트", "line": "택배는 경비실에 맡겨 두었습니다.",
     "paraphrase": "택배는 경비실에 있어요.",
     "question": "택배는 어디에 있어요?", "options": ["문 앞", "편의점", "우체국", "경비실"], "answer": 3},
    {"id": "c08", "place": "학교", "line": "내일은 체육 대신 미술을 하니까 물감을 챙겨 오세요.",
     "paraphrase": "내일은 미술 시간이 있어요. 물감을 가져오세요.",
     "question": "내일 무엇을 챙겨 가요?", "options": ["물감", "체육복", "도시락", "실내화"], "answer": 0},
    {"id": "c09", "place": "회사", "line": "회의실이 바뀌어서 삼 층 큰 방에서 해요.",
     "paraphrase": "회의는 삼 층 큰 방에서 해요. 장소가 바뀌었어요.",
     "question": "회의는 어디서 해요?", "options": ["이 층 작은 방", "삼 층 작은 방", "삼 층 큰 방", "사 층 큰 방"], "answer": 2},
    {"id": "c10", "place": "마트", "line": "우유는 하나 사면 하나 더 드려요.",
     "paraphrase": "우유 하나를 사면 하나를 공짜로 줘요.",
     "question": "우유를 하나 사면 어떻게 돼요?", "options": ["반값이에요", "할인이 없어요", "두 개 더 줘요", "하나 더 줘요"], "answer": 3},
    {"id": "c11", "place": "전화", "line": "지금 통화가 어려우니 문자로 남겨 주세요.",
     "paraphrase": "지금은 통화하기 힘들어요. 문자를 남겨 주세요.",
     "question": "어떻게 연락해야 해요?", "options": ["다시 전화하기", "문자 보내기", "메일 보내기", "직접 찾아가기"], "answer": 1},
    {"id": "c12", "place": "지하철", "line": "이 열차는 이번 역까지만 운행합니다. 모두 내려 주세요.",
     "paraphrase": "열차가 여기서 끝나요. 다 내리세요.",
     "question": "무엇을 해야 해요?", "options": ["계속 타고 있기", "다음 역에서 내리기", "앞 칸으로 옮기기", "이번 역에서 내리기"], "answer": 3},
    {"id": "c13", "place": "일기 예보", "line": "오후부터 비가 오다가 저녁에는 그친대요.",
     "paraphrase": "비는 오후에 오고 저녁에 멈춘대요.",
     "question": "비는 언제 그쳐요?", "options": ["오후", "저녁", "밤늦게", "내일 아침"], "answer": 1},
    {"id": "c14", "place": "미용실", "line": "커트는 만 오천 원이고, 파마는 오만 원이에요.",
     "paraphrase": "머리 자르는 건 만 오천 원이에요.",
     "question": "커트는 얼마예요?", "options": ["오천 원", "만 오천 원", "오만 원", "만 오백 원"], "answer": 1},
    {"id": "c15", "place": "친구", "line": "토요일은 안 되고 일요일 오후에 만나자.",
     "paraphrase": "일요일 오후에 보자. 토요일은 바빠.",
     "question": "언제 만나요?", "options": ["토요일 오전", "토요일 오후", "일요일 오전", "일요일 오후"], "answer": 3},
    {"id": "c16", "place": "병원 접수", "line": "처음 오셨으면 이 종이에 이름과 생년월일을 써 주세요.",
     "paraphrase": "처음이면 여기에 이름이랑 태어난 날을 적어 주세요.",
     "question": "종이에 무엇을 써요?", "options": ["이름과 생년월일", "이름과 전화번호", "주소와 생년월일", "주소와 전화번호"], "answer": 0},
    {"id": "c17", "place": "기차역", "line": "부산행 기차는 칠 번 타는 곳에서 출발합니다.",
     "paraphrase": "부산 가는 기차는 칠 번에서 타세요.",
     "question": "부산 가는 기차는 몇 번에서 타요?", "options": ["일 번", "사 번", "팔 번", "칠 번"], "answer": 3},
    {"id": "c18", "place": "도서관", "line": "책은 이 주 동안 빌릴 수 있어요.",
     "paraphrase": "빌린 책은 이 주 안에 돌려주세요.",
     "question": "책은 얼마 동안 빌릴 수 있어요?", "options": ["일주일", "한 달", "이 주", "사흘"], "answer": 2},
    {"id": "c19", "place": "가게", "line": "카드는 안 되고 현금만 받아요.",
     "paraphrase": "현금으로만 계산할 수 있어요.",
     "question": "어떻게 계산해요?", "options": ["카드", "휴대폰", "현금", "상품권"], "answer": 2},
    {"id": "c20", "place": "건물 안내", "line": "엘리베이터 점검 중이니 계단을 이용해 주세요.",
     "paraphrase": "엘리베이터를 고치고 있어요. 계단으로 가세요.",
     "question": "어떻게 올라가요?", "options": ["계단으로", "엘리베이터로", "에스컬레이터로", "옆 건물로"], "answer": 0},
    {"id": "c21", "place": "식당 주문", "line": "비빔밥은 다 떨어졌고 김치찌개는 돼요.",
     "paraphrase": "비빔밥은 없어요. 김치찌개는 있어요.",
     "question": "무엇을 주문할 수 있어요?", "options": ["김치찌개", "비빔밥", "둘 다", "둘 다 안 돼요"], "answer": 0},
    {"id": "c22", "place": "약속", "line": "버스를 놓쳐서 조금 늦을 것 같아요.",
     "paraphrase": "버스를 못 탔어요. 좀 늦게 가요.",
     "question": "왜 늦어요?", "options": ["늦잠을 자서", "지하철을 잘못 타서", "버스를 놓쳐서", "길이 막혀서"], "answer": 2},
    {"id": "c23", "place": "안내 방송", "line": "매장은 삼십 분 뒤에 문을 닫습니다.",
     "paraphrase": "가게가 곧 닫아요. 삼십 분 남았어요.",
     "question": "가게는 언제 문을 닫아요?", "options": ["십 분 뒤", "사십 분 뒤", "삼십 분 뒤", "한 시간 뒤"], "answer": 2},
    {"id": "c24", "place": "집", "line": "반찬은 식탁 위에 있으니까 데워 먹어.",
     "paraphrase": "반찬은 식탁에 있어. 따뜻하게 해서 먹어.",
     "question": "반찬은 어디에 있어요?", "options": ["냉장고", "전자레인지", "찬장", "식탁 위"], "answer": 3},
    {"id": "c25", "place": "수업", "line": "숙제는 금요일까지 메일로 보내세요.",
     "paraphrase": "숙제는 금요일 안에 메일로 내세요.",
     "question": "숙제는 언제까지 내요?", "options": ["월요일", "금요일", "수요일", "일요일"], "answer": 1},
    {"id": "c26", "place": "택시", "line": "여기서 내려 드릴까요, 건물 앞까지 갈까요?",
     "paraphrase": "지금 내릴래요, 아니면 건물 앞에서 내릴래요?",
     "question": "기사님이 무엇을 물어요?", "options": ["요금", "내릴 곳", "가는 길", "계산 방법"], "answer": 1},
    {"id": "c27", "place": "병원", "line": "검사 결과는 다음 주 화요일에 나와요.",
     "paraphrase": "결과는 다음 주 화요일에 알 수 있어요.",
     "question": "결과는 언제 나와요?", "options": ["이번 주 화요일", "다음 주 목요일", "다음 주 화요일", "다음 달"], "answer": 2},
    {"id": "c28", "place": "카페", "line": "주문하신 음료는 진동벨이 울리면 가져가세요.",
     "paraphrase": "벨이 울리면 음료를 받으러 오세요.",
     "question": "언제 음료를 가지러 가요?", "options": ["벨이 울리면", "바로", "이름을 부르면", "번호를 부르면"], "answer": 0},
    {"id": "c29", "place": "우체국", "line": "등기는 내일 도착하고, 일반 우편은 사흘 걸려요.",
     "paraphrase": "등기는 내일 가요. 보통 우편은 사흘 걸려요.",
     "question": "등기는 언제 도착해요?", "options": ["내일", "오늘", "사흘 뒤", "일주일 뒤"], "answer": 0},
    {"id": "c30", "place": "관리실 안내", "line": "내일 아침 아홉 시부터 물이 안 나온대요.",
     "paraphrase": "내일 아침 아홉 시에 물이 끊긴대요.",
     "question": "내일 아침에 무엇을 못 써요?", "options": ["전기", "가스", "인터넷", "물"], "answer": 3},
    # 10/7 연습 모드(상황별 대화 듣기)에서 장면 묶음마다 4문항 이상이 되게 더한 넷(docs/listen-integration-api-2026-10.md 6절).
    # 콘텐츠 검토(docs/review/listen-content-review-2026-10.md 5절)의 (가)~(바)를 따랐다. 들은 말 안에 소리가 비슷한 오답이 있다
    # (일곱 시·여섯 시 오십 분, 수요일·금요일, 오 층·이 층, 열 시·열두 시·열한 시).
    {"id": "c31", "place": "친구", "line": "영화는 일곱 시에 시작하니까 여섯 시 오십 분까지 극장 앞으로 와.",
     "paraphrase": "여섯 시 오십 분까지 극장 앞에 와. 영화는 일곱 시야.",
     "question": "몇 시까지 와야 해요?", "options": ["여섯 시", "일곱 시", "여섯 시 오십 분", "일곱 시 오십 분"], "answer": 2},
    {"id": "c32", "place": "회사", "line": "출장은 수요일에 가고, 금요일 아침에 돌아와요.",
     "paraphrase": "수요일에 출장을 가요. 금요일 아침에 와요.",
     "question": "언제 돌아와요?", "options": ["수요일 아침", "목요일 저녁", "금요일 저녁", "금요일 아침"], "answer": 3},
    {"id": "c33", "place": "도서관 안내", "line": "오 층 열람실은 공사 중이라 이 층 열람실만 쓸 수 있습니다.",
     "paraphrase": "오 층 열람실은 고치는 중이에요. 이 층 열람실로 가세요.",
     "question": "어느 열람실을 쓸 수 있어요?", "options": ["오 층 열람실", "일 층 열람실", "이 층 열람실", "사 층 열람실"], "answer": 2},
    {"id": "c34", "place": "아파트", "line": "내일 승강기 검사가 있어서 열 시부터 열두 시까지 못 타요.",
     "paraphrase": "내일 열 시부터 열두 시까지는 승강기를 쓸 수 없어요.",
     "question": "승강기는 언제부터 못 타요?", "options": ["아홉 시부터", "열한 시부터", "열두 시부터", "열 시부터"], "answer": 3},
]
CONVO_BY_ID = {c["id"]: c for c in CONVO_ITEMS}

# 상황별 대화 듣기(연습 모드 scenario)의 장면 묶음. 장소 이름(place)은 문항마다 달라 한 장소에 한 문항뿐인 곳이 많아서, 비슷한
# 장소를 묶어 묶음마다 4문항 이상이 되게 했다. 모든 장소는 정확히 한 묶음에 든다(test_listen_practice가 확인).
SCENES: List[Dict] = [
    {"key": "clinic", "label": "병원·약국", "places": ("병원", "약국", "병원 접수")},
    {"key": "food", "label": "식당·카페", "places": ("카페", "식당", "식당 주문")},
    {"key": "transit", "label": "교통", "places": ("버스 안내", "지하철", "기차역", "택시")},
    {"key": "shop", "label": "가게·은행·우체국", "places": ("은행", "마트", "미용실", "가게", "우체국")},
    {"key": "home", "label": "집·동네", "places": ("아파트", "집", "관리실 안내")},
    {"key": "work", "label": "학교·회사·도서관", "places": ("학교", "회사", "수업", "도서관")},
    {"key": "notice", "label": "안내 방송", "places": ("일기 예보", "건물 안내", "안내 방송", "도서관 안내")},
    {"key": "friends", "label": "친구·전화", "places": ("전화", "친구", "약속")},
]
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

def _has_final(word: str) -> bool:
    """마지막 글자를 읽을 때 받침이 있는가(조사 고르기). 완성형은 종성으로, 자음 자모(ㄱ 기역 … ㅎ 히읗)는 이름이 모두 받침으로 끝나
    있음, 모음 자모(ㅏ 아 …)는 없음."""
    if not word:
        return False
    ch = word[-1]
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3:
        return (o - 0xAC00) % 28 != 0
    return 0x3131 <= o <= 0x314E


def _josa(word: str, with_final: str, without_final: str) -> str:
    return word + (with_final if _has_final(word) else without_final)


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
                        "text": f"모음 {_josa(t, '과', '와')} {_josa(h, '을', '를')} 자주 헷갈려요." + (" 입모양은 달라서 입을 함께 보면 도움이 돼요." if lip
                                                                  else " 입모양도 비슷해서 소리 구별 연습이 필요해요."),
                        "routes": [{"label": "입모양 레슨" if lip else "소리 구별", "to": "/learn/viseme" if lip else "/learn/listening?stage=1"}]})
            continue
        vt = VISEME_MAP.get(t) if t not in ("-", "ㅇ") else None
        vh = VISEME_MAP.get(h) if h not in ("-", "ㅇ") else None
        lip = vt is not None and vh is not None and vt != vh
        where = "받침" if c.get("slot") == "coda" else "첫소리"
        # '-'는 받침 없음(contrast_of). 한쪽이 없음이면 둘 다 '받침 …'으로 적고("받침 ㄴ과 받침 없음을"), 조사는 앞 글자 받침에 맞춘다.
        # 예전에는 "받침 -와 ㄴ를"처럼 기호와 고정 조사가 그대로 나왔다
        if "-" in (t, h):
            a, b = (f"{where} {'없음' if x == '-' else x}" for x in (t, h))
        else:
            a, b = f"{where} {t}", h
        pair = f"{_josa(a, '과', '와')} {_josa(b, '을', '를')}"
        text = (f"{pair} 자주 헷갈려요. 입모양은 달라서 입을 함께 보면 구별할 수 있어요." if lip
                else f"{pair} 자주 헷갈려요. 입모양이 같거나 잘 안 보여서 소리로 가려야 해요.")
        routes = [{"label": "입모양 레슨", "to": "/learn/viseme"}] if lip else [{"label": "소리 구별", "to": "/learn/listening?stage=1"}]
        routes.append({"label": "말하기 자음", "to": "/learn/speaking?stage=3"})
        out.append({"pair": [t, h], "slot": c.get("slot"), "lip_differs": lip, "text": text, "routes": routes})
    return out


# 하루 연습 시간 추정(결과 화면의 7일 연습량을 권장 '하루 15~20분'과 비교하려고). 시행 기록의 시각 사이 간격을 더하되, 간격이
# IDLE_GAP_S를 넘으면 쉰 것으로 보고 넣지 않는다(학습 기록의 과제 시간 추정에서 흔히 쓰는 '쉼 끊기', Kovanović 2015는 끊는 값에 따라
# 추정이 크게 달라짐을 보였다). 소리 듣기 한 문항은 듣기·답 쓰기를 합쳐 보통 1분 안이고 다시 듣기와 단서 보고 고쳐 쓰기를 해도
# 3분을 넘기 드물어 3분으로 둔다. 쉰 뒤 처음 시행(그 앞 간격을 모르는 것)은 화면이 보낸 반응 시간(rt_ms, 문항을 띄운 때부터 답할
# 때까지)을 같은 상한으로 넣는다. 반응 시간이 없는 기록(소리 확인·검사 문장)은 그 시행 몫을 0으로 본다(덜 세는 쪽).
IDLE_GAP_S = 180


def practice_minutes(events: Sequence[Tuple["object", Optional[int]]], idle_gap_s: int = IDLE_GAP_S) -> float:
    """[(시각 datetime, rt_ms 또는 None)] 하루치 → 연습 분(소수 첫째 자리). 시각순이 아니어도 된다."""
    # 같은 시각이면 rt_ms가 있는 것을 앞에 둔다(들어온 순서와 상관없이 같은 값). 예전에는 (시각, rt_ms) 짝 그대로 정렬해, 같은 시각에
    # rt_ms가 없는 시행(소리 확인·검사)과 있는 시행이 겹치면 None과 int를 비교해 TypeError(요약·과제·분석·내보내기가 500)였다
    evs = sorted(((t, rt) for t, rt in events if t is not None), key=lambda e: (e[0], e[1] is None, e[1] or 0))
    total = 0.0
    prev = None
    for t, rt in evs:
        gap = (t - prev).total_seconds() if prev is not None else None
        if gap is not None and gap <= idle_gap_s:
            total += max(0.0, gap)
        elif rt:
            total += min(float(rt) / 1000.0, idle_gap_s)
        prev = t
    return round(total / 60.0, 1)


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

# ── 오늘의 듣기(하루 묶음 회기, 고도화 방안 P4) ──────────────────────────────
# 권장 용량은 하루 15~20분, 주 5일이고 결과를 좌우하는 것은 꾸준히 하는 비율이다(docs/auditory-training-evidence-2026-10.md 4절).
# 단계마다 따로 들어가는 대신 한 회기에 약한 대조 표적 문항, 문장(소음 속 또는 조용함), 대화를 정해진 비율로 섞는다.
# 블록마다 대략의 분(문항당 초 × 문항 수)을 붙여 15분 안팎이 되게 한다. 순수 함수: 단계 상태만 받는다.
TODAY_SECONDS = {"ling": 70, "ax": 12, "word_id": 15, "sentence": 40, "noise": 40, "convo": 45}


def today_plan(status: Dict[int, str], ling_done_today: bool, target_min: float = 15.0) -> List[Dict]:
    """status: {단계: 'locked'|'unlocked'|'in_progress'|'mastered'}. 반환: [{stage, mode, n, minutes, why}] 순서대로.
    0) 오늘 Ling 점검을 안 했으면 먼저(기기 점검), 1) 수준 단계(1·2) 중 아직 숙달 전인 앞 단계, 둘 다 숙달이면 2단계 유지 연습,
    2) 문장: 4단계가 열렸으면 소음 속, 아니면 3단계가 열렸으면 조용한 문장, 3) 5단계가 열렸으면 대화. 남는 시간은 문장 블록에 더한다."""
    open_ = lambda n: status.get(n, "locked") != "locked"
    plan: List[Dict] = []
    if not ling_done_today:
        plan.append({"stage": 0, "mode": "ling", "n": 8, "why": "오늘 기기 점검"})
    lev = next((n for n in (1, 2) if open_(n) and status.get(n) != "mastered"), None)
    if lev is None and open_(2):
        lev = 2
    if lev is not None:
        mode = "ax" if lev == 1 else "word_id"
        plan.append({"stage": lev, "mode": mode, "n": 12 if lev == 1 else 10, "why": "약한 소리 짝"})
    sent = 4 if open_(4) else 3 if open_(3) else None
    if sent is not None:
        plan.append({"stage": sent, "mode": "noise" if sent == 4 else "sentence", "n": 8, "why": "소음 속 문장" if sent == 4 else "문장"})
    if open_(5):
        plan.append({"stage": 5, "mode": "convo", "n": 4, "why": "대화 듣기"})
    for b in plan:
        b["minutes"] = round(b["n"] * TODAY_SECONDS[b["mode"]] / 60 if b["mode"] != "ling" else TODAY_SECONDS["ling"] / 60, 1)
    total = sum(b["minutes"] for b in plan)
    # 남는 시간은 문장 블록(없으면 수준 블록)에 문항을 더해 채운다(최대 2배)
    fill = next((b for b in plan if b["mode"] in ("noise", "sentence")), None) or next((b for b in plan if b["mode"] in ("ax", "word_id")), None)
    if fill and total < target_min:
        per = TODAY_SECONDS[fill["mode"]] / 60
        extra = min(fill["n"], int((target_min - total) / per))
        fill["n"] += extra
        fill["minutes"] = round(fill["n"] * per, 1)
    return plan


# ── 연습 모드(연습 탭의 소리 듣기, docs/listen-integration-api-2026-10.md) ─────────────────────
# 학습 경로 단계와 따로, 연습 탭에서 고르는 듣기 연습. 답은 단계 숙달·수준·4단계 소음 계단에 넣지 않고(시행 session
# 'practice:<모드>'), 혼동 집계·간격 복습·연습량에는 넣는다. 여기에는 문항을 만드는 순수 함수만 둔다(기록 규칙은 main.py).

PRACTICE_MODES: List[Dict] = [
    {"key": "contrast", "title": "소리 짝 집중 연습",
     "desc": "헷갈리는 소리 짝 하나를 골라 같은지 다른지 듣고, 그 소리로 갈리는 낱말을 골라요."},
    {"key": "dictation", "title": "문장 받아쓰기",
     "desc": "조용한 곳에서 문장을 듣고 들은 대로 써요. 끝없이 이어서 할 수 있어요."},
    {"key": "noise_endless", "title": "소음 속 문장 이어 듣기",
     "desc": "떠드는 소리 속에서 문장을 들어요. 맞히면 소음이 커지고 놓치면 작아져요. 학습 경로의 소음 단계와 따로 맞춰요."},
    {"key": "scenario", "title": "상황별 대화 듣기",
     "desc": "병원, 가게, 교통처럼 장면을 골라 그곳에서 듣는 말을 듣고 내용을 골라요."},
    {"key": "conditions", "title": "듣기 조건 고르기",
     "desc": "전화 소리, 울리는 방, 여러 가지 소음 가운데 골라 그 조건에서 문장을 들어요."},
]
PRACTICE_KEYS = tuple(m["key"] for m in PRACTICE_MODES)
# 시행 기록의 session. 'practice'(정답 단서를 본 뒤 다시 쓴 답, 잠긴 단계의 답)와 섞이지 않게 콜론 뒤에 모드를 붙인다.
# 'review'는 복습 탭의 듣기 복습(GET /api/listen/review)의 답이다.
PRACTICE_SESSION_PREFIX = "practice:"
PRACTICE_SESSION_MODES = PRACTICE_KEYS + ("review",)
# 연습 모드 소음 계단의 조건 이름. 4단계 계단(ao·av)과 따로 센다
PRACTICE_STAIR_CONDITION = "practice_ao"
PRACTICE_CONDS = ("phone", "room", "noise")


def practice_session(mode: str) -> str:
    return PRACTICE_SESSION_PREFIX + mode


def is_practice_session(session: Optional[str]) -> bool:
    return bool(session) and session.startswith(PRACTICE_SESSION_PREFIX)


# 소리 짝(대조) 이름: 'onset:ㅂ:ㅍ', 'vowel:ㅓ:ㅗ', 'coda:ㄴ:ㅁ'(받침 없음은 '-'), 'kind:fricative'(소리 구별 종류).
_SLOT_LABEL = {"onset": "첫소리", "vowel": "모음", "coda": "받침"}
_VOWELS = set(_V_BASE) | set(_V_GLIDE)
_ONSETS = {k for k in _C_FEAT if k} | {"ㅇ"}
_CODAS = {v for v in _CODA_REP.values() if v} | {"-"}
# 마찰음·파찰음(높은 주파수 바람 소리)
_FRIC = {"ㅅ", "ㅆ", "ㅈ", "ㅉ", "ㅊ", "ㅎ"}


def parse_contrast(spec: Optional[str]) -> Optional[Dict]:
    """대조 이름 → {key, type: 'slot'|'kind', slot?, a?, b?, kind?, label}. 모르는 이름이면 None."""
    if not spec or not isinstance(spec, str):
        return None
    parts = spec.strip().split(":")
    if len(parts) == 2 and parts[0] == "kind" and parts[1] in AX_KIND_LABEL:
        k = parts[1]
        return {"key": f"kind:{k}", "type": "kind", "kind": k, "label": AX_KIND_LABEL[k]}
    if len(parts) != 3 or parts[0] not in _SLOT_LABEL:
        return None
    slot, a, b = parts
    allowed = {"onset": _ONSETS, "vowel": _VOWELS, "coda": _CODAS}[slot]
    if a == b or a not in allowed or b not in allowed:
        return None
    if slot == "vowel" and not vowel_distance(a, b):
        return None   # ㅐ·ㅔ처럼 같은 소리

    def show(x):
        if x == "-":
            return "없음"
        return "소리 없음" if slot == "onset" and x == "ㅇ" else x
    return {"key": f"{slot}:{a}:{b}", "type": "slot", "slot": slot, "a": a, "b": b,
            "label": f"{_SLOT_LABEL[slot]} {show(a)}·{show(b)}"}


def contrast_kind(c: Dict) -> Optional[str]:
    """낱말 두 개 사이의 대조 하나({slot, target, heard}) → 소리 구별 종류(AX_KIND_LABEL의 키) 또는 None(섞인 대조).
    받침 → coda, 모음 → vowel. 첫소리는 세기만 다르면 laryngeal, 마찰음·파찰음이 끼고 자리가 다르면 fricative,
    방식만 다르면 manner, 자리만 다르면 place(소리 구별 짝 AX_PAIRS의 종류 나눔과 같다)."""
    slot = c.get("slot")
    if slot == "coda":
        return "coda"
    if slot == "vowel":
        return "vowel"
    if slot != "onset":
        return None
    a, b = c.get("target"), c.get("heard")
    fa, fb = _C_FEAT.get("" if a == "ㅇ" else a), _C_FEAT.get("" if b == "ㅇ" else b)
    if not fa or not fb or "none" in (fa[0], fb[0]):
        return None
    diff = [i for i in range(3) if fa[i] != fb[i]]
    if diff == [2]:
        return "laryngeal"
    if (a in _FRIC or b in _FRIC) and 0 in diff:
        return "fricative"
    if 0 not in diff and 1 in diff:
        return "manner"          # 콧소리·흐름소리는 세기가 'son'이라 방식과 세기가 함께 다르게 잡힌다(ㅁ·ㅂ)
    if diff == [0]:
        return "place"
    return None


def _contrast_pred(spec: Dict):
    """대조 이름 → 낱말 대조 하나를 받아 맞는지 돌려주는 함수."""
    if spec["type"] == "kind":
        return lambda c: contrast_kind(c) == spec["kind"]
    f = {"slot": spec["slot"], "target": spec["a"], "heard": spec["b"]}
    return lambda c: _matches(c, f)


def ax_pairs_for(spec: Dict) -> List[Dict]:
    """대조 이름에 맞는 소리 구별 짝. 종류면 그 종류의 짝 전부, 자리 대조면 그 대조 하나로만 갈리는 짝."""
    if spec["type"] == "kind":
        return [p for p in AX_PAIRS if p["kind"] == spec["kind"]]
    pred = _contrast_pred(spec)
    out = []
    for p in AX_PAIRS:
        cs = contrast_of(p["a"], p["b"])
        if len(cs) == 1 and pred(cs[0]):
            out.append(p)
    return out


def contrast_ax_items(pairs: Sequence[Dict], seed: str, n: int) -> List[Dict]:
    """짝 목록에서 같다·다르다 문항 n개(같음·다름 반반). 키·채점은 1단계와 같다(ax_key·ax_correct)."""
    if not pairs or n <= 0:
        return []
    r = _rng(f"pax:{seed}")
    out = []
    for k in range(n):
        p = r.choice(list(pairs))
        a, b = (p["a"], p["b"]) if r.random() < 0.5 else (p["b"], p["a"])
        first, second = (a, a) if k % 2 == 0 else (a, b)
        out.append({"type": "ax", "stage": 1, "key": ax_key(first, second, p["level"]), "first": first, "second": second,
                    "kind": p["kind"], "kind_label": AX_KIND_LABEL[p["kind"]], "level": p["level"],
                    "voice_pair": [0, 1] if p["level"] >= 3 else [0, 0], "avoid_voices": avoid_voices_ax(p["a"], p["b"])})
    return out


def contrast_word_items(spec: Dict, pool: Sequence[str], seed: str, n: int, level: int = 2) -> List[Dict]:
    """대조로 갈리는 낱말 고르기 문항 n개. 정답 낱말마다 그 대조 하나로만 갈리는 이웃(소리 거리 4 이하)을 보기에 꼭 넣는다
    (word_items의 focus와 같은 방식이지만 문항 전부가 그 대조다). 수준 2(4지, 나머지 보기는 거리 3~6) 또는 3(1~2)."""
    if n <= 0:
        return []
    level = max(2, min(3, int(level)))
    pred = _contrast_pred(spec)
    nb = _neighbors(pool)
    cands = list(pool)
    r = _rng(f"pw:{seed}:{spec['key']}")
    r.shuffle(cands)
    out: List[Dict] = []
    for w in cands:
        if len(out) >= n:
            break
        hit = None
        for d, o in nb.get(w, []):
            if d > 4:
                break
            cs = contrast_of(w, o)
            if len(cs) == 1 and pred(cs[0]):
                hit = (o, cs[0])
                break
        if not hit:
            continue
        it = word_item(w, level, pool, seed, nb=nb.get(w, []))
        if not it:
            continue
        if hit[0] not in it["options"]:
            it["options"][next(i for i, x in enumerate(it["options"]) if x != w)] = hit[0]
        out.append({"type": "word", "stage": 2, **it,
                    "focus": {"slot": hit[1]["slot"], "target": hit[1]["target"], "heard": hit[1]["heard"]}})
    return out


def contrast_practice_items(spec: Dict, pool: Sequence[str], seed: str, n: int = 12, level: int = 2) -> List[Dict]:
    """소리 짝 집중 연습 n개: 같다·다르다 문항과 낱말 고르기 문항을 반씩(한쪽이 모자라면 다른 쪽으로 채움) 섞는다."""
    pairs = ax_pairs_for(spec)
    words = contrast_word_items(spec, pool, seed, n if not pairs else n // 2, level)
    if not pairs:
        items = words
    else:
        items = contrast_ax_items(pairs, seed, n - len(words)) + words
    _rng(f"pmix:{seed}").shuffle(items)
    return items


# 소리 교실(소리 짝 둘러보기)의 종류별 설명. 무엇이 다른지, 보청기·인공와우로 왜 어려운지(docs/auditory-training-design.md,
# AX_PAIRS 머리말). 입모양 문장은 짝마다 engine.VISEME_MAP으로 판정해 contrast_catalog가 덧붙인다.
KIND_DESC = {
    "length": "말의 길이(음절 수)가 달라요. 바와 바다처럼 짧은 말과 긴 말을 가려요. 길이는 보청기나 인공와우로도 비교적 잘 들려 처음 연습하기 좋아요.",
    "intonation": "끝이 올라가면 묻는 말, 내려가면 말하는 말이에요. 인공와우는 소리의 높낮이를 자세히 전하지 못해 억양을 놓치기 쉬워요.",
    "vowel": "아, 이, 우처럼 모음이 달라요. 모음은 크고 길게 나서 잘 들리는 편이지만, 어와 오처럼 비슷한 모음은 헷갈리기 쉬워요.",
    "manner": "소리 내는 방법이 달라요. ㅁ은 코로 소리를 내고 ㅂ은 입술을 막았다가 터뜨려요. 방법 차이는 낮은 소리 쪽에도 남아 자리 차이보다는 잘 들리는 편이에요.",
    "laryngeal": "ㅂ, ㅃ, ㅍ처럼 같은 자리에서 소리의 세기가 달라요. 거센소리는 숨이 세게 나오고 된소리는 목에 힘이 들어가요. 숨소리 차이는 높은 소리 쪽에 있어 약하게 들릴 수 있어요.",
    "place": "소리를 내는 자리가 달라요. ㅂ은 입술, ㄷ은 혀끝, ㄱ은 혀 뒤에서 나요. 자리 차이는 아주 짧은 순간의 높은 소리 변화로만 들려서 보청기나 인공와우를 쓰면 가장 자주 놓쳐요.",
    "fricative": "ㅅ, ㅈ, ㅊ, ㅎ처럼 바람 소리가 나는 자음이에요. 아주 높은 소리라 높은 소리가 잘 안 들리면 거의 들리지 않을 수 있어요.",
    "coda": "받침이 달라요. 간과 감, 각과 갑처럼 음절 끝소리가 달라요. 받침은 짧고 약하게 나서 놓치기 쉬워요.",
}
LIP_TEXT = {
    "same": "입모양은 같아서 입만 봐서는 가를 수 없어요. 소리로 가려야 해요.",
    "differs": "입모양은 달라서 입을 함께 보면 도움이 돼요.",
    "mixed": "짝에 따라 입모양이 같기도 하고 다르기도 해요.",
}


def lip_same(c: Optional[Dict], kind: Optional[str] = None) -> Optional[bool]:
    """대조 하나의 두 소리가 입모양 무리(engine.VISEME_MAP)가 같은가. 길이 짝은 입 움직임 길이가 달라 False, 억양 짝은 글이 같아 True.
    받침 없음·소리 없는 첫소리처럼 무리를 정할 수 없으면 None."""
    if kind == "length":
        return False
    if kind == "intonation":
        return True
    if not c:
        return None
    from engine import VISEME_MAP
    a, b = c.get("target"), c.get("heard")
    if "-" in (a, b) or (c.get("slot") == "onset" and "ㅇ" in (a, b)):
        return None
    va, vb = VISEME_MAP.get(a), VISEME_MAP.get(b)
    if va is None or vb is None:
        return None
    return va == vb


def contrast_catalog(pool: Sequence[str], has_sound=None, n_words: int = 6) -> List[Dict]:
    """소리 교실 목록: 종류(AX_KIND_LABEL 순서)마다 설명·소리 구별 짝·예시 낱말 짝. has_sound(글)가 거짓인 글(서버 음성이 없는 글)은
    넣지 않는다. 예시 낱말은 그 종류의 대조 하나로만 갈리는 낱말 짝이고 소리 거리가 가까운 순이다(거리 1부터, 모자라면 2까지.
    마찰음 종류는 거리 1인 짝이 없다). 한 낱말은 한 번만 쓴다. 채점 없음."""
    ok = has_sound or (lambda t: True)
    words = [w for w in pool if ok(w)]
    nb = _neighbors(words)
    found: Dict[str, List[Tuple[int, str, str, Dict]]] = {k: [] for k in AX_KIND_LABEL}
    for w in sorted(words):
        for d, o in nb.get(w, []):
            if d > 2:
                break
            if o < w:
                continue
            cs = contrast_of(w, o)
            if len(cs) != 1:
                continue
            k = contrast_kind(cs[0])
            if k:
                found[k].append((d, w, o, cs[0]))
    out = []
    for k, label in AX_KIND_LABEL.items():
        pairs = []
        for p in AX_PAIRS:
            if p["kind"] != k or not (ok(p["a"]) and ok(p["b"])):
                continue
            cs = contrast_of(p["a"], p["b"])
            pairs.append({"a": p["a"], "b": p["b"], "level": p["level"],
                          "lip_same": lip_same(cs[0] if len(cs) == 1 else None, k), "avoid_voices": avoid_voices_ax(p["a"], p["b"])})
        ex, seen = [], set()
        for d, w, o, c in sorted(found[k], key=lambda x: (x[0], x[1], x[2])):
            if len(ex) >= n_words:
                break
            if w in seen or o in seen:
                continue
            seen |= {w, o}
            ex.append({"target": w, "partner": o, "distance": d, "contrast": f"{c['slot']}:{c['target']}:{c['heard']}",
                       "lip_same": lip_same(c), "avoid_voices": avoid_voices_ax(w, o)})
        flags = {x["lip_same"] for x in pairs + ex if x["lip_same"] is not None}
        lip = "same" if flags == {True} else "differs" if flags == {False} else "mixed" if flags else None
        out.append({"kind": k, "label": label, "practice_key": f"kind:{k}", "lip": lip,
                    "desc": KIND_DESC[k] + (" " + LIP_TEXT[lip] if lip else ""), "pairs": pairs, "words": ex})
    return out


def scene_places() -> List[Dict]:
    """장면 묶음 [{key, label, n, places}] (SCENES 순서). n은 문항 수, places는 그 묶음에 실제로 문항이 있는 장소 이름."""
    out = []
    for s in SCENES:
        its = [c for c in CONVO_ITEMS if c["place"] in s["places"]]
        out.append({"key": s["key"], "label": s["label"], "n": len(its),
                    "places": [p for p in s["places"] if any(c["place"] == p for c in its)]})
    return out


def scene_items(place: str, seed: str, recent: Sequence[str] = ()) -> Optional[List[Dict]]:
    """장면 묶음 key(또는 장소 이름 하나)의 대화 문항 전부. 최근에 낸 것(recent id)을 뒤로 두고 나머지는 seed 순서.
    정답 번호는 뺀다(convo_items와 같은 꼴). 모르는 이름이면 None."""
    sc = next((s for s in SCENES if s["key"] == place), None)
    if sc:
        places = set(sc["places"])
    elif any(c["place"] == place for c in CONVO_ITEMS):
        places = {place}
    else:
        return None
    ids = [c["id"] for c in CONVO_ITEMS if c["place"] in places]
    _rng(f"sc:{seed}:{place}").shuffle(ids)
    seen = set(recent)
    ids = [i for i in ids if i not in seen] + [i for i in ids if i in seen]
    out = []
    for i in ids:
        c = CONVO_BY_ID[i]
        out.append({"key": f"c:{i}", "id": i, "place": c["place"], "line": c["line"], "paraphrase": c["paraphrase"],
                    "question": c["question"], "options": list(c["options"])})
    return out


def condition_items(cond: str, seed: str, n: int = 10, recent: Sequence[str] = (), noise: Optional[str] = None,
                    snr_db: Optional[float] = None) -> List[Dict]:
    """듣기 조건 고르기: 훈련 문장 n개에 조건을 붙인다. room은 잔향 시간을 문항마다 돌리고(ROOM_RT60), noise는 잡음 종류를
    noise로 고정하거나(훈련 잡음만, 일반화용 talker2는 쓰지 않음) 문항마다 돌린다. snr_db는 noise 조건의 말과 잡음 크기 차이
    (main이 학습자의 4단계 역치로 정한다)."""
    out = []
    for k, it in enumerate(sentence_items(f"pc:{cond}:{seed}", n=n, recent=recent)):
        x = {**it, "cond": cond}
        if cond == "room":
            x["rt60"] = ROOM_RT60[k % len(ROOM_RT60)]
        elif cond == "noise":
            x["noise"] = noise if noise in TRAIN_NOISES else TRAIN_NOISES[k % len(TRAIN_NOISES)]
            x["snr_db"] = snr_db
        out.append(x)
    return out
