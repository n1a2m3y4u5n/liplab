"""소리 듣기(청능훈련) 커리큘럼 테스트(listen_curriculum, /api/listen/*)."""
import json
import os

import listen_curriculum as L


def test_stages_and_ling():
    assert [s["stage"] for s in L.stages_overview()] == [0, 1, 2, 3, 4, 5]
    seq = L.ling_sequence("u1")
    assert sorted(seq) == sorted(L.LING_KEYS + ["silent", "silent"])
    assert seq == L.ling_sequence("u1")
    s = L.ling_summary({"m": True, "u": True, "a": True, "i": True, "sh": False, "s": False, "silent_false_alarms": 1},
                       {"m": True, "u": True, "a": True, "i": True, "sh": True, "s": False})
    assert s["missed"] == ["sh", "s"] and s["dropped"] == ["sh"] and not s["reliable"]


def test_ax_items_balanced_and_parsed():
    for lv in (1, 2, 3, 4):
        its = L.ax_items(lv, "seed", n=12)
        assert len(its) == 12 and sum(it["first"] == it["second"] for it in its) == 6
        assert all(it["level"] == lv for it in its)
        for it in its:
            first, second, pair = L.ax_parse(it["key"])
            assert pair["level"] == lv
            assert L.ax_correct(it["key"], first == second) is True
    assert L.ax_parse("ax:4:가|하") is None and L.ax_parse("ax:바|다") is None          # 목록에 없는 짝은 받지 않는다
    assert L.ax_items(3, "s", n=4, multi_voice=True)[0]["voice_pair"] == [0, 1]
    assert L.ax_items(2, "s", n=4, multi_voice=True)[0]["voice_pair"] == [0, 0]


def test_level_rule_and_mastery():
    assert L.next_level([], 1) == 1
    up = [(1, True)] * 9 + [(1, False)]
    assert L.next_level(up, 1) == 2
    assert L.next_level(up + [(2, False)] * 3 + [(2, True)] * 3, 1) == 1     # 수준 2에서 6번 중 3번만 맞음 → 내림
    assert L.next_level([(4, True)] * 10, 1) == 4                             # 맨 위에서는 더 오르지 않는다
    assert not L.leveled_mastered([(4, True)] * 9, 1)
    assert L.leveled_mastered([(3, False)] * 5 + [(4, True)] * 9 + [(4, False)], 1)
    assert L.leveled_mastered([(3, True)] * 8 + [(3, False)] * 2, 2)


def test_sound_distance():
    assert L.sound_distance("개", "게") == 0          # ㅐ·ㅔ는 같은 소리
    assert L.sound_distance("불", "풀") == 1          # 세기 하나
    assert L.sound_distance("사과", "가방") > L.sound_distance("불", "풀")
    assert L.sound_distance("밥", "바다") == 99
    assert L.contrast_of("바다", "바라") == [{"slot": "onset", "target": "ㄷ", "heard": "ㄹ", "syllable": 1}]


def test_word_items_options_by_level():
    pool = L.word_pool()
    assert len(pool) > 300
    for lv, n in ((1, 2), (2, 4), (3, 4)):
        its = L.word_items(lv, pool, "seed", n=10)
        assert len(its) == 10
        for it in its:
            assert len(it["options"]) == n and it["target"] in it["options"] and len(set(it["options"])) == n
            # 소리가 같은 말은 보기로 내지 않는다
            assert all(L.sound_distance(it["target"], o) > 0 for o in it["options"] if o != it["target"])
            if lv == 3:
                assert all(L.sound_distance(it["target"], o) <= 4 for o in it["options"] if o != it["target"])


def test_stair_and_srt():
    st = L.stair_state([])
    assert st["next_db"] == 10.0 and st["srt_db"] is None
    assert L.stair_state([(10.0, True)])["next_db"] == 6.0
    assert L.stair_state([(10.0, False)])["next_db"] == 14.0
    assert L.stair_state([(25.0, False)])["next_db"] == 25.0               # 위 한계
    # 2 dB 근처에서 오르내리는 학습자: 역치가 그 근처로 모인다
    trials, snr = [], 10.0
    for k in range(30):
        ok = snr >= 2.0                     # 2 dB 이상이면 알아듣는 학습자
        trials.append((snr, ok))
        snr = L.stair_state(trials)["next_db"]
    est = L.stair_state(trials)["srt_db"]
    assert est is not None and -2.0 <= est <= 6.0
    assert L.noise_condition(0) == "ao" and L.noise_condition(3) == "av"


def test_noise_mastery():
    assert not L.noise_mastered([(10.0, True)] * 10)
    low = [(0.0, k % 2 == 0) for k in range(20)]
    assert L.noise_mastered(low)
    first = [(12.0, k % 2 == 0) for k in range(20)]
    later = [(8.0, k % 2 == 0) for k in range(20)]
    assert L.noise_mastered(first + later)                                   # 4 dB 내려감
    assert not L.noise_mastered(first + [(11.0, k % 2 == 0) for k in range(20)])


