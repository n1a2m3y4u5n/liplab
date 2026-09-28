#!/usr/bin/env python
"""
학습 콘텐츠 품질 감사(9/28, docs/content-audit-2026-09-28.md).

규칙으로 볼 수 있는 것만 기계적으로 점검한다. 문장이 자연스러운지, 보기 둘이 모두 문맥에 맞는지 같은 판단은 사람이 읽고
curriculum의 제외 목록(STAGE2_EXCLUDED·CLOSURE_EXCLUDED)과 문서에 남긴다. 이 스크립트는 그 결과가 규칙과 어긋나지 않는지도 본다.

  python scripts/content_audit.py            # 사람이 읽는 보고서
  python scripts/content_audit.py --json     # 항목별 원자료(JSON)
  python scripts/content_audit.py --strict   # 불변 조건(아래 '오류')이 하나라도 깨지면 종료 코드 1

오류(고쳐야 하는 것, _ERROR_KEYS): 짝의 관계 표시가 없거나 규칙과 다름·최소대립쌍이 자모 두 자리 이상 다름·같아 보임 표시가
입모양 규칙과 다름·중복, 단어 중복·형식·등급 값, 서빙 문맥 문항의 거의 같은 문장·문장 부호·없는 제외 id, 대화 대체 대사가 단계
길이를 넘거나 단계에 맞는 대사를 다 쓰기 전에 되풀이됨, 대체 문장이 단계 길이·어절 수 밖, 말하기 풀의 중복·드문 말, 억양 표시와
문장 부호가 어긋남. 참고(판단 재료): 빈도와 등급의 차이, 발음 규칙으로 입모양 열이 바뀌는 단어, 짝의 자모 거리 분포, 드문 말이
든 짝·문항, 비슷한 문장.

외부 파일은 받지 않는다. 빈도는 content_rules가 쓰는 wordfreq 사전(설치돼 있을 때만)을 그대로 쓴다.
"""
import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(os.path.dirname(_HERE), "backend")
sys.path.insert(0, _BACKEND)

import assessment as A  # noqa: E402
import content_rules as R  # noqa: E402
import curriculum as C  # noqa: E402
import engine as E  # noqa: E402

# 서빙 문맥 문항 두 개가 정답이 같고 글자 열이 _NEAR_DUP 이상 겹치면 '거의 같은 문장'(오류, 한 레슨에 겹쳐 나온다),
# _SIMILAR 이상이면 '비슷한 문장'(참고, 사람이 읽고 판단한다. 예: 말이 씨가 된다 / 말이 씨알도 안 먹힌다는 다른 관용구).
_NEAR_DUP = 0.7
_SIMILAR = 0.6
_WH = ("누구", "누가", "뭐", "무엇", "무슨", "어디", "언제", "왜", "어떻게", "어떤", "얼마", "몇")


def _jamo_distance(a, b):
    sa, sb = R._jamo_seq(a), R._jamo_seq(b)
    if not sa or not sb or len(sa) != len(sb):
        return None
    return sum(x != y for x, y in zip(sa, sb))


def _consonant_ui(word):
    """자음 뒤 ㅢ(흰색·희망 [힌색·히망], 표준 발음법 5항): 입모양 엔진은 이중모음(9)으로 보여 실제 발음 [ㅣ](3)과 다르다."""
    for ch in word:
        if R._is_hangul(ch):
            ini, med, _ = E.decompose_hangul(ch)
            if med == "ㅢ" and ini and ini != "ㅇ":
                return True
    return False


