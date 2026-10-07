#!/bin/bash
# 본 합성: 목소리마다 합성(Supertonic, CPU 6스레드) → 정렬·채점(앱 int8 정렬기·채점기) → 인코딩(Opus·AAC).
# 설정은 final.env: VOICES="f1:F1:texts.json:full m1:M1:listen.json:align ..."(목록 id:엔진 목소리:글 목록:평가 방식)
#   평가 방식 full = base 전사 + D-GOP + 두 번째 정렬기 점검, align = 정렬(시각)만
# 끝 표식 FINAL_DONE(logs/final.log). 다시 돌리면 이미 있는 파일은 건너뛴다.
set -u
cd /workspace/tts
export HF_HOME=/workspace/tts/hf
source final.env
F=out/final
mkdir -p $F/synth $F/eval $F/enc logs
echo "$(date +%T) start VOICES=$VOICES"
# 합성(목소리 셋씩 동시에, 각 2스레드. 할당 코어는 약 7.6개)
for spec in $VOICES; do
  IFS=: read -r vid ev tx mode <<< "$spec"
  ( venv/st/bin/python synth.py supertonic "$tx" $F/synth/$vid --voice "$ev" --vid "$vid" --threads 2 > logs/final_synth_$vid.log 2>&1 \
    && echo "$(date +%T) SYNTH $vid $(tail -n 1 logs/final_synth_$vid.log)" || echo "$(date +%T) SYNTH $vid FAIL" ) &
  while [ "$(jobs -rp | wc -l)" -ge 3 ]; do sleep 2; done
done
wait
# 인코딩(병렬 6)
for spec in $VOICES; do
  IFS=: read -r vid ev tx mode <<< "$spec"
  mkdir -p $F/enc/$vid
  ls $F/synth/$vid/*.wav 2>/dev/null | xargs -P 6 -I{} bash -c 'w={}; b=$(basename $w .wav); d='"$F/enc/$vid"'; \
    [ -s $d/$b.ogg ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 48000 -c:a libopus -b:a 24k -vbr on $d/$b.ogg; \
    [ -s $d/$b.m4a ] || ffmpeg -nostdin -y -loglevel error -i $w -ac 1 -ar 24000 -c:a aac -b:a 24k -movflags +faststart $d/$b.m4a'
  echo "$(date +%T) ENC $vid ogg=$(ls $F/enc/$vid/*.ogg 2>/dev/null | wc -l) m4a=$(ls $F/enc/$vid/*.m4a 2>/dev/null | wc -l)"
done
# 정렬·채점(병렬: 프로세스 4개 × 2스레드)
for spec in $VOICES; do
  IFS=: read -r vid ev tx mode <<< "$spec"
  if [ "$mode" = full ]; then args="--asr base --check"; else args="--asr '' --align-only"; fi
  for i in 0 1 2 3; do
    eval venv/score/bin/python evaluate.py "$tx" $F/synth/$vid $F/eval/$vid.$i.jsonl $args --shard $i/4 --threads 2 --vid "$vid" >> logs/final_eval_$vid.log 2>&1 &
  done
  wait
  echo "$(date +%T) EVAL $vid $(cat $F/eval/$vid.*.jsonl | wc -l)"
done
# 듣기 트랙 소음 다섯 가지(babble.sh → noises.py), 비교 표본의 자연스러움 대리 지표(UTMOS), 동적 합성 경로 측정
bash babble.sh > logs/babble.log 2>&1; echo "$(date +%T) $(tail -n 1 logs/babble.log)"
uv pip install -q -p venv/score/bin/python "torchaudio==2.14.0" --index-url https://download.pytorch.org/whl/cpu \
  && venv/score/bin/python utmos.py out/cmp/* > logs/utmos.log 2>&1; echo "$(date +%T) UTMOS $(tail -n 1 logs/utmos.log)"
python3 -c "import json;d=json.load(open('sample.json'));json.dump([e for e in d if 'closure' in e['sources'] or 'sentence' in e['sources']][:20],open('dyn20.json','w'),ensure_ascii=False)"
uv pip install -q -p venv/score/bin/python supertonic && taskset -c 0,1 venv/score/bin/python dynmeasure.py dyn20.json out/dyn.json > logs/dyn.log 2>&1
echo "$(date +%T) DYN $(tail -n 1 logs/dyn.log)"
echo "$(date +%T) FINAL_DONE"
