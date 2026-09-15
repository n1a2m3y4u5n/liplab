"""
D-GOP 음향 백본 — 고도화 축 B(음향 추론).

사전학습 wav2vec2(한국어)로 오디오의 프레임별 음소 사후확률을 얻고, 목표 텍스트를 강제정렬해
각 음소 구간의 사후확률로 발음정확도(D-GOP)를 산출한다. dgop.py(불확실성 보정·융합)에 분포를
공급하는 역할이다. **추론만 하므로 GPU 없이 로컬 CPU에서 동작**한다(느릴 뿐). 계획서 §2.5 그림5~7의
전사 비의존 발음채점을 실제 모델로 구현한 것.

torch·transformers·torchaudio가 없으면 is_available()=False로, 앱은 기존 전사 방식으로 폴백한다.
"""
import io
from typing import Dict, List, Optional

_MODEL_ID = "kresnik/wav2vec2-large-xlsr-korean"
_model = None
_processor = None


def is_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _model, _processor
    if _model is None:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        _processor = Wav2Vec2Processor.from_pretrained(_MODEL_ID)
        _model = Wav2Vec2ForCTC.from_pretrained(_MODEL_ID)
        _model.eval()
    return _model, _processor


def _to_waveform(audio_bytes: bytes):
    import torch  # noqa: F401
    import torchaudio
    wav, sr = torchaudio.load(io.BytesIO(audio_bytes))
    if wav.shape[0] > 1:
        wav = wav.mean(0, keepdim=True)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, sr, 16000)
    return wav.squeeze(0)


def _emission(audio_bytes: bytes):
    """오디오 → (log_prob 프레임행렬 [T,V], processor). CTC 로그확률."""
    import torch
    model, proc = _load()
    wav = _to_waveform(audio_bytes)
    inputs = proc(wav.numpy(), sampling_rate=16000, return_tensors="pt", padding=True)
    with torch.no_grad():
        logits = model(inputs.input_values).logits[0]  # (T, V)
    return torch.log_softmax(logits, dim=-1), proc


def dgop_from_audio(audio_bytes: bytes, target_text: str,
                    visual_score: Optional[float] = None) -> Dict:
    """
    목표 텍스트를 강제정렬해 음소(토큰) 구간별 D-GOP를 산출하고 문장 점수로 집계한다.
    visual_score(웹캠 입모양 0~100)가 오면 dgop.fuse_audio_visual로 후기 융합한다.
    """
    import torch
    import torchaudio
    import dgop

    log_probs, proc = _emission(audio_bytes)   # (T, V)
    # 목표 토큰열(한국어 문자 단위 CTC)
    tid = proc.tokenizer(target_text.replace(" ", "")).input_ids
    tid = [t for t in tid if t is not None]
    if not tid:
        return {"score": 0.0, "uncertainty": 1.0, "phones": [], "audio_available": True}

    targets = torch.tensor([tid], dtype=torch.int32)
    # 강제정렬 — 각 프레임에 목표 토큰 인덱스를 배정
    aligned, _scores = torchaudio.functional.forced_align(
        log_probs.unsqueeze(0), targets, blank=0)
    aligned = aligned[0].tolist()
    probs = log_probs.exp().numpy()  # (T, V)

    # 토큰별 구간을 모아 각 구간의 (목표 사후확률, 분포)로 D-GOP
    per: List[Dict] = []
    T = len(aligned)
    order = tid  # 정렬 결과에 등장하는 비-blank 토큰 순서와 매칭
    oi = 0
    i = 0
    while i < T and oi < len(order):
        tok = order[oi]
        # 이 토큰이 배정된 연속 프레임 구간 수집
        frames = []
        while i < T and aligned[i] == tok:
            frames.append(i)
            i += 1
        if frames:
            seg = probs[frames]                # (len, V)
            target_prob = float(seg[:, tok].mean())
            dist = seg.mean(axis=0).tolist()   # 구간 평균 분포(불확실성용)
            ph = dgop.dgop_phone(target_prob, dist)
            # 사람이 읽을 수 있는 토큰 라벨(음소/글자) 부착 — 프론트 음소별 표시용
            try:
                lab = proc.tokenizer.convert_ids_to_tokens([tok])[0]
                ph["label"] = "" if lab in ("|", "<pad>", "<s>", "</s>", "<unk>") else lab.replace("|", " ")
            except Exception:
                ph["label"] = ""
            per.append(ph)
            oi += 1
        else:
            i += 1

    sent = dgop.sentence_dgop(per)
    result = {**sent, "audio_available": True}
    if visual_score is not None:
        result["fused"] = dgop.fuse_audio_visual(sent["score"], sent["uncertainty"], visual_score)
    return result
