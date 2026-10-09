#!/bin/bash
# 파드 쪽 608 새 화자 확인 채점(docs/scoring-608-newspk-2026-10.md 3절). session.sh가 /workspace/ns에 풀고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 표식(/workspace/dax/logs/ns.log 줄 맨 앞): NS_SETUP_OK NS_SELFTEST_OK DGOP_OLD_OK DGOP_NEW_OK ASR_OK NS_OK / NS_FAIL
set -u
W=/workspace
R=$W/ns
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/ns.log" 2>&1
echo $$ > "$L/ns.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "NS_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_DISABLE_PROGRESS_BARS=1
# CPU 할당은 cgroup v2(cpu.max)·v1(cfs_quota) 순으로 본다(nproc만 보면 할당보다 많은 작업자가 떠서 OOM, KSC 10/9 사고)
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
MEMG=$(python3 -c "
try: v=int(open('/sys/fs/cgroup/memory.max').read())
except Exception:
    try: v=int(open('/sys/fs/cgroup/memory/memory.limit_in_bytes').read())
    except Exception: v=0
print(v//2**30 if 0 < v < 2**50 else 0)")
if [ "$MEMG" -gt 0 ] && [ "$WK" -gt $(( MEMG / 4 )) ]; then WK=$(( MEMG / 4 )); [ "$WK" -lt 1 ] && WK=1; fi
echo "=== [ns] start pid=$$ cpus=$NC workers=$WK mem_limit=${MEMG}G mem=$(free -g | awk '/Mem:/ {print $2}')G"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, faster_whisper, numpy; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__)" || fail env
(cd "$R/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC and not hasattr(DA, 'trim_trailing_silence')") || fail "acoustic import(old)"
(cd "$R/backend_new" && $PY -c "import dgop_acoustic as DA; assert DA.HAS_ACOUSTIC and hasattr(DA, 'trim_trailing_silence')") || fail "acoustic import(new)"
echo "NS_SETUP_OK"
X=$R/scripts/newspk.py
export NS_ROOT=$R
$PY $X selftest || fail selftest
if ! done_ dgop_old; then
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $X dgop_old "$WK" || fail dgop_old
  mark dgop_old
fi
if ! done_ dgop_new; then
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $X dgop_new "$WK" || fail dgop_new
  mark dgop_new
fi
if ! done_ asr; then
  OMP_NUM_THREADS=2 $PY $X asr "$WK" || fail asr
  mark asr
fi
tar -czf $W/ns_result.tgz -C $R out/dgop_old.jsonl out/dgop_new.jsonl out/tscore.jsonl out/asr.json -C $W dax/logs || fail tar
ls -la $W/ns_result.tgz
echo "NS_OK"
