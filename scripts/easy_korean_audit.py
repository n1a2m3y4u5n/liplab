#!/usr/bin/env python
"""
쉬운 한국어·용어 감사(C15, docs/idea-sweep-2026-10-03.md 다7, docs/easy-korean-audit.md).

선천성·조기 청력 손실 학습자에게 한국어 글은 제2언어이거나 읽기 수준이 낮을 수 있다. 화면에 보이는 한국어 문자열을 모아
문장 길이와 어휘 등급으로 채점한다.

  · 문자열 모으기
      프론트엔드: frontend/src의 .js·.jsx(테스트·개발자 화면 제외). JSX 글과 문자열 리터럴을 scripts/easy_korean_extract.mjs
                  (Babel 구문 분석)로 뽑는다. 주석·import·객체 키·비교 값·console·Error 인자·className 같은 비표시 속성은 뺀다.
      백엔드:     학습자에게 나가는 것만 파일별 규칙으로(BACKEND_RULES). 말하기·커리큘럼 안내(title·desc·guide·look·teach …),
                  피드백·코칭 문장(함수 안의 반환·조건식 문자열), main.py의 오류 안내(detail=), llm_service.py의 코칭 대체 문장.
                  LLM 프롬프트는 학습자가 읽지 않아 채점하지 않고, 출력 문체 지시만 따로 목록으로 낸다(prompt_style_rules).
  · 채점(문자열마다)
      문장 길이: 문장(줄바꿈·. ! ? 경계)마다 한글 음절 수. 30음절 넘는 문장이 있으면 실패.
      어휘: kiwipiepy 형태소 분석으로 내용어(일반 명사·동사·형용사·부사·관형사·어근·대명사·외국 글자)를 원형으로 바꿔 국립국어원
            「한국어 학습용 어휘 목록」(scripts/data/nikl_learner_vocab.tsv, A·B·C 등급)에서 찾는다. 고유 명사는 세지 않는다.
            A·B가 아닌 낱말(C 등급과 목록에 없는 낱말)이 내용어의 10%를 넘으면 실패.
      용어: 학습자에게 보이면 안 되는 전문 용어(JARGON)와 결손 중심 표현(DEFICIT)을 따로 표시한다(통과 판정에는 넣지 않음).
  · 판정(2026-10-09부터, docs/easy-korean-rebase-2026-10.md 7절): 세 층 기준. 낱말 결정표(scripts/data/easy_korean_termbook.json)에서
      결정 안 된 낱말 0개, 이름표(버튼·탭·제목) 95%가 어려운 말 0개, 문장형은 화면(파일) 단위 쉬운 말 덮기 95% 이상인 파일 90%와
      30음절 이하 95%. 계산은 scripts/easy_korean_rebase.py의 layers()이고 요약의 "layers"에 나온다.
      예전 엄격 통과율(A·B만, 문자열마다 10%, 목표 95%)은 숫자가 이어지게 pass_rate로 계속 낸다.

  python scripts/easy_korean_audit.py                 # 요약 출력
  python scripts/easy_korean_audit.py --json out.json # 문자열별 결과
  python scripts/easy_korean_audit.py --baseline docs/easy-korean-audit-baseline.json   # 고치기 전 기준선 저장(최악 80개 포함)
  python scripts/easy_korean_audit.py --doc           # docs/easy-korean-audit.md 다시 쓰기(기준선·고쳐 쓰기 표를 읽음)

의존성: kiwipiepy(형태소 분석, backend/requirements-gen.txt), Node(추출기, frontend/node_modules의 @babel/parser).
wordfreq가 있으면 목록에 없는 낱말의 빈도(zipf)를 참고로 붙인다. 목록 파일 다시 만들기: --build-vocab <xls>(xlrd 필요).
"""
import argparse
import ast
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
FRONT = os.path.join(ROOT, "frontend", "src")
BACK = os.path.join(ROOT, "backend")
VOCAB_TSV = os.path.join(_HERE, "data", "nikl_learner_vocab.tsv")
REWRITES = os.path.join(_HERE, "data", "easy_korean_rewrites.json")
DOC = os.path.join(ROOT, "docs", "easy-korean-audit.md")
BASELINE = os.path.join(ROOT, "docs", "easy-korean-audit-baseline.json")

MAX_SYL = 30            # 한 문장 음절 상한
MAX_HARD = 0.10         # A·B가 아닌 내용어 비율 상한
TARGET = 0.95           # 통과 문자열 비율 목표

# 개발자·운영자·연구용 화면(학습자에게 안 보임)
FRONT_EXCLUDE = {
    "pages/DevViseme.jsx",      # /dev-viseme 개발용 입모양 검사
    "pages/CueVideoDemo.jsx",   # /lab/cue-video 연구용 데모
    "pages/ContentReview.jsx",  # /admin/content-review 운영자 검수(LIPLAB_REVIEW=1일 때만)
    "config/team.js",           # 개발자 소개(소속·수상명 같은 고유 명사 자료)
}
OWNED_ELSEWHERE = {"pages/Practice.jsx"}   # 다른 작업이 맡은 파일. 채점은 하되 고쳐 쓰기는 제안만

