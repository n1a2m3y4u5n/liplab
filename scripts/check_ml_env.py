"""
축 A·B·D·E용 ML 환경 점검 스크립트.

torch·torchaudio·transformers가 실제로 끝까지 맞물려 동작하는지(공개 CTC 음성모델
다운로드 → forward pass) 확인한다. 로컬(GPU 없음)에서는 이 스크립트로 툴체인만
검증하고, 실제 미세조정·학습은 RunPod H100에서 수행한다(고도화계획서 4.2).

개발일지가 원래 지목한 kresnik/wav2vec2-xlsr-korean은 HF Hub API가 401을 반환해 접근 불가
확인(2026-09-07). 같은 저자의 kresnik/wav2vec2-large-xlsr-korean은 공개 확인되어
backend/dgop_acoustic.py의 DEFAULT_MODEL_ID로 채택했다 — 이 스크립트도 그 체크포인트로
검증한다. (다만 vocab이 음절 단위라 자모별 신뢰도가 필요하면 후속 분해 단계가 필요함 —
dgop_acoustic.py 모듈 docstring 참고.)

사용법: backend/venv/bin/python scripts/check_ml_env.py
"""
import sys
import time

CHECK_MODEL_ID = "kresnik/wav2vec2-large-xlsr-korean"  # backend/dgop_acoustic.DEFAULT_MODEL_ID와 동일하게 유지.


def main() -> int:
    print("[1/4] 패키지 임포트 확인")
    import torch
    import torchaudio
    import transformers

    print(f"      torch {torch.__version__} | torchaudio {torchaudio.__version__} | "
          f"transformers {transformers.__version__}")
    cuda = torch.cuda.is_available()
    print(f"      CUDA 사용 가능: {cuda} {'(RunPod에서는 True여야 함)' if not cuda else ''}")

    print(f"[2/4] 공개 체크포인트 다운로드: {CHECK_MODEL_ID}")
    from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

    t0 = time.time()
    processor = Wav2Vec2Processor.from_pretrained(CHECK_MODEL_ID)
    model = Wav2Vec2ForCTC.from_pretrained(CHECK_MODEL_ID)
    model.eval()
    print(f"      로드 완료 ({time.time() - t0:.1f}s)")

    print("[3/4] 합성 파형으로 forward pass (16kHz, 1초 사인파)")
    sample_rate = 16000
    t = torch.linspace(0, 1, sample_rate)
    synthetic_wave = 0.05 * torch.sin(2 * torch.pi * 220 * t)  # 무음에 가까운 저진폭 톤

    inputs = processor(synthetic_wave.numpy(), sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values).logits  # (batch, time, vocab)

    probs = torch.softmax(logits, dim=-1)
    print(f"      logits shape: {tuple(logits.shape)} (batch, 프레임, 음소 vocab)")
    print(f"      프레임당 확률 합(정규화 확인, 1.0 근접해야 함): {probs[0, 0].sum().item():.4f}")

    print("[4/4] 결과")
    print("      ML 툴체인 정상 동작 확인 (다운로드 → 전처리 → forward → CTC 확률 산출).")
    print("      다음 단계(축 A): OLKAVS 합성 코퍼스로 이 체크포인트를 농인 발화 근사에 맞게 미세조정.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
