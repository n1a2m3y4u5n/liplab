"""
디지털 독화 표준검사 검증 테스트 — 고도화 축 I.
배치검사 문항 구성과 채점이 난이도·정오에 맞게 동작하는지 확인한다. 외부 의존성 없음.
실행: python3 test_assessment.py
"""
import assessment as A
import curriculum as C


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def _words():
    return [w["word"] for w in C.WORD_BANK]


def test_build_items():
    items = A.build_placement_items(_words(), n=6, seed=1)
    _ok(len(items) == 6, "요청한 문항 수")
    _ok(all(it["word"] in it["options"] for it in items), "정답이 보기에 포함")
    _ok(all(len(it["options"]) == 4 for it in items), "4지선다")
    _ok(items[0]["difficulty"] <= items[-1]["difficulty"], "쉬움→어려움 순")


def test_score_all_correct():
    items = A.build_placement_items(_words(), n=6, seed=1)
    resp = {it["id"]: it["word"] for it in items}
    r = A.score_placement(items, resp)
    _ok(r["correct"] == 6 and r["accuracy"] == 1.0, "전부 정답")
    _ok(r["error_visemes"] == [], "다 맞으면 오류 음소 없음")
    _ok(1 <= r["level"] <= 5 and "recommended_start" in r, "수준·시작단계 추천")


def test_score_all_wrong():
    items = A.build_placement_items(_words(), n=6, seed=1)
    resp = {it["id"]: (it["options"][0] if it["options"][0] != it["word"] else it["options"][1])
            for it in items}
    r = A.score_placement(items, resp)
    _ok(r["correct"] == 0 and r["level"] == 1, "전부 오답이면 최저 수준")
    _ok(len(r["error_visemes"]) > 0, "틀린 문항의 음소가 오류 프로파일에")


def test_empty_response():
    r = A.score_placement([], {})
    _ok(r["level"] == 1 and r["recommended_start"]["key"] == "viseme", "무응답 기본 수준")


def _form_log(items, wrong_ids):
    """폼 문항을 wrong_ids만 틀리게(정답이 아닌 첫 보기) 풀었을 때의 score_placement 결과."""
    resp = {it["id"]: (next(o for o in it["options"] if o != it["word"]) if it["id"] in wrong_ids else it["word"])
            for it in items}
    return A.score_placement(items, resp)


def _full_viseme_errors(items, wrong_ids):
    """저장된 문항 입모양(it['visemes'])으로 센 전체 오류 수. 구현과 따로 세는 기준값."""
    c = {}
    for it in items:
        if it["id"] in wrong_ids:
            for v in it["visemes"]:
                c[v] = c.get(v, 0) + 1
    return c


def test_improvement_delta():
    base = {"accuracy": 0.4, "ability": 0.25, "level": 2, "error_visemes": [6, 7, 10]}
    late = {"accuracy": 0.8, "ability": 0.75, "level": 4, "error_visemes": [10]}
    d = A.improvement_delta(base, late)
    _ok(abs(d["accuracy"] - 0.4) < 1e-9, "정답률 향상 +0.4")
    _ok(abs(d["ability"] - 0.5) < 1e-9, "능력 향상 +0.5")
    _ok(d["level"] == 2, "수준 +2")
    # 문항 기록이 없는 옛 검사는 잘린 상위 3개로 극복을 정하지 않고 비운다
    _ok(d["resolved_visemes"] == [] and d["new_error_visemes"] == [], "문항 기록이 없으면 극복·신규를 비운다")
    # 문항 기록이 있으면: 첫 검사에서 틀린 입모양을 최근 검사에서 모두 맞혔다
    items = A.frozen_forms(build_if_missing=False)["A"]
    wrong = {it["id"] for it in items[:4]}
    s0, s1 = _form_log(items, wrong), _form_log(items, set())
    d = A.improvement_delta(s0, s1, s0["item_log"], s1["item_log"])
    _ok(d["resolved_visemes"] == sorted(_full_viseme_errors(items, wrong)), "극복한 취약 입모양")
    _ok(d["new_error_visemes"] == [], "새로 약해진 것 없음")


