#!/bin/bash
# 검사 폼 C·D 난이도 등가 측정 파드 세션(맥, docs/listen-forms-cd-2026-10.md 3.2절). 파드는 liplab-lab의 tools/pod/pod.sh로만 다룬다.
#   bash scripts/sound_pod/forms_session.sh stage     묶음(파드 없음): 앱 코드 몇 개 + 측정 스크립트 + 목록의 m3 클립(측정 문장만) + 소음 둘
#   bash scripts/sound_pod/forms_session.sh launch    파드 생성(워치독) → wait(자폭 타이머) → 속도 점검 → 올리기 → sha256 → forms_run.sh
#   bash scripts/sound_pod/forms_session.sh tail      파드 로그 끝부분
#   bash scripts/sound_pod/forms_session.sh fetch     결과(받아쓰기·채점 jsonl, 판정, 로그. 오디오 없음)를 data/pod_runs/<날짜>_<파드>/fcd/로
#   bash scripts/sound_pod/forms_session.sh finish    fetch → terminate → status
# 환경: ROUND(0·1·2), SIDS(쉼표 목록, 기본 all), REPS(기본 ROUND의 반복), EXTRA(교체 문장 {sid: 글} JSON), SPEC(판정 spec JSON),
#       LAB(기본 ~/Downloads/liplab-lab), GPUS, WD_MIN. 상태 폴더 .fcdstate, 파드 이름 liplab-fcd(다른 작업과 섞이지 않게).
# 키는 pod.sh가 ~/.runpod/config.toml에서 메모리로만 읽는다. AI Hub 자료는 올리지 않는다.
set -uo pipefail
APP=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$HOME/Downloads/liplab-lab}
P="$LAB/tools/pod/pod.sh"
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.fcdstate} POD_NAME=${POD_NAME:-liplab-fcd} POD_DISK_GB=${POD_DISK_GB:-40}
export DEADMAN_GRACE_MIN=${DEADMAN_GRACE_MIN:-15}
S=${STAGE_DIR:-$LAB/data/fcd_stage}
GPUS=${GPUS:-NVIDIA RTX A6000|SECURE,NVIDIA A40|SECURE,NVIDIA L40S|SECURE}
WD_MIN=${WD_MIN:-120}
ROUND=${ROUND:-0}
case "$ROUND" in 0) DEF_REPS=0,1,2 ;; 1) DEF_REPS=3,4,5 ;; 2) DEF_REPS=6,7,8 ;; *) echo "ROUND 0·1·2"; exit 2 ;; esac
REPS=${REPS:-$DEF_REPS}
SIDS=${SIDS:-all}
mkdir -p "$S" "$LAB/data/pod_runs" "$POD_STATE_DIR"
CMD=${1:-}
LOG="$LAB/data/pod_runs/session_fcd_${CMD}_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "FCD_FAIL $*"; exit 1; }
pod_id() { awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null; }

do_stage() {
  step "묶음(ROUND=$ROUND REPS=$REPS SIDS=$SIDS)"
  R=$S/root
  rm -rf "$R" && mkdir -p "$R/backend" "$R/scripts" "$R/sound/clips" "$R/sound/noise" "$R/work"
  for f in listen_curriculum.py sentence_feedback.py scoring.py engine.py korean_numbers.py sound_clips.py; do
    cp "$APP/backend/$f" "$R/backend/" || die "앱 $f"
  done
  cp "$APP/scripts/listen_virtual_listener.py" "$APP/scripts/listen_forms_equiv.py" "$APP/scripts/sound_pod/forms_run.sh" "$R/scripts/" || die scripts
  cp "$APP/backend/data/sound/manifest.json" "$R/sound/" || die manifest
  cp "$APP/backend/data/sound/noise/babble.ogg" "$APP/backend/data/sound/noise/talker2.ogg" "$R/sound/noise/" || die noise
  [ -n "${EXTRA:-}" ] && { cp "$EXTRA" "$R/work/extra.json" || die extra; }
  [ -n "${SPEC:-}" ] && { cp "$SPEC" "$R/work/spec.json" || die spec; }
  printf 'SIDS=%s\nREPS=%s\nROUND=%s\n' "$SIDS" "$REPS" "$ROUND" > "$R/work/run.env"
  python3 - "$R" "$APP/backend/data/sound/clips" <<'EOF' || die "클립 고르기"
import json, os, shutil, sys
R, src = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(R, "backend"))
import listen_curriculum as L, sound_clips as SC
man = json.load(open(os.path.join(R, "sound", "manifest.json"), encoding="utf-8"))
texts = [s for f in ("A", "B", "C", "D") for s in L.TEST_FORMS[f]]
ex = os.path.join(R, "work", "extra.json")
if os.path.exists(ex):
    texts += list(json.load(open(ex, encoding="utf-8")).values())
