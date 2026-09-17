"""
발화(말하기) 커리큘럼 — Ling 발화 발달 단계(청각장애 음성재활 임상 표준)를 한국어화.

진행 순서: 발성 → 운율(크기·길이·높낮이) → 모음 → 자음 → 음절·단어 → 문장·억양.
'잘 들리고/보이고/느껴지는' 것부터 추상적인 것으로 올라간다. 각 단계의 채점 규칙을
콘텐츠 옆에 함께 둔다(모드별 성공 기준이 곧 그 단계의 학습 목표라서).

채점 모드(mode):
  voicing  — 발성: 유성음을 목표 길이 이상 안정적으로 (지표: duration, loudness)
  prosody  — 운율: 드릴별(크게/작게/길게/올리기/내리기) 목표 달성 (지표)
  phoneme  — 모음·자음: Whisper 전사 + 음운 유사도(관대)
  word     — 단어: Whisper 전사 + 명료도
  sentence — 문장: Whisper 전사 + 문장 억양(pitch 방향) 곁들임
"""
from typing import Dict, List, Optional, Tuple

try:
    from curriculum import WORD_BANK as _WORD_BANK
except Exception:  # pragma: no cover
    _WORD_BANK = [{"word": w} for w in ["밥", "물", "우유", "사과", "가방", "바다", "나무", "그림"]]

# 4단계 단어 — 짧은 것부터(1음절 → 다음절). 다양한 초·중·종성이 골고루 나오도록 큐레이션.
# (읽기 WORD_BANK도 섞어 매번 같은 문제만 나오지 않게 풀을 넉넉히 확보)
_STAGE4_BASE = [
    # 1음절
    "밥", "물", "손", "발", "눈", "코", "입", "귀", "산", "달", "별", "꽃", "집", "차",
    # 2음절
    "우유", "사과", "가방", "바다", "나무", "구름", "하늘", "노래", "다리", "머리",
    "토끼", "기차", "친구", "학교", "사랑", "엄마", "아빠", "가을", "겨울", "여름",
    # 3음절
    "자동차", "강아지", "고양이", "바나나", "무지개", "선생님", "운동화", "책가방",
]
# 읽기 WORD_BANK에서 중복 없이 보강 → 풀을 더 크게
_STAGE4_WORDS = list(dict.fromkeys(_STAGE4_BASE + [w["word"] for w in _WORD_BANK]))


SPEAK_STAGES: List[Dict] = [
    {
        "stage": 0, "title": "발성", "icon": "🗣️", "mode": "voicing",
        "desc": "원할 때 목소리 내기 · 길게 유지",
        "guide": "배에 숨을 담고 '아—' 소리를 2초 이상 안정적으로 내보세요. 소리가 곧게 이어지는 게 목표예요.",
        "min_attempts": 5, "mastery": 70.0,
        "items": [{"target": "아"}, {"target": "이"}, {"target": "우"}],
    },
    {
        "stage": 1, "title": "운율 조절", "icon": "🎚️", "mode": "prosody",
        "desc": "크기 · 길이 · 높낮이 바꾸기",
        "guide": "지시대로 목소리의 크기·길이·억양을 바꿔보세요. 아래 곡선으로 바로 확인돼요.",
        "min_attempts": 10, "mastery": 70.0,
        "items": [
            {"target": "아", "drill": "loud", "prompt": "“아”를 크게! (크기 60 이상)"},
            {"target": "아", "drill": "soft", "prompt": "“아”를 작게, 속삭이듯 (크기 15~45)"},
            {"target": "아", "drill": "long", "prompt": "“아—”를 길게 (2초 이상)"},
            {"target": "아", "drill": "rise", "prompt": "“아?”처럼 끝을 올리며 (억양 상승)"},
            {"target": "아", "drill": "fall", "prompt": "“아.”처럼 끝을 내리며 (억양 하강)"},
        ],
    },
    {
        "stage": 2, "title": "모음", "icon": "👄", "mode": "phoneme",
        "desc": "기본 모음 8개 — 가장 잘 보이는 소리",
        "guide": "입을 크게 벌리고 아바타의 입 모양을 따라 또렷하게. 모음은 입 모양만 봐도 구별돼요.",
        "min_attempts": 8, "mastery": 65.0, "pass": 50.0,
        "items": [{"target": v} for v in ["아", "어", "오", "우", "으", "이", "애", "에"]],
    },
    {
        "stage": 3, "title": "자음", "icon": "🅿️", "mode": "phoneme",
        "desc": "입술소리부터 · 최소대립쌍",
        "guide": "같은 자리에서 나는 소리의 차이(예: 불/풀, 달/탈)를 입 모양과 바람으로 구별해 발음하세요.",
        "min_attempts": 8, "mastery": 65.0, "pass": 50.0,
        "items": [
            {"target": "마"}, {"target": "바"}, {"target": "파"},
            {"target": "불"}, {"target": "풀"},
            {"target": "달"}, {"target": "탈"},
            {"target": "가"}, {"target": "카"},
        ],
    },
    {
        "stage": 4, "title": "음절·단어", "icon": "🔤", "mode": "word",
        "desc": "짧은 단어부터 여러 음절까지",
        "guide": "또박또박, 음절 하나하나 분명하게. 끝소리(받침)까지 살려주세요.",
        "min_attempts": 8, "mastery": 70.0, "pass": 65.0,
        "items": [{"target": w} for w in _STAGE4_WORDS],
    },
    {
        "stage": 5, "title": "문장·억양", "icon": "💬", "mode": "sentence",
        "desc": "문장 억양 — 평서문은 내림, 의문문은 올림",
        "guide": "문장 끝의 억양까지 살려보세요. 평서문(.)은 끝을 내리고, 의문문(?)은 끝을 올려요.",
        "min_attempts": 6, "mastery": 70.0, "pass": 65.0,
        "items": [
            {"target": "밥 먹었어요.", "intonation": "fall"},
            {"target": "밥 먹었어요?", "intonation": "rise"},
            {"target": "오늘 날씨가 좋아요.", "intonation": "fall"},
            {"target": "같이 갈래요?", "intonation": "rise"},
            {"target": "고맙습니다.", "intonation": "fall"},
            {"target": "어디 가요?", "intonation": "rise"},
            {"target": "물 좀 주세요.", "intonation": "fall"},
            {"target": "이름이 뭐예요?", "intonation": "rise"},
            {"target": "정말 재미있어요.", "intonation": "fall"},
            {"target": "지금 몇 시예요?", "intonation": "rise"},
            {"target": "내일 만나요.", "intonation": "fall"},
            {"target": "괜찮으세요?", "intonation": "rise"},
            {"target": "잘 지냈어요.", "intonation": "fall"},
            {"target": "이거 얼마예요?", "intonation": "rise"},
            {"target": "천천히 말해 주세요.", "intonation": "fall"},
            {"target": "다시 한 번요?", "intonation": "rise"},
        ],
    },
]

