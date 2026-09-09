"""
CTC 강제정렬 자체 구현 검증 — 축 B 후속 과제.

핵심은 **torchaudio와 프레임 단위로 같은 답을 내는가**다. 정렬 구간이 한 프레임만 밀려도
구간 평균 분포가 달라져 D-GOP 점수가 바뀌고, 그러면 A-3에서 잰 변별력과 A-4 보정 앵커를
다시 증명해야 한다. 그래서 무작위 입력 다수에 대해 두 구현의 라벨·점수를 직접 맞춰 본다.

torchaudio가 없는 환경(앱 런타임 등)에서는 대조 테스트만 건너뛰고 나머지는 그대로 돈다 —
자체 구현을 넣은 목적이 torchaudio 의존을 덜어내는 것이므로, 이 파일이 torchaudio를
요구하면 앞뒤가 맞지 않는다.

실행: PYTHONPATH=. python test_ctc_align.py
"""
import ctc_align as A

try:
    import torch
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

try:
    import torchaudio.functional as TAF
    HAS_TORCHAUDIO = hasattr(TAF, "forced_align")
except Exception:
    HAS_TORCHAUDIO = False


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _rand_lp(T, C, seed):
    torch.manual_seed(seed)
    return torch.log_softmax(torch.randn(T, C), dim=-1)


def test_basic_shape_and_coverage():
    """라벨은 프레임마다 하나, 목표 토큰은 순서대로 전부 나타나야 한다."""
    lp = _rand_lp(30, 6, 0)
    labels, scores = A.forced_align(lp, [1, 2, 3], blank=0)
    _ok(len(labels) == 30 and len(scores) == 30, "길이가 프레임 수와 같아야 함")
    seq = [l for i, l in enumerate(labels) if l != 0 and (i == 0 or labels[i - 1] != l)]
    _ok(seq == [1, 2, 3], f"비blank 라벨이 목표 순서대로 나와야 함 — 받음 {seq}")
    # scores[t]는 그 프레임에서 고른 라벨의 로그확률이어야 한다.
    for t, lab in enumerate(labels):
        _ok(abs(scores[t] - lp[t, lab].item()) < 1e-5, f"프레임 {t} 점수가 방출확률과 불일치")


def test_adjacent_duplicates_get_blank_between():
    """CTC 규약 — 같은 라벨이 연달으면 사이에 blank가 반드시 끼어야 구별된다."""
    lp = _rand_lp(20, 5, 3)
    labels, _ = A.forced_align(lp, [1, 1, 2], blank=0)
    runs = A.token_spans(labels, [1, 1, 2], blank=0)
    _ok(len(runs) == 3, f"구간이 3개여야 함 — 받음 {len(runs)}")
    _ok(runs[0]["end"] < runs[1]["start"] - 0, "첫 두 ㄱ 사이가 떨어져 있어야 함")
    between = labels[runs[0]["end"] + 1:runs[1]["start"]]
    _ok(len(between) >= 1 and all(b == 0 for b in between),
        f"중복 라벨 사이는 blank로만 채워져야 함 — 받음 {between}")


def test_spans_separate_repeated_tokens():
    """
    같은 토큰이 문장에 여러 번 나오면 각 출현이 **따로** 잡혀야 한다.
    labels를 토큰 id로 필터링하는 방식(옛 align_targets)은 여기서 뭉개진다 —
    한국어 자모열은 같은 자모가 거의 항상 여러 번 나오므로 실제로 늘 밟는 경로다.
    """
    lp = _rand_lp(40, 5, 7)
    targets = [1, 2, 1, 3, 1]
    labels, _ = A.forced_align(lp, targets, blank=0)
    spans = A.token_spans(labels, targets, blank=0)
    _ok(len(spans) == 5, f"출현 5개가 각각 잡혀야 함 — 받음 {len(spans)}")
    starts = [s["start"] for s in spans]
    _ok(starts == sorted(starts), f"구간이 시간 순이어야 함 — 받음 {starts}")
    for a, b in zip(spans, spans[1:]):
        _ok(a["end"] < b["start"], f"구간이 겹치면 안 됨 — {a} vs {b}")
    # id 필터링과 비교: 토큰 1은 3번 나오는데 필터링하면 한 구간으로 뭉쳐진다.
    naive = [i for i, l in enumerate(labels) if l == 1]
    tok1 = [s for s, t in zip(spans, targets) if t == 1]
    _ok(min(naive) == tok1[0]["start"] and max(naive) == tok1[-1]["end"],
        "필터링 방식은 첫 출현 시작~마지막 출현 끝을 한 구간으로 만든다(뭉개짐의 근거)")
    _ok(tok1[0]["end"] < tok1[-1]["start"], "자체 구현은 출현별로 분리한다")


