#!/usr/bin/env python
"""
결과보고서용 그림 다시 그리기 — 그림 5(독화 난이도 지수), 그림 7 대응(538 실발화 재측정), 그림 12(시스템 데이터 흐름).

계획서의 두 그림은 제출 당시 프로토타입 출력과 계획 단계의 구조도다. 지금 구현에 맞춰 다시 그린다.
  · 그림 5: backend/perceptual.word_difficulty(규칙 기반, 528단어 은행 기준)의 실제 출력. 항목별 기여를 쌓아 보인다.
  · 그림 12: 실제 데이터·모델 흐름. 공유 백본 하나가 아니라 축마다 모델·규칙이 따로 있고, 영상은 기기 안에서만 처리한다.

  python3 scripts/make_report_figures.py [--b608 b608.json]   # → docs/figures/fig5_difficulty.png, fig7_b_remeasure.png, fig12_dataflow.png
의존성: matplotlib(시스템 python), 백엔드의 순수 파이썬 모듈(perceptual·curriculum·content_rules).
"""
import os
import sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "backend"))
OUT = os.path.join(_ROOT, "docs", "figures")

plt.rcParams.update({"font.family": "Apple SD Gothic Neo", "axes.unicode_minus": False, "font.size": 10})
INK, MUTED, LINE = "#1f2430", "#6b7280", "#c9ced8"
C1, C2, C3 = "#2f4b7c", "#7a93bf", "#c7d3e8"      # 한 계열의 진·중·연(의미: 기여 크기 순)
SERVER, DEVICE = "#e8eef8", "#e6f2ec"             # 서버 쪽 · 기기 안


def fig5():
    import curriculum as C
    import perceptual as P
    from content_rules import is_hangul_word, viseme_signature
    words = [w for w in dict.fromkeys(x["word"] for x in C.WORD_BANK) if is_hangul_word(w)]
    sig = Counter(viseme_signature(w) for w in words)
    bank = sorted((e for e in (P.word_difficulty(w, sig) for w in words) if e), key=lambda e: e["difficulty"])
    named = ["공항", "학교", "항구", "나비", "바다"]           # 계획서 본문이 예로 든 단어
    picks = {e["word"]: e for e in (P.word_difficulty(w, sig) for w in named) if e}
    for q in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0):              # 은행 분포에서 고른 단어
        e = bank[int(q * (len(bank) - 1))]
        picks.setdefault(e["word"], e)
    rows = sorted(picks.values(), key=lambda e: e["difficulty"])

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 4.6), gridspec_kw={"width_ratios": [1.35, 1]})
    y = range(len(rows))
    a = [0.5 * e["invisibility"] for e in rows]
    b = [0.3 * e["homophene_ratio"] for e in rows]
    c = [0.2 * e["neighbor_density"] for e in rows]
    ax.barh(y, a, color=C1, label="0.5 × 비가시성")
    ax.barh(y, b, left=a, color=C2, label="0.3 × 동구형이음 비율")
    ax.barh(y, c, left=[i + j for i, j in zip(a, b)], color=C3, label="0.2 × 혼동 이웃 밀도")
    for k, e in enumerate(rows):
        ax.text(e["difficulty"] + 0.012, k, f"{e['difficulty']:.2f}", va="center", color=INK, fontsize=9)
    ax.set_yticks(list(y), [e["word"] + (" *" if e["word"] in named else "") for e in rows])
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("독화 난이도 지수(0 쉬움 ~ 1 어려움)")
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    ax.set_title("(가) 단어별 지수와 항목별 기여", loc="left", fontsize=10.5, color=INK)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    vals = [e["difficulty"] for e in bank]
    bx.hist(vals, bins=20, range=(0, 1), color=C2, edgecolor="white")
    for w in named:
        v = picks[w]["difficulty"]
        bx.axvline(v, color=C1, lw=1, ls=(0, (3, 2)))
    bx.set_xlim(0, 1)
    bx.set_xlabel("독화 난이도 지수")
    bx.set_ylabel("단어 수")
    bx.set_title(f"(나) 단어 은행 {len(vals)}개의 분포(점선: * 단어)", loc="left", fontsize=10.5, color=INK)
    for s in ("top", "right"):
        bx.spines[s].set_visible(False)
    fig.text(0.01, 0.01, "지수 = 0.5×비가시성 + 0.3×동구형이음 비율 + 0.2×혼동 이웃 밀도(같은 입모양 순열의 다른 단어 수, 5개에서 포화). "
             "규칙 기반, backend/perceptual.py. * 계획서 본문의 예시 단어.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    p = os.path.join(OUT, "fig5_difficulty.png")
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def _box(ax, x, y, w, h, title, lines, fc, bold_color=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                fc=fc, ec=LINE, lw=1))
    ax.text(x + 0.012, y + h - 0.02, title, ha="left", va="top", fontsize=9.6, weight="bold", color=bold_color)
    for i, t in enumerate(lines):
        ax.text(x + 0.012, y + h - 0.052 - i * 0.03, t, ha="left", va="top", fontsize=8.2, color=INK)