n = 0
for t in texts:
    c = man["clips"]["m3"][SC.normalize_text(t)]
    shutil.copy(os.path.join(src, c["id"] + ".ogg"), os.path.join(R, "sound", "clips"))
    n += 1
print("CLIPS", n)
EOF
  ( cd "$R" && find backend scripts sound work -type f | sort | xargs shasum -a 256 ) > "$R/expect.sha256"
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/fcd.tar" -C "$R" . || die tar
  ls -la "$S/fcd.tar"
  echo "FCD_STAGE_OK"
}

do_launch() {
  [ -s "$S/fcd.tar" ] || die "묶음 없음(stage 먼저)"
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
  POD=$(pod_id)
  echo "FCD_POD $POD"
  bash "$P" wait || { bash "$P" terminate --force || true; die wait; }
  step "올리기 속도 점검(8MB)"
  T0=$(python3 -c 'import time; print(time.time())')
  head -c 8388608 /dev/urandom | perl -e 'alarm 90; exec @ARGV' bash "$P" ssh 'cat > /workspace/.speedtest && wc -c < /workspace/.speedtest && rm -f /workspace/.speedtest' \
    || { bash "$P" terminate --force || true; die speedtest; }
  T1=$(python3 -c 'import time; print(time.time())')
  echo "UPLOAD_MBPS $(python3 -c "print(round(8 / max(1e-3, $T1 - $T0), 2))") (연결 하나)"
  bash "$P" ssh 'nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; free -g | head -2; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
  step "올리기"
  python3 "$LAB/tools/pod/pupload.py" "$S/fcd.tar" /workspace/fcd.tar --chunk-mb 2 --par 8 > "$S/pupload.log" 2>&1
  PUP_RC=$?
  tail -n 3 "$S/pupload.log"
  { [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=1 fail=0' "$S/pupload.log"; } || die "upload(pupload rc=$PUP_RC, 파드는 그대로: finish로 정리)"
  bash "$P" ssh 'mkdir -p /workspace/fcd && cd /workspace/fcd && tar -xf ../fcd.tar && rm -f ../fcd.tar && sha256sum -c --quiet expect.sha256 && echo REMOTE_SHA_OK' \
    | tee "$S/unpack.log" || die "풀기"
  grep -q '^REMOTE_SHA_OK' "$S/unpack.log" || die "파드 쪽 sha256 불일치"
  step "forms_run.sh 시작"
  bash "$P" run "bash /workspace/fcd/scripts/forms_run.sh" || die run
  echo "FCD_LAUNCH_OK $POD"
}

do_fetch() {
  POD=$(pod_id)
  [ -n "$POD" ] || die "파드 없음"
  out="$LAB/data/pod_runs/$(date +%Y%m%d)_${POD}/fcd"
  mkdir -p "$out"
  bash "$P" ssh 'cd /workspace/fcd && tar -czf - work/asr.jsonl work/scored.jsonl work/items.json work/run.env work/spec.json work/extra.json out logs 2>/dev/null' \
    | tar -xzf - -C "$out" && echo "FCD_FETCH_OK $out" || echo "FCD_FETCH_WARN"
  ls -la "$out" "$out/work" "$out/out" 2>/dev/null | tail -20
}

case "$CMD" in
  stage) do_stage ;;
  launch) do_launch ;;
  tail) bash "$P" ssh 'tail -n 30 /workspace/fcd/logs/run.log' ;;
  fetch) do_fetch ;;
  finish) do_fetch; bash "$P" terminate --force || true; bash "$P" status || true ;;
  *) echo "forms_session.sh stage|launch|tail|fetch|finish"; exit 2 ;;
esac
