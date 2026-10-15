#!/usr/bin/env python
"""
개방형 타이핑 답 자동 채점 검증(P20) 도구: 표본 뽑기, 사람 채점표 내보내기, 일치도 분석(docs/pilot/typed-scoring-check.md 5·6절, 10절).

자동 채점은 backend/phoneme_accuracy.py의 strict_phoneme_accuracy(지금 strict-v2)다. 이 스크립트는 그 함수를 부르기만 하고,
앱 화면 채점(scoring.calculate_score)과 받아쓰기 판정(sentence_feedback)은 쓰지 않는다.

  # 1) 가명 내보내기(GET /api/pilot/export, 판 5 이상)에서 표본 200개 + 연습 20개 + 경계 사례 30개를 뽑아 채점표를 만든다
  python scripts/typed_scoring_check.py sample export.json --out p20/ [--n 200] [--seed 20261015] [--layers sentence] [--modality real]

  # 2) 채점자 두 사람이 rater_sheet_A.csv·rater_sheet_B.csv를 채운 뒤(발음 열쇠는 key_sheet.csv)
  python scripts/typed_scoring_check.py analyze p20/ --a p20/rater_sheet_A.csv --b p20/rater_sheet_B.csv [--keys p20/key_sheet.csv]

  # (시험) 가짜 내보내기와 가짜 채점으로 끝까지 돌려 본다. 판정에 쓰지 않는다
  python scripts/typed_scoring_check.py demo --out /tmp/p20demo

sample이 만드는 파일(--out 폴더)
  rater_sheet_A.csv, rater_sheet_B.csv  채점자에게 주는 표. 표본 id, 정답 문장, 친 답, 어절 수만 있고 자동 점수·층(점수 구간)·참여자는 없다.
                                        두 표는 행 순서가 다르다(순서 효과를 나누려고). 채점자가 채울 칸: 맞은 음소 수, 정답 음소 수,
                                        맞은 어절 수, 자리 바뀜(0·1), 메모
  practice_sheet.csv                    연습용 20개(표본에 없는 답). 같은 칸
  boundary_sheet.csv                    경계 사례 30개(일부러 만든 답, 판정에서 뺀다). '경우' 칸이 더 있다
  key_sheet.csv                         표본·연습·경계에 나오는 정답 문장마다 한 줄. 발음 열쇠(표준 발음법)와 정답 음소 수를 사람이 적는다.
                                        자동 채점의 발음열은 넣지 않는다(문서 4절)
  operator_key.csv                      운영자만 보는 열쇠. 표본 id마다 참여자 가명·회차·문항·점수 구간·자동 점수·앱 점수
  boundary_key.csv                      경계 사례의 자동 점수(운영자용)
  manifest.json                         시드, 내보내기 sha256, 대상 수, 구간 경계, 참여자별 몫, 빈 답 수, 경고

CSV는 엑셀에서 한글이 깨지지 않게 UTF-8 BOM(utf-8-sig)으로 쓴다. 읽을 때는 BOM이 있어도 없어도 된다.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from phoneme_accuracy import SCORER_VERSION, strict_phoneme_accuracy  # noqa: E402

TOOL_VERSION = "p20-tool-1"
DEFAULT_SEED = 20261015
N_STRATA = 5
PERSON_CAP = 0.30      # 한 사람 답이 표본에서 차지할 수 있는 몫(문서 5절 2항)
MAX_BLANK = 10         # 빈 답 상한(문서 5절 2항)
PASS_ICC = 0.90        # 주지표 점추정 기준(master-plan P20)
PASS_ICC_LO = 0.85     # 제안: 95% 구간 하한
PASS_BIAS = 0.02       # 제안: 평균 차이 절댓값 2%p
RATER_ICC_MIN = 0.90   # 채점자끼리 이보다 낮으면 판정을 미룬다(문서 6절)
DISAGREE = 0.03        # 원인 분류에 넣는 차이(문서 7절 1항, 3%p)

# 채점표 칸 이름(채점자가 보는 머리글)
C_ID, C_TARGET, C_ANSWER = "표본id", "정답 문장", "친 답"
C_NW = "어절 수"
C_MATCH, C_NT, C_WC, C_SWAP, C_MEMO = "맞은 음소 수", "정답 음소 수", "맞은 어절 수", "자리 바뀜(0/1)", "메모"
C_CASE = "경우"
RATER_COLS = [C_ID, C_TARGET, C_ANSWER, C_NW, C_MATCH, C_NT, C_WC, C_SWAP, C_MEMO]
KEY_COLS = ["문장id", C_TARGET, "발음 열쇠(표준 발음)", "정답 음소 수", "어절 수", "만든 사람", "메모"]

_BLANK_RE = re.compile(r"[\s\W_]+", re.UNICODE)

# 경계 사례 30개(문서 5절 3항). 규칙 대조용이고 ICC에는 넣지 않는다. (경우, 정답, 답)
BOUNDARY_CASES = [
    ("띄어쓰기", "옷 입어요", "옷입어요"),
    ("띄어쓰기", "학교에 가요", "학 교에가요"),
    ("띄어쓰기", "밥을 먹었어요", "밥을먹었 어요"),
    ("전각 공백", "옷 입어요", "옷　입어요"),
    ("줄 바꿈 없는 공백", "같이 가요", "같이 가요"),
    ("탭", "물 주세요", "물\t주세요"),
    ("쉼표", "네, 알겠어요", "네 알겠어요"),
    ("쉼표", "오늘 비가 와요", "오늘, 비가 와요."),
    ("문장 부호", "뭐 먹을래?", "뭐 먹을래"),
    ("낱자", "밥 먹었어", "밥 먹었ㅇ"),
    ("낱자", "사과 주세요", "ㅅㅏ과 주세요"),
    ("낱자", "고마워요", "고마ㅝ요"),
    ("숫자", "세 시에 만나요", "3시에 만나요"),
    ("숫자", "두 개 주세요", "2개 주세요"),
    ("숫자", "십 분만 기다려요", "10분만 기다려요"),
    ("영문", "커피 주세요", "coffee 주세요"),
    ("영문", "안녕하세요", "hello"),
    ("순서 바뀜", "학교에 가요", "가요 학교에"),
    ("순서 바뀜", "내일 만나요", "만나요 내일"),
    ("순서 바뀜", "빨리 와 주세요", "와 주세요 빨리"),
    ("덧붙임", "학교에 가요", "학교에 가요 학교에 가요"),
    ("덧붙임", "물 주세요", "찬물 좀 주세요"),
    ("덧붙임", "고마워요", "정말 고마워요 친구야"),
    ("발음대로 쓴 답", "같이 가요", "가치 가요"),
    ("발음대로 쓴 답", "닭이 울어요", "달기 울어요"),
    ("발음대로 쓴 답(낱말 경계)", "옷 입어요", "오디버요"),
    ("오타", "사과 주세요", "사과 주세여"),
    ("같은 입모양 대치", "밥 주세요", "맙 주세요"),
    ("빈 답", "오늘 날씨가 좋아요", ""),
    ("'모름'", "오늘 날씨가 좋아요", "모름"),
]


# ───────────────────────── 공통 ─────────────────────────
def is_blank(answer) -> bool:
    """빈 답: 공백·문장 부호를 지우면 아무것도 없다(화면의 '모르겠어요'는 빈 답으로 보낸다)."""
    return not _BLANK_RE.sub("", unicodedata.normalize("NFC", answer or ""))


def score(target: str, answer: str, loose_jamo: str = "drop") -> dict:
    return strict_phoneme_accuracy(target or "", answer or "", loose_jamo=loose_jamo)


def n_words(target: str) -> int:
    return score(target, "")["n_words"]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


# ───────────────────────── 1. 대상 모으기 ─────────────────────────
def collect(export: dict, layers=("sentence",), modality="real", loose_jamo="drop"):
    """내보내기에서 개방형 답을 모은다. 같은 참여자·회차·문항이 두 번 나오면(이어서 한 층 등) 처음 것만 쓴다."""
    out, seen = [], set()
    for p in export.get("participants") or []:
        pid = p.get("pid")
        for s in p.get("battery") or []:
            if s.get("layer") not in layers:
                continue
            for r in s.get("open") or []:
                if modality != "any" and (r.get("modality") or s.get("modality")) != modality:
                    continue
                target = r.get("target")
                if not target or r.get("answer_text") is None:
                    continue
                key = (pid, s.get("session_label"), s.get("layer"), r.get("item_id"))
                if key in seen:
                    continue
                seen.add(key)
                res = score(target, r.get("answer_text"), loose_jamo)
                out.append({
                    "pid": pid, "session_label": s.get("session_label"), "layer": s.get("layer"),
                    "form": s.get("form"), "modality": r.get("modality") or s.get("modality"),
                    "item_id": r.get("item_id"), "seq": r.get("seq"), "target": target, "answer_text": r.get("answer_text"),
                    "blank": is_blank(r.get("answer_text")),
                    "auto_phoneme_acc": res["phoneme_accuracy"], "n_matched_phonemes": res["n_matched_phonemes"],
                    "n_target_phonemes": res["n_target_phonemes"], "auto_word_acc": res["word_accuracy"],
                    "n_words_correct": res["n_words_correct"], "n_words": res["n_words"],
                    "n_loose_jamo": res["n_loose_jamo"], "n_extra_syllables": res["n_extra_syllables"],
                    "app_score": r.get("app_score"), "stored_auto_phoneme_acc": r.get("auto_phoneme_acc"),
                    "stored_scorer_version": r.get("scorer_version"),
                })
    return out


# ───────────────────────── 2. 표본 ─────────────────────────
def stratify(rows, rng, k=N_STRATA):
    """자동 엄격 음소 정답률 순위로 k개 층을 같은 크기로 나눈다. 같은 점수(1.0 등)가 많아 분위수 경계가 겹치므로
    같은 점수끼리는 시드로 섞은 순서를 쓴다. 분모가 0인 답(정답에 음소가 없음)은 빼지 않고 0으로 둔다."""
    order = list(range(len(rows)))
    rng.shuffle(order)
    order.sort(key=lambda i: rows[i]["auto_phoneme_acc"] or 0.0)
    n = len(order)
    cuts = []
    for s in range(k):
        lo, hi = (s * n) // k, ((s + 1) * n) // k
        for i in order[lo:hi]:
            rows[i]["stratum"] = s + 1
        if hi > lo:
            vals = [rows[i]["auto_phoneme_acc"] or 0.0 for i in order[lo:hi]]
            cuts.append({"stratum": s + 1, "n": hi - lo, "min": round(min(vals), 4), "max": round(max(vals), 4)})
    return cuts


def draw_sample(rows, n=200, seed=DEFAULT_SEED, person_cap=PERSON_CAP, max_blank=MAX_BLANK, k=N_STRATA):
    """문서 5절 2항: 층마다 n/k개씩, 한 사람 ≤ person_cap, 빈 답 ≤ max_blank. 대상이 n개 이하면 모두 쓴다(경고).
    층이 다 차지 않으면 가까운 층의 남은 답으로 채운다(manifest의 shortfall에 남는다)."""
    rng = random.Random(seed)
    cuts = stratify(rows, rng, k)
    warnings = []
    if len(rows) <= n:
        chosen = list(range(len(rows)))
        warnings.append(f"대상 {len(rows)}개가 {n}개 이하라 모두 쓴다. 문서 5절 2항대로 두 번째 리허설로 채운다")
        cnt = Counter(rows[i]["pid"] for i in chosen)
        if chosen and max(cnt.values()) > person_cap * len(chosen):
            warnings.append(f"한 사람 몫이 {max(cnt.values()) / len(chosen):.0%}로 {person_cap:.0%}를 넘는다")
        nb = sum(rows[i]["blank"] for i in chosen)
        if nb > max_blank:
            warnings.append(f"빈 답 {nb}개가 {max_blank}개를 넘는다")
        return chosen, cuts, warnings, {}
    cap = int(math.floor(person_cap * n))
    per = {s: [] for s in range(1, k + 1)}
    for i, r in enumerate(rows):
        per[r["stratum"]].append(i)
    for s in per:
        rng.shuffle(per[s])
    taken, by_pid, n_blank = [], Counter(), 0
    used = set()
    quota = {s: n // k + (1 if s <= n % k else 0) for s in range(1, k + 1)}
    got = Counter()

    def ok(i):
        r = rows[i]
        return i not in used and by_pid[r["pid"]] < cap and (not r["blank"] or n_blank < max_blank)

    def take(i, s):
        nonlocal n_blank
        used.add(i)
        taken.append(i)
        by_pid[rows[i]["pid"]] += 1
        n_blank += rows[i]["blank"]
        got[s] += 1

    for s in range(1, k + 1):
        for i in per[s]:
            if got[s] >= quota[s]:
                break
            if ok(i):
                take(i, s)
    shortfall = {s: quota[s] - got[s] for s in quota if got[s] < quota[s]}
    for s, short in sorted(shortfall.items()):
        for d in range(1, k):
            for s2 in (s - d, s + d):
                if s2 not in per:
                    continue
                for i in per[s2]:
                    if short == 0:
                        break
                    if ok(i):
                        take(i, s)   # 모자란 층의 몫으로 센다(실제 층은 operator_key의 stratum)
                        short -= 1
            if short == 0:
                break
        if short:
            warnings.append(f"층 {s}를 {short}개 채우지 못했다(한 사람·빈 답 상한 때문)")
    if shortfall:
        warnings.append("모자란 층을 이웃 층으로 채웠다: " + ", ".join(f"층 {s} {v}개" for s, v in sorted(shortfall.items())))
    return taken, cuts, warnings, shortfall


def draw_practice(rows, chosen, n=20, seed=DEFAULT_SEED):
    rest = [i for i in range(len(rows)) if i not in set(chosen) and not rows[i]["blank"]]
    rng = random.Random(seed + 1)
    rng.shuffle(rest)
    return rest[:n]


def sample(export_path, out, n=200, n_practice=20, seed=DEFAULT_SEED, layers=("sentence",), modality="real",
           loose_jamo="drop", export=None):
    if export is None:
        with open(export_path, encoding="utf-8") as f:
            export = json.load(f)
    if (export.get("version") or 0) < 5:
        raise SystemExit("판 5 이상의 가명 내보내기가 필요하다(battery가 없음)")
    rows = collect(export, layers=layers, modality=modality, loose_jamo=loose_jamo)
    if not rows:
        raise SystemExit("고른 층·조건에 개방형 답이 없다")
    chosen, cuts, warnings, shortfall = draw_sample(rows, n=n, seed=seed)
    practice = draw_practice(rows, chosen, n=n_practice, seed=seed)
    if len(practice) < n_practice:
        warnings.append(f"연습용 답이 {len(practice)}개뿐이다({n_practice}개 목표)")
    os.makedirs(out, exist_ok=True)

    # 표본 id는 무작위 순서로 매겨 id에 층·참여자 정보가 남지 않게 한다
    rng = random.Random(seed + 2)
    ids = list(chosen)
    rng.shuffle(ids)
    sid = {i: f"T{j + 1:03d}" for j, i in enumerate(ids)}
    order_a, order_b = list(ids), list(ids)
    random.Random(seed + 3).shuffle(order_a)
    random.Random(seed + 4).shuffle(order_b)

    def sheet_row(i, rid):
        r = rows[i]
        return {C_ID: rid, C_TARGET: r["target"], C_ANSWER: r["answer_text"], C_NW: r["n_words"],
                C_MATCH: "", C_NT: "", C_WC: "", C_SWAP: "", C_MEMO: ""}

    write_csv(os.path.join(out, "rater_sheet_A.csv"), RATER_COLS, [sheet_row(i, sid[i]) for i in order_a])
    write_csv(os.path.join(out, "rater_sheet_B.csv"), RATER_COLS, [sheet_row(i, sid[i]) for i in order_b])
    write_csv(os.path.join(out, "practice_sheet.csv"), RATER_COLS,
              [sheet_row(i, f"P{j + 1:02d}") for j, i in enumerate(practice)])

    brows = []
    for j, (case, t, a) in enumerate(BOUNDARY_CASES):
        res = score(t, a, loose_jamo)
        brows.append({C_ID: f"B{j + 1:02d}", C_CASE: case, C_TARGET: t, C_ANSWER: a, C_NW: res["n_words"],
                      C_MATCH: "", C_NT: "", C_WC: "", C_SWAP: "", C_MEMO: "",
                      "auto_n_matched": res["n_matched_phonemes"], "auto_n_target": res["n_target_phonemes"],
                      "auto_phoneme_acc": res["phoneme_accuracy"], "auto_n_words_correct": res["n_words_correct"],
                      "n_loose_jamo": res["n_loose_jamo"]})
    write_csv(os.path.join(out, "boundary_sheet.csv"), [C_ID, C_CASE] + RATER_COLS[1:], brows)
    write_csv(os.path.join(out, "boundary_key.csv"),
              [C_ID, C_CASE, C_TARGET, C_ANSWER, "auto_n_matched", "auto_n_target", "auto_phoneme_acc",
               "auto_n_words_correct", C_NW, "n_loose_jamo"], brows)

    # 발음 열쇠 표: 정답 문장마다 한 줄(표본·연습·경계)
    targets = []
    for i in ids + practice:
        if rows[i]["target"] not in targets:
            targets.append(rows[i]["target"])
    for _c, t, _a in BOUNDARY_CASES:
        if t not in targets:
            targets.append(t)
    write_csv(os.path.join(out, "key_sheet.csv"), KEY_COLS,
              [{"문장id": f"S{j + 1:03d}", C_TARGET: t, C_NW: n_words(t)} for j, t in enumerate(targets)])

    op_cols = ["sample_id", "pid", "session_label", "layer", "form", "modality", "item_id", "seq", "stratum", "blank",
               "auto_phoneme_acc", "n_matched_phonemes", "n_target_phonemes", "auto_word_acc", "n_words_correct", "n_words",
               "n_loose_jamo", "n_extra_syllables", "app_score", "stored_auto_phoneme_acc", "stored_scorer_version",
               "order_A", "order_B", "target", "answer_text"]
    pos_a = {i: j + 1 for j, i in enumerate(order_a)}
    pos_b = {i: j + 1 for j, i in enumerate(order_b)}
    op = [dict(rows[i], sample_id=sid[i], order_A=pos_a[i], order_B=pos_b[i], blank=int(rows[i]["blank"])) for i in ids]
    op += [dict(rows[i], sample_id=f"P{j + 1:02d}", order_A="", order_B="", blank=int(rows[i]["blank"]))
           for j, i in enumerate(practice)]
    write_csv(os.path.join(out, "operator_key.csv"), op_cols, op)

    stored_diff = sum(1 for i in ids if rows[i]["stored_auto_phoneme_acc"] is not None
                      and abs(rows[i]["stored_auto_phoneme_acc"] - (rows[i]["auto_phoneme_acc"] or 0)) > 1e-6)
    if stored_diff:
        warnings.append(f"내보내기에 저장된 auto_phoneme_acc와 지금 다시 계산한 값이 {stored_diff}개 다르다(채점 판본 확인)")
    by_pid = Counter(rows[i]["pid"] for i in ids)
    manifest = {
        "tool": TOOL_VERSION, "scorer_version": SCORER_VERSION, "loose_jamo": loose_jamo, "seed": seed,
        "export_sha256": file_sha256(export_path) if export_path and os.path.exists(export_path) else None,
        "export_version": export.get("version"), "layers": list(layers), "modality": modality,
        "n_eligible": len(rows), "n_sample": len(ids), "n_practice": len(practice), "n_boundary": len(BOUNDARY_CASES),
        "n_targets": len(targets), "strata": cuts,
        "sample_by_stratum": dict(sorted(Counter(rows[i]["stratum"] for i in ids).items())),
        "shortfall": shortfall, "n_blank": sum(rows[i]["blank"] for i in ids),
        "max_person_share": round(max(by_pid.values()) / len(ids), 4) if ids else None, "n_people": len(by_pid),
        "person_cap": PERSON_CAP, "max_blank": MAX_BLANK, "warnings": warnings,
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return manifest


# ───────────────────────── 3. 분석 ─────────────────────────
def icc_a1(x):
    """x: n×k 목록. ICC(A,1) 이원 무선, 절대 일치, 단일 측정(McGraw·Wong 1996 / Shrout·Fleiss ICC(2,1)).
    scripts/scoring_analyses_1006.py의 icc_a1과 같은 식이다(numpy 없이)."""
    n = len(x)
    k = len(x[0]) if n else 0
    if n < 2 or k < 2:
        return None
    gm = sum(sum(r) for r in x) / (n * k)
    rm = [sum(r) / k for r in x]
    cm = [sum(x[i][j] for i in range(n)) / n for j in range(k)]
    msr = k * sum((m - gm) ** 2 for m in rm) / (n - 1)
    msc = n * sum((m - gm) ** 2 for m in cm) / (k - 1)
    sse = sum((x[i][j] - rm[i] - cm[j] + gm) ** 2 for i in range(n) for j in range(k))
    mse = sse / ((n - 1) * (k - 1))
    den = msr + (k - 1) * mse + k * (msc - mse) / n
    return (msr - mse) / den if den > 0 else None


def boot_icc(x, B=2000, seed=0):
    """응답 재표집 부트스트랩 95% 구간(백분위). 점수가 모두 같은 표본은 건너뛴다."""
    if len(x) < 3:
        return None, None
    rng = random.Random(seed)
    vals = []
    n = len(x)
    for _ in range(B):
        v = icc_a1([x[rng.randrange(n)] for _ in range(n)])
        if v is not None:
            vals.append(v)
    if len(vals) < B // 2:
        return None, None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((v - ma) ** 2 for v in a))
    sb = math.sqrt(sum((v - mb) ** 2 for v in b))
    if not sa or not sb:
        return None
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (sa * sb)


def bland_altman(auto, ref):
    d = [a - r for a, r in zip(auto, ref)]
    m = [(a + r) / 2 for a, r in zip(auto, ref)]
    n = len(d)
    if n < 2:
        return None
    md = sum(d) / n
    sd = math.sqrt(sum((v - md) ** 2 for v in d) / (n - 1))
    return {"mean_diff": md, "sd_diff": sd, "loa_low": md - 1.96 * sd, "loa_high": md + 1.96 * sd,
            "r_diff_mean": _pearson(d, m)}


def _int(v, what, rid, errors, allow_blank=False):
    s = (v or "").strip()
    if not s:
        if not allow_blank:
            errors.append(f"{rid}: '{what}'이 비어 있다")
        return None
    try:
        x = float(s)
    except ValueError:
        errors.append(f"{rid}: '{what}' 값 '{s}'가 숫자가 아니다")
        return None
    if x < 0 or x != int(x):
        errors.append(f"{rid}: '{what}' 값 '{s}'는 0 이상의 정수여야 한다")
        return None
    return int(x)


def read_rater(path, ids):
    """채점표를 읽어 {표본id: {m, n, wc, nw, swap, memo}}. 칸이 비었거나 맞은 수 > 정답 수면 오류 목록에 넣는다."""
    out, errors = {}, []
    for r in read_csv(path):
        rid = (r.get(C_ID) or "").strip()
        if rid not in ids:
            continue
        m = _int(r.get(C_MATCH), C_MATCH, rid, errors)
        nt = _int(r.get(C_NT), C_NT, rid, errors)
        wc = _int(r.get(C_WC), C_WC, rid, errors, allow_blank=True)
        nw = _int(r.get(C_NW), C_NW, rid, errors, allow_blank=True)
        sw = _int(r.get(C_SWAP), C_SWAP, rid, errors, allow_blank=True)
        if m is not None and nt is not None and m > nt:
            errors.append(f"{rid}: 맞은 음소 수 {m} > 정답 음소 수 {nt}")
        if wc is not None and nw is not None and wc > nw:
            errors.append(f"{rid}: 맞은 어절 수 {wc} > 어절 수 {nw}")
        out[rid] = {"m": m, "n": nt, "wc": wc, "nw": nw, "swap": sw, "memo": (r.get(C_MEMO) or "").strip()}
    missing = sorted(set(ids) - set(out))
    if missing:
        errors.append(f"{os.path.basename(path)}에 없는 표본 {len(missing)}개: {', '.join(missing[:10])}")
    return out, errors


def _prop(m, n):
    return (m / n) if (m is not None and n) else (0.0 if (m == 0 and n == 0) else None)


def _icc_block(rows, B, seed):
    """rows: [(auto, a, b)] 비율. 주지표·채점자끼리·자동 대 각 채점자·블랜드-알트먼."""
    auto = [r[0] for r in rows]
    mean_ab = [(r[1] + r[2]) / 2 for r in rows]
    main = [[a, m] for a, m in zip(auto, mean_ab)]
    lo, hi = boot_icc(main, B=B, seed=seed)
    raters = [[r[1], r[2]] for r in rows]
    rlo, rhi = boot_icc(raters, B=B, seed=seed + 1)
    return {
        "n": len(rows),
        "icc_auto_vs_mean": icc_a1(main), "ci95": [lo, hi],
        "icc_raters": icc_a1(raters), "icc_raters_ci95": [rlo, rhi],
        "icc_auto_vs_A": icc_a1([[r[0], r[1]] for r in rows]), "icc_auto_vs_B": icc_a1([[r[0], r[2]] for r in rows]),
        "bland_altman": bland_altman(auto, mean_ab),
        "mean_auto": sum(auto) / len(auto) if auto else None, "mean_raters": sum(mean_ab) / len(mean_ab) if mean_ab else None,
    }


def judge(block):
    """문서 6절 판정. 채점자끼리가 0.90 미만이면 '보류'."""
    if not block or block.get("icc_auto_vs_mean") is None:
        return "판정 불가", ["ICC를 계산할 수 없다(표본이 너무 작거나 점수가 모두 같다)"]
    notes = []
    if block["icc_raters"] is not None and block["icc_raters"] < RATER_ICC_MIN:
        return "보류", [f"채점자끼리 ICC {block['icc_raters']:.3f} < {RATER_ICC_MIN}: 규칙 설명을 보강해 다시 채점(문서 6·7절)"]
    icc, lo = block["icc_auto_vs_mean"], block["ci95"][0]
    ba = block["bland_altman"] or {}
    ok_main = icc >= PASS_ICC
    ok_lo = lo is not None and lo >= PASS_ICC_LO
    ok_bias = ba.get("mean_diff") is not None and abs(ba["mean_diff"]) <= PASS_BIAS
    notes.append(f"주지표 ICC {icc:.3f} ({'≥' if ok_main else '<'} {PASS_ICC})")
    notes.append(f"구간 하한 {lo:.3f} ({'≥' if ok_lo else '<'} {PASS_ICC_LO}, 제안)" if lo is not None else "구간 하한 계산 불가")
    if ba.get("mean_diff") is not None:
        notes.append(f"평균 차이 {ba['mean_diff'] * 100:+.2f}%p ({'≤' if ok_bias else '>'} 2%p, 제안)")
    if ok_main and ok_lo and ok_bias:
        return "통과", notes
    if ok_main:
        return "통과(주지표만, 제안 조건 미달)", notes
    return "미달", notes


def analyze(folder, a_path, b_path, keys_path=None, B=2000, seed=0):
    op = [r for r in read_csv(os.path.join(folder, "operator_key.csv")) if r["sample_id"].startswith("T")]
    ids = [r["sample_id"] for r in op]
    A, ea = read_rater(a_path, ids)
    Bm, eb = read_rater(b_path, ids)
    errors = [f"A {e}" for e in ea] + [f"B {e}" for e in eb]
    if errors:
        return {"errors": errors}
    resp, word_rows, sess = [], [], defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    disagree, rater_gap, swaps = [], [], 0
    for r in op:
        rid = r["sample_id"]
        auto = float(r["auto_phoneme_acc"]) if r["auto_phoneme_acc"] not in ("", None) else 0.0
        pa, pb = _prop(A[rid]["m"], A[rid]["n"]), _prop(Bm[rid]["m"], Bm[rid]["n"])
        if pa is None or pb is None:
            continue
        resp.append((auto, pa, pb))
        mean_ab = (pa + pb) / 2
        if abs(auto - mean_ab) > DISAGREE:
            res = score(r["target"], r["answer_text"])
            disagree.append({"sample_id": rid, "target": r["target"], "answer_text": r["answer_text"],
                             "auto": round(auto, 4), "rater_A": round(pa, 4), "rater_B": round(pb, 4),
                             "diff_auto_minus_mean": round(auto - mean_ab, 4), "auto_n_target": r["n_target_phonemes"],
                             "A_n_target": A[rid]["n"], "B_n_target": Bm[rid]["n"], "n_loose_jamo": r["n_loose_jamo"],
                             "auto_alignment": " | ".join(f"{w['word']}:{w['key']}/{w['answer']}" for w in res["alignment"]),
                             "memo_A": A[rid]["memo"], "memo_B": Bm[rid]["memo"], "cause": ""})
        if abs(pa - pb) > DISAGREE:
            rater_gap.append({"sample_id": rid, "target": r["target"], "answer_text": r["answer_text"],
                              "A": f"{A[rid]['m']}/{A[rid]['n']}", "B": f"{Bm[rid]['m']}/{Bm[rid]['n']}",
                              "memo_A": A[rid]["memo"], "memo_B": Bm[rid]["memo"], "consensus_m": "", "consensus_n": ""})
        swaps += int(bool(A[rid]["swap"]) or bool(Bm[rid]["swap"]))
        nw = int(r["n_words"]) if r["n_words"] else 0
        if nw and A[rid]["wc"] is not None and Bm[rid]["wc"] is not None:
            word_rows.append((int(r["n_words_correct"]) / nw, A[rid]["wc"] / nw, Bm[rid]["wc"] / nw))
        s = sess[(r["pid"], r["session_label"])]
        s[0] += int(r["n_matched_phonemes"] or 0)
        s[1] += int(r["n_target_phonemes"] or 0)
        s[2] += A[rid]["m"]
        s[3] += A[rid]["n"]
        s[4] += Bm[rid]["m"]
        s[5] += Bm[rid]["n"]
    sess_rows = [(v[0] / v[1], v[2] / v[3], v[4] / v[5]) for v in sess.values() if v[1] and v[3] and v[5]]
    main = _icc_block(resp, B, seed)
    verdict, notes = judge(main)
    out = {
        "tool": TOOL_VERSION, "scorer_version": SCORER_VERSION, "n_sample": len(ids), "n_scored": len(resp),
        "response_level": main, "verdict": verdict, "verdict_notes": notes,
        "session_level": _icc_block(sess_rows, B, seed + 10) if len(sess_rows) >= 3 else {"n": len(sess_rows)},
        "word_accuracy": _icc_block(word_rows, B, seed + 20) if len(word_rows) >= 3 else {"n": len(word_rows)},
        "n_disagree_auto": len(disagree), "n_disagree_raters": len(rater_gap), "n_swapped_order": swaps,
    }
    write_csv(os.path.join(folder, "disagreements.csv"), list(disagree[0].keys()) if disagree else ["sample_id"], disagree)
    write_csv(os.path.join(folder, "rater_disagreements.csv"),
              list(rater_gap[0].keys()) if rater_gap else ["sample_id"], rater_gap)
    if keys_path:
        out["key_mismatch"] = key_mismatch(keys_path)
    with open(os.path.join(folder, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=lambda v: round(v, 6) if isinstance(v, float) else v)
    return out


def key_mismatch(keys_path):
    """발음 열쇠 표의 사람 정답 음소 수와 자동 채점 분모(n_target_phonemes)가 다른 문장(문서 4절 '따로 목록')."""
    out = []
    for r in read_csv(keys_path):
        t = r.get(C_TARGET) or ""
        h = (r.get("정답 음소 수") or "").strip()
        if not t or not h:
            continue
        auto_n = score(t, "")["n_target_phonemes"]
        try:
            hn = int(float(h))
        except ValueError:
            continue
        if hn != auto_n:
            out.append({"sentence_id": r.get("문장id"), "target": t, "human_key": r.get("발음 열쇠(표준 발음)"),
                        "human_n": hn, "auto_n": auto_n})
    return out


# ───────────────────────── 4. 시험(demo) ─────────────────────────
def _typo(rng, text):
    """가짜 답: 음절 하나를 지우거나, 받침·모음을 바꾸거나, 띄어쓰기를 바꾼다(실제 답 분포가 아니다)."""
    s = list(text)
    pos = [i for i, ch in enumerate(s) if "가" <= ch <= "힣"]
    if not pos:
        return text
    op = rng.random()
    i = rng.choice(pos)
    code = ord(s[i]) - 0xAC00
    cho, jung, jong = code // 588, (code % 588) // 28, code % 28
    if op < 0.25:
        del s[i]
    elif op < 0.5:
        s[i] = chr(0xAC00 + cho * 588 + jung * 28 + rng.choice([0, 4, 8, 16, 17]))
    elif op < 0.75:
        s[i] = chr(0xAC00 + rng.randrange(19) * 588 + jung * 28 + jong)
    else:
        s[i] = chr(0xAC00 + cho * 588 + rng.randrange(21) * 28 + jong)
    return "".join(s).replace(" ", "") if rng.random() < 0.3 else "".join(s)


def fake_export(seed=1, n_people=8, n_items=40):
    rng = random.Random(seed)
    base = ["오늘 날씨가 좋아요", "학교에 같이 가요", "밥을 먹었어요", "물 좀 주세요", "내일 다시 만나요", "버스를 타고 왔어요",
            "창문을 닫아 주세요", "옷 입어요", "닭이 울어요", "세 시에 만나요"]
    parts = []
    for p in range(n_people):
        skill = rng.random()
        opened = []
        for j in range(n_items):
            t = base[j % len(base)]
            r = rng.random()
            if r < 0.04:
                a = ""
            elif r < 0.25 + 0.6 * skill:
                a = t if rng.random() < 0.6 else t.replace(" ", "")
            else:
                a = t
                for _ in range(1 + int(rng.random() * 3)):
                    a = _typo(rng, a)
            opened.append({"seq": j, "item_id": f"s{j:02d}", "modality": "real", "target": t, "answer_text": a})
        parts.append({"pid": f"p{p:02d}", "battery": [{"session_label": "A1", "layer": "sentence", "modality": "real",
                                                      "form": "A", "open": opened}]})
    return {"version": 7, "participants": parts}


def fake_raters(folder, seed=2, noise=0.04):
    """가짜 채점: 자동 값 근처(정답 음소 수는 자동 분모, 맞은 수에 잡음). 도구가 끝까지 도는지만 본다."""
    op = {r["sample_id"]: r for r in read_csv(os.path.join(folder, "operator_key.csv"))}
    for name, sd in (("A", seed), ("B", seed + 1)):
        rng = random.Random(sd)
        rows = read_csv(os.path.join(folder, f"rater_sheet_{name}.csv"))
        for r in rows:
            o = op[r[C_ID]]
            n, m = int(o["n_target_phonemes"]), int(o["n_matched_phonemes"])
            m2 = max(0, min(n, m + (rng.choice([-1, 1]) if rng.random() < noise * n else 0)))
            r[C_MATCH], r[C_NT] = m2, n
            r[C_WC] = o["n_words_correct"]
            r[C_SWAP] = 0
        write_csv(os.path.join(folder, f"rater_sheet_{name}.csv"), RATER_COLS, rows)


# ───────────────────────── 출력 ─────────────────────────
def _fmt(v, nd=3):
    return "—" if v is None else f"{v:.{nd}f}"


def print_manifest(m):
    print(f"대상 {m['n_eligible']}개 → 표본 {m['n_sample']}개(층별 {m['sample_by_stratum']}), 연습 {m['n_practice']}개, "
          f"경계 {m['n_boundary']}개, 정답 문장 {m['n_targets']}개")
    print(f"참여자 {m['n_people']}명, 한 사람 최대 몫 {m['max_person_share']}, 빈 답 {m['n_blank']}개, 채점기 {m['scorer_version']}"
          f"(낱자 {m['loose_jamo']}), 시드 {m['seed']}")
    for w in m["warnings"]:
        print("  경고:", w)


def print_analysis(r):
    if r.get("errors"):
        print("채점표 오류(분석하지 않음):")
        for e in r["errors"][:40]:
            print("  ", e)
        return
    m = r["response_level"]
    ba = m["bland_altman"] or {}
    print(f"응답 {r['n_scored']}개 · 판정: {r['verdict']}")
    for n in r["verdict_notes"]:
        print("  ", n)
    print(f"  자동 대 두 채점자 평균 ICC(A,1) {_fmt(m['icc_auto_vs_mean'])} [{_fmt(m['ci95'][0])}, {_fmt(m['ci95'][1])}]")
    print(f"  채점자끼리 {_fmt(m['icc_raters'])} [{_fmt(m['icc_raters_ci95'][0])}, {_fmt(m['icc_raters_ci95'][1])}], "
          f"자동 대 A {_fmt(m['icc_auto_vs_A'])}, 자동 대 B {_fmt(m['icc_auto_vs_B'])}")
    if ba:
        print(f"  평균 차이(자동 − 사람) {ba['mean_diff'] * 100:+.2f}%p, 95% 일치 한계 [{ba['loa_low'] * 100:+.1f}, "
              f"{ba['loa_high'] * 100:+.1f}]%p, 차이와 평균의 상관 {_fmt(ba['r_diff_mean'])}")
    s = r["session_level"]
    if s.get("icc_auto_vs_mean") is not None:
        print(f"  회차 수준({s['n']}개) ICC {_fmt(s['icc_auto_vs_mean'])}")
    w = r["word_accuracy"]
    if w.get("icc_auto_vs_mean") is not None:
        print(f"  낱말 정답률({w['n']}개) ICC {_fmt(w['icc_auto_vs_mean'])}")
    print(f"  3%p 넘게 다른 응답: 자동 대 사람 {r['n_disagree_auto']}개(disagreements.csv), 채점자끼리 {r['n_disagree_raters']}개, "
          f"자리 바뀜 표시 {r['n_swapped_order']}개")
    if r.get("key_mismatch") is not None:
        print(f"  발음 열쇠와 자동 분모가 다른 문장 {len(r['key_mismatch'])}개")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("export")
    s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--practice", type=int, default=20)
    s.add_argument("--seed", type=int, default=DEFAULT_SEED)
    s.add_argument("--layers", default="sentence", help="쉼표로 여러 층(sentence,av,snr)")
    s.add_argument("--modality", default="real", help="real·avatar·A·AV 또는 any")
    s.add_argument("--loose-jamo", default="drop", choices=("drop", "compose"))
    a = sub.add_parser("analyze")
    a.add_argument("folder")
    a.add_argument("--a", required=True)
    a.add_argument("--b", required=True)
    a.add_argument("--keys")
    a.add_argument("--boot", type=int, default=2000)
    d = sub.add_parser("demo")
    d.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "sample":
        m = sample(args.export, args.out, n=args.n, n_practice=args.practice, seed=args.seed,
                   layers=tuple(x.strip() for x in args.layers.split(",") if x.strip()), modality=args.modality,
                   loose_jamo=args.loose_jamo)
        print_manifest(m)
    elif args.cmd == "analyze":
        r = analyze(args.folder, args.a, args.b, keys_path=args.keys, B=args.boot)
        print_analysis(r)
        if r.get("errors"):
            sys.exit(1)
    else:
        os.makedirs(args.out, exist_ok=True)
        ex = fake_export()
        p = os.path.join(args.out, "fake_export.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ex, f, ensure_ascii=False)
        m = sample(p, args.out)
        print_manifest(m)
        fake_raters(args.out)
        r = analyze(args.out, os.path.join(args.out, "rater_sheet_A.csv"), os.path.join(args.out, "rater_sheet_B.csv"), B=500)
        print("(가짜 자료 — 판정에 쓰지 않는다)")
        print_analysis(r)


if __name__ == "__main__":
    main()
