"""
D-GOP 음향 백본 — 고도화 축 B.

dgop.py는 '음소 사후확률 분포'를 입력받는 순수 함수만 담고 있다(모델 비의존, 결정론적
테스트 가능). 이 모듈이 그 분포를 실제로 공급한다: CTC 음향모델로 프레임별 로그확률을
얻고, CTC 강제정렬(ctc_align — 자체 Viterbi 구현)로 목표 음소열을 프레임 구간에 정렬한 뒤,
구간별 확률분포를 dgop.dgop_phone에 넘긴다.

torch·transformers는 requirements-ml.txt 전용 의존성이다(앱 런타임/배포에는
불필요 — content_rules.py의 wordfreq 분리와 같은 원칙). 미설치 환경에서는 HAS_ACOUSTIC=False로
두고 이 모듈의 실행 함수를 호출하지 않는다.

강제정렬·구간 집계(align_targets, span_distribution)는 CTC vocab에만 의존하는 일반 로직이라
어떤 체크포인트에도 그대로 적용된다 — 실제 모델 다운로드 없이 합성 log_probs로 결정론적
테스트가 가능하다(test_dgop_acoustic.py).

개발일지가 원래 언급한 kresnik/wav2vec2-xlsr-korean은 Hugging Face Hub API에서 401을 반환해
접근 불가 확인(2026-09-07). 같은 저자의 kresnik/wav2vec2-large-xlsr-korean은 공개(월 100만+
다운로드)라 이를 기본값으로 쓴다. 다만 이 체크포인트의 CTC vocab은 **한글 음절 단위**(1,205개
토큰, 자모 아님)라, dgop.py가 그리는 "음소별(초성/중성/종성) D-GOP"를 얻으려면 음절 신뢰도를
자모로 재분해하는 단계가 축 B 후속 작업으로 필요하다 — 지금은 음절 단위 정렬·신뢰도까지만
제공한다. 또한 이 체크포인트는 **정상 발화로 학습**되었으므로, 축 A가 농인 발화로 미세조정한
버전이 나오기 전까지는 D-GOP의 불확실성 보정에 더 의존하게 된다(계획서가 정확히 지적한 문제).
"""
import json
import os
from typing import Dict, List, Optional, Sequence

import dgop as _dgop

try:
    import torch
    from transformers import AutoModelForCTC, AutoProcessor
    HAS_ACOUSTIC = True
except Exception:  # torch/transformers 미설치
    HAS_ACOUSTIC = False

# 공개 확인된 한국어 CTC 체크포인트(음절 단위 vocab). 축 A가 농인 발화로 미세조정한
# 버전이 나오면 이 상수만 바꾸면 된다 — 정렬·집계 로직은 vocab에 의존하지 않는다.
DEFAULT_MODEL_ID = "kresnik/wav2vec2-large-xlsr-korean"

def resolve_device() -> str:
    """
    추론 장치. GPU가 있으면 쓴다 — wav2vec2-large 순전파는 CPU에서 수십 배 느려,
    A-3 변별력 평가(발화 40건 × severity 5 × 모델 2 = 400회 순전파)가 CPU로는
    현실적이지 않다. DGOP_DEVICE로 강제할 수 있다(예: 배포 서버에서 "cpu").
    """
    forced = os.getenv("DGOP_DEVICE")
    if forced:
        return forced
    if HAS_ACOUSTIC and torch.cuda.is_available():
        return "cuda"
    return "cpu"


# 표시용 점수 보정 앵커 파일. 없으면 dgop.DEFAULT_CALIBRATION(축 A A-3 실측)을 쓴다.
DEFAULT_CALIBRATION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "data", "dgop_calibration.json")
# 공개 kresnik 모델을 정렬기·채점기로 쓸 때의 앵커(A-7, 538 blank 수정판). 기본 파일은 팀원 채점기(A-4)용이다.
KRESNIK_CALIBRATION_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "data", "dgop_calibration_kresnik.json")
_calibration_cache: Dict[str, Dict] = {}


def calibration_path_for(scorer_id: Optional[str]) -> str:
    """채점기에 맞는 앵커 파일. DGOP_CALIBRATION이 있으면 그것, 채점기가 공개 kresnik 모델이면 그 모델로 맞춘 앵커,
    아니면 기본 파일. 원점수 눈금은 채점기마다 달라 다른 모델의 앵커를 쓰면 표시 점수가 어긋난다."""
    env = os.getenv("DGOP_CALIBRATION")
    if env:
        return env
    if scorer_id == DEFAULT_MODEL_ID and os.path.exists(KRESNIK_CALIBRATION_PATH):
        return KRESNIK_CALIBRATION_PATH
    return DEFAULT_CALIBRATION_PATH


