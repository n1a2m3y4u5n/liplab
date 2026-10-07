#!/bin/bash
# V15 입모양 표 보정(파드 쪽, 2026-10-07). 사전 등록: docs/viseme-calibration-2026-10.md(커밋 2bf2291).
#   v15_session.sh가 /workspace/v15에 푼 것: harness/(vite build + orig_face.glb), scripts/v2_render/render_jobs.py,
#   tools/{extract_blendshapes.py, face_landmarker.task}, in/(작업 JSON·후보 표). 추가 파일은 session push로 in/에 온다.
#   bash run_v15.sh setup                         환경(apt, mediapipe·playwright venv) → V15_SETUP_OK
#   bash run_v15.sh render NAME JOBS[,JOBS2] [GLB] [TABLES]
#        in/의 작업을 렌더해 out/NAME/renders에 mp4·sched, 추출을 out/NAME/bs에 → V15_RENDER_<NAME>_OK
#   표식은 /workspace/dax/logs/v15.log에 남는다. 렌더·추출은 이미 있는 결과를 건너뛰어 끊겨도 다시 돌리면 이어서 한다.
set -u
W=/workspace/v15
L=/workspace/dax/logs
mkdir -p "$L" "$W/out" "$W/in"
exec >> "$L/v15.log" 2>&1
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "V15_FAIL $*"; exit 1; }
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
NC=$(nproc --all)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -z "$Q" ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
  Q=$(awk -v p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)" '{ if ($1 > 0) print int($1 / p) }' /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
fi
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
VMP=/workspace/vmp/bin/python
CMD=${1:-}
echo "=== $(date '+%F %T') run_v15 $* (pid $$, cpus $NC)"

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
    cd "$W/scripts/v2_render" || fail cd
    out=$(timeout 300 $VMP render_jobs.py --harness "$W/harness" --jobs "$W/in/jobs_poses_slim.json" --out "$W/out/bench" --bench --gl egl 2>&1 | grep RJ_BENCH | tail -n 1)
    echo "$out"
    case "$out" in *SwiftShader*|"") fail "GPU 렌더 아님: $out" ;; esac
    echo "V15_SETUP_OK cpus=$NC" ;;
  render)
    NAME=$2; JOBS=$3; GLB=${4:-}; TABLES=${5:-}
    [ "$GLB" = "-" ] && GLB=""
    O=$W/out/$NAME
    mkdir -p "$O/renders" "$O/bs"
    cd "$W/scripts/v2_render" || fail cd
    JARGS=""
    IFS=',' read -r -a JL <<< "$JOBS"
    for j in "${JL[@]}"; do JARGS="$JARGS --jobs $W/in/$j"; done
    say "render $NAME jobs=$JOBS glb=${GLB:-app} tables=${TABLES:-none}"
    PORT=$(( 5200 + $(printf '%s' "$NAME" | cksum | cut -d' ' -f1) % 700 ))   # 렌더 단계를 겹쳐 돌려도 HTTP 포트가 겹치지 않게
    $VMP render_jobs.py --harness "$W/harness" $JARGS --out "$O/renders" --workers "${V15_RW:-$NC}" --gl egl --port "$PORT" \
      ${GLB:+--glb "$GLB"} ${TABLES:+--tables "$W/in/$TABLES"} > "$L/render_$NAME.log" 2>&1
    grep -h -E "RJ_DONE|RJ_WORKER_FAIL" "$L/render_$NAME.log"
    : > "$O/list.tsv"
    for f in "$O"/renders/*.mp4; do
      [ -e "$f" ] || continue
      b=$(basename "$f" .mp4); [ -s "$O/bs/$b.json" ] || printf '%s\t%s\n' "$f" "$O/bs/$b.json" >> "$O/list.tsv"
    done
    if [ -s "$O/list.tsv" ]; then
      rm -f "$O"/list.tsv.part.*
      split -n "l/$NC" -d "$O/list.tsv" "$O/list.tsv.part."
      for k in "$O"/list.tsv.part.*; do
        (cd "$W/tools" && $VMP extract_blendshapes.py --list "$k" --lips --no-audio > "$k.log" 2>&1) &
      done
      wait
      echo "EXTRACT_$NAME $(cat "$O"/list.tsv.part.*.log | grep -h LIST_DONE | tr '\n' ' ')"
    fi
    echo "V15_RENDER_${NAME}_OK renders=$(ls "$O"/renders/ | grep -c 'sched.json$') bs=$(ls "$O"/bs/ | grep -c 'json$')" ;;
  *) echo "사용: $0 setup | render NAME JOBS [GLB|-] [TABLES]"; exit 2 ;;
esac
