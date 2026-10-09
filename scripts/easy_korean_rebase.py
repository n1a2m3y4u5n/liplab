#!/usr/bin/env python
"""
쉬운 한국어 감사 기준 재설정안의 수치(docs/easy-korean-rebase-2026-10.md). 화면 문구는 바꾸지 않고, 감사 결과를 여러 기준으로 다시 센다.

  python scripts/easy_korean_audit.py --json /tmp/ek.json     # 문자열별 결과(kiwipiepy 필요)
  python scripts/easy_korean_rebase.py /tmp/ek.json           # 기준별 통과율, 유형별 통과율, 바꿀 후보의 효과
  python scripts/easy_korean_rebase.py /tmp/ek.json --md      # 문서에 넣는 표(마크다운)

용어 결정표 초안은 scripts/data/easy_korean_termbook_draft.json이다(사용자 결정 전 초안).
기준(누적):
  R0  지금 감사(A·B만 쉬운 말, 문자열마다 어려운 말 ≤ 10%, 한 문장 30음절 이하)
  R1  R0 + 측정 오류 고침(명사형 -기, 분석기가 자른 조각)
  R2  R1 + C 등급 허용(「한국어 학습용 어휘 목록」 5,965개 전체를 쉬운 말로)
  R3  R2 + 목록 밖 일상 말·법·연구 고지 용어 허용(결정표 everyday·notice)
  R4  R3 + 앱이 가르치는 핵심 용어 허용(결정표 taught, 처음 나올 때 풀이가 조건)
  P   R4를 문자열 유형별로: 이름표(버튼·탭·제목)는 어려운 말 0개, 문장형은 ≤ 10%와 30음절
  P+swap  P에서 바꿀 후보(결정표 swap)를 모두 쉬운 대안으로 바꿨다고 칠 때
"""
import argparse
import json
import os
import re
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB_TSV = os.path.join(_HERE, "data", "nikl_learner_vocab.tsv")
TERMBOOK = os.path.join(_HERE, "data", "easy_korean_termbook_draft.json")
MAX_HARD = 0.10
_END = re.compile(r"(요|다|까|죠|니다|세요|어|아|해|지|네|자|라|래|게|군)$")
_TAIL = re.compile(r"[\s.!?…·:)\]」』'\"○→~\-0-9A-Za-z%()]+$")