def load_calibration(path: Optional[str] = None) -> Dict:
    """
    표시용 점수 보정 앵커를 읽는다. 우선순위: 인자 path > DGOP_CALIBRATION 환경변수 >
    backend/data/dgop_calibration.json > dgop.DEFAULT_CALIBRATION(내장 기본값).

    체크포인트를 바꾸면 원점수 스케일이 함께 바뀌므로 그 모델로 다시 맞춘 앵커가 필요하다
    (scripts/fit_dgop_calibration.py). 파일이 깨졌거나 앵커가 없으면 조용히 내장 기본값으로
    떨어진다 — 보정 파일 하나 때문에 채점 자체가 죽지 않게 한다.
    """
    src = path or os.getenv("DGOP_CALIBRATION") or DEFAULT_CALIBRATION_PATH
    if src in _calibration_cache:
        return _calibration_cache[src]
    cal = _dgop.DEFAULT_CALIBRATION
    if os.path.exists(src):
        try:
            with open(src, encoding="utf-8") as f:
                loaded = json.load(f)
            if loaded.get("anchors"):
                cal = loaded
            else:
                print(f"[WARN] 보정 파일에 anchors가 없습니다: {src} — 내장 기본값 사용")
        except Exception as e:
            print(f"[WARN] 보정 파일을 읽지 못했습니다({src}): {e} — 내장 기본값 사용")
    _calibration_cache[src] = cal
    return cal


def _load(model_id: str = DEFAULT_MODEL_ID, device: str = None):
    """정렬기·채점기 (processor, model). 공용 백본 서비스(A-9)가 한 번만 올려 두고 나눠 준다."""
    if not HAS_ACOUSTIC:
        raise RuntimeError("torch/transformers 미설치 — backend/requirements-ml.txt 설치 필요")
    import backbone_service as _bb
    return _bb.load(model_id, "ctc", device or resolve_device())


def ctc_outputs(waveform, sample_rate: int, model_id: str = DEFAULT_MODEL_ID):
    """
    파형 → (log_probs, logits, vocab). 전부 CPU 텐서.

    **raw logit을 함께 돌려주는 이유**: softmax는 로짓의 절대 크기를 정규화로 지운다.
    OOD 입력(병리 발화)에서는 '모든 로짓이 낮다'는 그 정보가 과신을 드러내는 신호이고,
    Yeo et al. (Interspeech 2023)에서 베이스라인을 이긴 유일한 변형(MaxLogit)이 바로 그
    정보를 쓴다. 로짓을 버리면 그 계열을 아예 비교할 수 없다(gop_variants 참고).
    """
    device = resolve_device()
    processor, model = _load(model_id, device=device)
    inputs = processor(waveform, sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values.to(device)).logits[0]  # (T, C)
    # 순전파만 GPU에서 하고 결과는 CPU로 되돌린다 — 이후 강제정렬·구간 집계는
    # 순수 함수라 장치에 얽매이지 않아야 테스트(합성 텐서)와 배포가 함께 단순해진다.
    logits = logits.cpu()
    return torch.log_softmax(logits, dim=-1), logits, processor.tokenizer.get_vocab()


def ctc_log_probs(waveform, sample_rate: int, model_id: str = DEFAULT_MODEL_ID):
    """
    파형(1D 배열, 16kHz 권장)을 CTC 모델에 통과시켜 프레임별 로그확률과 vocab을 얻는다.
    실제 모델 다운로드·추론이 필요해 유닛테스트 대상이 아니다(scripts/check_ml_env.py로 점검).
    반환: (log_probs: Tensor[T, C], vocab: Dict[token, id])

    로짓까지 필요하면 ctc_outputs를 쓴다.
    """
    log_probs, _logits, vocab = ctc_outputs(waveform, sample_rate, model_id)
    return log_probs, vocab


# CTC blank의 이름은 체크포인트마다 다르다(자모 vocab·fairseq 계열은 "<pad>", kresnik 음절 vocab은 "[PAD]").
BLANK_CANDIDATES = ("<pad>", "[PAD]", "<blank>", "[BLANK]")
# 발음 채점 대상이 아닌 특수토큰(blank·unk·문장 경계·어절 경계). 자모 vocab의 판정(jamo_vocab.SPECIAL)에 더해 쓴다.
SPECIAL_TOKENS = frozenset(("<pad>", "[PAD]", "<unk>", "[UNK]", "<s>", "</s>", "|", "<blank>", "[BLANK]"))


