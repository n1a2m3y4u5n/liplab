#!/bin/bash
# 비교 단계: 표본 130개를 세 엔진으로 합성(GPU) → 앱 채점 경로로 평가(CPU) → CPU 2스레드 속도·메모리.
# 끝 표식 COMPARE_DONE(logs/compare.log). 3) 평가 부분은 CPU 전사(large-v3-turbo)가 너무 느려 중간에 멈추고 compare2.sh(GPU 전사)로 대신했다.
set -u
cd /workspace/tts
export HF_HOME=/workspace/tts/hf
NP=${NP:-8}
echo "$(date +%T) start NP=$NP"
V=venv
# 1) 합성(GPU): 엔진마다 한 번, Supertonic은 목소리 10개
for v in F1 F2 F3 F4 F5 M1 M2 M3 M4 M5; do
  $V/st/bin/python synth.py supertonic sample.json out/cmp/st_$v --voice $v > logs/synth_st_$v.log 2>&1 && echo "$(date +%T) SYNTH st_$v ok" || echo "$(date +%T) SYNTH st_$v FAIL"
done
$V/melo/bin/python synth.py melo sample.json out/cmp/melo > logs/synth_melo.log 2>&1 && echo "$(date +%T) SYNTH melo ok" || echo "$(date +%T) SYNTH melo FAIL"
# chatterbox 가상환경은 설치가 오래 걸려 최대 40분 기다린다
for i in $(seq 1 240); do grep -q "SETUP_cb_" setup.out && break; sleep 10; done
$V/cb/bin/python synth.py chatterbox sample.json out/cmp/chatterbox > logs/synth_cb.log 2>&1 && echo "$(date +%T) SYNTH cb ok" || echo "$(date +%T) SYNTH cb FAIL"
# 2) CPU 2스레드 속도(문장 20개)·메모리(최대 RSS). 서버(공유 CPU 2코어)에서 동적 합성이 되는지 가늠한다
head_json() { python3 -c "import json,sys;d=json.load(open('sample.json'));json.dump([e for e in d if 'closure' in e['sources'] or 'sentence' in e['sources']][:20],open('cpu20.json','w'),ensure_ascii=False)"; }
head_json
for m in supertonic melo chatterbox; do
  case $m in supertonic) py=$V/st/bin/python; extra="--voice F1";; melo) py=$V/melo/bin/python; extra="";; chatterbox) py=$V/cb/bin/python; extra="";; esac
  CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 taskset -c 0,1 $py synth.py $m cpu20.json out/cpu/$m --device cpu --threads 2 $extra > logs/cpu_$m.log 2>&1 \
    && echo "$(date +%T) CPU $m ok" || echo "$(date +%T) CPU $m FAIL"
done
echo "$(date +%T) SYNTH_ALL_DONE"
# 3) 평가(CPU 병렬). 주 비교 셋은 전사 2개 + D-GOP, 나머지 목소리는 base 전사 + D-GOP
mkdir -p eval
T=4; J=$(( NP / T )); [ "$J" -lt 1 ] && J=1
jobs_=()
run_eval() {  # dir asr shards
  local d=$1 asr=$2 n=$3 i
  for i in $(seq 0 $((n-1))); do
    $V/score/bin/python evaluate.py sample.json out/cmp/$d eval/$d.$i.jsonl --asr "$asr" --shard $i/$n --threads $T >> logs/eval_$d.log 2>&1 &
    while [ "$(jobs -rp | wc -l)" -ge "$J" ]; do sleep 2; done
  done
}
for d in melo chatterbox st_F1; do run_eval $d base,large-v3-turbo 3; done
for v in F2 F3 F4 F5 M1 M2 M3 M4 M5; do run_eval st_$v base 1; done
wait
echo "$(date +%T) COMPARE_DONE"
