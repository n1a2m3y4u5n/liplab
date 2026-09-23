#!/usr/bin/env python3
"""
고도화 축 C: 한국어 독화 표준 리소스를 공개 저장소(Zenodo 등)에 올릴 배포 묶음으로 만든다.

docs/perceptual-resources.json을 읽어 release/korean-speechreading-resources-<semver>/ 폴더에 다음 파일을 쓴다.
  perceptual-resources.json  자원 본체(데이터 유래 부분은 기본으로 뺌, meta.data_derived_included로 표시)
  README.md                  한국어 설명과 영어 요약
  LICENSE.md                 CC BY 4.0 고지와 출처 표시 예시(라이선스 전문은 싣지 않음)
  CITATION.cff               인용 정보(cff-version 1.2.0)
  zenodo.json                Zenodo 업로드 메타데이터 초안
  SHA256SUMS                 나머지 파일의 SHA-256
표준 라이브러리만 쓴다. 파일을 만들기만 하며 네트워크에 접속하거나 어디에 올리지 않는다.

데이터 유래 부분(jamo_visual_similarity_data)은 AI Hub 538 데이터에서 계산한 값이다. AI Hub 이용약관은 AI Hub
데이터를 승인 없이 제3자에게 제공하지 못하게 하고, 거기서 계산한 집계 통계를 재배포해도 되는지는 확인 전이라
기본으로 뺀다. AI Hub의 확인을 받은 뒤에만 --include-data-derived로 넣는다(폴더 이름 끝에 -with-data-derived가 붙는다).

저자·게시일·DOI 같은 게시 정보는 아래 RELEASE_INFO의 [...] 자리표시로 나온다. 채운 뒤 다시 만들면 모든 파일과
SHA256SUMS에 반영된다. 만든 파일을 손으로 고치면 체크섬이 어긋나므로 RELEASE_INFO에서 고친다.

  python3 scripts/build_resource_release.py                        # → release/korean-speechreading-resources-1.2.0/
  python3 scripts/build_resource_release.py --out /tmp/rel          # 출력 위치 변경
  python3 scripts/build_resource_release.py --include-data-derived  # AI Hub 확인 후에만
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "docs", "perceptual-resources.json")
_PERCEPTUAL_PY = os.path.join(_ROOT, "backend", "perceptual.py")
_DEFAULT_OUT = os.path.join(_ROOT, "release")

# ── 게시 정보: 게시 전에 팀이 채운다. [ ]로 감싼 값은 자리표시로 보고, 남아 있으면 경고한다 ──────────
RELEASE_INFO = {
    # CITATION.cff·zenodo.json 저자. 사람 수만큼 늘린다. 본문 인용에서는 한글 성·이름을 붙여 쓰고(홍길동),
    # 그 밖의 이름은 이름 성 순(Jane Doe)으로 쓴다.
    "authors": [
        {"family_names": "[성]", "given_names": "[이름]", "affiliation": "[소속]"},
    ],
    "date_released": "[YYYY-MM-DD]",   # 게시일. CITATION.cff의 date-released, 인용·저작권 표시의 연도
    "copyright_holder": "[저작권자]",    # LICENSE.md 저작권 표시
    "doi": "[DOI]",                      # Zenodo에서 받은 DOI(https://doi.org/ 없이). 쓰지 않으면 ""
    "repository_url": "[저장소 주소]",    # 재생성 코드가 있는 저장소. 공개하지 않으면 ""
    "api_base_url": "[서비스 주소]",      # 공개 API가 도는 서버 주소(https://...)
}

BUNDLE_PREFIX = "korean-speechreading-resources"
DATA_DERIVED_KEY = "jamo_visual_similarity_data"
RULE_KEYS = ("homophene_dictionary", "consonant_visual_space", "phoneme_confusion_matrix",
             "difficulty_index", "lookalike_pairs", "standard_benchmark", "standard_eval_set")
FILES = ("perceptual-resources.json", "README.md", "LICENSE.md", "CITATION.cff", "zenodo.json")
SUMS = "SHA256SUMS"

TITLE_KO = "한국어 독화 표준 리소스"
TITLE_EN = "Korean Speechreading Resources"
TITLE = f"LIPLAB {TITLE_EN} ({TITLE_KO})"
CC_BY_URL = "https://creativecommons.org/licenses/by/4.0/"
KEYWORDS = ["speechreading", "lipreading", "Korean", "viseme", "homophene", "benchmark",
            "독화", "입모양", "동구형이음"]

# README에 옮기는 데이터 유래 부분의 수치. docs/korean-speechreading-resources.md 표기 그대로다.
# 원본 JSON에 이 부분이 있으면 표기 자릿수의 반올림 범위 안에서 맞는지 확인하고, 어긋나면 멈춘다.
DOC_VALIDATION = {
    "balanced_acc": {"consonant": "0.345", "vowel": "0.386"},
    "spearman_data_vs_handcoded": {"consonant": "0.30", "vowel": "0.22"},
}
DOC_PAIRS = {"consonant": (16, 120), "vowel": (18, 153)}   # (자모 수, 쌍 수)
DOC_MB = "0.90"                                             # ㅁ·ㅂ 유사도(키 "ㅁㅂ")


def _die(msg):
    print(f"오류: {msg}", file=sys.stderr)
    sys.exit(2)


def _warn(msg):
    print(f"경고: {msg}", file=sys.stderr)


def _is_placeholder(v):
    return isinstance(v, str) and v.startswith("[") and v.endswith("]")


def _q(s):
    """YAML 큰따옴표 문자열. JSON 문자열 표기는 YAML에서도 그대로 유효하다."""
    return json.dumps(s, ensure_ascii=False)


# ── 원본 검사: README에 적는 설명이 원본과 어긋나면 묶음을 만들지 않는다 ─────────────────────────

def load_source(path):
    try:
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
    except (OSError, ValueError) as e:
        _die(f"원본을 읽지 못했다: {path} ({e})")
    meta = res.get("meta") or {}
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(meta.get("semver", ""))):
        _die(f"meta.semver가 x.y.z 형식이 아니다: {meta.get('semver')!r}")
    if meta.get("license") != "CC BY 4.0":
        _die(f"meta.license가 'CC BY 4.0'이 아니다({meta.get('license')!r}). LICENSE.md 문안부터 고친다.")
    missing = [k for k in RULE_KEYS if not res.get(k)]
    if missing:
        _die("규칙 기반 키가 비었거나 없다: " + ", ".join(missing)
             + " (numpy 없이 export하면 consonant_visual_space·phoneme_confusion_matrix가 null이 된다)")
    unknown = [k for k in res if k not in ("meta", DATA_DERIVED_KEY) + RULE_KEYS]
    if unknown:
        _die("README에 설명이 없는 키가 있다: " + ", ".join(unknown) + ". 이 스크립트의 README 표에 먼저 넣는다.")
    rel = {p.get("relation") for p in res["lookalike_pairs"]}
    if rel - {"homophene", "minimal_pair"}:
        _die(f"lookalike_pairs에 README가 모르는 relation이 있다: {sorted(map(str, rel))}")
    return res


def check_code_semver(semver):
    """원본 JSON 판본과 코드의 RESOURCE_SEMVER가 다르면(원본을 다시 만들지 않았을 수 있음) 경고한다."""
    try:
        with open(_PERCEPTUAL_PY, encoding="utf-8") as f:
            m = re.search(r'^RESOURCE_SEMVER\s*=\s*"([^"]+)"', f.read(), re.M)
    except OSError:
        return
    if m and m.group(1) != semver:
        _warn(f"원본 JSON 판본 {semver}와 backend/perceptual.py의 RESOURCE_SEMVER {m.group(1)}가 다르다. "
              "export_perceptual.py로 원본을 다시 만들었는지 확인한다.")


def check_difficulty_formula(entries):
    """README에 적는 난이도 식(0.5·0.3·0.2 가중)이 실제 값과 맞는지 확인한다."""
    bad = [e["word"] for e in entries
           if abs(0.5 * e["invisibility"] + 0.3 * e["homophene_ratio"] + 0.2 * e["neighbor_density"]
                  - e["difficulty"]) > 0.0006]
    if bad:
        _die(f"difficulty_index {len(bad)}개가 README의 난이도 식과 맞지 않는다(예: {bad[0]}). 식 설명을 고친다.")


def check_data_derived(part):
    """원본에 든 데이터 유래 부분이 README에 옮긴 문서 수치(검증값·쌍 수·ㅁ·ㅂ 값)와 맞는지 확인한다."""
    val = part.get("validation") or {}
    for metric, by_kind in DOC_VALIDATION.items():
        for kind, text in by_kind.items():
            got = (val.get(metric) or {}).get(kind)
            tol = 0.5 * 10 ** -len(text.split(".")[1]) + 1e-9
            if not isinstance(got, (int, float)) or abs(got - float(text)) > tol:
                _die(f"{DATA_DERIVED_KEY}.validation.{metric}.{kind}={got}가 README 수치 {text}와 맞지 않는다.")

    def kind_of(ch):
        return "consonant" if "ㄱ" <= ch <= "ㅎ" else "vowel" if "ㅏ" <= ch <= "ㅣ" else None

    sim = part.get("jamo_similarity") or {}
    jamo = {"consonant": set(), "vowel": set()}
    pairs = {"consonant": 0, "vowel": 0}
    for key in sim:
        kinds = {kind_of(c) for c in key}
        if len(key) != 2 or len(kinds) != 1 or None in kinds:
            _die(f"{DATA_DERIVED_KEY}의 키 형식이 README 설명(같은 종류 자모 두 개)과 다르다: {key!r}")
        k = kinds.pop()
        pairs[k] += 1
        jamo[k].update(key)
    for k, want in DOC_PAIRS.items():
        if (len(jamo[k]), pairs[k]) != want:
            _die(f"{DATA_DERIVED_KEY}의 {k} 자모·쌍 수 {(len(jamo[k]), pairs[k])}가 README 수치 {want}와 다르다.")
    mb = sim.get("ㅁㅂ")
    if not isinstance(mb, (int, float)) or abs(mb - float(DOC_MB)) > 0.005 + 1e-9:
        _die(f"{DATA_DERIVED_KEY}의 ㅁ·ㅂ 값 {mb}가 README 수치 {DOC_MB}와 맞지 않는다.")


def check_release_info():
    d = RELEASE_INFO["date_released"]
    if not _is_placeholder(d) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        _die(f"RELEASE_INFO['date_released']는 YYYY-MM-DD 형식이어야 한다: {d!r}")
    if not RELEASE_INFO["authors"]:
        _die("RELEASE_INFO['authors']가 비었다.")


def remaining_placeholders():
    left = []
    for k, v in RELEASE_INFO.items():
        if k == "authors":
            left += [f"authors[{i}].{f}" for i, a in enumerate(v) for f, x in a.items() if _is_placeholder(x)]
        elif _is_placeholder(v):
            left.append(k)
    return left


# ── 게시 정보 표기 ────────────────────────────────────────────────────────────────

def _hangul_only(s):
    return bool(s) and all("가" <= c <= "힣" for c in s)


def _authors_text():
    """본문 인용·출처 표시용 저자 표기. 자리표시가 남아 있으면 [저자] 하나로 적는다."""
    authors = RELEASE_INFO["authors"]
    if any(_is_placeholder(a.get(f, "")) for a in authors for f in ("family_names", "given_names")):
        return "[저자]"
    out = []
    for a in authors:
        fam, giv = a["family_names"], a.get("given_names", "")
        # 한글 이름은 성과 이름을 붙이고(홍길동), 그 밖은 이름 성 순(Jane Doe)으로 써서 쉼표가 저자 구분에만 쓰이게 한다.
        out.append(fam + giv if _hangul_only(fam) and _hangul_only(giv) else f"{giv} {fam}".strip())
    return ", ".join(out)


def _year_text():
    d = RELEASE_INFO["date_released"]
    return "[연도]" if _is_placeholder(d) else d[:4]


def _doi_text():
    doi = RELEASE_INFO["doi"]
    if not doi or _is_placeholder(doi):
        return doi
    return f"https://doi.org/{doi}"


# ── 묶음 내용 ───────────────────────────────────────────────────────────────────

def build_resource(res, include):
    out = dict(res)
    meta = dict(res["meta"])
    if include:
        if not res.get(DATA_DERIVED_KEY):
            _die("--include-data-derived를 줬지만 원본에 데이터 유래 부분이 없다.")
        meta["data_derived_included"] = True
        meta["data_derived_note"] = (f"{DATA_DERIVED_KEY}는 AI Hub 538 데이터에서 계산한 값이며, "
                                     "이 부분의 이용과 재배포는 AI Hub 이용약관을 따른다.")
    else:
        out.pop(DATA_DERIVED_KEY, None)
        meta["data_derived_included"] = False
        meta["data_derived_note"] = (f"{DATA_DERIVED_KEY}(AI Hub 538 데이터에서 계산)는 AI Hub에 재배포 허용 "
                                     "여부를 확인하기 전이라 이 배포본에서 뺐다.")
    out["meta"] = meta
    return out


def _identical_distractor_items(items, answer_key, visemes):
    """오답 보기 가운데 입모양 순열이 정답과 완전히 같은 것(입만 보고 구별 불가)이 든 문항 수."""
    n = 0
    for it in items:
        ans = it[answer_key]
        if ans not in visemes or any(o not in visemes for o in it["options"]):
            _die(f"평가셋 문항 {it.get('id')}의 단어가 difficulty_index에 없어 입모양을 비교할 수 없다.")
        n += any(o != ans and visemes[o] == visemes[ans] for o in it["options"])
    return n


def summarize(res):
    hd, pcm = res["homophene_dictionary"], res["phoneme_confusion_matrix"]
    bm, ev = res["standard_benchmark"], res["standard_eval_set"]
    rel, tiers = {}, {}
    for p in res["lookalike_pairs"]:
        rel[p["relation"]] = rel.get(p["relation"], 0) + 1
    for it in bm["items"]:
        tiers[it["tier"]] = tiers.get(it["tier"], 0) + 1
    per = [tiers.get(t, 0) for t in bm["tiers"]]
    visemes = {e["word"]: tuple(e["visemes"]) for e in res["difficulty_index"]}
    if _identical_distractor_items(ev["items"], "word", visemes):
        _die("standard_eval_set에 입모양이 정답과 같은 보기가 있다. README의 보기 선정 설명을 고친다.")
    return {
        "words": len(res["difficulty_index"]),
        "groups": len(hd["viseme_groups"]),
        "cluster_names": [c["name"] for c in hd["homophene_clusters"]],
        "consonants": len(res["consonant_visual_space"]["consonants"]),
        "pcm_c": len(pcm["consonants"]["symbols"]),
        "pcm_v": len(pcm["vowels"]["symbols"]),
        "pairs": len(res["lookalike_pairs"]),
        "pairs_homophene": rel.get("homophene", 0),
        "pairs_minimal": rel.get("minimal_pair", 0),
        "bm_items": len(bm["items"]), "bm_seed": bm["seed"], "bm_tiers": bm["tiers"],
        "bm_identical": _identical_distractor_items(bm["items"], "answer", visemes),
        "bm_per_tier": (f"구간별 {per[0]}" if len(set(per)) == 1
                        else ", ".join(f"{t} {n}" for t, n in zip(bm["tiers"], per))),
        "ev_items": len(ev["items"]), "ev_seed": ev["seed"],
    }


def build_readme(meta, s, include):
    semver = meta["semver"]
    V = DOC_VALIDATION
    (cj, cp), (vj, vp) = DOC_PAIRS["consonant"], DOC_PAIRS["vowel"]
    repo = RELEASE_INFO["repository_url"]
    api = RELEASE_INFO["api_base_url"]
    doi = _doi_text()
    head = f"{meta.get('source', 'LIPLAB')} · 판 {meta.get('edition', '')} · {meta['license']}"
    L = [
        f"# {TITLE_KO} {semver}", "",
        head + (" · 데이터 유래 부분 포함" if include else ""), "",
        ("한국어 독화(speechreading, 입모양 읽기)에 쓰는 표준 자원이다. 동구형이음 사전, 자음 시각 지각공간, 음소 혼동 행렬, "
         "단어별 독화 난이도 지수, 시각 혼동 단어쌍, 표준 평가셋 두 벌을 JSON 파일 하나(`perceptual-resources.json`)에 "
         "담았다. 한국어 독화에는 공개된 표준 자원이 거의 없어, LIPLAB 앱 밖의 연구와 교육에서도 쓸 수 있도록 공개한다."),
        "",
    ]
    if include:
        L += ["## 데이터 유래 부분 포함", "",
              (f"이 묶음에는 데이터 유래 부분인 `{DATA_DERIVED_KEY}`(자모쌍 시각유사도)가 들어 있다"
               "(`meta.data_derived_included`가 `true`). 이 값은 AI Hub 538 립리딩 데이터에서 계산했으며, 이 부분의 "
               "이용과 재배포는 AI Hub 이용약관을 따른다. 나머지 부분은 모두 규칙 기반이다."), ""]
    else:
        L += ["## 이 묶음에서 뺀 부분", "",
              (f"데이터 유래 부분인 `{DATA_DERIVED_KEY}`(자모쌍 시각유사도)는 이 묶음에 들어 있지 않다. 이 값은 AI Hub "
               "538 립리딩 데이터에서 계산했다. AI Hub 이용약관은 AI Hub 데이터를 승인 없이 제3자에게 제공하지 못하게 "
               "하며, 이 데이터에서 계산한 집계 통계를 재배포해도 되는지는 아직 확인되지 않았다. AI Hub에 확인할 때까지 "
               "이 부분을 빼 두었다. JSON의 `meta.data_derived_included`는 `false`이며, 이 부분을 만든 방법과 검증 "
               "결과는 아래 「검증과 한계」에 기록으로 남겼다."), ""]

    L += ["## 파일", "",
          "| 파일 | 내용 |", "|---|---|",
          "| `perceptual-resources.json` | 자원 본체(UTF-8 JSON) |",
          "| `README.md` | 이 설명서 |",
          "| `LICENSE.md` | CC BY 4.0 고지와 출처 표시 예시 |",
          "| `CITATION.cff` | 인용 정보(Citation File Format 1.2.0) |",
          "| `zenodo.json` | Zenodo 업로드 메타데이터 |",
          "| `SHA256SUMS` | 나머지 파일의 SHA-256 체크섬 |", ""]

    dd_scale = f"자음 {cj}개 {cp}쌍, 모음 {vj}개 {vp}쌍" if include else "이 묶음에 없음"
    L += ["## 구성", "",
          "| 키 | 내용 | 만든 방식 | 규모 |", "|---|---|---|---|",
          ("| `meta` | 판본(`semver`), 판(`edition`), 라이선스, 출처, 단어 수, 데이터 유래 부분 포함 여부"
           "(`data_derived_included`)와 설명(`data_derived_note`) | | |"),
          ("| `homophene_dictionary` | 동구형이음 사전. 음소를 입모양(viseme) 그룹으로 묶고 그룹마다 가시성(high·medium·low)을 "
           "단다. 같은 그룹의 음소는 눈으로 구별되지 않는다. 혼동 무리(" + ", ".join(s["cluster_names"]) + ")도 함께 든다 "
           f"| 규칙 | 입모양 그룹 {s['groups']}, 혼동 무리 {len(s['cluster_names'])} |"),
          ("| `consonant_visual_space` | 자음 시각 지각공간. 자음 쌍 시각 유사도 행렬(`similarity`, 코사인)과 고전 MDS 2차원 "
           f"좌표(`mds_2d`). 가까울수록 눈으로 헷갈린다 | 규칙(시각 자질) + 고전 MDS | 자음 {s['consonants']} |"),
          ("| `phoneme_confusion_matrix` | 자음·모음 혼동 행렬. 시각 지각공간(MDS 2차원)에서 두 음소 사이 거리 d를 "
           f"1 − d/dmax로 바꾼 값이며, 1에 가까울수록 구별하기 어렵다 | 규칙(지각공간 거리) | 자음 {s['pcm_c']}×{s['pcm_c']}, "
           f"모음 {s['pcm_v']}×{s['pcm_v']} |"),
          ("| `difficulty_index` | 단어별 독화 난이도(0 쉬움 ~ 1 어려움)와 세 성분, 음절 수, 입모양 순열. 난이도 순으로 "
           f"정렬했다 | 규칙 | 단어 {s['words']} |"),
          ("| `lookalike_pairs` | 눈으로 헷갈리는 단어쌍. `relation`이 `homophene`이면 보이는 입모양 순열이 완전히 같은 "
           "쌍(밥↔맘), `minimal_pair`면 자모 한 자리만 다른 쌍이다. `same_looking`은 입모양만으로 구별되지 않는지를 "
           f"나타낸다 | 규칙 | {s['pairs']}쌍(동구형이음 {s['pairs_homophene']}, 최소대립 {s['pairs_minimal']}) |"),
          ("| `standard_benchmark` | 표준 평가셋. 난이도 3구간(" + "·".join(s["bm_tiers"]) + ")으로 층화해 구간마다 "
           f"균등 간격으로 뽑은 4지선다 문항 | 규칙, seed {s['bm_seed']} | {s['bm_items']}문항({s['bm_per_tier']}) |"),
          ("| `standard_eval_set` | 배치검사용 표준 평가셋. 난이도 오름차순으로 균등 표집한 4지선다 문항 "
           f"| 규칙, seed {s['ev_seed']} | {s['ev_items']}문항 |"),
          (f"| `{DATA_DERIVED_KEY}` | 자모쌍 시각유사도(0~1). 실화자 영상에서 계산 | 데이터 유래(AI Hub 538) "
           f"| {dd_scale} |"),
          ""]

    L += ["## 만든 방식", "",
          ("규칙 기반 부분은 영상이나 음성 데이터를 쓰지 않는다. 음소를 입모양 그룹에 대응시킨 표(VISEME_MAP)와 조음 자질에서 "
           "결정론적으로 계산하므로, 같은 코드와 같은 단어 목록이면 같은 값이 나온다. 단어 목록은 LIPLAB 커리큘럼 단어 "
           f"{s['words']}개다."),
          "",
          ("- 입모양 순열: 단어를 소리 나는 대로 바꾼 뒤 눈에 보이는 입모양 번호만 순서대로 늘어놓는다(무음 초성 ㅇ 제외). "
           "동구형이음 판정과 난이도 지수의 기반이다."),
          ("- 시각 지각공간: 자음은 조음 위치(입모양)를 주 차원으로, 조음 방식을 작은 가중의 보조 차원으로 둔 벡터로 나타낸다. "
           "모음은 입모양 군을 주 차원으로, 개구도와 원순성을 보조 차원으로 둔다. 코사인 거리(1 − 코사인 유사도)에 고전 "
           "MDS를 적용해 2차원 좌표를 얻는다."),
          ("- 난이도 지수: `difficulty = 0.5 × invisibility + 0.3 × homophene_ratio + 0.2 × neighbor_density`. "
           "`invisibility`는 입모양 가시성 가중(high 0, medium 0.5, low 1)의 평균, `homophene_ratio`는 같은 입모양 그룹에 "
           "다른 음소가 있는 음소의 비율, `neighbor_density`는 입모양 순열이 같은 다른 단어 수(최대 5)를 5로 나눈 값이다."),
          ("- 단어쌍: 동구형이음과 최소대립에 모두 해당하는 쌍은 동구형이음으로 분류한다. 종성 유무만 다른 쌍(밥/바)은 "
           "최소대립으로 보지 않는다."),
          ("- 평가셋: 두 벌 모두 단어를 난이도순으로 정렬해 균등 간격으로 뽑는다. seed가 고정되어 다시 만들어도 같은 문항이 "
           "나온다. 오답 보기를 고르는 방식은 「표준 평가셋 사용법」에 적었다."),
          "",
          f"데이터 유래 부분은 `{DATA_DERIVED_KEY}` 하나이며, 만든 방법은 「검증과 한계」에 적었다.",
          ""]

    L += ["## 표준 평가셋 사용법", "",
          ("두 평가셋의 문항은 모두 4지선다다. 정답 단어의 입모양을 보여 주고 보기 네 개 중에서 고르게 한다. 오답 보기를 "
           "정답과 시각적으로 헷갈리는 단어로 채워 실제 독화 변별력을 잰다. seed가 고정되어 있어 같은 평가셋을 사전·사후에 "
           "반복 적용해 향상도를 비교할 수 있다."),
          "",
          ("- `standard_benchmark.items`: `answer`(정답), `options`(보기 4개), `tier`(난이도 구간), `difficulty`, "
           "`visemes`(입모양 순열), `n_homophenes`(단어 목록 안에서 입모양 순열이 같은 다른 단어 수). 오답 보기는 정답과 "
           "입모양 순열이 같은 단어(동구형이음)와 최소대립 단어를 먼저 쓰고, 모자라면 다른 단어로 채운다."),
          ("- `standard_eval_set.items`: `word`(정답), `options`, `difficulty`, `visemes`. 정답 필드 이름이 "
           "`standard_benchmark`와 다르다. 오답 보기는 입모양 거리로 고른다. 입모양이 정답과 완전히 같은 단어는 입만 보고 "
           "구별할 수 없어 빼고, 어려운 문항일수록 입모양이 가까운 보기를 쓴다. LIPLAB 앱의 사전·사후 검사 문항 단어는 "
           "검사 문항이 공개되지 않도록 넣지 않았다."),
          ""]

    L += ["## 검증과 한계", "", "### 규칙 기반 부분", "",
          "- 조음 자질 규칙으로 만든 값이며, 대규모 데이터로 검증하기 전 단계다.",
          f"- 혼동 이웃 밀도, 단어쌍, 평가셋은 위 단어 목록({s['words']}개) 안에서 계산했다. 어휘 집합이 바뀌면 값도 바뀐다.",
          "- 시각 지각공간과 혼동 행렬은 사람이 정한 자질 가중에서 나온 규칙판이며, 실측 혼동률이 아니다.",
          (f"- `standard_benchmark` {s['bm_items']}문항 가운데 {s['bm_identical']}문항은 입모양이 정답과 완전히 같은 오답 "
           "보기를 포함한다. 이런 문항은 입모양만으로 정답을 확정할 수 없어 정답률에 추측이 섞인다. 입모양 변별만 재려면 이 "
           "문항을 빼거나 `standard_eval_set`을 쓴다."),
          "", f"### 데이터 유래 부분 (`{DATA_DERIVED_KEY}`)", ""]
    if not include:
        L += [f"이 묶음에는 들어 있지 않다. LIPLAB {semver}에서 이 부분을 만든 방법과 검증 결과를 기록으로 남긴다.", ""]
    L += ["- 자료: AI Hub 538 실화자 10명 300문장. wav2vec2 강제정렬과 MediaPipe를 썼다.",
          ("- 방법: 강제정렬한 음절 창을 초성·모음 구간으로 나눠 입 주변 블렌드셰이프 27차원(화자별 정규화)을 평균하고, "
           f"LDA 공간의 자모 중심점 거리 d를 1 − d/dmax로 바꿨다. 자음 {cj}개 {cp}쌍, 모음 {vj}개 {vp}쌍이며, 키는 두 자모를 "
           "유니코드 순으로 붙인 문자열이다."),
          ("- 검증: 같은 특징으로 화자를 바꿔 입모양 그룹을 가르면 균형 정확도가 "
           f"자음 {V['balanced_acc']['consonant']}, 모음 {V['balanced_acc']['vowel']}(우연 0.2 안팎)으로 우연보다 높지만, "
           "손코딩 음운 유사도와의 순위상관은 "
           f"자음 {V['spearman_data_vs_handcoded']['consonant']}, 모음 {V['spearman_data_vs_handcoded']['vowel']}로 약하다."),
          ("- 한계: \"시각적으로 닮음\"과 \"조음·청각적으로 닮음\"이 갈리는 부분이 있으나, 데이터가 적어 쌍 하나하나의 값은 "
           f"흔들린다(예: ㅁ·ㅂ {DOC_MB}은 뚜렷하지만 ㅃ처럼 드문 자모는 불안정). 채점과 문항 선정에는 쓰지 않는 참고 자원이다."),
          ("- 이전 판: 1.1.0까지 든 판(4화자 160발화, CTC 구간을 그대로 평균한 코사인)은 CTC 구간이 1~3프레임으로 짧아 거의 "
           "모든 쌍이 0.99 안팎이었고, 손코딩과의 상관이 −0.19였다. 1.2.0에서 위 방식으로 바꿨다.")]
    if include:
        L += ["", f"소수 넷째 자리까지의 값은 `{DATA_DERIVED_KEY}.validation`에 있다."]
    L += [""]

    L += ["## 공개 API", "",
          ("LIPLAB 서비스는 같은 자원과 채점 기준을 로그인 없는 무상태 API로 연다. 요청 내용은 저장하지 않으며, "
           "IP마다 분당 요청 수만 제한한다."),
          "", f"- 서비스 주소: `{api}`", "",
          "| 메서드 | 경로 | 내용 | 요청 제한 |", "|---|---|---|---|",
          "| GET | `/api/public/resources` | 자원 한 벌(JSON). `meta`에 판본과 라이선스가 있다 | 분당 20회 |",
          "| POST | `/api/public/score` | 독화 답 채점 | 분당 30회 |",
          "",
          ("- `/api/public/resources`의 응답은 서버의 코드와 설정에 따라 이 묶음과 다를 수 있고, `standard_eval_set`은 "
           "들어 있지 않다. 연구 재현에는 판본이 고정되고 체크섬이 있는 이 묶음의 파일을 쓴다."),
          ("- `/api/public/score`는 목표 문장과 읽은 답을 소리 나는 대로 자모로 바꿔 입모양(viseme) 가중 음운 유사도로 "
           "채점한다. 표기가 달라도 소리가 같으면 만점이다(굳이·구지). 입력은 각 100자까지이며, 넘으면 400을 돌려준다."),
          ("- 채점 응답: `score`(0~100), `phoneme_accuracy`(초성·중성·종성), `viseme_errors`, `confusions`(자리, 목표 자모, "
           "읽은 자모, 입모양이 같은지), `method`."),
          "- 개인 학습 기록과 음성·영상은 받지 않는다.",
          "", "```bash",
          f"curl -X POST {api}/api/public/score \\",
          "  -H 'Content-Type: application/json' \\",
          "  -d '" + '{"target": "밥 먹었어요", "answer": "맘 먹었어요"}' + "'",
          "```", ""]

    where = f"LIPLAB 저장소({repo})" if repo else "LIPLAB 저장소"
    L += ["## 재생성", "",
          f"다음 명령은 {where}의 루트에서 실행한다. 규칙 기반 부분은 결정론적이라 같은 코드에서 같은 값이 나온다.",
          "", "```bash",
          "(cd backend && python ../scripts/export_perceptual.py)   # → docs/perceptual-resources.json",
          "python3 scripts/build_resource_release.py                 # → release/korean-speechreading-resources-<semver>/",
          "```", "",
          ("- `consonant_visual_space`와 `phoneme_confusion_matrix`는 numpy가 있어야 만들어진다. numpy가 없으면 두 키가 "
           "null이 되고, 배포 스크립트는 묶음을 만들지 않고 멈춘다."),
          ("- 원본 JSON에는 `backend/data/c_jamo_similarity.json`이 있을 때 데이터 유래 부분이 들어간다. 배포 스크립트는 "
           "기본값으로 이 부분을 빼고, `--include-data-derived`를 줄 때만 넣는다."),
          ""]

    L += ["## 파일 확인", "",
          "`SHA256SUMS`에 나머지 파일의 SHA-256 값이 있다. 묶음 폴더에서 다음을 실행한다.",
          "", "```bash",
          "sha256sum -c SHA256SUMS         # Linux",
          "shasum -a 256 -c SHA256SUMS     # macOS",
          "```", ""]

    cite = f"{_authors_text()} ({_year_text()}). *{TITLE}* (버전 {semver}) [데이터 세트]."
    L += ["## 인용", "",
          "인용 정보는 `CITATION.cff`에 있다. 본문 인용은 다음 형식을 쓸 수 있다.", "",
          "> " + cite + (f" {doi}" if doi else ""), "",
          "재사용할 때의 출처 표시 방법은 `LICENSE.md`에 있다.", ""]

    L += ["## English summary", "",
          f"**{TITLE_EN} {semver}** (LIPLAB, edition {meta.get('edition', '')}, CC BY 4.0)", "",
          ("Rule-based standard resources for Korean speechreading (lipreading), in one JSON file: a homophene dictionary "
           f"({s['groups']} viseme groups), a consonant visual space ({s['consonants']} consonants, classical MDS), phoneme "
           f"confusion matrices ({s['pcm_c']} consonants, {s['pcm_v']} vowels), a speechreading difficulty index for "
           f"{s['words']} words, {s['pairs']} look-alike word pairs, and two fixed-seed four-option test sets "
           f"({s['bm_items']} and {s['ev_items']} items). The rule-based parts are computed deterministically from "
           "articulatory rules over the LIPLAB curriculum word list and use no audio, video, or personal data. "
           f"In `standard_benchmark`, {s['bm_identical']} of the {s['bm_items']} items include a distractor that looks "
           "identical to the answer; `standard_eval_set` excludes such distractors."),
          ""]
    if include:
        L += [(f"**Included:** `{DATA_DERIVED_KEY}`, a jamo-pair visual similarity table computed from AI Hub dataset 538 "
               "(10 speakers, 300 sentences). Use and redistribution of this part follow the AI Hub terms of use "
               "(`meta.data_derived_included` is `true`)."), ""]
    else:
        L += [(f"**Excluded from this bundle:** `{DATA_DERIVED_KEY}`, a jamo-pair visual similarity table computed from "
               "AI Hub dataset 538. The AI Hub terms of use do not allow AI Hub data to be provided to third parties "
               "without approval, and it has not been confirmed whether aggregate statistics derived from the data may be "
               "redistributed. This part is left out pending confirmation with AI Hub (`meta.data_derived_included` is "
               "`false`)."), ""]
    L += [("Public API (no login, stateless, rate-limited): `GET /api/public/resources`, `POST /api/public/score`. "
           "Cite with `CITATION.cff`; the license notice and an attribution template are in `LICENSE.md`; verify the files "
           "with `SHA256SUMS`."), ""]
    return "\n".join(L)


def build_license(meta, include):
    semver = meta["semver"]
    holder = RELEASE_INFO["copyright_holder"]
    work_ko = f"「{TITLE_KO}」(LIPLAB {TITLE_EN}) {semver}"
    work_en = f"\"LIPLAB {TITLE_EN}\" version {semver}"
    ref = [x for x in (_doi_text(),) if x]
    attr_ko = ", ".join([_authors_text(), work_ko] + ref + [f"CC BY 4.0 ({CC_BY_URL})"])
    attr_en = ", ".join([_authors_text(), work_en] + ref + [f"licensed under CC BY 4.0 ({CC_BY_URL})"])
    if include:
        scope = [f"- 설명 문서와 `perceptual-resources.json`에서 `{DATA_DERIVED_KEY}`를 뺀 모든 키. 조음 규칙에서 만든 값이다.",
                 (f"- `{DATA_DERIVED_KEY}`는 AI Hub 538 데이터에서 계산한 값이다. 이 부분의 이용과 재배포는 AI Hub "
                  "이용약관을 따르며, 이 부분에 CC BY 4.0을 적용할 수 있는지는 AI Hub에 확인하지 않았다.")]
        scope_en = (f"`{DATA_DERIVED_KEY}` is derived from AI Hub dataset 538; its use and redistribution follow the AI Hub "
                    "terms of use, and whether CC BY 4.0 can apply to it has not been confirmed with AI Hub.")
    else:
        scope = ["- 이 묶음의 `perceptual-resources.json`과 설명 문서. 모든 키가 조음 규칙에서 만든 값이다.",
                 f"- 데이터 유래 부분(`{DATA_DERIVED_KEY}`, AI Hub 538 데이터에서 계산)은 이 묶음에 들어 있지 않다."]
        scope_en = f"The data-derived part (`{DATA_DERIVED_KEY}`, computed from AI Hub dataset 538) is not included in this bundle."
    L = ["# 라이선스", "",
         f"© {_year_text()} {holder}", "",
         f"{work_ko}은 크리에이티브 커먼즈 저작자표시 4.0 국제 라이선스(CC BY 4.0)에 따라 이용할 수 있다.", "",
         f"<{CC_BY_URL}>", "",
         ("출처를 표시하면 상업적 이용을 포함해 복제, 배포, 변경, 2차적 저작물 작성이 가능하다. 이 문서는 고지와 요약이며 "
          "라이선스 전문(Legal Code)이 아니다. 이용 조건은 위 주소에서 연결되는 라이선스 전문을 따른다. 자원은 있는 그대로 "
          "제공되며, 보증 부인과 책임 제한도 라이선스 전문을 따른다."), "",
         "## 적용 범위", ""] + scope + ["",
         "## 출처 표시 예시", "",
         "재사용할 때는 제목, 저작자, 출처, 라이선스를 밝히고, 변경했다면 변경했다는 사실을 적는다.", "",
         "> " + attr_ko, "",
         "변경한 경우에는 끝에 \"원자료를 변경함\"과 바꾼 내용을 덧붙인다.", "",
         "## English", "",
         (f"© {_year_text()} {holder}. {work_en} is licensed under the Creative Commons Attribution 4.0 International "
          f"License (CC BY 4.0), {CC_BY_URL}. This file is a notice, not the legal code; the legal code linked from that "
          "page governs, including its disclaimer of warranties and limitation of liability. " + scope_en), "",
         "Attribution template:", "",
         "> " + attr_en + ". Indicate if changes were made.", ""]
    return "\n".join(L)


def _abstracts(s, include):
    ko = (f"한국어 독화(speechreading, 입모양 읽기)를 위한 규칙 기반 표준 자원이다. 동구형이음 사전(입모양 그룹 {s['groups']}개), "
          f"자음 시각 지각공간(자음 {s['consonants']}개), 음소 혼동 행렬(자음 {s['pcm_c']}개, 모음 {s['pcm_v']}개), "
          f"단어 {s['words']}개의 독화 난이도 지수, 시각 혼동 단어쌍 {s['pairs']}개, seed를 고정한 4지선다 표준 평가셋 두 벌"
          f"({s['bm_items']}문항, {s['ev_items']}문항)을 JSON 파일 하나에 담았다. 규칙 기반 부분은 조음 자질 규칙에서 "
          "결정론적으로 계산했으며 음성, 영상, 개인 정보를 쓰지 않았다.")
    en = ("Rule-based standard resources for Korean speechreading (lipreading) in a single JSON file: a homophene "
          f"dictionary ({s['groups']} viseme groups), a consonant visual space ({s['consonants']} consonants), phoneme "
          f"confusion matrices ({s['pcm_c']} consonants, {s['pcm_v']} vowels), a speechreading difficulty index for "
          f"{s['words']} words, {s['pairs']} look-alike word pairs, and two fixed-seed four-option test sets "
          f"({s['bm_items']} and {s['ev_items']} items). The rule-based parts are computed deterministically from "
          "articulatory rules and use no audio, video, or personal data.")
    if include:
        ko2 = (f"자모쌍 시각유사도({DATA_DERIVED_KEY})는 AI Hub 538 데이터에서 계산한 값이며, 이 부분의 이용과 재배포는 "
               "AI Hub 이용약관을 따른다.")
        en2 = (f"The jamo-pair visual similarity table ({DATA_DERIVED_KEY}) is computed from AI Hub dataset 538; its use "
               "and redistribution follow the AI Hub terms of use.")
    else:
        ko2 = (f"AI Hub 538 데이터에서 계산한 자모쌍 시각유사도({DATA_DERIVED_KEY})는 AI Hub에 재배포 허용 여부를 "
               "확인하기 전이라 이 판에서 뺐다.")
        en2 = (f"The jamo-pair visual similarity table ({DATA_DERIVED_KEY}), computed from AI Hub dataset 538, is "
               "excluded from this version pending confirmation with AI Hub on whether it may be redistributed.")
    return [ko, ko2, en, en2]


def build_cff(meta, s, include):
    ko, ko2, en, en2 = _abstracts(s, include)
    L = ["cff-version: 1.2.0",
         "message: " + _q("이 자원을 사용했다면 아래 정보로 인용해 주십시오. "
                          "If you use these resources, please cite them using the metadata in this file."),
         "type: dataset",
         f"title: {_q(TITLE)}",
         f"version: {_q(meta['semver'])}",
         f"date-released: {_q(RELEASE_INFO['date_released'])}",
         "license: CC-BY-4.0",
         "authors:"]
    for a in RELEASE_INFO["authors"]:
        L.append(f"  - family-names: {_q(a['family_names'])}")
        if a.get("given_names"):
            L.append(f"    given-names: {_q(a['given_names'])}")
        if a.get("affiliation"):
            L.append(f"    affiliation: {_q(a['affiliation'])}")
    # DOI·저장소 주소는 자리표시인 동안 주석으로 둔다(자리표시 값은 CFF 형식 검사를 통과하지 못한다).
    for field, key in (("doi", "doi"), ("repository-code", "repository_url")):
        v = RELEASE_INFO[key]
        if v:
            L.append(f"# {field}: {_q(v)}  # RELEASE_INFO['{key}']를 채우면 주석이 풀린다" if _is_placeholder(v)
                     else f"{field}: {_q(v)}")
    L.append("keywords:")
    L += [f"  - {_q(k)}" for k in KEYWORDS]
    L.append(f"abstract: {_q(ko + ' ' + ko2 + chr(10) + chr(10) + en + ' ' + en2)}")
    return "\n".join(L) + "\n"


def build_zenodo(meta, s, include):
    ko, ko2, en, en2 = _abstracts(s, include)
    creators = []
    for a in RELEASE_INFO["authors"]:
        c = {"name": f"{a['family_names']}, {a['given_names']}" if a.get("given_names") else a["family_names"]}
        if a.get("affiliation"):
            c["affiliation"] = a["affiliation"]
        creators.append(c)
    md = {
        "upload_type": "dataset",
        "title": TITLE,
        "version": meta["semver"],
        "creators": creators,
        "description": "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in (ko + " " + ko2, en + " " + en2)),
        "license": "cc-by-4.0",
        "access_right": "open",
        "language": "kor",
        "keywords": KEYWORDS,
    }
    if not _is_placeholder(RELEASE_INFO["date_released"]):
        md["publication_date"] = RELEASE_INFO["date_released"]
    return {"metadata": md}


def prepare_dir(bundle):
    """묶음 폴더를 만든다. 이미 있으면 묶음 파일만 덮어쓰고, 묶음 밖 파일이 있으면 지우지 않고 멈춘다."""
    if os.path.exists(bundle) and not os.path.isdir(bundle):
        _die(f"폴더가 아니다: {bundle}")
    if os.path.isdir(bundle):
        extra = sorted(set(os.listdir(bundle)) - set(FILES + (SUMS,)))
        if extra:
            _die(f"{bundle}에 묶음 밖 파일이 있다: {', '.join(extra)}. 옮기거나 지운 뒤 다시 실행하거나 --out을 바꾼다.")
    os.makedirs(bundle, exist_ok=True)


def main():
    ap = argparse.ArgumentParser(description="한국어 독화 표준 리소스 공개 배포 묶음 만들기(어디에도 올리지 않는다)")
    ap.add_argument("--out", default=_DEFAULT_OUT,
                    help="묶음 폴더를 만들 상위 폴더(기본: 저장소의 release/)")
    ap.add_argument("--include-data-derived", action="store_true",
                    help=f"AI Hub 538 유래 {DATA_DERIVED_KEY}를 넣는다. AI Hub의 재배포 확인을 받은 뒤에만 쓴다")
    args = ap.parse_args()
    include = args.include_data_derived

    res = load_source(_SRC)
    semver = res["meta"]["semver"]
    check_code_semver(semver)
    check_difficulty_formula(res["difficulty_index"])
    if res.get(DATA_DERIVED_KEY):
        check_data_derived(res[DATA_DERIVED_KEY])
    check_release_info()

    rel = build_resource(res, include)
    s = summarize(rel)
    name = f"{BUNDLE_PREFIX}-{semver}" + ("-with-data-derived" if include else "")
    bundle = os.path.join(os.path.abspath(args.out), name)
    prepare_dir(bundle)

    texts = {
        "perceptual-resources.json": json.dumps(rel, ensure_ascii=False, indent=2) + "\n",
        "README.md": build_readme(rel["meta"], s, include),
        "LICENSE.md": build_license(rel["meta"], include),
        "CITATION.cff": build_cff(rel["meta"], s, include),
        "zenodo.json": json.dumps(build_zenodo(rel["meta"], s, include), ensure_ascii=False, indent=2) + "\n",
    }
    # 바이트로 직접 써서 운영체제와 무관하게 줄바꿈(LF)과 체크섬이 같게 한다.
    blobs = {n: t.encode("utf-8") for n, t in texts.items()}
    blobs[SUMS] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(blobs.items())).encode("ascii")
    for n, b in blobs.items():
        with open(os.path.join(bundle, n), "wb") as f:
            f.write(b)

    if include:
        _warn(f"{DATA_DERIVED_KEY}를 넣었다. AI Hub에서 재배포 확인을 받은 경우에만 이 묶음을 게시한다.")
    else:
        print(f"{DATA_DERIVED_KEY}는 뺐다(기본값).", file=sys.stderr)
    left = remaining_placeholders()
    if left:
        _warn(f"게시 전에 채울 자리표시 {len(left)}개(스크립트의 RELEASE_INFO): " + ", ".join(left))
    print(f"RELEASE_OK {bundle} files={len(blobs)}")


if __name__ == "__main__":
    main()
