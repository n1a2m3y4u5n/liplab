#!/bin/bash
# V7b 538 전문가 클립 MediaPipe 추출(파드 쪽, 2026-10-09). run_v18.sh(scripts/v18_pod)의 setup·extract_list를 줄인 판.
#   v7b_session.sh가 /workspace/v7b에 푼 것: tools/{extract_blendshapes.py, face_landmarker.task}, clips/*.mp4(고른 클립)
#   표식(/workspace/dax/logs/v7b.log): V7B_SETUP_OK  V7B_EXTRACT_OK bs=N  V7B_OK / V7B_FAIL
set -u
W=/workspace/v7b
L=/workspace/dax/logs
mkdir -p "$L" "$W/out/bs"
exec >> "$L/v7b.log" 2>&1
echo $$ > "$L/v7b.pid"
fail() { echo "V7B_FAIL $*"; exit 1; }
export PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
NC=$(nproc --all)
Q=$(awk '{ if ($1 != "max") print int($1 / $2) }' /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [ -n "$Q" ] && [ "$Q" -gt 0 ] && [ "$Q" -lt "$NC" ]; then NC=$Q; fi
VMP=/workspace/vmp/bin/python
[ "$NC" -gt "${V7B_MAXP:-24}" ] && NC=${V7B_MAXP:-24}   # 96개를 띄우면 mediapipe GpuResources::Create가 60개에서 죽었다(10/10)
echo "=== [v7b] start pid=$$ cpus=$NC $(date '+%F %T')"
if [ ! -f "$W/.apt_ok" ]; then
  (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg libegl1 libgl1) || fail "apt"
  touch "$W/.apt_ok"
fi
if [ ! -f /workspace/vmp/.ok ]; then
  python3 -m venv /workspace/vmp || fail "venv"
  /workspace/vmp/bin/pip install -q --upgrade pip
  /workspace/vmp/bin/pip install -q "mediapipe==0.10.14" "opencv-python-headless<4.11" "numpy<2" || fail "pip"
  touch /workspace/vmp/.ok
fi
$VMP -c "import mediapipe, cv2; print('ENVMP', mediapipe.__version__, cv2.__version__)" || fail "vmp"
(cd "$W/tools" && $VMP extract_blendshapes.py --selftest) | grep -q SELFTEST_OK || fail selftest
echo "V7B_SETUP_OK cpus=$NC"
LIST=$W/list.tsv
: > "$LIST"
for f in "$W"/clips/*.mp4; do b=$(basename "$f" .mp4); [ -s "$W/out/bs/$b.json" ] || printf '%s\t%s\n' "$f" "$W/out/bs/$b.json" >> "$LIST"; done
rm -f "$LIST".part.*
split -n "l/$NC" -d "$LIST" "$LIST.part."
( while sleep 60; do echo "PROGRESS bs=$(ls "$W/out/bs" | grep -c '\.json$')"; done ) &
TICK=$!
for k in "$LIST".part.*; do
  (cd "$W/tools" && $VMP extract_blendshapes.py --list "$k" --lips --no-audio > "$k.log" 2>&1) &
done
wait $(jobs -p | grep -v "^$TICK$")
kill $TICK 2>/dev/null
echo "EXTRACT $(cat "$LIST".part.*.log | grep -h LIST_DONE | tr '\n' ' ')"
echo "V7B_EXTRACT_OK bs=$(ls "$W/out/bs" | grep -c '\.json$')"
cd "$W/out" && tar -czf "$W/v7b_result.tgz" bs || fail tar
echo "V7B_OK"
