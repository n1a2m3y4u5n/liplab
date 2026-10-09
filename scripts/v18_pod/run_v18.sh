#!/bin/bash
# V18 입술 돌출(파드 쪽, 2026-10-09). 사전 등록: docs/lip-protrusion-v18-2026-10.md.
#   v18_session.sh가 /workspace/v18에 푼 것: harness/(vite build), scripts/{v2_avatar_validity.py, coart_pod_eval.py, v18_protrusion.py,
#   v2_render/render_jobs.py}, tools/{extract_blendshapes.py, face_landmarker.task}, backend/(정렬기 포함), clips/(비정면 538 클립),
#   in/{items_side.jsonl, jobs_v18.json, tables_v18.json}.
#   bash run_v18.sh setup                    환경(apt, mediapipe·playwright venv, 정렬용 torch venv) → V18_SETUP_OK
#   bash run_v18.sh real                     비정면 클립 추출(out/side_bs) + CTC 정렬(out/align_side.jsonl) → V18_REAL_OK
#   bash run_v18.sh render NAME CAM [ONLY]   in/jobs_v18.json을 카메라 CAM(x,y,z)으로 렌더·추출 → V18_RENDER_<NAME>_OK
#   표식은 /workspace/dax/logs/v18.log에 남는다. 이미 있는 결과는 건너뛴다.
set -u
W=/workspace/v18
L=/workspace/dax/logs
mkdir -p "$L" "$W/out" "$W/in"
exec >> "$L/v18.log" 2>&1
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "V18_FAIL $*"; exit 1; }
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
NC=$(nproc --all)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -z "$Q" ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
  Q=$(awk -v p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)" '{ if ($1 > 0) print int($1 / p) }' /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
fi
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
VMP=/workspace/vmp/bin/python
PY=/workspace/vapp/bin/python
CMD=${1:-}
echo "=== $(date '+%F %T') run_v18 $* (pid $$, cpus $NC)"

extract_list() {   # LIST OUTTAG
  local list=$1 tag=$2
  [ -s "$list" ] || { echo "EXTRACT_$tag empty"; return 0; }
  rm -f "$list".part.*
  split -n "l/$NC" -d "$list" "$list.part."
  for k in "$list".part.*; do
    (cd "$W/tools" && $VMP extract_blendshapes.py --list "$k" --lips --no-audio > "$k.log" 2>&1) &
  done
  wait
  echo "EXTRACT_$tag $(cat "$list".part.*.log | grep -h LIST_DONE | tr '\n' ' ')"
}

