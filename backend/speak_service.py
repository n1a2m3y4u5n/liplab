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
        return collapse_repeats("".join(seg.text for seg in segments).strip())

    return await asyncio.to_thread(_run)


def collapse_repeats(text: str, min_rep: int = 3, max_n: int = 6) -> str:
    """연속으로 min_rep번 이상 되풀이된 어절 묶음(1~max_n어절)을 한 번으로 접는다. Whisper는 잡음·무음에서 '이 영상은 영상에서
    영상에서 …'처럼 반복 루프를 지어내고, 실제 발화 끝에도 '통화 통화 통화 …'를 붙인다(538·608 전사 2,100개 중 16개). 채점은 목표를
    얼마나 말했는지(재현율)만 보므로 긴 루프가 목표 음절을 우연히 채워, 잡음 전사가 5단계 문항에 28% 합격했다. 접으면 0%이고,
    맞게 말한 문장의 불합격은 538 그대로·608 청각장애 발화 12.8 → 13.3%(360문장 중 2개)다(docs/speak-transcript-scoring.md).
    구두점은 떼고 비교하며, 두 번 반복('하하 하하', '아니 아니')은 그대로 둔다."""
    import re
    toks = (text or "").split()
    key = [re.sub(r"[^\w]", "", t) for t in toks]
    out, i = [], 0
    while i < len(toks):
        for n in range(1, max_n + 1):
            if i + n * min_rep > len(toks):
                out.append(toks[i]); i += 1
                break
            unit = key[i:i + n]
            k = 1
            while any(unit) and i + (k + 1) * n <= len(toks) and key[i + k * n:i + (k + 1) * n] == unit:
                k += 1
            if k >= min_rep:
                out += toks[i:i + n]; i += k * n
                break
        else:
            out.append(toks[i]); i += 1
    return " ".join(out)


def is_available() -> bool:
    """faster-whisper 설치 여부(엔드포인트에서 사전 점검용)."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False
