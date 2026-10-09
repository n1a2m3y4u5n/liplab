#!/bin/bash
# 608 범주 27 새 화자(파드 쪽, 2026-10-09): run_s13.sh(liplab-lab/tools/pod)의 venv·점검 부분을 그대로 쓰고 단계만 바꾼 판.
#   session_c27.sh가 /workspace에 푼 것: backend(앱 b675975, int8), backend_new(이 브랜치 backend), scripts/{speak_asr_pod_run.py(b675975),
#   scoring_s18_head.py}, tools/{s13_newspk.py, scores_1006.py, build_scores_csv.py, c27_pod.py}, n608/s608/*.flac + labels, bridge/(run1 538 30클립)
#   단계: venv 두 개 → selftest → prep → seg(large-v3, GPU) → c27 jobs(등록 2.1절 고르기) → dgop(b675975, CPU, 로짓 덤프) → S18 특성
#        → trim(지금 앱 D-GOP + 음소, 자기·다른 2·대치 + 다리)
# 표식(/workspace/dax/logs/c27.log): S13_SETUP_OK SEG_OK C27_JOBS_OK S13_DGOP_OK FEAT_OK C27_TRIM_OK C27_OK / C27_FAIL
set -u
W=/workspace
L=$W/dax/logs
O=$W/out
mkdir -p "$L" "$O" "$W/outb"
exec >> "$L/c27.log" 2>&1
echo $$ > "$L/c27.pid"
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "C27_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false SC_W=$W

