"""숙달 뒤 '빠른 말' 속도 단계(9/28). 엔진 1.0배는 실제 말보다 약 1.9배 느려(docs/engine-duration-check.md) 숙달이 곧 실제 대화
속도에서 읽는 능력은 아니다. 2단계를 숙달하면 1.25배를 열고, 한 단계에서 최근 12문항 중 10문항(0.8 이상)을 맞히면 다음 단계
(1.6배, 2.0배)를 연다. 2.0배는 538 문장 낭독의 음절 속도 근사다(엔진 초당 3.2음절, 낭독 6.0음절). 최근 12문항 중 10문항 규칙은
검증 없이 정한 값이다. 순수 함수라 DB 없이 테스트한다."""
from typing import Iterable, List, Tuple

LEVELS: List[float] = [1.25, 1.6, 2.0]
WINDOW = 12
NEED = 10
_TOL = 0.97   # 기록된 재생 속도(학습자 선택 × 적응 감속 비)의 반올림 여유


def unlocked(mastered: bool, recent: Iterable[Tuple[float, bool]]) -> int:
    """열린 단계 수(0이면 빠른 말 없음). recent는 최신순 (재생 속도, 정답) 기록."""
    if not mastered:
        return 0
    rows = [(float(s), bool(c)) for s, c in recent if s is not None]
    n = 1
    while n < len(LEVELS):
        at = [c for s, c in rows if s >= LEVELS[n - 1] * _TOL][:WINDOW]
        if len(at) < WINDOW or sum(at) < NEED:
            break
        n += 1
    return n