def load_grade():
    g = {}
    with open(VOCAB_TSV, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or line.startswith("word\t"):
                continue
            w, _p, gr = line.rstrip("\n").split("\t")
            if w not in g or gr < g[w]:
                g[w] = gr
    return g


def is_label(it) -> bool:
    """이름표(버튼·탭·제목·짧은 표시): 문장이 하나이고, 끝이 종결 어미가 아니며, 내용어가 4개 이하."""
    if it["sentences"] > 1 or it["n_words"] > 4:
        return False
    t = _TAIL.sub("", it["text"].strip())
    return not _END.search(t)


def evaluate(items, grade, tb):
    fix, every, notice, taught = set(tb["measure_fix"]), set(tb["everyday"]), set(tb["notice"]), set(tb["taught"])
    swap = set(tb["swap"])

    def hard_under(it, level, swapped=False):
        out = []
        for w in it["hard"]:
            if level >= 1 and w in fix:
                continue
            if level >= 2 and grade.get(w) == "C":
                continue
            if level >= 3 and (w in every or w in notice):
                continue
            if level >= 4 and w in taught:
                continue
            if swapped and w in swap:
                continue
            out.append(w)
        return out

    def ok_ratio(it, hard):
        r = len(hard) / it["n_words"] if it["n_words"] else 0.0
        return it["len_ok"] and r <= MAX_HARD

    def ok_typed(it, hard):
        return (not hard) if is_label(it) else ok_ratio(it, hard)

    rows = {}
    for name, level in (("R0", 0), ("R1", 1), ("R2", 2), ("R3", 3), ("R4", 4)):
        rows[name] = [ok_ratio(it, hard_under(it, level)) for it in items]
    rows["P"] = [ok_typed(it, hard_under(it, 4)) for it in items]
    rows["P+swap"] = [ok_typed(it, hard_under(it, 4, swapped=True)) for it in items]
    return rows, hard_under, ok_typed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audit_json")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    items = json.load(open(a.audit_json, encoding="utf-8"))
    grade = load_grade()
    tb = json.load(open(TERMBOOK, encoding="utf-8"))
    rows, hard_under, ok_typed = evaluate(items, grade, tb)
    n = len(items)
    labels = [is_label(it) for it in items]
    n_lab = sum(labels)
    uniq = {}
    for i, it in enumerate(items):
        uniq.setdefault(it["text"], i)
    idx_u = list(uniq.values())

    def rate(xs, sel=None):
        sel = range(len(xs)) if sel is None else sel
        sel = list(sel)
        return sum(xs[i] for i in sel) / len(sel) if sel else 0.0

    lab_idx = [i for i in range(n) if labels[i]]
    sen_idx = [i for i in range(n) if not labels[i]]
    out = {"strings": n, "unique_texts": len(idx_u), "labels": n_lab, "sentences": n - n_lab, "rates": {}}
    for k, xs in rows.items():
        out["rates"][k] = {"all": round(rate(xs), 4), "unique": round(rate(xs, idx_u), 4),
                           "labels": round(rate(xs, lab_idx), 4), "sentences": round(rate(xs, sen_idx), 4)}
    # 비율 기준이 사실상 '어려운 말 0개'가 되는 문자열(내용어 9개 이하에서는 1개만 있어도 10%를 넘는다)
    out["zero_tolerance_share"] = round(sum(1 for it in items if 0 < it["n_words"] <= 9) / n, 4)
    # 화면(파일) 단위 어휘 덮기 비율: 문장형 문자열의 내용어를 파일마다 모아 쉬운 말 비율을 낸다(L2 읽기 연구의 95% 덮기 기준)
    def coverage(swapped):
        per = {}
        for i in sen_idx:
            it = items[i]
            if not it["n_words"]:
                continue
            h = len(hard_under(it, 4, swapped=swapped))
            a_, b_ = per.get(it["file"], (0, 0))
            per[it["file"]] = (a_ + it["n_words"] - h, b_ + it["n_words"])
        tot = sum(b for _, b in per.values())
        easy = sum(a for a, _ in per.values())
        return {"files": len(per), "files_ge95": sum(1 for a, b in per.values() if a / b >= 0.95),
                "overall": round(easy / tot, 4) if tot else 0.0}
    out["coverage_R4"] = coverage(False)
    out["coverage_R4_swap"] = coverage(True)
    out["sentences_len_ok"] = round(sum(1 for i in sen_idx if items[i]["len_ok"]) / len(sen_idx), 4) if sen_idx else 0.0
    # 문장형에서 문자열마다 '풀이 없는 어려운 말 1개까지' 허용할 때
    out["sentences_le1_R4_swap"] = round(sum(1 for i in sen_idx if items[i]["len_ok"]
                                             and len(hard_under(items[i], 4, swapped=True)) <= 1) / len(sen_idx), 4)
    # 미결 낱말: P에서도 어려운 말로 남는 낱말(결정표에 없는 목록 밖 낱말)
    left = Counter(w for it in items for w in set(hard_under(it, 4)) if w not in tb["swap"])
    out["undecided_types"] = len(left)
    out["undecided_top"] = left.most_common(40)
    # 바꿀 후보마다: P에서 그 낱말 하나만 바꿨다고 칠 때 통과로 바뀌는 문자열 수
    base = rows["P"]
    gain = {}
    for w in tb["swap"]:
        flips = 0
        for i, it in enumerate(items):
            if base[i] or w not in it["hard"]:
                continue
            h = [x for x in hard_under(it, 4) if x != w]
            flips += ok_typed(it, h)
        gain[w] = {"strings": sum(1 for it in items if w in it["hard"]), "flips": flips,
                   "files": len({it["file"] for it in items if w in it["hard"]}), "grade": grade.get(w, "목록 없음")}
    out["swap_gain"] = dict(sorted(gain.items(), key=lambda kv: (-kv[1]["flips"], -kv[1]["strings"])))
    # P+swap에서도 실패하는 이유
    fail_len = sum(1 for i, it in enumerate(items) if not rows["P+swap"][i] and not it["len_ok"])
    out["p_swap_fail"] = {"total": sum(not x for x in rows["P+swap"]), "length": fail_len}
    if a.md:
        print("| 기준 | 전체 | 서로 다른 글 | 이름표 | 문장형 |\n|---|--:|--:|--:|--:|")
        for k, r in out["rates"].items():
            print(f"| {k} | {r['all']:.1%} | {r['unique']:.1%} | {r['labels']:.1%} | {r['sentences']:.1%} |")
        print()
        print("| 지금 말 | 대안 | 등급 | 문자열 | 파일 | P에서 통과로 바뀜 | 메모 |\n|---|---|---|--:|--:|--:|---|")
        for w, gn in out["swap_gain"].items():
            s = tb["swap"][w]
            print(f"| {w} | {s['alt']} | {gn['grade']} | {gn['strings']} | {gn['files']} | {gn['flips']} | {s['note']} |")
        print()
        print("미결 낱말 상위: " + ", ".join(f"{w}({c})" for w, c in out["undecided_top"]))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
