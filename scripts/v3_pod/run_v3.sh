#!/bin/bash
# V3 간이판(파드 쪽, 2026-10-15). 사전 등록: docs/avatar-v3-2026-10.md(커밋 2fdcd1ea).
#   v3_session.sh가 /workspace/v3에 푼 것: harness/, scripts/{v2_avatar_validity.py, v15_calibrate.py, coart_pod_eval.py, v3_avatar.py, data/viseme_v15.json,
#   v2_render/render_jobs.py}, tools/, backend/(정렬기 포함), clips/(확인 538 클립), ex/(탐색 자료 묶음), in/(작업·표·확인 목록).
#   bash run_v3.sh setup              환경(apt, mediapipe·playwright venv, 정렬·분석용 torch venv + scikit-learn) → V3_SETUP_OK
#   bash run_v3.sh prep               탐색 자료 풀기 + 확인 클립 추출(out/real_bs)·CTC 정렬(out/align_confirm.jsonl) → V3_PREP_OK
#   bash run_v3.sh render NAME JOBS   in/의 작업(쉼표로 여럿)을 in/tables.json과 렌더·추출 → V3_RENDER_<NAME>_OK
#   bash run_v3.sh py TAG ARGS...     scripts/v3_avatar.py ARGS(분석) → V3_PY_<TAG>_OK
#   bash run_v3.sh confirm            재개용(10/15 중단 뒤): 판독기 → 동결 표 묶음·확인 작업 → cfbase·cfv3 렌더 → 확인 판정 → V3_CONFIRM_OK
#                                     먼저 session push로 in/v3final.json과 최신 v3_avatar.py를 올리고 prep을 끝내 둔다. 끝난 단계는 건너뛴다.
#   표식은 /workspace/dax/logs/v3.log에 남는다. 이미 있는 결과는 건너뛴다.
set -u
W=/workspace/v3
L=/workspace/dax/logs
mkdir -p "$L" "$W/out" "$W/in"
exec >> "$L/v3.log" 2>&1
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "V3_FAIL $*"; exit 1; }
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
echo "=== $(date '+%F %T') run_v3 $* (pid $$, cpus $NC)"

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
      /workspace/vapp/bin/pip install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy "scikit-learn==1.7.2" || fail "의존"
      if ! /workspace/vapp/bin/pip install -q -r "$W/backend/requirements.txt"; then
        (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libavformat-dev libavcodec-dev \
          libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev) || fail "apt av"
        /workspace/vapp/bin/pip install -q -r "$W/backend/requirements.txt" || fail "backend requirements"
      fi
      touch /workspace/vapp/.ok
    fi
    $PY -c "import torch, transformers, sklearn; print('ENVAPP torch', torch.__version__, 'tf', transformers.__version__, 'sk', sklearn.__version__)" || fail "vapp"
    (cd "$W/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC") || fail "acoustic import"
    cd "$W/scripts/v2_render" || fail cd
    J=$W/in/jobs_ex1_h1.json
    out=$(timeout 300 $VMP render_jobs.py --harness "$W/harness" --jobs "$J" --tables "$W/in/tables.json" --out "$W/out/bench" --bench --gl egl 2>&1 | grep RJ_BENCH | tail -n 1)
    echo "$out"
    case "$out" in *SwiftShader*|"") fail "GPU 렌더 아님: $out" ;; esac
    echo "V3_SETUP_OK cpus=$NC" ;;
  prep)
    cd "$W/ex" || fail ex
    [ -d bs_real ] || tar -xzf bs_real.tgz || fail "bs_real"
    [ -d v1 ] || { mkdir -p v1 && tar -xzf v1_ex.tgz -C v1; } || fail "v1"
    [ -d v15 ] || { mkdir -p v15 && tar -xzf v15_ex.tgz -C v15; } || fail "v15"
    echo "EX real=$(ls bs_real | wc -l) v1=$(ls v1/bs_render | wc -l) v15=$(ls v15/bs | wc -l)"
    O=$W/out
    mkdir -p "$O/real_bs"
    : > "$W/list_real.tsv"
    for f in "$W"/clips/*.mp4; do b=$(basename "$f" .mp4); [ -s "$O/real_bs/$b.json" ] || printf '%s\t%s\n' "$f" "$O/real_bs/$b.json" >> "$W/list_real.tsv"; done
    ( extract_list "$W/list_real.tsv" REAL ) > "$L/extract_real.log" 2>&1 &
    EXPID=$!
    if [ ! -f "$O/.align_ok" ]; then
      sed "s#\"clips/#\"$W/clips/#" "$W/in/items_confirm.jsonl" > "$W/in/items_confirm_abs.jsonl"
      NS=$(( NC / 2 )); [ "$NS" -lt 1 ] && NS=1
      APIDS=""
      for s in $(seq 0 $((NS - 1))); do
        (cd "$W/scripts" && HF_HUB_OFFLINE=1 $PY v2_avatar_validity.py align --items "$W/in/items_confirm_abs.jsonl" --backend "$W/backend" \
           --shard "$s" --nshard "$NS" --threads 1 --out "$O/align_confirm.$s.jsonl" > "$L/align.$s.log" 2>&1) &
        APIDS="$APIDS $!"
      done
      wait $APIDS
      cat "$O"/align_confirm.*.jsonl > "$O/align_confirm.jsonl"
      touch "$O/.align_ok"
    fi
    wait "$EXPID"
    grep EXTRACT_REAL "$L/extract_real.log"
    echo "V3_PREP_OK bs=$(ls "$O/real_bs" | grep -c '\.json$') align=$(wc -l < "$O/align_confirm.jsonl") err=$(grep -c '"error"' "$O/align_confirm.jsonl")" ;;
  render)
    NAME=$2; JOBS=$3
    O=$W/out/$NAME
    mkdir -p "$O/renders" "$O/bs"
    cd "$W/scripts/v2_render" || fail cd
    JARGS=""
    IFS=',' read -r -a JL <<< "$JOBS"
    for j in "${JL[@]}"; do JARGS="$JARGS --jobs $W/in/$j"; done
    say "render $NAME jobs=$JOBS"
    PORT=$(( 5200 + $(printf '%s' "$NAME" | cksum | cut -d' ' -f1) % 700 ))
    $VMP render_jobs.py --harness "$W/harness" $JARGS --tables "$W/in/tables.json" --out "$O/renders" --workers "${V3_RW:-$NC}" --gl egl --port "$PORT" \
      > "$L/render_$NAME.log" 2>&1
    grep -h -E "RJ_GL|RJ_DONE|RJ_WORKER_FAIL" "$L/render_$NAME.log" | cut -c1-400
    : > "$O/list.tsv"
    for f in "$O"/renders/*.mp4; do
      [ -e "$f" ] || continue
      b=$(basename "$f" .mp4); [ -s "$O/bs/$b.json" ] || printf '%s\t%s\n' "$f" "$O/bs/$b.json" >> "$O/list.tsv"
    done
    extract_list "$O/list.tsv" "$NAME"
    echo "V3_RENDER_${NAME}_OK renders=$(ls "$O"/renders/ | grep -c 'sched.json$') bs=$(ls "$O"/bs/ | grep -c 'json$')" ;;
  py)
    TAG=$2; shift 2
    cd "$W/scripts" || fail cd
    say "py $TAG $*"
    ( set -o pipefail; $PY v3_avatar.py "$@" 2>&1 | sed -E '/RuntimeWarning|^  (out|return) /d' ) || fail "py $TAG"
    echo "V3_PY_${TAG}_OK" ;;
  confirm)
    [ -f "$W/out/.align_ok" ] || fail "prep 먼저"
    [ -f "$W/in/v3_avatar.py" ] && cp "$W/in/v3_avatar.py" "$W/scripts/v3_avatar.py"
    [ -f "$W/in/v3final.json" ] || fail "in/v3final.json 없음(session push)"
    cd "$W/scripts" || fail cd
    [ "$(sha256sum "$W/in/v3final.json" | cut -d' ' -f1)" = bbb30de3126b92f53e8f525476d43851b8d33460149e7b0685595ad62e3a587c ] || fail "동결 표 sha256"
    [ -s "$W/out/clf.pkl" ] || bash "$0" py CLF classifier --sel ../ex/sel.json --align ../ex/align_real.jsonl --real-bs ../ex/bs_real --out ../out/clf.pkl
    [ -s "$W/out/clf.pkl" ] || fail "판독기"
    $PY v3_avatar.py tables --v15 data/viseme_v15.json --v3 "$W/in/v3final.json" --out "$W/in/tables.json" || fail tables
    [ -s "$W/in/jobs_cf_v3f.json" ] || $PY v3_avatar.py jobs --sel ../in/sel_confirm.json --backend ../backend --cond v3:v3final --out ../in/jobs_cf_v3f.json || fail jobs
    bash "$0" render cfbase jobs_cf_base.json
    bash "$0" render cfv3 jobs_cf_v3f.json
    bash "$0" py CF evaluate --sel ../in/sel_confirm.json --align ../out/align_confirm.jsonl --real-bs ../out/real_bs \
      --renders ../out/cfbase/renders ../out/cfv3/renders --render-bs ../out/cfbase/bs ../out/cfv3/bs --tags - - --clf ../out/clf.pkl \
      --verdict --v3 v3-v3final --v1 v1 --cands v15 --out ../out/ev_confirm.json
    grep -q V3_PY_CF_OK "$L/v3.log" && echo "V3_CONFIRM_OK" || fail "confirm 평가" ;;
  *) echo "사용: $0 setup | prep | render NAME JOBS | py TAG ARGS... | confirm"; exit 2 ;;
esac
