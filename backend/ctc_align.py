"""
CTC 강제정렬(Viterbi) 자체 구현 — 축 B 후속 과제.

`dgop_acoustic.align_targets`는 지금까지 `torchaudio.functional.forced_align`에 전적으로
의존했다. 2026-09-08 RunPod(torchaudio 2.8.0)에서 이 API의 deprecation 경고를 확인해
`requirements-ml.txt`에 `torchaudio<2.9.0` 상한을 걸어 뒀는데, 상한은 축 A·B 전체를
낡은 torch에 묶어 두는 비용을 계속 물린다(torchcodec·CUDA 버전까지 연쇄로 묶인다).

알고리즘 자체는 단순한 Viterbi다. 자체 구현하면 상한을 풀 수 있고, 정렬 때문에 무거운
torchaudio를 깔 필요도 없어진다(모델 추론은 transformers, 오디오 디코딩은 이미
faster-whisper·soundfile 경로를 쓴다).

── 정렬 격자 ────────────────────────────────────────────────────────────────
목표 토큰열 y(길이 L)를 blank로 감싼 확장열 ext = [b, y0, b, y1, …, y(L-1), b](길이 2L+1)
위에서 최적 경로를 찾는다. 프레임마다 허용되는 이동은 셋뿐이다:

  · 머무름  s → s        (같은 상태를 여러 프레임 유지 — 음소가 길게 발음된 경우)
  · 전진    s-1 → s
  · 건너뜀  s-2 → s      s가 비blank이고 ext[s-2] != ext[s]일 때만

'건너뜀'에 조건이 붙는 이유: CTC는 같은 라벨이 연달아 오면 반드시 그 사이에 blank가
있어야 둘을 구별한다('ㄱㄱ' vs 길게 늘인 'ㄱ'). 그래서 ext[s-2] == ext[s]인 경우에는
사이의 blank(s-1)를 건너뛸 수 없다.

torchaudio와 **동일한 출력**을 내야 한다 — 정렬 구간이 바뀌면 D-GOP 점수가 바뀌고,
A-3에서 잰 변별력·A-4 보정 앵커를 다시 증명해야 한다. `test_ctc_align.py`가 torchaudio가
설치된 환경에서 무작위 입력으로 두 구현의 프레임별 라벨·점수 일치를 직접 검증한다
(torchaudio가 없으면 그 테스트만 건너뛴다).
"""
from typing import List, Sequence, Tuple

try:
    import torch
    HAS_TORCH = True
except Exception:  # torch 미설치 — 앱 런타임에서는 이 모듈을 부르지 않는다
    HAS_TORCH = False

_NEG_INF = float("-inf")

# 역추적용 이동 코드. 격자 크기가 T×(2L+1)이라 int8로 충분하다.
_STAY, _ADVANCE, _SKIP = 0, 1, 2


