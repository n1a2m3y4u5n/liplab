"""사용자가 정하는 MIME 외에 컨테이너 시그니처도 검사한다."""
from fastapi import HTTPException


def validate_audio(data):
    # WAV, Ogg, FLAC, WebM/Matroska, MP4/M4A, MP3(ID3 또는 프레임 헤더).
    valid = (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
             or len(data) >= 27 and data[:4] == b"OggS"
             or len(data) >= 42 and data[:4] == b"fLaC"
             or len(data) >= 16 and data[:4] == b"\x1a\x45\xdf\xa3"
             or len(data) >= 16 and data[4:8] == b"ftyp"
             or len(data) >= 10 and data[:3] == b"ID3"
             or len(data) >= 4 and data[0] == 255 and data[1] & 0xE0 == 0xE0
                and data[1] & 6 != 0 and data[2] & 0xF0 not in (0, 0xF0))
    if not valid:
        raise HTTPException(415, "지원하는 오디오 파일 형식이 아닙니다.")
