#!/bin/bash
# 608 도메인 적응 파드 세션(맥, docs/dgop-608-adapt-2026-10.md 10절). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/dgop_adapt_pod/session.sh stage    묶음(파드 없음): build.py 산출물 + 이 브랜치 backend·스크립트 → ad.tar
#   bash scripts/dgop_adapt_pod/session.sh launch   파드 생성(워치독) → wait(자폭 타이머) → 올리기 → sha256 → run.sh
#   bash scripts/dgop_adapt_pod/session.sh tail     파드 로그 끝부분
#   bash scripts/dgop_adapt_pod/session.sh mid      탐색 결과(ad_mid.tgz) 받기(파드는 그대로)
#   bash scripts/dgop_adapt_pod/session.sh fetch    결과·고른 가중치 받기(파드는 그대로)
#   bash scripts/dgop_adapt_pod/session.sh finish   fetch → terminate → status
# 상태 폴더 .adstate, 파드 이름 liplab-ad. RunPod 키는 pod.sh가 메모리로만 읽는다. 다른 이름의 파드는 건드리지 않는다.
# AI Hub 자료와 새 가중치는 liplab-lab과 파드에만 두고 앱 저장소에 넣지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.adstate} POD_NAME=${POD_NAME:-liplab-ad} POD_DISK_GB=${POD_DISK_GB:-200}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-20}
M8=${M8:-$LAB/models/dgop_ours_2026-09-25_int8}
S=${STAGE_DIR:-$LAB/data/adapt_stage}
R=$S/root
GPUS=${GPUS:-NVIDIA A100-SXM4-80GB|SECURE,NVIDIA A100 80GB PCIe|SECURE,NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE}
WD_MIN=${WD_MIN:-420}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
OUTW=${OUTW:-$LAB/models/dgop_ours_2026-10-09_adapt}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_ad_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "ADS_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  [ -f "$R/meta/build_summary.json" ] || die "build.py 먼저(STAGE_ROOT=$R)"
  step "가중치 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 int8 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 int8 sha256"
  step "묶음"
  rm -rf "$R/backend" "$R/scripts" "$R/models" && mkdir -p "$R/backend/data" "$R/scripts" "$R/models/R0"
  cp "$APP"/backend/*.py "$R/backend/" || die backend
  cp "$APP"/backend/data/dgop_calibration*.json "$R/backend/data/" || die calibration
  cp "$APP"/scripts/dgop_adapt_pod/{segment,train,evaluate,analyze}.py "$APP"/scripts/dgop_adapt_pod/run.sh "$R/scripts/" || die scripts
  cp "$APP"/scripts/export_int8.py "$APP"/scripts/speak_app_direction_pod_eval.py "$LAB/tools/make_deaf_corpus.py" "$R/scripts/" || die scripts2
  for m in aligner scorer; do
    mkdir -p "$R/models/R0/$m"
    for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors) ;; *) cp "$f" "$R/models/R0/$m/" ;; esac; done
  done
  ( cd "$R" && find backend scripts meta models audio -type f ! -name '.DS_Store' | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  printf '%s  models/R0/aligner/model.int8.safetensors\n%s  models/R0/scorer/model.int8.safetensors\n' "$SHA_ALIGNER" "$SHA_SCORER" >> "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/ad.tar" -C "$R" . || die tar
  ls -la "$S/ad.tar"
  echo "ADS_STAGE_OK"
}

do_launch() {
  [ -s "$S/ad.tar" ] || die "묶음 없음(stage 먼저)"
  step "잔액·파드 목록"
  bash "$P" status || true
  step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME, 디스크 ${POD_DISK_GB}GB)"
  created=0
  IFS=',' read -r -a CANDS <<< "$GPUS"
  for cand in "${CANDS[@]}"; do
    g=${cand%%|*}; c=${cand#*|}
    step "후보 $g / $c"
    if bash "$P" create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
  done
  [ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
  echo "ADS_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/ad.tar" /workspace/ad.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'mkdir -p /workspace/ad && cd /workspace/ad && tar -xf ../ad.tar && rm -f ../ad.tar && mv ../aligner.int8 models/R0/aligner/model.int8.safetensors && mv ../scorer.int8 models/R0/scorer/model.int8.safetensors && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run.sh 시작"
  bash "$P" run 'bash /workspace/ad/scripts/run.sh' || { bash "$P" terminate --force || true; die run; }
  echo "ADS_LAUNCH_OK $(pod_id)"
}

get() {  # 원격 파일 → 로컬, 크기 확인
  local rf=$1 lf=$2 rs ls_
  mkdir -p "$(dirname "$lf")"
  rs=$(bash "$P" ssh "stat -c %s '$rf' 2>/dev/null" | tr -d '\r\n')
  [ -n "$rs" ] || { echo "없음: $rf"; return 1; }
  bash "$P" ssh "cat '$rf'" > "$lf" || return 1
  ls_=$(stat -f %z "$lf")
  [ "$rs" = "$ls_" ] || { echo "크기 다름: $rf $rs vs $ls_"; return 1; }
  echo "받음 $lf ($ls_)"
}

outdir() { echo "$LAB/data/pod_runs/$(date +%Y%m%d)_$(pod_id)/ad"; }

do_mid() {
  POD=$(pod_id); [ -n "$POD" ] || die "파드 없음"
  out=$(outdir); mkdir -p "$out/mid"
  get /workspace/ad_mid.tgz "$out/mid/mid.tgz" && tar -xzf "$out/mid/mid.tgz" -C "$out/mid" && echo "ADS_MID_OK $out/mid" || echo "ADS_MID_WARN"
}

do_fetch() {
  POD=$(pod_id); [ -n "$POD" ] || die "파드 없음"
  out=$(outdir); mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/ad_result.tgz && grep -q "^AD_OK" /workspace/dax/logs/ad.log'; then
    get /workspace/ad_result.tgz "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "ADS_FETCH_OK $out" || echo "ADS_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - ad/out dax/logs 2>/dev/null' | tar -xzf - -C "$out" && echo "ADS_FETCH_PARTIAL $out" || echo "ADS_FETCH_WARN"
  fi
  # 고른 후보의 가중치(int8 + fp32). Zeroth·608로 학습한 가중치라 저장소에는 넣지 않는다
  PICK=$(bash "$P" ssh 'cat /workspace/ad/out/pick.txt 2>/dev/null || awk "/^PICK /{print \$2}" /workspace/ad/out/judge_explore.txt 2>/dev/null' | tr -d '\r\n')
  echo "PICK=$PICK"
  [ -n "$PICK" ] && [ "$PICK" != "None" ] || return 0
  case "$PICK" in S1A) M="S1 AL1" ;; S2A) M="S2 AL2" ;; *) M="$PICK" ;; esac
  for f in F1 F2; do
    for m in $M; do
      n=${f}_$m
      bash "$P" ssh "test -s /workspace/ad/models/$n/model.int8.safetensors" || continue
      for x in added_tokens.json config.json processor_config.json tokenizer_config.json vocab.json model.int8.safetensors; do
        get "/workspace/ad/models/$n/$x" "$OUTW/$n/int8/$x" || true
      done
      if [ "${FETCH_FP32:-1}" = 1 ]; then
        for x in added_tokens.json config.json processor_config.json tokenizer_config.json vocab.json train_log.json model.safetensors; do
          get "/workspace/ckpt/$n/$x" "$OUTW/$n/fp32/$x" || true
        done
      fi
    done
  done
  ( cd "$OUTW" 2>/dev/null && shasum -a 256 */int8/model.int8.safetensors */fp32/model.safetensors 2>/dev/null )
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 25 /workspace/dax/logs/ad.log; for f in /workspace/dax/logs/train_*.log; do [ -f "$f" ] && { echo "--- $(basename $f)"; tail -n 2 "$f"; }; done 2>/dev/null; tail -n 2 /workspace/dax/logs/seg0.log /workspace/dax/logs/seg1.log 2>/dev/null; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader' ;;
  mid) do_mid ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session.sh stage|launch|tail|mid|fetch|finish"; exit 2 ;;
esac