# 백엔드 파일별 학습자 문자열 규칙.
#   keys:  이 키의 사전 값만(문자열·f-문자열)
#   func:  함수 안의 문자열(독스트링·print·raise·로그 제외, 낱말 목록 제외)
#   detail: HTTPException(detail=...) 등 detail= 키워드
#   except_in: 이 함수의 except 블록 안 문자열만(LLM 실패 시 대체 문장)
BACKEND_RULES = {
    "curriculum.py": {"keys": {"name", "look", "teach", "title", "desc", "hint", "note"}},
    "speak_curriculum.py": {"keys": {"title", "desc", "guide", "prompt"}, "func": True},
    "articulation.py": {"keys": {"guide"}, "func": True},
    "formants.py": {"func": True},
    "scoring.py": {"keys": {"message", "tip", "feedback"}, "func": True},
    "main.py": {"detail": True, "keys": {"message", "note"}},
    "llm_service.py": {"except_in": {"generate_speaking_coaching"}},
}
FUNC_SKIP_CALLS = {"print", "RuntimeError", "ValueError", "KeyError", "TypeError", "Exception", "warn", "warning",
                   "debug", "info", "error", "exception", "log", "getenv", "get", "startswith", "endswith", "split",
                   "replace", "compile", "match", "search", "sub", "findall", "fullmatch", "strip", "join", "index", "count"}
DICT_SKIP_KEYS = {"word", "target", "answer", "a", "b", "place", "manner", "kind", "drill", "icon", "display", "mode",
                  "label", "sound", "jamo", "text"}

# 학습자에게 보이면 안 되는 전문 용어(설명 없이 나오면 표시). 말하기 단계처럼 가르치는 말로 쓰는 곳도 표시는 하되 판정은 사람이 한다.
JARGON = ["비심", "viseme", "숙달 추정", "이동 평균", "판별", "음소", "포먼트", "동구형이음", "양순음", "치경음", "연구개음",
          "경구개음", "성문음", "전설모음", "전설 모음", "원순모음", "원순 모음", "중설모음", "중설 모음", "개방모음", "개방 모음",
          "후설", "파열음", "파찰음", "유음", "비음", "조음", "연구개", "경구개", "치경", "성문", "양순", "D-GOP", "GOP", "AUC",
          "정규화", "신뢰구간", "표준편차", "백분위", "가중", "EWMA", "혼동행렬", "혼동 행렬", "최소대립쌍", "최소대립", "강제정렬",
          "기식", "동시조음", "정밀도", "재현율", "우연 보정", "효과크기", "효과 크기", "유의", "회귀", "분산", "중앙값", "추정치",
          "지각공간", "MDS", "CER", "WER", "F0", "기본주파수", "피치", "dB"]
DEFICIT = ["정상 발화", "정상인", "정상 화자", "정상 청력", "장애를 극복", "교정"]
# 앱이 직접 가르치는 핵심 말(보조 통과율에서만 쉬운 말로 친다). 1단계·말하기 단계에서 뜻을 보여 주고 쓰는 말이다.
CORE_TAUGHT = {"입모양", "받침", "자음", "모음", "음절", "억양", "수어", "독화", "자막", "아바타", "웹캠", "마이크", "첫소리",
               "끝소리", "가운데소리", "복습", "단계", "레슨"}
# 화면 전체에 되풀이되는 UI 용어와 쉬운 대안(국립국어원 등급). 바꾸면 앱 전체 이름표가 바뀌는 제품 결정이라 적용하지 않고,
# 바꿨다고 칠 때의 통과율만 계산한다(문서 2절).
UI_TERM_SWAPS = {
    "문항": "문제(A)", "완료": "끝(A)", "입력": "쓰기·적기(A)", "불러오다": "가져오다(A)", "오답": "틀린 문제(A·B)",
    "저장": "남기기(B)", "삭제": "지우기(A)", "재생": "보기·틀기", "화자": "말하는 사람(A)", "항목": "것·줄(A)",
    "진행": "하기(A)", "획득": "받기(A)", "레벨": "등급", "건너뛰다": "넘어가다(A)", "마크": "표시",
}
SL_OK = {"LIPLAB", "DOKA", "AI", "OK", "PC", "AA"}   # 서비스·마스코트 이름(고유 명사)과 흔한 약어

HANGUL = re.compile(r"[가-힣]")
CONTENT_TAGS = {"NNG", "NNP", "VV", "VA", "VX", "MAG", "MM", "XR", "NP", "SL", "VV-I", "VA-I", "VV-R", "VA-R", "VX-I", "VX-R"}
POS_OF = {"NNG": "명", "NNP": "명", "NP": "대", "VV": "동", "VX": "보", "VA": "형", "MAG": "부", "MM": "관", "XR": "명"}


