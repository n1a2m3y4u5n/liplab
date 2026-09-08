"""
D-GOP 음향 백본 — 고도화 축 B.

dgop.py는 '음소 사후확률 분포'를 입력받는 순수 함수만 담고 있다(모델 비의존, 결정론적
테스트 가능). 이 모듈이 그 분포를 실제로 공급한다: CTC 음향모델로 프레임별 로그확률을
얻고, torchaudio의 CTC 강제정렬(forced_align)로 목표 음소열을 프레임 구간에 정렬한 뒤,
구간별 확률분포를 dgop.dgop_phone에 넘긴다.

torch·torchaudio·transformers는 requirements-ml.txt 전용 의존성이다(앱 런타임/배포에는
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
from typing import Dict, List, Sequence

import dgop as _dgop

try:
    import torch
    import torchaudio
    from transformers import AutoModelForCTC, AutoProcessor
    HAS_ACOUSTIC = True
except Exception:  # torch/torchaudio/transformers 미설치
    HAS_ACOUSTIC = False

# 공개 확인된 한국어 CTC 체크포인트(음절 단위 vocab). 축 A가 농인 발화로 미세조정한
# 버전이 나오면 이 상수만 바꾸면 된다 — 정렬·집계 로직은 vocab에 의존하지 않는다.
DEFAULT_MODEL_ID = "kresnik/wav2vec2-large-xlsr-korean"

_model_cache: Dict[str, tuple] = {}


def _load(model_id: str = DEFAULT_MODEL_ID):
    if not HAS_ACOUSTIC:
        raise RuntimeError("torch/torchaudio/transformers 미설치 — backend/requirements-ml.txt 설치 필요")
    if model_id not in _model_cache:
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForCTC.from_pretrained(model_id)
        model.eval()
        _model_cache[model_id] = (processor, model)
    return _model_cache[model_id]


def ctc_log_probs(waveform, sample_rate: int, model_id: str = DEFAULT_MODEL_ID):
    """
    파형(1D 배열, 16kHz 권장)을 CTC 모델에 통과시켜 프레임별 로그확률과 vocab을 얻는다.
    실제 모델 다운로드·추론이 필요해 유닛테스트 대상이 아니다(scripts/check_ml_env.py로 점검).
    반환: (log_probs: Tensor[T, C], vocab: Dict[token, id])
    """
    processor, model = _load(model_id)
    inputs = processor(waveform, sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values).logits[0]  # (T, C)
    log_probs = torch.log_softmax(logits, dim=-1)
    return log_probs, processor.tokenizer.get_vocab()


def align_targets(log_probs, vocab: Dict[str, int], target_tokens: Sequence[str],
                   blank_token: str = "<pad>") -> List[Dict]:
    """
    CTC 강제정렬로 target_tokens 각각이 놓인 프레임 구간(시작·끝, 포함)을 찾는다.
    log_probs·vocab에만 의존하는 순수 함수 — 합성 log_probs로 모델 없이 테스트 가능.
    target_tokens 중 vocab에 없는 토큰은 정렬에서 제외되고 start=end=None으로 반환된다.
    """
    if not HAS_ACOUSTIC:
        raise RuntimeError("torch/torchaudio 미설치")
    blank_id = vocab.get(blank_token, 0)
    target_ids = [vocab[t] for t in target_tokens if t in vocab]
    if len(target_ids) != len(target_tokens):
        missing = [t for t in target_tokens if t not in vocab]
        raise KeyError(f"vocab에 없는 토큰: {missing}")

    lp = log_probs.unsqueeze(0)
    targets = torch.tensor([target_ids], dtype=torch.int64)
    path, _scores = torchaudio.functional.forced_align(lp, targets, blank=blank_id)
    path = path[0].tolist()

    spans = []
    for tok, tid in zip(target_tokens, target_ids):
        frames = [i for i, p in enumerate(path) if p == tid]
        spans.append({
            "token": tok,
            "start": min(frames) if frames else None,
            "end": max(frames) if frames else None,
        })
    return spans


def span_distribution(log_probs, start, end) -> List[float]:
    """구간 [start, end](프레임, 포함)의 평균 확률분포. start가 None이면 빈 리스트."""
    if start is None:
        return []
    probs = torch.softmax(log_probs[start:end + 1], dim=-1)
    return probs.mean(dim=0).tolist()


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

    results = []
    for span in spans:
        token = span["token"]
        # 어절 경계 같은 특수토큰은 정렬은 제약하되 발음 채점 대상은 아니다.
        scorable = _is_scorable(token)
        dist = span_distribution(score_lp, span["start"], span["end"])
        if not dist or token not in score_vocab:
            results.append({"token": token, "aligned": False, "scorable": scorable})
            continue
        target_prob = dist[score_vocab[token]]
        results.append({"token": token, "aligned": True, "scorable": scorable,
                        **_dgop.dgop_phone(target_prob, dist)})
    return results


def _is_jamo_vocab(vocab: Dict[str, int]) -> bool:
    """축 A가 학습한 자모 vocab인가(backend/jamo_vocab.py의 위치 접두 토큰으로 판별)."""
    return "o:\u3131" in vocab and "n:\u314f" in vocab


def _is_scorable(token: str) -> bool:
    """D-GOP 집계 대상 토큰인가. 자모 vocab이면 jamo_vocab의 판정을 따른다."""
    try:
        import jamo_vocab
        return jamo_vocab.is_scorable(token)
    except Exception:
        return True


def tokens_for_text(text: str, model_id: str = DEFAULT_MODEL_ID) -> List[str]:
    """
    목표 텍스트를 이 체크포인트 자신의 CTC vocab 토큰열로 변환한다.

    축 A가 학습한 자모 vocab(49토큰)이면 jamo_vocab.text_to_tokens를 쓴다 — 토큰이
    'o:ㄱ' 같은 위치 접두 문자열이라 HF 토크나이저가 원문에서 유도할 수 없고, 무엇보다
    **평파열음화·비음화 등 발음 규칙을 거쳐야** 라벨과 일치하기 때문이다.

    그 외(음절 vocab 등)에는 모델의 토크나이저를 그대로 쓴다 — 체크포인트를 바꿔도
    배관이 그대로 재사용된다.
    """
    processor, _ = _load(model_id)
    tokenizer = processor.tokenizer
    vocab = tokenizer.get_vocab()
    if _is_jamo_vocab(vocab):
        import jamo_vocab
        return jamo_vocab.text_to_tokens(text)
    ids = tokenizer(text).input_ids
    id2tok = {v: k for k, v in vocab.items()}
    return [id2tok[i] for i in ids if i in id2tok]


def assess_text(audio_bytes: bytes, target_text: str,
                 aligner_id: str = DEFAULT_MODEL_ID, scorer_id: str = None,
                 sample_rate: int = 16000) -> Dict:
    """
    녹음 바이트 + 목표 텍스트 → D-GOP 문장 점수. `/api/speak/assess`가 호출하는 통합
    지점(축 B 완성). 오디오 디코딩은 faster-whisper의 decode_audio를 재사용해(이미
    프로덕션에서 검증된 경로) 별도 오디오 컨테이너 의존성을 늘리지 않는다.

    aligner_id로 구간을 찾고 scorer_id로 채점한다(생략 시 동일 모델 — 기존 동작).
    두 모델을 나누는 이유는 phone_confidences의 docstring 참고.

    정렬 가능한 음소가 하나도 없으면(체크포인트-언어 불일치 등) score=None을 돌려주고,
    호출부가 전사 방식으로 폴백하도록 신호한다.
    """
    from faster_whisper.audio import decode_audio
    import io as _io

    waveform = decode_audio(_io.BytesIO(audio_bytes), sampling_rate=sample_rate)
    tokens = tokens_for_text(target_text, model_id=aligner_id)
    phones = phone_confidences(waveform, sample_rate, tokens,
                               aligner_id=aligner_id, scorer_id=scorer_id)
    # 정렬에 성공했고 채점 대상인 음소만 문장 점수에 넣는다(어절 경계 제외).
    scored = [p for p in phones if p.get("aligned") and p.get("scorable")]
    if not scored:
        return {"score": None, "uncertainty": 1.0, "phones": phones}
    return {**_dgop.sentence_dgop(scored), "phones": phones}
