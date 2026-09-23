#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""E-6 VocalTractLab 자산 빌드(오프라인 전용).

VocalTractLab(VTL, Peter Birkholz, GPL-3.0)을 파이썬 바인딩 vocaltractlab-cython(Paul Krug, GPL-3.0)의
파라미터 인터페이스로 불러, 한국어 단모음 8개와 자음 조음 위치 목표의 정중시상 단면 윤곽, 포먼트,
모음 합성음을 계산하고 frontend/public/vtl/ 아래에 데이터 파일로 쓴다.

  shapes.json      음소별 성도 파라미터·윤곽·포먼트(모음은 목표값과 함께)
  vowel_grid.json  모음 사이를 보간한 성도 격자(입술 펴짐/둥글림 두 층). 격자점마다 VTL 포먼트와 윤곽
  vowels/<id>.wav  모음 합성음(16 kHz 모노 16비트, 약 0.6초)
  meta.json        VTL 판본, 화자 파일, 빌드 날짜, 라이선스, 파일 해시

앱(프론트·백엔드)은 VTL을 번들하거나 호출하지 않고 위 결과 파일만 읽는다. 이 스크립트는 GPL
라이브러리를 import하므로 GPL-3.0-or-later로 둔다. 설명과 비교표는 docs/e6-vocaltractlab.md.

실행(의존성: pip install vocaltractlab-cython==0.0.17 numpy):
  python scripts/vtl_build_assets.py --build-date 2026-09-24
  python scripts/vtl_build_assets.py --build-date 2026-09-24 --report /tmp/vtl_report.md

