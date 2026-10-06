"""
숙달 판정의 지연 탐침(종합 계획 C16, idea-sweep 가6).

숙달 기준(편향 보정 이동 평균, 문턱 80~85)은 가상 학습자의 거짓 숙달률로만 골랐고, 한번 숙달하면 계속 유지된다
(`docs/mastery-ewma.md` 4.5 한계). 그래서 읽기 1~3단계를 **처음 숙달한 날**(StageProgress.mastered_at, KST) 1일 뒤와 7일 뒤에 처음 보는
탐침 문항 6개를 보조 없이(1.0배 자연 속도, 감속·힌트·가상 화자 없음, 정답 공개 없음) 그날 레슨에 섞어 낸다.
탐침 답은 따로 기록하고(`mastery_probes` 표) **숙달·복습(SRS)·시행 기록·XP에 넣지 않는다**. 숙달을 취소하지도 않는다.

일정은 저장하지 않고 숙달 날짜에서 계산한다(`due_waves`). 이 모듈 이전에 숙달한 학습자는 창이 지났으면 탐침이 없다.
- 1일 탐침: 숙달 1~6일 뒤에 낸다. 7일 탐침: 7~13일 뒤. 그날 다 못 풀면 창 안의 다음 레슨으로 넘어간다(실제 지연 일수를 남긴다).
- 비율 상한(`lesson_quota`): 한 레슨에서 탐침은 전체 문항(레슨 문항 + 탐침)의 20% 이하다. 12문항 레슨이면 3개라 6개는 두 레슨에 나뉜다.
  실제 얼굴 탐침(C8)을 붙이면 같은 함수에 그 레슨에서 이미 낸 탐침 수(used)를 넣어 상한을 함께 쓴다.

문항(모두 4지선다, 찍기 0.25):
- 1단계: 연습 자극(정지 입모양, 대표 음절, 보기 예시 음절, 예시 낱말 첫 음절)에 없던 음절을 아바타로 보이고 입모양 무리를 고른다.
  보기는 퀴즈에 나오는 무리(잘 보이는 무리)에서 고르되, 음절 안에 함께 들어 있는 다른 무리는 뺀다(바의 ㅏ 때문에 '입 크게 벌림'을 빼는 식).
- 2단계: 학습자가 시행 기록에서 한 번도 정답으로 만나지 않은 단어. 보기는 표준검사와 같은 입모양 거리 규칙(가를 수 있는 헷갈리는 단어).
- 3단계: 학습자가 레슨에서 만나지 않은 코드 속 문장. 보기는 3단계와 같은 규칙(음절 수가 가까운 레슨 밖 문장).

분석(`probe_report`): 학습자·단계·회차마다 정답 확률을 추정하고(찍기 하한 0.25를 둔 균등 사전분포의 사후 평균), 거짓 숙달 선
(1·2단계 0.65, 3단계 0.60) 아래인 비율을 시뮬레이션 예측(1·2단계 6.5%, 3단계 10.9%, `docs/mastery-ewma.md` 4.5·5.3절)과 비교한다.
판정 기준(idea-sweep 가6): 7일 탐침의 그 비율이 예측 + 10%p 이하면 유지, 넘으면 숙달 규칙 재검토를 결정 목록에 올린다. 1일·7일 차이로
망각 크기를 보고한다. 보고만 하고 숙달 규칙은 바꾸지 않는다.
한계: 6문항 추정은 잡음이 커서, 실제 정답 확률이 선 바로 위인 학습자도 선 아래로 분류될 수 있다(시뮬레이션의 거짓 숙달은 참값 기준).
그래서 원 정답률 기준 비율도 함께 낸다.

**순수 함수**만 둔다. DB 조회(이미 본 단어·문장, 숙달 날짜)와 저장은 main.py가 한다.
"""
import random
import zlib
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Sequence

PROBE_STAGES = (1, 2, 3)
PROBE_ITEMS = 6                       # 회차마다 탐침 수(가6의 6~8개 중 하한, 비율 상한 때문에 두 레슨에 나뉜다)
WAVES = {1: (1, 6), 7: (7, 13)}       # 회차(숙달 뒤 일수): (낼 수 있는 첫날, 마지막 날)
PROBE_SHARE_CAP = 0.2                 # 한 레슨에서 탐침(지연 탐침 + 앞으로의 실제 얼굴 탐침)이 차지할 수 있는 비율
GUESS = 0.25                          # 4지선다 찍기
FALSE_MASTERY_LINE = {1: 0.65, 2: 0.65, 3: 0.60}
SIM_PREDICTION = {"1-2": 0.065, "3": 0.109}   # 판정 시점 거짓 숙달 비율(시뮬레이션, docs/mastery-ewma.md 4.5·5.3절)
DECISION_MARGIN = 0.10                # 예측 + 10%p 이하면 유지
MIN_ANSWERED = 4                      # 회차에서 이만큼 답해야 추정에 넣는다