def _arrow(ax, p, q, text=None, rad=0.0, color=MUTED):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11, lw=1.2, color=color,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 0.018, text, ha="center", va="bottom", fontsize=7.8, color=MUTED)


def fig12():
    """행마다 데이터 → 모델·규칙 → 학습자 화면 → 기록이 가로로 이어지게 놓아 화살표가 겹치지 않게 한다.
    학습자 화면 첫 행을 비워, 지식추적에서 개인화(콘텐츠 선택)로 돌아가는 순환 화살표가 그 줄로 지나가게 한다."""
    fig = plt.figure(figsize=(13.5, 7.6))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    X0, X1, X2, X3 = 0.02, 0.235, 0.53, 0.775        # 열 왼쪽
    W0, W1, W2, W3 = 0.17, 0.25, 0.2, 0.2
    for x, t in ((X0, "데이터"), (X1, "모델·규칙"), (X2, "학습자 화면"), (X3, "기록")):
        ax.text(x, 0.968, t, fontsize=11.5, weight="bold", color=INK, va="top")
    rows = {"A": (0.76, 0.13), "B": (0.60, 0.13), "C": (0.44, 0.13), "D": (0.28, 0.13), "E": (0.06, 0.16)}
    cy = {k: y + h / 2 for k, (y, h) in rows.items()}
    GRAY, AMBER = "#f4f5f7", "#fbf7ee"

    def box(col, row, title, lines, fc):
        x, w = {0: (X0, W0), 1: (X1, W1), 2: (X2, W2), 3: (X3, W3)}[col]
        y, h = rows[row]
        _box(ax, x, y, w, h, title, lines, fc)

    # 서버·기기 묶음(모델 열)
    ax.add_patch(FancyBboxPatch((X1 - 0.01, 0.268), W1 + 0.02, 0.655, boxstyle="round,pad=0.004,rounding_size=0.014",
                                fc="none", ec=C2, lw=1, ls=(0, (4, 3))))
    ax.text(X1 - 0.003, 0.918, "서버", fontsize=8.5, color=C1, va="top")
    ax.add_patch(FancyBboxPatch((X1 - 0.01, 0.045), W1 + 0.02, 0.21, boxstyle="round,pad=0.004,rounding_size=0.014",
                                fc="none", ec="#5a9a78", lw=1, ls=(0, (4, 3))))
    ax.text(X1 - 0.003, 0.25, "기기 안(영상은 밖으로 나가지 않음)", fontsize=8.5, color="#2f6b4f", va="top")

    box(0, "A", "규칙 자원", ["비심 표·표준발음법", "LLM 생성 후보(검수 전)"], GRAY)
    box(0, "B", "AI Hub 538 립리딩", ["30화자 영상·음성", "A·D 학습, C 데이터 유사도"], GRAY)
    box(0, "C", "낭독 음성", ["zeroth_korean·538 음성", "채점 모델·보정 기준"], GRAY)
    box(0, "D", "AI Hub 608 언어청각장애", ["감음신경성 화자 음성", "실제 발화 측정"], GRAY)
    box(0, "E", "학습자 웹캠·마이크", ["웹캠 영상은 기기 안에서", "입 계수로만 바뀐다"], GRAY)

    box(1, "A", "C·G 콘텐츠와 개인화", ["규칙 게이트 → 사람 검수 → 승인 문항", "약한 입모양이 든 문항·기호 표적 선택"], SERVER)
    box(1, "B", "A 음성구동 아바타", ["동결 WavLM + BiGRU(20화자)", "예시 입모양은 미리 계산"], SERVER)
    box(1, "C", "B 발음 채점", ["전사 채점 + 소리·입모양 융합", "D-GOP(전사 비의존, 기본 꺼짐)"], SERVER)
    box(1, "D", "A 농인 발화 합성(연구)", ["규칙 교란 경·중·심 → 견고성 실험", "제품 모델에는 넣지 않음(A1 판정)"], SERVER)
    box(1, "E", "D·K·E 기기 안 추론", ["MediaPipe 입 계수 → ONNX(단어·비음)", "웹캠 3차원·모음 포먼트 교정",
                                        "혀 역추정은 USC-TIMIT 랩 실증(미이식)"], DEVICE)

    box(2, "B", "독화 레슨·다자 대화", ["입모양·단어·문장·문맥·복습·엔드리스", "F 아바타, J 시각 기호(답 확인 뒤)"], "#ffffff")
    box(2, "C", "말하기 연습", ["소리·입모양 점수", "약한 소리 코칭"], "#ffffff")
    box(2, "D", "I 표준검사", ["동형 폼 A·B(사전·사후)", "오답 입모양 → 지식추적 시드"], "#ffffff")
    box(2, "E", "웹캠 입모양 연습", ["단어 레슨 입모양 확인", "교정 세션·비음 기호"], "#ffffff")

    box(3, "A", "지식추적", ["입모양별 숙달도 추정", "약한 입모양 목록"], AMBER)
    _box(ax, X3, 0.06, W3, 0.67, "학습 기록", ["시행·정오답·고른 보기", "말하기 점수·교정 세션 오차", "검사 문항 기록",
                                              "파일럿 가명 내보내기"], AMBER)

    for r in ("A", "B", "C", "E"):                                  # 데이터 → 모델(제품 흐름)
        _arrow(ax, (X0 + W0, cy[r]), (X1, cy[r]))
    ax.add_patch(FancyArrowPatch((X0 + W0, cy["D"]), (X1, cy["D"]), arrowstyle="-|>", mutation_scale=11, lw=1.2,
                                 color=MUTED, ls=(0, (3, 2))))       # 연구·검증 흐름
    for r in ("B", "C", "E"):                                       # 모델 → 학습자 화면
        _arrow(ax, (X1 + W1, cy[r]), (X2, cy[r]))
    _arrow(ax, (X1 + W1, rows["A"][0] + 0.02), (X2, rows["B"][0] + rows["B"][1] - 0.025))   # 개인화 → 레슨
    for r in ("B", "C", "D", "E"):                                  # 학습자 화면 → 기록
        _arrow(ax, (X2 + W2, cy[r]), (X3, cy[r]))
    _arrow(ax, (X3 + W3 / 2, 0.73), (X3 + W3 / 2, 0.76))            # 기록 → 지식추적
    _arrow(ax, (X3, cy["A"]), (X1 + W1, cy["A"]), color=C1)  # 순환: 지식추적 → 개인화
    ax.text((X2 + X2 + W2) / 2, cy["A"] + 0.03, "순환: 약한 입모양 → 다음 문항·기호 표적", ha="center", fontsize=8.6, color=C1)
    ax.text(0.02, 0.012, "실선은 제품의 데이터 흐름, 점선은 연구·검증 흐름. 공유 백본 하나가 아니라 축마다 모델·규칙이 따로 있다"
            "(A-9 공용 백본 서비스는 미구현). AI Hub 자료는 재배포할 수 없어 앱 데모에는 합성 음성을 쓴다.", fontsize=8, color=MUTED)
    p = os.path.join(OUT, "fig12_dataflow.png")
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


