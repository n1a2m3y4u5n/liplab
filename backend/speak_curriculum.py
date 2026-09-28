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
import math
import random
import re
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
# 읽기 WORD_BANK에서 중복 없이 보강 → 풀을 더 크게. 사전·사후 표준검사 정답과 드문 말은 뺀다(9/27 감사: 말하기 화면은 아바타로
# 그 단어의 입모양을 보여 줘 검사 단어가 훈련에 노출됐다. 우유·가방·하늘·무지개가 처음 60문항 안에 있었다).
try:
    from assessment import test_only_words as _test_only_words
    _SKIP = set(_test_only_words())
except Exception:
    _SKIP = set()
try:
    from curriculum import STAGE2_EXCLUDED as _RARE
    _SKIP |= set(_RARE)
except Exception:
    pass
_STAGE4_WORDS = [w for w in dict.fromkeys(_STAGE4_BASE + [w["word"] for w in _WORD_BANK]) if w not in _SKIP]


# D-GOP를 쓰는 4·5단계(합격 65)의 숙달 문턱은 9/28 실제 청각장애 발화 측정으로 90·85 → 77로 내렸다. 608 감음신경성 화자가 대본을
# 읽은 문장의 65점 합격률은 82.2%(화자 절반 1은 73.1%)라 90·85는 대본대로 읽어도 닿기 어려웠다. 문턱 = 기대 합격률 − 5점
# (docs/curriculum-roadmap.md 2-1, docs/speak-transcript-scoring.md D-GOP 절). 그래도 문턱 아래에 머무는 학습자를 위해 개인 향상 경로를
# 둔다: 이 단계 시도가 20번 이상이고 최근 10번 점수 중앙값이 처음 10번 중앙값보다 15점 이상 높으면 숙달(gain_mastered).
_GAIN = {"first": 10, "recent": 10, "delta": 15.0, "min_attempts": 20}


def gain_mastered(scores: List[float], gain: Optional[Dict]) -> bool:
    """개인 향상 경로 숙달: 시간순 점수에서 최근 창 중앙값 − 처음 창 중앙값 >= delta. 순수 함수."""
    if not gain:
        return False
    xs = [float(x) for x in scores if x is not None]
    if len(xs) < int(gain["min_attempts"]):
        return False
    def med(v):
        v = sorted(v)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return med(xs[-int(gain["recent"]):]) - med(xs[:int(gain["first"])]) >= float(gain["delta"])


# 모음·자음(2·3) 음운 수준 확인(docs/curriculum-roadmap.md 2-5, P9). 따로 낸 음절 점수만으로는 그 소리를 뜻 있는 낱말 속에서도
# 내는지(Ling의 음운 수준) 알 수 없어, 이동 평균이 문턱에 닿으면 4단계 단어 풀에서 목표 소리가 첫 음절에 든 낱말 n개를 내고
# 최근 n번 중 need번 이상 합격(4단계 규칙, 합격 65)해야 숙달로 본다. 처음 설계는 5개 중 4개였지만 가상 학습자에서 숙달까지 시도가
# 27% 늘어(기준 20%) 4개 중 3개로 줄였다(20%, 시드 1 확인). 맞게 말한 청각장애 발화의 65점 합격률 82%에서 한 번에 넘을 확률은
# 4개 중 3개 85%, 5개 중 4개 78%다(docs/mastery-ewma.md 8절).
_PROBE = {"n": 4, "need": 3}
_PROBE_FAMILIAR = 4   # 소리마다 풀 앞쪽 몇 개 안에서 고를지(probe_words)


