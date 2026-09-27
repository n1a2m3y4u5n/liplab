"""
시각 난이도 모듈(visual_difficulty) 검증 테스트.

입모양 순열·가시성·동구형이음/최소대립 이웃·점수의 단조성·2단계 보기 구성·시나리오 구간 선별이
규칙대로 동작하는지 결정론적으로 확인한다. DB·네트워크·API 키 없이 실행된다.

실행: python3 test_visual_difficulty.py   또는   pytest test_visual_difficulty.py
"""
import random
import unicodedata

import content_rules as R
import curriculum as C
import visual_difficulty as V

SMALL = ["밥", "맘", "밤", "달", "탈", "갈", "말", "발", "바", "우유", "이유", "오이", "사과", "다과",
         "자전거", "나무", "하늘", "가방", "코", "고", "소", "물", "불", "풀", "눈", "손"]


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_visibility_classes_follow_curriculum_labels():
    _ok(V.VISIBILITY_CLASS == {l["viseme_id"]: l["visibility"] for l in C.VISEME_LESSONS},
        "가시성 등급은 VISEME_LESSONS 라벨을 그대로 따른다")
    _ok(V.VISIBILITY_CLASS[1] == "high" and V.VISIBILITY_CLASS[5] == "medium" and V.VISIBILITY_CLASS[6] == "low",
        "양순 high, 중설 medium, 치경 low")
    _ok(set(V.INSIDE_CLUSTER) == set(R._INSIDE_CLUSTER) == {6, 7, 8, 10},
        "입 안쪽 무리는 content_rules와 같은 6·7·8·10")


def test_viseme_sequence_uses_pronounced_form_like_the_app():
    for w in [x["word"] for x in C.WORD_BANK][:200]:
        _ok(V.viseme_sequence(w) == R.viseme_signature(w), f"앱 시그니처와 같아야 한다: {w}")
    _ok(V.viseme_sequence("밥을") == (1, 2, 1, 5, 6), "연음: 밥을 → 바블")
    _ok(V.viseme_sequence("좋다") == (10, 4, 6, 2), "격음화: 좋다 → 조타(ㅎ 프레임 없음)")
    _ok(V.viseme_sequence("같이") == (7, 2, 10, 3), "구개음화: 같이 → 가치")
    nfd = unicodedata.normalize("NFD", "사과")
    _ok(V.viseme_sequence(nfd) == V.viseme_sequence("사과"), "분해형(NFD) 입력도 같은 결과")
    s = "밥을 먹었어요"
    _ok(V.viseme_sequence(s) == V.viseme_sequence("밥을") + V.viseme_sequence("먹었어요"),
        "공백은 연음을 끊으므로 문장 = 어절 순열의 연결")


def test_visibility_profile_and_low_share():
    p = V.visibility_profile(V.viseme_sequence("달"))
    _ok(abs(p["low"] - 2 / 3) < 1e-3 and abs(p["invisibility"] - 2 / 3) < 1e-3, "달: ㄷ·ㄹ low, ㅏ high")
    _ok(V.low_visibility_share("우유") == 0.0, "우유는 전부 잘 보임")
    _ok(V.visibility_profile(V.viseme_sequence("어"))["invisibility"] == 0.5, "중설모음은 가중 0.5")
    _ok(V.visibility_profile(())["invisibility"] == 0.0, "빈 순열은 0")


