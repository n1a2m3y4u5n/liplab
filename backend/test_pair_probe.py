"""2단계 짝 탐색 문항(docs/confusion-pair-serving.md 5.4-2).

레슨 12문항 중 선다형 1문항은 후보 혼동 짝의 target 자모가 든 단어 + 그 자리 자모만 바꾼 대비 단어가 든 보기로 낸다.
후보 짝이 없으면 탐색할 수 있는 짝을 무작위로 고른다. 탐색 문항은 보통 단어 문항처럼 숙달에 들어가고, 시행 기록에 probe가 남는다.
"""
import json
import os
import random
import subprocess
import sys
import tempfile

import confusion_pairs as C


def _table():
    import main
    return main._stage2_table(), main._stage2_pairs()


def test_pair_index_candidates_and_contrasts():
    table, pidx = _table()
    assert len(pidx.candidates) > 100 and 50 < len(pidx.probe_pairs) <= len(pidx.candidates)
    for pair in pidx.probe_pairs:
        p, t, r = pair
        assert C.visible_jamo_pair(p, t, r)
        for w, cs in list(pidx.contrast[pair].items())[:5]:
            for c in cs:
                assert c in table.index and c != w
                assert C.jamo_diffs(w, c) == [pair]   # 그 자리 자모 하나만 다르다
                assert table.classes(w) and c not in table.index.homophenes(w)


def test_probe_items_use_candidate_pair_first_then_random():
    table, pidx = _table()
    rng = random.Random(3)
    pri = {w: 1 for w in table.words}
    pair = pidx.probe_pairs[len(pidx.probe_pairs) // 2]
    focus = [{"position": "중성", "target": "ㅢ", "read": "ㅏ"},          # 대비 단어가 없는 짝은 건너뛴다
             {"position": pair[0], "target": pair[1], "read": pair[2]}]
    items = C.probe_items(pidx, focus, pri, 2, table.classes, rng)
    assert items and len({x["word"] for x in items}) == len(items)
    for x in items:
        pr = x["probe"]
        assert (pr["position"], pr["target"], pr["read"]) == pair and pr["source"] == "candidate"
        assert pr["contrast"] in x["distractors"] and x["word"] not in x["distractors"]
        assert len(set(x["distractors"])) == 3
        assert C.valid_probe(pr, x["word"], [x["word"], *x["distractors"]]) is not None
    rnd = C.probe_items(pidx, [], pri, 2, table.classes, rng)
    assert rnd and all(x["probe"]["source"] == "random" for x in rnd)
    assert tuple(rnd[0]["probe"][k] for k in ("position", "target", "read")) in pidx.probe_pairs


def test_valid_probe_rejects_mismatch():
    table, pidx = _table()
    pair = pidx.probe_pairs[0]
    w, cs = next(iter(pidx.contrast[pair].items()))
    pr = {"position": pair[0], "target": pair[1], "read": pair[2], "contrast": cs[0], "source": "random"}
    opts = [w, cs[0], "가", "나"]
    assert C.valid_probe(pr, w, opts)["contrast"] == cs[0]
    assert C.valid_probe(pr, w, [w, "가", "나", "다"]) is None                # 대비 단어가 보기에 없다
    assert C.valid_probe({**pr, "read": pair[1]}, w, opts) is None           # 같은 자모
    assert C.valid_probe({**pr, "contrast": w}, w, opts) is None
    assert C.valid_probe("x", w, opts) is None and C.valid_probe(pr, w, None) is None


_FLOW = r'''
import json, sqlite3, os
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "pb@example.com", "username": "pbu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    w1 = c.get("/api/curriculum/words", headers=h).json()
    probes = w1["probes"]
    p = probes[0]
    opts = [p["word"], *p["distractors"]]
    pr = p["probe"]
    post = lambda body: c.post("/api/curriculum/word-answer", json=body, headers=h).json()
    # 탐색 문항에서 대비 단어를 두 번 고른다 → 그 짝이 후보가 된다
    a1 = post({"word": p["word"], "correct": False, "chosen": pr["contrast"], "options": opts, "probe": pr})
    a2 = post({"word": p["word"], "correct": False, "chosen": pr["contrast"], "options": opts, "probe": pr})
    # 보기와 맞지 않는 탐색 표시는 보통 문항으로 남는다
    a3 = post({"word": p["word"], "correct": True, "chosen": p["word"], "options": [p["word"], "가", "나", "다"], "probe": pr})
    w2 = c.get("/api/curriculum/words", headers=h).json()
db = sqlite3.connect(os.environ["T_DB"])
rows = db.execute("select item_type, probe from trial_attempts order by id").fetchall()
sp = db.execute("select attempts from stage_progress where stage = 2").fetchone()
print("RESULT " + json.dumps({"n_probes": len(probes), "p": p, "a": [a1["attempts"], a2["attempts"], a3["attempts"]],
                              "rows": [[t, json.loads(x) if x else None] for t, x in rows], "sp": sp[0],
                              "p2": [x["probe"] for x in w2["probes"]], "words_ok": len(w2["words"]) > 400},
                             ensure_ascii=False))
'''


def test_probe_endpoint_records_and_counts_for_mastery():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.db")
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{f}", T_DB=f, PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert 1 <= r["n_probes"] <= C.PROBE_OFFER and r["words_ok"]
    pr = r["p"]["probe"]
    assert pr["source"] == "random"                    # 새 학습자는 후보 짝이 없다
    # 보통 단어 문항처럼 숙달 시도에 들어간다
    assert r["a"] == [1, 2, 3] and r["sp"] == 3
    assert [x[0] for x in r["rows"]] == ["word"] * 3
    assert r["rows"][0][1]["contrast"] == pr["contrast"] and r["rows"][1][1] is not None
    assert r["rows"][2][1] is None
    # 대비 단어를 두 번 고른 짝이 다음 레슨의 탐색 후보가 된다
    key = (pr["position"], pr["target"], pr["read"])
    assert r["p2"] and all((x["position"], x["target"], x["read"]) == key and x["source"] == "candidate" for x in r["p2"])