def blank_id_for(vocab: Dict[str, int], blank_token: Optional[str] = None) -> int:
    """CTC blank의 id. blank_token을 주면 그 이름만, 없으면 BLANK_CANDIDATES를 차례로 찾는다.

    ⚠️ 2026-09-24 수정 — 예전에는 blank_token 기본값 "<pad>"를 vocab.get(…, 0)으로 찾았다. kresnik 음절 vocab에는
    "<pad>"가 없고(blank는 "[PAD]", id 1204) id 0은 음절 '볍'이라, 강제정렬이 '볍'을 blank로 두고 진짜 blank 프레임을
    목표 음절에 나눠 붙였다. 구간이 넓게 퍼져 구간 평균 분포의 목표 확률이 묽어지고, 깨끗한 발화의 원점수가
    낮게 나왔다(재측정은 GPU 세션 3). 이제는 찾지 못하면 조용히 0을 쓰지 않고 KeyError를 낸다."""
    names = (blank_token,) if blank_token else BLANK_CANDIDATES
    for name in names:
        if name in vocab:
            return int(vocab[name])
    raise KeyError(f"CTC blank 토큰을 vocab에서 찾지 못함: {list(names)}")


def align_targets(log_probs, vocab: Dict[str, int], target_tokens: Sequence[str],
                   blank_token: Optional[str] = None) -> List[Dict]:
    """
    CTC 강제정렬로 target_tokens **각 출현**이 놓인 프레임 구간(시작·끝, 포함)을 찾는다.
    log_probs·vocab에만 의존하는 순수 함수 — 합성 log_probs로 모델 없이 테스트 가능.
    vocab에 없는 토큰이 있으면 KeyError를 낸다.

    정렬은 ctc_align(자체 Viterbi 구현)이 한다. torchaudio.functional.forced_align과
    프레임 단위로 같은 답을 내는 것을 test_ctc_align이 무작위 입력으로 검증한다.

    ⚠️ 2026-09-09 수정 — 이전 구현은 정렬 경로를 **토큰 id로 필터링**해서
    `start=min(해당 id 프레임), end=max(...)`로 구간을 잡았다. 같은 토큰이 문장에 여러 번
    나오면 모든 출현이 '첫 출현 시작 ~ 마지막 출현 끝'이라는 하나의 거대한 구간으로 뭉개진다.
    자모 vocab은 49토큰인데 Zeroth 라벨은 중앙값 103토큰이라 **중복은 예외가 아니라 기본**이다
    (실측: 짧은 문장에서도 토큰의 20~57%가 중복 출현). 뭉개진 구간의 평균 분포는 평평해져
    confidence가 0에 수렴하고, 그 음소의 D-GOP가 통째로 깎인다 —
    A-3이 "원인 미상"으로 남긴 한계 ②(깨끗한 발화 9.51/100)의 실제 원인이다.
    """
    if not HAS_ACOUSTIC:
        raise RuntimeError("torch 미설치")
    import ctc_align

    blank_id = blank_id_for(vocab, blank_token)
    missing = [t for t in target_tokens if t not in vocab]
    if missing:
        raise KeyError(f"vocab에 없는 토큰: {missing}")
    target_ids = [vocab[t] for t in target_tokens]

    labels, _scores = ctc_align.forced_align(log_probs, target_ids, blank=blank_id)
    spans = ctc_align.token_spans(labels, target_ids, blank=blank_id)
    return [{"token": tok, "start": sp["start"], "end": sp["end"]}
            for tok, sp in zip(target_tokens, spans)]


def span_distribution(log_probs, start, end) -> List[float]:
    """구간 [start, end](프레임, 포함)의 평균 확률분포. start가 None이면 빈 리스트."""
    if start is None:
        return []
    probs = torch.softmax(log_probs[start:end + 1], dim=-1)
    return probs.mean(dim=0).tolist()