def test_rejects_bad_input():
    lp = _rand_lp(10, 5, 1)
    for targets, why in [([], "빈 목표열"), ([0, 1], "blank가 목표열에 포함"),
                          ([1, 9], "vocab 범위 초과")]:
        try:
            A.forced_align(lp, targets, blank=0)
            _ok(False, f"{why} — 예외가 나야 함")
        except ValueError:
            pass
    # 프레임 부족 — 목표 6개(중복 2쌍 포함 → 최소 8프레임)에 5프레임
    try:
        A.forced_align(_rand_lp(5, 5, 2), [1, 1, 2, 2, 3, 3], blank=0)
        _ok(False, "프레임 부족 — 예외가 나야 함")
    except ValueError as e:
        _ok("최소" in str(e), f"필요 프레임 수를 알려줘야 함 — 받음 {e}")


def test_exact_length_path():
    """프레임 수가 최소치와 같으면 경로가 하나뿐 — blank 없이 딱 맞아야 한다."""
    labels, _ = A.forced_align(_rand_lp(3, 5, 4), [1, 2, 3], blank=0)
    _ok(labels == [1, 2, 3], f"유일 경로여야 함 — 받음 {labels}")


def test_matches_torchaudio():
    """
    무작위 입력 다수에서 torchaudio.functional.forced_align과 프레임 단위로 일치해야 한다.
    (torchaudio 미설치·API 제거 환경에서는 건너뛴다 — 그게 자체 구현을 넣은 이유다.)
    """
    if not HAS_TORCHAUDIO:
        print("    (torchaudio 없음 — 대조 테스트 건너뜀)")
        return
    cases = [
        (30, 6, [1, 2, 3]),
        (12, 5, [1, 1, 2]),                       # 인접 중복
        (40, 5, [1, 2, 1, 3, 1]),                 # 같은 토큰 반복 출현
        (3, 5, [1, 2, 3]),                        # 최소 길이(유일 경로)
        (200, 49, [1, 5, 5, 20, 3, 48, 3, 3]),    # 자모 vocab 크기·현실적 프레임 수
        (60, 49, list(range(1, 25))),             # 긴 목표열
    ]
    for seed, (T, C, targets) in enumerate(cases):
        lp = _rand_lp(T, C, 100 + seed)
        mine_lab, mine_sc = A.forced_align(lp, targets, blank=0)
        ta_lab, ta_sc = TAF.forced_align(
            lp.unsqueeze(0), torch.tensor([targets], dtype=torch.int64), blank=0)
        ta_lab = ta_lab[0].tolist()
        ta_sc = ta_sc[0].tolist()
        _ok(mine_lab == ta_lab,
            f"T={T} C={C} 목표{len(targets)}개 라벨 불일치\n  자체 {mine_lab}\n  torchaudio {ta_lab}")
        for t, (a, b) in enumerate(zip(mine_sc, ta_sc)):
            _ok(abs(a - b) < 1e-4, f"T={T} 프레임 {t} 점수 불일치 {a} vs {b}")
    print(f"    (torchaudio와 {len(cases)}개 사례 전부 일치)")


def test_matches_torchaudio_random_sweep():
    """형상을 무작위로 흔들어도 일치하는가 — 사례 6개로는 못 보는 경로를 훑는다."""
    if not HAS_TORCHAUDIO:
        print("    (torchaudio 없음 — 대조 테스트 건너뜀)")
        return
    import random
    rng = random.Random(0)
    for i in range(40):
        C = rng.randint(3, 50)
        L = rng.randint(1, 20)
        targets = [rng.randrange(1, C) for _ in range(L)]
        min_frames = L + sum(1 for a, b in zip(targets, targets[1:]) if a == b)
        T = min_frames + rng.randint(0, 30)
        lp = _rand_lp(T, C, 1000 + i)
        mine, _ = A.forced_align(lp, targets, blank=0)
        ta, _ = TAF.forced_align(lp.unsqueeze(0),
                                 torch.tensor([targets], dtype=torch.int64), blank=0)
        _ok(mine == ta[0].tolist(),
            f"sweep {i} (T={T} C={C} L={L}) 불일치\n  자체 {mine}\n  torchaudio {ta[0].tolist()}")
    print("    (무작위 40회 전부 일치)")


if __name__ == "__main__":
    if not HAS_TORCH:
        print("torch 미설치 — backend/requirements-ml.txt 설치 필요 (건너뜀)")
        raise SystemExit(0)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
