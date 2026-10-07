#!/bin/bash
# 파드 준비: ffmpeg, uv, 모델마다 따로 둔 가상환경(의존성 충돌을 피한다). 표식 SETUP_<이름>_OK / _FAIL.
set -u
cd /workspace/tts
mkdir -p logs venv out
export UV_CACHE_DIR=/workspace/tts/.uvcache HF_HOME=/workspace/tts/hf PIP_DISABLE_PIP_VERSION_CHECK=1
(apt-get update -qq && apt-get install -y -qq ffmpeg espeak-ng >/dev/null 2>&1 && echo SETUP_APT_OK || echo SETUP_APT_FAIL) &
if ! command -v uv >/dev/null; then pip install -q uv && echo SETUP_UV_OK || echo SETUP_UV_FAIL; fi
UV=$(command -v uv)

mk() {  # 이름 파이썬판 설치명령...
  local name=$1 py=$2; shift 2
  ( set -e
    "$UV" venv -q -p "$py" "venv/$name"
    source "venv/$name/bin/activate"
    "$@"
  ) > "logs/setup_$name.log" 2>&1 && echo "SETUP_${name}_OK" || echo "SETUP_${name}_FAIL"
}

mk st 3.11 bash -c 'uv pip install -q supertonic soundfile numpy onnxruntime-gpu' &
mk cb 3.11 bash -c 'uv pip install -q chatterbox-tts soundfile' &
mk melo 3.10 bash -c 'uv pip install -q "git+https://github.com/myshell-ai/MeloTTS.git" soundfile && python -m unidic download' &
mk score 3.11 bash -c 'uv pip install -q "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu && uv pip install -q transformers==5.17.0 faster-whisper soundfile numpy python-dotenv sqlalchemy aiosqlite pydantic' &
wait
echo SETUP_DONE