class SharedFeatureEncoder(torch.nn.Module if HAS_ACOUSTIC else object):
    """정렬기·채점기의 CNN 특징 추출부를 한 벌로 두고, 바로 전과 같은 입력이면 결과를 다시 쓴다(9/27).
    정렬기는 채점기에서 이어받아 미세조정할 때 특징 추출부를 고정해 두 모델의 이 부분 가중치가 비트 단위로 같다(28개 텐서).
    그래서 한 번만 계산해도 결과가 같고, 채점 한 번에 CNN 한 번(모델 순전파의 약 18%, 맥 2스레드)을 아낀다. 모델 순전파는
    그대로 쓰고 이 모듈만 바꿔 끼우므로 transformers 내부 순서를 흉내 내지 않는다."""

    def __init__(self, inner):
        super().__init__()
        self.inner = inner
        self._last = None          # (입력 사본, 출력)

    def forward(self, input_values):
        last = self._last
        if last is not None and last[0].shape == input_values.shape and torch.equal(last[0], input_values):
            return last[1]
        out = self.inner(input_values)
        self._last = (input_values.detach().clone(), out)
        return out


_SHARED_PAIRS = set()


def share_feature_encoder(aligner_model, scorer_model) -> bool:
    """두 CTC 모델의 특징 추출부 가중치가 모두 같으면 한 벌(SharedFeatureEncoder)로 묶는다. 묶었으면 True.
    이미 묶였거나 가중치가 하나라도 다르면 아무것도 바꾸지 않는다(결과가 달라질 수 있는 공유는 하지 않는다)."""
    a, b = aligner_model.wav2vec2, scorer_model.wav2vec2
    if isinstance(a.feature_extractor, SharedFeatureEncoder) and a.feature_extractor is b.feature_extractor:
        return True
    if isinstance(a.feature_extractor, SharedFeatureEncoder) or isinstance(b.feature_extractor, SharedFeatureEncoder):
        return False
    sa, sb = a.feature_extractor.state_dict(), b.feature_extractor.state_dict()
    if sa.keys() != sb.keys() or not all(torch.equal(sa[k], sb[k]) for k in sa):
        return False
    shared = SharedFeatureEncoder(a.feature_extractor)
    a.feature_extractor = shared
    b.feature_extractor = shared
    return True


def _share_once(aligner_id: str, scorer_id: str) -> None:
    key = (aligner_id, scorer_id)
    if key in _SHARED_PAIRS:
        return
    _SHARED_PAIRS.add(key)
    try:
        device = resolve_device()
        _, am = _load(aligner_id, device=device)
        _, sm = _load(scorer_id, device=device)
        ok = share_feature_encoder(am, sm)
        print(f"[dgop] 특징 추출부 공유: {'켬' if ok else '가중치가 달라 끔'} ({aligner_id} · {scorer_id})")
    except Exception as e:   # 공유는 속도 최적화일 뿐이라 실패해도 채점은 그대로 한다
        print(f"[WARN] 특징 추출부 공유 실패: {type(e).__name__}: {e}")


# 문장 끝 모음 정렬 결함(docs/dgop-final-vowel-2026-10.md, 2026-10-07). 자체 학습 정렬기·채점기는 마지막 토큰(대개 끝 모음)을
# 말소리 안이 아니라 입력의 마지막 프레임에 낸다. 앱 녹음은 정지 버튼으로 끝나 끝 무음이 길어서, 끝 모음이 녹음 끝 무음에 놓이고
# 말 빠르기·입모양 비교의 시각이 그만큼 늦어졌다. 정렬기에 넣기 전에 말소리 끝 + 여유에서 자른다(앞은 자르지 않는다).
TAIL_TRIM_MARGIN_S = 0.05
_TRIM_WIN_S = 0.01
_TRIM_MIN_S = 0.1


def speech_end_seconds(waveform, sample_rate: int) -> Optional[float]:
    """말소리 끝(초). 10 ms 창 RMS(dB)가 max(99백분위 − 35 dB, 10백분위 + 6 dB)를 넘는 마지막 창의 끝. 창이 3개 미만이거나
    넘는 창이 없으면 None."""
    import numpy as np
    if waveform is None:
        return None
    y = np.asarray(waveform, dtype=np.float64).reshape(-1)
    n = int(sample_rate * _TRIM_WIN_S)
    m = len(y) // n if n > 0 else 0
    if m < 3:
        return None
    db = 20.0 * np.log10(np.sqrt(np.mean(y[:m * n].reshape(m, n) ** 2, axis=1) + 1e-12))
    thr = max(np.percentile(db, 99) - 35.0, np.percentile(db, 10) + 6.0)
    idx = np.nonzero(db > thr)[0]
    return None if not len(idx) else float((idx[-1] + 1) * _TRIM_WIN_S)