결정론: 같은 환경에서 다시 실행하면 출력 바이트가 같다. 빌드 날짜는 인자로 받고, 부동소수는 반올림해
쓰고, 합성음은 같은 입력에서 같은 결과를 내는 VTL 합성(프로세스를 바꿔 두 번 실행해 확인)을 정수 PCM으로
양자화한다. meta.json의 파일별 SHA-256으로 비교할 수 있다.
"""
import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import wave
from importlib import metadata

import numpy as np

try:
    import vocaltractlab_cython as vtl
except ImportError:  # pragma: no cover
    sys.exit("vocaltractlab-cython이 필요하다: pip install vocaltractlab-cython==0.0.17 numpy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "frontend", "public", "vtl")
SIM_JSX = os.path.join(ROOT, "frontend", "src", "components", "VocalTractSimulator.jsx")
SCHEMA = 1

# ── 한국어 단모음 레시피 ────────────────────────────────────────────────────────────
# base: JD3 화자 파일의 모음 형상과 가중치(둘이면 파라미터를 그 비율로 섞는다).
# lips: 입술 두 변수(LP 돌출, LD 상하 간격)를 가져올 형상. 혀·턱·설골·연구개는 base를 따른다.
# fit:  base의 전달함수 포먼트가 앱 판정 폭(formants.py, F1 ±35%·F2 ±15%) 밖이면 이 변수 하나를
#       step 단위로 옮겨, 판정 폭 안으로 들어오는 가장 작은 변화를 쓴다. 판정 폭 안이면 옮기지 않는다.
VOWELS = [
    dict(id="i", ko="ㅣ", ipa="i", round=0, base=[("i", 1.0)],
         why="독일어 /iː/ 형상. 전달함수 F1이 목표보다 30% 낮아 혀 몸통 높이만 조금 내린다.",
         fit=dict(param="TCY", step=-0.01, max_steps=60)),
    dict(id="e", ko="ㅔ", ipa="e", round=0, base=[("e", 0.5), ("E", 0.5)],
         why="목표 F1(450 Hz)이 독일어 긴장 /eː/와 이완 /ɛ/ 사이라 두 형상을 반씩 섞는다(중모음 [e̞])."),
    dict(id="ae", ko="ㅐ", ipa="ɛ", round=0, base=[("E", 1.0)],
         why="독일어 /ɛ/ 형상을 그대로 쓴다."),
    dict(id="a", ko="ㅏ", ipa="a", round=0, base=[("a", 1.0)],
         why="독일어 /a/ 형상을 그대로 쓴다."),
    dict(id="eo", ko="ㅓ", ipa="ʌ", round=0, base=[("O", 1.0)], lips="a",
         why="독일어에 평순 후설 중저모음이 없어 /ɔ/의 혀·턱에 /a/의 펴진 입술을 붙인다."),
    dict(id="o", ko="ㅗ", ipa="o", round=1, base=[("o", 0.5), ("O", 0.5)],
         why="목표 F1(460 Hz)이 독일어 긴장 /oː/와 이완 /ɔ/ 사이라 두 형상을 반씩 섞는다(중모음 [o̞])."),
    dict(id="u", ko="ㅜ", ipa="u", round=1, base=[("u", 1.0)],
         why="독일어 /uː/ 형상을 그대로 쓴다."),
    dict(id="eu", ko="ㅡ", ipa="ɯ", round=0, base=[("u", 1.0)], lips="i",
         why="/uː/의 뒤쪽 높은 혀에 /iː/의 펴진 입술을 붙인다(평순 고모음)."),
]

# ── 자음 조음 위치 목표 ────────────────────────────────────────────────────────────
# JD3의 자음 형상은 모음 문맥(a·i·u)별로 있다. 문맥에 따라 혀 몸통 자세가 달라지므로(동시조음)
# 여기서는 모두 /a/ 문맥 하나로 맞춘다. 비음은 같은 형상에서 연구개 개방(VO)만 바꾼다.
NASAL_VO = 0.5          # VTL 파라미터 VO. tract_state_to_tube_state 기준 연구개 통로 1.0 cm²
CONSONANTS = [
    dict(id="b", ko="ㅂ", ipa="p", place="양순", manner="파열", base="ll-labial-closure(a)", pair="m",
         why="두 입술 폐쇄. 연구개는 닫혀 있다."),
    dict(id="m", ko="ㅁ", ipa="m", place="양순", manner="비음", base="ll-labial-closure(a)", nasal=True, pair="b",
         why="ㅂ과 같은 형상에서 연구개만 내린다. 입술은 ㅂ과 같아 입모양으로는 구별되지 않는다."),
    dict(id="d", ko="ㄷ", ipa="t", place="치경", manner="파열", base="tt-alveolar-closure(a)", pair="n",
         why="혀끝이 윗잇몸(치경)에 닿는 폐쇄."),
    dict(id="n", ko="ㄴ", ipa="n", place="치경", manner="비음", base="tt-alveolar-closure(a)", nasal=True, pair="d",
         why="ㄷ과 같은 형상에서 연구개만 내린다."),
    dict(id="g", ko="ㄱ", ipa="k", place="연구개", manner="파열", base="tb-velar-closure(a)", pair="ng",
         why="혀 뒤쪽이 연구개에 닿는 폐쇄."),
    dict(id="ng", ko="ㅇ", ipa="ŋ", place="연구개", manner="비음", base="tb-velar-closure(a)", nasal=True, pair="g",
         why="ㄱ과 같은 형상에서 연구개만 내린다(받침 ㅇ)."),
    dict(id="s", ko="ㅅ", ipa="s", place="치경", manner="마찰", base="tt-alveolar-fricative(a)",
         why="혀끝과 치경 사이의 좁은 틈."),
    dict(id="j", ko="ㅈ", ipa="tɕ", place="경구개(근사)", manner="파찰", base="tt-postalveolar-closure(a)",
         why="JD3에 치경경구개 파찰음이 없어 후치경 폐쇄로 폐쇄 단계를 근사한다."),
    dict(id="l", ko="ㄹ", ipa="l", place="치경", manner="설측(근사)", base="tt-alveolar-lateral(a)",
         why="받침·겹친 ㄹ의 설측음 [l] 목표. 모음 사이의 탄설음 [ɾ]은 같은 자리를 짧게 치는 움직임이라 "
             "정지 형상 하나로는 나타낼 수 없다."),
]
# 중립 자세(입모양 도식 VocalTract.jsx의 비심 8·14·15 자리). 발음 목표가 아니라 표시용이다.
NEUTRALS = [
    dict(id="schwa", ko="중립", ipa="ə", base="@", set={},
         why="혀·입술에 힘을 뺀 중립 모음 [ə]. ㅎ처럼 성도 모양이 뒤 모음을 따르는 소리의 자리에 쓴다."),
    dict(id="rest", ko="쉼", ipa="", base="@", set={"JA": -2.0, "LD": 0.0},
         why="[ə]의 혀에 턱을 VTL 중립값(JA -2°)으로 올리고 입술을 붙인(LD 0) 입 다문 쉼 자세."),
]
SKIPPED = [
    ("ㅎ", "성문 마찰음이라 혀·입술의 형상 목표가 따로 없다. 성도는 뒤 모음의 모양을 따르고 성문만 열린다."),
    ("ㅋ·ㅌ·ㅍ·ㅊ, ㄲ·ㄸ·ㅃ·ㅆ·ㅉ", "격음·경음은 조음 위치가 평음과 같고 차이는 성문(기식·긴장)에 있어 "
     "성도 단면으로는 평음과 같다."),
]

# 정중시상 윤곽: VTL SVG 내보내기의 폴리라인 14개 중 앞 7개. 나머지(혀 옆면 점선, 옆니 줄)는 뺀다.
PARTS = ["wall", "uvula", "upper", "larynx", "epiglottis", "lower", "tongue"]
PART_POINTS = [9, 8, 27, 5, 8, 25, 37]
# 폴리라인 안의 해부 구간(점 번호, 양끝 포함). 모든 형상에서 점 개수가 같아 번호가 고정된다.
SEGMENTS = {
    "velum": ["upper", 0, 6],        # 연구개(목젖 앞 구간)
    "palate": ["upper", 6, 12],      # 경구개(입천장)
    "upperTeeth": ["upper", 12, 18],  # 윗앞니
    "upperLip": ["upper", 18, 26],
    "floor": ["lower", 0, 12],        # 아래턱 안쪽(구강 바닥)
    "lowerTeeth": ["lower", 12, 16],
    "lowerLip": ["lower", 16, 24],
}
SVG_PX_PER_CM = 37.8
# 좌표 틀: x는 입술 쪽이 +, y는 아래가 +(SVG와 같음). 단위 0.01 cm 정수.
FRAME = dict(x0=-4.0, y0=2.6, unit=0.01)

# 격자
GRID_STEP_BARK = 0.5
LAYERS = [0, 1]                       # 0 입술 펴짐, 1 입술 둥글림

# 합성음
WAV_RATE = 16000
WAV_DUR = 0.6
WAV_RMS_DBFS = -20.0
WAV_PEAK_MAX = 0.89                   # 약 -1 dBFS
PRESSURE_RAMP_S = 0.03
FADE_S = 0.01

# 전달함수 포먼트
TF_N = 8192
TF_SR = 44100.0
TF_FMAX = 4500.0


# ── 공통 ────────────────────────────────────────────────────────────────────────────
def bark(f):
    """Traunmüller(1990) Bark 척도."""
    return 26.81 * f / (1960.0 + f) - 0.53


def r4(x):
    return float(round(float(x), 4))


class Vtl:
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
        self.const = vtl.get_constants()
        self.names = [p["name"] for p in vtl.get_param_info("tract")]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.info = {p["name"]: p for p in vtl.get_param_info("tract")}

    def shape(self, name):
        return np.asarray(vtl.get_shape(name, "tract"), dtype=np.float64).copy()

    def glottis(self, name="modal"):
        return np.asarray(vtl.get_shape(name, "glottis"), dtype=np.float64).copy()

    def formants(self, state):
        """전달함수(성문→입술 체적속도) 크기 스펙트럼의 극대점 앞 세 개. 포물선 보간으로 빈 사이를 메운다."""
        tf = vtl.tract_state_to_transfer_function(np.asarray(state, dtype=np.float64), n_spectrum_samples=TF_N,
                                                  save_phase_spectrum=False)
        mag = tf["magnitude_spectrum"]
        df = TF_SR / TF_N
        kmax = int(TF_FMAX / df)
        lv = 20.0 * np.log10(np.maximum(mag[:kmax + 2], 1e-12))
        peaks = []
        for k in range(2, kmax):
            if lv[k] > lv[k - 1] and lv[k] >= lv[k + 1]:
                a, b, c = lv[k - 1], lv[k], lv[k + 1]
                den = a - 2.0 * b + c
                off = 0.5 * (a - c) / den if den != 0 else 0.0
                f = (k + off) * df
                if f > 150.0:
                    peaks.append(f)
        if len(peaks) < 3:
            raise RuntimeError(f"포먼트 극대점이 3개 미만: {peaks}")
        return peaks[:3]

    def velum_area(self, state):
        return float(vtl.tract_state_to_tube_state(np.asarray(state, dtype=np.float64))["velum_opening"])

    def outline(self, state):
        """VTL SVG 내보내기를 읽어 폴리라인 7개를 FRAME 정수 좌표로 바꾼다."""
        fn = os.path.join(self.tmpdir, "tract.svg")
        vtl.tract_state_to_svg(np.asarray(state, dtype=np.float64), fn)
        with open(fn, encoding="utf-8") as f:
            txt = f.read()
        polys = re.findall(r'<polyline[^>]*points="([^"]*)"', txt)
        if len(polys) != 14:
            raise RuntimeError(f"SVG 폴리라인 수가 14가 아니다({len(polys)}). VTL 판본을 확인할 것")
        out = []
        for k, n_expect in enumerate(PART_POINTS):
            vals = [float(t) for t in polys[k].split()]
            if len(vals) != 2 * n_expect:
                raise RuntimeError(f"폴리라인 {k}의 점 수가 {len(vals) // 2}(기대 {n_expect})")
            flat = []
            for j in range(0, len(vals), 2):
                x_cm = vals[j] / SVG_PX_PER_CM
                y_cm = -vals[j + 1] / SVG_PX_PER_CM
                flat.append(int(round((x_cm - FRAME["x0"]) / FRAME["unit"])))
                flat.append(int(round((FRAME["y0"] - y_cm) / FRAME["unit"])))
            out.append(flat)
        return out


def load_targets():
    """backend/formants.py의 VOWEL_TARGETS를 읽고, VocalTractSimulator.jsx의 VOWELS와 같은지 확인한다."""
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    import formants as coach  # numpy만 쓰는 순수 모듈
    targets = {k: (int(v["f1"]), int(v["f2"]), int(v["round"])) for k, v in coach.VOWEL_TARGETS.items()}
    with open(SIM_JSX, encoding="utf-8") as f:
        jsx = f.read()
    jsx_vowels = {m[0]: (int(m[1]), int(m[2]), int(m[3])) for m in
                  re.findall(r"\{\s*ko:\s*'(.)',\s*f1:\s*(\d+),\s*f2:\s*(\d+),\s*round:\s*(\d)\s*\}", jsx)}
    if jsx_vowels != targets:
        raise SystemExit(f"목표값 불일치: formants.py {targets} / VocalTractSimulator.jsx {jsx_vowels}")
    return targets, coach


def in_band(f1, f2, t1, t2, coach):
    return (1 / coach._F1_TOL <= f1 / t1 <= coach._F1_TOL) and (1 / coach._F2_TOL <= f2 / t2 <= coach._F2_TOL)


# ── 모음·자음 형상 ──────────────────────────────────────────────────────────────────
def build_vowels(V, targets, coach):
    out = []
    for rec in VOWELS:
        p = np.zeros(len(V.names))
        for name, w in rec["base"]:
            p += w * V.shape(name)
        if rec.get("lips"):
            src = V.shape(rec["lips"])
            for n in ("LP", "LD"):
                p[V.idx[n]] = src[V.idx[n]]
        p = np.array([r4(x) for x in p])
        t1, t2, tr = targets[rec["ko"]]
        if tr != rec["round"]:
            raise SystemExit(f"{rec['ko']} 원순 여부가 목표값과 다르다")
        f_base = V.formants(p)
        edits = []
        if rec.get("fit") and not in_band(f_base[0], f_base[1], t1, t2, coach):
            spec = rec["fit"]
            j = V.idx[spec["param"]]
            for k in range(1, spec["max_steps"] + 1):
                q = p.copy()
                q[j] = r4(p[j] + k * spec["step"])
                fq = V.formants(q)
                if in_band(fq[0], fq[1], t1, t2, coach):
                    edits.append([spec["param"], r4(p[j]), r4(q[j])])
                    p = q
                    break
            else:
                raise SystemExit(f"{rec['ko']}: {spec['param']}를 옮겨도 판정 폭에 들어오지 않는다")
        f = V.formants(p)
        out.append(dict(rec=rec, params=p, f_base=f_base, f=f, edits=edits, target=(t1, t2)))
    return out


def build_consonants(V):
    out = []
    for rec in CONSONANTS:
        p = np.array([r4(x) for x in V.shape(rec["base"])])
        edits = []
        if rec.get("nasal"):
            j = V.idx["VO"]
            edits.append(["VO", r4(p[j]), r4(NASAL_VO)])
            p[j] = r4(NASAL_VO)
        out.append(dict(rec=rec, params=p, edits=edits))
    return out


def build_neutrals(V):
    out = []
    for rec in NEUTRALS:
        p = np.array([r4(x) for x in V.shape(rec["base"])])
        edits = []
        for name, val in rec["set"].items():
            j = V.idx[name]
            edits.append([name, r4(p[j]), r4(val)])
            p[j] = r4(val)
        out.append(dict(rec=rec, params=p, edits=edits))
    return out


# ── 격자(들로네 삼각분할 + 무게중심 보간) ────────────────────────────────────────────
def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _in_circle(p, a, b, c):
    if _orient(a, b, c) < 0:
        b, c = c, b
    ax, ay = a[0] - p[0], a[1] - p[1]
    bx, by = b[0] - p[0], b[1] - p[1]
    cx, cy = c[0] - p[0], c[1] - p[1]
    det = ((ax * ax + ay * ay) * (bx * cy - cx * by) - (bx * bx + by * by) * (ax * cy - cx * ay)
           + (cx * cx + cy * cy) * (ax * by - bx * ay))
    return det > 1e-12


def delaunay(pts):
    """Bowyer-Watson. 점 8개 규모라 단순 구현으로 충분하다. 결과는 정렬해 결정론을 지킨다."""
    n = len(pts)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    big = 100.0 * max(max(xs) - min(xs), max(ys) - min(ys))
    allp = list(pts) + [(cx - 2 * big, cy - big), (cx + 2 * big, cy - big), (cx, cy + 2 * big)]
    tris = [(n, n + 1, n + 2)]
    for i in range(n):
        p = allp[i]
        bad = [t for t in tris if _in_circle(p, allp[t[0]], allp[t[1]], allp[t[2]])]
        edges = {}
        for t in bad:
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                key = tuple(sorted(e))
                edges[key] = edges.get(key, 0) + 1
        tris = [t for t in tris if t not in bad]
        for (a, b), cnt in sorted(edges.items()):
            if cnt == 1:
                tris.append((a, b, i))
    tris = [tuple(sorted(t)) for t in tris if max(t) < n]
    return sorted(set(tris))


def convex_hull(pts):
    """Andrew monotone chain. 반시계 방향 꼭짓점 번호."""
    order = sorted(range(len(pts)), key=lambda i: (pts[i][0], pts[i][1]))
    lower, upper = [], []
    for i in order:
        while len(lower) >= 2 and _orient(pts[lower[-2]], pts[lower[-1]], pts[i]) <= 0:
            lower.pop()
        lower.append(i)
    for i in reversed(order):
        while len(upper) >= 2 and _orient(pts[upper[-2]], pts[upper[-1]], pts[i]) <= 0:
            upper.pop()
        upper.append(i)
    return lower[:-1] + upper[:-1]


def _area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def barycentric(p, a, b, c):
    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    l1 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / det
    l2 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / det
    return l1, l2, 1.0 - l1 - l2


def grid_nodes(anchor_pts, tris, step):
    """목표값 Bark 평면(x=Bark F2, y=Bark F1)의 격자점. 꼭짓점, 볼록 껍질 변 위의 점, 내부 격자점 순서."""
    hull = convex_hull(anchor_pts)
    nodes = []

    def add(p):
        for q in nodes:
            if math.hypot(p[0] - q[0], p[1] - q[1]) < 0.3 * step:
                return
        nodes.append((float(p[0]), float(p[1])))

    for p in anchor_pts:
        add(p)
    for k in range(len(hull)):
        a, b = anchor_pts[hull[k]], anchor_pts[hull[(k + 1) % len(hull)]]
        m = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
        for j in range(1, m):
            add((a[0] + (b[0] - a[0]) * j / m, a[1] + (b[1] - a[1]) * j / m))
    xs = [p[0] for p in anchor_pts]
    ys = [p[1] for p in anchor_pts]
    for yi in range(int(math.floor(min(ys) / step)), int(math.ceil(max(ys) / step)) + 1):
        for xi in range(int(math.floor(min(xs) / step)), int(math.ceil(max(xs) / step)) + 1):
            p = (xi * step, yi * step)
            if weights_at(p, anchor_pts, tris) is not None:
                add(p)
    return nodes, hull


def weights_at(p, anchor_pts, tris, eps=1e-9, clamp=False):
    """p를 담는 삼각형의 무게중심 좌표 {꼭짓점 번호: 무게}. 밖이면 None.
    clamp=True면 가장 가까운 삼각형을 골라 음수 무게를 0으로 자른다(껍질 변 위 점의 부동소수 오차용)."""
    best, best_t = None, None
    for t in tris:
        l = barycentric(p, anchor_pts[t[0]], anchor_pts[t[1]], anchor_pts[t[2]])
        if best is None or min(l) > min(best):
            best, best_t = l, t
    if best is None or (min(best) < -eps and not clamp):
        return None
    l = [max(0.0, x) for x in best]
    s = sum(l)
    return {best_t[k]: l[k] / s for k in range(3) if l[k] / s > 1e-9}


def build_grid(V, vowels):
    anchors = [(bark(v["target"][1]), bark(v["target"][0])) for v in vowels]
    tris = delaunay(anchors)
    hull_idx = convex_hull(anchors)
    hull_area = _area([anchors[i] for i in hull_idx])
    tri_area = sum(_area([anchors[t[0]], anchors[t[1]], anchors[t[2]]]) for t in tris)
    if abs(hull_area - tri_area) > 1e-6:
        raise RuntimeError(f"삼각분할이 볼록 껍질을 덮지 않는다({tri_area:.4f} / {hull_area:.4f})")
    nodes, hull = grid_nodes(anchors, tris, GRID_STEP_BARK)

    li, ldi = V.idx["LP"], V.idx["LD"]
    layer_lips = {}
    for layer in LAYERS:
        native = [v["params"] for v in vowels if v["rec"]["round"] == layer]
        layer_lips[layer] = (r4(np.mean([p[li] for p in native])), r4(np.mean([p[ldi] for p in native])))

    states = []
    for layer in LAYERS:
        verts = []
        for v in vowels:
            p = v["params"].copy()
            if v["rec"]["round"] != layer:
                p[li], p[ldi] = layer_lips[layer]
            verts.append(p)
        for node in nodes:
            w = weights_at(node, anchors, tris, clamp=True)
            p = np.zeros(len(V.names))
            for k, wk in sorted(w.items()):
                p += wk * verts[k]
            p = np.array([r4(x) for x in p])
            f = V.formants(p)
            nominal = (_inv_bark(node[1]), _inv_bark(node[0]))
            states.append(dict(layer=layer, w=w, params=p, f=f, nominal=nominal, outline=V.outline(p)))
    return dict(anchors=anchors, tris=tris, hull=hull, nodes=nodes, layer_lips=layer_lips, states=states)


def _inv_bark(z):
    return 1960.0 * (z + 0.53) / (26.28 - z)


# ── 합성음 ──────────────────────────────────────────────────────────────────────────
def synth_vowel(V, params):
    """성도 형상을 고정하고 성문 'modal'(F0 120 Hz)로 WAV_DUR초 발성. 폐압을 30 ms 동안 올리고 내려
    시작·끝의 딸깍 소리를 막는다."""
    c = V.const
    glot = V.glottis("modal")
    n = int(round(WAV_DUR * c["sr_internal"])) + 1
    tract = np.tile(params, (n, 1))
    g = np.tile(glot, (n, 1))
    ramp = int(round(PRESSURE_RAMP_S * c["sr_internal"]))
    pr = glot[1]                                   # 폐압(dPa)
    g[:ramp, 1] = np.linspace(0.0, pr, ramp)
    g[-ramp:, 1] = np.linspace(pr, 0.0, ramp)
    y = np.asarray(vtl.synth_block(tract, g), dtype=np.float64)
    # 44.1 kHz → 16 kHz: 양끝이 0으로 끝나도록 페이드한 뒤 FFT 절단 리샘플링(formants.py와 같은 방식)
    y = _fade(y, int(FADE_S * c["sr_audio"]))
    n_out = int(round(len(y) * WAV_RATE / c["sr_audio"]))
    spec = np.fft.rfft(y)
    bins = n_out // 2 + 1
    spec_out = np.zeros(bins, dtype=complex)
    m = min(len(spec), bins)
    spec_out[:m] = spec[:m]
    z = np.fft.irfft(spec_out, n_out) * (n_out / len(y))
    z = _fade(z, int(FADE_S * WAV_RATE))
    rms = float(np.sqrt(np.mean(z * z)))
    gain = (10 ** (WAV_RMS_DBFS / 20.0)) / max(rms, 1e-12)
    peak = float(np.max(np.abs(z))) * gain
    if peak > WAV_PEAK_MAX:
        gain *= WAV_PEAK_MAX / peak
    pcm = np.clip(np.round(z * gain * 32767.0), -32768, 32767).astype("<i2")
    return pcm


def _fade(y, n):
    y = y.copy()
    if n > 1:
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(n) / n)
        y[:n] *= w
        y[-n:] *= w[::-1]
    return y


def wav_bytes(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(WAV_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# ── 출력 ────────────────────────────────────────────────────────────────────────────
def dump_compact(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def dump_pretty(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def frame_json():
    return dict(x0=FRAME["x0"], y0=FRAME["y0"], unit=FRAME["unit"],
                note="x: 입술 쪽이 +, y: 아래가 +. 정수 좌표 × unit(cm) = 실제 거리")


def write_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build-date", required=True, help="meta.json에 적을 빌드 날짜(YYYY-MM-DD). 결정론을 위해 인자로 받는다")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report", default=None, help="비교표(markdown)를 쓸 경로. 없으면 표준출력만")
    args = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.build_date):
        ap.error("--build-date는 YYYY-MM-DD")

    targets, coach = load_targets()
    with tempfile.TemporaryDirectory() as tmp:
        V = Vtl(tmp)
        vowels = build_vowels(V, targets, coach)
        consonants = build_consonants(V)
        neutrals = build_neutrals(V)
        grid = build_grid(V, vowels)
        for item in vowels + consonants + neutrals:
            item["outline"] = V.outline(item["params"])
            item["velum"] = V.velum_area(item["params"])
        wavs = {}
        for v in vowels:
            pcm = synth_vowel(V, v["params"])
            wavs[v["rec"]["id"]] = pcm
            est = coach.estimate_formants(pcm.astype(np.float64) / 32768.0, WAV_RATE)
            v["lpc"] = est
            t1, t2 = v["target"]
            v["lpc_ok"] = bool(est) and in_band(est["f1"], est["f2"], t1, t2, coach)

    files = {}
    # 1) shapes.json
    phonemes = []
    for v in vowels:
        rec = v["rec"]
        phonemes.append(dict(
            id=rec["id"], ko=rec["ko"], ipa=rec["ipa"], kind="vowel", round=rec["round"],
            source=" + ".join(f"{w:g}×{n}" if w != 1 else n for n, w in rec["base"]) + (f", 입술 {rec['lips']}" if rec.get("lips") else ""),
            why=rec["why"], edits=v["edits"],
            f=[int(round(x)) for x in v["f"]], target=list(v["target"]),
            velum=round(v["velum"], 3), wav=f"vowels/{rec['id']}.wav",
            p=[r4(x) for x in v["params"]], o=v["outline"]))
    for c in consonants:
        rec = c["rec"]
        phonemes.append(dict(
            id=rec["id"], ko=rec["ko"], ipa=rec["ipa"], kind="consonant", place=rec["place"], manner=rec["manner"],
            nasal=bool(rec.get("nasal")), pair=rec.get("pair"), source=rec["base"], why=rec["why"], edits=c["edits"],
            velum=round(c["velum"], 3), p=[r4(x) for x in c["params"]], o=c["outline"]))
    for nt in neutrals:
        rec = nt["rec"]
        phonemes.append(dict(
            id=rec["id"], ko=rec["ko"], ipa=rec["ipa"], kind="neutral", source=rec["base"], why=rec["why"],
            edits=nt["edits"], velum=round(nt["velum"], 3), p=[r4(x) for x in nt["params"]], o=nt["outline"]))
    shapes = dict(schema=SCHEMA, frame=frame_json(), parts=PARTS, segments=SEGMENTS, params=V.names,
                  phonemes=phonemes, skipped=[dict(ko=k, why=w) for k, w in SKIPPED])
    files["shapes.json"] = write_file(os.path.join(args.out, "shapes.json"), dump_compact(shapes))

    # 2) vowel_grid.json
    vowel_ids = [v["rec"]["id"] for v in vowels]
    anchors = [dict(id=v["rec"]["id"], ko=v["rec"]["ko"], round=v["rec"]["round"], target=list(v["target"]),
                    vtl=[int(round(v["f"][0])), int(round(v["f"][1]))]) for v in vowels]
    gstates = []
    for s in grid["states"]:
        gstates.append(dict(
            f=[int(round(x)) for x in s["f"]], r=s["layer"],
            a=[int(round(s["nominal"][0])), int(round(s["nominal"][1]))],
            w=[[k, round(wk, 3)] for k, wk in sorted(s["w"].items())],
            o=s["outline"]))
    grid_json = dict(
        schema=SCHEMA, frame=frame_json(), parts=PARTS, segments=SEGMENTS, scale="bark",
        note=("f: 이 성도 상태의 VTL 전달함수 포먼트[F1,F2,F3] Hz. r: 입술 층(0 펴짐, 1 둥글림). "
              "a: 격자를 만든 앱 목표값 평면의 명목 좌표[F1,F2] Hz. w: 모음 꼭짓점 번호와 무게. o: 윤곽"),
        vowels=anchors, triangles=[list(t) for t in grid["tris"]],
        layerLips={str(k): dict(LP=vv[0], LD=vv[1]) for k, vv in grid["layer_lips"].items()},
        step=GRID_STEP_BARK, states=gstates)
    files["vowel_grid.json"] = write_file(os.path.join(args.out, "vowel_grid.json"), dump_compact(grid_json))

    # 3) vowels/*.wav
    for vid in vowel_ids:
        files[f"vowels/{vid}.wav"] = write_file(os.path.join(args.out, "vowels", f"{vid}.wav"), wav_bytes(wavs[vid]))

    # 4) meta.json
    with open(vtl.speaker_path(), "rb") as f:
        speaker_sha = hashlib.sha256(f.read()).hexdigest()
    meta = dict(
        schema=SCHEMA, buildDate=args.build_date, generator="scripts/vtl_build_assets.py",
        vtl=dict(api=vtl.get_version().strip(), binding=f"vocaltractlab-cython {metadata.version('vocaltractlab_cython')}",
                 speaker=vtl.DEFAULT_SPEAKER, speakerSha256=speaker_sha, glottisModel="Geometric glottis (JD3 기본)",
                 glottisShape="modal", audioRateHz=V.const["sr_audio"], stateRateHz=round(V.const["sr_internal"], 4)),
        wav=dict(rateHz=WAV_RATE, seconds=WAV_DUR, rmsDbfs=WAV_RMS_DBFS, note="모음마다 RMS를 같게 맞췄다(피크 -1 dBFS 이하)"),
        formants=dict(method="tract_state_to_transfer_function 크기 스펙트럼 극대점", nSpectrum=TF_N,
                      targetsFrom="backend/formants.py VOWEL_TARGETS (VocalTractSimulator.jsx VOWELS와 같음)"),
        grid=dict(step=GRID_STEP_BARK, nodesPerLayer=len(grid["nodes"]), layers=LAYERS, states=len(grid["states"])),
        license=("VocalTractLab(Copyright Peter Birkholz)과 vocaltractlab-cython(Paul Krug)은 GPL-3.0이다. "
                 "이 폴더의 파일은 그 프로그램을 오프라인에서 실행해 얻은 좌표·포먼트·파형과 JD3 화자 파일의 "
                 "형상 파라미터 값이며, 앱은 VTL 코드를 포함하거나 호출하지 않는다. 빌드 스크립트는 GPL-3.0-or-later."),
        attribution=["Birkholz, P. VocalTractLab. https://www.vocaltractlab.de",
                     "Krug, P. vocaltractlab-cython. https://github.com/paul-krug/vocaltractlab-cython"],
        files={k: files[k] for k in sorted(files)})
    files["meta.json"] = write_file(os.path.join(args.out, "meta.json"), dump_pretty(meta))

    report = make_report(V, vowels, consonants + neutrals, grid, files, coach)
    print(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)


def make_report(V, vowels, consonants, grid, files, coach):
    L = []
    L.append(f"VTL {vtl.get_version().strip()}, 화자 {vtl.DEFAULT_SPEAKER}, 격자 {len(grid['nodes'])}점 × {len(LAYERS)}층")
    L.append("")
    L.append("| 모음 | 출발 형상 | 보정 | VTL F1/F2/F3 (Hz) | 목표 F1/F2 | F1 비 | F2 비 | Bark 거리 | 판정 폭 | 합성음 LPC F1/F2 | 코치 판정 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for v in vowels:
        rec = v["rec"]
        t1, t2 = v["target"]
        f = v["f"]
        src = " + ".join(f"{w:g}×{n}" if w != 1 else n for n, w in rec["base"]) + (f", 입술 {rec['lips']}" if rec.get("lips") else "")
        if v["edits"]:
            e = v["edits"][0]
            ed = f"{e[0]} {e[1]:+.2f}→{e[2]:+.2f} ({e[2] - e[1]:+.2f}); 보정 전 {v['f_base'][0]:.0f}/{v['f_base'][1]:.0f}"
        else:
            ed = "없음"
        d = math.hypot(bark(f[0]) - bark(t1), bark(f[1]) - bark(t2))
        lpc = v["lpc"]
        L.append(f"| {rec['ko']} | {src} | {ed} | {f[0]:.0f}/{f[1]:.0f}/{f[2]:.0f} | {t1}/{t2} | {f[0] / t1:.2f} | "
                 f"{f[1] / t2:.2f} | {d:.2f} | {'안' if in_band(f[0], f[1], t1, t2, coach) else '밖'} | "
                 f"{lpc['f1']:.0f}/{lpc['f2']:.0f} | {'통과' if v['lpc_ok'] else '벗어남'} |")
    L.append("")
    L.append("| 자음·중립 | 출발 형상 | 보정 | 연구개 통로(cm²) |")
    L.append("|---|---|---|---|")
    for c in consonants:
        rec = c["rec"]
        ed = ", ".join(f"{e[0]} {e[1]:+.2f}→{e[2]:+.2f}" for e in c["edits"]) or "없음"
        L.append(f"| {rec['ko']} | {rec['base']} | {ed} | {c['velum']:.2f} |")
    L.append("")
    ko = [v["rec"]["ko"] for v in vowels]
    L.append("삼각형: " + ", ".join("-".join(ko[i] for i in t) for t in grid["tris"]))
    L.append("볼록 껍질: " + " → ".join(ko[i] for i in grid["hull"]))
    L.append(f"입술 층 기본값: " + ", ".join(f"층{k} LP {a:.3f} LD {b:.3f}" for k, (a, b) in grid["layer_lips"].items()))
    for layer in LAYERS:
        fs = np.array([s["f"][:2] for s in grid["states"] if s["layer"] == layer])
        L.append(f"층{layer}: F1 {fs[:, 0].min():.0f}~{fs[:, 0].max():.0f} Hz, F2 {fs[:, 1].min():.0f}~{fs[:, 1].max():.0f} Hz")
    # 격자 상태의 VTL 포먼트가, 그 상태를 만든 명목 좌표(앱 목표값 평면)를 모음 대응으로 옮긴 위치와 얼마나
    # 가까운지. 꼭짓점 입술이 제 층과 같은 상태(펴짐 층의 평순 모음 사이, 둥글림 층의 ㅗ·ㅜ 사이)만 센다.
    A = [(bark(v["target"][0]), bark(v["target"][1])) for v in vowels]
    Vv = [(bark(v["f"][0]), bark(v["f"][1])) for v in vowels]
    errs = []
    for s in grid["states"]:
        if sum(wk for k, wk in s["w"].items() if vowels[k]["rec"]["round"] == s["layer"]) < 0.999:
            continue
        q = (bark(s["nominal"][0]), bark(s["nominal"][1]))
        wq = warp(q, A, Vv)
        errs.append(math.hypot(wq[0] - bark(s["f"][0]), wq[1] - bark(s["f"][1])))
    errs = np.array(errs)
    L.append(f"명목 좌표→VTL 옮김 오차(Bark, {len(errs)}상태): 중앙값 {np.median(errs):.2f}, "
             f"90% {np.percentile(errs, 90):.2f}, 최대 {errs.max():.2f}")
    L.append("")
    L.append("| 파일 | 바이트 |")
    L.append("|---|---|")
    for k in sorted(files):
        L.append(f"| {k} | {files[k]['bytes']} |")
    L.append(f"| 합계 | {sum(x['bytes'] for x in files.values())} |")
    return "\n".join(L) + "\n"


def warp(q, A, Vv, power=2.0):
    """앱 목표값 좌표 q(Bark F1, F2)를 VTL 좌표로 옮긴다. 모음 대응 변위의 역거리 제곱 가중 평균(Shepard).
    프론트 lib/vtlShapes.js의 warpToVtl과 같은 식."""
    num = [0.0, 0.0]
    den = 0.0
    for a, v in zip(A, Vv):
        d = math.hypot(q[0] - a[0], q[1] - a[1])
        if d < 1e-9:
            return v
        w = 1.0 / d ** power
        num[0] += w * (v[0] - a[0])
        num[1] += w * (v[1] - a[1])
        den += w
    return (q[0] + num[0] / den, q[1] + num[1] / den)


if __name__ == "__main__":
    main()