def test_vocab_index_neighbors():
    idx = V.VocabIndex(SMALL)
    _ok(set(idx.homophenes("밥")) == {"맘", "밤"}, "밥의 동구형이음은 맘·밤(순열 [1,2,1])")
    _ok("밥" not in idx.homophenes("밥"), "자기 자신은 이웃이 아니다")
    _ok(set(idx.homophenes("달")) == {"탈"}, "달·탈은 동구형이음")
    _ok("갈" in idx.near_homophenes("달") and "갈" not in idx.homophenes("달"),
        "달/갈은 입 안쪽 무리(6↔7) 차이뿐이라 준동구형")
    mp = set(idx.minimal_pairs("달"))
    _ok({"말", "발", "갈"} <= mp, "달의 최소대립에 말·발(보이는 차이)과 갈(안 보이는 차이)이 든다")
    vis = set(idx.visible_minimal_pairs("달"))
    _ok({"말", "발"} <= vis and "갈" not in vis, "보이는 최소대립에서 입 안쪽끼리의 차이는 빠진다")
    _ok("바" not in idx.minimal_pairs("밥"), "삽입·삭제(바/밥)는 최소대립으로 세지 않는다")
    _ok(V.homophene_neighbors("밥", SMALL) == idx.homophenes("밥"), "목록으로 줘도 같다")
    _ok(V.minimal_pair_neighbors("밥", None) == [], "어휘가 없으면 이웃 없음")
    _ok(len(V.VocabIndex(["밥", "밥", "apple", ""])) == 1, "중복·비한글·빈 값은 색인에서 빠진다")


def test_score_is_bounded_and_monotone():
    _ok(abs(V.W_INVISIBILITY + V.W_HOMOPHENE + V.W_MINIMAL + V.W_BREVITY - 1.0) < 1e-9, "가중 합은 1")
    base = dict(invisibility=0.4, n_homophenes=1, n_minimal=2, n_syllables=2)
    s0 = V.score_from_features(**base)
    for key, bigger in (("invisibility", 0.6), ("n_homophenes", 3), ("n_minimal", 6)):
        _ok(V.score_from_features(**{**base, key: bigger}) > s0, f"{key}가 커지면 점수도 커진다")
    _ok(V.score_from_features(**{**base, "n_syllables": 3}) < s0, "음절이 많을수록 점수는 작아진다")
    _ok(V.score_from_features(0.0, 0, 0, 10**6) >= 0.0, "하한 0")
    _ok(V.score_from_features(1.0, 10**6, 10**6, 1) <= 1.0, "상한 1")
    _ok(V.homophene_term(1) == 0.5 and V.minimal_term(3) == 0.5, "반포화점: 동구형이음 1, 최소대립 3")


def test_word_difficulty_features_and_ordering():
    idx = V.VocabIndex([w["word"] for w in C.WORD_BANK])
    _ok(V.word_difficulty("apple", idx) is None and V.word_difficulty("", idx) is None, "비한글·빈 값은 None")
    d = V.word_difficulty("밥", idx)
    _ok(d["visemes"] == [1, 2, 1] and d["syllables"] == 1 and d["low_share"] == 0.0, "밥의 특징")
    _ok(d["n_homophenes"] == len(d["homophenes"]) >= 2, "밥은 은행 안에 동구형이음이 있다")
    _ok(V.word_difficulty("달", idx)["score"] > V.word_difficulty("우유", idx)["score"],
        "입 안쪽 자음이 많고 동구형이음이 많은 달이 우유보다 어렵다")
    _ok(V.word_difficulty("자전거", idx)["score"] < V.word_difficulty("눈", idx)["score"],
        "이웃이 없는 긴 단어가 이웃 많은 1음절보다 쉽다")
    no_vocab = V.word_difficulty("밥")
    _ok(no_vocab["n_homophenes"] == 0 and no_vocab["score"] < d["score"], "어휘가 없으면 이웃 성분이 0")


def test_sentence_difficulty_and_dispatch():
    idx = V.VocabIndex(SMALL + ["아이"])
    _ok(V.lookup_key("밥을", idx) == "밥", "어휘에 어간이 있으면 조사를 뗀다")
    _ok(V.lookup_key("아이", idx) == "아이", "어절 자체가 어휘에 있으면 떼지 않는다(아이 → 아 오분리 방지)")
    _ok(V.lookup_key("아이가", idx) == "아이", "아이가 → 아이")
    _ok(V.lookup_key("주세요", idx) == "주세요", "어간이 어휘에 없으면 그대로")
    s = V.sentence_difficulty("밥을 먹었어요.", idx)
    _ok(s["n_eojeol"] == 2 and s["eojeols"][0]["key"] == "밥" and s["eojeols"][0]["n_homophenes"] == 2,
        "문장의 어절 이웃은 어간으로 찾는다")
    _ok(0.0 <= s["score"] <= 1.0 and s["chars"] == len("밥을 먹었어요."), "문장 점수 범위와 글자 수")
    _ok(V.difficulty("밥", idx)["score"] == V.word_difficulty("밥", idx)["score"], "어절 하나면 단어 점수")
    _ok("n_eojeol" in V.difficulty("밥 먹어", idx), "어절이 둘 이상이면 문장 점수")
    _ok(V.sentence_difficulty("!!! ???") is None, "보이는 입모양이 없으면 None")


