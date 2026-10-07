#!/bin/bash
# 파드 쪽 목소리별 대조 측정·다시 합성(docs/listen-voice-contrast-2026-10.md). contrast_session.sh가 올리고 띄운다.
#   bash contrast_run.sh score     kresnik CTC 점수(work/score.jsonl) → VC_SCORE_OK
#   bash contrast_run.sh setup2    다시 합성용 가상환경(소리 품질 점검과 같은 판: supertonic 1.3.1, torch 2.14 CPU, transformers 5.17,
#                                  faster-whisper) → VC_SETUP2_OK
#   bash contrast_run.sh resynth   후보 c0~c15 합성 → 전사·D-GOP·판정 → margin → 채택 → 인코딩 → Ogg 다시 매기기 → 묶음 → VC_RESYNTH_OK
# 다시 불러도 끝난 단계는 건너뛴다(work/.done_<단계>). 로그 logs/<명령>.log.
set -uo pipefail
V=/workspace/vc
CMD=${1:-}
mkdir -p $V/logs
exec >> $V/logs/$CMD.log 2>&1
echo "=== $(date '+%F %T') $CMD 시작 pid=$$"
export HF_HOME=/workspace/hf PIP_DISABLE_PIP_VERSION_CHECK=1 TOKENIZERS_PARALLELISM=false PYTHONDONTWRITEBYTECODE=1
fail() { echo "VC_FAIL $CMD $*"; exit 1; }
done_() { [ -f "$1/.done_$2" ]; }
mark() { touch "$1/.done_$2"; echo "$(date '+%T') STEP_OK $2"; }
CPUS=$(python3 -c "import os
def rd(p):
    try: return open(p).read().split()
    except OSError: return None
q = rd('/sys/fs/cgroup/cpu.max')
if q and q[0] != 'max': print(max(1, int(int(q[0]) / int(q[1])))); raise SystemExit
a, b = rd('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'), rd('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
if a and b and int(a[0]) > 0: print(max(1, int(int(a[0]) / int(b[0])))); raise SystemExit
print(min(8, os.cpu_count()))")
echo "cpus=$CPUS"

# 판정자 환경: 이미지의 torch 2.1(cu118)에 transformers 4.46.3(폼 C·D 측정과 같은 판)
judge_env() {
  [ -f $V/.judge_ok ] && return 0
  (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1)) || fail apt
  pip install -q "transformers==4.46.3" "numpy<2" soundfile || fail pip
  python -c "import torch, transformers; print('torch', torch.__version__, 'tf', transformers.__version__, torch.cuda.get_device_name(0))" || fail import
  touch $V/.judge_ok
}

case "$CMD" in
score)
  W=$V/work; mkdir -p $W
  judge_env
  python $V/scripts/contrast_score.py x y --clips x --selftest || fail selftest
  python $V/scripts/contrast_score.py $W/targets.jsonl $W/score.jsonl --clips $V/sound/clips || fail score
  echo "rows=$(wc -l < $W/score.jsonl) err=$(grep -c '"err"' $W/score.jsonl)"
  echo "VC_SCORE_OK"
  ;;
setup2)
  R=/workspace/sqa; mkdir -p $R/work
  if ! done_ $R/work setup; then
    (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1)) || fail apt
    export UV_CACHE_DIR=/workspace/.uvcache
    command -v uv >/dev/null || pip install -q uv || fail uv
    cd $R
    uv venv -q -p 3.11 venv/st && uv pip install -q -p venv/st/bin/python "supertonic==1.3.1" soundfile numpy scipy || fail venv_st
    uv venv -q -p 3.11 venv/score && uv pip install -q -p venv/score/bin/python "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu || fail torch
    uv pip install -q -p venv/score/bin/python "transformers==5.17.0" faster-whisper soundfile numpy scipy python-Levenshtein \
      nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || fail venv_score
    # 엔진 내려받기·예열(합성 자체는 resynth에서)
    venv/st/bin/python -c "from supertonic import TTS; t = TTS(auto_download=True); print('supertonic ok')" || fail st
    mark $R/work setup
  fi
  echo "VC_SETUP2_OK"
  ;;