_BY_STAGE = {s["stage"]: s for s in SPEAK_STAGES}


def get_stage(n: Optional[int]) -> Optional[Dict]:
    return _BY_STAGE.get(n) if n is not None else None


def stages_overview() -> List[Dict]:
    """단계 메타(콘텐츠 개수 포함, items 제외) — 대시보드 사다리용."""
    out = []
    for s in SPEAK_STAGES:
        meta = {k: v for k, v in s.items() if k != "items"}
        meta["count"] = len(s["items"])
        out.append(meta)
    return out


def _score_prosody(drill: str, m: Dict) -> Tuple[float, bool, str]:
    loud = m.get("loudness", 0) or 0
    dur = m.get("duration", 0) or 0
    d = (m.get("pitch_end", 0) or 0) - (m.get("pitch_start", 0) or 0)   # 끝 - 시작 (Hz)
    if drill == "loud":
        passed = loud >= 60
        return round(min(100, loud / 60 * 100), 1), passed, (
            "크게 잘 냈어요!" if passed else f"조금 더 크게 (지금 {int(loud)}/100, 목표 60↑).")
    if drill == "soft":
        passed = 12 <= loud <= 45
        score = 100.0 if passed else max(0.0, 100 - abs(loud - 30) * 3)
        note = "적당히 작게 잘 냈어요!" if passed else (
            f"너무 커요 (지금 {int(loud)}). 더 작게." if loud > 45 else "소리가 거의 없어요. 살짝만 소리 내며.")
        return round(score, 1), passed, note
    if drill == "long":
        passed = dur >= 2.0
        return round(min(100, dur / 2.0 * 100), 1), passed, (
            "충분히 길게 유지했어요!" if passed else f"더 길게 (지금 {dur:.1f}초, 목표 2초↑).")
    if drill == "rise":
        passed = d >= 15
        return round(min(100, max(0.0, d) / 15 * 100), 1), passed, (
            "끝을 잘 올렸어요!" if passed else "끝을 더 확실히 올려보세요 (끝음이 시작보다 높게).")
    if drill == "fall":
        passed = (-d) >= 15
        return round(min(100, max(0.0, -d) / 15 * 100), 1), passed, (
            "끝을 잘 내렸어요!" if passed else "끝을 더 확실히 내려보세요 (끝음이 시작보다 낮게).")
    return 0.0, False, ""


def score_attempt(stage_no: int, target: str, transcript: Optional[str],
                  metrics: Dict, drill: Optional[str] = None,
                  sim_score: Optional[float] = None) -> Tuple[float, bool, str]:
    """단계 모드에 맞춰 (점수 0~100, 성공 여부, 한 줄 코칭)을 반환."""
    stg = get_stage(stage_no)
    if not stg:
        return round(sim_score or 0.0, 1), (sim_score or 0) >= 60, ""
    mode = stg["mode"]
    m = metrics or {}

    if mode == "voicing":
        loud = m.get("loudness", 0) or 0
        dur = m.get("duration", 0) or 0
        voiced = loud >= 22
        passed = voiced and dur >= 1.2
        score = min(100.0, min(dur, 2.0) / 2.0 * 60 + min(loud, 60) / 60 * 40)
        note = ("좋아요! 안정적으로 소리를 냈어요." if passed
                else ("소리는 났어요. 조금 더 길게 이어보세요." if voiced
                      else "소리가 약해요. 배에 힘을 주고 더 또렷이."))
        return round(score, 1), passed, note

    if mode == "prosody":
        return _score_prosody(drill or "", m)

    # phoneme / word / sentence — 음운 유사도 기반
    sc = float(sim_score or 0.0)
    passf = float(stg.get("pass", 60.0))
    passed = sc >= passf
    note = ""
    if mode == "sentence":
        exp = next((it.get("intonation") for it in stg["items"] if it["target"] == target), None)
        if exp:
            d = (m.get("pitch_end", 0) or 0) - (m.get("pitch_start", 0) or 0)
            got = "rise" if d > 12 else "fall" if d < -12 else "flat"
            if got == exp:
                note = "억양 방향도 맞았어요!"
            elif got == "flat":
                note = f"억양이 평평했어요. 끝을 {'올려' if exp == 'rise' else '내려'}보세요."
            else:
                note = f"억양 방향이 반대예요. 끝을 {'올려' if exp == 'rise' else '내려'}보세요."
    return round(sc, 1), passed, note
