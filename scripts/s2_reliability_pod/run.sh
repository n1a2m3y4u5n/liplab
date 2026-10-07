#!/bin/bash
# 파드 쪽 S2 측정(docs/phoneme-feedback-reliability-2026-10.md). session.sh가 /workspace/s2에 풀고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 표식(/workspace/dax/logs/s2.log): S2_SETUP_OK S2_SELFTEST_OK S2_RUN_OK S2_OK / S2_FAIL
set -u
W=/workspace
R=$W/s2
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/s2.log" 2>&1
echo $$ > "$L/s2.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "S2_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1
NC=$(nproc)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
SH=$(( NC > 8 ? 8 : NC )); [ "$SH" -lt 2 ] && SH=2
echo "=== [s2] start pid=$$ cpus=$NC shards=$SH mem=$(free -g | awk '/Mem:/ {print $2}')G"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, faster_whisper, numpy; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())" || fail env
$PY -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" || fail "cuda 없음"
echo "S2_SETUP_OK"
export DGOP_DEVICE=cuda BACKBONE_QUANT=int8 HF_HUB_OFFLINE=1
M=$R/scripts/measure.py
if [ ! -f "$O/.done_selftest" ]; then
  $PY $M selftest $R || fail selftest
  touch "$O/.done_selftest"; echo "S2_SELFTEST_OK"
fi
if [ ! -f "$O/.done_run" ]; then
  say "run 시작(샤드 $SH)"
  for i in $(seq 0 $((SH - 1))); do $PY $M run $R $O/run.$i.jsonl --shard $i/$SH > $L/run.$i.log 2>&1 & done
  wait
  [ "$(cat $L/run.*.log | grep -c 'MEASURE_OK run')" = "$SH" ] || fail run
  touch "$O/.done_run"; echo "S2_RUN_OK $(cat $O/run.*.jsonl | wc -l) err=$(cat $O/run.*.jsonl | grep -c '"error"')"
fi
tar -czf $W/s2_result.tgz -C $W s2/out dax/logs || fail tar
ls -la $W/s2_result.tgz
echo "S2_OK"