def forced_align(log_probs, targets: Sequence[int], blank: int = 0) -> Tuple[List[int], List[float]]:
    """
    프레임별 로그확률 + 목표 토큰열 → 프레임별 정렬 라벨.

    log_probs: (T, C) 텐서 — 프레임 T개, vocab C개의 **로그**확률
    targets:   길이 L의 토큰 id 열 (blank는 들어올 수 없다)
    반환: (labels, scores) — 둘 다 길이 T의 리스트.
          labels[t]는 그 프레임에 놓인 토큰 id(blank 구간은 blank id),
          scores[t]는 그 선택의 로그확률. torchaudio.functional.forced_align과 같은 규약.

    T가 정렬에 필요한 최소 프레임 수보다 짧으면 ValueError를 낸다 — 조용히 엉뚱한 구간을
    돌려주면 그 점수가 그대로 학습자에게 간다.
    """
    if not HAS_TORCH:
        raise RuntimeError("torch 미설치 — backend/requirements-ml.txt 설치 필요")

    tgt = [int(t) for t in targets]
    if not tgt:
        raise ValueError("목표 토큰열이 비어 있습니다")
    if blank in tgt:
        raise ValueError(f"목표 토큰열에 blank(id {blank})가 들어 있습니다 — 정렬할 수 없습니다")

    lp = log_probs
    if lp.dim() != 2:
        raise ValueError(f"log_probs는 (T, C) 2차원이어야 합니다 — 받은 형상 {tuple(lp.shape)}")
    T, C = lp.shape
    for t in tgt + [blank]:
        if not 0 <= t < C:
            raise ValueError(f"토큰 id {t}가 vocab 범위(0~{C - 1})를 벗어납니다")

    # 확장열 ext와 '건너뜀 허용' 마스크를 한 번만 만든다.
    ext: List[int] = [blank]
    for tok in tgt:
        ext.extend((tok, blank))
    S = len(ext)                                     # 2L+1

    # 최소 필요 프레임 수 = L + (인접 중복 라벨 사이에 강제로 끼는 blank 수)
    min_frames = len(tgt) + sum(1 for a, b in zip(tgt, tgt[1:]) if a == b)
    if T < min_frames:
        raise ValueError(
            f"프레임이 부족해 정렬할 수 없습니다 — 프레임 {T}개, 최소 {min_frames}개 필요"
            f"(목표 토큰 {len(tgt)}개, 인접 중복 {min_frames - len(tgt)}개). "
            "녹음이 너무 짧거나 목표 문장이 너무 깁니다."
        )

    device = lp.device
    ext_idx = torch.tensor(ext, dtype=torch.long, device=device)
    # ext[s]가 비blank이고 ext[s-2] != ext[s]인 s에서만 건너뜀을 허용한다.
    can_skip = torch.zeros(S, dtype=torch.bool, device=device)
    for s in range(2, S):
        if ext[s] != blank and ext[s - 2] != ext[s]:
            can_skip[s] = True

    emit = lp[:, ext_idx]                            # (T, S) — 상태별 방출 로그확률

    # ── 전방 Viterbi ──
    alpha = torch.full((S,), _NEG_INF, dtype=torch.float32, device=device)
    alpha[0] = emit[0, 0]                            # 첫 프레임은 blank 또는 y0에서만 시작
    if S > 1:
        alpha[1] = emit[0, 1]
    back = torch.zeros((T, S), dtype=torch.int8, device=device)

    for t in range(1, T):
        stay = alpha
        adv = torch.cat([torch.full((1,), _NEG_INF, device=device), alpha[:-1]])
        skip = torch.cat([torch.full((2,), _NEG_INF, device=device), alpha[:-2]])
        skip = torch.where(can_skip, skip, torch.full_like(skip, _NEG_INF))
        # 동점일 때는 머무름 → 전진 → 건너뜀 순으로 고른다(torchaudio와 같은 우선순위).
        cand = torch.stack([stay, adv, skip])        # (3, S)
        best, move = cand.max(dim=0)
        alpha = best + emit[t]
        back[t] = move.to(torch.int8)

    # ── 역추적 ──
    # 마지막 프레임은 마지막 라벨(S-2) 또는 그 뒤 blank(S-1)에서 끝난다.
    if S > 1 and alpha[S - 2] > alpha[S - 1]:
        s = S - 2
    else:
        s = S - 1
    if alpha[s] == _NEG_INF:
        raise ValueError("유효한 정렬 경로가 없습니다 — 목표 토큰열과 프레임 수를 확인하세요")

    moves = back.tolist()
    labels = [0] * T
    scores = [0.0] * T
    emit_rows = emit.tolist()
    for t in range(T - 1, -1, -1):
        labels[t] = ext[s]
        scores[t] = emit_rows[t][s]
        if t > 0:
            s -= (0, 1, 2)[moves[t][s]]
    return labels, scores


def token_spans(labels: Sequence[int], targets: Sequence[int], blank: int = 0) -> List[dict]:
    """
    프레임별 정렬 라벨 → 목표 토큰 **각 출현**의 프레임 구간 [start, end](포함).

    labels를 토큰 id로 필터링하면 안 된다 — 같은 토큰이 문장에 여러 번 나오면
    (한국어 자모는 거의 항상 그렇다) 모든 출현이 한 구간으로 뭉쳐진다. blank로 끊어지는
    연속 구간(run)을 순서대로 목표열에 맞춰 배정한다.
    """
    runs: List[List[int]] = []                       # [토큰, 시작, 끝]
    for t, lab in enumerate(labels):
        if lab == blank:
            continue
        if runs and runs[-1][0] == lab and runs[-1][2] == t - 1:
            runs[-1][2] = t                          # 같은 토큰이 이어지는 중
        else:
            runs.append([lab, t, t])
    if len(runs) != len(targets):
        raise ValueError(
            f"정렬 구간 수가 목표 토큰 수와 다릅니다({len(runs)} vs {len(targets)}) — "
            "정렬 결과가 손상되었습니다"
        )
    return [{"start": r[1], "end": r[2]} for r in runs]