def test_test_srt():
    trials = [(10.0, True), (6.0, True), (2.0, True)]
    assert L.test_next_snr(trials) == -2.0
    assert L.test_next_snr(trials + [(-2.0, False), (2.0, False)]) == 4.0   # 다섯째부터 2 dB
    assert L.test_srt(trials) is None
    alt = []
    for k in range(20):
        s = L.test_next_snr(alt) if alt else 10.0
        alt.append((s, s >= 3.0))
    srt = L.test_srt(alt)
    assert srt is not None and 1.0 <= srt <= 5.0
    assert L.test_form_for(2, 0) == "A" and L.test_form_for(2, 1) == "B" and L.test_form_for(3, 0) == "B"
    # 연습 문장: 연습은 4 dB, 검사 문장은 처음부터 2 dB. 역치는 연습을 뺀 검사 문장 20개로
    prac = [(10.0, True), (6.0, True), (2.0, False), (6.0, True), (2.0, True)]
    assert L.test_next_snr(prac, n_practice=5) == -2.0
    assert L.test_next_snr(prac + [(-2.0, False)], n_practice=5) == 0.0
    seq, snr = list(prac), -2.0
    for k in range(20):
        seq.append((snr, snr >= 3.0))
        snr = L.test_next_snr(seq, n_practice=5)
    assert L.test_srt(seq[:24], n_practice=5) is None
    srt5 = L.test_srt(seq, n_practice=5)
    assert srt5 is not None and 1.0 <= srt5 <= 5.0
    test_snrs = [s for s, _ in seq[5:]]
    assert srt5 == round((sum(test_snrs[4:20]) + snr) / 17, 1)
    items = L.test_practice_items("test:abc")
    assert len(items) == L.TEST_STAIR["practice"] == 5 and all(it["practice"] and it["key"].startswith("testp:t") for it in items)
    assert items == L.test_practice_items("test:abc") and items != L.test_practice_items("test:abd")
    tests = {"".join(ch for ch in s if ch.isalnum()) for f in L.TEST_FORMS.values() for s in f}
    assert not tests & {"".join(ch for ch in it["text"] if ch.isalnum()) for it in items}


def test_test_form_assignment():
    """babble은 A·B, talker2는 C·D를 학습자 id 홀짝 순서로 번갈아 쓴다. C·D 소리가 없으면 talker2는 같은 회차 babble의 반대 폼."""
    assert set(L.TEST_FORMS) == {"A", "B", "C", "D"} and L.TEST_FORM_PAIRS == {"babble": ("A", "B"), "talker2": ("C", "D")}
    for uid in (2, 3, 10, 11):
        bb = [L.test_form_for(uid, n, "babble") for n in range(4)]
        t2 = [L.test_form_for(uid, n, "talker2") for n in range(4)]
        fb = [L.test_form_for(uid, n, "talker2", heldout_ready=False) for n in range(4)]
        assert bb == [L.test_form_for(uid, n) for n in range(4)]            # 예전 호출(잡음 생략)은 babble 그대로
        assert set(bb[:2]) == {"A", "B"} and bb[2:] == bb[:2]
        assert set(t2[:2]) == {"C", "D"} and t2[2:] == t2[:2]
        assert (bb[0], t2[0]) == (("A", "C") if uid % 2 == 0 else ("B", "D"))   # 같은 홀짝 역균형
        assert all(f != b and f in "AB" for f, b in zip(fb, bb))           # 대체 규칙: 같은 회차의 babble과 다른 폼
        # 사전(회차 0)에 두 잡음을 다 해도 다른 문장이고, 사전·사후 사이에 같은 잡음 폼이 되풀이되지 않는다
        assert bb[0] != t2[0] and bb[0] != bb[1] and t2[0] != t2[1]
    assert L.test_form_for(2, 0, "bogus") == "A"
    assert L.heldout_forms_ready(lambda t: True) and not L.heldout_forms_ready(lambda t: t != L.TEST_FORMS["D"][19])
    assert L.heldout_forms_ready(lambda t: t not in L.TEST_FORMS["A"])   # A·B 소리와 무관


def test_test_forms_have_listen_voice_audio():
    """네 폼 문장은 서버 음성 목록의 듣기 목소리(마지막이 검사 목소리 m3) 모두에 소리가 있다(docs/listen-forms-cd-2026-10.md)."""
    import sound_clips as S
    here = os.path.dirname(os.path.abspath(__file__))
    man = S.load_manifest(os.path.join(here, "data", "sound", "manifest.json"))
    voices = [v["id"] for v in man["voices"]]
    assert voices and voices[-1] == "m3"
    missing = [(v, s) for v in voices for f in sorted(L.TEST_FORMS) for s in L.TEST_FORMS[f]
               if not S.lookup({"clips": man["clips"].get(v, {})}, s)]
    assert not missing, missing[:5]