def trim_trailing_silence(waveform, sample_rate: int, margin_s: Optional[float] = None):
    """정렬기·채점기에 넣을 소리: 말소리 끝 + margin_s 뒤를 잘라 낸다. 말소리 끝을 못 찾으면 그대로, 0.1초보다 짧게 만들지 않는다.
    DGOP_TAIL_TRIM=0이면 자르지 않는다(측정 비교용)."""
    if waveform is None or os.getenv("DGOP_TAIL_TRIM", "1") == "0":
        return waveform
    end = speech_end_seconds(waveform, sample_rate)
    if end is None:
        return waveform
    margin = TAIL_TRIM_MARGIN_S if margin_s is None else margin_s
    cut = min(len(waveform), int(round((end + margin) * sample_rate)))
    return waveform[:max(cut, int(_TRIM_MIN_S * sample_rate))]


# 끝 구간 다시 나누기(docs/dgop-final-vowel-fix2-2026-10.md, 2026-10-09). 끝 자르기는 끝 모음을 말소리 끝 근처로 옮길 뿐 실제 모음
# 시작을 찾지 못한다('요'는 말소리 안에서 빈칸이 이겨 ㅛ가 나오지 않고 입력 끝에서만 나온다). 정렬기 사후확률에서 빈칸을 빼고 다시
# 정규화하면 ㅛ 구간에서도 ㅛ가 앞 소리보다 높으므로, 앞 토큰부터 말소리 끝 + 여유까지를 빈칸 없는 단조 분할(HMM식)로 다시 나눠
# 끝 토큰들의 시작·끝 시각을 정한다. 채점(구간 평균 분포)은 CTC 구간 그대로 쓰고 시각만 바꾼다. DGOP_TAIL_RESEG=1일 때만 켠다.
TAIL_RESEG_GATE = "late"       # "late": 끝 토큰이 말소리 끝 근처 이후에 나왔을 때만, "all": 늘(탐색 절반 0에서 고른다, 문서 3절)
TAIL_RESEG_LATE_FRAMES = 2


def tail_reseg_enabled() -> bool:
    return os.getenv("DGOP_TAIL_RESEG", "0") == "1"


def _monotone_segments(scores) -> List[int]:
    """scores (n, S): 상태 S개를 순서대로 하나 이상 프레임씩 차지하는 분할 가운데 점수 합이 가장 큰 것의 상태별 시작 프레임.
    첫 프레임은 상태 0, 마지막 프레임은 상태 S−1. 동점이면 머무름을 고른다. n < S면 ValueError."""
    import numpy as np
    sc = np.asarray(scores, dtype=np.float64)
    n, S = sc.shape
    if n < S:
        raise ValueError("프레임이 상태 수보다 적습니다")
    neg = -np.inf
    acc = np.full(S, neg)
    acc[0] = sc[0, 0]
    adv = np.zeros((n, S), dtype=bool)
    for t in range(1, n):
        prev = np.concatenate([[neg], acc[:-1]])
        take = prev > acc
        acc = np.where(take, prev, acc) + sc[t]
        adv[t] = take
    starts = [0] * S
    s = S - 1
    for t in range(n - 1, 0, -1):
        if s == 0:
            break
        if adv[t, s]:
            starts[s] = t
            s -= 1
    return starts


