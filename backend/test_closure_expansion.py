"""문맥 문항 확장(9/29, docs/closure-expansion-2026-09-29.md): 서빙 풀 크기, 문장 틀 중복, 검수 전 문항의 표시·조건."""
import difflib
import json
import os
import re
import tempfile

import assessment as A
import content_review as CR
import content_rules as R
import curriculum as C

# 서빙 문항 둘의 문장(빈칸 포함, 띄어쓰기·문장 부호 무시)이 이만큼 겹치면 같은 틀로 본다. 정답이 달라도 본다.
# 감사 스크립트의 '거의 같은 문장'(정답이 같을 때 0.7)과 같은 값이다. 9/29 기준 가장 비슷한 두 문장이 0.64.
_SAME_TEMPLATE = 0.7


def _served():
    import main
    return main._training_closures()


def _frame(display):
    return re.sub(r"[\s.,!?~]", "", display)


def test_served_pool_is_large_enough():
    # 3단계 문맥 추론 12문항 + 2단계 레슨마다 2문항이 같은 풀에서 나온다. 81개로는 일곱 레슨쯤부터 되풀이됐다.
    assert len(_served()) >= 200


def test_no_two_served_items_share_a_sentence_template():
    served = _served()
    frames = [_frame(c["display"]) for c in served]
    assert len(frames) == len(set(frames))
    close = []
    for i, a in enumerate(frames):
        for j in range(i + 1, len(frames)):
            r = difflib.SequenceMatcher(None, a, frames[j]).ratio()
            if r >= _SAME_TEMPLATE:
                close.append((round(r, 2), served[i]["display"], served[j]["display"]))
    assert not close, close[:5]


def _unreviewed():
    with open(C._UNREVIEWED_PATH, encoding="utf-8") as f:
        return json.load(f)["closures"]


def test_unreviewed_items_are_served_but_flagged():
    new = _unreviewed()
    assert len(new) >= 120
    served = {c["id"]: c for c in _served()}
    with open(C._APPROVED_PATH, encoding="utf-8") as f:
        approved = {(c["display"], c["answer"]) for c in json.load(f)["closures"]}
    for c in new:
        # 사람이 승인한 것처럼 approved.json에 넣지 않았고, 서빙되는 쪽에는 검수 대기 표시가 붙는다.
        # 사람이 읽고 뺀 문항(CLOSURE_EXCLUDED, 10/7 g3934e0dd)은 파일에 남지만 서빙되지 않는다
        assert (c["display"], c["answer"]) not in approved, c["id"]
        if c["id"] in C.CLOSURE_EXCLUDED:
            assert c["id"] not in served, c["id"]
            continue
        assert c["id"] in served and served[c["id"]].get("review") == "pending", c["id"]
        # id는 승인할 때 붙는 내용 기반 id와 같아 승인 뒤에도 답 기록이 이어진다
        assert c["id"] == CR.closure_id(c)
    # 기존 문항에는 표시가 없다
    assert not [c["id"] for c in C.CLOSURE_ITEMS if c.get("review") and c["id"] not in {x["id"] for x in new}]


def test_unreviewed_items_meet_the_writing_rules():
    tw = A.test_only_words()
    ex = set(C.STAGE2_EXCLUDED)
    tier = {w["word"]: w["tier"] for w in C.WORD_BANK}
    for c in _unreviewed():
        a, opts, d = c["answer"], c["options"], c["display"]
        # 정답은 단어 은행의 일상어(등급 1·2), 검사 단어·드문 말이 아니다
        assert tier.get(a, 9) <= 2 and a not in tw and a not in ex, (c["id"], a)
        # 보기 셋, 오답 둘 다 정답과 입모양이 같거나 눈으로 못 가르는 실단어
        assert len(opts) == 3 and opts[0] == a and len(set(opts)) == 3, c["id"]
        for o in opts[1:]:
            assert R._visually_confusable(a, o) and o not in tw and o not in ex, (c["id"], o)
        # 정답이 문장의 다른 자리에 적혀 있지 않다(읽기만 해도 풀리지 않게)
        assert a not in d.replace("___", ""), c["id"]
        ok, _, why = R.check_closure(d, a, opts, hint=c.get("hint"))
        assert ok, (c["id"], why)


def test_rejected_item_leaves_the_pool_and_pending_lists_the_rest():
    new = _unreviewed()
    saved = (list(C.CLOSURE_ITEMS), C._REJECTED_PATH)
    try:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rejected.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"closures": [new[0]]}, f, ensure_ascii=False)
            C.CLOSURE_ITEMS[:] = [c for c in C.CLOSURE_ITEMS if not c.get("review")]
            C._REJECTED_PATH = path
            n = C._merge_unreviewed_closures()
            ids = {c["id"] for c in C.CLOSURE_ITEMS}
            assert n == len(new) - 1 and new[0]["id"] not in ids and new[1]["id"] in ids
    finally:
        C.CLOSURE_ITEMS[:] = saved[0]
        C._REJECTED_PATH = saved[1]
    # 운영자 검수 대기 목록에 검수 전 문항이 보인다(승인·반려된 것은 빠진다)
    keys = {CR._key("closures", it) for it in CR.pending()["pending"]["closures"]}
    assert CR._key("closures", new[1]) in keys
