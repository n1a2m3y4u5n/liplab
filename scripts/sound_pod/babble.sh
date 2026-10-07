#!/bin/bash
# 듣기 트랙 소음 다섯 가지(talker1_f·talker1_m·talker2·babble·ssn) 만들기 + 인코딩(48kHz 모노). 끝 표식 BABBLE_DONE(logs/babble.log)
cd /workspace/tts
export HF_HOME=/workspace/tts/hf
mkdir -p out/noise
OMP_NUM_THREADS=4 venv/st/bin/python noises.py all.json out/noise out/final/synth/m1 out/final/synth/f1 out/final/synth/m2 out/final/synth/f2 out/final/synth/m3 \
  || { echo BABBLE_FAIL; exit 1; }
for n in talker1_f talker1_m talker2 babble ssn; do
  [ -f out/noise/$n.wav ] || continue
  ffmpeg -nostdin -y -loglevel error -i out/noise/$n.wav -ac 1 -ar 48000 -c:a libopus -b:a 32k out/noise/$n.ogg
  ffmpeg -nostdin -y -loglevel error -i out/noise/$n.wav -ac 1 -ar 48000 -c:a aac -b:a 64k -movflags +faststart out/noise/$n.m4a
  for f in out/noise/$n.ogg out/noise/$n.m4a; do
    ffmpeg -nostdin -hide_banner -i $f -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume" | sed "s|^|$f |"
  done
done
ls -la out/noise
echo BABBLE_DONE
