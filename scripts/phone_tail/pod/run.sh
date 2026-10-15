#!/bin/bash
# 파드 쪽(docs/phone-tail-2026-10.md 6.1절, docs/scorer-stream-latency-2026-10.md 5절). session.sh가 /workspace/pt에 풀고 띄운다.
# 표식(/workspace/dax/logs/pt.log): PT_SETUP_OK PT_LP_OK PT_EXPORT_OK PT_FID_OK PT_LAT_OK PT_OK / PT_FAIL
set -u
W=/workspace
R=$W/pt
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/pt.log" 2>&1
echo $$ > "$L/pt.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "PT_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1 S4_W=$R
echo "=== [pt] start pid=$$ nproc=$(nproc) mem=$(free -g | awk '/Mem:/ {print $2}')G"
if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy \
    "onnx==1.23.2" "onnxruntime==1.23.2" "huggingface_hub>=0.34" hf_xet "faster-whisper>=1.1" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, onnx, onnxruntime, numpy, faster_whisper; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'onnx', onnx.__version__, 'ort', onnxruntime.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())" || fail env
echo "PT_SETUP_OK"
export DGOP_DEVICE=cuda BACKBONE_QUANT=int8
if [ ! -f "$O/.done_lp" ]; then
  say "A1 로그확률(샤드 4)"
  for i in 0 1 2 3; do HF_HUB_OFFLINE=1 $PY $R/scripts/measure_lp.py $R $O --shard $i/4 > $L/lp.$i.log 2>&1 & done
  wait
  [ "$(cat $L/lp.*.log | grep -c '^LP_OK')" = 4 ] || fail lp
  touch "$O/.done_lp"; echo "PT_LP_OK n=$(ls $O/lp_n | wc -l) t=$(ls $O/lp_t | wc -l)"
fi
if [ ! -f "$O/.done_export" ]; then
  (cd $R/scripts && CUDA_VISIBLE_DEVICES="" $PY stream_lat.py export) || fail export
  touch "$O/.done_export"; echo "PT_EXPORT_OK"
fi
if [ ! -f "$O/.done_fid" ]; then
  (cd $R/scripts && $PY stream_lat.py fidelity) || fail fidelity
  touch "$O/.done_fid"; echo "PT_FID_OK"
fi
if [ ! -f "$O/.done_lat" ]; then
  (cd $R/scripts && HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES="" OMP_NUM_THREADS=2 $PY stream_lat.py latency) || fail latency
  touch "$O/.done_lat"; echo "PT_LAT_OK"
fi
tar -czf $W/pt_result.tgz -C $W pt/out dax/logs --exclude 'pt/out/*.onnx' || fail tar
ls -la $W/pt_result.tgz
echo "PT_OK"