# 1단계 화면이 이미 보인 음절(보기 이름의 예시 음절, frontend/src/lib/visemeLabels.js VISEME_PLAIN). 탐침에서 뺀다.
LABEL_SYLLABLES = {"바", "마", "아", "이", "오", "우", "어", "으", "와", "다", "나", "가", "하", "자"}

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"]
# 모음 무리 탐침의 첫소리: 소리 없는 ㅇ과 퀴즈에 나오지 않는 입 안쪽 무리(혀끝·혀 뒤·숨소리)라 보기와 겹치지 않는다
_VOWEL_ONSETS = ("ㅇ", "ㄷ", "ㄴ", "ㄱ", "ㅎ", "ㅅ")
# 자음 무리 탐침의 모음: 쓰는 모음의 무리는 보기에서 빠진다
_CONSONANT_VOWELS = ("ㅏ", "ㅓ", "ㅣ", "ㅗ", "ㅜ", "ㅡ")


def compose(cho: str, jung: str) -> Optional[str]:
    """첫소리·가운뎃소리로 받침 없는 음절을 만든다. 모르는 자모면 None."""
    if cho not in _CHO or jung not in _JUNG:
        return None
    return chr(0xAC00 + (_CHO.index(cho) * 21 + _JUNG.index(jung)) * 28)


def seed_for(user_id: int, stage: int, wave: int) -> int:
    """학습자·단계·회차마다 고정된 씨앗(같은 회차는 다시 만들어도 같은 문항)."""
    return zlib.crc32(f"mastery-probe:{user_id}:{stage}:{wave}".encode())


def due_waves(mastered_on: Optional[date], today: date) -> List[Dict]:
    """오늘 낼 수 있는 회차. [{wave, due_on, delay_days}]. 숙달 날짜가 없으면 빈 목록."""
    if mastered_on is None:
        return []
    days = (today - mastered_on).days
    out = []
    for wave, (first, last) in WAVES.items():
        if first <= days <= last:
            out.append({"wave": wave, "due_on": (mastered_on + timedelta(days=first)).isoformat(), "delay_days": days})
    return out


def lesson_quota(lesson_len: int, used: int = 0, cap: float = PROBE_SHARE_CAP) -> int:
    """한 레슨에 더 낼 수 있는 탐침 수. 탐침 / (레슨 문항 + 탐침) ≤ cap. used는 그 레슨에서 이미 낸 다른 탐침(실제 얼굴 등) 수."""
    n = max(0, int(lesson_len or 0))
    if n == 0 or cap <= 0 or cap >= 1:
        return 0
    total = int(cap * n / (1.0 - cap) + 1e-9)
    return max(0, total - max(0, int(used)))


# ── 문항 고르기 ──

def _phoneme_groups(lessons: Sequence[Dict]) -> Dict[str, int]:
    out = {}
    for l in lessons:
        for p in l.get("phonemes") or []:
            out.setdefault(p, l["viseme_id"])
    return out


def stage1_items(lessons: Sequence[Dict], seen: Iterable[str], rng: random.Random, n: int = PROBE_ITEMS) -> List[Dict]:
    """1단계 탐침: 처음 보는 음절 → 입모양 무리 4지선다. lessons는 curriculum.VISEME_LESSONS 모양(viseme_id·kind·phonemes·visibility).
    무리를 돌아가며 하나씩 고르므로 6개면 퀴즈 무리 여섯이 한 번씩 나온다."""
    quiz = [l for l in lessons if l.get("visibility") != "low"]
    groups = _phoneme_groups(lessons)
    seen = set(seen) | LABEL_SYLLABLES
    per_group = []
    for l in quiz:
        cands = []
        if l.get("kind") == "consonant":
            for c in l.get("phonemes") or []:
                for v in _CONSONANT_VOWELS:
                    s = compose(c, v)
                    if s:
                        cands.append((s, {l["viseme_id"], groups.get(v)}))
        else:
            for v in l.get("phonemes") or []:
                for c in _VOWEL_ONSETS:
                    s = compose(c, v)
                    if s:
                        cands.append((s, {l["viseme_id"], groups.get(c)}))
        cands = [c for c in cands if c[0] not in seen]
        rng.shuffle(cands)
        if cands:
            per_group.append((l, cands))
    rng.shuffle(per_group)
    out, used = [], set()
    i = 0
    while len(out) < n and per_group and i < n * 4:
        l, cands = per_group[i % len(per_group)]
        i += 1
        pick = next((c for c in cands if c[0] not in used), None)
        if pick is None:
            continue
        syl, inside = pick
        used.add(syl)
        others = [q for q in quiz if q["viseme_id"] not in inside]
        rng.shuffle(others)
        if len(others) < 3:
            continue
        opts = [l] + others[:3]
        rng.shuffle(opts)
        out.append({"kind": "viseme", "stimulus": syl, "target": str(l["viseme_id"]),
                    "options": [{"value": str(o["viseme_id"]), "label": o["name"], "viseme_id": o["viseme_id"]} for o in opts]})
    return out