# ── 단어 은행 ────────────────────────────────────────────────────────────────
def audit_words():
    tw = A.test_only_words()
    ex = C.STAGE2_EXCLUDED
    words = [w["word"] for w in C.WORD_BANK]
    served = [w for w in C.WORD_BANK if w["word"] not in tw and w["word"] not in ex]
    out = {"n": len(words), "n_served": len(served), "n_test": len(set(words) & tw), "n_excluded": len(set(words) & set(ex))}
    out["duplicates"] = sorted(w for w, n in Counter(words).items() if n > 1)
    out["bad_form"] = [w for w in words if not R.check_word(w, max_syllable=4)[0]]
    out["bad_tier"] = [w["word"] for w in C.WORD_BANK if w.get("tier") not in (1, 2, 3)]
    out["tier_counts"] = dict(sorted(Counter(w.get("tier") for w in served).items()))
    # 빈도 등급과 두 칸 이상 어긋나는 서빙 단어(참고). 한국어 웹 말뭉치 빈도는 한 음절 동형이의어(도·만·이)를 부풀리고
    # 아이들이 아는 구체 명사(공책·지우개)를 낮게 잡아, 등급은 사람이 고친 값이 우선이다.
    gap = []
    if R.HAS_FREQUENCY:
        for w in served:
            ft = R.tier_of(w["word"])
            if abs(ft - w["tier"]) >= 2:
                gap.append({"word": w["word"], "tier": w["tier"], "freq_tier": ft, "zipf": R.word_zipf(w["word"])})
    out["tier_freq_gap"] = gap
    # 발음 규칙으로 입모양 열이 표기와 달라지는 단어(엔진이 처리함, 참고)와 엔진이 처리하지 못하는 자음 뒤 ㅢ
    pron = []
    for w in words:
        spelled = []
        for ch in w:
            ini, med, fin = E.decompose_hangul(ch)
            spelled += [E.VISEME_MAP.get(j) for j in ((ini if ini != "ㅇ" else ""), med, fin) if j]   # 초성 ㅇ은 무음
        if R.word_visemes(w) != [v for v in spelled if v not in (None, 14, 15)]:
            pron.append(w)
    out["pronunciation_changes"] = pron
    out["consonant_ui"] = [w for w in words if _consonant_ui(w)]
    return out


# ── 최소대립쌍·동구형이음 짝 ──────────────────────────────────────────────────
def audit_pairs():
    tw = A.test_only_words()
    ex = C.STAGE2_EXCLUDED
    bank = {w["word"] for w in C.WORD_BANK}
    out = defaultdict(list)
    seen = Counter(frozenset((p["a"], p["b"])) for p in C.MINIMAL_PAIRS)
    out["duplicates"] = sorted("/".join(sorted(k)) for k, n in seen.items() if n > 1)
    dist = Counter()
    for p in C.MINIMAL_PAIRS:
        a, b = p["a"], p["b"]
        tag = f"{a}/{b}"
        d = _jamo_distance(a, b)
        dist[(p.get("relation", "(없음)"), d)] += 1
        ok, item, why = R.check_lookalike_pair(a, b)
        if not ok:
            out["not_teaching_pair"].append(f"{tag}: {why}")
            continue
        rel = p.get("relation")
        if rel is None:
            out["missing_relation"].append(f"{tag} (규칙: {item['relation']})")
        elif rel != item["relation"]:
            out["wrong_relation"].append(f"{tag}: {rel} → {item['relation']}")
        if rel == "minimal_pair" and d != 1:
            out["minimal_not_one_jamo"].append(f"{tag} (자모 {d}자리)")
        if bool(p.get("same_looking")) != R._visually_confusable(a, b):
            out["wrong_same_looking"].append(f"{tag}: {p.get('same_looking')} → {R._visually_confusable(a, b)}")
        note = p.get("note", "")
        if (p.get("same_looking") and "구별 가능" in note) or (not p.get("same_looking") and ("구별 불가" in note or "동일" in note)):
            out["note_contradicts_label"].append(f"{tag}: {note}")
        if a not in bank or b not in bank:
            out["not_in_bank"].append(tag)
        if a in ex or b in ex:
            out["rare_member"].append(tag)
        if a in tw or b in tw:
            out["test_word_member"].append(tag)
        if E.to_pronounced_syllables(a) == E.to_pronounced_syllables(b):
            out["same_pronunciation"].append(tag)
    out = {k: v for k, v in out.items()}
    out["n"] = len(C.MINIMAL_PAIRS)
    out["relation_distance"] = {f"{r}:{d}": n for (r, d), n in sorted(dist.items(), key=lambda x: (x[0][0], x[0][1] or 0))}
    out["same_looking"] = dict(Counter(bool(p.get("same_looking")) for p in C.MINIMAL_PAIRS))
    return out


# ── 문맥 추론 문항(문맥 추론 화면·2단계 레슨의 문맥 문항이 같은 풀) ──────────────
def _served_closures():
    tw = A.test_only_words()
    ex = C.CLOSURE_EXCLUDED
    status = {}
    served = []
    for c in C.CLOSURE_ITEMS:
        opts = c.get("options") or []
        ok, _, why = R.check_closure(c.get("display", ""), c["answer"], opts, hint=c.get("hint"),
                                     compound=bool(c.get("compound")))
        if c["id"] in ex:
            status[c["id"]] = "excluded"
        elif not ok:
            status[c["id"]] = "gate: " + why
        elif c["answer"] in tw or set(opts) & tw:
            status[c["id"]] = "test_word"
        elif len(opts) < 3:
            status[c["id"]] = "two_options"
        else:
            status[c["id"]] = "served"
            served.append(c)
    return served, status


