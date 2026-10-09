#!/bin/bash
# 608 범주 27 새 화자 채점 파드 세션(맥, docs/newdata-608c27-538-2026-10.md). 파드는 liplab-lab/tools/pod/pod.sh로만 다룬다.
#   bash scripts/newdata_c27/session_c27.sh stage    묶음(파드 없음): b675975 backend, 이 브랜치 backend, 도구, c27 FLAC·라벨, 다리
#   bash scripts/newdata_c27/session_c27.sh launch   파드 생성(워치독) → wait → 올리기 → sha256 → run_c27.sh → 끝까지 기다림 → 받기 → terminate
#   bash scripts/newdata_c27/session_c27.sh tail     파드 로그 끝부분
#   bash scripts/newdata_c27/session_c27.sh finish   (launch가 중간에 멈췄을 때) 결과 받기 → terminate → status
# 상태 폴더 tools/pod/.c27state, 파드 이름 liplab-c27. RunPod 키는 pod.sh가 메모리로만 읽는다. 다른 작업의 파드는 건드리지 않는다.
# 608 원자료·조각은 lab 묶음 폴더(data/c27stage)와 파드에만 두고 앱 저장소에 넣지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.c27state} POD_NAME=${POD_NAME:-liplab-c27} POD_DISK_GB=${POD_DISK_GB:-40}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
M8=$LAB/models/dgop_ours_2026-09-25_int8
S=${STAGE_DIR:-$LAB/data/c27stage}
FLAC=$LAB/data/hi608/c27/flac16
HI=$LAB/data/hi608
RUN1=$LAB/data/pod_runs/20261006_uoqtuk2pyq0nty/s13
V1=$LAB/data/v1_538
COMMIT=b675975e670ebe637458e89a0e44709db0b5174e
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-150}
SHA_ALIGNER=18681947f740b7486f8fa4f93c7c0f68fe1595ac4fa9822800dfd38d713f5e66
SHA_SCORER=e8340d58dd911e380eca508815526eb77ec658560456ce1fe4c16b9b6e3654c4
SHA_S18HEAD=f48cb31bc63961ed5ecede82f72e58b76136f8e34dbbf2d4c225370027b06eb8
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_c27_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "C27S_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }
sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }

do_stage() {
  step "가중치·코드 확인"
  [ "$(sha_of "$M8/aligner/model.int8.safetensors")" = "$SHA_ALIGNER" ] || die "정렬기 sha256"
  [ "$(sha_of "$M8/scorer/model.int8.safetensors")" = "$SHA_SCORER" ] || die "채점기 sha256"
  [ "$(sha_of "$APP/scripts/scoring_s18_head.py")" = "$SHA_S18HEAD" ] || die "scoring_s18_head.py가 10/6 등록판과 다름"
  ls "$FLAC"/*.flac >/dev/null 2>&1 || die "c27 FLAC 없음(받기 먼저)"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/tools" "$R/scripts" "$R/backend_new" "$R/n608/s608" "$R/n608/labels" "$R/bridge"
  git -C "$APP" archive "$COMMIT" backend scripts/speak_asr_pod_run.py | tar -x -C "$R" || die "git archive b675975"
  git -C "$APP" archive HEAD backend | tar -x -C "$R/backend_new" --strip-components=1 || die "git archive HEAD"
  rm -rf "$R/backend/data/sound" "$R/backend_new/data/sound"
  cp "$APP/scripts/scoring_s18_head.py" "$R/scripts/" || die s18head
  for bk in backend backend_new; do
    for m in aligner scorer; do
      mkdir -p "$R/$bk/models/dgop_ours/$m"
      for f in "$M8/$m"/*; do case "$(basename "$f")" in model.int8.safetensors|model.safetensors) ;; *) cp -c "$f" "$R/$bk/models/dgop_ours/$m/" ;; esac; done
    done
  done
  for t in s13_newspk.py scores_1006.py build_scores_csv.py; do cp -c "$LAB/tools/$t" "$R/tools/" || die "도구 $t"; done
  cp "$APP/scripts/newdata_c27/c27_pod.py" "$R/tools/" && cp "$APP/scripts/newdata_c27/run_c27.sh" "$R/" || die scripts
  (cd "$R/tools" && python3 c27_pod.py selftest) | tail -n 1 | grep -q C27_SELFTEST_OK || die "로컬 selftest"
  n=0
  for f in "$FLAC"/*.flac; do
    b=$(basename "$f" .flac)
    src=$(ls "$HI/labels/"*/"$b.json" 2>/dev/null | head -n 1)
    [ -n "$src" ] || die "라벨 없음 $b"
    cp -c "$f" "$R/n608/s608/" && cp -c "$src" "$R/n608/labels/$b.json" || die "608 복사 $b"
    n=$((n + 1))
  done
  echo "flac608 $n"
  python3 - "$RUN1" "$R" "$V1" <<'EOFB' || die bridge
