#!/bin/bash
# 파드 쪽 폼 C·D 등가 측정(forms_session.sh가 올리고 띄운다). 다시 불러도 이어 한다. 표식 FCD_*_OK / FCD_FAIL.
set -uo pipefail
cd /workspace/fcd
mkdir -p logs out work
exec >> logs/run.log 2>&1
echo "=== $(date '+%F %T') 시작 pid=$$"
. work/run.env
export HF_HOME=/workspace/hf PIP_DISABLE_PIP_VERSION_CHECK=1 TOKENIZERS_PARALLELISM=false
export LIPLAB_BACKEND=/workspace/fcd/backend PYTHONDONTWRITEBYTECODE=1
V=scripts/listen_virtual_listener.py
X=scripts/listen_forms_equiv.py
fail() { echo "FCD_FAIL $*"; exit 1; }
if [ ! -f .setup_ok ]; then
  (command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg >/dev/null 2>&1)) || fail apt
  pip install -q "transformers==4.46.3" "numpy<2" "scipy<1.15" soundfile || fail pip
  python -c "import torch, transformers, scipy; print('torch', torch.__version__, 'tf', transformers.__version__, 'scipy', scipy.__version__, torch.cuda.get_device_name(0))" || fail import
  touch .setup_ok
fi
echo "FCD_SETUP_OK"
python $V selftest || fail selftest
[ -f work/cache.npz ] || python $X prep --sound sound --work work $( [ -f work/extra.json ] && echo --extra work/extra.json ) || fail prep
echo "FCD_PREP_OK"
NP=$(python -c "import os; q=open('/sys/fs/cgroup/cpu.max').read().split() if os.path.exists('/sys/fs/cgroup/cpu.max') else ['max']; print(max(2, min(os.cpu_count(), int(int(q[0])/int(q[1])) if q[0]!='max' else os.cpu_count()) - 1))")
echo "procs=$NP SIDS=$SIDS REPS=$REPS ROUND=$ROUND"
python $X run --work work --sids "$SIDS" --reps "$REPS" --quiet --procs "$NP" --batch "${BATCH:-64}" || fail run
python $X score --work work || fail score
if [ -f work/spec.json ]; then
  python $X judge --work work --spec work/spec.json --out out/judge_round${ROUND}.json || fail judge
fi
echo "FCD_ALL_OK"
