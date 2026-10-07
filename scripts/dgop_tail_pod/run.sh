#!/bin/bash
# 파드 쪽 끝 모음 측정(docs/dgop-final-vowel-2026-10.md). session.sh가 /workspace/fv에 풀고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 표식(/workspace/dax/logs/fv.log): FV_SETUP_OK FV_SELFTEST_OK FV_MAIN_OK FV_TTS_OK FV_HYP_OK FV_ZEROTH_OK|FV_ZEROTH_SKIP FV_OK / FV_FAIL
set -u
W=/workspace
R=$W/fv
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/fv.log" 2>&1
echo $$ > "$L/fv.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "FV_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; echo "FV_$2_OK"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1
echo "=== [fv] start pid=$$ nproc=$(nproc) mem=$(free -g | awk '/Mem:/ {print $2}')G"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" "datasets>=3,<4" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, faster_whisper, numpy; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available())" || fail env
$PY -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" || fail "cuda 없음"
echo "FV_SETUP_OK"
export DGOP_DEVICE=cuda BACKBONE_QUANT=int8
M=$R/scripts/measure.py
if ! done_ selftest; then
  HF_HUB_OFFLINE=1 $PY $M selftest $R || fail selftest
  mark selftest SELFTEST
fi
if ! done_ main; then
  say "main·tts 시작"
  for i in 0 1 2 3; do HF_HUB_OFFLINE=1 $PY $M main $R $O/main.$i.jsonl --shard $i/4 --dump $O/lp > $L/main.$i.log 2>&1 & done
  for i in 0 1; do HF_HUB_OFFLINE=1 $PY $M tts $R $O/tts.$i.jsonl --shard $i/2 > $L/tts.$i.log 2>&1 & done
  wait
  [ "$(cat $L/main.*.log | grep -c 'MEASURE_OK main')" = 4 ] || fail main
  [ "$(cat $L/tts.*.log | grep -c 'MEASURE_OK tts')" = 2 ] || fail tts
  echo "FV_TTS_OK"
  mark main MAIN
fi
if ! done_ hyp; then
  say "hyp 시작"
  for i in 0 1; do $PY $M hyp $R $O/hyp.$i.jsonl --shard $i/2 --which int8,fp32,kresnik > $L/hyp.$i.log 2>&1 & done
  wait
  [ "$(cat $L/hyp.*.log | grep -c 'MEASURE_OK hyp')" = 2 ] || fail hyp
  mark hyp HYP
fi
if ! done_ zeroth; then
  say "zeroth 시작(제한 30분)"
  if timeout 1800 $PY $M zeroth $R $O/zeroth.0.jsonl --n-test 500 --n-train 1000 > $L/zeroth.log 2>&1; then
    mark zeroth ZEROTH
  else
    tail -n 5 $L/zeroth.log; echo "FV_ZEROTH_SKIP"; touch "$O/.done_zeroth"
  fi
fi
tar -czf $W/fv_result.tgz -C $W fv/out dax/logs || fail tar
ls -la $W/fv_result.tgz
echo "FV_OK"