import json, shutil, sys
run1, r, v1 = sys.argv[1:4]
J = json.load(open(f"{run1}/out/jobs.json", encoding="utf-8"))
rows = [j for j in J["s18"] if j["set"] == "538"]
clips = sorted({j["clip"] for j in rows})[::20][:30]          # run1 538 클립 600개 가운데 이름 순 20개마다 하나(30개, 10/9 s18n과 같다)
out = [{"spk": j["spk"], "clip": j["clip"], "target": j["target"], "kind": j["kind"]} for j in rows if j["clip"] in set(clips)]
for c in clips:
    shutil.copyfile(f"{v1}/clips/{c}.wav", f"{r}/bridge/{c}.wav")
json.dump(out, open(f"{r}/bridge/bridge.json", "w"), ensure_ascii=False)
print("BRIDGE(run1) clips", len(clips), "rows", len(out))
EOFB
  ( cd "$R" && find backend backend_new scripts tools bridge n608 run_c27.sh -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  for bk in backend backend_new; do
    printf '%s  %s/models/dgop_ours/aligner/model.int8.safetensors\n%s  %s/models/dgop_ours/scorer/model.int8.safetensors\n' \
      "$SHA_ALIGNER" "$bk" "$SHA_SCORER" "$bk" >> "$R/expect.sha256"
  done
  git -C "$APP" rev-parse HEAD > "$S/backend_new.rev"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/c27.tar" -C "$R" . || die tar
  ls -la "$S/c27.tar"
  echo "C27S_STAGE_OK backend_new=$(cat "$S/backend_new.rev")"
}

fetch_result() {
  local POD out
  POD=$(pod_id)
  [ -n "$POD" ] || { echo "파드 없음"; return 1; }
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/c27"
  mkdir -p "$out"
  if bash "$P" ssh 'test -s /workspace/c27_result.tgz && grep -q "^C27_OK" /workspace/dax/logs/c27.log'; then
    bash "$P" ssh 'cat /workspace/c27_result.tgz' > "$out/result.tgz" && tar -xzf "$out/result.tgz" -C "$out" && echo "C27S_FETCH_OK $out" || echo "C27S_FETCH_WARN"
  else
    bash "$P" ssh 'cd /workspace && tar -czf - out/*.json out/*.jsonl out/*.csv outb/*.jsonl n608/out/cuts608.json dax/logs/*.log 2>/dev/null' | tar -xzf - -C "$out" && echo "C27S_FETCH_PARTIAL $out" || echo "C27S_FETCH_WARN"
  fi
  ls -la "$out" "$out/out" 2>/dev/null | tail -20
}

do_launch() {
  [ -s "$S/c27.tar" ] || die "묶음 없음(stage 먼저)"
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
  echo "C27S_POD $(pod_id)"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; df -h /workspace | tail -1; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/c27.tar" /workspace/c27.tar "$M8/aligner/model.int8.safetensors" /workspace/aligner.int8 \
    "$M8/scorer/model.int8.safetensors" /workspace/scorer.int8 --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 4 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { bash "$P" terminate --force || true; die "upload(rc=$PUP_RC)"; }
  bash "$P" ssh 'cd /workspace && tar -xf c27.tar && rm -f c27.tar && for bk in backend backend_new; do cp aligner.int8 $bk/models/dgop_ours/aligner/model.int8.safetensors && cp scorer.int8 $bk/models/dgop_ours/scorer/model.int8.safetensors; done && rm -f aligner.int8 scorer.int8 && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || { bash "$P" terminate --force || true; die "풀기"; }
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || { bash "$P" terminate --force || true; die "sha256 불일치"; }
  step "run_c27.sh 시작"
  bash "$P" run 'bash /workspace/run_c27.sh' || { bash "$P" terminate --force || true; die run; }
  echo "C27S_LAUNCH_OK $(pod_id)"
  WAITFOR_MAX_MIN=${WAIT_MAX:-140} WAIT_POLL=60 bash "$P" waitfor C27_OK logs/c27.log
  WRC=$?
  bash "$P" ssh 'grep -E "^(ENV|S13_|SEG|C27|JOBS|DGOP|FEAT|TRIM|===)" /workspace/dax/logs/c27.log | tail -n 40' || true
  fetch_result
  bash "$P" terminate --force || true
  bash "$P" status || true
  [ "$WRC" = 0 ] && echo "C27S_DONE" || die "waitfor rc=$WRC"
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/dax/logs/c27.log' ;;
  finish) fetch_result; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "session_c27.sh stage|launch|tail|finish"; exit 2 ;;
esac