# mastery는 최근 가중 합격률(편향 보정 이동 평균 a 0.08, main._bump_speak_progress)의 문턱이다. 9/27 밤 누적 합격률 65·70에서
# 바꿨다: 가상 학습자에서 거짓 숙달과 지연이 모든 단계에서 줄고 숙련 학습자는 최소 시도 수 그대로(docs/mastery-ewma.md 6절).
SPEAK_STAGES: List[Dict] = [
    {
        "stage": 0, "title": "발성", "icon": "🗣️", "mode": "voicing",
        "desc": "원할 때 목소리 내기 · 길게 유지",
        "guide": "배에 숨을 담고 '아' 소리를 2초 이상 안정적으로 내보세요. 소리가 곧게 이어지는 게 목표예요.",
        "min_attempts": 5, "mastery": 85.0,
        "items": [{"target": "아"}, {"target": "이"}, {"target": "우"}],
    },
    {
        "stage": 1, "title": "운율 조절", "icon": "🎚️", "mode": "prosody",
        "desc": "크기 · 길이 · 높낮이 바꾸기",
        "guide": "지시대로 목소리의 크기·길이·억양을 바꿔보세요. 아래 곡선으로 바로 확인돼요.",
        "min_attempts": 10, "mastery": 90.0,
        "items": [
            {"target": "아", "drill": "loud", "prompt": "“아”를 크게! (크기 60 이상)"},
            {"target": "아", "drill": "soft", "prompt": "“아”를 작게, 속삭이듯 (크기 12~45)"},
            {"target": "아", "drill": "long", "prompt": "“아—”를 길게 (2초 이상)"},
            {"target": "아", "drill": "rise", "prompt": "“아?”처럼 끝을 올리며 (억양 상승)"},
            {"target": "아", "drill": "fall", "prompt": "“아.”처럼 끝을 내리며 (억양 하강)"},
        ],
    },
    {
        "stage": 2, "title": "모음", "icon": "👄", "mode": "phoneme",
        "desc": "기본 모음 8개, 가장 잘 보이는 소리",
        # 예전 안내 '입을 크게 벌리고 … 모음은 입 모양만 봐도 구별돼요'는 이·우·으(작게 벌림)에 틀렸고, 오/우·어/으는
        # 입모양 무리가 같다(engine.VISEME_MAP 4·5).
        "guide": "아바타의 입 모양을 따라 모음마다 입 벌림(아는 크게, 이·우·으는 작게)과 입술 모양(오·우는 동그랗게, "
                 "이·으는 옆으로)을 또렷하게 바꿔 보세요. 오/우, 어/으처럼 입 모양이 비슷한 짝은 턱을 벌리는 정도(오·어가 "
                 "더 크게)로 구별해요.",
        "min_attempts": 8, "mastery": 85.0, "pass": 50.0, "probe": _PROBE,
        "items": [{"target": v} for v in ["아", "어", "오", "우", "으", "이", "애", "에"]],
    },
    {
        "stage": 3, "title": "자음", "icon": "🅿️", "mode": "phoneme",
        "desc": "입술소리부터 · 최소대립쌍",
        "guide": "같은 자리에서 나는 소리(예: 불/풀, 달/탈)는 입 모양이 같고 숨의 세기가 달라요. 거센소리(ㅍ·ㅌ·ㅋ)는 "
                 "손바닥을 입 앞에 대고 바람이 세게 닿게 내 보세요.",
        "min_attempts": 8, "mastery": 85.0, "pass": 50.0, "probe": _PROBE,
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
        "min_attempts": 8, "mastery": 77.0, "pass": 65.0, "gain": _GAIN,
        "items": [{"target": w} for w in _STAGE4_WORDS],
    },
    {
        "stage": 5, "title": "문장·억양", "icon": "💬", "mode": "sentence",
        "desc": "문장 억양: 평서문은 내림, 의문문은 올림",
        "guide": "문장 끝의 억양까지 살려보세요. 평서문(.)은 끝을 내리고, 예/아니오로 답하는 의문문(?)은 마지막 음절을 올려요.",
        "min_attempts": 6, "mastery": 77.0, "pass": 65.0, "gain": _GAIN,
        "items": [
            {"target": "밥 먹었어요.", "intonation": "fall"},
            {"target": "밥 먹었어요?", "intonation": "rise"},
            {"target": "오늘 날씨가 좋아요.", "intonation": "fall"},
            {"target": "같이 갈래요?", "intonation": "rise"},
            {"target": "고맙습니다.", "intonation": "fall"},
            {"target": "학교 가요?", "intonation": "rise"},
            {"target": "물 좀 주세요.", "intonation": "fall"},
            {"target": "처음 오셨어요?", "intonation": "rise"},
            {"target": "정말 재미있어요.", "intonation": "fall"},
            {"target": "지금 바빠요?", "intonation": "rise"},
            {"target": "내일 만나요.", "intonation": "fall"},
            {"target": "괜찮으세요?", "intonation": "rise"},
            {"target": "잘 지냈어요.", "intonation": "fall"},
            {"target": "이거 새로 샀어요?", "intonation": "rise"},
            {"target": "천천히 말해 주세요.", "intonation": "fall"},
            {"target": "다시 한 번요?", "intonation": "rise"},
        ],
    },
]

