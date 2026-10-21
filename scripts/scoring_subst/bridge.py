"""다리 점검(docs/scoring-subst-2026-10.md 7.3절): 이번 특성 파일의 앱 점수가 10/15·10/17 기록(scripts/scoring_rules/feat_pod.py 출력)과 같은가.

  python bridge.py NEW.jsonl OLD.jsonl [OLD2.jsonl ...]     (클립, 목표 글) 짝이 같은 행의 |점수 차| 최댓값, 0.1 넘는 행 수
"""
import json
import sys


def rows(path, key="score"):
    out = {}
    for line in open(path, encoding="utf-8"):
        j = json.loads(line)
        if j.get("rec") == "t" and j.get(key) is not None:
            out[(j["clip"], j["target"])] = j[key]
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    new = rows(sys.argv[1])
    old = {}
    for p in sys.argv[2:]:
        old.update(rows(p))
    common = [k for k in new if k in old]
    diff = [abs(new[k] - old[k]) for k in common]
    bad = sum(1 for d in diff if d > 0.1 + 1e-6)   # 점수는 소수 첫째 자리라 정확히 0.1 차이가 부동소수로 0.1을 넘게 세어지지 않게(변경 기록 6)
    print("SUB_BRIDGE", json.dumps({"new": len(new), "matched": len(common), "max_abs_diff": round(max(diff), 4) if diff else None,
                                    "over_0.1": bad, "ok": bool(common) and bad == 0}, ensure_ascii=False))