# ── 어휘 목록 ─────────────────────────────────────────────────────────────────
def build_vocab(xls_path):
    import xlrd
    s = xlrd.open_workbook(xls_path).sheet_by_index(0)
    best = {}
    for r in range(1, s.nrows):
        _rank, word, pos, _orig, grade = s.row_values(r)
        k = (re.sub(r"\d+$", "", word.strip()), pos)
        if k not in best or grade < best[k]:
            best[k] = grade
    with open(VOCAB_TSV, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 국립국어원 「한국어 학습용 어휘 목록」(2003, 5,965개) 등급표에서 낱말·품사·등급만 옮김(같은 형태의 동형어는 가장 쉬운 등급).\n")
        f.write("# 출처: 국립국어원 https://www.korean.go.kr/front/etcData/etcDataView.do?mn_id=46&etc_seq=71 (공공누리 제1유형, 출처 표시)\n")
        f.write("# 다시 만들기: python scripts/easy_korean_audit.py --build-vocab 한국어학습용어휘목록.xls (xlrd 필요)\n")
        f.write("word\tpos\tgrade\n")
        for (w, p), g in sorted(best.items()):
            f.write(f"{w}\t{p}\t{g}\n")
    print(f"{len(best)}개 → {VOCAB_TSV}")


def load_vocab():
    grade = {}
    with open(VOCAB_TSV, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or line.startswith("word\t"):
                continue
            w, _p, g = line.rstrip("\n").split("\t")
            if w not in grade or g < grade[w]:
                grade[w] = g
    return grade


# ── 추출 ──────────────────────────────────────────────────────────────────────
def front_files():
    out = []
    for p in sorted(glob.glob(os.path.join(FRONT, "**", "*.js*"), recursive=True)):
        rel = os.path.relpath(p, FRONT).replace(os.sep, "/")
        if not re.search(r"\.(js|jsx)$", rel) or ".test." in rel or rel in FRONT_EXCLUDE:
            continue
        out.append(p)
    return out


def extract_front():
    files = front_files()
    raw = subprocess.run(["node", os.path.join(_HERE, "easy_korean_extract.mjs"), *files],
                         capture_output=True, text=True, check=True).stdout
    items = []
    for x in json.loads(raw):
        if "error" in x:
            print("구문 분석 실패:", x["file"], x["error"], file=sys.stderr)
            continue
        rel = "frontend/src/" + os.path.relpath(x["file"], FRONT).replace(os.sep, "/")
        items.append({"file": rel, "line": x["line"], "kind": x["kind"], "text": x["text"]})
    return items


def _fstring_text(node):
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            parts.append("○")
    return "".join(parts)


def _str_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _fstring_text(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):   # "가" + "나" 이어 붙임
        a, b = _str_of(node.left), _str_of(node.right)
        if a is not None or b is not None:
            return (a or "○") + (b or "○")
    return None


def extract_back():
    items = []
    for fname, rule in BACKEND_RULES.items():
        path = os.path.join(BACK, fname)
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        parent = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parent[c] = n
        seen = set()

        def add(node, kind):
            s = _str_of(node)
            if s is None or not HANGUL.search(s) or id(node) in seen:
                return
            if "운영자" in s:
                return                            # 운영자 전용 안내(검수 기능·파일럿 내보내기)
            for sub in ast.walk(node):
                seen.add(id(sub))
            items.append({"file": f"backend/{fname}", "line": node.lineno, "kind": kind,
                          "text": re.sub(r"\s+", " ", s).strip()})

        def top_str(n):   # 이어 붙인 문자열·f-문자열의 가장 바깥 노드
            while isinstance(parent.get(n), (ast.JoinedStr, ast.BinOp, ast.FormattedValue)):
                n = parent[n]
            return n

        def in_func(n):
            p = parent.get(n)
            while p is not None:
                if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return p
                p = parent.get(p)
            return None

        def skip_call(n):
            p = parent.get(n)
            for _ in range(4):
                if p is None:
                    return False
                if isinstance(p, ast.Call):
                    f = p.func
                    name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                    if name in FUNC_SKIP_CALLS:
                        return True
                if isinstance(p, (ast.Raise, ast.Assert)):
                    return True
                p = parent.get(p)
            return False

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and HANGUL.search(node.value)):
                continue
            top = top_str(node)
            par = parent.get(top)
            if isinstance(par, ast.Expr):            # 독스트링·떠 있는 문자열
                continue
            if rule.get("keys") and isinstance(par, ast.Dict) and top in par.values:
                k = par.keys[par.values.index(top)]
                if isinstance(k, ast.Constant) and k.value in rule["keys"]:
                    add(top, f"dict:{k.value}")
                continue
            if rule.get("detail") and isinstance(par, ast.keyword) and par.arg == "detail":
                add(top, "detail")
                continue
            if rule.get("except_in"):
                f = in_func(top)
                if f is not None and f.name in rule["except_in"]:
                    p = parent.get(top)
                    while p is not None and p is not f:
                        if isinstance(p, ast.ExceptHandler):
                            if not skip_call(top):
                                add(top, "fallback")
                            break
                        p = parent.get(p)
                continue
            if rule.get("func") and in_func(top) is not None:
                if isinstance(par, ast.Dict) and (top not in par.values):
                    continue                          # 사전 키
                if isinstance(par, ast.Dict):
                    k = par.keys[par.values.index(top)]
                    if isinstance(k, ast.Constant) and k.value in DICT_SKIP_KEYS:
                        continue
                if isinstance(par, ast.Compare) or isinstance(par, ast.Subscript) or skip_call(top):
                    continue
                s = _str_of(top) or ""
                if not re.search(r"\s|[.!?]", s.strip()):
                    continue                          # 낱말 하나(자모·음절 목록·키 값)
                add(top, "func")
            elif rule.get("func") and isinstance(par, (ast.Tuple, ast.List)):
                # 모듈 수준 표(교정 문구 짝 등). 띄어쓰기 있는 문장만, 낱말 목록은 뺀다.
                s = _str_of(top) or ""
                if fname != "speak_curriculum.py" and re.search(r"\s", s.strip()) and re.search(r"(요|다|세요)[.!?]?$", s.strip()):
                    add(top, "table")
    return items


def prompt_style_rules():
    """학습자가 읽는 글을 만드는 LLM 프롬프트와 그 안의 문체 지시(쉬운 말·짧은 문장) 여부."""
    targets = [
        ("backend/llm_service.py", "generate_speaking_coaching", "말하기 코칭 문단(학습자가 읽는 설명)"),
        ("backend/llm_service.py", "generate_conversation_turn", "4단계 대화 상대의 한 문장"),
        ("backend/llm_service.py", "rephrase_turn", "대화 '다른 말로 해 주세요'"),
        ("backend/conversation_scenario.py", "generate_multi_conversation", "여러 명 대화 턴"),
        ("backend/llm_service.py", "generate_adaptive_scenario", "3단계 상황별 문장 5개(난이도 단계가 어휘·길이를 정함)"),
    ]
    out = []
    for rel, fn, what in targets:
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        tree = ast.parse(src)
        body = ""
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn:
                body = ast.get_source_segment(src, n) or ""
        rule = re.search(r"PLAIN_KO_STYLE|PLAIN_KO_WORDS|쉬운 (일상 )?낱말|쉬운 말", body)
        out.append({"file": rel, "function": fn, "what": what, "plain_rule": bool(rule),
                    "rule": rule.group(0) if rule else ""})
    return out


# ── 채점 ──────────────────────────────────────────────────────────────────────
_kiwi = None


def kiwi():
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
        for w in CORE_TAUGHT | {"말하기", "듣기"}:   # 앱 용어를 한 낱말로 자르게(독화 → 독+화 방지)
            _kiwi.add_user_word(w, "NNG")
    return _kiwi


def sentences(text):
    t = text.replace("○", " ")
    parts = re.split(r"\n|(?<=[.!?。…])\s+|(?<=[.!?])(?=[가-힣])", t)
    return [p.strip() for p in parts if p and HANGUL.search(p)]


def syllables(s):
    return len(HANGUL.findall(s))


def lemma(tok):
    tag = tok.tag.split("-")[0]
    form = tok.form
    if tag in ("VV", "VA", "VX"):
        return form + "다"
    return form


def score_text(text, grade, zipf=None):
    sents = sentences(text)
    syl = [syllables(s) for s in sents]
    long_sents = [s for s, n in zip(sents, syl) if n > MAX_SYL]
    # 자모 낱자(ㅂ·ㅍ 등 소리 이름)는 글 읽기 부담을 따로 재지 않는다. 낱자 뒤 조사는 아래 한 음절 규칙으로 빠진다.
    clean = re.sub(r"[ㄱ-ㅎㅏ-ㅣ]+(으로|은|는|이|가|을|를|과|와|도|의|로|만)?", " ", text.replace("○", " "))
    toks = kiwi().tokenize(clean)
    words, hard, hard_core = [], [], []
    for i, t in enumerate(toks):
        tag = t.tag.split("-")[0]
        if tag not in CONTENT_TAGS:
            continue
        if tag == "NNP":
            continue                     # 고유 명사는 세지 않는다
        if tag == "SL":
            if t.form.upper() in SL_OK or len(t.form) == 1:
                continue
            words.append(t.form)
            hard.append(t.form)
            hard_core.append(t.form)
            continue
        w = lemma(t)
        # 명사 + 하다/되다(XSV·XSA)는 명사, 어근(XR)은 어근+하다로도 찾는다
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        cands = [w]
        if tag == "XR" or (nxt is not None and nxt.tag.startswith(("XSV", "XSA"))):
            cands += [w + "하다", w + "되다", w + "스럽다"]
        g = min((grade[c] for c in cands if c in grade), default=None)
        if g is None and len(t.form) == 1 and tag not in ("VV", "VA", "VX"):
            continue                     # 목록에 없는 한 음절 명사·부사는 대부분 분석 조각('우'·'으' 같은 소리 이름 포함)
        words.append(w)
        if g not in ("A", "B"):
            hard.append(w)
            if w not in CORE_TAUGHT:
                hard_core.append(w)
    n = len(words)
    ratio = len(hard) / n if n else 0.0
    ratio_core = len(hard_core) / n if n else 0.0
    jargon = [j for j in JARGON if (re.search(r"(?<![가-힣A-Za-z])" + re.escape(j), text, re.I) if re.match(r"[A-Za-z]", j) else j in text)]
    # 짧은 용어가 긴 용어 안에 든 경우(조음 ⊂ 동시조음 등)는 긴 쪽만
    jargon = [j for j in jargon if not any(j != k and j in k for k in jargon)]
    deficit = [d for d in DEFICIT if d in text]
    vocab_ok = ratio <= MAX_HARD
    len_ok = not long_sents
    return {
        "sentences": len(sents), "max_syl": max(syl) if syl else 0, "long": long_sents,
        "n_words": n, "hard": hard, "hard_ratio": round(ratio, 3), "hard_ratio_core": round(ratio_core, 3),
        "jargon": jargon, "deficit": deficit,
        "pass": vocab_ok and len_ok, "pass_core": (ratio_core <= MAX_HARD) and len_ok,
        "vocab_ok": vocab_ok, "len_ok": len_ok,
    }


def severity(r):
    over_words = max(0.0, len(r["hard"]) - MAX_HARD * r["n_words"])
    over_syl = sum(max(0, syllables(s) - MAX_SYL) for s in r["long"]) / 10
    return round(over_words + over_syl + 2 * len(r["jargon"]) + 2 * len(r["deficit"]), 2)


def run():
    grade = load_vocab()
    items = extract_front() + extract_back()
    # 표시용이 아닌 문자열 거르기: 자모·음절 낱개 목록, 정규식, 경로
    keep = []
    for it in items:
        t = it["text"]
        if len(HANGUL.findall(t)) < 2 and not re.search(r"[ㄱ-ㅎㅏ-ㅣ]", t):
            # 한 음절짜리 보기(예: '아')는 글 읽기 부담이 없다
            continue
        if re.search(r"[\\^$]\W|\[\^|\(\?", t):
            continue                     # 정규식
        keep.append(it)
    zipf = None
    try:
        # zipf_frequency('ko')는 MeCab을 부른다. content_rules처럼 토큰 사전을 직접 본다(요구 사항 파일 주석).
        import math
        from wordfreq import get_frequency_dict
        _fd = get_frequency_dict("ko")
        zipf = lambda w: math.log10(_fd[w] * 1e9) if _fd.get(w) else 0.0
    except Exception:
        pass
    for it in keep:
        it.update(score_text(it["text"], grade))
        it["severity"] = severity(it)
        it["owned_elsewhere"] = it["file"].replace("frontend/src/", "") in OWNED_ELSEWHERE
    unlisted = Counter(w for it in keep for w in it["hard"])
    top_unlisted = [{"word": w, "count": c, "grade": grade.get(w, "목록 없음"),
                     "zipf": round(zipf(w), 2) if zipf else None} for w, c in unlisted.most_common(60)]
    return keep, top_unlisted


def summarize(items):
    n = len(items)
    by_src = Counter("프론트엔드" if it["file"].startswith("frontend") else "백엔드" for it in items)
    p = sum(it["pass"] for it in items)
    pc = sum(it["pass_core"] for it in items)
    return {
        "strings": n, "by_source": dict(by_src),
        "pass": p, "pass_rate": round(p / n, 4) if n else 0,
        "pass_core": pc, "pass_rate_core": round(pc / n, 4) if n else 0,
        "fail_length": sum(not it["len_ok"] for it in items),
        "fail_vocab": sum(not it["vocab_ok"] for it in items),
        "with_jargon": sum(bool(it["jargon"]) for it in items),
        "with_deficit": sum(bool(it["deficit"]) for it in items),
        "target": TARGET,
    }


def swap_pass_rate(items, swaps=UI_TERM_SWAPS):
    ok = 0
    for it in items:
        hard = [w for w in it["hard"] if w not in swaps]
        ratio = len(hard) / it["n_words"] if it["n_words"] else 0.0
        ok += it["len_ok"] and ratio <= MAX_HARD
    return round(ok / len(items), 4) if items else 0


def worst(items, k=80):
    return sorted(items, key=lambda it: (-it["severity"], it["file"], it["line"]))[:k]


# ── 문서 ──────────────────────────────────────────────────────────────────────
def _md(s):
    return s.replace("|", "\\|").replace("\n", " / ")


def write_doc(items, top_unlisted):
    now = summarize(items)
    base = json.load(open(BASELINE, encoding="utf-8")) if os.path.exists(BASELINE) else None
    rew = json.load(open(REWRITES, encoding="utf-8")) if os.path.exists(REWRITES) else {"proposals": []}
    props = rew["proposals"]
    prompts = prompt_style_rules()
    jcount = Counter(j for it in items for j in it["jargon"])
    L = []
    w = L.append
    w("# 쉬운 한국어·용어 감사 (C15, 2026-10-06)")
    w("")
    w("> 계획: `docs/master-plan-2026-10.md` C15, `docs/idea-sweep-2026-10-03.md` 다7. 스크립트: `scripts/easy_korean_audit.py`"
      "(추출기 `scripts/easy_korean_extract.mjs`). 이 문서는 `python scripts/easy_korean_audit.py --doc`으로 다시 만든다.")
    w("")
    w("## 1. 방법")
    w("")
    w("- **대상.** 프론트엔드 `frontend/src`의 JSX 글·문자열 리터럴 가운데 한글이 든 것(주석·테스트·import·객체 키·비교 값·"
      "console·Error·className 등 비표시 속성 제외, 개발자·운영자·연구 화면 " + ", ".join(f"`{x}`" for x in sorted(FRONT_EXCLUDE)) +
      " 제외). 백엔드는 학습자에게 나가는 문자열만 파일별 규칙으로: 커리큘럼·말하기 안내(`curriculum.py`·`speak_curriculum.py`의 "
      "title·desc·guide·look·teach·hint 등), 피드백·코칭 문장(`speak_curriculum.py`·`articulation.py`·`formants.py`·`scoring.py`의 함수 안 문장), "
      "`main.py`의 오류 안내(detail=)와 message·note, `llm_service.py`의 코칭 대체 문장. 한 음절 보기와 정규식은 뺐다. "
      "학습 내용 자체(단어 은행·문장·문맥 문항)는 난이도 단계가 정하는 자료라 대상이 아니다.")
    w("- **어휘 등급.** 국립국어원 「한국어 학습용 어휘 목록」(2003, 5,965개, A 982·B 2,111·C 2,872)을 공식 누리집에서 내려받아"
      "(공공누리 제1유형) 낱말·품사·등급만 `scripts/data/nikl_learner_vocab.tsv`로 옮겼다. 그래서 wordfreq 대체는 쓰지 않았고, "
      "wordfreq는 목록에 없는 낱말의 빈도를 참고로 붙이는 데만 쓴다. 형태소 분석은 kiwipiepy(원형 복원, 명사+하다는 명사로도 찾음).")
    w(f"- **통과 기준(문자열마다).** 내용어(일반 명사·동사·형용사·보조 용언·부사·관형사·어근·대명사·외국 글자) 가운데 A·B 등급이 아닌 낱말"
      f"(C 등급과 목록에 없는 낱말, 고유 명사 제외)이 {int(MAX_HARD*100)}% 이하이고, 모든 문장이 한글 {MAX_SYL}음절 이하. 목표는 문자열의 "
      f"{int(TARGET*100)}% 통과(다7).")
    w("- **보조 통과율.** 앱이 직접 가르치는 핵심 말(" + "·".join(sorted(CORE_TAUGHT)) + ")을 쉬운 말로 칠 때의 통과율. "
      "2003년 목록에는 '입모양'·'자음'·'모음'·'수어'도 없어 엄격 기준이 앱의 기본 용어까지 실패로 센다. 판정은 엄격 기준으로 한다.")
    w("- **용어 표시.** 설명 없이 보이면 안 되는 전문 용어(비심·음소·포먼트·숙달 추정·이동 평균·판별·조음 위치 이름 등 "
      f"{len(JARGON)}개)와 결손 중심 표현(정상 발화·교정 등)은 통과 판정과 따로 센다.")
    w("- **한계.** 형태소 분석 오류(특히 앱 고유 합성어), 문맥을 보지 않는 등급 판정, 한 화면에 함께 보이는 문자열을 따로 센 점. "
      "LLM이 실시간으로 만드는 글(코칭·대화)은 이 표에 없고, 프롬프트의 문체 지시만 고쳤다(5절). 쉬운 보기 대화 100턴 표본 판정(다7의 셋째 기준)은 아직 안 했다.")
    w("")
    w("## 2. 결과")
    w("")
    w("| | 문자열 | 통과(엄격) | 통과율 | 보조 통과율 | 길이 실패 | 어휘 실패 | 전문 용어 | 결손 표현 |")
    w("|---|---|---|---|---|---|---|---|---|")
    if base:
        b = base["summary"]
        w(f"| 고치기 전 | {b['strings']} | {b['pass']} | **{b['pass_rate']*100:.1f}%** | {b['pass_rate_core']*100:.1f}% | "
          f"{b['fail_length']} | {b['fail_vocab']} | {b['with_jargon']} | {b['with_deficit']} |")
    w(f"| 지금 | {now['strings']} | {now['pass']} | **{now['pass_rate']*100:.1f}%** | {now['pass_rate_core']*100:.1f}% | "
      f"{now['fail_length']} | {now['fail_vocab']} | {now['with_jargon']} | {now['with_deficit']} |")
    w("")
    w(f"출처별 문자열 수(지금): " + ", ".join(f"{k} {v}" for k, v in now["by_source"].items()) + ".")
    w("")
    gap = now["pass_rate"] < TARGET
    w(("**판정: 목표 95%에 못 미친다.** " if gap else "**판정: 목표 95%를 넘었다.** ") +
      "실패의 대부분은 어휘 기준이다. 2003년 목록은 5,965개뿐이라 '연습'·'복습'·'녹음'은 A·B인데 '단계'·'기록'·'화면'은 C이고 "
      "'오답'·'숙달'·'입모양'은 목록에 없다. 짧은 버튼 글은 내용어가 한두 개라 하나만 목록 밖이어도 50~100%가 된다. "
      "뜻을 지키면서 바꿀 수 있는 문장만 고쳤고, 기준을 맞추려고 앱 용어를 억지로 풀어 쓰지는 않았다.")
    w("")
    w("### UI 용어를 바꾼다면")
    w("")
    sw = swap_pass_rate(items)
    w(f"화면 곳곳에 되풀이되는 UI 용어 {len(UI_TERM_SWAPS)}개를 쉬운 말로 바꿨다고 치면 엄격 통과율은 {now['pass_rate']*100:.1f}% → "
      f"**{sw*100:.1f}%**다(같은 기준으로 다시 셈, 핵심 말까지 쉬운 말로 치면 "
      f"{swap_pass_rate(items, set(UI_TERM_SWAPS) | CORE_TAUGHT)*100:.1f}%). 메뉴·버튼 이름이 함께 바뀌는 제품 결정이라 적용하지 않았다.")
    w("")
    w("| 지금 용어 | 쉬운 대안(등급) |")
    w("|---|---|")
    for k, v in UI_TERM_SWAPS.items():
        w(f"| {k} | {v} |")
    w("")
    w("95%에 닿지 못하는 나머지는 대부분 '단계·기록·숙달·정확도·독화·발화·문맥·음성'처럼 앱이 가르치는 개념 자체이거나, "
      "목록(2003년, 5,965개)에 없는 요즘 말(웹캠·아바타·이메일)이다. 이 기준을 그대로 목표로 삼으려면 핵심 말 목록을 화면에서 "
      "한 번 풀어 보여 주는 방식(용어 풀이 카드)과 함께 목표를 다시 정해야 한다.")
    w("")
    w("### 많이 나온 목록 밖·C 등급 낱말(상위 40)")
    w("")
    w("| 낱말 | 횟수 | 등급 | wordfreq zipf |")
    w("|---|---|---|---|")
    for u in top_unlisted[:40]:
        w(f"| {u['word']} | {u['count']} | {u['grade']} | {u['zipf'] if u['zipf'] else '-'} |")
    w("")
    w("### 전문 용어가 보이는 횟수(지금)")
    w("")
    w(", ".join(f"{j} {c}" for j, c in jcount.most_common()) or "없음")
    w("")
    w("## 3. 가장 나쁜 80개와 쉬운 고쳐 쓰기 제안(고치기 전 기준)")
    w("")
    w("점수 = A·B 밖 낱말 초과 수 + 30음절 넘은 음절/10 + 전문 용어·결손 표현 2점씩. '반영'은 7절 표에 들어간 것이다. "
      "'보류'는 뜻이 달라질 수 있거나(법적 문구·측정 설명) 다른 작업이 맡은 파일(`Practice.jsx`)이라 제안만 남긴 것이다.")
    w("")
    w("| # | 위치 | 원문 | 점수 | 걸린 것 | 제안 | 처리 |")
    w("|---|---|---|---|---|---|---|")
    pmap = {(p["file"], p["before"]): p for p in props}
    for i, it in enumerate(base["worst"] if base else worst(items), 1):
        p = pmap.get((it["file"], it["text"]))
        why = []
        if it["long"]:
            why.append(f"{it['max_syl']}음절")
        if not it["vocab_ok"]:
            why.append("어휘 " + "·".join(dict.fromkeys(it["hard"]))[:60])
        if it["jargon"]:
            why.append("용어 " + "·".join(it["jargon"]))
        if it["deficit"]:
            why.append("결손 " + "·".join(it["deficit"]))
        status = "-"
        if p:
            status = "반영" if p.get("applied") else ("보류: " + p.get("note", "") if p.get("note") else "보류")
        w(f"| {i} | `{it['file'].replace('frontend/src/', '')}:{it['line']}` | {_md(it['text'])[:300]} | {it['severity']} | "
          f"{_md('; '.join(why))} | {_md(p['after']) if p else '(제안 없음)'} | {status} |")
    w("")
    w("## 4. `Practice.jsx` 제안(이 작업에서는 고치지 않음)")
    w("")
    w("다른 작업이 이 파일을 맡고 있어 제안만 남긴다.")
    w("")
    w("| 줄 | 원문 | 제안 |")
    w("|---|---|---|")
    for p in props:
        if p["file"].endswith("pages/Practice.jsx"):
            w(f"| {p.get('line', '')} | {_md(p['before'])} | {_md(p['after'])} |")
    w("")
    w("## 5. LLM 프롬프트의 문체 지시")
    w("")
    w("학습자가 읽는 글을 만드는 프롬프트에 '쉬운 낱말·짧은 문장' 규칙을 더했다. 길이·형식·채점 같은 로직은 그대로다.")
    w("")
    w("| 파일 | 함수 | 무엇을 만드나 | 쉬운 말 규칙 |")
    w("|---|---|---|---|")
    for pr in prompts:
        w(f"| `{pr['file']}` | `{pr['function']}` | {pr['what']} | {('있음(`' + pr['rule'] + '`)') if pr['plain_rule'] else '없음'} |")
    w("")
    w("- `PLAIN_KO_STYLE`(코칭 문단): 쉬운 일상 낱말, 한 문장 30자 안팎, 음소·조음·포먼트 같은 전문 용어 금지. 기존 '3~5문장, 250자 이내'는 그대로.")
    w("- `PLAIN_KO_WORDS`(대화 한 문장·다른 말로·여러 명 대화): 쉬운 일상 낱말, 전문 용어·어려운 한자어 피하기. 문장 길이는 기존 "
      "단계 기준(글자 수 상한·재시도 로직)을 그대로 따르도록 명시했다.")
    w("")
    w("`generate_adaptive_scenario`는 독화 목표 문장을 만들고, 난이도 단계(1~5)가 어휘와 길이를 정하는 것이 로직이라(규칙 5) "
      "쉬운 말 규칙을 넣지 않았다. 말하기 콘텐츠 생성(`content_gen.py`)·검수 파이프라인·수어 번역 프롬프트도 학습 자료나 수어 글로스를 "
      "만드는 것이라 그대로 두었다. 다7의 'C6 쉬운 보기 프로필에서 대화 프롬프트에 어휘 등급 제약' 연동은 서버로 학습자 정보를 보내지 "
      "않는다는 C6 설계와 맞물려 따로 정해야 한다.")
    w("")
    w("## 6. 고쳐 쓰기 원칙")
    w("")
    w("- 학습자 화면의 안내·피드백만 고친다. 학습 내용(단어·문장), 법적 문구(`Legal.jsx`), 개발자 소개는 고치지 않는다.")
    w("- 뜻이 분명히 같을 때만. 숫자·조건·기준값은 그대로 둔다. 전문 용어는 쉬운 말로 바꾸거나 괄호 설명을 붙인다.")
    w("- 한 문장 30음절 안쪽으로 나누고, 화면의 기존 말투(해요체)를 지킨다.")
    w("- 고친 문장의 의미 보존은 두 번째 LLM과 팀원 1명이 확인해야 한다(다7 판정 기준, 아직 안 함).")
    w("- 조음 위치 이름은 학교 문법의 고유어 이름으로 바꿨다(양순음 → 입술소리, 치경음 → 잇몸소리, 경구개음 → 센입천장소리, "
      "연구개 → 여린입천장, 성문 → 목청). 입모양 무리 이름 목록(엔드리스·자가진단 결과·입모양 본뜨기)은 1단계 보기와 같은 쉬운 이름"
      "(`lib/visemeLabels`)을 쓴다.")
    w("")
    w("### 남긴 전문 용어(다음에 볼 것)")
    w("")
    w("- `backend/scoring.py`의 입모양 무리 이름(`viseme_name_ko`, '치경음(혀끝)' 등)은 테스트가 이름을 직접 확인해 이번에 바꾸지 않았다.")
    w("- `articulation.py`의 place·manner 값('양순'·'파열·비음')은 1단계 학습 자료의 칩으로 보이지만 테스트·로직이 값을 쓴다. "
      "화면에서만 쉬운 이름으로 바꾸는 표시용 표가 필요하다.")
    w("- `VocalTractVTL.jsx`·`lib/vtlShapes.js`의 '연구개'는 그림 속 이름표와 짝이라 그림과 함께 바꿔야 한다. "
      "'성도 단면'·'성도 실험실'도 기능 이름이라 그대로 두었다.")
    w("- 1단계 학습 자료의 무리 이름(양순음 등)과 '(동구형이음)'처럼 괄호로 풀어 둔 용어는 가르치는 말이라 그대로 두었다.")
    w("")
    w("## 7. 반영한 고쳐 쓰기")
    w("")
    applied = [p for p in props if p.get("applied")]
    w(f"총 {len(applied)}건.")
    w("")
    w("| 파일 | 고치기 전 | 고친 뒤 |")
    w("|---|---|---|")
    for p in applied:
        w(f"| `{p['file']}` | {_md(p['before'])} | {_md(p['after'])} |")
    w("")
    with open(DOC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print(f"→ {DOC}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="문자열별 결과를 이 파일로")
    ap.add_argument("--baseline", nargs="?", const=BASELINE, help="요약과 최악 80개를 기준선 파일로 저장")
    ap.add_argument("--doc", action="store_true", help="docs/easy-korean-audit.md 다시 쓰기")
    ap.add_argument("--build-vocab", metavar="XLS", help="국립국어원 xls에서 등급 목록 TSV 만들기")
    ap.add_argument("--worst", type=int, default=0, help="최악 N개를 출력")
    a = ap.parse_args()
    if a.build_vocab:
        build_vocab(a.build_vocab)
        return
    items, top_unlisted = run()
    s = summarize(items)
    try:
        import easy_korean_rebase as _rb   # 세 층 판정(같은 scripts 폴더)
        lay = _rb.layers(items, load_vocab(), json.load(open(_rb.TERMBOOK, encoding="utf-8")))
        s["layers"] = {k: lay[k] for k in ("undecided_types", "labels", "n_labels", "files_ge95", "n_files", "coverage_overall",
                                           "sentences_len_ok", "n_sentences", "pass")}
        s["layers"]["undecided_top"] = lay["undecided"][:20]
    except Exception as e:   # 결정표가 없어도 예전 요약은 낸다
        s["layers_error"] = str(e)
    print(json.dumps(s, ensure_ascii=False))
    if a.json:
        json.dump(items, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.baseline:
        keys = ("file", "line", "kind", "text", "severity", "max_syl", "long", "hard", "hard_ratio", "jargon", "deficit",
                "vocab_ok", "len_ok", "n_words")
        json.dump({"summary": s, "worst": [{k: it[k] for k in keys} for it in worst(items)],
                   "top_unlisted": top_unlisted}, open(a.baseline, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"기준선 → {a.baseline}")
    if a.worst:
        for it in worst(items, a.worst):
            print(f"{it['severity']:5} {it['file']}:{it['line']} | {it['text'][:120]} | hard={it['hard']} jargon={it['jargon']} long={len(it['long'])}")
    if a.doc:
        write_doc(items, top_unlisted)


if __name__ == "__main__":
    main()