def test_distractor_kind_examples():
    _ok(V.distractor_kind("밥", "맘") == "homophene", "밥/맘 동구형이음")
    _ok(V.distractor_kind("달", "갈") == "near_homophene", "달/갈 준동구형")
    _ok(V.distractor_kind("달", "말") == "minimal_pair", "달/말 보이는 최소대립")
    _ok(V.distractor_kind("밥", "바") == "close", "밥/바 삽입·삭제 하나는 close")
    _ok(V.distractor_kind("밥", "하늘") == "distinct", "밥/하늘 뚜렷이 다름")


def test_viseme_distance_matches_assessment():
    import assessment as A
    pairs = [("밥", "맘"), ("달", "갈"), ("사과", "다과"), ("우유", "하늘"), ("자전거", "나무"), ("코", "고")]
    for a, b in pairs:
        _ok(abs(V.viseme_distance(a, b) - A.viseme_distance(a, b)) < 1e-9, f"assessment와 같은 거리: {a}/{b}")


def test_pick_distractors_never_uses_homophenes():
    words = [w["word"] for w in C.WORD_BANK]
    idx = V.VocabIndex(words)
    rng = random.Random(5)
    sample = random.Random(1).sample(idx.words, 60)
    for t in sample:
        cls = V.classify_pool(t, idx)
        for level in (1, 2, 3):
            ds = V.pick_distractors(t, idx, level, rng, classes=cls)
            kinds = [V.distractor_kind(t, d) for d in ds]
            _ok(len(ds) == 3 and len(set(ds)) == 3 and t not in ds, f"보기 3개, 중복·정답 없음: {t}")
            _ok("homophene" not in kinds and "near_homophene" not in kinds,
                f"동구형이음·준동구형은 어떤 단계에서도 빠진다: {t} L{level} {ds}")
            if level == 1:
                _ok(all(k == "distinct" for k in kinds), f"1단계는 뚜렷이 다른 단어만: {t} {ds}")
            if level == 3 and len(cls["minimal_pair"]) >= 3:
                _ok(all(k == "minimal_pair" for k in kinds), f"3단계는 보이는 최소대립 우선: {t} {ds}")
    a = V.pick_distractors("달", idx, 2, random.Random(9))
    b = V.pick_distractors("달", idx, 2, random.Random(9))
    _ok(a == b, "같은 시드면 같은 보기")


def test_option_level_and_target_quantile():
    _ok(V.option_level(False) == 2 and V.option_level(True) == 3, "숙달 전 2단계(최소대립 1개), 숙달 뒤 3단계")
    _ok(V.next_target_quantile(0) == 0.15, "처음에는 쉬운 쪽")
    _ok(V.next_target_quantile(30) > V.next_target_quantile(10) > V.next_target_quantile(0), "답할수록 어려운 쪽으로")
    _ok(V.next_target_quantile(1000) == 0.9, "상한 0.9")


def test_serve_weight_and_quantiles():
    _ok(V.serve_weight(0.5, 0.5) == 30 and V.serve_weight(0.95, 0.1) == 1, "목표에서 최대(1 + 29), 멀면 최소 1")
    _ok(V.serve_weight(0.3, 0.5) < V.serve_weight(0.45, 0.5), "목표에 가까울수록 크다")
    qr = V.quantile_ranks({"a": 0.1, "b": 0.2, "c": 0.2, "d": 0.9})
    _ok(qr["a"] == 0.0 and qr["d"] == 1.0 and qr["b"] == qr["c"] == 0.5, "동점은 평균 순위")