def text_items(kind: str, pool: Sequence[str], seen: Iterable[str], rng: random.Random,
               options_fn: Callable[[str, List[str]], List[str]], n: int = PROBE_ITEMS) -> List[Dict]:
    """2단계(kind 'word')·3단계(kind 'sentence') 탐침: 본 적 없는 낱말·문장 → 4지선다. options_fn(정답, 이번 회차 정답들)은 오답 3개를 준다.
    오답이 3개가 안 되는 후보는 건너뛴다."""
    seen = set(seen)
    cands = [w for w in dict.fromkeys(pool) if w and w not in seen]
    rng.shuffle(cands)
    out, targets = [], []
    for w in cands:
        if len(out) >= n:
            break
        wrong = [o for o in (options_fn(w, targets) or []) if o != w][:3]
        if len(wrong) < 3 or len(set(wrong)) < 3:
            continue
        opts = [w] + wrong
        rng.shuffle(opts)
        targets.append(w)
        out.append({"kind": kind, "stimulus": w, "target": w, "options": [{"value": o, "label": o} for o in opts]})
    return out


# ── 분석(보고만 한다) ──

def estimate_p(k: int, n: int, floor: float = GUESS, grid: int = 400) -> Optional[float]:
    """n문항 중 k개 정답일 때 정답 확률의 사후 평균. 사전분포는 [floor, 1] 균등(4지선다라 0.25 아래는 없다고 본다)."""
    if n <= 0:
        return None
    num = den = 0.0
    for i in range(grid):
        p = floor + (1.0 - floor) * (i + 0.5) / grid
        like = (p ** k) * ((1.0 - p) ** (n - k))
        num += p * like
        den += like
    return num / den if den else None


def _group(stage: int) -> str:
    return "3" if int(stage) == 3 else "1-2"


def probe_report(rows: Sequence[Dict], min_answered: int = MIN_ANSWERED) -> Dict:
    """rows: {user_id, stage, wave, correct(None이면 아직 안 품)}. 단계 묶음(1-2, 3)·회차별로
    추정 정답 확률이 거짓 숙달 선 아래인 학습자 비율을 시뮬레이션 예측과 비교한다. 7일 회차의 within_margin이 판정 기준이다."""
    cells: Dict = {}
    for r in rows:
        if r.get("correct") is None:
            continue
        key = (r.get("user_id"), int(r["stage"]), int(r["wave"]))
        n, k = cells.get(key, (0, 0))
        cells[key] = (n + 1, k + (1 if r["correct"] else 0))
    est: Dict = {}
    for (uid, stage, wave), (n, k) in cells.items():
        if n < min_answered:
            continue
        line = FALSE_MASTERY_LINE.get(stage, 0.65)
        p = estimate_p(k, n)
        est.setdefault((_group(stage), wave), []).append(
            {"user_id": uid, "stage": stage, "p": p, "raw": k / n, "below": p < line, "raw_below": k / n < line})
    out = {"groups": {}, "min_answered": min_answered, "margin": DECISION_MARGIN}
    for grp in ("1-2", "3"):
        g = {"line": FALSE_MASTERY_LINE[1] if grp == "1-2" else FALSE_MASTERY_LINE[3],
             "sim_prediction": SIM_PREDICTION[grp], "waves": {}}
        for wave in WAVES:
            es = est.get((grp, wave), [])
            if not es:
                g["waves"][wave] = {"learners": 0, "share_below": None, "share_below_raw": None, "mean_p": None}
                continue
            share = sum(e["below"] for e in es) / len(es)
            g["waves"][wave] = {
                "learners": len(es),
                "share_below": round(share, 4),
                "share_below_raw": round(sum(e["raw_below"] for e in es) / len(es), 4),
                "mean_p": round(sum(e["p"] for e in es) / len(es), 4),
                "within_margin": share <= SIM_PREDICTION[grp] + DECISION_MARGIN,
            }
        # 망각: 1일·7일을 모두 푼 학습자의 추정값 차이(1일 − 7일) 평균
        by1 = {(e["user_id"], e["stage"]): e["p"] for e in est.get((grp, 1), [])}
        diffs = [by1[(e["user_id"], e["stage"])] - e["p"] for e in est.get((grp, 7), []) if (e["user_id"], e["stage"]) in by1]
        g["forgetting"] = {"learners": len(diffs), "mean_drop": round(sum(diffs) / len(diffs), 4) if diffs else None}
        w7 = g["waves"][7]
        g["decision"] = (None if not w7["learners"] else
                         ("유지" if w7["within_margin"] else "숙달 규칙 재검토를 결정 목록에 올림"))
        out["groups"][grp] = g
    return out