def test_improvement_delta_regression():
    # 나빠진 경우도 음수로 정확히 표현
    d = A.improvement_delta({"accuracy": 0.6, "ability": 0.5, "level": 3, "error_visemes": []},
                            {"accuracy": 0.5, "ability": 0.5, "level": 3, "error_visemes": [1]})
    _ok(d["accuracy"] < 0, "정답률 하락은 음수")
    items = A.frozen_forms(build_if_missing=False)["A"]
    wrong = {items[5]["id"]}
    s0, s1 = _form_log(items, set()), _form_log(items, wrong)
    d = A.improvement_delta(s0, s1, s0["item_log"], s1["item_log"])
    _ok(d["new_error_visemes"] == sorted(set(items[5]["visemes"])), "새로 약해진 입모양 표시")
    _ok(d["resolved_visemes"] == [], "극복 없음")


def test_resolved_visemes_use_full_counts_not_top3():
    # 감사 재현(폼 A, 두 검사 모두 6문항 오답): 예전에는 상위 3개끼리 비교해 극복 목록이 뜬 보고서의 99%가
    # 최근 검사에서도 틀린 입모양을 '이제 안 틀리는 입모양'으로 보였다. 이제 극복은 최근 검사 오류 0이고 풀어 본 입모양뿐이다.
    import random
    items = A.frozen_forms(build_if_missing=False)["A"]
    ids = [it["id"] for it in items]
    rng = random.Random(0)
    shown = stale = 0
    for _ in range(300):
        w0, w1 = set(rng.sample(ids, 6)), set(rng.sample(ids, 6))
        s0, s1 = _form_log(items, w0), _form_log(items, w1)
        f0, f1 = _full_viseme_errors(items, w0), _full_viseme_errors(items, w1)
        top3_resolved = set(s0["error_visemes"]) - set(s1["error_visemes"])
        stale += any(f1.get(v, 0) for v in top3_resolved)
        d = A.improvement_delta(s0, s1, s0["item_log"], s1["item_log"])
        expect = sorted(v for v in f0 if not f1.get(v))            # 폼 A는 입모양 1~10을 모두 묻는다
        _ok(d["resolved_visemes"] == expect, f"극복 = 첫 검사 오류 > 0, 최근 오류 0: {d['resolved_visemes']} != {expect}")
        _ok(d["new_error_visemes"] == sorted(v for v in f1 if not f0.get(v)), "신규도 전체 개수로")
        shown += bool(d["resolved_visemes"])
    _ok(stale > 200, f"예전 방식이면 여전히 틀리는 입모양이 극복으로 나온다(재현 확인): {stale}")
    _ok(shown > 0, "진짜 극복한 입모양은 계속 보인다")


def test_error_counts_match_stored_visemes_and_score_placement():
    f = A.frozen_forms(build_if_missing=False)
    for k in ("A", "B"):
        items = f[k]
        wrong = {it["id"] for it in items[::3]}
        s = _form_log(items, wrong)
        ec = A.error_counts(s["item_log"])
        _ok(dict(ec["visemes"]) == _full_viseme_errors(items, wrong), f"폼 {k}: item_log로 다시 센 입모양 오류 = 저장 입모양")
        top = [v for v, _ in ec["visemes"].most_common(3)]
        _ok(top == s["error_visemes"], "상위 3개는 저장값과 같다(같은 셈)")
        _ok({e["phoneme"]: e["count"] for e in s["error_phonemes"]}
            == {p: c for p, c in ec["phonemes"].most_common(6)}, "상위 6개 자모도 저장값과 같다")
    _ok(A.error_counts(None) is None and A.error_counts([]) is None, "기록 없음")
    _ok(A.error_counts([{"id": "q1", "word": "밥", "chosen": None}]) is None, "답한 문항이 없으면 None")


