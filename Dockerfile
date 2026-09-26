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
# 이미지에 미리 받아 둔다. 기계가 자동으로 멈췄다 켜질 때마다 다시 받지 않게 하려는 것이다.
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

# 파일럿 자료 파기 도구(§4.7) — 서버에서 fly ssh로 실행한다(scripts/pilot_retention.py 머리말)
COPY scripts/pilot_retention.py ./scripts/pilot_retention.py

# Copy built frontend from stage 1
COPY --from=frontend-builder /frontend/dist ./frontend/dist

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
