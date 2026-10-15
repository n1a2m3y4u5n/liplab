#!/bin/bash
# 문장 점수 규칙 후보 파드 쪽(docs/scoring-rules-2026-10.md). run_c27.sh(10/9)의 venv·점검 부분을 그대로 쓰고 단계만 바꾼 판.
#   bash run_sr.sh explore   jobs.json(538 절반 0·범주 28 절반 0·범주 27 첫 묶음) → out/feat_explore.jsonl
#   bash run_sr.sh confirm   범주 27 두 번째 묶음 자르기(large-v3, GPU) → 고르기·짝 → 특성, 그리고 jobs.json(538·범주 28 절반 1) 특성
# 표식(/workspace/dax/logs/sr.log): SR_SETUP_OK [SEG_OK B2JOBS_OK] FEAT_DONE… SR_OK / SR_FAIL
set -u
PH=${1:?explore|confirm}
W=/workspace
L=$W/dax/logs
O=$W/out
mkdir -p "$L" "$O"
exec >> "$L/sr.log" 2>&1
echo $$ > "$L/sr.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "SR_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false SR_W=$W SR_BACKEND=$W/backend

NC=$(nproc)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -z "$Q" ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
  Q=$(awk -v p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)" '{ if ($1 > 0) print int($1 / p) }' /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
fi
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
WK=$(( NC / 2 )); [ "$WK" -lt 1 ] && WK=1
MEMG=$(free -g | awk '/Mem:/ {print $2}')
MAXW=$(( MEMG / 3 )); [ "$MAXW" -ge 1 ] && [ "$WK" -gt "$MAXW" ] && WK=$MAXW
echo "=== [sr $PH] start pid=$$ cpus=$NC mem=${MEMG}G workers=$WK"

for f in "$W/backend/dgop_acoustic.py" "$W/backend/data/dgop_calibration_ours.json" "$W/backend/models/dgop_ours/aligner/model.int8.safetensors" \
         "$W/backend/models/dgop_ours/scorer/model.int8.safetensors" "$W/tools/feat_pod.py" "$W/tools/targets.py" "$W/jobs.json"; do
  [ -e "$f" ] || fail "없음: $f"
done
for m in aligner scorer; do [ ! -e "$W/backend/models/dgop_ours/$m/model.safetensors" ] || fail "fp32 가중치가 있음($m)"; done

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail "vapp venv"
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail "torch"
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy || fail "의존"
  if ! "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt"; then
    (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libavformat-dev libavcodec-dev \
      libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev) || fail "apt av"
    "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt" || fail "backend requirements"
  fi
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, faster_whisper, numpy, soundfile; print('ENVAPP torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())" || fail "vapp 확인"
(cd "$W/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC and hasattr(DA, 'retime_tail')") || fail "acoustic import"
(cd "$W/tools" && $PY feat_pod.py selftest) | tee "$L/selftest.txt"
grep -q SR_SELFTEST_OK "$L/selftest.txt" || fail selftest
echo "SR_SETUP_OK"

if [ "$PH" = confirm ]; then
  [ -d "$W/c27b2/s608" ] || fail "c27b2 없음"
  if [ ! -f "$W/vseg/.ok" ]; then
    say "vseg 설치"
    python3 -m venv "$W/vseg" || fail "vseg venv"
    "$W/vseg/bin/pip" install -q --upgrade pip
    "$W/vseg/bin/pip" install -q --no-deps "faster-whisper==0.10.1" || fail "vseg faster-whisper"
    "$W/vseg/bin/pip" install -q "ctranslate2>=3.22,<4" "huggingface_hub>=0.13" "tokenizers>=0.13,<0.16" "onnxruntime>=1.14,<2" \
      "nvidia-cublas-cu11" "nvidia-cudnn-cu11==8.9.6.50" soundfile "numpy<2" "av>=11,<13" || fail "vseg 의존"
    touch "$W/vseg/.ok"
  fi
  SEGLIB=$("$W/vseg/bin/python" -c "import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ':' + os.path.dirname(nvidia.cudnn.lib.__file__))")
  export SEG_LD="$SEGLIB:${LD_LIBRARY_PATH:-}"
  LD_LIBRARY_PATH=$SEG_LD "$W/vseg/bin/python" -c "import ctranslate2, faster_whisper; print('ENVSEG ct2', ctranslate2.__version__, 'fw', faster_whisper.__version__, 'cuda', ctranslate2.get_cuda_device_count())" || fail "vseg 확인"
  (cd "$W/tools" && $PY feat_pod.py b2prep) || fail b2prep
  if [ ! -s "$W/c27b2/out/cuts608.json" ]; then
    say "seg c27b2"
    (cd "$W/scripts" && LD_LIBRARY_PATH=$SEG_LD "$W/vseg/bin/python" -c "
import os
import speak_asr_pod_run as m
m.W = '/workspace/c27b2'; m.OUT = '/workspace/c27b2/out'
os.makedirs(m.OUT, exist_ok=True); os.makedirs('/workspace/c27b2/cuts', exist_ok=True)
m.cut_608()
print('SEG DONE')") || fail "seg"
  fi
  echo "SEG_OK $(python3 -c "import json; c=json.load(open('$W/c27b2/out/cuts608.json')); print(len(c), sum(1 for x in c if x['cut']), len({x['file'] for x in c if x['cut']}))")"
  (cd "$W/tools" && $PY feat_pod.py b2jobs) || fail b2jobs
  (cd "$W/tools" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY feat_pod.py feat "$W/jobs_b2.json" "$O/feat_b2.jsonl" "$WK") || fail "feat b2"
  (cd "$W/tools" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY feat_pod.py feat "$W/jobs.json" "$O/feat_confirm.jsonl" "$WK") || fail "feat confirm"
  cd "$W" && tar -czf "$W/sr_result.tgz" out/feat_b2.jsonl out/feat_confirm.jsonl jobs_b2.json c27b2/out/cuts608.json dax/logs/sr.log dax/logs/selftest.txt || fail tar
else
  (cd "$W/tools" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY feat_pod.py feat "$W/jobs.json" "$O/feat_explore.jsonl" "$WK") || fail "feat explore"
  cd "$W" && tar -czf "$W/sr_result.tgz" out/feat_explore.jsonl dax/logs/sr.log dax/logs/selftest.txt || fail tar
fi
echo "ERRORS $(grep -c '"error"' $O/feat_*.jsonl | tr '\n' ' ')"
echo "SR_OK"
