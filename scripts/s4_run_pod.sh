#!/bin/bash
# S4 채점 모델 증류(파드 쪽 단계 실행, docs/scorer-distill-2026-10.md). s16_distill.sh가 /workspace에 푼 것을 쓴다:
#   backend(앱 커밋 b675975, models/dgop_ours는 교사 int8 + 설정), scripts/(s4_*.py, speak_app_direction_pod_eval.py,
#   speak_consonant_app_analyze.py), tools/make_deaf_corpus.py, eval/(538 wav 1,740 + manifest, 608 세션 FLAC 27, cuts608.json, e1_rows.jsonl)
# 단계마다 표식 파일(/workspace/out/.done_<단계>)을 남겨 다시 부르면 끝난 단계는 건너뛴다. 로그 /workspace/dax/logs/s4.log
#   표식(줄 맨 앞): S4_SETUP_OK SELFTEST_OK SMOKE_OK DATA_OK TEACHER_OK TRAIN_OK EXPORT_OK PREP_OK PAIRS_OK E2_OK LATENCY_OK S4_OK / S4_FAIL
set -u
W=/workspace
L=$W/dax/logs
O=$W/out
mkdir -p "$L" "$O" "$W/runs"
exec >> "$L/s4.log" 2>&1
echo $$ > "$L/s4.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "S4_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false HF_HUB_DISABLE_PROGRESS_BARS=1
STAGES=${S4_STAGES:-setup selftest smoke data teacher trainH exportH trainX exportX prep evteacher evstudent latency}

NC=$(nproc)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -z "$Q" ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
  Q=$(awk -v p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)" '{ if ($1 > 0) print int($1 / p) }' /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
fi
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
MEMG=$(free -g | awk '/Mem:/ {print $2}')
WK=$(( NC / 2 )); [ "$WK" -lt 1 ] && WK=1
GW=4; [ "$GW" -gt "$WK" ] && GW=$WK
echo "=== [s4] start pid=$$ cpus=$NC mem=${MEMG}G cpu_workers=$WK gpu_workers=$GW stages: $STAGES"
PY=$W/vapp/bin/python
done_() { touch "$O/.done_$1"; }
isdone() { [ -f "$O/.done_$1" ]; }