def retime_tail(log_probs, vocab: Dict[str, int], target_tokens: Sequence[str], spans: Sequence[Dict],
                end_frame: Optional[int], gate: Optional[str] = None, blank_token: Optional[str] = None) -> List[Dict]:
    """끝 토큰들(마지막 중성과 그 뒤 종성)의 시각용 구간을 다시 정한 spans 사본. 다른 토큰은 그대로다.
    log_probs: 정렬기 (T, C) 로그확률. end_frame: 말소리 끝 + 여유의 프레임(포함). 바꾼 토큰에는 retimed=True.
    묶음은 마지막 중성과 그 뒤 토큰, 그리고 그 앞에서 CTC 시작이 end_frame − TAIL_RESEG_LATE_FRAMES 이후인 토큰들이다. 묶음 바로 앞의
    어절 경계가 아닌 토큰 p의 CTC 구간 시작부터 end_frame까지를 상태 [p, p 뒤 토큰들]로 빈칸 없이 나눈다.
    gate "late"는 마지막 토큰의 CTC 시작이 end_frame − TAIL_RESEG_LATE_FRAMES 이후일 때만 바꾼다. 조건이 맞지 않으면 그대로."""
    import numpy as np
    out = [dict(s) for s in spans]
    gate = gate or TAIL_RESEG_GATE
    toks = list(target_tokens)
    if end_frame is None or not toks or len(out) != len(toks):
        return out
    nuc = [i for i, t in enumerate(toks) if str(t).startswith("n:")]
    if not nuc:
        return out
    k, K = nuc[-1], len(toks) - 1
    if any(s.get("start") is None for s in out):
        return out
    lp = log_probs.detach().cpu().numpy() if hasattr(log_probs, "detach") else np.asarray(log_probs)
    T = lp.shape[0]
    e = min(int(end_frame), T - 1)
    late = e - TAIL_RESEG_LATE_FRAMES
    if gate == "late" and out[K]["start"] < late:
        return out
    # 묶음: 마지막 중성부터, 그 앞에서 말소리 끝 근처 이후에 놓인 토큰들까지(끝 토큰 여럿이 함께 입력 끝에 몰린 경우, 사후 변경 1)
    g = k
    while g - 1 >= 0 and out[g - 1]["start"] >= late:
        g -= 1
    p = g - 1
    while p >= 0 and toks[p] in ("|",):
        p -= 1
    if p < 0:
        return out
    a = int(out[p]["start"])
    states = [p] + list(range(p + 1, K + 1))
    if e - a + 1 < len(states) or any(toks[i] not in vocab for i in states):
        return out
    blank = blank_id_for(vocab, blank_token)
    seg = lp[a:e + 1].astype(np.float64).copy()
    seg[:, blank] = -np.inf
    m = seg.max(axis=1, keepdims=True)
    seg = seg - (m + np.log(np.exp(seg - m).sum(axis=1, keepdims=True)))   # 빈칸을 뺀 다시 정규화
    starts = _monotone_segments(seg[:, [vocab[toks[i]] for i in states]])
    bounds = starts[1:] + [e - a + 1]
    for j, i in enumerate(states[1:]):
        out[i] = {**out[i], "start": a + bounds[j], "end": a + bounds[j + 1] - 1, "retimed": True}
    return out