def _pilot_builder():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "build_pilot_manifest.py")
    spec = importlib.util.spec_from_file_location("build_pilot_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_content_separation():
    """검사 문장은 훈련 문장·대화와 겹치지 않고, P3 파일럿 문장과도 겹치지 않는다. 네 폼은 같은 길이이고 같은 자리끼리 어절 수가 같다.
    10/7에 더한 C·D는 P3 빌드의 유사도 점검(similarity_reasons)으로도 훈련 문장·대화·앱 문장·P3 문장·다른 검사 문장과 가깝지 않다."""
    def key(s):
        return "".join(ch for ch in s if ch.isalnum())
    test = {key(s) for f in L.TEST_FORMS.values() for s in f}
    train = {key(s) for s in L.TRAIN_SENTENCES} | {key(c[k]) for c in L.CONVO_ITEMS for k in ("line", "paraphrase")}
    assert not test & train
    assert len(L.TRAIN_SENTENCES) == len(set(map(key, L.TRAIN_SENTENCES)))
    assert len(test) == 80 and all(len(L.TEST_FORMS[f]) == 20 for f in "ABCD")
    for row in zip(*(L.TEST_FORMS[f] for f in "ABCD")):
        assert len({len(s.split()) for s in row}) == 1, row
    assert not any(ch.isdigit() for f in "CD" for s in L.TEST_FORMS[f] for ch in s)   # 숫자는 한글로
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "data", "pilot", "battery_manifest.json"), encoding="utf-8") as f:
        raw = f.read()
    pilot = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("text", "word") and isinstance(v, str):
                    pilot.add(key(v))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(json.loads(raw))
    assert pilot and not (test | {key(s) for s in L.TRAIN_SENTENCES}) & pilot
    # C·D 유사도 점검(P3 빌드와 같은 규칙). 비교 대상: 듣기 훈련 문장·대화, 앱의 훈련 문장(독화·말하기·문맥), P3 문장, 네 폼의 다른 문장
    B = _pilot_builder()
    p3 = []

    def walk2(x):
        if isinstance(x, dict):
            if isinstance(x.get("text"), str) and " " in x["text"].strip():
                p3.append(x["text"])
            for v in x.values():
                walk2(v)
        elif isinstance(x, list):
            for v in x:
                walk2(v)
    walk2(json.loads(raw))
    others = list(L.TRAIN_SENTENCES) + [c[k] for c in L.CONVO_ITEMS for k in ("line", "paraphrase")] + \
        list(B.training_sentences()) + p3
    assert len(p3) > 50
    for f in "CD":
        for i, s in enumerate(L.TEST_FORMS[f]):
            hits = [(t, B.similarity_reasons(s, t)) for t in others if B.similarity_reasons(s, t)]
            assert not hits, (f, i + 1, s, hits[:3])
            for g in "ABCD":
                for j, t in enumerate(L.TEST_FORMS[g]):
                    if (g, j) != (f, i):
                        assert not B.similarity_reasons(s, t, both_ways=True), (s, t)


def test_convo_items_hide_answer():
    its = L.convo_items("s", n=8)
    assert len(its) == 8 and all("answer" not in it for it in its)
    for c in L.CONVO_ITEMS:
        assert len(c["options"]) == 4 and 0 <= c["answer"] < 4 and len(set(c["options"])) == 4
    assert L.convo_correct("c:c01", 0) is True and L.convo_correct("c:c01", 1) is False


def test_convo_content_quality():
    """대화 문항: 정답 자리가 한쪽으로 쏠리지 않고(자리마다 6~9개), 정답이 혼자 가장 긴 보기가 아니다(10/7 콘텐츠 검토)."""
    from collections import Counter
    pos = Counter(c["answer"] for c in L.CONVO_ITEMS)
    assert set(pos) == {0, 1, 2, 3} and all(6 <= n <= 9 for n in pos.values()), pos
    for c in L.CONVO_ITEMS:
        lens = [len(o.replace(" ", "")) for o in c["options"]]
        a = lens[c["answer"]]
        assert not (a == max(lens) and lens.count(a) == 1), c["id"]


def test_listen_excluded_words():
    pool = set(L.word_pool(include_gen=True))
    assert L.LISTEN_EXCLUDED and not pool & set(L.LISTEN_EXCLUDED)
    assert not set(L.GEN_WORDS) & set(L.LISTEN_EXCLUDED)
    assert all(len(w) <= 2 for w in L.GEN_WORDS) and len(set(L.GEN_WORDS)) == 20
    assert 2 <= min(len(s.split()) for s in L.TRAIN_SENTENCES) and max(len(s.split()) for s in L.TRAIN_SENTENCES) <= 5


def test_word_score_and_recommendations():
    ws = L.word_score("창문 좀 열어 주세요.", "창문 좀 열어 줘요")
    assert ws["feedback"]["total_words"] == 4 and ws["proportion"] == 0.75
    conf = L.tally_confusions([("불", "풀"), ("발", "팔"), ("달", "갈")])
    assert conf[0] == {"slot": "onset", "target": "ㅂ", "heard": "ㅍ", "n": 2}
    recs = L.recommendations(conf)
    assert recs[0]["lip_differs"] is False                                  # ㅂ·ㅍ는 입모양이 같다
    assert recs[1]["lip_differs"] is True                                   # ㄷ·ㄱ는 입모양 무리가 다르다


def test_inventory_texts():
    texts = L.inventory_texts()
    assert len(texts) == len(set(texts)) and "바" in texts and L.TEST_FORMS["A"][0] in texts


