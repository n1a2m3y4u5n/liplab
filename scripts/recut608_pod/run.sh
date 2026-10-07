#!/bin/bash
# 파드 쪽 608 다시 자르기·채점(docs/scoring-608-recut-2026-10.md). session.sh가 /workspace/rc에 풀고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 표식(/workspace/dax/logs/rc.log 줄 맨 앞): RC_SETUP_OK RC_SELFTEST_OK RECUT_OK DGOP_OLD_OK ASR_OK DGOP_NEW_OK S4_OK LATENCY_OK RC_OK / RC_FAIL
set -u
W=/workspace
R=$W/rc
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/rc.log" 2>&1
echo $$ > "$L/rc.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "RC_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_DISABLE_PROGRESS_BARS=1
NC=$(python3 -c "import os
def rd(p):
    try: return open(p).read().split()
    except OSError: return None
q = rd('/sys/fs/cgroup/cpu.max')
if q and q[0] != 'max': print(max(1, int(int(q[0]) / int(q[1])))); raise SystemExit
a, b = rd('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'), rd('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
if a and b and int(a[0]) > 0: print(max(1, int(int(a[0]) / int(b[0])))); raise SystemExit
print(min(8, os.cpu_count()))")
WK=$(( NC / 2 )); [ "$WK" -lt 1 ] && WK=1; [ "$WK" -gt 6 ] && WK=6
echo "=== [rc] start pid=$$ cpus=$NC workers=$WK mem=$(free -g | awk '/Mem:/ {print $2}')G"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" "librosa==0.11.0" \
    "onnx>=1.17" "onnxruntime>=1.20" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
SP=$($PY -c "import site; print(site.getsitepackages()[0])")
WLD="$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
$PY -c "import torch, transformers, faster_whisper, onnxruntime, numpy; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'ort', onnxruntime.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())" || fail env
LD_LIBRARY_PATH=$WLD $PY -c "import ctranslate2; print('ct2', ctranslate2.__version__, 'cuda', ctranslate2.get_cuda_device_count())" || fail ct2
(cd "$R/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC") || fail "acoustic import(old)"
(cd "$R/backend_new" && $PY -c "import dgop_acoustic as DA; assert DA.HAS_ACOUSTIC and hasattr(DA, 'trim_trailing_silence')") || fail "acoustic import(new)"
echo "RC_SETUP_OK"
X=$R/scripts/recut.py
export RC_ROOT=$R
$PY $X selftest || fail selftest
if ! done_ recut; then
  LD_LIBRARY_PATH=$WLD $PY $X recut || fail recut
  mark recut
fi
if ! done_ dgop_old; then
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $X dgop_old "$WK" || fail dgop_old
  mark dgop_old
fi
if ! done_ asr; then
  OMP_NUM_THREADS=2 $PY $X asr "$WK" || fail asr
  mark asr
fi
if ! done_ dgop_new; then
  OMP_NUM_THREADS=4 $PY $X dgop_new || fail dgop_new
  mark dgop_new
fi
if ! done_ s4; then
  OMP_NUM_THREADS=4 $PY $X s4 || fail s4
  mark s4
fi
if ! done_ latency; then
  LAT_THREADS=2 $PY $X latency || fail latency
  mark latency
fi
tar -czf $W/rc_result.tgz -C $R out/recut.json out/dgop_full_recut.jsonl out/tscore_recut.jsonl out/asr_recut.json out/trim_recut.jsonl \
  out/s4_recut.jsonl out/lp $(cd $R && ls out/lat_*.json) -C $W dax/logs || fail tar
ls -la $W/rc_result.tgz
echo "RC_OK"
