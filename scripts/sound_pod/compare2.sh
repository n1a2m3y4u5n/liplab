#!/bin/bash
# 비교 평가 2판: 전사는 GPU(asr_gpu.py), D-GOP·정렬은 CPU 프로세스 4개 × 2스레드(evaluate.py --asr ''), 자연스러움 UTMOS(CPU).
# 끝 표식 COMPARE2_DONE(logs/compare2.log)
cd /workspace/tts
export HF_HOME=/workspace/tts/hf
SP=venv/score/lib/python3.11/site-packages
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
uv pip install -q -p venv/score/bin/python nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" && echo "$(date +%T) CUDA_LIBS_OK"
mkdir -p eval asr
DIRS="out/cmp/melo out/cmp/st_F1 out/cmp/st_F2 out/cmp/st_F3 out/cmp/st_F4 out/cmp/st_F5 out/cmp/st_M1 out/cmp/st_M2 out/cmp/st_M3 out/cmp/st_M4 out/cmp/st_M5"
venv/score/bin/python asr_gpu.py sample.json asr $DIRS > logs/asr_gpu.log 2>&1 && echo "$(date +%T) ASR ok" || echo "$(date +%T) ASR FAIL"
# D-GOP: (디렉토리, 조각) 쌍을 4개씩
jobs_list=""
for d in $DIRS; do n=$(basename $d); for i in 0 1; do jobs_list="$jobs_list $n:$i"; done; done
for j in $jobs_list; do
  n=${j%:*}; i=${j#*:}
  venv/score/bin/python evaluate.py sample.json out/cmp/$n eval/$n.$i.jsonl --asr "" --shard $i/2 --threads 2 >> logs/eval_$n.log 2>&1 &
  while [ "$(jobs -rp | wc -l)" -ge 4 ]; do sleep 2; done
done
wait
echo "$(date +%T) DGOP ok"
venv/score/bin/python utmos.py $DIRS > logs/utmos.log 2>&1 && echo "$(date +%T) UTMOS ok" || echo "$(date +%T) UTMOS FAIL"
echo "$(date +%T) COMPARE2_DONE"
