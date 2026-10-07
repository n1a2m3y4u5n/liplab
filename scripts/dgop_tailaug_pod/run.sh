#!/bin/bash
# 파드 쪽: 끝 무음 증강 재학습과 측정(docs/dgop-aligner-tailaug-2026-10.md). session.sh가 /workspace/ta에 풀고 띄운다.
# 다시 불러도 끝난 단계는 건너뛴다. 표식(/workspace/dax/logs/ta.log):
#   TA_SETUP_OK TA_MFAPREP_OK TA_DATA_OK TA_DRY_OK TA_TRAIN_AL_OK TA_TRAIN_SC_OK|TA_TRAIN_SC_FAIL TA_EXPORT_OK
#   TA_SELFTEST_OK TA_MAIN_OK TA_HYP_OK TA_ZEROTH_OK|TA_ZEROTH_SKIP TA_MFA_OK|TA_MFA_SKIP TA_LAT_OK TA_OK / TA_FAIL
set -u
W=/workspace
R=$W/ta
L=$W/dax/logs
O=$R/out
CK=$W/ckpt
mkdir -p "$L" "$O" "$CK"
exec >> "$L/ta.log" 2>&1
echo $$ > "$L/ta.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "TA_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; echo "TA_$2_OK"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1
echo "=== [ta] start pid=$$ nproc=$(nproc) mem=$(free -g | awk '/Mem:/ {print $2}')G cpu.max=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null)"

# cgroup 할당 코어(보이는 코어보다 적다) 기준으로 워커 수
Q=$(awk '{ if ($1 != "max" && $2 > 0) printf "%d", $1 / $2; }' /sys/fs/cgroup/cpu.max 2>/dev/null)
[ -n "$Q" ] && [ "$Q" -gt 0 ] 2>/dev/null || Q=$(nproc)
WK=$(( Q > 14 ? 12 : (Q > 6 ? Q - 2 : 4) ))
echo "cores=$Q workers=$WK"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" "accelerate>=1.2" safetensors soundfile "numpy==2.2.6" scipy \
    "faster-whisper>=1.1" "datasets>=3,<4" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, accelerate, datasets, numpy, librosa; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'acc', accelerate.__version__, 'ds', datasets.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))" || fail env
echo "TA_SETUP_OK"
M=$R/scripts/measure.py

if ! done_ mfaprep; then
  HF_HUB_OFFLINE=1 DGOP_DEVICE=cpu $PY $M mfaprep $R $R/mfa > $L/mfaprep.log 2>&1 || { tail -n 5 $L/mfaprep.log; fail mfaprep; }
  mark mfaprep MFAPREP
fi
# MFA(독립 참조)는 CPU로 학습과 함께 돈다. 실패해도 학습은 계속한다(판정에서 C2를 측정할 수 없게 될 뿐)
if [ ! -f "$R/mfa/.mfa_done" ]; then
  ( bash $R/scripts/mfa.sh > $L/mfa.log 2>&1; touch $R/mfa/.mfa_done ) &
  echo $! > $L/mfa.pid
fi

if ! done_ data; then
  say "Zeroth 받기"
  $PY -c "
from datasets import load_dataset
for s in ('train', 'test'):
    d = load_dataset('kresnik/zeroth_korean', split=s); print(s, len(d))
" > $L/data.log 2>&1 || { tail -n 5 $L/data.log; fail data; }
  cat $L/data.log
  mark data DATA
fi
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
TR=$R/scripts/train_aligner.py
SRC=$R/models/scorer_fp32

if ! done_ dry; then
  say "배관 점검(3스텝)"
  $PY $TR --from $SRC --out $CK/dry --bf16 --pad-aug --max-steps 3 --workers $WK > $L/dry.log 2>&1 || { tail -n 20 $L/dry.log; fail dry; }
  rm -rf $CK/dry
  mark dry DRY
fi
if ! done_ train_al; then
  say "정렬기 학습(저하 0~4 + 끝 무음 증강, 4에폭)"
  $PY $TR --from $SRC --out $CK/aligner_ta --bf16 --pad-aug --epochs 4 --workers $WK > $L/train_al.log 2>&1 || { tail -n 30 $L/train_al.log; fail train_al; }
  grep -q "저장 완료" $L/train_al.log || fail "train_al 저장 없음"
  mark train_al TRAIN_AL
fi
if ! done_ train_sc; then
  say "채점기 이어 학습(저하 없음 + 끝 무음 증강, 2에폭)"
  if $PY $TR --from $SRC --out $CK/scorer_ta --bf16 --pad-aug --severities 0 --epochs 2 --workers $WK > $L/train_sc.log 2>&1 \
     && grep -q "저장 완료" $L/train_sc.log; then
    mark train_sc TRAIN_SC
  else
    tail -n 30 $L/train_sc.log; echo "TA_TRAIN_SC_FAIL"; touch "$O/.done_train_sc"
  fi