def test_phoneme_change_full_counts_and_tested_in_both():
    import random
    f = A.frozen_forms(build_if_missing=False)
    fa, fb = f["A"], f["B"]
    rng = random.Random(1)
    wa = set(rng.sample([it["id"] for it in fa], 6))
    wb = set(rng.sample([it["id"] for it in fb], 6))
    s0, s1 = _form_log(fa, wa), _form_log(fb, wb)
    rows = A.phoneme_change(s0["item_log"], s1["item_log"])
    in_a = {p for it in fa for p in A._word_phonemes(it["word"])}
    in_b = {p for it in fb for p in A._word_phonemes(it["word"])}
    _ok(rows and all(r["phoneme"] in in_a and r["phoneme"] in in_b for r in rows), "두 폼 모두 묻는 자모만 싣는다")
    ea, eb = A.error_counts(s0["item_log"]), A.error_counts(s1["item_log"])
    _ok(all(r["before"] == ea["phonemes"][r["phoneme"]] and r["after"] == eb["phonemes"][r["phoneme"]]
            and r["delta"] == r["after"] - r["before"] for r in rows), "전체 개수끼리 비교")
    _ok(A.phoneme_change(s0["item_log"], []) == [] and A.phoneme_change(None, s1["item_log"]) == [],
        "문항 기록이 없는 검사가 끼면 비운다")


def test_adaptive_staircase():
    """적응형(축 I): 정답이면 다음 문항이 더 어렵고, 오답이면 더 쉬워야 한다."""
    words = _words()
    it1 = A.select_next_item([], {}, words, seed=0)
    _ok(it1 is not None and len(it1["options"]) == 4, "첫 문항 4지선다")
    # 정답
    up = A.select_next_item([it1], {it1["id"]: it1["word"]}, words, seed=0)
    _ok(up["difficulty"] >= it1["difficulty"] - 1e-9, "정답 후 난이도 상승(또는 동급)")
    # 오답
    wrong = next(o for o in it1["options"] if o != it1["word"])
    est = A.estimate_ability([it1], {it1["id"]: wrong})
    down = A.select_next_item([it1], {it1["id"]: wrong}, words, seed=0)
    _ok(est["ability"] < 0.5, "오답 후 능력추정 하락")
    _ok(down["difficulty"] <= it1["difficulty"] + 1e-9, "오답 후 난이도 하락(또는 동급)")


def test_adaptive_no_repeat_and_targets():
    """적응형: 같은 단어를 중복 출제하지 않고, 오답 자질을 표적으로 반영한다."""
    words = _words()
    asked, resp = [], {}
    first = A.select_next_item([], {}, words, seed=1)
    asked.append(first)
    # 첫 문항 오답으로 표적 자질 생성
    resp[first["id"]] = next(o for o in first["options"] if o != first["word"])
    seen = {first["word"]}
    for _ in range(7):
        nx = A.select_next_item(asked, resp, words, seed=len(asked))
        if nx is None:
            break
        _ok(nx["word"] not in seen, "이미 낸 단어 중복 금지")
        seen.add(nx["word"]); asked.append(nx); resp[nx["id"]] = nx["word"]
    _ok(len(seen) >= 6, "적응형으로 여러 문항 생성")


def test_adaptive_stops_when_stage_is_clear():
    """적응형 길이(docs/assessment-design.md 12절): 최소 5문항 뒤 한 시작 단계의 사후 확률이 0.85 이상이면 끝낸다."""
    def run(pattern):
        asked, resp = [], {}
        for i, (d, ok) in enumerate(pattern):
            it = {"id": f"q{i + 1}", "word": "정답", "difficulty": d, "visemes": [], "options": ["정답", "a", "b", "c"]}
            asked.append(it)
            resp[it["id"]] = "정답" if ok else "a"
        return A.estimate_ability(asked, resp)
    pr = A.stage_probabilities([(0.6, True, 4), (0.7, False, 4)])
    _ok(abs(sum(pr) - 1) < 1e-9 and len(pr) == 3, "세 단계 확률의 합은 1")
    strong = run([(0.6, True), (0.7, True), (0.8, True), (0.85, True), (0.87, True)])
    _ok(strong["confident"] and strong["stage_confidence"] >= A.STOP_CONFIDENCE, "어려운 문항을 모두 맞히면 5문항에서 끝")
    _ok(not run([(0.6, True)] * 4)["confident"], "5문항 전에는 끝내지 않는다")
    edge = run([(0.6, True), (0.7, False), (0.65, True), (0.72, True), (0.76, False)])
    _ok(not edge["confident"], "단계 경계 근처면 계속 낸다")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")


