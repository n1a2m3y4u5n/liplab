#!/bin/bash
# 파드 쪽 소리 품질 점검·재합성(docs/sound-qa-2026-10.md). qa_session.sh가 올리고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
#   bash qa_run.sh            전체(설정 → 기존 점검 → 1단계 후보 → 2단계 후보 → 선택 → 인코딩 → 묶음)
#   MODE=missing bash qa_run.sh   목록에 없던 글만(targets.jsonl에 orig_id가 없음): 기존 점검·정리 결정을 건너뛰고 qa_ref.json 기준
# 단계 표식 work/.done_<단계>, 로그 logs/run.log, 끝 표식 QA_ALL_OK / 실패 QA_FAIL <단계>.
set -uo pipefail
R=/workspace/sqa
cd $R
mkdir -p logs work/asr work/eval work/cand work/enc
exec >> logs/run.log 2>&1
echo "=== $(date '+%F %T') 시작 pid=$$ MODE=${MODE:-full}"
export HF_HOME=/workspace/hf UV_CACHE_DIR=/workspace/.uvcache PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
export LIPLAB_BACKEND=$R/backend TOKENIZERS_PARALLELISM=false
W=$R/work
X=$R/scripts
ST=$R/venv/st/bin/python
SC=$R/venv/score/bin/python
fail() { echo "QA_FAIL $*"; exit 1; }
done_() { [ -f "$W/.done_$1" ]; }
mark() { touch "$W/.done_$1"; echo "$(date '+%T') STEP_OK $1"; }

