"""말하기 소리 단서 S7: 문장 말 빠르기(초당 음절). numpy만 쓴다.

D-GOP 정렬 결과(음소 토큰마다 t0·t1초, dgop_acoustic.phone_confidences)와 같은 녹음의 16kHz 파형에서 계산한다.
측정과 판정은 docs/speak-visual-cues.md(사전 등록 2026-10-06 2bd6eba, 결과 7절).

- S7 말 빠르기: 확인 절반 608 감음신경성 대 538 정상 문장 AUC 0.863 [0.77, 0.957]으로 기준 0.70을 넘었다. 사람 유창성 평가(AI Hub
  71663)와의 상관은 아직 재지 않아 '조건부 채택'이고, 화면에는 '참고'를 붙인다. 목표 범위는 538 탐색 절반 문장의 10~90백분위다.
- S5 마찰(ㅅ 대 ㄷ)과 S6 기식(거센 대 예사)은 같은 측정에서 기준에 못 미쳐 넣지 않았다(같은 문서 7절). 측정한 지표 코드는
  liplab-lab/tools/speak_cues_measured_1006.py에 그대로 남아 있다(sha256 28b911ba…). 이 파일의 rate_pause는 그 코드와 같다.
"""
from typing import Dict, Optional, Sequence

import numpy as np

SR = 16000

PAUSE_MIN = 0.20      # 이보다 짧은 무음은 파열음 폐쇄 등으로 보고 쉼으로 세지 않는다
SILENCE_DB = 30.0     # 문장 구간 프레임 에너지 95백분위 − 30dB 아래를 무음으로 본다

# 538 정상 화자 문장(탐색 절반 900개)의 초당 음절 10·50·90백분위. 10백분위 아래면 '느린 편'으로 안내한다(사전 등록 4절).
RATE_P10, RATE_P50, RATE_P90 = 4.08, 5.27, 6.82
RATE_SLOW_MSG = "말 빠르기가 보통 낭독보다 느린 편이에요. 낱말 사이에서 쉬지 말고 한 숨에 이어 말해 보세요."


def _frames(x: np.ndarray, win: int, hop: int) -> np.ndarray:
    if len(x) < win:
        return np.zeros((0, win), dtype=np.float64)
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return x[idx].astype(np.float64)


def rate_pause(y: np.ndarray, phones: Sequence[Dict], sr: int = SR) -> Optional[Dict]:
    """정렬된 첫 토큰 시작 ~ 마지막 토큰 끝을 말한 구간(span)으로 보고 초당 음절·쉼 비율·쉼 뺀 초당 음절을 낸다.
    음절 수는 정렬된 모음 토큰(n:) 수. 정렬 토큰은 CTC라 1~2프레임짜리 점이어서 구간 끝은 마지막 음절 안쪽에 놓일 수 있다.
    쉼은 구간 안 25ms 창·10ms 간격 에너지가 95백분위 − 30dB 아래인 프레임이 200ms 이상 이어진 것. 구간 0.5초 미만이거나
    음절 3개 미만이면 None."""
    al = [p for p in (phones or []) if p.get("aligned") and p.get("t0") is not None and (p.get("token") or "") != "|"]
    n_syll = sum(1 for p in al if (p.get("token") or "").startswith("n:"))
    if not al or n_syll < 3:
        return None
    s0, s1 = float(al[0]["t0"]), float(al[-1]["t1"])
    span = s1 - s0
    if span < 0.5:
        return None
    hop, win = int(0.010 * sr), int(0.025 * sr)
    a, b = max(0, int(round(s0 * sr))), min(len(y), int(round(s1 * sr)))
    fr = _frames(np.asarray(y)[a:b], win, hop)
    pause = 0.0
    if len(fr):
        e = 10.0 * np.log10(np.maximum(((fr - fr.mean(axis=1, keepdims=True)) ** 2).sum(axis=1), 1e-12))
        sil = e < np.percentile(e, 95) - SILENCE_DB
        run = 0
        for s in list(sil) + [False]:
            if s:
                run += 1
            else:
                d = (run - 1) * hop / sr + win / sr if run else 0.0
                if d >= PAUSE_MIN:
                    pause += d
                run = 0
    pause = min(pause, span)
    speak = span - pause
    return {"n_syll": n_syll, "span": round(span, 3), "pause": round(pause, 3),
            "rate": round(n_syll / span, 3), "pause_ratio": round(pause / span, 4),
            "artic": round(n_syll / speak, 3) if speak > 0.2 else None}


def rate_cue(rp: Optional[Dict]) -> Optional[Dict]:
    """문장 단계 결과 화면의 지표 하나(말 빠르기). rate_pause 결과가 없으면 None.
    slow는 538 10백분위 아래인가. 빠른 쪽은 사전 등록에서 안내하지 않기로 했다(청각장애 화자의 차이는 느린 쪽이었다)."""
    if not rp or rp.get("rate") is None:
        return None
    v = float(rp["rate"])
    slow = v < RATE_P10
    return {"kind": "rate", "label": "말 빠르기", "value": round(v, 1), "unit": "음절/초",
            "range": [RATE_P10, RATE_P90], "typical": RATE_P50, "slow": slow,
            "message": RATE_SLOW_MSG if slow else None, "reference": True}