_BY_STAGE = {s["stage"]: s for s in SPEAK_STAGES}


def _n_syllables(text: str) -> int:
    return sum(1 for ch in text or "" if "가" <= ch <= "힣")


def mixed_order(items: List[Dict], seed: str, lead: int = 3) -> List[Dict]:
    """4단계 단어 순서. 음절 수 층(1·2·3음절)을 seed로 각각 섞고, 처음 lead개는 1음절로 둔 뒤 층을 크기 비율대로 고르게 끼운다
    (층마다 (i+0.5)/층 크기 자리에 놓고 합친다). 예전에는 늘 같은 고정 순서라 앞 14개가 모두 1음절(밥·물·손…)이었고, 프론트는
    들어올 때마다 0번부터 시작해 합격률 0.95 학습자의 93%가 1음절 단어만 말하고 숙달했다(최소 8회, 이동 평균 90).
    seed는 (사용자, 날짜)라 같은 날에는 순서가 고정되고 날마다 앞 문항이 바뀐다."""
    rng = random.Random(seed)
    strata: Dict[int, List[Dict]] = {}
    for it in items:
        strata.setdefault(_n_syllables(it.get("target", "")), []).append(it)
    for k in sorted(strata):
        rng.shuffle(strata[k])
    shortest = min(strata) if strata else 0
    head = strata.get(shortest, [])[:lead]
    rest = {k: (v[len(head):] if k == shortest else v) for k, v in strata.items()}
    slots = [((i + 0.5) / len(v), k, i) for k, v in rest.items() for i in range(len(v))]
    return head + [rest[k][i] for _, k, i in sorted(slots)]


def interleaved_order(items: List[Dict], attempts: int, seed: str) -> List[Dict]:
    """모음·자음 단계(2·3) 순서(docs/curriculum-roadmap.md 2-4). 이 단계를 항목 수만큼 연습하기 전에는 원래 순서(아 어 오 …, 대립 짝끼리
    붙은 순서)로 한 번씩 익히고, 그 뒤로는 (사용자, 날짜) seed로 섞는다. 같은 항목을 차례로 반복하는 블록 연습은 습득은 빠르지만
    유지·전이는 섞은 연습이 낫다(운동학습 원리, Maas 외 2008)."""
    if attempts < len(items):
        return list(items)
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


def weak_sounds(attempts: List[Dict], k: int = 3, min_n: int = 2, rel_max: float = 0.8) -> List[str]:
    """최근 말하기 시도에서 약한 소리(자모) k개. D-GOP가 음소마다 잰 점수(phones: [{label, dgop}])를 시도마다 그 시도 평균으로
    나눠 상대값으로 모으고(문장 난이도·목소리 차이를 지움), min_n번 이상 나왔고 상대 평균이 rel_max 미만인 것을 낮은 순으로 고른다.
    전사 경로 시도는 음소 점수가 없으므로 혼동 기록(confusions: [{correct, confused_as}])에서 2번 이상 틀린 소리를 더한다."""
    rel: Dict[str, List[float]] = {}
    conf: Dict[str, int] = {}
    for a in attempts:
        ph = [p for p in (a.get("phones") or []) if p.get("label") and p.get("dgop") is not None]
        if len(ph) >= 2:
            m = sum(float(p["dgop"]) for p in ph) / len(ph)
            if m > 0:
                for p in ph:
                    rel.setdefault(p["label"], []).append(float(p["dgop"]) / m)
        for c in a.get("confusions") or []:
            j = (c or {}).get("correct")
            if j:
                conf[j] = conf.get(j, 0) + 1
    ranked = sorted(((sum(v) / len(v), lab) for lab, v in rel.items() if len(v) >= min_n and sum(v) / len(v) < rel_max))
    out = [lab for _, lab in ranked]
    out += [j for j, n in sorted(conf.items(), key=lambda x: -x[1]) if n >= 2 and j not in out]
    return out[:k]


