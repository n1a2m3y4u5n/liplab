#!/usr/bin/env python
"""
파일럿 분석(연구 계획서 `docs/pilot/protocol.md` 6절) — 가명 내보내기(`GET /api/pilot/export`, 2판)를 받아
사전·사후 변화, 집단 비교, 효과크기, 폼별 KR-20·문항 분석을 계산하고 보고서(Markdown)·수치(JSON)·참여자별 표(CSV)를 만든다.

분석 규칙(6.1, 자료를 보기 전에 정한 것)을 그대로 옮겼다.
- 사전: 첫 동형 폼 기록(기본은 A여야 한다. --counterbalanced면 그 참여자의 첫 폼). 사후: 사전 뒤에 처음 완료한 다른 폼.
- 같은 폼을 다시 푼 기록, 계획과 순서가 다른 참여자, 사전·사후 form_version이 다른 참여자는 빼고 건수를 보고한다.
- 자가진단(placement) 기록은 쓰지 않는다. 동의를 철회한 참여자(--withdrawn)는 모든 분석에서 뺀다.
- 사후 검사가 없는 참여자는 변화 분석에서 빼고 집단별 인원만 보고한다(값을 채워 넣지 않는다).
가설 검정은 하지 않는다(6.2). 평균 변화의 95% 신뢰구간(t 분포)과 효과크기(d_av, Hedges g_av)만 낸다.

  python scripts/pilot_analysis.py export.json --out pilot_report \\
      --learning 청각장애 --control 대조군 [--test-only 검사만] [--nocue 기호없음] [--counterbalanced] \\
      [--withdrawn pid1,pid2] [--min-active-days 5] [--plots]

집단 이름은 참여 코드에 붙인 집단(`LIPLAB_PILOT_CODES`의 값)이다. 한 집단이 여러 역할에 들어가도 된다
(예: 기호 없는 학습 집단은 --learning과 --nocue에 함께 넣는다).
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict

FORM_LENGTH = 24           # backend/assessment.py FORM_LENGTH(동형 폼 문항 수)
CHANCE = FORM_LENGTH / 4   # 보기 네 개 중 하나
FLOOR_MAX = 8              # 우연 수준 근처로 표시할 정답 수 상한(6 ± 약 2)
CEIL_MIN = 22              # 천장 근처로 표시할 정답 수 하한


# ───────────────────────── 통계 보조(외부 의존 없음) ─────────────────────────
def _betacf(a, b, x):
    """정규화 불완전 베타 함수의 연분수(Numerical Recipes betacf)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / c if abs(1.0 + aa / c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-12:
            break
    return h


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    x = df / (df + t * t)
    tail = 0.5 * _betainc(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_crit(df, level=0.95):
    """양측 신뢰수준 level의 t 임계값(이분법)."""
    target = 1 - (1 - level) / 2
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def describe(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    out = {"n": len(xs), "mean": statistics.fmean(xs), "median": statistics.median(xs), "min": min(xs), "max": max(xs)}
    out["sd"] = statistics.stdev(xs) if len(xs) > 1 else None
    return out


def mean_ci(xs, level=0.95):
    """평균의 t 신뢰구간. 두 명 미만이면 None."""
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m, s = statistics.fmean(xs), statistics.stdev(xs)
    h = t_crit(len(xs) - 1, level) * s / math.sqrt(len(xs))
    return [m - h, m + h]


def welch_ci(a, b, level=0.95):
    """평균 차(a − b)의 Welch t 신뢰구간. 한쪽이라도 두 명 미만이면 None."""
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se = math.sqrt(va + vb)
    if se == 0:
        return [ma - mb, ma - mb]
    df = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    h = t_crit(df, level) * se
    return [ma - mb - h, ma - mb + h]


def effect_sizes(pre, post):
    """대응 자료 효과크기(Lakens 2013). d_av = 평균 변화 / 사전·사후 표준편차의 평균, g_av = d_av × (1 − 3/(4(n−1) − 1))."""
    n = len(pre)
    if n < 2:
        return {"d_av": None, "g_av": None}
    sd_av = (statistics.stdev(pre) + statistics.stdev(post)) / 2
    if sd_av == 0:
        return {"d_av": None, "g_av": None}
    d = (statistics.fmean(post) - statistics.fmean(pre)) / sd_av
    j = 1 - 3 / (4 * (n - 1) - 1) if n > 2 else None
    return {"d_av": d, "g_av": d * j if j is not None else None}


def kr20(matrix):
    """KR-20. matrix: 응시자 × 문항(0/1). 총점 분산은 모분산(KR-20 관례). 응시자 2명 미만이거나 분산 0이면 None."""
    if len(matrix) < 2:
        return None
    k = len(matrix[0])
    totals = [sum(r) for r in matrix]
    var = statistics.pvariance(totals)
    if k < 2 or var == 0:
        return None
    pq = 0.0
    for j in range(k):
        p = sum(r[j] for r in matrix) / len(matrix)
        pq += p * (1 - p)
    return (k / (k - 1)) * (1 - pq / var)


def _pearson(x, y):
    if len(x) < 2:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


# ───────────────────────── 분석 규칙(6.1) ─────────────────────────
def correct_count(test):
    items = test.get("items")
    if items:
        return sum(1 for i in items if i.get("correct"))
    return round((test.get("accuracy") or 0) * FORM_LENGTH)


def select_pair(p, counterbalanced=False):
    """(사전, 사후, 뺀 사유, 다시 푼 기록 수). 사유: None | 'no_form_test' | 'order' | 'no_post' | 'version'."""
    forms = [t for t in (p.get("tests") or []) if t.get("form") in ("A", "B")]
    if not forms:
        return None, None, "no_form_test", 0
    pre = forms[0]
    if not counterbalanced and pre["form"] != "A":
        return None, None, "order", 0
    other = "B" if pre["form"] == "A" else "A"
    repeats = sum(1 for t in forms[1:] if t["form"] == pre["form"])
    post = next((t for t in forms[1:] if t["form"] == other), None)
    if post is None:
        return pre, None, "no_post", repeats
    repeats += sum(1 for t in forms[forms.index(post) + 1:] if t["form"] == other)
    if (pre.get("form_version") or "") != (post.get("form_version") or ""):
        return pre, post, "version", repeats
    return pre, post, None, repeats


def learning_amount(p):
    sj = p.get("since_join") or {}
    trials = sum((v or {}).get("n", 0) for v in (sj.get("trials_by_stage") or {}).values())
    return {"active_days": sj.get("active_days"), "trials": trials, "speak_n": (sj.get("speak") or {}).get("n")}


def analyze(export, learning=(), control=(), test_only=(), nocue=(), counterbalanced=False, withdrawn=(),
            min_active_days=None):
    parts = [p for p in export.get("participants") or [] if p.get("pid") not in set(withdrawn)]
    n_withdrawn = len(export.get("participants") or []) - len(parts)
    rows, excluded = [], defaultdict(Counter)
    for p in parts:
        pre, post, reason, repeats = select_pair(p, counterbalanced)
        cohort = p.get("cohort") or "(없음)"
        if reason:
            excluded[cohort][reason] += 1
        if repeats:
            excluded[cohort]["repeat_records"] += repeats
        if reason is not None:
            continue
        a, b = correct_count(pre), correct_count(post)
        rows.append({"pid": p["pid"], "cohort": cohort, "order": f"{pre['form']}→{post['form']}",
                     "form_version": pre.get("form_version"), "pre": a, "post": b, "change": b - a,
                     "pre_date": pre.get("date"), "post_date": post.get("date"), "pre_after_join": pre.get("after_join"),
                     "floor": a <= FLOOR_MAX or b <= FLOOR_MAX, "ceiling": a >= CEIL_MIN or b >= CEIL_MIN,
                     **learning_amount(p)})

    def group_stats(rs):
        pre = [r["pre"] for r in rs]
        post = [r["post"] for r in rs]
        ch = [r["change"] for r in rs]
        return {"n": len(rs), "pre": describe(pre), "post": describe(post), "change": describe(ch),
                "change_ci95": mean_ci(ch), **effect_sizes(pre, post)}

    by_cohort = defaultdict(list)
    for r in rows:
        by_cohort[r["cohort"]].append(r)
    groups = {c: group_stats(rs) for c, rs in sorted(by_cohort.items())}

    def pick(names):
        return [r for r in rows if r["cohort"] in set(names)]

    roles = {}
    for name, members in (("learning", learning), ("control", control), ("test_only", test_only)):
        if members:
            roles[name] = {"cohorts": list(members), **group_stats(pick(members))}
    comparisons = {}
    if learning and control:
        lr, cr = pick(learning), pick(control)
        comparisons["learning_minus_control_change"] = {
            "diff": (statistics.fmean([r["change"] for r in lr]) - statistics.fmean([r["change"] for r in cr]))
            if lr and cr else None,
            "ci95": welch_ci([r["change"] for r in lr], [r["change"] for r in cr])}
        comparisons["learning_minus_control_pre"] = {
            "diff": (statistics.fmean([r["pre"] for r in lr]) - statistics.fmean([r["pre"] for r in cr]))
            if lr and cr else None,
            "ci95": welch_ci([r["pre"] for r in lr], [r["pre"] for r in cr])}
    if nocue and learning:
        on = [r for r in pick(learning) if r["cohort"] not in set(nocue)]
        off = [r for r in pick(learning) if r["cohort"] in set(nocue)]
        comparisons["cue_on_minus_off_change"] = {
            "n_on": len(on), "n_off": len(off),
            "diff": (statistics.fmean([r["change"] for r in on]) - statistics.fmean([r["change"] for r in off]))
            if on and off else None,
            "ci95": welch_ci([r["change"] for r in on], [r["change"] for r in off])}
    if counterbalanced:
        acc = defaultdict(list)
        for p in parts:
            for t in p.get("tests") or []:
                if t.get("form") in ("A", "B"):
                    acc[t["form"]].append(correct_count(t))
        comparisons["form_A_minus_B_mean_correct"] = {
            "diff": (statistics.fmean(acc["A"]) - statistics.fmean(acc["B"])) if acc["A"] and acc["B"] else None,
            "n_A": len(acc["A"]), "n_B": len(acc["B"])}

    completers = None
    if min_active_days is not None:
        cr = [r for r in rows if (r["active_days"] or 0) >= min_active_days]
        completers = {"min_active_days": min_active_days, **group_stats(cr),
                      "by_cohort": {c: group_stats([r for r in cr if r["cohort"] == c])
                                    for c in sorted({r["cohort"] for r in cr})}}

    items = item_analysis(parts, rows)
    return {"version": export.get("version"), "exported_at": export.get("exported_at"),
            "rules": {"counterbalanced": counterbalanced, "form_length": FORM_LENGTH,
                      "floor_max": FLOOR_MAX, "ceiling_min": CEIL_MIN},
            "n_participants": len(parts), "n_withdrawn_excluded": n_withdrawn, "n_analyzed": len(rows),
            "excluded": {c: dict(v) for c, v in excluded.items()},
            "groups": groups, "roles": roles, "comparisons": comparisons, "completers": completers,
            "items": items, "rows": rows}


def item_analysis(parts, rows):
    """폼별 KR-20·문항 정답률·교정 점이연 상관·오답 보기 빈도. 분석에 들어간 참여자의 사전·사후 기록만 쓴다(6.3)."""
    use = {r["pid"] for r in rows}
    per_form = defaultdict(list)
    for p in parts:
        if p["pid"] not in use:
            continue
        pre, post, _, _ = select_pair(p, True)
        for t in (pre, post):
            if t and t.get("items"):
                per_form[t["form"]].append(t["items"])
    out = {}
    for form, logs in sorted(per_form.items()):
        ids = sorted({i.get("id") for log in logs for i in log}, key=str)
        complete = [log for log in logs if {i.get("id") for i in log} == set(ids)]
        matrix = [[1 if {i.get("id"): i for i in log}[q].get("correct") else 0 for q in ids] for log in complete]
        wrong_choices = defaultdict(Counter)
        for log in logs:
            for i in log:
                if not i.get("correct") and i.get("chosen") is not None:
                    wrong_choices[i.get("id")][str(i.get("chosen"))] += 1
        items = []
        for j, q in enumerate(ids):
            col = [r[j] for r in matrix]
            rest = [sum(r) - r[j] for r in matrix]
            items.append({"id": q, "p": statistics.fmean(col) if col else None,
                          "r_it_corrected": _pearson(col, rest),
                          "top_wrong": wrong_choices[q].most_common(3)})
        out[form] = {"n_records": len(logs), "n_complete": len(complete), "k": len(ids),
                     "kr20": kr20(matrix) if matrix else None, "items": items}
    return out


# ───────────────────────── 출력 ─────────────────────────
def _f(x, nd=2):
    if x is None:
        return "-"
    if isinstance(x, (list, tuple)):
        return "[" + ", ".join(_f(v, nd) for v in x) + "]"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


REASONS = {"no_form_test": "동형 폼 기록 없음", "order": "계획과 순서가 다름(A가 먼저가 아님)", "no_post": "사후 검사 없음",
           "version": "사전·사후 판본 다름", "repeat_records": "같은 폼을 다시 푼 기록(뺀 기록 수)"}


def report_md(res):
    L = ["# 파일럿 분석 결과", "",
         f"가명 내보내기 {res['exported_at']}(판 {res['version']}), 참여자 {res['n_participants']}명 중 분석 {res['n_analyzed']}명. "
         f"동의 철회로 뺀 참여자 {res['n_withdrawn_excluded']}명. 규칙은 `docs/pilot/protocol.md` 6.1절"
         f"({'역균형' if res['rules']['counterbalanced'] else 'A→B 고정'}). 정답 수는 {FORM_LENGTH}문항 기준이다.", "",
         "가설 검정은 하지 않았다. 신뢰구간은 인원이 적어 넓다.", "", "## 1. 뺀 기록(6.1·6.4)", "",
         "| 집단 | 사유 | 수 |", "|---|---|---|"]
    for c, v in sorted(res["excluded"].items()):
        for k, n in v.items():
            L.append(f"| {c} | {REASONS.get(k, k)} | {n} |")
    L += ["", "## 2. 집단별 사전·사후(6.2)", "",
          "| 집단 | n | 사전 평균(SD) | 사후 평균(SD) | 변화 평균 [95% CI] | 변화 중앙값(범위) | d_av | g_av |",
          "|---|---|---|---|---|---|---|---|"]

    def grow(name, g):
        if not g.get("n"):
            return f"| {name} | 0 | - | - | - | - | - | - |"
        pre, post, ch = g["pre"], g["post"], g["change"]
        return (f"| {name} | {g['n']} | {_f(pre['mean'])}({_f(pre.get('sd'))}) | {_f(post['mean'])}({_f(post.get('sd'))}) | "
                f"{_f(ch['mean'])} {_f(g['change_ci95'])} | {_f(ch['median'])}({_f(ch['min'], 0)}~{_f(ch['max'], 0)}) | "
                f"{_f(g.get('d_av'))} | {_f(g.get('g_av'))} |")
    for c, g in res["groups"].items():
        L.append(grow(c, g))
    if res["roles"]:
        L += ["", "역할별 묶음:", "", "| 역할 | 집단 | n | 사전 평균 | 사후 평균 | 변화 평균 [95% CI] | g_av |", "|---|---|---|---|---|---|---|"]
        names = {"learning": "당사자 학습", "control": "비당사자 대조", "test_only": "검사만(학습 없이 생기는 변화)"}
        for k, g in res["roles"].items():
            if g.get("n"):
                L.append(f"| {names[k]} | {', '.join(g['cohorts'])} | {g['n']} | {_f(g['pre']['mean'])} | {_f(g['post']['mean'])} | "
                         f"{_f(g['change']['mean'])} {_f(g['change_ci95'])} | {_f(g.get('g_av'))} |")
    if res["comparisons"]:
        L += ["", "비교:", ""]
        labels = {"learning_minus_control_change": "학습 − 대조, 변화량 차", "learning_minus_control_pre": "학습 − 대조, 사전 점수 차",
                  "cue_on_minus_off_change": "기호 켬 − 기호 끔, 변화량 차(학습 집단 안)", "form_A_minus_B_mean_correct": "A폼 − B폼 평균 정답 수"}
        for k, v in res["comparisons"].items():
            extra = f" (켬 {v['n_on']}명, 끔 {v['n_off']}명)" if "n_on" in v else ""
            L.append(f"- {labels.get(k, k)}: {_f(v.get('diff'))} {_f(v.get('ci95')) if v.get('ci95') else ''}{extra}")
    if res.get("completers"):
        cp = res["completers"]
        L += ["", f"## 3. 권장 학습량을 채운 참여자(학습한 날 {cp['min_active_days']}일 이상, 6.3)", "",
              "| 집단 | n | 변화 평균 [95% CI] | g_av |", "|---|---|---|---|"]
        for c, g in cp["by_cohort"].items():
            if g.get("n"):
                L.append(f"| {c} | {g['n']} | {_f(g['change']['mean'])} {_f(g['change_ci95'])} | {_f(g.get('g_av'))} |")
    L += ["", "## 4. 표준검사 문항 분석(6.3, 참고용)", ""]
    for form, it in res["items"].items():
        L.append(f"- {form}폼: 기록 {it['n_records']}건(모든 문항이 있는 {it['n_complete']}건), 문항 {it['k']}개, "
                 f"KR-20 {_f(it['kr20'])}. 인원이 적어 신뢰도의 근거로 쓰지 않는다.")
        hard = sorted([i for i in it["items"] if i["p"] is not None], key=lambda i: i["p"])[:5]
        if hard:
            L.append("  - 정답률이 가장 낮은 문항: " + ", ".join(f"{i['id']}({_f(i['p'])})" for i in hard))
        neg = [i for i in it["items"] if i["r_it_corrected"] is not None and i["r_it_corrected"] < 0]
        if neg:
            L.append("  - 교정 점이연 상관이 음수인 문항(판본 v2 교체 후보): " + ", ".join(str(i["id"]) for i in neg))
    flagged = [r for r in res["rows"] if r["floor"] or r["ceiling"]]
    L += ["", "## 5. 참여자별(표 전체는 participants.csv)", "",
          f"우연 수준 근처(정답 {FLOOR_MAX}개 이하) 또는 천장 근처({CEIL_MIN}개 이상)인 참여자 {len(flagged)}명은 표에 표시했다. "
          "개인 변화의 의미는 판정하지 않는다(6.2).", ""]
    return "\n".join(L) + "\n"


def write_outputs(res, out_dir, plots=False):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md(res))
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    cols = ["pid", "cohort", "order", "form_version", "pre", "post", "change", "floor", "ceiling",
            "pre_date", "post_date", "pre_after_join", "active_days", "trials", "speak_n"]
    with open(os.path.join(out_dir, "participants.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in res["rows"]:
            w.writerow(r)
    if plots and res["rows"]:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return
        cohorts = sorted({r["cohort"] for r in res["rows"]})
        fig, axes = plt.subplots(1, len(cohorts), figsize=(3.2 * len(cohorts), 3.4), sharey=True, squeeze=False)
        for ax, c in zip(axes[0], cohorts):
            for r in [r for r in res["rows"] if r["cohort"] == c]:
                ax.plot([0, 1], [r["pre"], r["post"]], color="#6b7280", lw=1, marker="o", ms=3)
            ax.axhline(CHANCE, color="#9ca3af", ls="--", lw=0.8)
            ax.set_xticks([0, 1], ["사전", "사후"])
            ax.set_title(c, fontsize=10)
            ax.set_ylim(0, FORM_LENGTH)
        axes[0][0].set_ylabel(f"정답 수(/{FORM_LENGTH})")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "pre_post.png"), dpi=150)
        plt.close(fig)


def _list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="파일럿 가명 내보내기 분석(protocol.md 6절)")
    ap.add_argument("export", help="GET /api/pilot/export 결과 JSON 파일")
    ap.add_argument("--out", default="pilot_report", help="결과 폴더(보고서·수치·참여자 표)")
    ap.add_argument("--learning", default="", help="당사자 학습 집단(쉼표 구분)")
    ap.add_argument("--control", default="", help="비당사자 대조 집단")
    ap.add_argument("--test-only", default="", help="검사만 하는 집단")
    ap.add_argument("--nocue", default="", help="기호 없이 학습한 집단(LIPLAB_PILOT_NOCUE_COHORTS)")
    ap.add_argument("--counterbalanced", action="store_true", help="역균형(참여자마다 첫 폼이 사전)")
    ap.add_argument("--withdrawn", default="", help="동의 철회한 가명(쉼표 구분), 모든 분석에서 뺀다")
    ap.add_argument("--min-active-days", type=int, default=None, help="권장 학습량 기준(학습한 날 수)")
    ap.add_argument("--plots", action="store_true", help="참여자별 사전·사후 선 그래프(pre_post.png)")
    a = ap.parse_args(argv)
    with open(a.export, encoding="utf-8") as f:
        export = json.load(f)
    if export.get("version") != 2:
        print(f"[WARN] 내보내기 판이 2가 아니다({export.get('version')}). 문항 기록이 없으면 KR-20을 계산하지 못한다.",
              file=sys.stderr)
    res = analyze(export, _list(a.learning), _list(a.control), _list(a.test_only), _list(a.nocue),
                  a.counterbalanced, _list(a.withdrawn), a.min_active_days)
    write_outputs(res, a.out, a.plots)
    print(f"분석 {res['n_analyzed']}명 / 참여자 {res['n_participants']}명 → {os.path.join(a.out, 'report.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
