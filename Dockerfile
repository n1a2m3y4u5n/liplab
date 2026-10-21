# Multi-stage Docker build for LIPLAB
# Stage 1: Build React frontend with Node.js
FROM node:18-alpine AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies (devDependencies needed for build)
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# S4 스트리밍 채점(빌드 인자 DGOP_STREAM=1일 때만, 기본 0). 프론트는 녹음 중 소리 조각을 서버에 보내고(VITE_DGOP_STREAM),
# 서버는 아래 단계에서 같은 인자로 켠다. 한 인자로 묶어 프론트와 서버가 어긋나지 않게 한다(DEPLOY.md 10항).
ARG DGOP_STREAM=0
ENV VITE_DGOP_STREAM=$DGOP_STREAM

# 독화 ① 화소 입술 ROI 모델(빌드 인자 LIPREAD_ROI=1일 때만, 기본 0, DEPLOY.md 11항). 웹캠 '기계 확인'이 입 27계수 모델 대신 이 모델을 쓴다.
# 모델(6.1MB)은 공개 저장소에 없으므로 빌드 폴더의 frontend/public/models/roi/(git 제외)에 복사해 둔다. 켰는데 없으면 빌드를 멈추고,
# 끈 채로 폴더가 있으면 쓰지 않는 파일이 이미지에 들어가지 않게 지운다.
ARG LIPREAD_ROI=0
ENV VITE_LIPREAD_ROI=$LIPREAD_ROI
RUN if [ "$LIPREAD_ROI" = "1" ]; then \
      test -s public/models/roi/kr_lipread_roi.web.onnx && test -s public/models/roi/kr_lipread_roi.web.meta.json \
      || { echo "frontend/public/models/roi/ 모델이 없다(DEPLOY.md 11항)"; exit 1; }; \
    else rm -rf public/models/roi; fi

# Build for production
RUN npm run build

# Stage 2: Python backend with FastAPI
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the Whisper model into the image so cold starts don't fetch it
# at runtime (the machine auto-stops and its filesystem resets between wakes).
# HF_HOME을 받기 전에 정한다. 예전에는 아래(ML 단계)에서 정해 Whisper가 /root/.cache에 받혔고, 실행 때는 /app/hf만
# 찾아 전시앱은 켜질 때마다 다시 받고, 오프라인(HF_HUB_OFFLINE=1)인 liplab-dev는 전사 대체 경로가 모델을 못 찾았다.
ENV HF_HOME=/app/hf
ENV WHISPER_MODEL=base
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# 서버 추론(D-GOP 발음채점·음성구동 아바타) — WITH_ML=1일 때만(fly.dev.toml). 기본값 0이라 전시앱 이미지는 그대로다.
# torch CPU 휠과 transformers를 깔고, 모델 두 개(kresnik 정렬·채점, WavLM-large 아바타 백본, 각 약 1.2GB)를
# 이미지에 미리 받아 둔다. 기계가 자동으로 멈췄다 켜질 때마다 다시 받지 않게 하려는 것이다. WavLM-large는 아래에서 int8로
# 바꾼 뒤 fp32를 지운다(9/27).
ARG WITH_ML=0
# D-GOP 채점 모델: kresnik(공개 모델, 빌드 때 받는다) 또는 ours(자체 학습 정렬기·채점기, 9/25 재검 통과).
# ours는 backend/models/dgop_ours/{aligner,scorer}에 둔 체크포인트(git 제외, DEPLOY.md 9항)를 아래 COPY로 싣는다.
# 9/26부터는 미리 변환한 int8 파일(model.int8.safetensors, 모델당 355MB)을 싣는다. fp32(1.26GB)도 받지만 켜질 때 느리다.
ARG DGOP_MODEL=kresnik
COPY backend/requirements-infer.txt ./
RUN if [ "$WITH_ML" = "1" ]; then \
      pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r requirements-infer.txt && \
      python -c "from transformers import AutoModel, AutoModelForCTC, AutoProcessor; \
k='kresnik/wav2vec2-large-xlsr-korean'; \
'$DGOP_MODEL' == 'kresnik' and (AutoProcessor.from_pretrained(k), AutoModelForCTC.from_pretrained(k)); \
AutoModel.from_pretrained('microsoft/wavlm-large')"; \
    fi

