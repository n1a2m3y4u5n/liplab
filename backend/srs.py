"""
간격 반복 스케줄러 — SM-2 경량판 (고도화 축 J 보강).

기존 SRS는 '정답이면 간격×2, 오답이면 내일'의 이진 방식이라, 3·4단계가 0~100 점수를
내는데도 pass/fail만 반영했고 항목별 난이도 차이를 담지 못했다. 여기서는 항목마다
난이도 계수(ease_factor)와 응답 품질(quality 0~5)을 두어, 잘 맞히는 항목은 빠르게
뜸해지고 자주 틀리는 항목(누수·leech)은 촘촘히 다시 나오게 한다.

**순수 함수** — DB·현재시각 같은 부수효과가 없어 결정론적이고 단위테스트가 쉽다.
간격(일수)만 돌려주고, 실제 due_date 계산·저장·삭제는 호출부(main.py)가 맡는다.
"""
from typing import Dict, Optional

EF_MIN = 1.3          # ease 하한 (SM-2 표준)
EF_START = 2.5        # 신규 항목 기본 ease
GRADUATE_INTERVAL = 60  # 이 간격(일) 이상이면 졸업 후보 — 큐에서 제거


def quality_from_score(score: float) -> int:
    """0~100 점수를 SM-2 품질등급 0~5로 사상. 60 미만은 실패(<3)로 간주한다."""
    if score >= 95:
        return 5
    if score >= 85:
        return 4
    if score >= 60:
        return 3
    if score >= 40:
        return 2
    if score >= 20:
        return 1
    return 0


def quality_from_correct(correct: bool) -> int:
    """이진 정오답(복습 큐 등)을 품질등급으로. 정답=4(무난한 성공), 오답=1(실패)."""
    return 4 if correct else 1


def schedule(
    quality: int,
    ease_factor: Optional[float] = None,
    interval_days: int = 0,
    repetitions: int = 0,
    lapses: int = 0,
) -> Dict:
    """
    SM-2 한 스텝. 현재 항목 상태 + 이번 응답 품질(0~5) → 다음 상태.

    반환: {ease_factor, interval_days, repetitions, lapses, graduated}
      - quality < 3(실패): 반복 초기화, 내일 재등장, ease 감소, lapse +1
      - quality >= 3(성공): 반복 1→1일, 2→6일, 이후 interval×ease. ease는 품질로 미세조정
      - graduated: 다음 간격이 GRADUATE_INTERVAL 이상이면 True (호출부가 큐에서 제거)
    """
    ef = ease_factor if ease_factor and ease_factor >= EF_MIN else EF_START
    q = max(0, min(5, int(quality)))

    if q < 3:
        repetitions = 0
        interval = 1
        lapses = (lapses or 0) + 1
        ef = max(EF_MIN, ef - 0.2)
    else:
        repetitions = (repetitions or 0) + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = max(1, round((interval_days or 1) * ef))
        # SM-2 ease 갱신식 — 품질이 높을수록 ease가 오르고, 낮을수록 내린다
        ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        ef = max(EF_MIN, ef)

    return {
        "ease_factor": round(ef, 3),
        "interval_days": int(interval),
        "repetitions": int(repetitions),
        "lapses": int(lapses),
        "graduated": interval >= GRADUATE_INTERVAL,
    }
