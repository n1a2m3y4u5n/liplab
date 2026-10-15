#!/bin/bash
# v1_session.sh(맥, 2026-10-15): V1 재학습·판정 한 번에. 사전등록 liplab-integrate docs/lipread-v1-prereg-2026-10.md.
#   묶음(새 화자 클립 data/v1_538r + 기존 68명 bs·spans + 평가 40명 목록) → 파드 생성(워치독 WD_MIN) → setup → 올리기
#   → smoke → extract → align → 새 화자 bs·spans 먼저 받기 → v1_remote.sh(벤치·학습·선택·평가·판정) → 결과 받기 → terminate.
#   파드를 만든 뒤의 모든 실패는 받을 수 있는 것을 받고 파드를 끝낸다. 다른 작업과 상태가 섞이지 않게 상태 폴더와 이름을 따로 쓴다.
#   [GPUS="NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE"] [WD_MIN=330] bash v1_session.sh [--stage-only]
set -uo pipefail
cd "$(dirname "$0")"
LAB=$(cd ../.. && pwd)
P=pod.sh
export POD_STATE_DIR=${POD_STATE_DIR:-$LAB/tools/pod/.v1state} POD_NAME=${POD_NAME:-liplab-v1}
R=$LAB/data/v1_538r
PR=$LAB/data/pod_runs
S=${V1STAGE:-$LAB/data/v1stage}
INTEG=${INTEG:-$HOME/Downloads/LIPLAB_ALL/wt-v1}
GPUS=${GPUS:-NVIDIA A40|SECURE,NVIDIA RTX A6000|SECURE}
WD_MIN=${WD_MIN:-330}
STAGE_ONLY=0
[ "${1:-}" = --stage-only ] && STAGE_ONLY=1
mkdir -p "$S" "$PR" "$POD_STATE_DIR"
LOG="$PR/session_v1_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "$LOG") 2>&1
step() { echo "=== $(date '+%F %T') $*"; }
die() { echo "V1S_FAIL $*"; exit 1; }

step "확인"
grep -q '^V1R_DL end' "$R/v1r_dl.out" || die "받기가 아직 안 끝남(data/v1_538r/v1r_dl.out)"
[ -s "$R/eval40.txt" ] || die "eval40.txt 없음(v1_pick_eval.py)"
cmp -s "$R/eval40.txt" <(git -C "$INTEG" show HEAD:scripts/lipread_v1/eval40.txt 2>/dev/null) \
  || die "평가 화자 목록이 커밋된 판(scripts/lipread_v1/eval40.txt)과 다름 — 먼저 커밋"

step "묶음"
rm -rf "$S/v1" && mkdir -p "$S/v1/more/clips" "$S/v1/v1" "$S/v1/old"
cp -c "$R/manifest.tsv" "$S/v1/more/manifest.tsv" || die manifest
n=0
while IFS="$(printf '\t')" read -r base _s _t; do
  b=${base%.mp4}
  cp -c "$R/clips/$b.mp4" "$R/clips/$b.wav" "$S/v1/more/clips/" || die "클립 복사 $b"
  n=$((n + 1))
done < "$R/manifest.tsv"
echo "새 화자 클립 $n개, 화자 $(cut -f2 "$R/manifest.tsv" | sort -u | wc -l | tr -d ' ')명"
cat "$PR/20260924_k74l2l74024fsz/d/spans.jsonl" "$PR/20260925_4aol7xkyf762yh/dax/d/spans.jsonl" \
    "$PR/20260925_nwcqu40di2ct11/dax/d/spans.jsonl" > "$S/v1/old/spans.jsonl"
cp -c "$R/eval40.txt" "$S/v1/v1/eval40.txt"
git -C "$INTEG" show HEAD:docs/lipread-v1-prereg-2026-10.md > "$S/v1/v1/prereg.md"
[ -s "$S/old_bs.tgz" ] || (COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czf "$S/old_bs.tgz" \
    -C "$PR/20260924_k74l2l74024fsz" bs -C "$PR/20260925_nwcqu40di2ct11/dax" bs) || die old_bs
cp -c "$PR/20260925_4aol7xkyf762yh/dax/bs_new12.tgz" "$S/bs_new12.tgz"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs --exclude .DS_Store --exclude '._*' -cf "$S/v1.tar" -C "$S/v1" more v1 old \
  || die tar
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -cf "$S/v1code.tar" -C "$LAB/tools" v1_train.py v1_judge.py lip_roi_extract.py \
    -C "$LAB/tools/pod" v1_remote.sh || die code
