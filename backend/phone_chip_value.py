"""
음소 칩 값 보정(docs/phone-tail-2026-10.md). 기본은 끔이고 `DGOP_CHIP_VALUE=E1`일 때만 쓴다.

맞게 낸 소리의 약 7%가 칩에서 0점 근처로 떨어지는 꼬리가 있었다. 정렬기가 토큰을 한 프레임에 끼워 넣을 때 채점기가 그 소리를 바로 옆 프레임에
내는 경우가 그 일부다. E1은 칩 값을 max(구간 평균 분포의 목표 확률, [구간 시작 − 1, 구간 끝 + 1] 프레임마다의 목표 확률 최댓값)으로 둔다.
538 확인 21명(앱과 같은 끝 자르기)에서 꼬리 6.9 → 5.0%, 거짓 빨강 15.7 → 13.0%, 대치 변별 AUC 0.966 → 0.975였다.

- 문장 점수(dgop·naive)는 바꾸지 않는다. 칩 값은 음소의 `chip` 키로 따로 붙고, 화면 칩·약한 소리 코칭이 `chip`이 있으면 그것을 쓴다.
- E1일 때만 E1 칩 값으로 판정한 신뢰도 표(`data/phone_reliability_e1.json`)를 쓴다(phone_reliability.table_path).
"""
import os
from typing import Optional

MODES = ("E1",)


def mode() -> Optional[str]:
    m = (os.getenv("DGOP_CHIP_VALUE") or "").strip().upper()
    return m if m in MODES else None


def e1(frame_probs, token_id: int, start: int, end: int, span_value: float) -> float:
    """frame_probs: 채점기 프레임 확률(T × V, softmax 뒤, 텐서 또는 배열). span_value: 구간 평균 분포의 목표 확률(지금 naive)."""
    n = len(frame_probs)
    a, b = max(0, int(start) - 1), min(n - 1, int(end) + 1)
    best = max(float(frame_probs[t][token_id]) for t in range(a, b + 1))
    return round(max(0.0, min(1.0, max(float(span_value), best))), 4)