_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ls@example.com", "username": "ls1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    st = c.get("/api/listen/curriculum", headers=h).json()["stages"]
    out["initial"] = [s["status"] for s in st]
    out["ling_bad"] = c.post("/api/listen/ling", json={"results": {"m": True}}, headers=h).status_code
    res = {k: True for k in ["m", "u", "a", "i", "sh", "s"]}
    out["ling1"] = c.post("/api/listen/ling", json={"results": res, "false_alarms": 0}, headers=h).json()["summary"]
    out["ling2"] = c.post("/api/listen/ling", json={"results": {**res, "s": False}, "false_alarms": 1}, headers=h).json()["summary"]
    out["after_ling"] = [s["status"] for s in c.get("/api/listen/curriculum", headers=h).json()["stages"]]
    s1 = c.get("/api/listen/stage/1", headers=h).json()
    out["s1_level"] = s1["level"]
    # 수준 1에서 10번 다 맞히면 수준 2
    for it in s1["items"][:10]:
        last = c.post("/api/listen/answer", json={"stage": 1, "item_key": it["key"], "same": it["first"] == it["second"]},
                      headers=h).json()
    out["s1_after"] = last["level"]
    wrong = c.post("/api/listen/answer", json={"stage": 1, "item_key": "ax:4:가|하", "same": True}, headers=h)
    out["s1_bad"] = wrong.status_code
    # 잠긴 3단계 답은 세지 않는다
    s3 = c.get("/api/listen/stage/3", headers=h).json()
    it = s3["items"][0]
    a3 = c.post("/api/listen/answer", json={"stage": 3, "item_key": it["key"], "answer": it["text"]}, headers=h).json()
    out["s3_locked"] = [a3["counted"], a3["correct"], a3.get("target") == it["text"]]
    # 건너뛰기로 2·3·4단계를 연다
    for n in (2, 3, 4):
        out[f"skip{n}"] = c.post("/api/listen/skip", json={"stage": n}, headers=h).status_code
    out["skip5_ok"] = c.post("/api/listen/skip", json={"stage": 5}, headers=h).status_code
    s2 = c.get("/api/listen/stage/2", headers=h).json()
    w = s2["items"][0]
    other = next(o for o in w["options"] if o != w["target"])
    a2 = c.post("/api/listen/answer", json={"stage": 2, "item_key": w["key"], "answer": other, "level": w["level"]}, headers=h).json()
    out["s2"] = [a2["correct"], a2["target"] == w["target"], isinstance(a2["contrast"], list)]
    s4 = c.get("/api/listen/stage/4", headers=h).json()
    out["s4"] = [s4["stair"]["ao"]["next_db"], s4["next_condition"], s4["needs_pretest"]]
    a4 = c.post("/api/listen/answer", json={"stage": 4, "item_key": s4["items"][0]["key"], "answer": s4["items"][0]["text"],
                                            "snr_db": 10, "condition": "ao"}, headers=h).json()
    out["a4"] = [a4["correct"], a4["stair"]["ao"]["next_db"], a4["next_condition"]]
    ts = c.post("/api/listen/test/start", json={}, headers=h).json()
    out["test_form"] = ts["form"]
    out["test_practice"] = [ts["n_practice"], [it["practice"] for it in ts["items"]][:6], len(ts["items"]),
                            all(it["key"].startswith("testp:") for it in ts["items"][:5])]
    snrs = []
    for k, it in enumerate(ts["items"]):
        r = c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": it["key"],
                                                   "answer": it["text"] if k % 2 == 0 else ""}, headers=h).json()
        snrs.append(r["snr_db"])
        if k == 0:
            out["prac_resp"] = [r["practice"], r.get("target") == it["text"], r["n"], r["n_practice"], r["done"]]
        if k == 5:
            out["first_test"] = [r["practice"], "target" not in r, r["n"], r["n_practice"]]
    out["test_done"] = [r["done"], r["srt_db"] is not None, snrs[:3], snrs[4:8], r["n"], r["n_practice"]]
    out["test_dup"] = c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": ts["items"][0]["key"],
                                                             "answer": ""}, headers=h).status_code
    out["s4_after"] = c.get("/api/listen/stage/4", headers=h).json()["needs_pretest"]
    ts2 = c.post("/api/listen/test/start", json={}, headers=h).json()
    out["next_form"] = ts2["form"]
    r2 = c.post("/api/listen/test/answer", json={"session": ts2["session"], "item_key": ts2["items"][5]["key"], "answer": ""},
                headers=h).json()
    late = c.post("/api/listen/test/answer", json={"session": ts2["session"], "item_key": ts2["items"][0]["key"], "answer": ""},
                  headers=h)
    alien = c.post("/api/listen/test/answer", json={"session": ts2["session"], "item_key": "testp:t001", "answer": ""}, headers=h)
    out["practice_order"] = [r2["snr_db"], r2["n"], late.status_code, alien.status_code in (400, 409)]
    out["s5_locked"] = c.get("/api/listen/stage/5", headers=h).json()["status"]
    summ = c.get("/api/listen/summary", headers=h).json()
    out["summary"] = [summ["n_checks"], len(summ["tests"]), summ["last_check"]["summary"]["dropped"], len(summ["days"]),
                      len(summ["confusions"]) >= 1]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_listen_api_flow():
    import subprocess
    import sys
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="0")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["initial"] == ["unlocked", "locked", "locked", "locked", "locked", "locked"]
    assert r["ling_bad"] == 400
    assert r["ling1"]["reliable"] and r["ling2"]["dropped"] == ["s"] and not r["ling2"]["reliable"]
    assert r["after_ling"][:2] == ["mastered", "unlocked"]
    assert r["s1_level"] == 1 and r["s1_after"] == 2 and r["s1_bad"] == 400
    assert r["s3_locked"] == [False, True, True]
    assert r["skip2"] == 200 and r["skip3"] == 200 and r["skip4"] == 200 and r["skip5_ok"] == 200
    assert r["s2"] == [False, True, True]
    assert r["s4"] == [10.0, "ao", True]
    assert r["a4"] == [True, 6.0, "ao"]
    assert r["test_form"] == "B" or r["test_form"] == "A"
    assert r["test_practice"] == [5, [True] * 5 + [False], 25, True]
    assert r["prac_resp"] == [True, True, 0, 1, False]
    assert r["first_test"] == [False, True, 1, 5]
    # 연습 5문장(맞음·틀림 번갈아, 4 dB) 10, 6, 10, 6, 10. 연습 마지막(맞음) 뒤 첫 검사 문장 6, 그 뒤 검사는 2 dB(틀림 8, 맞음 6)
    assert r["test_done"][0] and r["test_done"][1] and r["test_done"][2] == [10.0, 6.0, 10.0]
    assert r["test_done"][3] == [10.0, 6.0, 8.0, 6.0] and r["test_done"][4:] == [20, 5]
    assert r["practice_order"] == [10.0, 1, 400, True]                       # 연습 없이 시작하면 옛 규칙, 검사 뒤 연습은 받지 않음
    assert r["test_dup"] == 409 and r["s4_after"] is False and r["next_form"] != r["test_form"]
    assert r["s5_locked"] == "unlocked"
    assert r["summary"][0] == 2 and r["summary"][1] == 1 and r["summary"][2] == ["s"] and r["summary"][3] == 7


