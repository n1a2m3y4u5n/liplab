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


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("  ✓", n)
    print("통과")
