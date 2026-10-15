#!/bin/bash
# v1_remote.sh — 파드 쪽 V1 단계(2026-10-15, 사전등록 docs/lipread-v1-prereg-2026-10.md). /workspace/dax 에서.
#   remote.sh extract·align이 끝난 뒤 v1_session.sh가 'pod.sh run'으로 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
#   벤치(기존 68명 old/ + 새 화자 bs/·d/spans.jsonl) → 분할 → 입 영역 추출(CPU, 뒤에서) → 후보 A·B × 시드 0·1·2 학습(GPU 하나에 동시)
#   (맥 시험: DAX=<폴더> PY=<파이썬> V1_SKIP_ROI=1 V1_TRAIN_EXTRA="--epochs 1 --max-items 200 --max-val 100" bash v1_remote.sh)
#   → 선택(검증 화자만) → 평가 40명 product4way(현재 모델 + 6개) → 판정 → 선택 모델 ONNX → V1_ALL_OK / V1_FAIL
set -uo pipefail
cd "${DAX:-/workspace/dax}"
mkdir -p logs v1
exec >> logs/v1.log 2>&1
echo "=== [v1] start pid=$$ at=$(date '+%FT%T') ==="
echo $$ > logs/v1.pid
PY=${PY:-python}
fail() { echo "V1_ALL_FAIL $*"; exit 1; }
beat() {  # PID... — 모두 끝날 때까지 5분마다 진행 한 줄씩(맥 waitfor의 정체 감지 30분 대비)
  local p any
  while :; do
    any=0
    for p in "$@"; do kill -0 "$p" 2>/dev/null && any=1; done
    [ "$any" = 1 ] || break
    sleep "${BEAT_S:-300}"
    echo "[v1 $(date +%H:%M)] $(for f in logs/v1_train_*.log logs/v1_p4_*.log; do [ -f "$f" ] && printf '%s: %s | ' "$(basename "$f" .log)" "$(tail -n 1 "$f" | cut -c1-60)"; done)"
  done
}
NCPU=$(nproc 2>/dev/null || echo 8)
EV=$(grep -v '^#' v1/eval40.txt | grep . | paste -sd, -)
[ -n "$EV" ] || fail "v1/eval40.txt 없음"

if [ ! -s v1/bench_v1.pkl ]; then
  $PY d_bench.py build --spans old/spans.jsonl --bs old/bs --spans d/spans.jsonl --bs bs --rule 3,3 --out v1/bench_v1.pkl \
      > logs/v1_build.log 2>&1 || { tail -n 20 logs/v1_build.log; fail build; }
fi
tail -n 3 logs/v1_build.log
echo "V1_BUILD_OK"
$PY v1_train.py split --bench v1/bench_v1.pkl --eval-list v1/eval40.txt --val-n 12 --out v1/split.json || fail split
echo "V1_SPLIT_OK"

# 입 영역(88×88 흑백) — 새 화자 클립만, 학습과 동시에 CPU로(원본 영상을 지운 뒤에도 연구용으로 남길 것)
RW=$(( NCPU / 3 )); [ "$RW" -lt 2 ] && RW=2; [ "$RW" -gt 8 ] && RW=8
if [ "${V1_SKIP_ROI:-0}" != 1 ] && [ ! -f roi/_extract_stats.json ]; then
  ( echo "=== [roi_extract] start pid=$BASHPID ==="; $PY lip_roi_extract.py --clips more/clips --out roi --workers "$RW" --preview 4 ) \
      > logs/roi_extract.log 2>&1 &
  ROI_PID=$!
else
  ROI_PID=""
fi

