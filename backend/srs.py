"""
간격 반복 스케줄러 — SM-2 경량판 (고도화 축 J 보강).

기존 SRS는 '정답이면 간격×2, 오답이면 내일'의 이진 방식이라, 3·4단계가 0~100 점수를
내는데도 pass/fail만 반영했고 항목별 난이도 차이를 담지 못했다. 여기서는 항목마다
난이도 계수(ease_factor)와 응답 품질(quality 0~5)을 두어, 잘 맞히는 항목은 빠르게
뜸해지고 자주 틀리는 항목(누수·leech)은 촘촘히 다시 나오게 한다.

**순수 함수** — DB·현재시각 같은 부수효과가 없어 결정론적이고 단위테스트가 쉽다.
간격(일수)만 돌려주고, 실제 due_date 계산·저장·삭제는 호출부(main.py)가 맡는다.

찍기·감속 보정(9/29, `quality_for_answer`): 복습 답(/api/review/answer)은 예전에 정오만 받아 정답이면 모두 품질 4였다.
4지선다는 몰라도 25%를 맞히고, 느리게(1.0배 미만) 본 정답은 자연 속도에서 읽는다는 근거가 약한데 간격은 똑같이 늘었다.
이제 답 방식(answer_mode)과 재생 속도(speed)를 받아, 보기를 고른 정답과 1.0배 미만에서 얻은 정답은 품질 3(어렵게 맞힘),
자연 속도(1.0배 이상)에서 직접 입력한 정답만 4로 둔다. 오답은 그대로 1이다. 품질 3은 반복 간격을 끊지 않고 ease만
0.14 내린다. 첫 실패로 등록된 항목(ease 2.3)이 연달아 맞히면 간격이 4는 1·6·14·32·74일(다섯 번째에 졸업, 그 전까지 53일),
3은 1·6·12·23·40·64일(여섯 번째에 졸업, 82일)이다.
이 값은 자료 없이 정한 원칙적인 작은 변경이다. 시뮬레이션이나 실측으로 고른 값이 아니다. 복습 기록이 쌓이면 다음 예정일에
다시 맞힌 비율(답 방식·속도별 다음 복습 통과율)로 품질 3·4가 기억 유지를 제대로 가르는지 다시 본다.
문장 레슨(/api/progress)에서 예정된 문장을 다시 만난 답은 점수 등급을 쓰되, 4지선다 합격(정확 일치 100점)은 같은 이유로
품질 3을 넘지 않게 한다(main._sr_touch max_quality). 레슨 문장의 속도는 적용하지 않는다. 약한 입모양 적응 감속이 거의
모든 문장에 걸려(docs/mastery-ewma.md 9절) 속도로 가르면 사실상 모든 문장이 품질 3이 되기 때문이다.
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


def quality_for_answer(correct: bool, answer_mode: Optional[str] = None, speed: Optional[float] = None) -> int:
    """복습 답의 품질등급. 오답 1, 보기를 고른 정답·1.0배 미만 정답 3, 자연 속도에서 직접 입력한 정답 4(머리말 참고).
    answer_mode·speed를 보내지 않은 옛 화면은 예전처럼 정답 4다."""
    if not correct:
        return quality_from_correct(False)
    if answer_mode == "choice":
        return 3
    try:
        slowed = speed is not None and float(speed) < 0.999
    except (TypeError, ValueError):
        slowed = False
    return 3 if slowed else quality_from_correct(True)


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
