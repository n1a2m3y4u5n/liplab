"""
발화(말하기) 채점 — 서버 음성인식(faster-whisper, 오픈소스·무료).

녹음 오디오 → 한국어 텍스트 전사. 채점은 호출부(main)에서 기존 음운 유사도
엔진(scoring.calculate_score)을 재활용한다. 즉 여기서는 '귀' 역할만.

모델은 최초 1회 로드해 프로세스에 상주. 환경변수 WHISPER_MODEL(기본 'base')로
크기 조절 — base는 가볍고 빠름(단어/짧은 문장에 충분), small은 더 정확하나 무겁다.

정직한 한계: Whisper는 '정상 발화'로 학습돼 어눌한 발음은 오인식할 수 있다.
그래서 이 전사는 '정답'이 아니라 '얼마나 알아들리는지'의 신호로 쓴다.
"""
import os
import io
import asyncio

_MODEL = None
_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")


def _get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel  # 지연 import — 미설치 환경에서도 앱 기동
        _MODEL = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
    return _MODEL


async def transcribe(audio_bytes: bytes) -> str:
    """녹음 오디오(webm/wav/…) → 한국어 텍스트. 무거운 추론은 스레드로 오프로드."""
    if not audio_bytes:
        return ""

    def _run():
        model = _get_model()
        segments, _info = model.transcribe(
            io.BytesIO(audio_bytes),
            language="ko",
            beam_size=1,          # 짧은 발화라 빔서치 최소로 속도 우선
            temperature=0.0,
        )
        return "".join(seg.text for seg in segments).strip()

    return await asyncio.to_thread(_run)


def is_available() -> bool:
    """faster-whisper 설치 여부(엔드포인트에서 사전 점검용)."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False
