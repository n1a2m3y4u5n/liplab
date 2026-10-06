"""P3 개방형 답 엄격 음소 정답률 다시 계산(docs/pilot/battery.md 6절).

가명 내보내기(GET /api/pilot/export, 판 5 이상) JSON의 battery[].open[]에서 auto_phoneme_acc가 비어 있는 행을
backend/phoneme_accuracy.py의 strict_phoneme_accuracy(target, answer_text)로 채운다. 검사 때 그 모듈이 아직 없었거나
채점 규칙이 바뀌어 다시 매길 때 쓴다. 원래 값이 있는 행은 --all을 주지 않으면 그대로 둔다.

    python3 scripts/pilot_battery_rescore.py export.json -o export_rescored.json [--all]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import pilot_battery as pb  # noqa: E402


def rescore(export: dict, redo_all: bool = False) -> dict:
    """export를 고쳐 쓰고 {filled, skipped, unavailable} 건수를 돌려준다."""
    n = {"filled": 0, "skipped": 0, "unavailable": 0}
    for p in export.get("participants") or []:
        for s in p.get("battery") or []:
            for r in s.get("open") or []:
                if r.get("auto_phoneme_acc") is not None and not redo_all:
                    n["skipped"] += 1
                    continue
                res = pb.strict_score(r.get("target") or "", r.get("answer_text") or "")
                if res is None:
                    n["unavailable"] += 1
                    continue
                f = pb.strict_fields(res)
                for k in ("auto_phoneme_acc", "auto_word_acc", "n_matched_phonemes", "n_target_phonemes"):
                    r[k] = f[k]
                r["scorer_version"] = f["strict_version"] or "strict"
                n["filled"] += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--all", action="store_true", help="값이 있는 행도 다시 매긴다")
    a = ap.parse_args()
    with open(a.export, encoding="utf-8") as f:
        ex = json.load(f)
    if (ex.get("version") or 0) < 5:
        raise SystemExit("판 5 이상의 내보내기가 필요하다(battery가 없음)")
    n = rescore(ex, a.all)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ex, f, ensure_ascii=False, indent=1)
    print(f"채움 {n['filled']}, 그대로 {n['skipped']}, 채점 함수 없음 {n['unavailable']}")
    if n["unavailable"]:
        print("backend/phoneme_accuracy.py(strict_phoneme_accuracy)가 없거나 오류가 나 채우지 못한 행이 있다", file=sys.stderr)


if __name__ == "__main__":
    main()
