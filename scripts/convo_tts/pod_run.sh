#!/bin/bash
# 파드 쪽 측정(docs/listen-convo-tts-2026-10.md 5절). session.sh가 올리고 띄운다. 다시 불러도 끝난 단계는 건너뛴다.
# 단계 표식 work/.done_<단계>, 로그 logs/run.log, 끝 표식 CT_ALL_OK / 실패 CT_FAIL <단계>.
set -uo pipefail
R=/workspace/ct
cd $R
mkdir -p logs work
exec >> logs/run.log 2>&1
echo "=== $(date '+%F %T') 시작 pid=$$"
export HF_HOME=$R/hf UV_CACHE_DIR=/workspace/.uvcache PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
export SUPERTONIC_CACHE_DIR=$R/supertonic3
B=$R/backend
W=$R/work
X=$R/scripts
APP=$R/venv/app/bin/python
QA=$R/venv/qa/bin/python
fail() { echo "CT_FAIL $*"; exit 1; }
done_() { [ -f "$W/.done_$1" ]; }
mark() { touch "$W/.done_$1"; echo "$(date '+%T') STEP_OK $1"; }
nproc; cat /sys/fs/cgroup/cpu.max 2>/dev/null; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null; free -g | head -2

# ── 설정: 앱 가상환경(이미지와 같은 판) + 품질 가상환경(10/7 qa_run.sh와 같은 판) ──
if ! done_ setup; then
  (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1)) || fail apt
  command -v uv >/dev/null || pip install -q uv || fail uv
  uv venv -q -p 3.11 venv/app || fail venv_app
  uv pip install -q -p $APP -r $B/requirements.txt || fail req
  uv pip install -q -p $APP "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu || fail torch
  uv pip install -q -p $APP -r $B/requirements-infer.txt "supertonic==1.3.1" || fail infer
  uv venv -q -p 3.11 venv/qa || fail venv_qa
  uv pip install -q -p $QA "torch==2.14.0" --index-url https://download.pytorch.org/whl/cpu || fail qa_torch
  uv pip install -q -p $QA "transformers==5.17.0" faster-whisper soundfile numpy scipy python-Levenshtein requests \
    nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || fail qa_pkgs
  $APP -m pip --version >/dev/null 2>&1 || true
  $APP -c "import fastapi, torch, transformers, supertonic, av, faster_whisper; print('app', torch.__version__, transformers.__version__, faster_whisper.__version__)" || fail app_import
  mark setup
