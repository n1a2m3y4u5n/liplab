#!/bin/bash
# 파드 쪽: 독립 참조 정렬(Montreal Forced Aligner, korean_mfa). run.sh가 mfaprep 뒤에 띄운다(CPU만 쓴다).
# conda-forge에서 micromamba로 MFA를 깔고, 사전에 없는 낱말은 korean_mfa G2P로 발음을 만들어 사전에 붙인 뒤 정렬한다.
# 표식: MFA_SETUP_OK MFA_G2P_OK|MFA_G2P_WARN MFA_ALIGN_OK / MFA_FAIL
set -u
W=/workspace
D=$W/ta/mfa
export MAMBA_ROOT_PREFIX=$W/mm/root MFA_ROOT_DIR=$W/mfa_root
MM=$W/mm/bin/micromamba
fail() { echo "MFA_FAIL $*"; exit 1; }
echo "=== [mfa] $(date '+%F %T')"
if [ ! -x "$MM" ]; then
  mkdir -p $W/mm
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C $W/mm bin/micromamba || fail micromamba
fi
if [ ! -f $W/mfaenv/.ok ]; then
  $MM create -y -q -p $W/mfaenv -c conda-forge python=3.11 montreal-forced-aligner || fail "mfa 설치"
  $MM run -p $W/mfaenv pip install -q python-mecab-ko || echo "mecab-ko 설치 실패(계속)"
  touch $W/mfaenv/.ok
fi
MFA="$MM run -p $W/mfaenv mfa"
$MFA version || fail version
for k in acoustic dictionary g2p; do $MFA model download $k korean_mfa > /dev/null 2>&1 || $MFA model download $k korean_mfa || fail "model $k"; done
DICT=$(ls $MFA_ROOT_DIR/pretrained_models/dictionary/korean_mfa.dict 2>/dev/null | head -n 1)
[ -s "$DICT" ] || fail "사전 파일 없음"
echo "MFA_SETUP_OK $DICT"
cd $D || fail "mfa 폴더 없음"
# 사전에 없는 낱말(공백 단위)만 G2P
cat corpus/*/*.lab | tr ' ' '\n' | sed '/^$/d' | sort -u > words.txt
cut -f1 "$DICT" | awk '{print $1}' | sort -u > dict_words.txt
comm -23 words.txt dict_words.txt > oov.txt
echo "낱말 $(wc -l < words.txt), 사전에 없음 $(wc -l < oov.txt)"
: > oov.dict
if [ -s oov.txt ]; then
  if $MFA g2p oov.txt korean_mfa oov.dict -j 8 > g2p.log 2>&1 && [ -s oov.dict ]; then echo "MFA_G2P_OK $(wc -l < oov.dict)"
  else tail -n 5 g2p.log; echo "MFA_G2P_WARN"; fi
fi
cat "$DICT" oov.dict > combined.dict
$MFA align --clean -j 8 --beam 100 --retry_beam 400 corpus combined.dict korean_mfa aligned > align.log 2>&1 || { tail -n 20 align.log; fail align; }
echo "TextGrid $(find aligned -name '*.TextGrid' | wc -l)"
echo "MFA_ALIGN_OK"