def phone_confidences(waveform, sample_rate: int, target_tokens: Sequence[str],
                       aligner_id: str = DEFAULT_MODEL_ID,
                       scorer_id: str = None) -> List[Dict]:
    """
    오디오 + 목표 음소(토큰)열 → 강제정렬 → 구간별 D-GOP.
    dgop.py 순수 함수에 실제 음향 신호를 공급하는 통합 지점.

    ── 왜 모델이 둘인가 (축 A의 핵심 설계) ────────────────────────────────
    D-GOP 점수는 naive × confidence이고, 뭉갠 발화에서 분포가 평평해져 confidence가
    떨어지는 것 자체가 '발음이 부정확하다'는 신호다. 그래서 **채점기(scorer)는 정상 발화
    기준(canonical) 모델이어야 한다** — 저하 발화로 강인하게 만들면 뭉개도 점수가 높아져
    변별력이 사라진다.

    반면 **정렬기(aligner)는 저하 발화에 강인해야** 한다. 구간을 못 찾으면 채점 자체가
    불가능하기 때문이다. 두 요구가 정반대라 모델을 나눈다:
      · aligner → forced_align으로 '어디에 놓였나'만 찾는다
      · scorer  → 그 구간의 사후확률로 '정상 발화에서 얼마나 벗어났나'를 잰다
    (docs/axis-a-training-plan.md §0·§1)

    scorer_id를 생략하면 aligner_id와 같은 모델을 써 기존 단일 모델 동작으로 되돌아간다.
    두 모델은 같은 wav2vec2 conv 설정(stride 320)을 공유해야 프레임 구간이 그대로 옮겨진다 —
    aligner는 scorer에서 이어받아 미세조정하므로 자연히 만족되지만, 어긋나면 즉시 예외를 낸다.

    모델 다운로드가 필요해 유닛테스트 대상이 아니다(scripts/eval_dgop_discrimination.py로 검증).
    """
    scorer_id = scorer_id or aligner_id
    if scorer_id != aligner_id:
        _share_once(aligner_id, scorer_id)
    # 끝 무음을 잘라 넣는다(TAIL_TRIM_MARGIN_S 참고). 자르는 것은 끝뿐이라 아래 시각(초)은 원래 녹음 기준 그대로다.
    waveform = trim_trailing_silence(waveform, sample_rate)
    log_probs, vocab = ctc_log_probs(waveform, sample_rate, aligner_id)
    spans = align_targets(log_probs, vocab, target_tokens)

    if scorer_id == aligner_id:
        score_lp, score_vocab = log_probs, vocab
    else:
        score_lp, score_vocab = ctc_log_probs(waveform, sample_rate, scorer_id)
        if score_lp.shape[0] != log_probs.shape[0]:
            raise ValueError(
                f"정렬기·채점기의 프레임 수가 다릅니다({log_probs.shape[0]} vs {score_lp.shape[0]}) — "
                "구간을 옮길 수 없습니다. 두 모델의 conv stride 설정이 같아야 합니다."
            )

    # 프레임 → 초(구간별 입모양 보완 B-6이 웹캠 입모양 타임라인과 맞출 때 쓴다). wav2vec2는 약 20ms/프레임.
    n_frames = max(1, int(log_probs.shape[0]))
    n_samples = len(waveform) if waveform is not None else 0
    sec_per_frame = (n_samples / float(sample_rate)) / n_frames if n_samples else 0.02
    # 시각용 구간: 끝 구간 다시 나누기를 켰으면 끝 토큰들의 시각만 바꾼다(채점은 아래에서 CTC 구간 그대로)
    timing_spans = spans
    if tail_reseg_enabled() and n_samples:
        end_s = speech_end_seconds(waveform, sample_rate)
        if end_s is not None:
            end_frame = int(round((end_s + TAIL_TRIM_MARGIN_S) / sec_per_frame))
            timing_spans = retime_tail(log_probs, vocab, target_tokens, spans, end_frame)
    results = []
    for span, tspan in zip(spans, timing_spans):
        token = span["token"]
        # 어절 경계 같은 특수토큰은 정렬은 제약하되 발음 채점 대상은 아니다.
        scorable = _is_scorable(token)
        timing = ({"t0": round(tspan["start"] * sec_per_frame, 3), "t1": round((tspan["end"] + 1) * sec_per_frame, 3)}
                  if tspan.get("start") is not None and tspan.get("end") is not None else {})
        if tspan.get("retimed"):
            timing["retimed"] = True
        dist = span_distribution(score_lp, span["start"], span["end"])
        if not dist or token not in score_vocab:
            results.append({"token": token, "aligned": False, "scorable": scorable, **timing})
            continue
        target_prob = dist[score_vocab[token]]
        results.append({"token": token, "aligned": True, "scorable": scorable, **timing,
                        **_dgop.dgop_phone(target_prob, dist)})
    return results


def _is_jamo_vocab(vocab: Dict[str, int]) -> bool:
    """축 A가 학습한 자모 vocab인가(backend/jamo_vocab.py의 위치 접두 토큰으로 판별)."""
    return "o:\u3131" in vocab and "n:\u314f" in vocab


def _is_scorable(token: str) -> bool:
    """D-GOP 집계 대상 토큰인가. 특수토큰(음절 vocab의 [UNK]·[PAD] 포함)은 빼고, 자모 vocab이면 jamo_vocab의 판정을 따른다."""
    if token in SPECIAL_TOKENS:
        return False
    try:
        import jamo_vocab
        return jamo_vocab.is_scorable(token)
    except Exception:
        return True