resynth)
  R=/workspace/sqa; W=$R/work; X=$R/scripts
  cd $R
  done_ $W setup || fail "setup2 먼저"
  export LIPLAB_BACKEND=$R/backend
  ST=$R/venv/st/bin/python; SC=$R/venv/score/bin/python
  SP=$R/venv/score/lib/python3.11/site-packages
  ALL=c0,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,c14,c15
  NP=$(( CPUS / 2 )); [ "$NP" -lt 2 ] && NP=2; [ "$NP" -gt 8 ] && NP=8
  mkdir -p $W/asr $W/eval $W/cand $W/enc
  python3 -c "import json;print('\n'.join(json.loads(l)['uid'] for l in open('$W/targets.jsonl') if l.strip()))" > $W/all.uids
  echo "targets=$(wc -l < $W/all.uids) procs=$NP"
  if ! done_ $W synth; then
    for i in $(seq 0 $((NP - 1))); do
      $ST $X/qa_synth.py $W/targets.jsonl $W/cand --cands $ALL --uids $W/all.uids --shard $i/$NP --threads 2 >> logs/synth.log 2>&1 &
    done
    wait
    [ "$(grep -c SYNTH_OK logs/synth.log)" -ge "$NP" ] || fail synth
    mark $W synth
  fi
  if ! done_ $W measure; then
    export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
    for i in 0 1; do
      $SC $X/qa_asr.py $W/targets.jsonl $W/asr/r.$i.jsonl --cands $ALL --clips $R/sound/clips --cand-root $W/cand --shard $i/2 >> logs/asr.log 2>&1 &
    done
    for i in $(seq 0 $((NP - 1))); do
      env DGOP_DEVICE=cpu $SC $X/qa_eval.py $W/targets.jsonl $W/eval/r.$i.jsonl --cands $ALL --clips $R/sound/clips --cand-root $W/cand \
        --models $R/models/dgop_ours --shard $i/$NP --threads 2 >> logs/eval.log 2>&1 &
    done
    wait
    [ "$(grep -c ASR_OK logs/asr.log)" -ge 2 ] && [ "$(grep -c EVAL_OK logs/eval.log)" -ge "$NP" ] || fail measure
    unset LD_LIBRARY_PATH
    mark $W measure
  fi
  if ! done_ $W judge; then
    $SC $X/qa_judge.py judge $W --cands $ALL --ref $X/qa_ref.json || fail judge
    mark $W judge
  fi
  if ! done_ $W margin; then
    judge_env
    python $X/contrast_pick.py wavmap $W > $W/wavmap.json || fail wavmap
    python $X/contrast_score.py $W/comps.jsonl $W/cand_score.jsonl --clips $R/sound/clips --wav-map $W/wavmap.json || fail margin
    mark $W margin
  fi
  if ! done_ $W pick; then
    python $X/contrast_pick.py pick $W || fail pick
    cut -f1 $W/enc.list | while read -r cu; do
      c=${cu%%/*}; u=${cu#*/}; w=$W/cand/$c/$u.wav; b=${c}_$u
      [ -s $W/enc/$b.ogg ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 48000 -c:a libopus -b:a 24k -vbr on $W/enc/$b.ogg
      [ -s $W/enc/$b.m4a ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 24000 -c:a aac -b:a 24k -movflags +faststart $W/enc/$b.m4a
    done
    python $X/contrast_pick.py encmap $W > $W/encmap.json || fail encmap
    rm -f $W/enc_score.jsonl
    python $X/contrast_score.py $W/comps.jsonl $W/enc_score.jsonl --clips $R/sound/clips --wav-map $W/encmap.json || fail enc_margin
    python $X/contrast_pick.py final $W || fail final
    mark $W pick
  fi
  (cd $W && tar -czf $R/result.tgz final.jsonl pick.json cand_score.jsonl enc_score.jsonl judged.*.jsonl enc targets.jsonl comps.jsonl \
     -C $R logs) || fail pack
  ls -la $R/result.tgz
  echo "VC_RESYNTH_OK"
  ;;
*) echo "contrast_run.sh score|setup2|resynth"; exit 2 ;;
esac
