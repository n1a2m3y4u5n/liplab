"""
레슨별 정신적 노력 한 문항(종합 계획 C14, idea-sweep 나23).

레슨이 끝나면 Paas(1992) 9점 정신적 노력 문항을 쉬운 말과 그림 척도로 한 번 묻는다. 답하지 않아도 된다(건너뛰기).
레슨 세션마다 한 행(`lesson_efforts` 표, 화면이 만든 세션 id로 구분)을 남긴다. **적응 규칙은 아직 없다.** 기록과 분석만 한다.
나23 판정 기준: 응답률이 80% 미만이면 묻는 방식을 다시 설계하고, 노력 7 이상 레슨 뒤 다음 회차 복귀의 오즈비 구간이 1보다 작을 때만
상한 규칙(다음 레슨 문항 수 줄이기 등)을 검토한다(이 모듈은 응답률·단계별 노력만 낸다).
근거: Paas 1992 https://research-portal.uu.nl/files/19196510/cognitive.pdf

응답 종류(response): 'answered'(점수를 고름), 'skipped'(건너뛰기를 누름), 'left'(답하지 않고 화면을 떠남).
같은 세션에 여러 번 오면 answered > skipped > left 순으로 남긴다(개발 모드에서 화면이 두 번 붙었다 떨어져도 답이 지워지지 않게).

**순수 함수**만 둔다.
"""
from statistics import median
from typing import Dict, Optional, Sequence

SCALE_MIN, SCALE_MAX = 1, 9
HIGH_EFFORT = 7                       # 나23의 '노력이 높은 레슨' 기준
RESPONSE_RATE_TARGET = 0.8
RESPONSES = ("answered", "skipped", "left")
_RANK = {"left": 0, "skipped": 1, "answered": 2}
# 화면 문구와 같은 기준점(frontend/src/components/EffortCheck.jsx). Paas 원문의 'very, very low ~ very, very high mental effort'를 쉬운 말로
ANCHORS = {1: "아주 아주 조금", 3: "조금", 5: "보통", 7: "많이", 9: "아주 아주 많이"}
LESSON_KINDS = ("viseme", "word", "sentence", "closure", "review")


def clean_rating(value) -> Optional[int]:
    """1~9 정수만 받는다. 그 밖은 None."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if SCALE_MIN <= v <= SCALE_MAX and str(value).strip().lstrip("+").isdigit() else None


def clean_response(response, rating) -> str:
    if rating is not None:
        return "answered"
    return response if response in ("skipped", "left") else "skipped"


def merge(old_response: Optional[str], new_response: str) -> bool:
    """새 응답으로 덮어쓸지. answered > skipped > left, 같은 등급이면 덮어쓴다(점수를 바꾼 경우)."""
    if old_response is None:
        return True
    return _RANK.get(new_response, 0) >= _RANK.get(old_response, 0)


def report(rows: Sequence[Dict]) -> Dict:
    """rows: {stage, lesson_kind, response, rating}. 전체 응답률과 단계별(없으면 레슨 종류별) 노력 요약."""
    n = len(rows)
    answered = [r for r in rows if r.get("response") == "answered" and r.get("rating") is not None]
    out = {"sessions": n, "answered": len(answered),
           "skipped": sum(1 for r in rows if r.get("response") == "skipped"),
           "left": sum(1 for r in rows if r.get("response") == "left"),
           "response_rate": round(len(answered) / n, 4) if n else None,
           "target": RESPONSE_RATE_TARGET}
    out["meets_target"] = None if not n else out["response_rate"] >= RESPONSE_RATE_TARGET
    by: Dict = {}
    for r in rows:
        key = str(r.get("stage")) if r.get("stage") is not None else (r.get("lesson_kind") or "기타")
        by.setdefault(key, []).append(r)
    stages = {}
    for key, rs in sorted(by.items()):
        vals = [int(r["rating"]) for r in rs if r.get("response") == "answered" and r.get("rating") is not None]
        stages[key] = {
            "sessions": len(rs), "answered": len(vals),
            "response_rate": round(len(vals) / len(rs), 4) if rs else None,
            "mean": round(sum(vals) / len(vals), 3) if vals else None,
            "median": median(vals) if vals else None,
            "high_share": round(sum(v >= HIGH_EFFORT for v in vals) / len(vals), 4) if vals else None,
            "distribution": {str(k): sum(1 for v in vals if v == k) for k in range(SCALE_MIN, SCALE_MAX + 1)},
        }
    out["by_stage"] = stages
    return out
