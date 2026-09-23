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


def test_improvement_delta():
    base = {"accuracy": 0.4, "ability": 0.25, "level": 2, "error_visemes": [6, 7, 10]}
    late = {"accuracy": 0.8, "ability": 0.75, "level": 4, "error_visemes": [10]}
    d = A.improvement_delta(base, late)
    _ok(abs(d["accuracy"] - 0.4) < 1e-9, "정답률 향상 +0.4")
    _ok(abs(d["ability"] - 0.5) < 1e-9, "능력 향상 +0.5")
    _ok(d["level"] == 2, "수준 +2")
    _ok(d["resolved_visemes"] == [6, 7], "극복한 취약 입모양")
    _ok(d["new_error_visemes"] == [], "새로 약해진 것 없음")


def test_improvement_delta_regression():
    # 나빠진 경우도 음수로 정확히 표현
    d = A.improvement_delta({"accuracy": 0.6, "ability": 0.5, "level": 3, "error_visemes": []},
                            {"accuracy": 0.5, "ability": 0.5, "level": 3, "error_visemes": [1]})
    _ok(d["accuracy"] < 0, "정답률 하락은 음수")
    _ok(d["new_error_visemes"] == [1], "새로 약해진 입모양 표시")


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
    _ok(f is not None and f["version"] == A.FORMS_VERSION, "v1 동결 파일이 있어야 한다")
    L = A.FORM_LENGTH
    _ok(len(f["A"]) == L and len(f["B"]) == L, "A·B 각 FORM_LENGTH문항")
    da = sum(i["difficulty"] for i in f["A"]) / L
    db = sum(i["difficulty"] for i in f["B"]) / L
    _ok(abs(da - db) < 0.02, "동형: 평균 난이도 차 < 0.02")
    tw = A.test_only_words()
    _ok(len(tw) == 2 * L and not ({i["word"] for i in f["A"]} & {i["word"] for i in f["B"]}), "A·B 문항 겹침 없음")


def test_score_logs_items_and_confusion_direction():
    f = A.frozen_forms(build_if_missing=False)
    items = f["A"]
    wrong = {it["id"]: next(o for o in it["options"] if o != it["word"]) for it in items[:3]}
    r = A.score_placement(items, wrong)
    _ok(len(r["item_log"]) == len(items), "문항 단위 기록(미응답 포함)")
    _ok(sum(1 for x in r["item_log"] if x["chosen"] is None) == len(items) - 3, "미응답은 chosen=None")
    _ok(all({"target", "read", "count"} <= set(c) for c in r["error_confusions"]), "오독 방향 필드")
