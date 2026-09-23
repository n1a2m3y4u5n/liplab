"""콘텐츠 사람검수(축 G) 순수 로직 테스트 — 파일 쓰기 없이 키·대기목록 구조만 검증."""
import content_review as cr


def _ok(c, m):
    assert c, "FAIL: " + m


def test_key_stability():
    # 쌍은 순서 무관해야 중복 판정이 정확
    _ok(cr._key("pairs", {"a": "밥", "b": "맘"}) == cr._key("pairs", {"a": "맘", "b": "밥"}), "쌍 키 순서무관")
    _ok(cr._key("words", {"word": "책상"}) == "책상", "단어 키=단어")
    # 문항 키는 내용(display|answer) — 배치마다 재사용되는 id(g1…)에 기대지 않는다
    _ok(cr._key("closures", {"id": "g1", "display": "x", "answer": "a"}) == "x|a", "문항 키=내용")
    _ok(cr._key("closures", {"id": "g1", "display": "x", "answer": "a"})
        != cr._key("closures", {"id": "g1", "display": "y", "answer": "b"}), "같은 id·다른 내용은 다른 키")


def test_pending_structure():
    p = cr.pending()  # 읽기 전용(파일 미변경)
    _ok(set(p["pending"]) >= {"words", "pairs", "closures"}, "대기 종류 3가지")
    for k in ("words", "pairs", "closures"):
        c = p["counts"][k]
        _ok(all(x in c for x in ("pending", "approved", "rejected", "candidates")), "카운트 필드")
        _ok(c["pending"] >= 0, "대기 수 음수 아님")


_CL = {"display": "오늘 ___ 이 유난히 밝네.", "answer": "달", "options": ["달", "살", "쌀"], "id": "g1"}


def test_review_logs_reviewer_and_content_id():
    """승인하면 review_log에 가명 태그·일시가 남고, 문항 id는 배치 번호(g1) 대신 내용 기반으로 바뀐다(4.4-4)."""
    import json, os, tempfile
    old = (cr._APPROVED, cr._REJECTED)
    with tempfile.TemporaryDirectory() as d:
        cr._APPROVED, cr._REJECTED = os.path.join(d, "approved.json"), os.path.join(d, "rejected.json")
        try:
            r = cr.review("closures", dict(_CL), "approve", reviewer="op-test", now="2026-09-23T00:00:00Z")
            again = cr.review("closures", dict(_CL), "approve", reviewer="op-test")
            store = json.load(open(cr._APPROVED, encoding="utf-8"))
        finally:
            cr._APPROVED, cr._REJECTED = old
    _ok(r["added"] and not again["added"], "같은 문항은 한 번만 추가")
    _ok(store["closures"][0]["id"] == cr.closure_id(_CL) != "g1", "내용 기반 id")
    log = store["meta"]["review_log"]
    _ok(len(log) == 1 and log[0]["by"] == "op-test" and log[0]["at"] == "2026-09-23T00:00:00Z"
        and log[0]["decision"] == "approve" and log[0]["key"] == "오늘 ___ 이 유난히 밝네.|달", "검수 기록")


def test_merge_union_and_regate():
    """두 판본 합집합 + 게이트 재검사: 2지 문항은 떨어지고, 다른 판본의 3지 판이 있으면 그쪽을 쓴다."""
    two = dict(_CL, options=["달", "살"])
    first = {"meta": {"review_log": [{"kind": "words", "key": "책상", "decision": "approve", "by": "cli", "at": "x"}]},
             "words": [{"word": "책상", "tier": 1}], "pairs": [{"a": "토끼", "b": "도끼"}],
             "closures": [two]}
    second = {"words": [{"word": "책상", "tier": 2}, {"word": "abc"}],
              "pairs": [{"a": "도끼", "b": "토끼"}, {"a": "책", "b": "책"}],
              "closures": [dict(_CL)]}
    merged, rep = cr.merge(first, second, now="2026-09-23T00:00:00Z")
    _ok(merged["meta"]["counts"] == {"words": 1, "pairs": 1, "closures": 1}, "합집합 개수")
    _ok(merged["words"][0]["tier"] == 1, "같은 단어는 첫 판본")
    _ok(merged["closures"][0]["options"] == ["달", "살", "쌀"], "3지 판을 씀")
    _ok(merged["closures"][0]["id"] == cr.closure_id(_CL), "문항 id 내용 기반")
    reasons = {(d["kind"], d["key"]) for d in rep["dropped"]}
    _ok(reasons == {("words", "abc"), ("pairs", "책|책")}, f"탈락 목록 {reasons}")
    _ok(rep["duplicates"] == {"words": 1, "pairs": 1, "closures": 0}, f"중복 {rep['duplicates']}")
    _ok(merged["meta"]["review_log"][0]["key"] == "책상" and merged["meta"]["review_log"][-1]["decision"] == "merge",
        "검수 기록 이어 붙임")


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("  ✓", n)
    print("통과")
