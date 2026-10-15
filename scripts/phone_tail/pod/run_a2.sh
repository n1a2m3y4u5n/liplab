#!/bin/bash
# A2 재확인 파드 쪽(docs/phone-tail-2026-10.md 8절). session_a2.sh가 /workspace/pta2에 풀고 띄운다.
# 표식(/workspace/dax/logs/a2.log): A2_SETUP_OK A2_LP_OK A2_BRIDGE_OK A2_SCORE_OK A2_OK / A2_FAIL
set -u
W=/workspace
R=$W/pta2
L=$W/dax/logs
O=$R/out
mkdir -p "$L" "$O"
exec >> "$L/a2.log" 2>&1
say() { echo "$(date '+%F %T') $*"; }
fail() { echo "A2_FAIL $*"; exit 1; }
export HF_HOME=$W/hf PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 LIPLAB_CONTENT_WARMUP=0
if [ ! -f "$W/vapp/.ok" ]; then
  python3 -m venv "$W/vapp" || fail venv
  "$W/vapp/bin/pip" install -q --upgrade pip
  "$W/vapp/bin/pip" install -q "torch==2.8.0" --index-url https://download.pytorch.org/whl/cu128 || fail torch
  "$W/vapp/bin/pip" install -q "transformers==5.17.0" safetensors soundfile "librosa==0.11.0" "numpy==2.2.6" scipy "faster-whisper>=1.1" || fail deps
  touch "$W/vapp/.ok"
fi
PY=$W/vapp/bin/python
$PY -c "import torch, transformers, numpy; print('ENV', torch.__version__, transformers.__version__, numpy.__version__, torch.cuda.is_available())" || fail env
echo "A2_SETUP_OK"
export DGOP_DEVICE=cuda BACKBONE_QUANT=int8 HF_HUB_OFFLINE=1
if [ ! -f "$O/.done_lp" ]; then
  for i in 0 1 2 3; do $PY $R/scripts/phone_tail/pod/measure_lp.py $R $O --shard $i/4 > $L/lp.$i.log 2>&1 & done
  wait
  [ "$(cat $L/lp.*.log | grep -c '^LP_OK')" = 4 ] || fail lp
  touch "$O/.done_lp"; echo "A2_LP_OK t=$(ls $O/lp_t | wc -l)"
fi
# 다리: 처음·마지막 클립에서 저장 로그확률의 K가 앱 assess_text(t, GPU)의 naive와 같은가
$PY - "$R" "$O" <<'PYEOF' || fail bridge
import json, os, sys
R, O = sys.argv[1:3]
sys.path.insert(0, f"{R}/backend"); sys.path.insert(0, f"{R}/scripts/phone_tail")
os.environ["PT_VOCAB"] = f"{R}/backend/models/dgop_ours/aligner/vocab.json"
import dgop_acoustic as DA, offline as OF, chipval as CV
js = [json.loads(l) for l in open(f"{R}/data/jobs.jsonl", encoding="utf-8")]
AL, SC = f"{R}/backend/models/dgop_ours/aligner", f"{R}/backend/models/dgop_ours/scorer"
for j in (js[0], js[-1]):
    lp, slp = OF.load_lp(f"{O}/lp_t/538_{j['clip']}.npz")
    k = OF.score_all(lp, CV.softmax(slp), j["tokens"], ["K"])["K"]
    r = DA.assess_text(open(f"{R}/data/wav/{j['clip']}.wav", "rb").read(), j["target"], aligner_id=AL, scorer_id=SC)
    app = [p.get("naive") if p.get("aligned") and p.get("scorable") else None for p in r["phones"]]
    d = max(abs(a - b) for a, b in zip(k, app) if a is not None and b is not None)
    print("BRIDGE", j["clip"], d)
    assert d <= 0.002, d
PYEOF
echo "A2_BRIDGE_OK"
if [ ! -f "$O/.done_score" ]; then
  NS=16
  $PY - "$R" $NS <<'PYEOF' || fail split
import sys
R, n = sys.argv[1], int(sys.argv[2])
ls = open(f"{R}/data/jobs.jsonl", encoding="utf-8").readlines()
for i in range(n):
    open(f"{R}/data/jobs.{i}.jsonl", "w", encoding="utf-8").writelines(ls[i::n])
PYEOF
  export PT_VOCAB=$R/backend/models/dgop_ours/aligner/vocab.json OMP_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=""
  for i in $(seq 0 $((NS - 1))); do $PY $R/scripts/phone_tail/offline.py s2 $O/lp_t $R/data/jobs.$i.jsonl A2 $O/sc.$i --cands K,E1 > $L/sc.$i.log 2>&1 & done
  wait
  [ "$(cat $L/sc.*.log | grep -c '^S2_OFFLINE_OK')" = "$NS" ] || fail score
  for c in K E1; do mkdir -p $O/a2t/$c; cat $O/sc.*/$c/run.0.jsonl > $O/a2t/$c/run.0.jsonl; done
  touch "$O/.done_score"; echo "A2_SCORE_OK $(wc -l < $O/a2t/K/run.0.jsonl)"
fi
tar -czf $W/a2_result.tgz -C $O a2t -C $W dax/logs || fail tar
echo "A2_OK"
