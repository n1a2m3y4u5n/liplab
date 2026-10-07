#!/bin/bash
# 단계 하나를 떼어 띄운다: launch.sh NAME → NAME.sh를 setsid nohup으로, 로그 logs/NAME.log
cd /workspace/tts
n=$1
[ -f "$n.sh" ] || { echo "no $n.sh"; exit 2; }
(setsid nohup bash "$n.sh" > "logs/$n.log" 2>&1 < /dev/null &)
echo "LAUNCHED $n"