def test_no_homophene_distractors():
    # 입모양이 정답과 완전히 같은 보기는 입만 보고 풀 수 없어 문항 타당도를 해친다 → 없어야 한다.
    words = [w["word"] for w in C.WORD_BANK]
    forms = A.build_progression_forms(words, n=8)
    for k in ("A", "B"):
        for it in forms[k]:
            for o in it["options"]:
                if o != it["word"]:
                    _ok(A.viseme_distance(it["word"], o) > 0, f"동구형이음 보기 {it['word']}/{o}")


def test_frozen_forms_v1():
    f = A.frozen_forms(build_if_missing=False)
    _ok(f is not None and f["version"] == A.FORMS_VERSION, "지금 판본의 동결 파일이 있어야 한다")
    L = A.FORM_LENGTH
    _ok(len(f["A"]) == L and len(f["B"]) == L, "A·B 각 FORM_LENGTH문항")
    da = sum(i["difficulty"] for i in f["A"]) / L
    db = sum(i["difficulty"] for i in f["B"]) / L
    _ok(abs(da - db) < 0.02, "동형: 평균 난이도 차 < 0.02")
    tw = A.test_only_words()
    _ok(len(tw) == 2 * L and not ({i["word"] for i in f["A"]} & {i["word"] for i in f["B"]}), "A·B 문항 겹침 없음")


def test_forms_v2_revision():
    """v2(9/27): v1과 정답·문항 수가 같고, 입모양으로 가를 수 없는 오답과 드문 말 오답이 없다(docs/assessment-design.md 7절)."""
    import json, os
    import curriculum as C
    v1 = json.load(open(os.path.join(os.path.dirname(A._FORMS_PATH), "forms_v1.json"), encoding="utf-8"))
    v2 = A.frozen_forms(build_if_missing=False)
    _ok(v2["version"] == "v2" and v2.get("revised_from") == "v1", "판본 v2, v1에서 개정")
    words = lambda f: sorted(it["word"] for k in ("A", "B") for it in f[k])   # noqa: E731
    _ok(words(v1) == words(v2), "정답 48개는 v1과 같다(훈련에서 빼는 단어가 바뀌지 않는다)")
    # 9/28 콘텐츠 감사가 2단계에서 더 뺀 드문 말 가운데 v2 오답에 이미 든 7개. 폼은 사전·사후 비교를 위해 동결이라 바꾸지 않는다
    # (docs/content-audit-2026-09-28.md 1절). 다음 판본을 만들 때 revise_forms가 이 오답도 바꾼다.
    frozen_rare = {"사무", "박", "공무", "공모", "능", "솔", "사부"}
    bad = [(it["id"], o) for k in ("A", "B") for it in v2[k] for o in it["options"]
           if o != it["word"] and (A.indistinguishable(it["word"], o) or (o in C.STAGE2_EXCLUDED and o not in frozen_rare))]
    _ok(not bad, f"가를 수 없는 오답·드문 말 오답이 없다: {bad}")
    _ok(all(len(it["options"]) == 4 and it["word"] in it["options"] for k in ("A", "B") for it in v2[k]), "4지선다 유지")
    _ok(A.indistinguishable("닭", "갓") and not A.indistinguishable("닭", "담"), "입 안쪽 차이가 두 자리여도 가를 수 없다")