def _has_sound(text: str, sounds) -> bool:
    import jamo_vocab
    return any(t.split(":", 1)[-1] in sounds for t in jamo_vocab.text_to_tokens(text))


def focus_order(items: List[Dict], sounds: List[str], lead: int = 0) -> List[Dict]:
    """약한 소리가 든 문항을 앞쪽에 고르게 끼운다. 처음 lead개는 그대로 두고, 그 뒤로 두 칸에 한 칸꼴(최대 절반)로 약한 소리 문항을
    넣는다(나머지 소리 연습이 빠지지 않게). 소리가 없거나 해당 문항이 없으면 그대로. 모음·자음 단계는 lead 0으로 약한 소리부터 낸다."""
    if not sounds:
        return items
    head, rest = items[:lead], items[lead:]
    hit = [it for it in rest if _has_sound(it.get("target", ""), sounds)]
    if not hit:
        return items
    other = [it for it in rest if not _has_sound(it.get("target", ""), sounds)]
    out = []
    while hit or other:
        if hit:
            out.append(hit.pop(0))
        if other:
            out.append(other.pop(0))
    return head + out


def _first_syllable(word: str) -> Optional[Tuple[str, str, str]]:
    from scoring import to_pronounced_jamos
    js = to_pronounced_jamos(word or "")
    return js[0] if js else None


def probe_sound(stage_no: int, word: str) -> Optional[str]:
    """음운 수준 확인에서 이 낱말이 가리키는 목표 소리. 자음 단계(3)는 첫 음절 첫소리, 모음 단계(2)는 첫 음절 모음(ㅔ는 ㅐ로 본다).
    첫 음절 첫소리·모음은 소리 나는 대로 바꿔도 달라지지 않아 채점 위치가 분명하다. 대상 단계가 아니면 None."""
    j = _first_syllable(word)
    if not j:
        return None
    if stage_no == 3:
        return j[0] or None
    if stage_no == 2:
        return _SAME_VOWEL.get(j[1], j[1])
    return None


def stage_sounds(stage_no: int) -> List[str]:
    """모음·자음 단계의 목표 소리(문항 순서, 중복 없이). 모음은 애·에를 한 소리(ㅐ)로 센다."""
    stg = get_stage(stage_no)
    if not stg or not stg.get("probe"):
        return []
    return list(dict.fromkeys(s for s in (probe_sound(stage_no, it["target"]) for it in stg["items"]) if s))