def test_targeted_picking_and_ling_scale():
    assert {L.pick_mode_for(i) for i in range(20)} == set(L.PICK_MODES)
    assert L.pick_mode_for(7) == L.pick_mode_for(7)
    # 0.75 근처 짝이 거의 다 맞히는 짝보다 자주 나온다
    st = {"4:사|자": (20, 15), "4:각|갑": (20, 20)}
    its = L.ax_items(4, "s", n=400, pick="targeted", stats=st)
    diff = [i for i in its if i["first"] != i["second"]]
    n_mid = sum(1 for i in diff if {i["first"], i["second"]} == {"사", "자"})
    n_easy = sum(1 for i in diff if {i["first"], i["second"]} == {"각", "갑"})
    assert n_mid > n_easy and all(i["pick"] == "targeted" for i in its)
    assert L.ax_pair_stats([("ax:4:사|자", True), ("ax:4:자|사", False), ("ax:4:사|사", True)]) == {"4:사|자": (2, 1)}
    # 쉬·스가 모두 안 들리면 마찰음 짝을 내지 않는다
    assert L.ling_avoid_kinds({"sh": False, "s": False}) == {"fricative": 0.0}
    assert L.ling_avoid_kinds({"sh": True, "s": False}) == {"fricative": 0.5}
    its = L.ax_items(4, "s", n=60, kind_scale={"fricative": 0.0})
    assert all(i["kind"] != "fricative" for i in its)


def test_word_focus_and_review():
    pool = L.word_pool()
    f = [{"slot": "onset", "target": "ㅂ", "heard": "ㅍ"}]
    its = L.word_items(3, pool, "s", n=10, pick="targeted", focus=f)
    foc = [i for i in its if i.get("focus")]
    assert 1 <= len(foc) <= 5
    for i in foc:
        assert any(len(L.contrast_of(i["target"], o)) == 1 and {L.contrast_of(i["target"], o)[0]["target"], L.contrast_of(i["target"], o)[0]["heard"]} == {"ㅂ", "ㅍ"}
                   for o in i["options"] if o != i["target"])
    assert not any(i.get("focus") for i in L.word_items(3, pool, "s", n=10, pick="uniform", focus=f))
    rv = L.word_items(2, pool, "s", n=10, review=[pool[5]])
    assert rv[0]["target"] == pool[5] or not rv[0].get("review")   # 복습 낱말이 2수준 후보면 맨 앞
    import datetime as D
    t = D.date(2026, 10, 7)
    h = [("a", False, t - D.timedelta(2)), ("b", False, t), ("c", False, t - D.timedelta(5)), ("c", True, t - D.timedelta(4)),
         ("d", False, t - D.timedelta(5)), ("d", True, t - D.timedelta(4)), ("d", True, t - D.timedelta(1)),
         ("e", False, t - D.timedelta(3)), ("e", True, t - D.timedelta(1))]
    assert L.due_reviews(h, t) == ["c", "a"]          # b는 오늘 틀림, d는 두 번 맞혀 빠짐, e는 맞힌 지 1일이라 아직
    s = L.sentence_items("x", n=8, review=["t005", "t006", "t007"])
    assert [i["id"] for i in s[:2]] == ["t005", "t006"] and s[0]["review"] and "review" not in s[2]


def test_gen_words_excluded_from_training():
    pool = L.word_pool()
    assert not set(L.GEN_WORDS) & set(pool)
    assert set(L.GEN_WORDS) <= set(L.word_pool(include_gen=True))
    items = L.gen_test_items(L.word_pool(include_gen=True))
    assert len(items) == 20 and [i["target"] for i in items] == L.GEN_WORDS
    for it in items:
        assert len(it["options"]) == 4 and it["target"] in it["options"]
        assert not (set(it["options"]) - {it["target"]}) & set(L.GEN_WORDS)
    assert set(L.GEN_WORDS) <= set(L.inventory_texts())
    assert L.TEST_NOISES == ("babble", "talker2") and L.HELDOUT_NOISE not in L.TRAIN_NOISES