def audit_closures():
    served, status = _served_closures()
    ex_words = C.STAGE2_EXCLUDED
    out = {"n": len(C.CLOSURE_ITEMS), "n_served": len(served)}
    out["status"] = dict(Counter(s.split(":")[0] for s in status.values()))
    out["gate_reasons"] = dict(Counter(s[6:] for s in status.values() if s.startswith("gate: ")))
    ids = Counter(c["id"] for c in C.CLOSURE_ITEMS)
    out["duplicate_ids"] = sorted(i for i, n in ids.items() if n > 1)
    out["stale_exclusions"] = sorted(set(C.CLOSURE_EXCLUDED) - set(ids))
    # 2단계에서 뺀 말이 정답인 문항(참고): 합성어(놋그릇)나 동사 활용(매듭을 푼)처럼 문맥 안에서는 쓰이는 경우가 있어 사람이 본다
    out["rare_answer"] = [f"{c['id']} {c['answer']}" for c in served if c["answer"] in ex_words]
    out["rare_distractor"] = [f"{c['id']} {o}" for c in served for o in c["options"] if o != c["answer"] and o in ex_words]
    out["no_final_punct"] = [f"{c['id']} {c['display']}" for c in served if not re.search(r"[.?!]$", c["display"].strip())]
    near, similar = [], []
    for i, a in enumerate(served):
        for b in served[i + 1:]:
            if a["answer"] != b["answer"]:
                continue
            r = difflib.SequenceMatcher(None, a["display"], b["display"]).ratio()
            if r >= _SIMILAR:
                (near if r >= _NEAR_DUP else similar).append(f"{a['id']}~{b['id']} ({r:.2f}) {a['display']} / {b['display']}")
    out["near_duplicates"] = near
    out["similar"] = similar
    out["answer_counts"] = dict(Counter(c["answer"] for c in served).most_common(8))
    return out


# ── 대화·상황 문장 대체 콘텐츠 ────────────────────────────────────────────────
def audit_conversation():
    import llm_service as L
    import conversation_scenario as CS
    out = {}
    lim = L._CONV_MAX_CHARS
    # 대화 대체 대사: 단계마다 그 단계 길이에 맞는 대사가 있고, 대화가 이어질 때 같은 대사를 연달아 되풀이하지 않는가
    fits = {}
    for sit, lines in list(L.FALLBACK_TURNS.items()) + [("(일반)", L.FALLBACK_TURNS_GENERIC)]:
        for lv in sorted(lim):
            fits[f"{sit}:{lv}"] = sum(1 for t in lines if len(t) <= lim[lv])
    out["turn_lines_fitting_level"] = fits
    over, repeats = [], []
    pick = getattr(L, "fallback_turn", None)
    for sit in list(L.FALLBACK_TURNS) + ["(목록에 없는 상황)"]:
        for lv in (1, 2, 3, 4, 5):
            hist, said = [], []
            for _ in range(6):
                if pick:
                    t = pick(sit, lv, hist)
                else:   # 예전 방식(9/28 전): 대화 기록 길이로 순환
                    fb = L.FALLBACK_TURNS.get(sit) or L.FALLBACK_TURNS_GENERIC
                    t = fb[len(hist) % len(fb)]
                if not L.conv_turn_ok(t, lv):
                    over.append(f"{sit} {lv}단계: {t} ({len(t)}자 > {lim.get(lv)})")
                said.append(t)
                hist += [{"role": "assistant", "content": t}, {"role": "user", "content": t}]
            n_rep = len(said) - len(set(said))
            n_fit = sum(1 for x in set(L.FALLBACK_TURNS.get(sit) or L.FALLBACK_TURNS_GENERIC) if L.conv_turn_ok(x, lv))
            if n_rep > max(0, len(said) - n_fit):          # 단계에 맞는 대사를 다 쓰기 전에 되풀이
                repeats.append(f"{sit} {lv}단계 6턴: {' / '.join(said)}")
    out["turn_over_length"] = sorted(set(over))
    out["turn_repeats"] = repeats
    # 상황별 시나리오 대체 문장: 단계 길이·어절 수
    bad = []
    for lv, bank in L.FALLBACK_BY_LEVEL.items():
        for s in bank:
            ok, _, why = R.check_sentence(s, max_chars=L.SCENARIO_MAX_CHARS.get(lv, 40))
            if not ok:
                bad.append(f"{lv}단계 {s}: {why}")
            if len(s.split()) < L.SCENARIO_MIN_WORDS.get(lv, 1):
                bad.append(f"{lv}단계 {s}: 어절 {len(s.split())} < {L.SCENARIO_MIN_WORDS[lv]}")
    for sit, bank in L._SITUATION_DEFAULTS.items():
        for s in bank:
            ok, _, why = R.check_sentence(s, max_chars=L.SCENARIO_MAX_CHARS[1])
            if not ok:
                bad.append(f"{sit} 기본 {s}: {why}")
    out["scenario_bad"] = bad
    allsent = [s for b in L.FALLBACK_BY_LEVEL.values() for s in b] + [s for b in L._SITUATION_DEFAULTS.values() for s in b]
    out["scenario_duplicates"] = sorted(s for s, n in Counter(allsent).items() if n > 1)
    # 다자 대화 대체 대사(장면별): 같은 장면 안 중복, 한 턴 길이(3단계 6~14자에 여유)
    ml = []
    for scene, lines in list(CS._FALLBACK_LINES.items()) + [("(일반)", CS._GENERIC_LINES)]:
        if len(set(lines)) != len(lines):
            ml.append(f"{scene}: 중복 대사")
        ml += [f"{scene}: {t} ({len(t)}자)" for t in lines if not (3 <= len(t) <= 16)]
    out["multi_lines_bad"] = ml
    return out


