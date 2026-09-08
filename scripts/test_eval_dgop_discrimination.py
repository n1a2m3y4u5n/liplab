"""
변별력 평가 지표 검증 — 축 A A-3.

spearman·auc는 모델·데이터 의존이 없는 순수 함수라 결정론적으로 검증할 수 있다
(dgop.py 테스트와 같은 원칙). 지표가 틀리면 학습이 성공했는지 실패했는지를 잘못
판정하게 되므로, 실제 평가를 돌리기 전에 여기가 통과해야 한다.

실행: python3 scripts/test_eval_dgop_discrimination.py
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
_spec = importlib.util.spec_from_file_location(
    "eval_dgop_discrimination", os.path.join(_HERE, "eval_dgop_discrimination.py"))
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _close(a, b, tol=1e-4):
    return abs(a - b) < tol


def test_spearman_monotonic():
    _ok(_close(E.spearman([0, 1, 2, 3, 4], [10, 20, 30, 40, 50]), 1.0), "완전 단조증가 → 1.0")
    _ok(_close(E.spearman([0, 1, 2, 3, 4], [50, 40, 30, 20, 10]), -1.0), "완전 단조감소 → -1.0")
    # 선형이 아니어도 순위만 맞으면 1.0 (순위상관의 요점)
    _ok(_close(E.spearman([0, 1, 2, 3], [1, 100, 101, 9999]), 1.0), "비선형 단조도 1.0")


def test_spearman_ties_and_degenerate():
    # x에 동점이 없고 y에만 있으면 1.0에 닿을 수 없다. 4/sqrt(20) = 0.894427…
    _ok(_close(E.spearman([0, 1, 2, 3], [5, 5, 9, 9]), 0.894427), "동점 보정이 반영돼야 함")
    _ok(E.spearman([0, 1, 2], [7, 7, 7]) == 0.0, "상수열은 정의되지 않아 0.0")
    _ok(E.spearman([1, 1, 1], [1, 2, 3]) == 0.0, "양쪽 중 하나가 상수여도 0.0")


def test_auc_separation():
    _ok(E.auc([9, 8, 7], [3, 2, 1]) == 1.0, "완전 분리 → 1.0")
    _ok(E.auc([1, 2, 3], [7, 8, 9]) == 0.0, "완전 역분리 → 0.0")
    _ok(E.auc([5, 5], [5, 5]) == 0.5, "동일 분포(전부 동점) → 0.5")
    _ok(E.auc([3, 4], [2, 5]) == 0.5, "부분 겹침 → 0.5")
    _ok(E.auc([], [1, 2]) != E.auc([], [1, 2]), "빈 입력은 nan (자기 자신과 다름)")


def test_targets_are_stated():
    """합격선이 코드에 명시돼 있어야 판정이 재현된다."""
    _ok(E.TARGET_MONOTONICITY == 0.90, "단조성 목표 0.90")
    _ok(E.TARGET_AUC == 0.85, "분리도 목표 0.85")
    _ok(E.TARGET_ALIGNED == 0.95, "정렬 견고성 목표 0.95")
    _ok(E.SEVERITIES == [0, 1, 2, 3, 4], "severity 0(원본)이 포함돼야 비교가 성립")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