NC=$(nproc)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -z "$Q" ] && [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
  Q=$(awk -v p="$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)" '{ if ($1 > 0) print int($1 / p) }' /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
fi
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
WK=$(( NC / 2 )); [ "$WK" -lt 1 ] && WK=1
MEMG=$(free -g | awk '/Mem:/ {print $2}')
MAXW=$(( MEMG / 3 )); [ "$MAXW" -ge 1 ] && [ "$WK" -gt "$MAXW" ] && WK=$MAXW
echo "=== [c27] start pid=$$ cpus=$NC mem=${MEMG}G workers=$WK"

for f in "$W/backend/dgop_acoustic.py" "$W/backend/data/dgop_calibration_ours.json" "$W/backend/models/dgop_ours/aligner/model.int8.safetensors" \
         "$W/backend/models/dgop_ours/scorer/model.int8.safetensors" "$W/scripts/speak_asr_pod_run.py" "$W/scripts/scoring_s18_head.py" \
         "$W/tools/s13_newspk.py" "$W/tools/scores_1006.py" "$W/tools/build_scores_csv.py" "$W/tools/c27_pod.py" \
         "$W/backend_new/dgop_acoustic.py" "$W/bridge/bridge.json"; do
  [ -e "$f" ] || fail "없음: $f"
done
for bk in backend backend_new; do for m in aligner scorer; do [ ! -e "$W/$bk/models/dgop_ours/$m/model.safetensors" ] || fail "fp32 가중치가 있음($bk $m)"; done; done
echo "S13_INPUT_OK flac608=$(ls $W/n608/s608/*.flac 2>/dev/null | wc -l) bridge=$(ls $W/bridge/*.wav 2>/dev/null | wc -l)"

# ── venv(run_scores.sh와 같은 판)
if [ ! -f "$W/vseg/.ok" ]; then
  say "vseg 설치"
  python3 -m venv "$W/vseg" || fail "vseg venv"
  "$W/vseg/bin/pip" install -q --upgrade pip
  "$W/vseg/bin/pip" install -q --no-deps "faster-whisper==0.10.1" || fail "vseg faster-whisper"
  "$W/vseg/bin/pip" install -q "ctranslate2>=3.22,<4" "huggingface_hub>=0.13" "tokenizers>=0.13,<0.16" "onnxruntime>=1.14,<2" \
    "nvidia-cublas-cu11" "nvidia-cudnn-cu11==8.9.6.50" soundfile "numpy<2" "av>=11,<13" || fail "vseg 의존"
  touch "$W/vseg/.ok"
fi
SEGLIB=$("$W/vseg/bin/python" -c "import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ':' + os.path.dirname(nvidia.cudnn.lib.__file__))")
export SEG_LD="$SEGLIB:${LD_LIBRARY_PATH:-}"
LD_LIBRARY_PATH=$SEG_LD "$W/vseg/bin/python" -c "import ctranslate2, faster_whisper; print('ENVSEG ct2', ctranslate2.__version__, 'fw', faster_whisper.__version__, 'cuda', ctranslate2.get_cuda_device_count())" || fail "vseg 확인"
if [ ! -f "$W/vapp/.ok" ]; then
  say "vapp 설치"
  python3 -m venv "$W/vapp" || fail "vapp venv"
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail "torch"
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy || fail "의존"
  if ! "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt"; then
    (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq pkg-config libavformat-dev libavcodec-dev \
      libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev) || fail "apt av"
    "$W/vapp/bin/pip" install -q -r "$W/backend/requirements.txt" || fail "backend requirements"
  fi
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, faster_whisper, ctranslate2, numpy, librosa, scipy; print('ENVAPP torch', torch.__version__, 'tf', transformers.__version__, 'fw', faster_whisper.__version__, 'numpy', numpy.__version__, 'librosa', librosa.__version__, 'scipy', scipy.__version__, 'cuda', torch.cuda.is_available())" || fail "vapp 확인"
(cd "$W/backend" && $PY -c "import dgop_acoustic as DA, quant_int8; assert DA.HAS_ACOUSTIC") || fail "acoustic import"
# scoring_s18_head.features가 찾는 경로(맥 lab 배치)를 파드에 맞춘다
mkdir -p /root/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8/aligner /root/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8/scorer /root/Downloads/liplab-lab/tools
for m in aligner scorer; do ln -sfn "$W/backend/models/dgop_ours/$m/vocab.json" "/root/Downloads/liplab-lab/models/dgop_ours_2026-09-25_int8/$m/vocab.json"; done
ln -sfn "$W/tools/build_scores_csv.py" /root/Downloads/liplab-lab/tools/build_scores_csv.py
mkdir -p /root/Downloads/liplab-integrate && ln -sfn "$W/backend" /root/Downloads/liplab-integrate/backend   # build_scores_csv가 dgop을 여기서 찾는다
(cd "$W/tools" && $PY c27_pod.py selftest) | tee "$L/selftest.txt"
grep -q C27_SELFTEST_OK "$L/selftest.txt" || fail selftest
(cd "$W/backend_new" && $PY -c "import dgop_acoustic as DA; assert DA.HAS_ACOUSTIC and hasattr(DA, 'trim_trailing_silence')") || fail "backend_new import"
echo "S13_SETUP_OK"

# ── prep·seg(608 새 세션)
[ -s "$W/n608/s608/meta.json" ] || (cd "$W/tools" && $PY s13_newspk.py prep) || fail prep
if [ ! -s "$W/n608/out/cuts608.json" ]; then
  say "seg n608"
  (cd "$W/scripts" && LD_LIBRARY_PATH=$SEG_LD "$W/vseg/bin/python" -c "
import os
import speak_asr_pod_run as m
m.W = '/workspace/n608'; m.OUT = '/workspace/n608/out'
os.makedirs(m.OUT, exist_ok=True); os.makedirs('/workspace/n608/cuts', exist_ok=True)
m.cut_608()
print('SEG DONE')") || fail "seg"
fi
echo "SEG_OK $(python3 -c "import json; c=json.load(open('$W/n608/out/cuts608.json')); print(len(c), sum(1 for x in c if x['cut']), len({x['file'] for x in c if x['cut']}))")"

# ── c27 jobs → b675975 dgop(S18 특성) → 지금 앱 trim
(cd "$W/tools" && $PY c27_pod.py jobs) || fail jobs
if [ ! -f "$O/.dgop_ok" ]; then
  (cd "$W/tools" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY s13_newspk.py dgop "$WK") || fail dgop
  touch "$O/.dgop_ok"
fi
echo "DGOP_COUNTS new=$(wc -l < $O/dgop_full.jsonl) err=$(grep -c '"error"' $O/dgop_full.jsonl) bridge=$(wc -l < $W/outb/dgop_full.jsonl) err=$(grep -c '"error"' $W/outb/dgop_full.jsonl)"
(cd "$W/scripts" && $PY scoring_s18_head.py features "$O" "$O/s18_features_new.csv") || fail "features new"
(cd "$W/scripts" && $PY scoring_s18_head.py features "$W/outb" "$O/s18_features_bridge.csv") || fail "features bridge"
echo "FEAT_OK"
rm -rf "$O/lp" "$W/outb/lp"
if [ ! -f "$O/.trim_ok" ]; then
  (cd "$W/tools" && OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 $PY c27_pod.py trim "$WK") || fail trim
  touch "$O/.trim_ok"
fi
echo "TRIM_COUNTS rows=$(wc -l < $O/trim.jsonl) err=$(grep -c '"error"' $O/trim.jsonl) bridge=$(wc -l < $W/outb/trim_bridge.jsonl)"
cd "$W" && tar -czf "$W/c27_result.tgz" out/jobs.json out/dgop_full.jsonl out/trim.jsonl out/s18_features_new.csv out/s18_features_bridge.csv \
  outb/dgop_full.jsonl outb/trim_bridge.jsonl n608/out/cuts608.json dax/logs/c27.log dax/logs/selftest.txt || fail tar
echo "C27_OK"