pids=()
for c in A B; do
  for s in 0 1 2; do
    d=v1/run_${c}${s}
    if grep -q '^V1_TRAIN_DONE' "logs/v1_train_${c}${s}.log" 2>/dev/null && [ -s "$d/train_summary.json" ]; then continue; fi
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY v1_train.py train --bench v1/bench_v1.pkl --split v1/split.json --cand "$c" \
        --seed "$s" --out "$d" --threads 2 ${V1_TRAIN_EXTRA:-} > "logs/v1_train_${c}${s}.log" 2>&1 &
    pids+=("$!")
  done
done
beat "${pids[@]}"
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
for c in A B; do for s in 0 1 2; do
  grep -q '^V1_TRAIN_DONE' "logs/v1_train_${c}${s}.log" || rc=1
  grep -E '^\[data\]|^V1_TRAIN' "logs/v1_train_${c}${s}.log" | sed "s/^/[${c}${s}] /"
done; done
[ "$rc" = 0 ] || fail "train(logs/v1_train_*.log)"
echo "V1_TRAIN_OK"
RUNS=v1/run_A0,v1/run_A1,v1/run_A2,v1/run_B0,v1/run_B1,v1/run_B2
$PY v1_train.py select --runs "$RUNS" --out v1/sel.json || fail select
SEL=$($PY -c 'import json; print(json.load(open("v1/sel.json"))["selected"]["run"])')
echo "V1_SELECT_OK sel=$SEL"

P4=(--scoring greedy_lev,ctc_ll --alpha 1 --pad idle75 --dup 1,2 --speakers "$EV" --boot 10000)
pids=()
OMP_NUM_THREADS=2 $PY d_bench.py product4way --bench v1/bench_v1.pkl --ctc kr_d_lipread_1120.pt "${P4[@]}" \
    --out v1/p4_base.json > logs/v1_p4_base.log 2>&1 &
pids+=("$!")
for r in A0 A1 A2 B0 B1 B2; do
  OMP_NUM_THREADS=2 $PY d_bench.py product4way --bench v1/bench_v1.pkl --ctc "v1/run_$r/model.pt" "${P4[@]}" \
      --out "v1/p4_$r.json" > "logs/v1_p4_$r.log" 2>&1 &
  pids+=("$!")
done
beat "${pids[@]}"
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
for r in base A0 A1 A2 B0 B1 B2; do grep -q '^P4_DONE' "logs/v1_p4_$r.log" || rc=1; done
[ "$rc" = 0 ] || fail "product4way(logs/v1_p4_*.log)"
echo "V1_P4_OK"
S=${SEL##*_}
OTH=$(for r in A0 A1 A2 B0 B1 B2; do [ "$r" = "$S" ] || printf 'v1/p4_%s.json,' "$r"; done)
$PY v1_judge.py --sel v1/sel.json --p4 "v1/p4_$S.json" --base v1/p4_base.json --others "${OTH%,}" --out v1/v1_verdict.json \
    || fail judge
$PY - "$SEL/model.pt" v1/kr_d_lipread_v1.onnx > logs/v1_onnx.log 2>&1 <<'PYX' || echo "[v1] ONNX 내보내기 실패(판정과 무관, logs/v1_onnx.log)"
import inspect, runpy, sys
import torch
_orig = torch.onnx.export
try:
    has_dyn = 'dynamo' in inspect.signature(_orig).parameters
except (TypeError, ValueError):
    has_dyn = False
if not has_dyn:
    def _export(*a, **k):
        k.pop('dynamo', None)
        return _orig(*a, **k)
    torch.onnx.export = _export
sys.argv = ['export_lipread_onnx.py', sys.argv[1], sys.argv[2]]
runpy.run_path('export_lipread_onnx.py', run_name='__main__')
PYX
tail -n 2 logs/v1_onnx.log
if [ -n "${ROI_PID:-}" ]; then wait "$ROI_PID" || echo "[v1] ROI 추출 rc≠0(logs/roi_extract.log)"; fi
tail -n 2 logs/roi_extract.log
echo "V1_ALL_OK $(grep -h '^V1_GATE' logs/v1.log | tail -n 1)"