fi
if ! done_ export; then
  say "int8 변환"
  mkdir -p $R/models/ta
  WAV=$(ls $R/data/c538wav/*.wav | head -n 1)
  DGOP_DEVICE=cpu $PY $R/scripts/export_int8.py $CK/aligner_ta $R/models/ta/aligner --wav "$WAV" > $L/export_al.log 2>&1 || { cat $L/export_al.log; fail export_al; }
  if [ -s $CK/scorer_ta/model.safetensors ]; then
    DGOP_DEVICE=cpu $PY $R/scripts/export_int8.py $CK/scorer_ta $R/models/ta/scorer --wav "$WAV" > $L/export_sc.log 2>&1 || { cat $L/export_sc.log; fail export_sc; }
  fi
  cat $L/export_*.log
  ( cd $R/models/ta && sha256sum */model.int8.safetensors ) | tee $O/ta_int8.sha256
  mark export EXPORT
fi

export DGOP_DEVICE=cuda BACKBONE_QUANT=int8
if ! done_ selftest; then
  $PY $M selftest $R > $L/selftest.log 2>&1 || { tail -n 10 $L/selftest.log; fail selftest; }
  cat $L/selftest.log | tail -n 2
  mark selftest SELFTEST
fi
if ! done_ main; then
  say "main·tts 시작"
  PIDS=""
  for i in 0 1 2 3; do $PY $M main $R $O/main.$i.jsonl --shard $i/4 > $L/main.$i.log 2>&1 & PIDS="$PIDS $!"; done
  for i in 0 1; do $PY $M tts $R $O/tts.$i.jsonl --shard $i/2 > $L/tts.$i.log 2>&1 & PIDS="$PIDS $!"; done
  wait $PIDS
  [ "$(cat $L/main.*.log | grep -c 'MEASURE_OK main')" = 4 ] || fail main
  [ "$(cat $L/tts.*.log | grep -c 'MEASURE_OK tts')" = 2 ] || fail tts
  mark main MAIN
fi
if ! done_ hyp; then
  say "hyp 시작"
  PIDS=""
  for i in 0 1; do $PY $M hyp $R $O/hyp.$i.jsonl --shard $i/2 > $L/hyp.$i.log 2>&1 & PIDS="$PIDS $!"; done
  wait $PIDS
  [ "$(cat $L/hyp.*.log | grep -c 'MEASURE_OK hyp')" = 2 ] || fail hyp
  mark hyp HYP
fi
if ! done_ zeroth; then
  say "zeroth 시작(제한 20분)"
  if timeout 1200 $PY $M zeroth $R $O/zeroth.0.jsonl > $L/zeroth.log 2>&1; then
    mark zeroth ZEROTH
  else
    tail -n 5 $L/zeroth.log; echo "TA_ZEROTH_SKIP"; touch "$O/.done_zeroth"
  fi
fi
if ! done_ mfa; then
  say "MFA 기다림(최대 40분)"
  for _ in $(seq 1 240); do [ -f $R/mfa/.mfa_done ] && break; sleep 10; done
  if grep -q "^MFA_ALIGN_OK" $L/mfa.log 2>/dev/null && $PY $M mfaparse $R $R/mfa $O/mfa.jsonl > $L/mfaparse.log 2>&1; then
    tail -n 1 $L/mfaparse.log; mark mfa MFA
  else
    tail -n 15 $L/mfa.log; echo "TA_MFA_SKIP"; touch "$O/.done_mfa"
  fi
fi
if ! done_ lat; then
  say "지연(CPU 2스레드, 짝마다 따로)"
  for p in K0 A B; do
    DGOP_DEVICE=cpu OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY $M latency $R $O/latency_$p.json --pair $p --threads 2 > $L/lat_$p.log 2>&1 || tail -n 3 $L/lat_$p.log
  done
  mark lat LAT
fi
for d in aligner_ta scorer_ta; do
  [ -d $CK/$d ] && { mkdir -p $O/train/$d; cp $CK/$d/*.json $O/train/$d/ 2>/dev/null; f=$(ls -d $CK/$d/checkpoint-* 2>/dev/null | tail -n 1); [ -n "$f" ] && cp $f/trainer_state.json $O/train/$d/; }
done
tar -czf $W/ta_result.tgz -C $W ta/out dax/logs || fail tar
ls -la $W/ta_result.tgz
echo "TA_OK"