_FLOW2 = r'''
import json
from fastapi.testclient import TestClient
import main
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "lw@example.com", "username": "lw1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    w = c.post("/api/listen/wordtest/start", headers=h).json()
    for k, it in enumerate(w["items"]):
        a = c.post("/api/listen/wordtest/answer", json={"session": w["session"], "item_key": it["key"],
                   "answer": it["target"] if k < 15 else "x", "sim": "ci"}, headers=h).json()
    out["wt"] = [a["done"], a["accuracy"]]
    out["s2_level"] = c.get("/api/listen/stage/2", headers=h).json().get("level")
    t1 = c.post("/api/listen/test/start", json={"noise": "talker2"}, headers=h).json()
    t2 = c.post("/api/listen/test/start", json={"noise": "bogus"}, headers=h).json()
    out["noise"] = [t1["noise"], t2["noise"]]
    for it in t1["items"]:
        c.post("/api/listen/test/answer", json={"session": t1["session"], "item_key": it["key"], "answer": "", "noise": "talker2"}, headers=h)
    summ = c.get("/api/listen/summary", headers=h).json()
    out["summ"] = [summ["tests"][0]["noise"], summ["word_tests"][0]["accuracy"], summ["word_tests"][0]["sim"]]
    out["next_t2_form"] = c.post("/api/listen/test/start", json={"noise": "talker2"}, headers=h).json()["form"]
    # 중간에 그만둔 회차(검사 문장 하나만 답함)도 폼 순서에 센다
    t3 = c.post("/api/listen/test/start", json={"noise": "talker2"}, headers=h).json()
    first_test = next(it for it in t3["items"] if not it.get("practice"))
    for it in t3["items"]:
        c.post("/api/listen/test/answer", json={"session": t3["session"], "item_key": it["key"], "answer": "", "noise": "talker2"}, headers=h)
        if it["key"] == first_test["key"]:
            break
    out["after_abandon"] = c.post("/api/listen/test/start", json={"noise": "talker2"}, headers=h).json()["form"]
    out["next_bb_form"] = c.post("/api/listen/test/start", json={"noise": "babble"}, headers=h).json()["form"]
    out["t1_form"] = t1["form"]
    out["t1_items_form"] = sorted({it["key"][5] for it in t1["items"] if not it.get("practice")})
    out["ready"] = main._listen_heldout_ready()
    out["summ_forms"] = [t["form"] for t in summ["tests"]]
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_wordtest_and_test_noise_api():
    import subprocess
    import sys
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW2], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["wt"] == [True, 0.75]
    assert r["s2_level"] == 1                      # 일반화 검사 답은 2단계 수준·숙달에 들어가지 않는다
    assert r["noise"] == ["talker2", "babble"]
    assert r["summ"] == ["talker2", 0.75, "ci"]
    assert r["next_t2_form"] != r["next_bb_form"]  # 잡음마다 폼을 따로 번갈아 쓴다
    assert r["after_abandon"] != r["next_t2_form"]  # 그만둔 회차 뒤에는 다른 폼
    # 저장소의 서버 음성에는 C·D 검사 목소리 소리가 있으므로 talker2는 C·D, babble은 A·B
    assert r["ready"] is True
    assert r["t1_form"] in ("C", "D") and r["t1_items_form"] == [r["t1_form"]] and r["next_t2_form"] in ("C", "D")
    assert r["next_t2_form"] != r["t1_form"] and r["next_bb_form"] in ("A", "B") and r["summ_forms"] == [r["t1_form"]]


_FLOW_FALLBACK = r'''
import json
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "lf@example.com", "username": "lf1", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    bb = c.post("/api/listen/test/start", json={"noise": "babble"}, headers=h).json()
    t2 = c.post("/api/listen/test/start", json={"noise": "talker2"}, headers=h).json()
    print("RESULT " + json.dumps({"ready": main._listen_heldout_ready(), "bb": bb["form"], "t2": t2["form"]}))
