"""청인 예비 파일럿(P3) 검사 묶음 테스트(pilot_battery.py, docs/pilot/battery.md).

순수 함수(순서 배정, 목록 점검, 무의미 낱말 생성, 계단, 렌더링 기록 정리)는 바로 검사하고, API 흐름(파일럿 참여자만, 영상 없는 문항은
내지도 세지도 않음, 답 저장, 가명 내보내기 판 5, 학습 초기화·계정 삭제)은 test_pilot.py처럼 임시 DB의 별도 프로세스에서 돌린다.
"""
import functools
import json
import os
import subprocess
import sys
import tempfile
import types
from collections import Counter

import pytest

import pilot_battery as pb


# ── 순수 함수 ─────────────────────────────────────────
def test_order_assignment_is_cyclic_latin_square():
    orders = [pb.assign_order(i) for i in range(1, 10)]
    assert orders == ["ABC", "BCA", "CAB"] * 3
    # 세 순서를 같은 수로 채우면 회차마다 각 폼이 한 번씩 나온다(폼 난이도가 평균에서 상쇄)
    for label in ("A1", "A2", "B"):
        assert sorted(pb.form_for(o, label) for o in pb.ORDERS) == ["A", "B", "C"]
    # 한 사람 안에서 A1·A2·B는 서로 다른 폼, 유지 검사는 사후와 같은 폼
    for o in pb.ORDERS:
        forms = [pb.form_for(o, l) for l in ("A1", "A2", "B")]
        assert len(set(forms)) == 3 and pb.form_for(o, "R") == forms[2]
    with pytest.raises(ValueError):
        pb.form_for("ABC", "X")


def test_frozen_manifest_validates_and_counts():
    m = pb.load_manifest()
    assert pb.validate_manifest(m) == []
    L = m["layers"]
    for f in pb.FORMS:
        assert len(L["word"]["items"][f]) == 24
        assert len(L["sentence"]["items"][f]) == 40
        assert len(L["nonsense"]["items"][f]) == 16
        assert len(L["av"]["items"][f]) == 20
    # 문장: 6~10음절, 채점 음소 14~26, 폼 사이 음소 수 평균 차이 0.5 이하
    means = []
    for f in pb.FORMS:
        items = L["sentence"]["items"][f]
        assert all(6 <= len(pb.syllables(x["text"])) <= 10 and 14 <= pb.phoneme_count(x["text"]) <= 26 for x in items)
        means.append(sum(pb.phoneme_count(x["text"]) for x in items) / len(items))
    assert max(means) - min(means) <= 0.5
    # 소음 속 문장·SNR 문장은 10/7에 글을 정했다(조건·유사도 점검 통과). 말소리 크기는 촬영 전이라 비어 있다(지어낸 음성 없음)
    av_all = [x for f in pb.FORMS for x in L["av"]["items"][f]] + list(L["snr"]["items"])
    assert all(x["text"] and 6 <= len(pb.syllables(x["text"])) <= 10 and x["speech_rms_dbfs"] is None for x in av_all)
    assert len({x["text"] for x in av_all}) == len(av_all)
    open_texts = {x["text"] for f in pb.FORMS for x in L["sentence"]["items"][f]}
    assert not (open_texts & {x["text"] for x in av_all})


def test_validate_manifest_catches_errors():
    m = pb.load_manifest()
    bad = json.loads(json.dumps(m))
    bad["orders"] = ["ABC", "ABC", "CAB"]
    bad["layers"]["word"]["items"]["A"][0]["options"] = ["가", "가", "나", "다"]
    bad["layers"]["nonsense"]["items"]["B"][0]["text"] = "가나"
    bad["layers"]["sentence"]["items"]["C"].pop()
    bad["layers"]["word"]["media_pattern"] = "../{talker}/{id}.mp4"
    bad["layers_by_label"]["B"].append("snr")
    bad["layers"]["sentence"]["items"]["A"][1]["id"] = bad["layers"]["sentence"]["items"]["A"][0]["id"]
    errs = " | ".join(pb.validate_manifest(bad))
    for frag in ("라틴 방진", "word A1", "text가 자음", "sentence.C 문항 수", "word.media_pattern", "snr 층은 A1", "중복"):
        assert frag in errs, (frag, errs)


def test_nonsense_forms_use_c10_heldout_lists_and_never_trained_words():
    import nonsense_words as nw
    m = pb.load_manifest()
    L = m["layers"]["nonsense"]
    data = nw.load()
    forms = [[it["text"] for it in L["items"][f]] for f in pb.FORMS]
    # 폼 A·B는 짝 맞추기 학습이 남겨 둔 두 목록 그대로, 폼 C는 같은 생성기의 세 번째 남겨 둔 목록(다시 만들면 같다)
    assert forms[0] == data["heldout"][0] and forms[1] == data["heldout"][1]
    assert [[it["text"] for it in f] for f in pb.nonsense_forms()] == forms
    trained = {w["word"] for s in data["sets"] for w in s["words"]}
    trained_skel = {nw.skeleton(w) for w in trained}
    allw = [w for f in forms for w in f]
    assert len(trained) == 48 and len(set(allw)) == 48
    assert not (set(allw) & trained) and not ({nw.skeleton(w) for w in allw} & trained_skel)
    assert not (set(allw) & (nw.repo_real_words() | set(data["excluded_by_wordfreq"]) | nw.MANUAL_EXCLUDED
                             | pb.NONSENSE_EXTRA_EXCLUDED))
    assert L["consonant_sets"] == pb.nonsense_consonant_sets()
    for f in pb.FORMS:
        for it in L["items"][f]:
            c1, v1, c2, v2, c3 = nw.parts(it["text"])
            assert it["consonants"] == [c1, c2, c3] and it["vowels"] == [v1, v2]
    # 목록 파일(data/pilot)이 짝 맞추기 생성기의 '실제 낱말' 자료에 들어가지 않는다(넣으면 남겨 둔 목록이 스스로를 뺀다)
    assert "처슴" not in nw.repo_real_words()


