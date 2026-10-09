#!/bin/bash
# 파드 쪽: 608 도메인 적응 전체 흐름(docs/dgop-608-adapt-2026-10.md 6·10절). session.sh가 /workspace/ad에 풀고 띄운다.
# 다시 불러도 끝난 단계는 건너뛴다(out/.done_*). 표식(/workspace/dax/logs/ad.log 줄 맨 앞):
#   AD_SETUP_OK AD_PREFETCH_OK AD_SELFTEST_OK AD_SEG_OK AD_R0_OK AD_TRAIN_<이름>_OK|AD_TRAIN_<이름>_FAIL AD_EXPLORE_OK
#   AD_MID_READY AD_F2_OK AD_BRIDGE_OK AD_OK / AD_FAIL
set -u
W=/workspace
R=$W/ad
L=$W/dax/logs
O=$R/out
CK=$W/ckpt
mkdir -p "$L" "$O" "$CK" "$R/models"
exec >> "$L/ad.log" 2>&1
echo $$ > "$L/ad.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "AD_FAIL $*"; exit 1; }
done_() { [ -f "$O/.done_$1" ]; }
mark() { touch "$O/.done_$1"; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false PIP_DISABLE_PIP_VERSION_CHECK=1 \
  HF_HUB_DISABLE_PROGRESS_BARS=1 AD_ROOT=$R OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
NC=$(python3 -c "import os
def rd(p):
    try: return open(p).read().split()
    except OSError: return None
q = rd('/sys/fs/cgroup/cpu.max')
if q and q[0] != 'max': print(max(1, int(int(q[0]) / int(q[1])))); raise SystemExit
a, b = rd('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'), rd('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
if a and b and int(a[0]) > 0: print(max(1, int(int(a[0]) / int(b[0])))); raise SystemExit
print(min(16, os.cpu_count()))")
EW=$(( NC / 3 )); [ "$EW" -lt 2 ] && EW=2; [ "$EW" -gt 6 ] && EW=6      # 채점 작업자(학습과 함께 돌 때)
TW=$(( NC / 4 )); [ "$TW" -lt 2 ] && TW=2; [ "$TW" -gt 4 ] && TW=4      # 학습 데이터로더 작업자(묶음마다)
echo "=== [ad] start pid=$$ cpus=$NC eval_workers=$EW train_workers=$TW mem=$(free -g | awk '/Mem:/ {print $2}')G"

if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" "accelerate>=1.2" safetensors soundfile "numpy==2.2.6" scipy "faster-whisper>=1.1" \
    "datasets>=3,<4" "librosa==0.11.0" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
SP=$($PY -c "import site; print(site.getsitepackages()[0])")
export LD_LIBRARY_PATH="$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
$PY -c "import torch, transformers, faster_whisper, datasets, numpy, librosa; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'ds', datasets.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))" || fail env
$PY -c "import ctranslate2; print('ct2', ctranslate2.__version__, 'cuda', ctranslate2.get_cuda_device_count())" || fail ct2
echo "AD_SETUP_OK"
S=$R/scripts
AL0=$R/models/R0/aligner
SC0=$R/models/R0/scorer

if ! done_ prefetch; then
  say "Zeroth·XLSR-53·large-v3 받기"
  $PY -c "
from datasets import load_dataset
d = load_dataset('kresnik/zeroth_korean', split='train'); print('zeroth train', len(d))
from huggingface_hub import snapshot_download
print(snapshot_download('facebook/wav2vec2-large-xlsr-53', allow_patterns=['*.json', '*.bin', '*.safetensors', '*.txt']))
from faster_whisper import WhisperModel
WhisperModel('large-v3', device='cpu', compute_type='int8'); print('large-v3 ok')
" > $L/prefetch.log 2>&1 || { tail -n 20 $L/prefetch.log; fail prefetch; }
  tail -n 3 $L/prefetch.log
  mark prefetch; echo "AD_PREFETCH_OK"
fi
export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1

if ! done_ selftest; then
  say "시작점 점검: int8 → fp32 → int8이 앱 파일과 같은가, 채점 3클립"
  $PY - > $L/selftest.log 2>&1 <<EOF || { tail -n 30 $L/selftest.log; fail selftest; }
import os, sys, torch, tempfile
sys.path.insert(0, "$S"); sys.path.insert(0, "$R/backend")
import train, quant_int8 as Q
from safetensors.torch import load_file
for m in ("aligner", "scorer"):
    src = "$R/models/R0/" + m
    model, n = train.dequant_model(src)
    d = tempfile.mkdtemp()
    model.save_pretrained(d)
    e = tempfile.mkdtemp()
    Q.export_ctc(d, e)
    a, b = load_file(src + "/model.int8.safetensors"), load_file(e + "/model.int8.safetensors")
    bad = [k for k in a if k not in b or not torch.equal(a[k], b[k])]
    print(m, "linears", n, "tensors", len(a), "different", len(bad), bad[:3])
    assert not bad
print("SELFTEST_REQUANT_OK")
EOF
  $PY $S/evaluate.py pairs R0 $AL0 $SC0 A,538 $O/selftest_rows.jsonl --workers 2 --limit-per-set 3 >> $L/selftest.log 2>&1 || { tail -n 30 $L/selftest.log; fail selftest_eval; }
  tail -n 3 $L/selftest.log
  mark selftest; echo "AD_SELFTEST_OK"
fi

# 기준선 채점은 자르기와 함께 돈다(GPU 공유)
if ! done_ r0; then
  ( $PY $S/evaluate.py pairs R0 $AL0 $SC0 A,B,538 $O/rows_R0.jsonl --workers $EW > $L/eval_R0.log 2>&1 && \
    $PY $S/evaluate.py e2 R0 $AL0 $SC0 538,A,B $O/e2_R0.json --workers $EW > $L/e2_R0.log 2>&1 && touch $O/.done_r0 ) &
  R0PID=$!
fi
if ! done_ seg; then
  say "large-v3 자르기(2 샤드)"
  $PY $S/segment.py whisper $R 0 2 > $L/seg0.log 2>&1 &
  P0=$!
  $PY $S/segment.py whisper $R 1 2 > $L/seg1.log 2>&1 &
  P1=$!
  wait $P0 $P1
  grep -q SEG_WHISPER_OK $L/seg0.log && grep -q SEG_WHISPER_OK $L/seg1.log || { tail -n 20 $L/seg0.log $L/seg1.log; fail seg_whisper; }
  $PY $S/segment.py lists $R > $L/seg_lists.log 2>&1 || { tail -n 20 $L/seg_lists.log; fail seg_lists; }
  tail -n 2 $L/seg_lists.log
  mark seg; echo "AD_SEG_OK"
fi
if ! done_ dry; then
  say "배관 점검(모드마다 3스텝)"
  for md in ctc joint aligner; do
    init=$SC0; [ "$md" = aligner ] && init=$AL0
    $PY $S/train.py --mode $md --init $init --fold F1 --lr 1e-5 --lam 0.2 --seed 0 --steps 3 --out $CK/dry_$md --workers 2 > $L/dry_$md.log 2>&1 \
      || { tail -n 30 $L/dry_$md.log; fail dry_$md; }
    tail -n 2 $L/dry_$md.log
  done
  rm -rf $CK/dry_*
  mark dry; echo "AD_DRY_OK"
fi
[ -n "${R0PID:-}" ] && wait $R0PID
done_ r0 || { tail -n 20 $L/eval_R0.log $L/e2_R0.log; fail r0; }
echo "AD_R0_OK"
NLAB_F1=$($PY -c "import json; print(json.load(open('$O/train_lists.json'))['stats']['F1']['kept'])")
NLAB_F2=$($PY -c "import json; print(json.load(open('$O/train_lists.json'))['stats']['F2']['kept'])")
echo "labeled segments F1=$NLAB_F1 F2=$NLAB_F2"

train_one() {  # 이름 모드 시작점 접기 lr lam 시드
  local name=$1 mode=$2 init=$3 fold=$4 lr=$5 lam=$6 seed=$7
  if done_ "train_$name"; then return 0; fi
  if [ -f "$O/.fail_train_$name" ]; then return 1; fi
  say "학습 $name ($mode, $fold, lr $lr, lam $lam, seed $seed)"
  if $PY $S/train.py --mode $mode --init $init --fold $fold --lr $lr --lam $lam --seed $seed --out $CK/$name --workers $TW > $L/train_$name.log 2>&1 \
     && grep -q TRAIN_OK $L/train_$name.log \
     && $PY $S/export_int8.py $CK/$name $R/models/$name --wav $(ls $R/audio/e538/*.wav | head -n 1) > $L/export_$name.log 2>&1; then
    cp $CK/$name/train_log.json $O/train_log_$name.json
    mark "train_$name"; echo "AD_TRAIN_${name}_OK"; return 0
  fi
  tail -n 30 $L/train_$name.log $L/export_$name.log 2>/dev/null; touch "$O/.fail_train_$name"; echo "AD_TRAIN_${name}_FAIL"; return 1
}
eval_bg() {  # 이름 정렬기 채점기 pairs세트 e2세트 → 배경 실행, PID를 EVPIDS에
  local name=$1 al=$2 sc=$3 ps=$4 es=$5
  if done_ "eval_$name"; then return 0; fi
  ( $PY $S/evaluate.py pairs $name $al $sc $ps $O/rows_$name.jsonl --workers $EW > $L/eval_$name.log 2>&1 && \
    $PY $S/evaluate.py e2 $name $al $sc $es $O/e2_$name.json --workers $EW > $L/e2_$name.log 2>&1 && touch $O/.done_eval_$name ) &
  EVPIDS="${EVPIDS:-} $!"
}
budget_ok() { [ ! -f "$R/STOP_$1" ]; }    # 맥에서 예산 때문에 뺄 후보는 STOP_<이름> 파일로 알린다(8절)

# ── 탐색(F1, 시드 0) ──
EVPIDS=""
if [ "$NLAB_F1" -ge 1000 ]; then
  train_one F1_S1 ctc $SC0 F1 1e-5 0 0 && eval_bg F1_S1 $AL0 $R/models/F1_S1 A,538 538,A
  train_one F1_S2 ctc $SC0 F1 3e-5 0 0 && eval_bg F1_S2 $AL0 $R/models/F1_S2 A,538 538,A
fi
train_one F1_U1 joint $SC0 F1 2e-5 0.2 0 && eval_bg F1_U1 $AL0 $R/models/F1_U1 A,538 538,A
budget_ok U2 && train_one F1_U2 joint $SC0 F1 2e-5 1.0 0 && eval_bg F1_U2 $AL0 $R/models/F1_U2 A,538 538,A
if [ "$NLAB_F1" -ge 1000 ]; then
  budget_ok S1A && done_ train_F1_S1 && train_one F1_AL1 aligner $AL0 F1 1e-5 0 0 && eval_bg F1_S1A $R/models/F1_AL1 $R/models/F1_S1 A,538 538,A
  budget_ok S2A && done_ train_F1_S2 && train_one F1_AL2 aligner $AL0 F1 3e-5 0 0 && eval_bg F1_S2A $R/models/F1_AL2 $R/models/F1_S2 A,538 538,A
fi
for p in $EVPIDS; do wait $p; done
$PY $S/analyze.py explore $O > $L/explore.log 2>&1 || { tail -n 30 $L/explore.log; fail explore; }
cat $L/explore.log
echo "AD_EXPLORE_OK"
PICK=$(awk '/^PICK /{print $2}' $O/judge_explore.txt)
tar -czf $W/ad_mid.tgz -C $R out -C $W dax/logs 2>/dev/null && echo "AD_MID_READY"
if [ -z "$PICK" ] || [ "$PICK" = "None" ]; then
  say "고른 후보 없음 → 확인 생략(6절 2)"
else
  # ── 확인 2(F2, 시드 1): 같은 레시피를 A + C 자료로 ──
  case "$PICK" in
    S1) train_one F2_S1 ctc $SC0 F2 1e-5 0 1 && eval_bg F2_S1 $AL0 $R/models/F2_S1 B,538 538,B ;;
    S2) train_one F2_S2 ctc $SC0 F2 3e-5 0 1 && eval_bg F2_S2 $AL0 $R/models/F2_S2 B,538 538,B ;;
    U1) train_one F2_U1 joint $SC0 F2 2e-5 0.2 1 && eval_bg F2_U1 $AL0 $R/models/F2_U1 B,538 538,B ;;
    U2) train_one F2_U2 joint $SC0 F2 2e-5 1.0 1 && eval_bg F2_U2 $AL0 $R/models/F2_U2 B,538 538,B ;;
    S1A) train_one F2_S1 ctc $SC0 F2 1e-5 0 1 && train_one F2_AL1 aligner $AL0 F2 1e-5 0 1 && eval_bg F2_S1A $R/models/F2_AL1 $R/models/F2_S1 B,538 538,B ;;
    S2A) train_one F2_S2 ctc $SC0 F2 3e-5 0 1 && train_one F2_AL2 aligner $AL0 F2 3e-5 0 1 && eval_bg F2_S2A $R/models/F2_AL2 $R/models/F2_S2 B,538 538,B ;;
  esac
  for p in $EVPIDS; do wait $p; done
  echo "AD_F2_OK"
  # ── CPU 다리(5.5절): 앱 경로 그대로(2스레드) ──
  case "$PICK" in
    S1A) F1AL=$R/models/F1_AL1; F1SC=$R/models/F1_S1; F2AL=$R/models/F2_AL1; F2SC=$R/models/F2_S1
         EX1="$L/export_F1_S1.log,$L/export_F1_AL1.log"; EX2="$L/export_F2_S1.log,$L/export_F2_AL1.log" ;;
    S2A) F1AL=$R/models/F1_AL2; F1SC=$R/models/F1_S2; F2AL=$R/models/F2_AL2; F2SC=$R/models/F2_S2
         EX1="$L/export_F1_S2.log,$L/export_F1_AL2.log"; EX2="$L/export_F2_S2.log,$L/export_F2_AL2.log" ;;
    *) F1AL=$AL0; F1SC=$R/models/F1_$PICK; F2AL=$AL0; F2SC=$R/models/F2_$PICK
       EX1="$L/export_F1_$PICK.log"; EX2="$L/export_F2_$PICK.log" ;;
  esac
  CW=$(( NC / 2 )); [ "$CW" -lt 1 ] && CW=1; [ "$CW" -gt 6 ] && CW=6
  $PY $S/evaluate.py pairs cpu_R0 $AL0 $SC0 A,B,538 $O/rows_cpu_R0.jsonl --workers $CW --device cpu --threads 2 --limit-per-set 20 --no-degrade > $L/cpu_R0.log 2>&1
  $PY $S/evaluate.py pairs cpu_F1_$PICK $F1AL $F1SC A,538 $O/rows_cpu_F1_$PICK.jsonl --workers $CW --device cpu --threads 2 --limit-per-set 20 --no-degrade > $L/cpu_F1.log 2>&1
  $PY $S/evaluate.py pairs cpu_F2_$PICK $F2AL $F2SC B,538 $O/rows_cpu_F2_$PICK.jsonl --workers $CW --device cpu --threads 2 --limit-per-set 20 --no-degrade > $L/cpu_F2.log 2>&1
  $PY $S/analyze.py bridge $O R0 "" > $L/bridge.log 2>&1
  $PY $S/analyze.py bridge $O F1_$PICK "$EX1" >> $L/bridge.log 2>&1
  $PY $S/analyze.py bridge $O F2_$PICK "$EX2" >> $L/bridge.log 2>&1
  cat $L/bridge.log
  echo "AD_BRIDGE_OK"
  $PY $S/analyze.py confirm $O F1 $PICK $O/bridge_F1_$PICK.json > $L/confirm_F1.log 2>&1; cat $L/confirm_F1.log
  $PY $S/analyze.py confirm $O F2 $PICK $O/bridge_F2_$PICK.json > $L/confirm_F2.log 2>&1; cat $L/confirm_F2.log
fi
$PY $S/analyze.py report $O > $L/report.log 2>&1
echo "$PICK" > $O/pick.txt
tar -czf $W/ad_result.tgz -C $R out -C $W dax/logs || fail tar
ls -la $W/ad_result.tgz
echo "AD_OK"