def fig7(ref, b608=None):
    """B·A 실측 — 538 실발화 300문장에 규칙 교란(경·중·심)을 걸었을 때 전사 오류와 D-GOP가 강도에 따라 어떻게 변하는가.
    (가)(나) 조건별 전사 오류·D-GOP 평균과 95% 부트스트랩 구간, (다) 문장 단위 D-GOP 대 전사 정확도(1 - CER, 5조건).
    b608(선택)을 주면 실제
    청각장애 발화(608 감음신경성) 문장 분포를 (가)에 함께 놓는다."""
    import json
    import numpy as np
    per = json.load(open(ref, encoding="utf-8"))["per_clip"]
    conds = [("clean", "원본"), ("mild", "경"), ("mod", "중"), ("sev", "심")]
    real = None
    if b608 and os.path.exists(b608):
        rows = json.load(open(b608, encoding="utf-8"))["per_sentence"]
        real = [r for r in rows if "감음신경성" in r.get("cat", "")]
    rng = np.random.default_rng(0)

    def mci(v):
        v = np.asarray([x for x in v if x is not None], float)
        bs = [rng.choice(v, len(v)).mean() for _ in range(2000)]
        return v.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)

    fig, axs = plt.subplots(1, 3, figsize=(12.5, 4.2), gridspec_kw={"width_ratios": [1, 1, 1.15]})
    for ax, key, lab in ((axs[0], "cer", "전사 오류(음절 CER)"), (axs[1], "dgop", "D-GOP 원점수(naive ×100)")):
        xs = list(range(len(conds)))
        st = [mci([r[c][key] for r in per if r.get(c)]) for c, _ in conds]
        ax.errorbar(xs, [m for m, _, _ in st], yerr=[[m - lo for m, lo, _ in st], [hi - m for m, _, hi in st]],
                    color=C1, marker="o", capsize=3, lw=1.6, label="538 실발화 + 규칙 교란")
        names = [n for _, n in conds]
        if real:
            m, lo, hi = mci([r[key] for r in real])
            ax.errorbar([len(conds)], [m], yerr=[[m - lo], [hi - m]], color="#b45309", marker="s", capsize=3, lw=0,
                        elinewidth=1.6, label="608 실제 청각장애 발화")
            names = names + ["608"]
        ax.set_xticks(list(range(len(names))), names)
        ax.set_xlim(-0.4, len(names) - 0.6)
        ax.set_title(lab, loc="left", fontsize=10.5, color=INK)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axs[0].set_ylim(0, 1)
    axs[1].set_ylim(0, None)
    axs[0].legend(loc="lower right", frameon=False, fontsize=8)
    ax = axs[2]
    sc = conds + [("blur", "흐림(평가용)")]            # remeasure_b 요약의 문장 단위 상관과 같은 5조건
    for (c, n), col in zip(sc, (C1, C2, C3, "#9aa3b2", "#d4a373")):
        pts = [(1 - r[c]["cer"], r[c]["dgop"]) for r in per if r.get(c) and r[c]["cer"] is not None and r[c]["dgop"] is not None]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=7, color=col, alpha=0.6, label=n, lw=0)
    allp = [(1 - r[c]["cer"], r[c]["dgop"]) for r in per for c, _ in sc
            if r.get(c) and r[c]["cer"] is not None and r[c]["dgop"] is not None]
    a, b = np.array([p[0] for p in allp]), np.array([p[1] for p in allp])
    rho = np.corrcoef(a.argsort().argsort(), b.argsort().argsort())[0, 1]
    ax.set_xlabel("전사 정확도(1 - CER)")
    ax.set_ylabel("D-GOP 원점수")
    ax.set_title(f"(다) 문장 단위(5조건), 스피어만 {rho:.2f}", loc="left", fontsize=10.5, color=INK)
    ax.legend(loc="upper left", frameon=False, fontsize=8, markerscale=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    axs[0].set_title("(가) " + axs[0].get_title(loc="left"), loc="left", fontsize=10.5, color=INK)
    axs[1].set_title("(나) " + axs[1].get_title(loc="left"), loc="left", fontsize=10.5, color=INK)
    fig.text(0.01, 0.01, f"AI Hub 538 10화자 {len(per)}문장, 전사·정렬 모델 kresnik wav2vec2(그리디). 막대는 평균의 95% 부트스트랩 구간."
             + (" 608은 감음신경성 화자 문장(세션 문장 분할 후 같은 채점)." if real else ""), fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    p = os.path.join(OUT, "fig7_b_remeasure.png")
    fig.savefig(p, dpi=200)
    plt.close(fig)
    return p


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--b-ref", default=os.path.expanduser("~/Downloads/liplab-lab/data/pod_runs/20260923_n5mpjqpx5cvge6/b_remeasure.json"),
                    help="remeasure_b.py 결과(그림 7 대응)")
    ap.add_argument("--b608", default=None, help="b608_measure.py 결과(있으면 그림 7에 608 분포를 더한다)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    print(fig5())
    print(fig12())
    if os.path.exists(a.b_ref):
        print(fig7(a.b_ref, a.b608))