'''


def test_test_noise_fallback_without_heldout_audio():
    """C·D 소리가 없으면(서버 음성 폴더가 비었을 때) talker2는 같은 회차의 babble 폼과 반대 폼(A·B)을 쓴다."""
    import subprocess
    import sys
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "sound"))
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1",
                   LIPLAB_SOUND_DIR=os.path.join(d, "sound"), LIPLAB_SOUND_CACHE_DIR="")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW_FALLBACK], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["ready"] is False and r["bb"] in ("A", "B") and r["t2"] in ("A", "B") and r["t2"] != r["bb"]


# ── 10/7 코드 검토 회귀(docs/review/listen-code-review-2026-10.md) ─────────────────────────────

def test_recommendation_wording():
    """받침 없음('-')은 글로 적고, 조사 와/과·을/를은 앞 글자 받침에 맞춘다(예전 '받침 -와 ㄴ를')."""
    t = lambda s, a, b: L.recommendations([{"slot": s, "target": a, "heard": b, "n": 3}])[0]["text"]
    assert t("coda", "-", "ㄴ").startswith("받침 없음과 받침 ㄴ을 자주 헷갈려요.")
    assert t("coda", "ㄴ", "-").startswith("받침 ㄴ과 받침 없음을 자주 헷갈려요.")
    assert t("onset", "ㅅ", "ㄷ").startswith("첫소리 ㅅ과 ㄷ을 자주 헷갈려요.")
    assert t("vowel", "ㅓ", "ㅗ").startswith("모음 ㅓ와 ㅗ를 자주 헷갈려요.")
    assert all("-" not in t("coda", a, b).split(".")[0] for a, b in (("-", "ㄱ"), ("ㅁ", "-")))
    assert L._has_final("없음") and L._has_final("ㄹ") and not L._has_final("ㅏ") and not L._has_final("바")


def test_practice_minutes():
    """시행 간격을 더하고 3분 넘는 쉼은 빼며, 쉰 뒤 첫 시행은 반응 시간(상한 3분)으로 센다."""
    import datetime as D
    t0 = D.datetime(2026, 10, 7, 1, 0, 0)
    ev = [(t0 + D.timedelta(seconds=s), rt) for s, rt in [(0, 20000), (30, 15000), (90, None), (150, 10000),
                                                         (2000, 40000), (2030, None), (2060, 999999)]]
    # 첫 시행 반응 시간 20초 + 간격 30·60·60, 1850초 쉼은 빼고 쉰 뒤 첫 시행 반응 시간 40초 + 간격 30·30 = 270초
    assert L.practice_minutes(ev) == round((20 + 30 + 60 + 60 + 40 + 30 + 30) / 60, 1)
    assert L.practice_minutes([]) == 0.0
    assert L.practice_minutes([(t0, None)]) == 0.0
    assert L.practice_minutes([(t0, 10 ** 9)]) == 3.0           # 반응 시간도 상한


def test_word_review_not_blocked_by_non_candidates():
    """복습 낱말 앞쪽 셋이 이 수준의 정답 후보가 아니어도 뒤의 후보 복습 낱말은 나온다(예전에는 자른 뒤 걸러 하나도 안 나왔다)."""
    pool = L.word_pool()
    nb = L._neighbors(pool)
    cfg = L.WORD_LEVELS[3]
    cands = {w for w in pool if sum(1 for d, _ in nb.get(w, []) if d <= cfg["hi"]) >= cfg["n"] - 1}
    non = [w for w in pool if w not in cands][:3]
    yes = [w for w in pool if w in cands][:2]
    its = L.word_items(3, pool, "s", n=10, review=non + yes)
    assert [i["target"] for i in its if i.get("review")] == yes


def test_gen_test_items_fixed_and_fast():
    """일반화 검사 20문항(보기 포함)은 예전 방식(낱말마다 '훈련 풀 + 그 낱말'로 이웃 표를 새로 만듦)과 똑같고, 만드는 데 몇 초씩
    걸리지 않는다(예전 약 12초 동안 서버가 다른 요청을 받지 못했다)."""
    import time
    L._NEIGHBOR_CACHE.clear()
    pool = L.word_pool(include_gen=True)
    t = time.perf_counter()
    items = L.gen_test_items(pool)
    took = time.perf_counter() - t
    assert took < 3.0, took
    train = [w for w in pool if w not in set(L.GEN_WORDS)]
    naive = []
    for i, w in enumerate(L.GEN_WORDS):
        it = L.word_item(w, 2, list(train) + [w], "gen-20261007")
        if it:
            naive.append({"key": f"g:{w}", "target": w, "options": it["options"], "n": i + 1})
    assert items == naive
    t = time.perf_counter()
    L.word_items(2, L.word_pool(), "x", n=10)          # 검사 풀을 쓴 뒤에도 훈련 풀 이웃 표를 다시 만들지 않는다
    assert time.perf_counter() - t < 0.5


_FLOW_RACE = r'''
import asyncio, json
import httpx
import main
out = {}


