#!/usr/bin/env python3
"""AI Hub 608 TS02 범주 27(전음성) 두 번째 묶음: 10/9 첫 묶음 30명 뒤의 적격 화자를 흘려받는다(2026-10-15, 문장 점수 규칙 확인용).

선택 규칙(받기 전에 정함, liplab-integrate docs/scoring-rules-2026-10.md 2절과 같다. 라벨만 본다):
  - 적격 세션·갈래 규칙은 첫 묶음(fetch608_c27.py)과 같다: 과제 02, 문장부호 10개 이상, playTime 20분 이하,
    02-01·02-02 갈래에서 각각 playTime이 가장 짧은 세션 하나(같으면 이름 순), 화자당 최대 2세션.
  - 뺄 화자: (1) 첫 묶음과 같이 hi608 기존 폴더에 범주 27 파일이 있는 화자 24명, (2) 10/9 첫 묶음 30명(c27/select.json의 chosen),
    (3) (1)·(2)와 이니셜·성별이 같고 나이 차 ≤ 2인 화자, (4) 이번 묶음 안에서 앞선 화자와 이니셜·성별이 같고 나이 차 ≤ 2인 화자(뒤의 것을 뺌).
  - 남은 적격 화자를 흘려받는 순서(이름 순)로 전부 받는다(상한 61명). 사람이 화자를 고르지 않는다.
저장: data/hi608/c27/b2/wav48(받는 중, 변환 뒤 지움) → data/hi608/c27/b2/flac16. 첫 묶음 폴더와 hi608 기존 폴더는 건드리지 않는다.
디스크·키·멈춤 처리는 fetch608_c27.py 그대로(여유 8GB 아래면 멈춤, 키는 aihub608.Fetcher가 0600 임시 파일로만 다룸).

  python3 tools/fetch608_c27b.py --dry-run
  nohup caffeinate -i python3 tools/fetch608_c27b.py > data/hi608/c27/b2/fetch.log 2>&1 &
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch608_c27 as F  # noqa: E402

FIRST = os.path.join(F.OUT, "select.json")
F.OUT = os.path.join(F.HI, "c27", "b2")
F.WAV = os.path.join(F.OUT, "wav48")
F.FLAC = os.path.join(F.OUT, "flac16")
F.N_SPK = 61


def _near(a, b):
    try:
        ai, asx, aa = a.split("-")
        bi, bsx, ba = b.split("-")
        return ai == bi and asx == bsx and abs(int(aa) - int(ba)) <= 2
    except ValueError:
        return a == b


def select_b2():
    used = F.used_keys()
    first = json.load(open(FIRST, encoding="utf-8"))
    first_keys = {c["key"] for c in first["chosen"]}
    excl = used | first_keys
    rows = F.labels27()
    by = {}
    for r in rows:
        if r["task"] != "02" or r["sub"] not in ("01", "02") or r["nsent"] < F.MIN_SENT or r["min"] > F.MAX_MIN:
            continue
        if r["key"] in excl or any(_near(r["key"], u) for u in excl):
            continue
        by.setdefault(r["key"], []).append(r)
    order = []
    for k in sorted(by, key=lambda k: min(x["stem"] for x in by[k])):
        if any(_near(k, o) for o in order):
            continue
        order.append(k)
    chosen = []
    for k in order[:F.N_SPK]:
        for sub in ("01", "02"):
            c = sorted((x for x in by[k] if x["sub"] == sub), key=lambda x: (x["min"], x["stem"]))
            if c:
                chosen.append(dict(c[0], group=sub))
    return excl, order, chosen


F.select = select_b2

if __name__ == "__main__":
    F.main()