def probe_words(stage_no: int, seed: str, weak: Optional[List[str]] = None, pool: Optional[List[str]] = None) -> List[Dict]:
    """음운 수준 확인 낱말(docs/curriculum-roadmap.md 2-5). 4단계 단어 풀에서 목표 소리가 첫 음절(자음은 첫소리, 모음은 모음)에 든
    낱말을 소리마다 하나씩, 서로 다른 소리 n개(_PROBE)로 고른다. 약한 소리(weak_sounds)부터 고르고 나머지는 seed로 섞는다. 1·2음절 낱말을
    먼저 쓰고 없으면 3음절까지, 이 단계 문항과 같은 낱말(달·탈·불 등)은 빼서 따로 낸 음절의 되풀이가 되지 않게 한다.
    seed는 (사용자, 날짜)라 같은 날에는 같은 낱말이다."""
    stg = get_stage(stage_no)
    cfg = (stg or {}).get("probe")
    if not cfg:
        return []
    rng = random.Random(seed)
    sounds = stage_sounds(stage_no)
    items = {it["target"] for it in stg["items"]}
    cands: Dict[str, List[str]] = {s: [] for s in sounds}
    for w in (pool if pool is not None else _STAGE4_WORDS):
        n = _n_syllables(w)
        if w in items or n < 1 or n != len(w) or n > 3:   # 한글 음절만으로 된 1~3음절
            continue
        s = probe_sound(stage_no, w)
        if s in cands:
            cands[s].append(w)
    weak_n = [_SAME_VOWEL.get(x, x) if stage_no == 2 else x for x in (weak or [])]
    first = [s for s in dict.fromkeys(weak_n) if s in cands]
    rest = [s for s in sounds if s not in first]
    rng.shuffle(rest)
    out: List[Dict] = []
    for s in first + rest:
        ws = cands[s]
        # 풀은 큐레이션 단어 → 단어 은행 순이고 앞쪽일수록 쉬운 말이라, 소리마다 앞쪽 _PROBE_FAMILIAR개 안에서 고른다.
        # 전체에서 고르면 능·탓·짚·폭로처럼 드문 말이 나와 소리보다 낱말이 낯설어 틀리게 된다.
        pick = ([w for w in ws if _n_syllables(w) <= 2] or ws)[:_PROBE_FAMILIAR]
        if not pick:
            continue
        out.append({"target": rng.choice(pick), "probe": True, "sound": s})
        if len(out) >= int(cfg["n"]):
            break
    return out


def probes_ok(passes: List[Optional[bool]], cfg: Optional[Dict]) -> bool:
    """음운 수준 확인 통과: 시간순 합격 기록의 최근 n번 중 need번 이상 합격. 순수 함수."""
    if not cfg:
        return True
    window = [bool(p) for p in passes][-int(cfg["n"]):]
    return sum(window) >= int(cfg["need"])


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


# 억양 방향은 반음(로그 척도)으로 잰다. 예전 Hz 기준(올리기·내리기 15Hz, 문장 방향 12Hz)은 목소리 높이에 따라 실제 어려움이 달랐다
# (15Hz가 남성 120Hz에서는 2.0반음, 여성 220Hz에서는 1.1반음, 아동 260Hz에서는 1.0반음). 문턱은 예전 Hz 기준을 150Hz 목소리에서 환산한
# 값이라 남성은 조금 쉬워지고(약 12Hz) 여성·아동은 조금 어려워진다(약 22·26Hz). 프론트 lib/speakTone.js도 같은 값이다.
RISE_FALL_ST = 1.65      # 올리기·내리기 연습(예전 15Hz)
SENTENCE_DIR_ST = 1.33   # 문장 억양 방향(예전 12Hz)


def semitones(f_from: float, f_to: float) -> float:
    """f_from → f_to 음높이 변화(반음). 둘 중 하나라도 0 이하면(음높이를 못 잼) 0."""
    return 12.0 * math.log2(f_to / f_from) if f_from and f_to and f_from > 0 and f_to > 0 else 0.0


def sentence_direction(m: Dict) -> float:
    """문장 끝 억양(반음). 클라이언트가 pitch_ref(유성 프레임 전체 중앙값)·pitch_final(마지막 3프레임 중앙값)을 보내면 그것으로,
    없으면(예전 클라이언트) 앞 30% → 뒤 30% 평균. 예전 척도는 마지막 음절의 상승을 앞 음절과 섞어 묻었다. 538 음성 확인 절반에서
    예/아니오 의문문 대 평서문 AUC 0.540 → 0.670, 의문문 올림 판정 0.25 → 0.38, 평서문 내림 판정 0.53 → 0.70
    (docs/sentence-intonation.md)."""
    ref, fin = m.get("pitch_ref") or 0, m.get("pitch_final") or 0
    if ref > 0 and fin > 0:
        return semitones(ref, fin)
    return semitones(m.get("pitch_start", 0) or 0, m.get("pitch_end", 0) or 0)


