#!/bin/bash
# chatterbox 표본(이어서): CUDA 단언이면 그 문항을 실패로 적고 다시 띄운다. 그 뒤 GPU 전사와 CPU D-GOP·UTMOS. 끝 표식 CBRETRY_DONE
cd /workspace/tts
export HF_HOME=/workspace/tts/hf
SP=venv/score/lib/python3.11/site-packages
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
for k in $(seq 1 140); do
  venv/cb/bin/python synth.py chatterbox sample.json out/cmp/cb --threads 2 > logs/synth_cb_$k.log 2>&1
  rc=$?
  [ "$rc" = 3 ] || break
done
echo "$(date +%T) CB synth rc=$rc ok=$(ls out/cmp/cb/*.wav | wc -l) failed=$(cat out/cmp/cb/failed.txt 2>/dev/null | wc -l)"
# compare2가 CUDA 라이브러리를 깐 뒤에 돈다
for k in $(seq 1 120); do grep -q CUDA_LIBS_OK logs/compare2.log 2>/dev/null && break; sleep 10; done
venv/score/bin/python asr_gpu.py sample.json asr out/cmp/cb > logs/asr_cb.log 2>&1 && echo "$(date +%T) ASR cb ok" || echo "$(date +%T) ASR cb FAIL"
for i in 0 1; do
  venv/score/bin/python evaluate.py sample.json out/cmp/cb eval/cb.$i.jsonl --asr "" --shard $i/2 --threads 2 >> logs/eval_cb.log 2>&1 &
done
wait
venv/score/bin/python utmos.py out/cmp/cb > logs/utmos_cb.log 2>&1
echo "$(date +%T) CBRETRY_DONE"
