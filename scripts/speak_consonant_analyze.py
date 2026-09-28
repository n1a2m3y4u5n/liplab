"""말하기 자음 확장(docs/curriculum-roadmap.md 1-5) 선행 검증 분석. 파드 결과 out/cons.json(speak_consonant_pod_eval.py)을 읽어
목표 초성마다 바뀐 자리 음소 D-GOP의 AUC(제 문장 쪽이 높을 확률, 비짝)와 짝 비교 승률(같은 클립에서 제 문장 쪽이 높은 비율)을 낸다.
채택 기준(결과 전에 적음): 목표 초성의 AUC(대립 자음을 합쳐서) >= 0.80.
    python speak_consonant_analyze.py out/cons.json
"""
import collections
import json
import sys

rows = [r for r in json.load(open(sys.argv[1] if len(sys.argv) > 1 else "out/cons.json")) if "error" not in r]
NEW = ["ㅅ", "ㅆ", "ㅈ", "ㅊ", "ㅉ", "ㅎ"]


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


by = collections.defaultdict(list)
for r in rows:
    by[r["target"]].append(r)
print(f"rows {len(rows)} errors {sum(1 for r in json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'out/cons.json')) if 'error' in r)}")
for tgt in NEW + sorted(k for k in by if k not in NEW):
    rs = by.get(tgt, [])
    if not rs:
        print(f"{tgt}: 표본 없음")
        continue
    a = auc([r["same"] for r in rs], [r["alt"] for r in rs])
    win = sum(r["same"] > r["alt"] for r in rs) / len(rs)
    parts = []
    for c in sorted({r["contrast"] for r in rs}):
        cs = [r for r in rs if r["contrast"] == c]
        parts.append(f"→{c} n{len(cs)} AUC {auc([r['same'] for r in cs], [r['alt'] for r in cs]):.3f}")
    tag = "새" if tgt in NEW else "기존"
    print(f"[{tag}] {tgt}: n{len(rs)} AUC {a:.3f} 짝승률 {win:.3f} {'통과' if a >= 0.80 else '미달'} | " + " ".join(parts))