# 의문사 의문문(설명 의문문)은 끝이 대개 내려가(538 음성에서 끝 상승 비율이 평서문과 비슷) '끝을 올리라'는 문항으로 맞지 않는다.
_WH_WORD = re.compile(r"(뭐|뭘|무엇|무슨|어디|언제|누구|누가|누굴|왜|어떻게|어떤|어느|몇|얼마)")


def expected_intonation(text: str) -> Optional[str]:
    """문장 부호로 정한 기대 억양. 예/아니오 의문문 'rise', 평서·감탄 'fall', 의문사 의문문은 None(억양 문항으로 쓰지 않음)."""
    t = (text or "").strip()
    if t.endswith("?"):
        last = re.split(r"(?<=[.?!])\s+", t)[-1]
        return None if _WH_WORD.search(last) else "rise"
    return "fall"


def _sustained(m: Dict) -> float:
    """이어 낸 소리 길이(초). 클라이언트가 가장 긴 발성 구간(voiced_duration)을 보내면 그것, 없으면 녹음 길이(예전 클라이언트).
    예전에는 늘 녹음 길이라 '아'를 짧게 내고 기다렸다 멈춰도 '길게 유지'로 통과했다."""
    v = m.get("voiced_duration")
    return float(v) if v is not None else float(m.get("duration", 0) or 0)


def _score_prosody(drill: str, m: Dict) -> Tuple[float, bool, str]:
    loud = m.get("loudness", 0) or 0
    dur = _sustained(m)
    d = semitones(m.get("pitch_start", 0) or 0, m.get("pitch_end", 0) or 0)   # 시작 → 끝(반음)
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
        passed = d >= RISE_FALL_ST
        return round(min(100, max(0.0, d) / RISE_FALL_ST * 100), 1), passed, (
            "끝을 잘 올렸어요!" if passed else "끝을 더 확실히 올려보세요 (끝음이 시작보다 높게).")
    if drill == "fall":
        passed = (-d) >= RISE_FALL_ST
        return round(min(100, max(0.0, -d) / RISE_FALL_ST * 100), 1), passed, (
            "끝을 잘 내렸어요!" if passed else "끝을 더 확실히 내려보세요 (끝음이 시작보다 낮게).")
    return 0.0, False, ""


NO_VOICE_NOTE = "소리가 잡히지 않았어요. 마이크를 확인하고 가까이에서 다시 말해 보세요."


def no_voice(m: Dict) -> bool:
    """녹음에 소리가 없음(프론트 micIssue: 크기 0 또는 이어 낸 소리 0초). 값이 없으면(예전 클라이언트) 판정하지 않는다.
    이런 녹음도 크기가 500바이트를 넘으면 채점에 와서, Whisper가 무음에서 만든 문장이 합격할 수 있었다
    ('시청해 주셔서 감사합니다.'이면 2단계 8/8, 3단계 9/9 합격)."""
    loud, vd = m.get("loudness"), m.get("voiced_duration")
    return (loud is not None and loud <= 0) or (vd is not None and vd <= 0)


# 전사 경로 모음·자음 단계의 초점 자모. 음운 유사도(scoring)는 초성 30·중성 50·종성 20이고 받침이 둘 다 없으면 종성 몫을 줘서,
# 무음 초성 음절은 모음이 틀려도 50점(합격선 50)이 됐다. 9/27 감사에서 틀린 모음 160/160, 같은 모음의 틀린 첫소리 162/162가
# 합격했다(아→우 50.15, 풀→불 91.0). 모음 단계는 중성, 자음 단계는 첫소리와 (있으면) 받침이 전사와 같아야 합격이다.
# ㅐ와 ㅔ는 같은 소리로 본다(합류 여부는 사용자 결정 대기라 여기서 앞지르지 않는다).
_FOCUS = {2: ("중성",), 3: ("초성", "종성")}
_SAME_VOWEL = {"ㅔ": "ㅐ"}