for st in $STAGES; do
  if isdone "$st"; then say "skip $st (done)"; continue; fi
  say "stage $st"
  case "$st" in
    setup)
      if [ ! -f "$W/vapp/.ok" ]; then
        python3 -m venv "$W/vapp" || fail "venv"
        "$W/vapp/bin/pip" install -q --upgrade pip
        "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail "torch"
        "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy \
          "onnx>=1.17" "onnxruntime>=1.20" pyarrow "huggingface_hub>=0.34" hf_xet || fail "의존"
        if ! "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt"; then
          (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libavformat-dev libavcodec-dev \
            libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev) || fail "apt av"
          "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt" || fail "backend requirements"
        fi
        touch "$W/vapp/.ok"
      fi
      $PY -c "import torch, transformers, onnx, onnxruntime, numpy, faster_whisper; print('ENV torch', torch.__version__, 'tf', transformers.__version__, 'onnx', onnx.__version__, 'ort', onnxruntime.__version__, 'numpy', numpy.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')" || fail "env"
      $PY -c "import torch; assert torch.cuda.is_available()" || fail "cuda"
      (cd "$W/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC") || fail "acoustic import"
      echo "S4_SETUP_OK" ;;
    selftest) (cd "$W/scripts" && OMP_NUM_THREADS=8 $PY s4_distill_pod.py selftest) || fail selftest ;;
    smoke) (cd "$W/scripts" && OMP_NUM_THREADS=8 $PY s4_distill_pod.py smoke) || fail smoke ;;
    data) (cd "$W/scripts" && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 $PY s4_distill_pod.py data ${S4_QUICK:+--quick}) || fail data ;;
    teacher) (cd "$W/scripts" && OMP_NUM_THREADS=8 $PY s4_distill_pod.py teacher) || fail teacher ;;
    trainH) (cd "$W/scripts" && OMP_NUM_THREADS=8 $PY s4_distill_pod.py train H ${S4_STEPS:+--steps $S4_STEPS}) || fail trainH ;;
    trainX) (cd "$W/scripts" && OMP_NUM_THREADS=8 $PY s4_distill_pod.py train X ${S4_STEPS:+--steps $S4_STEPS}) || fail trainX ;;
    exportH) (cd "$W/scripts" && OMP_NUM_THREADS=4 $PY s4_distill_pod.py export H) || fail exportH ;;
    exportX) (cd "$W/scripts" && OMP_NUM_THREADS=4 $PY s4_distill_pod.py export X) || fail exportX ;;
    prep) (cd "$W/scripts" && $PY s4_eval_pod.py prep) || fail prep ;;
    evteacher)
      cd "$W/scripts"
      for s in dev e1; do [ -s "$O/${s}_teacher.jsonl" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py $s teacher $GW "$O/${s}_teacher.jsonl" || fail "ev teacher $s"; done
      [ -s "$O/e2_teacher.json" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py e2 teacher $GW "$O/e2_teacher.json" || fail "ev teacher e2"
      cd "$W" ;;
    evstudent)
      cd "$W/scripts"
      for i in H X; do
        [ -s "$O/dev_$i.jsonl" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py dev "onnx:$W/runs/$i/student_w8.onnx" $WK "$O/dev_$i.jsonl" || fail "dev $i"
      done
      for i in H X; do
        [ -s "$O/e1_$i.jsonl" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py e1 "onnx:$W/runs/$i/student_w8.onnx" $WK "$O/e1_$i.jsonl" || fail "e1 $i"
        [ -s "$O/e2_$i.json" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py e2 "onnx:$W/runs/$i/student_w8.onnx" $WK "$O/e2_$i.json" || fail "e2 $i"
      done
      for i in H X; do
        [ -s "$O/e1_${i}_fp32.jsonl" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py e1 "torch:$i" $GW "$O/e1_${i}_fp32.jsonl" || echo "WARN e1 fp32 $i"
        [ -s "$O/e1_${i}_dyn8.jsonl" ] || OMP_NUM_THREADS=2 $PY s4_eval_pod.py e1 "onnx:$W/runs/$i/student_dyn8.onnx" $WK "$O/e1_${i}_dyn8.jsonl" || echo "WARN e1 dyn8 $i"
      done
      cd "$W" ;;
    latency)
      cd "$W/scripts"
      for i in H X; do
        for t in 2 1 4; do
          [ -s "$O/lat_${i}_w8_t$t.json" ] || LAT_THREADS=$t $PY s4_eval_pod.py latency "onnx:$W/runs/$i/student_w8.onnx" "$O/lat_${i}_w8_t$t.json" || fail "lat $i $t"
        done
        [ -s "$O/lat_${i}_dyn8_t2.json" ] || LAT_THREADS=2 $PY s4_eval_pod.py latency "onnx:$W/runs/$i/student_dyn8.onnx" "$O/lat_${i}_dyn8_t2.json" || echo "WARN lat dyn8 $i"
      done
      [ -s "$O/lat_teacher_cpu_t2.json" ] || LAT_THREADS=2 $PY s4_eval_pod.py latency teacher_cpu "$O/lat_teacher_cpu_t2.json" || echo "WARN lat teacher"
      cd "$W" ;;
    *) fail "알 수 없는 단계 $st" ;;
  esac
  done_ "$st"
  echo "STAGE_DONE $st"
done
for i in H X; do
  cp -f "$W/runs/$i/export.json" "$O/export_$i.json" 2>/dev/null
  cp -f "$W/runs/$i/train_summary.json" "$O/train_$i.json" 2>/dev/null
done
cp -f "$W/data/data_summary.json" "$W/data/teacher_batch_check.json" "$W/runs/smoke.json" "$O/" 2>/dev/null
echo "S4_OK"