def test_score_logs_items_and_confusion_direction():
    f = A.frozen_forms(build_if_missing=False)
    items = f["A"]
    wrong = {it["id"]: next(o for o in it["options"] if o != it["word"]) for it in items[:3]}
    r = A.score_placement(items, wrong)
    _ok(len(r["item_log"]) == len(items), "문항 단위 기록(미응답 포함)")
    _ok(sum(1 for x in r["item_log"] if x["chosen"] is None) == len(items) - 3, "미응답은 chosen=None")
    _ok(all({"target", "read", "count"} <= set(c) for c in r["error_confusions"]), "오독 방향 필드")


def test_error_phonemes_count_only_misread_jamo():
    # 밥을 맘으로 읽었다 → 틀린 자모는 초성 ㅂ(→ㅁ)뿐. 모음 ㅏ나 종성 ㅂ은 오류로 세지 않는다.
    items = [{"id": "q1", "word": "밥", "options": ["밥", "맘", "발", "방"], "visemes": [1, 2], "difficulty": 0.5}]
    r = A.score_placement(items, {"q1": "맘"})
    phs = {e["phoneme"]: e["count"] for e in r["error_phonemes"]}
    assert "ㅏ" not in phs and sum(phs.values()) <= 2
    assert r["error_confusions"], "무엇을 무엇으로 읽었는지도 남아야 한다"


def test_silent_onset_is_not_a_missed_sound():
    # 아이를 바이로 읽었다 → 없는 자음(ㅂ)을 읽은 것이지 ㅇ이라는 소리를 놓친 것이 아니다('자주 놓친 소리 ㅇ'이 뜨던 것)
    items = [{"id": "q1", "word": "아이", "options": ["아이", "바이", "오이", "마이"], "visemes": [2, 3], "difficulty": 0.5}]
    r = A.score_placement(items, {"q1": "바이"})
    assert "ㅇ" not in {e["phoneme"] for e in r["error_phonemes"]}
    assert r["error_confusions"] and r["error_confusions"][0]["target"] == "ㅇ", "오독 방향 기록은 남긴다"


def test_lucky_guess_on_hardest_item_does_not_jump_level():
    # 폼 A 24문항에서 가장 어려운 문항 하나만 맞히고(찍기) 나머지는 틀림 → 예전(맞힌 최고 난이도 0.833)은 수준 4, 문장 단계 추천
    f = A.frozen_forms(build_if_missing=False)
    items = f["A"]
    hardest = max(items, key=lambda it: it["difficulty"])
    resp = {it["id"]: (it["word"] if it is hardest else next(o for o in it["options"] if o != it["word"])) for it in items}
    r = A.score_placement(items, resp)
    _ok(r["level"] <= 2 and r["recommended_start"]["key"] != "sentence", f"찍어 맞힌 한 문항으로 수준이 뛰면 안 된다: {r['level']}")
    # 쉬운 문항부터 대부분 맞히고 어려운 문항 일부를 틀리면 높은 수준
    ordered = sorted(items, key=lambda it: it["difficulty"])
    resp2 = {it["id"]: (it["word"] if i < 21 else next(o for o in it["options"] if o != it["word"])) for i, it in enumerate(ordered)}
    _ok(A.score_placement(items, resp2)["level"] >= 3, "대부분 맞히면 높은 수준")


def test_rescore_log_matches_score():
    f = A.frozen_forms(build_if_missing=False)
    items = f["A"]
    resp = {it["id"]: it["word"] for it in items[:10]}
    r = A.score_placement(items, resp)
    again = A.rescore_log(r["item_log"])
    _ok(again["ability"] == r["ability"] and again["level"] == r["level"], "저장된 문항 기록으로 다시 채점해도 같다")
    _ok(A.rescore_log([]) is None and A.rescore_log([{"id": "x", "chosen": None, "difficulty": 0.5}]) is None, "답한 문항이 없으면 None")