case "$CMD" in
  setup)
    if [ ! -f "$W/.apt_ok" ]; then
      (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg libvulkan1 libegl1 libgl1) || fail "apt"
      touch "$W/.apt_ok"
    fi
    if [ ! -f /workspace/vmp/.ok ]; then
      python3 -m venv /workspace/vmp || fail "venv"
      /workspace/vmp/bin/pip install -q --upgrade pip
      /workspace/vmp/bin/pip install -q "mediapipe==0.10.14" "opencv-python-headless<4.11" "numpy<2" scipy "playwright==1.48.0" || fail "pip"
      /workspace/vmp/bin/python -m playwright install --with-deps chromium > "$L/playwright_install.log" 2>&1 || fail "playwright"
      touch /workspace/vmp/.ok
    fi
    $VMP -c "import mediapipe, cv2; print('ENVMP', mediapipe.__version__, cv2.__version__)" || fail "vmp"
    if [ ! -f /workspace/vapp/.ok ]; then
      python3 -m venv /workspace/vapp || fail "vapp venv"
      /workspace/vapp/bin/pip install -q --upgrade pip
      /workspace/vapp/bin/pip install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail "torch"
      /workspace/vapp/bin/pip install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy || fail "의존"
      if ! /workspace/vapp/bin/pip install -q -r "$W/backend/requirements.txt"; then
        (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libavformat-dev libavcodec-dev \
          libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev) || fail "apt av"
        /workspace/vapp/bin/pip install -q -r "$W/backend/requirements.txt" || fail "backend requirements"
      fi
      touch /workspace/vapp/.ok
    fi
    $PY -c "import torch, transformers; print('ENVAPP torch', torch.__version__, 'tf', transformers.__version__, 'cuda', torch.cuda.is_available())" || fail "vapp"
    (cd "$W/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC") || fail "acoustic import"
    cd "$W/scripts/v2_render" || fail cd
    out=$(timeout 300 $VMP render_jobs.py --harness "$W/harness" --jobs "$W/in/jobs_v18.json" --out "$W/out/bench" --bench --gl egl 2>&1 | grep RJ_BENCH | tail -n 1)
    echo "$out"
    case "$out" in *SwiftShader*|"") fail "GPU 렌더 아님: $out" ;; esac
    echo "V18_SETUP_OK cpus=$NC" ;;
  real)
    O=$W/out
    mkdir -p "$O/side_bs"
    : > "$W/list_side.tsv"
    for f in "$W"/clips/*.mp4; do b=$(basename "$f" .mp4); [ -s "$O/side_bs/$b.json" ] || printf '%s\t%s\n' "$f" "$O/side_bs/$b.json" >> "$W/list_side.tsv"; done
    ( extract_list "$W/list_side.tsv" SIDE ) > "$L/extract_side.log" 2>&1 &
    EXPID=$!
    if [ ! -f "$O/.align_side_ok" ]; then
      NS=$(( NC / 2 )); [ "$NS" -lt 1 ] && NS=1
      APIDS=""
      for s in $(seq 0 $((NS - 1))); do
        (cd "$W/scripts" && HF_HUB_OFFLINE=1 $PY v2_avatar_validity.py align --items "$W/in/items_side.jsonl" --backend "$W/backend" \
           --shard "$s" --nshard "$NS" --threads 1 --out "$O/align_side.$s.jsonl" > "$L/align_side.$s.log" 2>&1) &
        APIDS="$APIDS $!"
      done
      wait $APIDS
      cat "$O"/align_side.*.jsonl > "$O/align_side.jsonl"
      touch "$O/.align_side_ok"
    fi
    wait "$EXPID"
    grep EXTRACT_SIDE "$L/extract_side.log"
    echo "V18_REAL_OK bs=$(ls "$O/side_bs" | grep -c '\.json$') align=$(wc -l < "$O/align_side.jsonl") err=$(grep -c '"error"' "$O/align_side.jsonl")" ;;
  render)
    NAME=$2; CAM=$3; ONLY=${4:-}
    O=$W/out/$NAME
    mkdir -p "$O/renders" "$O/bs"
    cd "$W/scripts/v2_render" || fail cd
    say "render $NAME cam=$CAM only=${ONLY:-all}"
    PORT=$(( 5200 + $(printf '%s' "$NAME" | cksum | cut -d' ' -f1) % 700 ))
    $VMP render_jobs.py --harness "$W/harness" --jobs "$W/in/jobs_v18.json" --tables "$W/in/tables_v18.json" --out "$O/renders" \
      --workers "${V18_RW:-$NC}" --gl egl --port "$PORT" --cam "$CAM" ${ONLY:+--only "$ONLY"} > "$L/render_$NAME.log" 2>&1
    grep -h -E "RJ_DONE|RJ_WORKER_FAIL" "$L/render_$NAME.log"
    : > "$O/list.tsv"
    for f in "$O"/renders/*.mp4; do
      [ -e "$f" ] || continue
      b=$(basename "$f" .mp4); [ -s "$O/bs/$b.json" ] || printf '%s\t%s\n' "$f" "$O/bs/$b.json" >> "$O/list.tsv"
    done
    extract_list "$O/list.tsv" "$NAME"
    echo "V18_RENDER_${NAME}_OK renders=$(ls "$O"/renders/ | grep -c 'sched.json$') bs=$(ls "$O"/bs/ | grep -c 'json$')" ;;
  *) echo "사용: $0 setup | real | render NAME CAM [ONLY]"; exit 2 ;;
esac