async def run():
    async with main.app.router.lifespan_context(main.app):
        tr = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=tr, base_url="http://t") as c:
            r = await c.post("/api/auth/register", json={"email": "race@example.com", "username": "race1", "password": "pw-123456",
                                                         "agree_terms": True, "age_confirmed": True})
            h = {"Authorization": f"Bearer {r.json()['access_token']}"}
            its = (await c.get("/api/listen/stage/3", headers=h)).json()["items"]
            post = lambda it: c.post("/api/listen/answer", json={"stage": 3, "item_key": it["key"], "answer": it["text"]}, headers=h)
            out["first_pair"] = [x.status_code for x in await asyncio.gather(*[post(it) for it in its[:2]])]
            out["four"] = [x.status_code for x in await asyncio.gather(*[post(it) for it in its[2:6]])]
            out["attempts"] = (await c.get("/api/listen/curriculum", headers=h)).json()["stages"][3].get("attempts")
            from database import AsyncSessionLocal, ListenAttempt
            from sqlalchemy import select, func
            async with AsyncSessionLocal() as db:
                out["rows"] = (await db.execute(select(func.count(ListenAttempt.id)).where(ListenAttempt.stage == 3))).scalar()
            ts = (await c.post("/api/listen/test/start", json={}, headers=h)).json()
            it = ts["items"][0]
            rs = await asyncio.gather(*[c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": it["key"],
                                                                              "answer": ""}, headers=h) for _ in range(2)])
            out["test_dup"] = sorted(x.status_code for x in rs)
            out["test_dup_same_body"] = rs[0].json()["next_db"] == rs[1].json()["next_db"] and rs[0].json()["snr_db"] == rs[1].json()["snr_db"]
            it2 = ts["items"][1]
            a = (await c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": it2["key"], "answer": it2["text"]}, headers=h)).json()
            b = await c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": it2["key"], "answer": it2["text"]}, headers=h)
            out["test_resend"] = [b.status_code, b.json().get("replayed"), b.json().get("next_db") == a["next_db"], b.json().get("n") == a["n"]]
            out["test_resend_other"] = (await c.post("/api/listen/test/answer", json={"session": ts["session"], "item_key": it2["key"],
                                                                                     "answer": "다른 답"}, headers=h)).status_code
            w = (await c.post("/api/listen/wordtest/start", headers=h)).json()
            wi = w["items"][0]
            rs = await asyncio.gather(*[c.post("/api/listen/wordtest/answer", json={"session": w["session"], "item_key": wi["key"],
                                                                                  "answer": wi["target"]}, headers=h) for _ in range(2)])
            out["wtest_dup"] = sorted(x.status_code for x in rs)
            out["wtest_other"] = (await c.post("/api/listen/wordtest/answer", json={"session": w["session"], "item_key": wi["key"],
                                                                                  "answer": "x"}, headers=h)).status_code
            async with AsyncSessionLocal() as db:
                out["test_rows"] = (await db.execute(select(func.count(ListenAttempt.id)).where(ListenAttempt.session == ts["session"]))).scalar()
                out["wtest_rows"] = (await db.execute(select(func.count(ListenAttempt.id)).where(ListenAttempt.session == w["session"]))).scalar()
            res = {k: True for k in ["m", "u", "a", "i", "sh", "s"]}
            ling = lambda: c.post("/api/listen/ling", json={"results": res, "false_alarms": 10**30}, headers=h)
            rs = await asyncio.gather(ling(), ling())
            out["ling"] = [x.status_code for x in rs] + [rs[0].json()["summary"]["false_alarms"]]
            out["ling_attempts"] = (await c.get("/api/listen/curriculum", headers=h)).json()["stages"][0].get("attempts")
            # 입력 검증
            s5 = (await c.get("/api/listen/stage/5", headers=h)).json()["items"][0]
            out["convo_bad_choice"] = (await c.post("/api/listen/answer", json={"stage": 5, "item_key": s5["key"], "choice": 7}, headers=h)).status_code
            s4 = (await c.get("/api/listen/stage/4", headers=h)).json()["items"][0]
            out["noise_no_snr"] = (await c.post("/api/listen/answer", json={"stage": 4, "item_key": s4["key"], "answer": "x"}, headers=h)).status_code
            out["huge_plays"] = (await c.post("/api/listen/answer", json={"stage": 3, "item_key": its[0]["key"], "answer": "x",
                                                                           "plays": 10**20}, headers=h)).status_code
            w2 = (await c.get("/api/listen/stage/2", headers=h)).json()["items"][0]
            a2 = (await c.post("/api/listen/answer", json={"stage": 2, "item_key": w2["key"], "answer": w2["target"], "level": 0}, headers=h)).json()
            out["word_level0"] = a2.get("level")
            days = (await c.get("/api/listen/summary", headers=h)).json()["days"]
            out["days"] = [len(days), days[-1]["n"] > 0, isinstance(days[-1].get("minutes"), (int, float))]


asyncio.run(run())
print("RESULT " + json.dumps(out))
'''


def test_listen_concurrent_answers_and_validation():
    """같은 사용자의 답이 동시에 와도: 첫 답 두 개가 둘 다 기록되고(예전 둘째 500), 시도 수가 기록 수와 같고(예전 유실),
    검사·낱말 검사의 같은 문항 두 번은 하나만 남는다(예전 둘 다 들어감). 범위 밖 입력은 400·422."""
    import subprocess
    import sys
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1", LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW_RACE], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["first_pair"] == [200, 200]
    assert r["four"] == [200, 200, 200, 200]
    assert r["attempts"] == r["rows"] == 6
    # 같은 답이 두 번 오면 하나만 기록하고 둘 다 같은 결과(멱등), 다른 답이면 409
    assert r["test_dup"] == [200, 200] and r["test_dup_same_body"] and r["test_rows"] == 2
    assert r["test_resend"] == [200, True, True, True] and r["test_resend_other"] == 409
    assert r["wtest_dup"] == [200, 200] and r["wtest_rows"] == 1 and r["wtest_other"] == 409
    assert r["days"] == [7, True, True]
    assert r["ling"] == [200, 200, 2] and r["ling_attempts"] == 2
    assert r["convo_bad_choice"] == 400 and r["noise_no_snr"] == 400 and r["huge_plays"] == 422
    assert r["word_level0"] == 1


def test_today_plan():
    st = {0: "mastered", 1: "in_progress", 2: "locked", 3: "locked", 4: "locked", 5: "locked"}
    p = L.today_plan(st, ling_done_today=False)
    assert [b["mode"] for b in p] == ["ling", "ax"]
    assert p[1]["n"] > 12                       # 남는 시간을 수준 블록에 채운다
    st = {0: "mastered", 1: "mastered", 2: "mastered", 3: "mastered", 4: "in_progress", 5: "unlocked"}
    p = L.today_plan(st, ling_done_today=True)
    assert [b["mode"] for b in p] == ["word_id", "noise", "convo"]
    assert 12 <= sum(b["minutes"] for b in p) <= 17
    assert L.today_plan({0: "unlocked"}, ling_done_today=True) == []
