#!/bin/bash
# 파드 쪽: 끝 구간 다시 나누기 확인 측정(docs/dgop-final-vowel-fix2-2026-10.md). session.sh가 /workspace/al에 풀고 띄운다.
# 다시 불러도 끝난 단계는 건너뛴다. 표식(/workspace/dax/logs/al.log):
#   AL_SETUP_OK AL_MFAPREP_OK AL_SELFTEST_OK AL_MAIN_OK AL_MFA_OK|AL_MFA_SKIP AL_CPU_OK AL_OK / AL_FAIL
set -u
W=/workspace
R=$W/al
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/al.log" 2>&1
echo $$ > "$L/al.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "AL_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; echo "AL_$2_OK"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
echo "=== [al] start pid=$$ nproc=$(nproc) mem=$(free -g | awk '/Mem:/ {print $2}')G cpu.max=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null)"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" "accelerate>=1.2" safetensors soundfile "numpy==2.2.6" scipy \
    "faster-whisper>=1.1" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, numpy, librosa; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'numpy', numpy.__version__, 'librosa', librosa.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))" || fail env
echo "AL_SETUP_OK"
M=$R/scripts/measure.py
export HF_HUB_OFFLINE=1

if ! done_ mfaprep; then
  DGOP_DEVICE=cpu $PY $M mfaprep $R $R/mfa > $L/mfaprep.log 2>&1 || { tail -n 5 $L/mfaprep.log; fail mfaprep; }
  tail -n 1 $L/mfaprep.log
  mark mfaprep MFAPREP
fi
# MFA(독립 참조)는 CPU로 측정과 함께 돈다. 실패해도 측정은 계속한다(C2를 판정할 수 없게 될 뿐)
if [ ! -f "$R/mfa/.mfa_done" ]; then
  ( bash $R/scripts/mfa.sh > $L/mfa.log 2>&1; touch $R/mfa/.mfa_done ) &
  echo $! > $L/mfa.pid
fi

export DGOP_DEVICE=cuda BACKBONE_QUANT=int8
if ! done_ selftest; then
  $PY $M selftest $R > $L/selftest.log 2>&1 || { tail -n 10 $L/selftest.log; fail selftest; }
  tail -n 1 $L/selftest.log
  mark selftest SELFTEST
fi
if ! done_ main; then
  say "main·tts·deg 시작"
  PIDS=""
  for i in 0 1 2; do $PY $M main $R $O/main.$i.jsonl --shard $i/3 > $L/main.$i.log 2>&1 & PIDS="$PIDS $!"; done
  for i in 0 1; do $PY $M tts $R $O/tts.$i.jsonl --shard $i/2 > $L/tts.$i.log 2>&1 & PIDS="$PIDS $!"; done
  for i in 0 1; do $PY $M deg $R $O/deg.$i.jsonl --shard $i/2 > $L/deg.$i.log 2>&1 & PIDS="$PIDS $!"; done
  wait $PIDS
  [ "$(cat $L/main.*.log | grep -c 'MEASURE_OK main')" = 3 ] || fail main
  [ "$(cat $L/tts.*.log | grep -c 'MEASURE_OK tts')" = 2 ] || fail tts
  [ "$(cat $L/deg.*.log | grep -c 'MEASURE_OK deg')" = 2 ] || fail deg
  mark main MAIN
fi
if ! done_ mfa; then
  say "MFA 기다림(최대 40분)"
  for _ in $(seq 1 240); do [ -f $R/mfa/.mfa_done ] && break; sleep 10; done
  if grep -q "^MFA_ALIGN_OK" $L/mfa.log 2>/dev/null && $PY $M mfaparse $R $R/mfa $O/mfa.jsonl > $L/mfaparse.log 2>&1; then
    tail -n 1 $L/mfaparse.log; mark mfa MFA
  else
    tail -n 15 $L/mfa.log; echo "AL_MFA_SKIP"; touch "$O/.done_mfa"
  fi
fi
if ! done_ cpu; then
  say "CPU 2스레드 지연·경로 일치"
  DGOP_DEVICE=cpu OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $M cpu $R $O/cpu.json "$O/main.*.jsonl" --threads 2 > $L/cpu.log 2>&1 || { tail -n 5 $L/cpu.log; fail cpu; }
  mark cpu CPU
fi
tar -czf $W/al_result.tgz -C $W al/out dax/logs || fail tar
ls -la $W/al_result.tgz
echo "AL_OK"
