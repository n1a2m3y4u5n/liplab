#!/bin/bash
# S20 파드 쪽(docs/speak-intelligibility-index-2026-10.md 8.2절). session.sh가 /workspace/s20에 풀고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 표식(/workspace/dax/logs/s20.log 줄 맨 앞): S20_SETUP_OK S20_SELFTEST_OK ASR_V3_OK ASR_BASE_OK DGOP_OK ACOUSTIC_OK S20_OK / S20_FAIL
set -u
W=/workspace
R=$W/s20
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/s20.log" 2>&1
echo $$ > "$L/s20.pid"
fail() { echo "S20_FAIL $*"; exit 1; }
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
echo "=== [s20] start pid=$$ cpus=$NC workers=$WK mem=$(free -g | awk '/Mem:/ {print $2}')G"
if [ ! -f "$W/vapp/.ok" ]; then
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" "librosa==0.11.0" \
    "praat-parselmouth==0.4.7" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
SP=$($PY -c "import site; print(site.getsitepackages()[0])")
WLD="$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
$PY -c "import torch, transformers, faster_whisper, numpy, parselmouth; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'pm', parselmouth.__version__, 'cuda', torch.cuda.is_available())" || fail env
LD_LIBRARY_PATH=$WLD $PY -c "import ctranslate2; print('ct2', ctranslate2.__version__, 'cuda', ctranslate2.get_cuda_device_count())" || fail ct2
(cd "$R/backend" && $PY -c "import dgop_acoustic as DA; assert DA.HAS_ACOUSTIC and hasattr(DA, 'trim_trailing_silence')") || fail "acoustic import"
echo "S20_SETUP_OK"
X=$R/scripts/s20.py
export S20_ROOT=$R
$PY $X selftest || fail selftest
echo "S20_SELFTEST_OK"
if ! done_ asr_v3; then LD_LIBRARY_PATH=$WLD $PY $X asr_v3 || fail asr_v3; mark asr_v3; fi
if ! done_ dgop; then OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $X dgop "$WK" || fail dgop; mark dgop; fi
if ! done_ asr_base; then OMP_NUM_THREADS=2 $PY $X asr_base "$WK" || fail asr_base; mark asr_base; fi
if ! done_ acoustic; then OMP_NUM_THREADS=1 $PY $X acoustic "$NC" || fail acoustic; mark acoustic; fi
tar -czf $W/s20_result.tgz -C $R out/asr_v3.jsonl out/asr_base.jsonl out/dgop.jsonl out/acoustic.jsonl -C $W dax/logs || fail tar
ls -la $W/s20_result.tgz
echo "S20_OK"