def test_stage2_plan():
    pool = [w["word"] for w in C.WORD_BANK][:150]
    table = V.Stage2Table(pool)
    plan = V.stage2_plan(table, n_answers=0, mastered=False, weak_visemes=[6], rng=random.Random(2))
    _ok(plan["option_level"] == 2 and plan["target_quantile"] == 0.15, "새 학습자: 보기 2단계, 쉬운 쪽")
    later = V.stage2_plan(table, n_answers=60, mastered=True, rng=random.Random(2))
    _ok(later["option_level"] == 3 and later["target_quantile"] > plan["target_quantile"], "숙달 뒤 3단계, 더 어려운 쪽")
    by = {e["word"]: e for e in plan["words"]}
    _ok(all(e["priority"] >= 1 for e in plan["words"]), "priority는 1 이상(프론트 호환)")
    no_weak = {e["word"]: e["priority"] for e in V.stage2_plan(table, 0, False, rng=random.Random(2))["words"]}
    w6 = [w for w in table.words if 6 in table.index.seq[w]]
    _ok(all(by[w]["priority"] > no_weak[w] for w in w6), "약점 비심(6)을 담은 단어는 priority가 커진다")
    for e in plan["words"] + later["words"]:
        _ok(not (set(e["distractors"]) & set(table.index.homophenes(e["word"]))), "보기에 동구형이음 없음")
    top = max(plan["words"], key=lambda e: e["priority"])
    _ok(abs(top["quantile"] - 0.15) < 0.1, "새 학습자는 쉬운 쪽(분위 0.15 근처)을 가장 자주")


def test_scenario_bands_and_rerank():
    _ok(sorted(V.SCENARIO_BANDS) == [1, 2, 3, 4, 5], "1~5단계 구간")
    prompt = {1: (5, 8), 2: (7, 10), 3: (10, 13), 4: (12, 15), 5: (15, 20)}
    for lvl, (lo, hi) in prompt.items():
        e_lo, e_hi = V.SCENARIO_BANDS[lvl]["eojeol"]
        _ok(e_lo <= lo and hi <= e_hi, f"{lvl}단계 어절 구간이 지시 범위를 품는다")
    _ok(V.band_distance(6, 0.2, 1) == 0.0, "구간 안이면 거리 0")
    _ok(V.band_distance(2, 0.2, 1) == 1.0, "어절 2개 모자라면 거리 1")
    _ok(abs(V.band_distance(6, 0.42, 1) - 2.0) < 1e-6, "점수 0.1 넘으면 거리 2")

    short = ["물 좀 주세요."] * 2                      # 1단계 길이 미달
    fit = ["오늘은 따뜻한 커피 한 잔을 마시고 싶어요.", "여기 앉아서 천천히 이야기를 나눠 봐요.",
           "아이가 좋아하는 우유를 하나 더 주세요."]
    sents = [short[0], fit[0], fit[1], short[1], fit[2]]
    rows = {s: V.sentence_difficulty(s, V.default_vocab_index()) for s in sents}
    in_band = [s for s in sents if V.band_distance(rows[s]["n_eojeol"], rows[s]["score"], 1) == 0]
    kept, rep = V.rerank_by_band(sents, 1)
    _ok(rep["considered"] == 5 and rep["in_band"] == len(in_band), "요약 수치")
    if len(in_band) >= 3:
        _ok(kept == in_band, "구간 안 문장이 셋 이상이면 그것만 남긴다(원래 순서)")
    _ok(len(kept) >= 3, "적어도 세 문장은 남는다")
    kept2, rep2 = V.rerank_by_band(short + ["감사합니다.", "안녕하세요."], 5)
    _ok(rep2["in_band"] == 0 and len(kept2) == 3, "구간 안이 없으면 가장 가까운 셋으로 채운다(대체 문장으로 넘기지 않음)")
    kept3, _ = V.rerank_by_band(short, 3)
    _ok(kept3 == short, "입력이 셋보다 적으면 그대로(부족 판정은 호출부)")
    order = [sents.index(s) for s in kept]
    _ok(order == sorted(order), "고른 문장은 원래 순서를 지킨다")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
