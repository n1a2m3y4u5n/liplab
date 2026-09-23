"""approved.json 병합 회귀 테스트(축 G).

9/22 대량화 때 문맥 문항 id가 배치마다 g1부터 다시 매겨져 181개 중 118개가 런타임에서
빠진 결함이 있었다. 승인 문항이 전부 실리고 id가 유일한지 확인한다.
"""
import json
import os

import curriculum as cur
from content_pipeline import closure_id


def _approved():
    path = os.path.join(os.path.dirname(__file__), "data", "curriculum", "approved.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_all_approved_closures_loaded():
    data = _approved()
    contents = {(c.get("display", ""), c.get("answer", "")) for c in data["closures"] if c.get("answer")}
    loaded = {(c.get("display", ""), c.get("answer", "")) for c in cur.CLOSURE_ITEMS}
    assert contents <= loaded, f"런타임 누락 {len(contents - loaded)}개"


def test_closure_ids_unique():
    ids = [c["id"] for c in cur.CLOSURE_ITEMS]
    assert len(ids) == len(set(ids)), "문맥 문항 id 중복(채점 API가 id로 문항을 찾음)"


def test_approved_file_ids_unique():
    ids = [c.get("id") for c in _approved()["closures"]]
    assert len(ids) == len(set(ids)), "approved.json 안에 중복 id"


def test_closure_id_is_content_based():
    a = {"display": "나는 ___를 먹었다", "answer": "밥"}
    b = {"display": "나는 ___를 먹었다", "answer": "맘"}
    assert closure_id(a) == closure_id(dict(a)), "같은 내용이면 같은 id"
    assert closure_id(a) != closure_id(b), "내용이 다르면 다른 id"
    assert closure_id(a).startswith("g") and len(closure_id(a)) == 9