def normalize_syllable_text(text: str) -> str:
    """음절 vocab 모델에 넣을 목표 문장 — 한글 음절과 공백만 남긴다. 문장부호·숫자·영문은 토크나이저가 [UNK]로 바꿔
    강제정렬이 그 토큰에 프레임을 억지로 배정하고 채점까지 되던 것을 막는다(숫자는 읽는 법을 알 수 없어 뺀다)."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣\s]", " ", text or "")).strip()


def tokens_for_text(text: str, model_id: str = DEFAULT_MODEL_ID) -> List[str]:
    """
    목표 텍스트를 이 체크포인트 자신의 CTC vocab 토큰열로 변환한다.

    축 A가 학습한 자모 vocab(49토큰)이면 jamo_vocab.text_to_tokens를 쓴다 — 토큰이
    'o:ㄱ' 같은 위치 접두 문자열이라 HF 토크나이저가 원문에서 유도할 수 없고, 무엇보다
    **평파열음화·비음화 등 발음 규칙을 거쳐야** 라벨과 일치하기 때문이다.

    그 외(음절 vocab 등)에는 모델의 토크나이저를 쓰되, 한글과 공백만 남긴 문장을 넣는다
    (normalize_syllable_text) — 체크포인트를 바꿔도 배관이 그대로 재사용된다.
    """
    processor, _ = _load(model_id)
    tokenizer = processor.tokenizer
    vocab = tokenizer.get_vocab()
    if _is_jamo_vocab(vocab):
        import jamo_vocab
        return jamo_vocab.text_to_tokens(text)
    ids = tokenizer(normalize_syllable_text(text)).input_ids
    id2tok = {v: k for k, v in vocab.items()}
    return [id2tok[i] for i in ids if i in id2tok]


def assess_text(audio_bytes: bytes, target_text: str,
                 aligner_id: str = DEFAULT_MODEL_ID, scorer_id: str = None,
                 sample_rate: int = 16000, calibrate: bool = True) -> Dict:
    """
    녹음 바이트 + 목표 텍스트 → D-GOP 문장 점수. `/api/speak/assess`가 호출하는 통합
    지점(축 B 완성). 오디오 디코딩은 faster-whisper의 decode_audio를 재사용해(이미
    프로덕션에서 검증된 경로) 별도 오디오 컨테이너 의존성을 늘리지 않는다.

    aligner_id로 구간을 찾고 scorer_id로 채점한다(생략 시 동일 모델 — 기존 동작).
    두 모델을 나누는 이유는 phone_confidences의 docstring 참고.

    score는 **표시용 보정 점수**, raw_score는 보정 전 원점수다(A-3 한계 ② 대응 —
    원점수는 깨끗한 발화가 9.51/100이라 학습자에게 그대로 보여줄 수 없다). 보정은 단조
    변환이라 순위는 그대로다. calibrate=False면 원점수를 그대로 score로 돌려준다 —
    변별력 평가처럼 보정 이전 값을 봐야 하는 쪽을 위한 문이다.

    정렬 가능한 음소가 하나도 없으면(체크포인트-언어 불일치 등) score=None을 돌려주고,
    호출부가 전사 방식으로 폴백하도록 신호한다.
    """
    from faster_whisper.audio import decode_audio
    import io as _io

    # 앞 30초만 채점한다(연습 발화는 몇 초이고, 긴 업로드를 통째로 넣으면 정렬기·채점기 메모리가 길이에 따라 커진다)
    waveform = decode_audio(_io.BytesIO(audio_bytes), sampling_rate=sample_rate)[:sample_rate * 30]
    tokens = tokens_for_text(target_text, model_id=aligner_id)
    phones = phone_confidences(waveform, sample_rate, tokens,
                               aligner_id=aligner_id, scorer_id=scorer_id)
    # ㄶ·ㅀ + 모음에서 라벨에만 남은 ㅎ(표준 발음은 내지 않음)에 표시한다. 문장 점수는 보정이 이 토큰까지 넣고 맞춰져 그대로 두고,
    # 코칭·음소 칩·시행 기록이 빼 쓴다(jamo_vocab.silent_linking_h).
    try:
        import jamo_vocab
        if list(tokens) == jamo_vocab.text_to_tokens(target_text):
            for i in jamo_vocab.silent_linking_h(target_text):
                if i < len(phones):
                    phones[i]["silent_h"] = True
    except Exception:
        pass
    # 정렬에 성공했고 채점 대상인 음소만 문장 점수에 넣는다(어절 경계 제외).
    scored = [p for p in phones if p.get("aligned") and p.get("scorable")]
    if not scored:
        return {"score": None, "raw_score": None, "uncertainty": 1.0, "phones": phones}
    result = {**_dgop.sentence_dgop(scored), "phones": phones}
    result["raw_score"] = result["score"]
    # S7 말 빠르기·쉼(docs/speak-visual-cues.md): 같은 파형과 정렬에서 바로 잰다. 점수에는 넣지 않고, 문장 단계 화면의 지표 하나로만 쓴다.
    try:
        import speak_cues
        result["rate"] = speak_cues.rate_pause(waveform, phones, sample_rate)
    except Exception as e:   # 단서 계산 실패는 채점과 무관
        print(f"[WARN] rate_pause 실패: {type(e).__name__}: {e}")
        result["rate"] = None
    if calibrate:
        cal = load_calibration(calibration_path_for(scorer_id or aligner_id))
        result["score"] = _dgop.calibrate_score(result["raw_score"], cal)
        result["calibration"] = cal.get("source") or "내장 기본값"
    return result