# CPU 할당(cgroup) 기준 병렬 수: 프로세스마다 2스레드
# cgroup v2(cpu.max)나 v1(cpu.cfs_quota_us)의 할당 코어. nproc·cpu_count는 호스트 코어(96)를 보여 과다 구독이 된다
CPUS=$(python3 -c "import os
def rd(p):
    try: return open(p).read().split()
    except OSError: return None
q = rd('/sys/fs/cgroup/cpu.max')
if q and q[0] != 'max': print(max(1, int(int(q[0]) / int(q[1])))); raise SystemExit
a, b = rd('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'), rd('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
if a and b and int(a[0]) > 0: print(max(1, int(int(a[0]) / int(b[0])))); raise SystemExit
print(min(8, os.cpu_count()))")
NP=$(( CPUS / 2 )); [ "$NP" -lt 2 ] && NP=2; [ "$NP" -gt 8 ] && NP=8
NA=${NA:-2}   # GPU 전사 프로세스 수
echo "cpus=$CPUS eval_procs=$NP asr_procs=$NA"

# ── 설정 ──
if ! done_ setup; then
  (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1)) || fail apt
  command -v uv >/dev/null || pip install -q uv || fail uv
  uv venv -q -p 3.11 venv/st && uv pip install -q -p venv/st/bin/python "supertonic==1.3.1" soundfile numpy scipy || fail venv_st
  uv venv -q -p 3.11 venv/score && uv pip install -q -p venv/score/bin/python "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu || fail torch
  uv pip install -q -p venv/score/bin/python "transformers==5.17.0" faster-whisper soundfile numpy scipy python-Levenshtein \
    nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || fail venv_score
  mark setup
fi
SP=$R/venv/score/lib/python3.11/site-packages
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
if ! done_ smoke; then
  $SC $X/qa_rules.py selftest || fail selftest
  $ST -c "import inspect, supertonic; from supertonic import TTS; print('supertonic', getattr(supertonic,'__version__','?')); print('init', inspect.signature(TTS.__init__)); print('synth', inspect.signature(TTS.synthesize))" || fail st_import
  # 기본값 확인(문서 3절: 지금 클립 설정 total_steps 8, speed 1.05)과 시드 재현성
  $ST - <<'EOF' || fail st_seed
import inspect, numpy as np
from supertonic import TTS
t = TTS(auto_download=True)
src = inspect.getsource(TTS.synthesize)
print("synthesize defaults", {k: v.default for k, v in inspect.signature(t.synthesize).parameters.items() if v.default is not inspect._empty})
st = t.get_voice_style(voice_name="M1")
outs = []
for s in (0, 0, 1):
    np.random.seed(s)
    w, _ = t.synthesize("사과", voice_style=st, lang="ko", total_steps=8, speed=1.05)
    outs.append(np.asarray(w).reshape(-1))
same = outs[0].shape == outs[1].shape and float(np.max(np.abs(outs[0] - outs[1]))) < 1e-6
diff = outs[0].shape != outs[2].shape or float(np.max(np.abs(outs[0][:len(outs[2])] - outs[2][:len(outs[0])]))) > 1e-4
print("SEED_REPRO same_seed_identical=%s other_seed_differs=%s" % (same, diff))
EOF
  $SC -c "import ctranslate2; print('ct2 cuda devices', ctranslate2.get_cuda_device_count())" || fail ct2
  mark smoke
fi

run_asr() {  # 후보목록 이름 [uids]
  local cands=$1 name=$2 uids=${3:-} i
  for i in $(seq 0 $((NA - 1))); do
    $SC $X/qa_asr.py $W/targets.jsonl $W/asr/$name.$i.jsonl --cands "$cands" --clips $R/sound/clips --cand-root $W/cand \
      --shard $i/$NA ${uids:+--uids $uids} >> logs/asr_$name.log 2>&1 &
  done
}
run_eval() {
  local cands=$1 name=$2 uids=${3:-} i
  for i in $(seq 0 $((NP - 1))); do
    $SC $X/qa_eval.py $W/targets.jsonl $W/eval/$name.$i.jsonl --cands "$cands" --clips $R/sound/clips --cand-root $W/cand \
      --models $R/models/dgop_ours --shard $i/$NP --threads 2 ${uids:+--uids $uids} >> logs/eval_$name.log 2>&1 &
  done
}
measure() {  # 후보목록 이름 [uids] — 전사(GPU)와 D-GOP·신호(CPU)를 함께 돌리고 둘 다 끝날 때까지
  run_asr "$@"; run_eval "$@"; wait
  grep -c ASR_OK logs/asr_$2.log | xargs echo "asr_ok_procs"; grep -c EVAL_OK logs/eval_$2.log | xargs echo "eval_ok_procs"
  [ "$(grep -c ASR_OK logs/asr_$2.log)" -ge "$NA" ] && [ "$(grep -c EVAL_OK logs/eval_$2.log)" -ge "$NP" ]
}
synth() {  # 후보목록 uids
  local cands=$1 uids=$2 i S=$(( CPUS / 2 )); [ "$S" -lt 2 ] && S=2; [ "$S" -gt 8 ] && S=8
  for i in $(seq 0 $((S - 1))); do
    $ST $X/qa_synth.py $W/targets.jsonl $W/cand --cands "$cands" --uids "$uids" --shard $i/$S --threads 2 >> logs/synth.log 2>&1 &
  done
  wait
  echo "synth_ok_procs $(grep -c 'SYNTH_OK.*cands='"$cands" logs/synth.log)"
}

# ── 기존 클립 점검 ──
if [ "${MODE:-full}" = full ]; then
  if ! done_ orig; then
    measure orig orig || fail orig_measure
    $SC $X/qa_judge.py judge $W --cands orig && $SC $X/qa_judge.py ref $W && $SC $X/qa_judge.py judge $W --cands orig || fail orig_judge
    $SC $X/qa_judge.py decide $W ${FORCE_NORMALIZE:+--force-normalize $FORCE_NORMALIZE} || fail decide
    mark orig
  fi
else
  if ! done_ orig; then
    cp $X/qa_ref.json $W/ref.json || fail ref
    python3 -c "import json;print('\n'.join(json.loads(l)['uid'] for l in open('$W/targets.jsonl') if l.strip()))" > $W/stage1.uids
    echo '{"normalize": true, "mode": "missing"}' > $W/plan.json
    mark orig
  fi
fi

# ── 1단계 후보 c0·c1 ──
if ! done_ stage1; then
  synth c0,c1 $W/stage1.uids
  measure c0,c1 s1 $W/stage1.uids || fail s1_measure
  $SC $X/qa_judge.py judge $W --cands c0,c1 && $SC $X/qa_judge.py escalate $W || fail s1_judge
  mark stage1
fi
# ── 2단계 후보 c2~c7(1단계에 통과 후보가 없는 것만) ──
if ! done_ stage2; then
  if [ -s $W/stage2.uids ]; then
    synth c2,c3,c4,c5,c6,c7 $W/stage2.uids
    measure c2,c3,c4,c5,c6,c7 s2 $W/stage2.uids || fail s2_measure
  fi
  $SC $X/qa_judge.py judge $W --cands c2,c3,c4,c5,c6,c7 || fail s2_judge
  mark stage2
fi
# ── 선택·인코딩·묶음 ──
if ! done_ final; then
  $SC $X/qa_judge.py final $W || fail final
  python3 - <<EOF > $W/enc.list || fail enc_list
import json
for l in open("$W/final.jsonl"):
    r = json.loads(l); print(r["cand"] + "/" + r["uid"])
EOF
  cat $W/enc.list | xargs -P "$CPUS" -I{} bash -c 'w='"$W"'/cand/{}.wav; b=$(echo {} | tr / _); d='"$W"'/enc; \
    [ -s $d/$b.ogg ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 48000 -c:a libopus -b:a 24k -vbr on $d/$b.ogg; \
    [ -s $d/$b.m4a ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 24000 -c:a aac -b:a 24k -movflags +faststart $d/$b.m4a'
  echo "enc ogg=$(ls $W/enc/*.ogg 2>/dev/null | wc -l) m4a=$(ls $W/enc/*.m4a 2>/dev/null | wc -l) want=$(wc -l < $W/enc.list)"
  mark final
fi
# 맥으로 받을 묶음: 판정·선택·요약·인코딩 소리(wav 후보는 빼고)
(cd $W && tar -czf $R/result.tgz final.jsonl summary.json plan.json ref.json judged.*.jsonl enc stage1.uids stage2.uids -C $R logs) || fail pack
ls -la $R/result.tgz
echo "QA_ALL_OK"