ls -la "$S"/*.tar "$S"/*.tgz
[ "$STAGE_ONLY" = 1 ] && { echo V1S_STAGE_ONLY_OK; exit 0; }

step "잔액"
bash $P status | tail -n 3
bal=$(bash $P status | awk '/^BALANCE/ {gsub(/\$/, "", $2); print int($2)}')
[ "${bal:-0}" -ge 5 ] || die "잔액 ${bal:-?}달러 < 5"

step "파드 생성(워치독 ${WD_MIN}분, 상태 $POD_STATE_DIR, 이름 $POD_NAME)"
created=0
IFS=',' read -r -a CANDS <<< "$GPUS"
for cand in "${CANDS[@]}"; do
  g=${cand%%|*}; c=${cand#*|}
  step "후보 $g / $c"
  if bash $P create "$g" "$c" --watchdog "$WD_MIN"; then created=1; break; fi
done
[ "$created" = 1 ] || die "create(모든 후보 실패, 파드 없음)"
POD=$(awk -F= '$1 == "POD_ID" {print $2}' "$POD_STATE_DIR/.pod_state" 2>/dev/null)
OUT="$PR/$(date +%Y%m%d)_${POD:-unknown}"
mkdir -p "$OUT"
echo "V1S_POD $POD → $OUT"
bash $P wait || { bash $P terminate --force || true; die wait; }
finish() {
  step "결과 받기·종료"
  mkdir -p "$OUT/dax"
  bash $P ssh 'cd /workspace/dax && tar -cf - v1/*.json v1/*.txt v1/*.md v1/*.onnx v1/run_*/train_summary.json v1/run_*/model.pt d/spans.jsonl d/build_cd_stats.json logs manifest_all.tsv 2>/dev/null' \
    | tar -xf - -C "$OUT/dax" || echo "받기 경고(결과)"
  bash $P ssh 'cd /workspace/dax && tar -czf - v1/bench_v1.pkl 2>/dev/null' | tar -xzf - -C "$OUT/dax" || echo "받기 경고(벤치)"
  bash $P ssh 'cd /workspace/dax && [ -d roi ] && tar -cf - roi' | tar -xf - -C "$OUT/dax" || echo "받기 경고(입 영역)"
  ls -la "$OUT/dax" "$OUT/dax/v1" 2>/dev/null | head -40
  bash $P terminate --force || true
  bash $P status || true
}
step "setup"
bash $P setup || { finish; die setup; }
step "올리기"
python3 pupload.py "$S/v1.tar" /workspace/v1.tar "$S/old_bs.tgz" /workspace/old_bs.tgz "$S/bs_new12.tgz" /workspace/bs_new12.tgz \
    --chunk-mb 8 --par 24 > "$S/pupload.log" 2>&1
PUP_RC=$?
tail -n 3 "$S/pupload.log"
{ [ "$PUP_RC" = 0 ] && grep -q '^PUP_DONE ok=3 fail=0' "$S/pupload.log"; } || { finish; die "upload(rc=$PUP_RC)"; }
bash $P ssh 'cd /workspace/dax && tar -xf /workspace/v1.tar && tar -xzf /workspace/old_bs.tgz -C old && tar -xzf /workspace/bs_new12.tgz -C old && rm -f /workspace/v1.tar /workspace/old_bs.tgz /workspace/bs_new12.tgz && bash remote.sh mkmanifest && ls more/clips | wc -l && ls old/bs | wc -l && wc -l < old/spans.jsonl' \
  || { finish; die unpack; }
bash $P ssh 'tar -xf - -C /workspace/dax' < "$S/v1code.tar" || { finish; die code; }
step "smoke(아바타 항목 건너뜀)"
bash $P run 'env SMOKE_SKIP="a4_selftest a4_synth a4_featurize a4_plan a4_cv a4_report a4_product a4_fixed_plan a4_fixed_cv a4_evalckpt a4_fixed_report lipread_tiny" bash remote.sh smoke' || { finish; die smoke_run; }
WAITFOR_MAX_MIN=40 WAIT_POLL=20 bash $P waitfor SMOKE_OK logs/smoke.log || { finish; die smoke; }
step "extract"
EXTRACT_MAX_MIN=120 bash $P stage extract || { finish; die extract; }
step "align"
bash $P stage align || { finish; die align; }
step "새 화자 bs·spans 먼저 받기"
mkdir -p "$OUT/dax"
bash $P ssh 'cd /workspace/dax && tar -czf - bs d/spans.jsonl d/build_cd_stats.json logs/extract_stats.json extract_fail.txt 2>/dev/null' \
  | tar -xzf - -C "$OUT/dax" || echo "받기 경고(bs)"
echo "받은 bs $(ls "$OUT/dax/bs" 2>/dev/null | wc -l | tr -d ' ')개"
step "V1(벤치·학습·선택·평가·판정)"
bash $P run 'bash v1_remote.sh' || { finish; die v1_run; }
WAITFOR_MAX_MIN=${V1_MAX_MIN:-200} WAIT_POLL=60 bash $P waitfor V1_ALL_OK logs/v1.log \
  || { bash $P ssh 'tail -n 40 /workspace/dax/logs/v1.log'; finish; die v1; }
bash $P ssh 'grep -E "^V1|^  |^\[A|^\[B" /workspace/dax/logs/v1.log | grep -v "^  \[" | tail -n 60'
finish
echo V1S_DONE
