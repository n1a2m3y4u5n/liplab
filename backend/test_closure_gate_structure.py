"""생성 문맥 문항이 보기 개수·정답 위치로 답을 누설하지 않는지 검사."""
import pytest

import content_rules as R
import curriculum as C


BAD_CASES = [
    ("___을 먹었어요", ["밥", "맘", "맘"]),
    ("___을 먹었어요", ["밥", "맘", "밤", "밤"]),
    ("___을 먹었어요", ["밥", "밥", "맘", "밤"]),
    ("___을 먹었어요", ["밥", "맘", " 밤 ", "밤"]),
    ("___을 ___ 먹었어요", ["밥", "맘", "밤"]),
    ("___을 먹고 ___을 먹었어요", ["밥", "맘", "밤"]),
]


@pytest.mark.parametrize("display,options", BAD_CASES)
def test_malformed_closures_are_rejected(display, options):
    assert not R.check_closure(display, "밥", options)[0]


def test_valid_closure_keeps_original_option_order():
    ok, item, _ = R.check_closure("___을 먹었어요", "밥", ["밤", " 밥 ", "맘"])
    assert ok
    assert item["options"] == ["밤", "밥", "맘"]


def test_shipped_closures_have_unique_options_and_one_blank():
    # 새 게이트가 현재 정상 콘텐츠를 줄이지 않는지도 확인한다.
    for item in C.CLOSURE_ITEMS:
        if item["id"] in C.CLOSURE_EXCLUDED:
            continue
        options = [str(o).strip() for o in item["options"]]
        assert len(options) == len(set(options)), item["id"]
        assert item["display"].count("___") == 1, item["id"]