def focus_miss(stage_no: int, target: str, transcript: str) -> Optional[str]:
    """모음·자음 단계에서 초점 자모가 전사와 어긋나면 안내 한 문장, 맞거나 대상 단계가 아니면 None.
    정렬은 채점·혼동 표시와 같은 scoring.align_jamos(소리 나는 대로 바꾼 자모)를 쓴다."""
    parts = _FOCUS.get(stage_no)
    if not parts:
        return None
    import unicodedata
    from scoring import align_jamos, to_pronounced_jamos
    cj = to_pronounced_jamos(unicodedata.normalize("NFC", target or "").replace(" ", ""))
    uj = to_pronounced_jamos(unicodedata.normalize("NFC", transcript or "").replace(" ", ""))
    for cs, us in align_jamos(cj, uj):
        if cs is None:
            continue
        if "중성" in parts:
            want = cs[1]
            if us is None:
                return f"목표 모음 '{want}' 소리가 들리지 않았어요."
            if _SAME_VOWEL.get(us[1], us[1]) != _SAME_VOWEL.get(want, want):
                return f"목표 모음은 '{want}'인데 '{us[1]}' 소리로 들렸어요."
        if "초성" in parts and cs[0]:
            if us is None or not us[0]:
                return f"목표 첫소리 '{cs[0]}' 소리가 들리지 않았어요."
            if us[0] != cs[0]:
                return f"목표 첫소리는 '{cs[0]}'인데 '{us[0]}' 소리로 들렸어요."
        if "종성" in parts and cs[2]:
            if us is None or not us[2]:
                return f"받침 '{cs[2]}' 소리가 들리지 않았어요."
            if us[2] != cs[2]:
                return f"목표 받침은 '{cs[2]}'인데 '{us[2]}' 소리로 들렸어요."
    return None


def score_attempt(stage_no: int, target: str, transcript: Optional[str],
                  metrics: Dict, drill: Optional[str] = None,
                  sim_score: Optional[float] = None) -> Tuple[float, bool, str]:
    """단계 모드에 맞춰 (점수 0~100, 성공 여부, 한 줄 코칭)을 반환.
    transcript는 전사 경로에서만 문자열이다(D-GOP 경로는 None). 소리 없음·초점 자모 판정은 전사 경로에만 적용한다."""
    stg = get_stage(stage_no)
    if not stg:
        return round(sim_score or 0.0, 1), (sim_score or 0) >= 60, ""
    mode = stg["mode"]
    m = metrics or {}

    if mode == "voicing":
        loud = m.get("loudness", 0) or 0
        dur = _sustained(m)
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
    if transcript is not None and no_voice(m):
        return 0.0, False, NO_VOICE_NOTE
    sc = float(sim_score or 0.0)
    passf = float(stg.get("pass", 60.0))
    passed = sc >= passf
    note = ""
    if mode == "phoneme" and transcript is not None:
        note = focus_miss(stage_no, target, transcript) or ""
        passed = passed and not note
    if mode == "sentence":
        # 고정 문항에 없는 문장(AI 생성·복습)은 문장 부호로 기대 억양을 정한다. 예전에는 고정 16문항만 찾아 AI 문장은 억양 판정이
        # 없었고, 대신 코칭에 목소리 높이에 따라 어려움이 다른 25Hz 규칙이 들어갔다. 의문사 의문문은 None이라 판정하지 않는다.
        exp = next((it.get("intonation") for it in stg["items"] if it["target"] == target), None) or expected_intonation(target)
        if exp:
            d = sentence_direction(m)
            got = "rise" if d > SENTENCE_DIR_ST else "fall" if d < -SENTENCE_DIR_ST else "flat"
            if got == exp:
                note = "억양 방향도 맞았어요!"
            elif got == "flat":
                note = f"억양이 평평했어요. 끝을 {'올려' if exp == 'rise' else '내려'}보세요."
            else:
                note = f"억양 방향이 반대예요. 끝을 {'올려' if exp == 'rise' else '내려'}보세요."
    return round(sc, 1), passed, note