@functools.lru_cache(maxsize=1)
def _builder():
    """scripts/build_pilot_manifest.py를 모듈로 불러온다(유사도 점검 함수와 폼 배정)."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "build_pilot_manifest.py")
    spec = importlib.util.spec_from_file_location("build_pilot_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_manifest_sentences_pass_similarity_guard():
    # 올린 목록의 개방형 문장이 스크립트의 폼 배정과 같고, 조건·훈련 문장 유사도·폼 문장끼리 유사도를 모두 통과한다.
    # 예비 문장도 훈련 문장, 폼 문장, 다른 예비 문장과 가깝지 않다
    B = _builder()
    m = pb.load_manifest()
    S = m["layers"]["sentence"]
    forms = {f: [x["text"] for x in S["items"][f]] for f in pb.FORMS}
    assert forms == B.FORM_SENTENCES
    words = {x["word"] for f in pb.FORMS for x in m["layers"]["word"]["items"][f]}
    training = B.training_sentences()
    assert len(training) > 300
    assert B.form_problems(forms, words, training) == []
    flat = [t for f in pb.FORMS for t in forms[f]]
    reserve = [x["text"] for x in S["reserve"]]
    assert len(reserve) == B.N_RESERVE
    for i, r in enumerate(reserve):
        assert not B.basic_problem(r, words), r
        assert not B.training_conflicts(r, training), r
        for t in flat + reserve[i + 1:]:
            assert not B.similarity_reasons(r, t, both_ways=True), (r, t)


def test_similarity_guard_catches_review_cases():
    # 10/7 내용 1차 검토(docs/review/pilot-sentences.tsv)가 훈련 문장·다른 검사 문장과 겹친다고 찾은 경우는 모두 걸리고,
    # 검토가 '가벼움'·'경계, 사람 판단'으로 둔 경우는 통과한다
    B = _builder()
    caught = [
        ("많이 기다렸지요", "많이 기다렸어?"), ("머리가 조금 아파요", "머리가 아파요."),
        ("엄마랑 시장에 갔어요", "엄마랑 시장에 가서 채소를 샀어."), ("내일 아침에 일찍 만나요", "내일 아침 아홉 시에 만나요."),
        ("맛있게 많이 드세요", "맛있게 드세요."), ("우산을 챙겨 가세요", "비가 올 것 같으니까 우산을 꼭 챙겨 가세요."),
        ("잠깐만 기다려 주세요", "잠시만 기다려 주세요."), ("조심히 들어가세요", "조심히 가세요."),
        ("창문 좀 열어 주세요", "더우니까 창문 좀 열어 줄래?"), ("밥을 천천히 먹어요", "천천히 먹어"),
        ("손을 깨끗이 씻으세요", "밥 먹기 전에 손을 깨끗이 씻어."), ("오늘 날씨가 참 좋네요", "오늘 날씨가 좋아요."),
        ("밤에 잠이 잘 안 와요", "밤에 잠이 안 와서 책을 읽었어."),   # 예비 SR04, 검토가 교체용으로 쓰지 않음
        ("약을 먹고 푹 쉬세요", "푹 쉬세요."), ("신발을 새로 샀어요", "이거 새로 샀어요?"),   # 점검이 더 찾은 둘
    ]
    for a, b in caught:
        assert B.similarity_reasons(a, b), (a, b)
    # 검사 문장끼리(같은 폼 포함, 다른 폼 틀 겹침)
    assert "포함" in B.similarity_reasons("동생이 감기에 걸렸어요", "감기에 걸렸어요", both_ways=True)
    assert B.similarity_reasons("전화가 잘 안 들려요", "소리가 잘 안 들려요", both_ways=True)
    assert B.similarity_reasons("머리가 조금 아파요", "다리가 조금 아파요", both_ways=True)
    passed = [
        ("물이 너무 뜨거워요", "솥뚜껑이 너무 뜨거워."), ("비가 그칠 것 같아요", "구름이 잔뜩 껴서 곧 비가 올 것 같아."),
        ("길을 잃어서 헤맸어요", "택시 기사가 길을 잘 몰라서 헤맸어."), ("주말에 산에 올라갔어요", "주말마다 아빠랑 산에 올라가."),
        ("너무 피곤해 보여요", "거울에 비친 내 얼굴이 피곤해 보여."), ("숙제를 다 끝냈어요", "친구 덕에 숙제를 빨리 끝냈어."),
        ("시장에서 사과를 샀어요", "엄마랑 시장에 가서 채소를 샀어."),
        ("감기에 걸렸어요", "요즘 날씨가 갑자기 추워져서 주변에 감기에 걸린 사람이 많다고 하네요."),
    ]
    for a, b in passed:
        assert not B.similarity_reasons(a, b), (a, b, B.similarity_reasons(a, b))
    assert not B.similarity_reasons("글씨가 너무 작아요", "옷이 너무 작아졌어요", both_ways=True)
    # 경계 표시는 검토의 '경계' 다섯을 잡는다(예비에서는 뺀다)
    for a, b in passed[2:7]:
        assert B.is_borderline(a, b), (a, b)


def test_word_form_c_matches_difficulty_and_avoids_test_words():
    m = pb.load_manifest()
    W = m["layers"]["word"]["items"]
    regen = pb.build_word_form_c(m["layers"]["word"]["word_c_seed"])
    assert [{k: x[k] for k in ("id", "word", "options", "difficulty")} for x in regen] == W["C"]
    mean = lambda f: sum(x["difficulty"] for x in W[f]) / len(W[f])   # noqa: E731
    assert abs(mean("C") - mean("A")) < 0.01 and abs(mean("C") - mean("B")) < 0.01
    ab = {x["word"] for f in "AB" for x in W[f]}
    assert not ({x["word"] for x in W["C"]} & ab)
    assert len({x["word"] for x in W["C"]}) == 24


def test_talker_and_block_assignment():
    talkers = ["T1", "T2", "T3", "T4"]
    for seq in (1, 2, 7):
        for label in ("A1", "A2", "B"):
            c = Counter(pb.word_talker(seq, label, i, talkers) for i in range(24))
            assert all(v == 6 for v in c.values())
    assert [pb.sentence_talker(s, ["T1", "T2"]) for s in range(1, 5)] == ["T1", "T2", "T1", "T2"]
    items = [{"id": f"V{i}"} for i in range(20)]
    blocks = [pb.av_blocks(items, s) for s in range(1, 5)]
    for b in blocks:
        assert Counter(x["block"] for x in b) == {"A": 10, "AV": 10}
    # 블록 순서는 참여자마다, 어느 절반이 A인지는 둘마다 바뀐다
    assert [b[0]["block"] for b in blocks] == ["A", "AV", "A", "AV"]
    first_half_a = [{x["id"] for x in b if x["block"] == "A"} == {f"V{i}" for i in range(10)} for b in blocks]
    assert first_half_a == [True, True, False, False]
    # 제시 순서는 결정론적이고 사람·회차마다 다르다
    its = [{"id": str(i)} for i in range(40)]
    assert pb.presentation_order(its, 3, "A1", "sentence") == pb.presentation_order(its, 3, "A1", "sentence")
    assert pb.presentation_order(its, 3, "A1", "sentence") != pb.presentation_order(its, 3, "A2", "sentence")


def test_item_readiness_and_media_paths(tmp_path):
    L = {"media_pattern": "words/{talker}/{id}.mp4"}
    rel = pb.media_relpath(L, {"id": "A1"}, "T1")
    assert rel == "words/T1/A1.mp4"
    assert pb.media_relpath(L, {"id": "../x"}, "T1") is None
    assert pb.media_path("../../etc/passwd", str(tmp_path)) is None
    assert not pb.media_exists(rel, str(tmp_path))
    (tmp_path / "words" / "T1").mkdir(parents=True)
    (tmp_path / "words" / "T1" / "A1.mp4").write_bytes(b"x")
    assert pb.media_exists(rel, str(tmp_path))
    assert pb.item_ready("word", "real", {"id": "A1"}, False) == (False, "media")
    assert pb.item_ready("word", "real", {"id": "A1"}, True) == (True, None)
    assert pb.item_ready("sentence", "avatar", {"id": "S", "text": "밥 먹어요"}, False) == (True, None)
    assert pb.item_ready("sentence", "real", {"id": "S", "text": "밥 먹어요"}, False) == (False, "media")
    assert pb.item_ready("av", "real", {"id": "V", "text": None}, True) == (False, "text")
    assert pb.item_ready("av", "real", {"id": "V", "text": "가", "speech_rms_dbfs": -20}, True, True, None) == (False, "snr")
    assert pb.item_ready("av", "real", {"id": "V", "text": "가", "speech_rms_dbfs": -20}, True, False, 0) == (False, "noise")
    assert pb.item_ready("av", "real", {"id": "V", "text": "가", "speech_rms_dbfs": -20}, True, True, -3) == (True, None)
    assert pb.item_ready("snr", "audio", {"id": "V", "text": "가", "speech_rms_dbfs": -20}, True, True, None) == (True, None)


def test_scoring_helpers():
    it = {"consonants": ["ㅂ", "ㄹ", "ㄱ"]}
    s = pb.score_nonsense(it, ["ㅂ", "ㄷ", "ㄱ"])
    assert s["hits"] == 2 and s["per_position"] == [True, False, True] and s["correct"] is False
    assert pb.score_nonsense(it, ["ㅂ", "ㄹ", "ㄱ"])["correct"] is True
    assert pb.score_nonsense(it, ["ㅂ"])["chosen"] == ["ㅂ", None, None]
    assert pb.score_choice({"word": "수박"}, "수박") and not pb.score_choice({"word": "수박"}, None)
    assert pb.clean_answer("  밥 먹어요 ") == "밥 먹어요"
    assert pb.word_proportion("밥을 먹어요.", "밥을 먹었어요") == 0.5
    # 띄어쓰기를 빼먹거나 잘못 띄어도 같다(검토 결함 4), 낱말 안 음절 끼움·순서 바뀜은 틀린다
    assert pb.word_proportion("감기에 걸렸어요.", "감기에걸렸어요") == 1.0
    assert pb.word_proportion("감기에 걸렸어요.", "감 기에 걸렸어요") == 1.0
    assert pb.word_proportion("감기에 걸렸어요", "걸렸어요 감기에") == 0.5
    assert pb.word_proportion("가 봐", "각 봐") == 0.5
    assert pb.phoneme_count("밥 먹어요") == 3 + 3 + 1 + 1   # 밥(ㅂㅏㅂ) 먹(ㅁㅓㄱ) 어(ㅓ) 요(ㅛ)


def test_strict_hook_absent_and_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "phoneme_accuracy", None)   # 모듈이 없을 때(import가 실패)
    assert pb.strict_score("밥", "밥") is None
    assert pb.strict_fields(None) == {"auto_phoneme_acc": None, "auto_word_acc": None, "n_matched_phonemes": None,
                                      "n_target_phonemes": None, "strict_version": None}
    fake = types.ModuleType("phoneme_accuracy")
    fake.strict_phoneme_accuracy = lambda t, a: {"phoneme_accuracy": 0.75, "word_accuracy": 0.5, "version": "s1"}
    monkeypatch.setitem(sys.modules, "phoneme_accuracy", fake)
    r = pb.strict_score("밥 먹어요", "밥 먹어")
    assert pb.strict_fields(r) == {"auto_phoneme_acc": 0.75, "auto_word_acc": 0.5, "n_matched_phonemes": None,
                                   "n_target_phonemes": None, "strict_version": "s1"}
    fake.strict_phoneme_accuracy = lambda t, a: 1 / 0
    assert pb.strict_score("밥", "밥") is None


def test_staircase_converges_near_target_proportion():
    import random
    params = {"start_db": 0, "step_down_db": 3, "step_up_db": 2, "min_db": -20, "max_db": 10, "reversals": 8,
              "use_last": 6, "max_trials": 200}
    # 모의 청자: SNR이 높을수록 맞힘(로지스틱, 50% 지점 −6 dB, 기울기 0.3/dB). 가중 계단은 p = 0.4 근처(약 −7.4 dB)로 간다
    import math
    ests = []
    for seed in range(200):
        rng = random.Random(seed)
        outs = []
        while True:
            st = pb.staircase_run(params, outs)
            if st["done"]:
                break
            p = 1 / (1 + math.exp(-0.3 * (st["next_db"] + 6)))
            outs.append(rng.random() < p)
        ests.append(st["estimate_db"])
    mean = sum(ests) / len(ests)
    assert -10 < mean < -5, mean
    st = pb.staircase_run({**params, "max_trials": 4}, [True, True, True, True])
    assert st["done"] and st["history"] == [0, -3, -6, -9] and st["estimate_db"] is None   # 반전 없음, 시행 4 < use_last 6
    st = pb.staircase_run({**params, "max_trials": 6}, [True] * 6)
    assert st["estimate_kind"] == "last_levels" and st["estimate_db"] == round(sum([0, -3, -6, -9, -12, -15]) / 6, 2)
    assert pb.staircase_run(params, [])["next_db"] == 0
    assert abs(pb.noise_gain(-20, -20, 0) - 1.0) < 1e-9 and abs(pb.noise_gain(-20, -20, 6) - 10 ** (-6 / 20)) < 1e-9


def test_clean_render_log_keeps_only_known_keys():
    raw = {"frames": 120, "mean_late_ms": 3.2, "over20_rate": 2, "render_mode": "avatar3d", "device_class": "phone",
           "gpu_renderer": "ANGLE (Apple M1)", "user_agent": "Mozilla/5.0", "dpr": 2, "os_family": "beos", "webgl": True}
    out = pb.clean_render_log(raw)
    assert out == {"frames": 120.0, "mean_late_ms": 3.2, "over20_rate": 1.0, "render_mode": "avatar3d",
                   "device_class": "phone", "dpr": 2.0, "webgl": True}
    assert pb.clean_render_log("x") is None and pb.clean_render_log({"foo": 1}) is None


# ── API 흐름(별도 프로세스, 임시 DB·임시 매체 폴더) ───────────────
_SCENARIO = r'''
import json, os, sys
from fastapi.testclient import TestClient
import pilot_battery as pb
media = os.environ["LIPLAB_PILOT_MEDIA_DIR"]
# 목록 사본: SNR·소음 문장 몇 개에 글과 크기를 넣고(테스트 전용) 매체 파일을 만든다
m = pb.load_manifest()
for i, it in enumerate(m["layers"]["snr"]["items"]):
    it["text"], it["speech_rms_dbfs"] = "밥을 먹었어요", -23.0
for f in pb.FORMS:
    for it in m["layers"]["av"]["items"][f][:4]:
        it["text"], it["speech_rms_dbfs"] = "물을 마셨어요", -23.0
mp = os.path.join(media, "manifest.json")
json.dump(m, open(mp, "w"), ensure_ascii=False)
os.environ["LIPLAB_PILOT_MANIFEST"] = mp
def touch(rel):
    p = os.path.join(media, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(b"\x00" * 16)
import main
out = {}
with TestClient(main.app) as c:
    def reg(email, name):
        r = c.post("/api/auth/register", json={"email": email, "username": name, "password": "pw-123456",
                                               "agree_terms": True, "age_confirmed": True})
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    p1 = reg("b1@example.com", "batt1"); p2 = reg("b2@example.com", "batt2"); op = reg("op@example.com", "operator")
    out["off"] = c.get("/api/pilot/battery/status", headers=p1).status_code
    os.environ["LIPLAB_PILOT"] = "1"; os.environ["LIPLAB_PILOT_CODES"] = "ALPHA:train"; os.environ["LIPLAB_ADMIN_EMAILS"] = "op@example.com"
    out["not_joined"] = c.get("/api/pilot/battery/status", headers=p1).status_code
    demo = {"Authorization": "Bearer " + c.post("/api/auth/demo").json()["access_token"]}
    out["demo"] = c.get("/api/pilot/battery/status", headers=demo).status_code
    c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=p1)
    c.post("/api/pilot/join", json={"code": "ALPHA"}, headers=p2)
    st1 = c.get("/api/pilot/battery/status", headers=p1).json()
    st2 = c.get("/api/pilot/battery/status", headers=p2).json()
    out["orders"] = [(st1["seq"], st1["order"]), (st2["seq"], st2["order"])]
    out["status_again"] = c.get("/api/pilot/battery/status", headers=p1).json()["seq"]
    out["labels"] = [(l["label"], l["form"], l["available"]) for l in st1["labels"]]
    out["next"] = st1["next_label"]
    out["manifest_errors"] = st1["manifest"]["n_errors"]
    out["a2_locked"] = c.post("/api/pilot/battery/start", json={"label": "A2", "layer": "word"}, headers=p1).status_code
    out["bad_layer"] = c.post("/api/pilot/battery/start", json={"label": "R", "layer": "snr"}, headers=p1).status_code

    # 무의미 낱말(아바타, 매체 필요 없음): 정답 글 없이 입모양 프레임만 온다
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "nonsense"}, headers=p1).json()
    out["nonsense"] = {"n": s["n_items"], "ready": s["n_ready"], "has_frames": all(i.get("frames") for i in s["items"]),
                       "leak": any("text" in i or "consonants" in i for i in s["items"]), "sets": sorted(s["consonant_sets"])}
    form = s["form"]
    tgt = {it["id"]: it for it in m["layers"]["nonsense"]["items"][form]}
    first = s["items"][0]
    t = tgt[first["id"]]["consonants"]
    r = c.post("/api/pilot/battery/answer", json={"session_id": s["session_id"], "item_id": first["id"],
               "chosen_consonants": [t[0], t[1], "ㅇ" if t[2] != "ㅇ" else "ㄱ"], "rt_ms": 1500, "rt_from_onset_ms": 2400, "plays": 2},
               headers=p1)
    out["nonsense_answer"] = r.json()
    out["nonsense_dup"] = c.post("/api/pilot/battery/answer", json={"session_id": s["session_id"], "item_id": first["id"],
                                 "chosen_consonants": t}, headers=p1).json()
    out["nonsense_bad"] = c.post("/api/pilot/battery/answer", json={"session_id": s["session_id"], "item_id": s["items"][1]["id"],
                                 "chosen_consonants": ["ㄲ", None, None]}, headers=p1).status_code
    out["other_user"] = c.post("/api/pilot/battery/answer", json={"session_id": s["session_id"], "item_id": first["id"],
                               "chosen_consonants": t}, headers=p2).status_code
    fin = c.post("/api/pilot/battery/finish", json={"session_id": s["session_id"], "render_log": {
        "frames": 300, "mean_late_ms": 2.5, "render_mode": "avatar3d", "screen_w": 1280, "dpr": 2, "gpu_renderer": "X"}},
        headers=p1).json()
    out["nonsense_finish"] = fin
    out["finished_again"] = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "nonsense"}, headers=p1).status_code

    # 실제 얼굴 낱말: 영상 두 개만 만들면 그 두 문항만 '준비됨', 나머지는 내지도 받지도 않는다
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "word"}, headers=p1).json()
    out["word_before"] = {"n": s["n_items"], "ready": s["n_ready"], "missing": s["missing"]}
    wid = s["session_id"]
    ready_ids = []
    for it in s["items"][:2]:
        # 회차 순서의 첫 두 문항 영상을 만든다(화자는 서버 배정을 따른다)
        x = next(x for x in main._battery_items(m, "A1", "word", st1["seq"], st1["order"]) if x["item"]["id"] == it["id"])
        touch(x["rel"]); ready_ids.append(it["id"])
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "word"}, headers=p1).json()
    out["word_after"] = {"ready": s["n_ready"], "ids": sorted(i["id"] for i in s["items"] if i["ready"]) == sorted(ready_ids),
                         "media": all(i.get("media", "").startswith("/pilot/battery/media/") for i in s["items"] if i["ready"])}
    it0 = next(i for i in s["items"] if i["ready"])
    out["media_get"] = c.get("/api/pilot" + it0["media"][len("/pilot"):], headers=p1).status_code
    out["media_other"] = c.get("/api/pilot" + it0["media"][len("/pilot"):], headers=p2).status_code
    notready = next(i for i in s["items"] if not i["ready"])
    out["not_ready_answer"] = c.post("/api/pilot/battery/answer", json={"session_id": wid, "item_id": notready["id"],
                                     "chosen": "가"}, headers=p1).status_code
    out["media_missing"] = c.get(f"/api/pilot/battery/media/{wid}/{notready['id']}", headers=p1).status_code
    out["word_bad_choice"] = c.post("/api/pilot/battery/answer", json={"session_id": wid, "item_id": it0["id"], "chosen": "없는말"},
                                    headers=p1).status_code
    c.post("/api/pilot/battery/answer", json={"session_id": wid, "item_id": it0["id"], "chosen": it0["options"][0],
           "rt_ms": 800, "rt_from_onset_ms": 1900, "plays": 1}, headers=p1)
    out["word_finish"] = c.post("/api/pilot/battery/finish", json={"session_id": wid}, headers=p1).json()

    # 개방형 문장(아바타 조건): 원문과 앱 점수를 남긴다. 엄격 음소 정답률 모듈이 없으면 NULL
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "sentence"}, headers=p1).json()
    out["sentence"] = {"modality": s["modality"], "ready": s["n_ready"], "leak": any("text" in i for i in s["items"])}
    sid = s["session_id"]
    stg = {it["id"]: it["text"] for it in m["layers"]["sentence"]["items"][s["form"]]}
    i0, i1 = s["items"][0]["id"], s["items"][1]["id"]
    c.post("/api/pilot/battery/answer", json={"session_id": sid, "item_id": i0, "answer_text": " " + stg[i0] + " ", "rt_ms": 4000,
           "rt_from_onset_ms": 6000, "plays": 1}, headers=p1)
    c.post("/api/pilot/battery/answer", json={"session_id": sid, "item_id": i1, "answer_text": ""}, headers=p1)
    out["sentence_targets"] = [stg[i0], stg[i1]]

    # SNR 계단(테스트 목록에 글·크기를 넣고 매체를 만든 뒤): 판정에 따라 다음 SNR이 바뀐다
    out["snr_not_ready"] = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "snr"}, headers=p1).json()["missing"]
    for it in m["layers"]["snr"]["items"]:
        for tk in ("T1", "T2"):
            touch(f"av/{tk}/{it['id']}.mp4")
    for f in pb.FORMS:
        for it in m["layers"]["av"]["items"][f][:4]:
            for tk in ("T1", "T2"):
                touch(f"av/{tk}/{it['id']}.mp4")
    out["snr_no_noise"] = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "snr"}, headers=p1).json()["missing"]
    touch("noise/babble.wav")
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "snr"}, headers=p1).json()
    out["snr_start"] = {"ready": s["n_ready"], "next": s["staircase"]["next_db"], "noise": s["noise"].startswith("/pilot/battery/noise/")}
    out["noise_get"] = c.get("/api/pilot" + s["noise"][len("/pilot"):], headers=p1).status_code
    snr_id = s["session_id"]
    seqs = []
    early = c.post("/api/pilot/battery/finish", json={"session_id": snr_id}, headers=p1).status_code
    out["snr_early_finish"] = early
    for k, it in enumerate(s["items"]):
        ok = (k % 3 != 2)
        r = c.post("/api/pilot/battery/answer", json={"session_id": snr_id, "item_id": it["id"],
                   "answer_text": "밥을 먹었어요" if ok else "모르겠어요"}, headers=p1).json()
        if r.get("recorded"):
            seqs.append(r["staircase"]["next_db"])
        if r.get("staircase", {}).get("done"):
            break
    out["snr_levels"] = seqs[:4]
    fin = c.post("/api/pilot/battery/finish", json={"session_id": snr_id, "headphone_check": True, "volume_fixed": True}, headers=p1).json()
    out["snr_finish"] = {"est": fin.get("snr_calibrated_db"), "kind": fin.get("estimate_kind")}
    s = c.post("/api/pilot/battery/start", json={"label": "A1", "layer": "av"}, headers=p1).json()
    out["av_start"] = {"ready": s["n_ready"], "snr": s["snr_db"], "blocks": sorted({i["modality"] for i in s["items"] if i["ready"]}),
                       "missing": s["missing"]}
    av_it = next(i for i in s["items"] if i["ready"])
    c.post("/api/pilot/battery/answer", json={"session_id": s["session_id"], "item_id": av_it["id"], "answer_text": "물을 마셨어요"},
           headers=p1)

    # 학습 시행의 측정 필드(P0)
    item = main._training_closures()[0]
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"], "options": item.get("options"),
           "rt_from_onset_ms": 3210, "talker": "t2", "hint_used": True}, headers=p1)
    c.post("/api/curriculum/closure-answer", json={"item_id": item["id"], "chosen": item["answer"], "talker": "bad talker!"}, headers=p1)
    c.post("/api/lesson/effort", json={"session_id": "ls-abcdef", "lesson_kind": "word", "stage": 2, "rating": 4,
           "render_log": {"frames": 50, "dpr": 3, "user_agent": "x"}}, headers=p1)

    ex = c.get("/api/pilot/export", params={"trials": True}, headers=op).json()
    out["version"] = ex["version"]
    row = next(r for r in ex["participants"] if r["join_seq"] == st1["seq"])
    out["export_row_keys"] = sorted(k for k in ("join_seq", "planned_order", "b_completed_seq", "battery", "review_logs",
                                                  "mastery_probes", "retention_results", "lesson_efforts", "progress_log",
                                                  "trial_log") if k in row)
    out["planned_order"] = row["planned_order"]
    bat = {(b["session_label"], b["layer"]): b for b in row["battery"]}
    out["bat_keys"] = sorted(f"{a}:{b}" for a, b in bat)
    nb = bat[("A1", "nonsense")]
    out["bat_nonsense"] = {"completed": nb["completed"], "n_ready": nb["n_ready"], "render": nb["render_log"],
                           "resp": nb["closed"][0] if nb["closed"] else None}
    out["bat_word"] = {"missing": bat[("A1", "word")]["missing"], "n_closed": len(bat[("A1", "word")]["closed"])}
    out["bat_sentence"] = bat[("A1", "sentence")]["open"]
    out["bat_snr"] = {"est": bat[("A1", "snr")]["snr_calibrated_db"], "hp": bat[("A1", "snr")]["headphone_check"],
                      "n": len(bat[("A1", "snr")]["open"]), "snr0": bat[("A1", "snr")]["open"][0]["snr_db"]}
    out["bat_av"] = bat[("A1", "av")]["open"][0]
    out["trial_meta"] = [{k: t.get(k) for k in ("talker", "rt_from_onset_ms", "hint_used", "target", "options", "chosen")}
                         for t in row["trial_log"]]
    out["effort_render"] = row["lesson_efforts"][0]["render_log"] if row["lesson_efforts"] else None
    out["text"] = json.dumps(ex, ensure_ascii=False)

    # 학습 초기화: 파일럿 참여자는 P3 기록이 남는다
    rr = c.post("/api/account/learning-reset", params={"confirm": True}, headers=p1).json()
    out["reset_kept"] = rr.get("kept")
    out["reset_removed_p3"] = rr["removed"].get("p3_test_sessions")
    out["after_reset_status"] = [(l["label"], [x["state"] for x in l["layers"]]) for l in
                                 c.get("/api/pilot/battery/status", headers=p1).json()["labels"]][:1]
    # 계정 삭제: P3 기록까지 모두 지운다(user_id가 있는 모든 표, pilot_data.user_data_models)
    d = c.request("DELETE", "/api/account", params={"confirm": True}, json={"password": "pw-123456"}, headers=p1).json()
    out["deleted_counts"] = {k: v for k, v in d["removed"].items() if k.startswith("p3_")}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


@functools.lru_cache(maxsize=1)
def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        media = os.path.join(d, "media")
        os.makedirs(media)
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_PILOT_MEDIA_DIR=media)
        for k in ("LIPLAB_PILOT", "LIPLAB_PILOT_CODES", "LIPLAB_ADMIN_EMAILS", "LIPLAB_PILOT_NOCUE_COHORTS",
                  "LIPLAB_PILOT_SECRET", "LIPLAB_PILOT_MANIFEST", "ANTHROPIC_API_KEY"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}"
    return json.loads(line[len("RESULT "):])


def test_battery_gate_and_order():
    r = _run()
    assert r["off"] == 403 and r["not_joined"] == 403 and r["demo"] == 403
    assert r["orders"] == [[1, "ABC"], [2, "BCA"]] and r["status_again"] == 1
    assert r["labels"] == [["A1", "A", True], ["A2", "B", False], ["B", "C", False], ["R", "C", False]]
    assert r["next"] == "A1" and r["manifest_errors"] == 0
    assert r["a2_locked"] == 409 and r["bad_layer"] == 400


def test_battery_nonsense_and_missing_media():
    r = _run()
    ns = r["nonsense"]
    assert ns == {"n": 16, "ready": 16, "has_frames": True, "leak": False, "sets": ["C1", "C2", "C3"]}
    assert r["nonsense_answer"] == {"recorded": True} and r["nonsense_dup"] == {"recorded": False, "duplicate": True}
    assert r["nonsense_bad"] == 400 and r["other_user"] == 404
    assert r["nonsense_finish"]["completed"] and r["nonsense_finish"]["n_answered"] == 1 and r["finished_again"] == 409
    assert r["word_before"] == {"n": 24, "ready": 0, "missing": {"media": 24}}
    assert r["word_after"] == {"ready": 2, "ids": True, "media": True}
    assert r["media_get"] == 200 and r["media_other"] == 404 and r["media_missing"] == 404
    assert r["not_ready_answer"] == 409 and r["word_bad_choice"] == 400
    assert r["word_finish"]["n_ready"] == 2 and r["word_finish"]["missing"] == {"media": 22} and r["word_finish"]["n_answered"] == 1


def test_battery_open_responses_snr_and_av():
    r = _run()
    assert r["sentence"] == {"modality": "avatar", "ready": 40, "leak": False}
    first, second = r["bat_sentence"]
    assert first["answer_text"] == r["sentence_targets"][0] and first["app_score"] == 100.0
    # 엄격 음소 정답률(phoneme_accuracy.py, 0~1)과 회차 합산용 음소 수
    assert first["auto_phoneme_acc"] == 1.0 and first["scorer_version"] == "strict-v1"
    assert first["n_target_phonemes"] > 0 and first["n_matched_phonemes"] == first["n_target_phonemes"]
    assert first["rt_ms"] == 4000 and first["rt_from_onset_ms"] == 6000 and first["modality"] == "avatar"
    assert second["answer_text"] == "" and second["app_score"] == 0.0 and second["n_matched_phonemes"] == 0
    assert r["snr_not_ready"] == {"media": 24}
    assert r["snr_no_noise"] == {"noise": 24}
    assert r["snr_start"] == {"ready": 24, "next": 0, "noise": True} and r["noise_get"] == 200
    assert r["snr_early_finish"] == 409
    assert r["snr_levels"][:3] == [-3, -6, -4]   # 맞음 −3, 맞음 −3, 틀림 +2
    assert r["snr_finish"]["est"] is not None and r["snr_finish"]["kind"] in ("reversals", "last_levels")
    av = r["av_start"]
    assert av["snr"] == r["snr_finish"]["est"] and av["ready"] == 4 and av["missing"] == {"media": 16}
    assert set(av["blocks"]) <= {"A", "AV"} and av["blocks"]
    assert r["bat_av"]["snr_db"] == r["snr_finish"]["est"] and r["bat_av"]["noise_type"] == "babble"
    assert r["bat_av"]["modality"] in ("A", "AV")
    assert r["bat_snr"]["hp"] is True and r["bat_snr"]["snr0"] == 0


def test_battery_export_v5_and_training_fields():
    r = _run()
    assert r["version"] == 6
    assert r["export_row_keys"] == sorted(["join_seq", "planned_order", "b_completed_seq", "battery", "review_logs",
                                           "mastery_probes", "retention_results", "lesson_efforts", "progress_log", "trial_log"])
    assert r["planned_order"] == "ABC"
    assert r["bat_keys"] == ["A1:av", "A1:nonsense", "A1:sentence", "A1:snr", "A1:word"]
    nb = r["bat_nonsense"]
    assert nb["completed"] and nb["n_ready"] == 16
    assert nb["render"] == {"frames": 300.0, "mean_late_ms": 2.5, "render_mode": "avatar3d", "screen_w": 1280.0, "dpr": 2.0}
    resp = nb["resp"]
    assert resp["consonant_hits"] == 2 and resp["correct"] is False and resp["plays"] == 2 and resp["rt_ms"] == 1500
    assert len(resp["target_consonants"]) == 3 and resp["speed"] == 1.0
    assert r["bat_word"] == {"missing": {"media": 22}, "n_closed": 1}
    tm = r["trial_meta"]
    assert tm[0]["talker"] == "t2" and tm[0]["rt_from_onset_ms"] == 3210 and tm[0]["hint_used"] is True and tm[0]["target"]
    assert tm[1]["talker"] is None
    assert r["effort_render"] == {"frames": 50.0, "dpr": 3.0}
    assert "b1@example.com" not in r["text"] and "batt1" not in r["text"]


def test_battery_reset_keeps_and_delete_removes():
    r = _run()
    assert r["reset_kept"]["p3_test_sessions"] == 5 and r["reset_removed_p3"] is None
    assert r["after_reset_status"][0][1][0] == "done"
    assert r["deleted_counts"]["p3_test_sessions"] == 5
    assert r["deleted_counts"]["p3_closed_responses"] == 2 and r["deleted_counts"]["p3_open_responses"] >= 4


def test_rescore_script_fills_missing_strict_scores(monkeypatch):
    here = os.path.dirname(os.path.abspath(__file__))
    monkeypatch.syspath_prepend(os.path.join(here, "..", "scripts"))
    import pilot_battery_rescore as rs
    ex = {"version": 5, "participants": [{"battery": [{"open": [
        {"target": "밥 먹어요", "answer_text": "밥 먹어", "auto_phoneme_acc": None},
        {"target": "물", "answer_text": "물", "auto_phoneme_acc": 1.0}]}]}]}
    monkeypatch.setitem(sys.modules, "phoneme_accuracy", None)
    assert rs.rescore(json.loads(json.dumps(ex))) == {"filled": 0, "skipped": 1, "unavailable": 1}
    fake = types.ModuleType("phoneme_accuracy")
    fake.strict_phoneme_accuracy = lambda t, a: {"phoneme_accuracy": 0.8}
    monkeypatch.setitem(sys.modules, "phoneme_accuracy", fake)
    e2 = json.loads(json.dumps(ex))
    assert rs.rescore(e2) == {"filled": 1, "skipped": 1, "unavailable": 0}
    assert e2["participants"][0]["battery"][0]["open"][0]["auto_phoneme_acc"] == 0.8


def test_strict_hook_with_real_module():
    r = pb.strict_score("밥 먹어요", "밥 먹어")
    f = pb.strict_fields(r)
    assert f["strict_version"] == "strict-v1" and 0 < f["auto_phoneme_acc"] < 1
    assert f["n_target_phonemes"] >= f["n_matched_phonemes"] > 0


def test_label_done_is_stable_once_later_label_started():
    # 검토 결함 6: 뒤 회차를 시작했으면, 건너뛴 층에 나중에 영상이 생겨도 앞 회차는 마친 것으로 본다
    import main
    class R:
        def __init__(self, completed): self.completed = completed
    m = {"layers_by_label": {"A1": ["word"], "A2": ["word"]}, "layers": {"word": {}}}
    rows = {("A2", "word"): R(False)}
    assert main._battery_label_done(m, rows, "A1", 1, "ABC") is True


_FLOW_SEQ = r'''
import asyncio, json
import database
from sqlalchemy.exc import IntegrityError
async def run():
    await database.init_db()
    async with database.AsyncSessionLocal() as db:
        db.add(database.LearningProfile(user_id=1, pilot_seq=5))
        db.add(database.LearningProfile(user_id=2, pilot_seq=None))
        db.add(database.LearningProfile(user_id=3, pilot_seq=None))
        await db.commit()
    async with database.AsyncSessionLocal() as db:
        db.add(database.LearningProfile(user_id=4, pilot_seq=5))
        try:
            await db.commit(); return "no-error"
        except IntegrityError:
            return "blocked"
print("RESULT " + json.dumps(asyncio.run(run())))
'''


def test_pilot_seq_unique_index_blocks_duplicates():
    # 검토 결함 2: 같은 순간 처음 연 두 참여자가 같은 순번을 받지 못하게 고유 인덱스(NULL은 여럿 허용)
    import json, os, subprocess, sys, tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW_SEQ], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    assert json.loads(line[len("RESULT "):]) == "blocked"