fi
# ── 모델(이미지 빌드와 같은 단계): Whisper base, 아바타 백본 int8(fp32 캐시는 지움), Supertonic 3 ──
if ! done_ models; then
  ( cd $B && WHISPER_MODEL=base $APP -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" ) || fail whisper
  ( cd $B && $APP -c "import quant_int8 as Q; print('wavlm int8:', Q.export_base('microsoft/wavlm-large', 'models/wavlm_large_int8'))" ) || fail wavlm
  rm -rf "$HF_HOME/hub/models--microsoft--wavlm-large"
  ( cd $B && $APP -c "from supertonic import TTS; t = TTS(auto_download=True); print('supertonic', t.model_dir, t.sample_rate, t.voice_style_names)" ) || fail supertonic
  du -sh $SUPERTONIC_CACHE_DIR $B/models/* $HF_HOME
  mark models
fi
du -sb $SUPERTONIC_CACHE_DIR | awk '{print "SUPERTONIC_BYTES", $1}'

server_env() {   # fly.dev.toml [env] + 이 측정의 켜기
  echo "PORT=8080 PYTHONUNBUFFERED=1 DATABASE_URL=sqlite+aiosqlite:///$W/$1.db JWT_SECRET=ct-measure-only LIPLAB_AI_ITEMS=0 \
LIPLAB_UNLOCK_ALL=demo DGOP_ALIGNER_ID=$B/models/dgop_ours/aligner DGOP_SCORER_ID=$B/models/dgop_ours/scorer \
DGOP_CALIBRATION=$B/data/dgop_calibration_ours.json HF_HUB_OFFLINE=1 BACKBONE_QUANT=int8 LIPLAB_WARMUP=1 LIPLAB_REVIEW=1 \
WHISPER_MODEL=base OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 LIPLAB_SOUND_THREADS=2 LIPLAB_SOUND_DYNAMIC=1 LIPLAB_SOUND_CACHE_DIR=$W/cache_$1 \
LIPLAB_SOUND_KEEP_REJECTED=1 LIPLAB_LLM_BUDGET_FILE=$W/llm_$1.json"
}

run_server() {   # 이름 추가환경
  local name=$1; shift
  rm -rf $W/cache_$name $W/$name.db
  ( cd $B && env -u ANTHROPIC_API_KEY $(server_env $name) "$@" taskset -c 0,1 $APP -m uvicorn main:app --host 127.0.0.1 --port 8080 --workers 1 \
      > $R/logs/server_$name.log 2>&1 & echo $! > $W/server_$name.pid )
  # $!는 감싼 셸의 PID라 서버(python) PID를 따로 찾는다(메모리는 그 프로세스의 /proc/PID/status로 잰다)
  local pid=""
  for i in $(seq 1 30); do
    pid=$(pgrep -f "^$APP -m uvicorn main:app" | head -1)
    [ -n "$pid" ] && break; sleep 0.5
  done
  [ -n "$pid" ] || return 1
  echo "server $name pid=$pid"
  taskset -pc $pid
  taskset -pc $pid | grep -q "list: 0,1$\|list: 0-1$" || { echo "affinity 아님"; kill $pid; return 1; }
  OMP_NUM_THREADS=1 taskset -c 4,5 $QA $X/measure.py $name --pid $pid --out $W/measure_$name.json --fixture $X/fixture_items.json \
    --sound-dir $B/data/sound --log $R/logs/server_$name.log --backend $B > $R/logs/measure_$name.log 2>&1
  local rc=$?
  grep -E "PHASE|MEASURE_OK" $R/logs/measure_$name.log | cut -c1-400
  cat /proc/$pid/status | grep -E "VmHWM|VmRSS" || true
  kill $pid; sleep 3; kill -9 $pid 2>/dev/null || true
  [ $rc = 0 ] || return 1
}

if [ "${STAGES:-main}" = explore ]; then
  # 사후 탐색(보고만): 같은 생성 흐름 뒤 클립 120개를 더 만들 때의 메모리, glibc 아레나 제한(MALLOC_ARENA_MAX=2) 유무
  done_ explore_a || { run_server explore_a LIPLAB_LISTEN_GEN=1 LIPLAB_LISTEN_GEN_FIXTURE=$X/fixture_items.json LIPLAB_ML_CONCURRENCY=1 || fail explore_a; mark explore_a; }
  done_ explore_b || { run_server explore_b MALLOC_ARENA_MAX=2 LIPLAB_LISTEN_GEN=1 LIPLAB_LISTEN_GEN_FIXTURE=$X/fixture_items.json LIPLAB_ML_CONCURRENCY=1 || fail explore_b; mark explore_b; }
  tar -czf $R/result.tgz -C $R work/measure_explore_a.json work/measure_explore_b.json logs 2>/dev/null
  echo "CT_ALL_OK"
  exit 0
fi
if ! done_ server1; then
  run_server server1 LIPLAB_LISTEN_GEN=1 LIPLAB_LISTEN_GEN_FIXTURE=$X/fixture_items.json LIPLAB_ML_CONCURRENCY=1 || fail server1
  mark server1
fi
if ! done_ server2; then
  run_server server2 LIPLAB_LISTEN_GEN=0 LIPLAB_ML_CONCURRENCY=3 || fail server2
  mark server2
fi

# ── 품질(10/7 기존 클립 점검과 같은 방법) ──
SP=$R/venv/qa/lib/python3.11/site-packages
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
export LIPLAB_BACKEND=$B
if ! done_ qa; then
  $QA $X/qa_targets.py $W/cache_server1 $W/qa_served $W/qa_rejected || fail qa_targets
  for k in served rejected; do
    WK=$W/qa_$k
    [ -s $WK/targets.jsonl ] || continue
    CL=$W/cache_server1; [ $k = rejected ] && CL=$W/cache_server1/rejected
    mkdir -p $WK/asr $WK/eval
    $QA $X/qa_asr.py $WK/targets.jsonl $WK/asr/a.0.jsonl --cands orig --clips $CL --cand-root $WK/cand >> logs/qa_asr_$k.log 2>&1 || fail asr_$k
    for i in 0 1 2; do
      OMP_NUM_THREADS=2 DGOP_DEVICE=cpu $QA $X/qa_eval.py $WK/targets.jsonl $WK/eval/e.$i.jsonl --cands orig --clips $CL --cand-root $WK/cand \
        --models $B/models/dgop_ours --shard $i/3 --threads 2 >> logs/qa_eval_$k.log 2>&1 &
    done
    wait
    $QA $X/qa_judge.py judge $WK --cands orig --ref $X/qa_ref.json || fail judge_$k
  done
  mark qa
fi
$QA $X/summarize.py $W > $W/summary.txt 2>&1 || echo "SUMMARY_WARN"
cat $W/summary.txt | head -80
tar -czf $R/result.tgz -C $R work/measure_server1.json work/measure_server2.json work/summary.json work/summary.txt \
  work/qa_served work/qa_rejected work/cache_server1/index.json work/cache_server1/convo_items.json logs 2>/dev/null
echo "CT_ALL_OK"