# ── 말하기 ────────────────────────────────────────────────────────────────────
def audit_speaking():
    import speak_curriculum as S
    out = {}
    st4 = S._BY_STAGE[4]["items"]
    words = [it["target"] for it in st4]
    out["stage4_n"] = len(words)
    out["stage4_duplicates"] = sorted(w for w, n in Counter(words).items() if n > 1)
    skip = A.test_only_words() | set(C.STAGE2_EXCLUDED)
    out["stage4_excluded_leak"] = [w for w in words if w in skip]
    out["stage4_bad_form"] = [w for w in words if not R.check_word(w, max_syllable=4)[0]]
    bad = []
    for it in S._BY_STAGE[5]["items"]:
        t, lab = it["target"].strip(), it.get("intonation")
        want = "rise" if t.endswith("?") else "fall" if t.endswith(".") else None
        if want != lab:
            bad.append(f"{t}: {lab} (문장 부호로는 {want})")
        if lab == "rise" and any(t.startswith(w) or f" {w}" in t for w in _WH):
            bad.append(f"{t}: 의문사 의문문은 끝을 내린다(예/아니오 의문문만 올림)")
    out["stage5_intonation"] = bad
    s5 = [it["target"] for it in S._BY_STAGE[5]["items"]]
    out["stage5_duplicates"] = sorted(s for s, n in Counter(s5).items() if n > 1)
    return out


_ERROR_KEYS = {
    "pairs": ("duplicates", "not_teaching_pair", "wrong_relation", "missing_relation", "minimal_not_one_jamo",
              "wrong_same_looking", "note_contradicts_label", "same_pronunciation"),
    "words": ("duplicates", "bad_form", "bad_tier"),
    "closures": ("duplicate_ids", "stale_exclusions", "near_duplicates", "no_final_punct"),
    "conversation": ("turn_over_length", "turn_repeats", "scenario_bad", "scenario_duplicates", "multi_lines_bad"),
    "speaking": ("stage4_duplicates", "stage4_excluded_leak", "stage4_bad_form", "stage5_intonation", "stage5_duplicates"),
}


def run():
    return {"words": audit_words(), "pairs": audit_pairs(), "closures": audit_closures(),
            "conversation": audit_conversation(), "speaking": audit_speaking()}


def errors(rep):
    return {f"{sec}.{k}": rep[sec][k] for sec, keys in _ERROR_KEYS.items() for k in keys if rep[sec].get(k)}


def _print(rep):
    for sec, body in rep.items():
        print(f"\n== {sec} ==")
        for k, v in body.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)}")
                for x in v[:12]:
                    print(f"      {x}")
                if len(v) > 12:
                    print(f"      … 외 {len(v) - 12}")
            else:
                print(f"  {k}: {v}")
    errs = errors(rep)
    print(f"\n불변 조건 위반: {sum(len(v) for v in errs.values())}건" + (f" ({', '.join(errs)})" if errs else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    os.environ.pop("ANTHROPIC_API_KEY", None)   # 감사는 유료 API를 부르지 않는다(llm_service는 run 안에서 처음 불러온다)
    rep = run()
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    else:
        _print(rep)
    sys.exit(1 if a.strict and errors(rep) else 0)