# Copy backend source
COPY backend/ ./
# 자체 학습 채점 모델로 빌드할 때는 체크포인트가 빌드 폴더에 있어야 한다(없으면 D-GOP가 전사로 폴백하므로 빌드를 멈춘다).
# 켜질 때와 같은 적재 경로(backbone_service._load_ctc, fly.dev.toml의 BACKBONE_QUANT=int8)로 전처리기까지 실제로 올려 본다
# (이 이미지의 torch·transformers로 못 읽으면 배포 전에 빌드에서 멈춘다). int8 파일로 올렸는지(file) 실행 중 변환인지(runtime)와
# torch·transformers 판을 빌드 기록에 남긴다.
RUN if [ "$WITH_ML" = "1" ] && [ "$DGOP_MODEL" = "ours" ]; then \
      for m in aligner scorer; do \
        test -s models/dgop_ours/$m/model.int8.safetensors || test -s models/dgop_ours/$m/model.safetensors \
        || { echo "backend/models/dgop_ours/$m 체크포인트가 없다(DEPLOY.md 9항)"; exit 1; }; \
      done && \
      BACKBONE_QUANT=int8 python -c "import torch, transformers, backbone_service as B; \
torch.set_grad_enabled(False); \
rs=[(d,) + B._load_ctc('models/dgop_ours/' + d, 'cpu') for d in ('aligner', 'scorer')]; \
x=torch.zeros(1, 16000); \
[m(x) for _, p, m in rs]; \
print('dgop_ours ok:', [(d, getattr(m, 'liplab_quant_from', None)) for d, p, m in rs], 'torch', torch.__version__, 'transformers', transformers.__version__)"; \
    fi

# A4 아바타 백본(WavLM-large)을 int8로 바꿔 싣고 fp32 허브 캐시는 지운다(9/27 세션 10 관문 통과: jawOpen 상관 0.9995,
# 앱 프로세스 메모리 약 0.87GiB 감소, 켜질 때 읽는 양 1.26GB → 0.36GB, 추론 1.08배, docs/speed-int8-a4.md). audio2face는
# models/wavlm_large_int8의 원본 id(source)가 체크포인트 백본과 같을 때 그 폴더를 쓴다. 켜질 때와 같은 경로로 올려 본다.
RUN if [ "$WITH_ML" = "1" ]; then \
      python -c "import quant_int8 as Q; print('wavlm int8:', Q.export_base('microsoft/wavlm-large', 'models/wavlm_large_int8'))" && \
      rm -rf "$HF_HOME/hub/models--microsoft--wavlm-large" && \
      python -c "import torch, backbone_service as B, audio2face as A; torch.set_grad_enabled(False); \
loc = A._backbone_location('microsoft/wavlm-large'); p, m = B._load_base(loc, 'cpu'); m(torch.zeros(1, 16000)); \
print('a4 backbone ok:', loc, m.liplab_quant_from, 'torch', torch.__version__)"; \
    fi

# S4 스트리밍 채점 학생(DGOP_STREAM=1일 때만, docs/scorer-stream-chunk-2026-10.md 10절 통과). 가중치는 공개 저장소에 넣지 않고
# dgop_ours처럼 빌드 폴더 backend/models/dgop_stream/(git 제외)에 둔 것을 위의 COPY backend/로 싣는다(DEPLOY.md 10항).
# 파일이 없거나 서버 추론(WITH_ML=1)이 꺼져 있으면 빌드를 멈추고, 켜질 때와 같은 경로(dgop_stream.load_backend)로 학생을 올려
# 1초 무음을 한 번 돌려 본다. 플래그가 0이면 아무것도 하지 않는다(그 폴더가 빌드 폴더에 있으면 이미지에는 들어간다, 약 105MB).
ARG DGOP_STREAM=0
RUN if [ "$DGOP_STREAM" = "1" ]; then \
      test "$WITH_ML" = "1" || { echo "DGOP_STREAM=1은 WITH_ML=1이 필요하다(채점 후처리가 torch를 쓴다)"; exit 1; }; \
      for f in student_w8.onnx calibration.json; do \
        test -s models/dgop_stream/$f || { echo "backend/models/dgop_stream/$f 이 없다(DEPLOY.md 10항)"; exit 1; }; \
      done && \
      DGOP_STREAM=1 DGOP_STREAM_MODEL=/app/models/dgop_stream/student_w8.onnx python -c "import numpy as np, onnxruntime, dgop_stream as S; \
f, v, c = S.load_backend(); al, sc = f(np.zeros(16000, np.float32)); \
assert al.shape == sc.shape == (49, 49), (al.shape, sc.shape); \
print('dgop_stream ok:', c, al.shape, 'onnxruntime', onnxruntime.__version__)"; \
    fi
ENV DGOP_STREAM=$DGOP_STREAM

# 파일럿 자료 파기 도구(§4.7) — 서버에서 fly ssh로 실행한다(scripts/pilot_retention.py 머리말)
COPY scripts/pilot_retention.py ./scripts/pilot_retention.py

# Copy built frontend from stage 1
COPY --from=frontend-builder /frontend/dist ./frontend/dist
# 아바타 GLB는 fly 프록시가 압축하지 않으므로 미리 gzip해 두고 gzip을 받는 요청에 그것을 보낸다(2.5MB → 1.5MB,
# backend/static_serving.py).
RUN python static_serving.py precompress frontend/dist

# Create directory for SQLite database (if used)
RUN mkdir -p /data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run FastAPI with Uvicorn
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
