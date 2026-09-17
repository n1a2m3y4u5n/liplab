"""
이번 고도화에서 추가된 기능들의 회귀 테스트 — 축 B(AV융합)·G(개인화 필터)·I(향상도검사)·
J(시각증강 페이딩)·A4(audio2face 폴백). 순수 함수/결정론 위주(모델·네트워크 불요).
"""
import cue_overlay
import content_rules as cr
import assessment as asmt
import curriculum as cur
import dgop


# ── 축 J: 숙달도 기반 점진 페이딩(strength) ────────────────────────────────
def test_cue_strength_gradual_fade():
    # mastery 없으면 strength=1.0
    cues0 = cue_overlay.generate_cues("통화")
    assert cues0 and all(c["strength"] == 1.0 for c in cues0)
    # mastery가 올라가면 strength가 1.0 미만으로 점진 감소(이진 소거 아님)
    vids = {c["viseme"] for c in cues0}
    vid = next(iter(vids))
    mid = cue_overlay.generate_cues("통화", mastery={vid: 0.5})
    faded = [c for c in mid if c["viseme"] == vid]
    assert faded and all(0.2 <= c["strength"] < 1.0 for c in faded)
    # fade_threshold 이상이면 완전 소거
    gone = cue_overlay.generate_cues("통화", mastery={vid: 0.9}, fade_threshold=0.85)
    assert all(c["viseme"] != vid for c in gone)


# ── 축 G: 개인화 strict 필터(무적중 제거, 부족하면 폴백) ──────────────────
def test_select_personalized_strict_filters():
    words = [{"word": "바", "tier": 1}, {"word": "마", "tier": 1},
             {"word": "가", "tier": 1}, {"word": "다", "tier": 1}]
    # 표적 viseme=1(양순: 바·마). strict면 무적중(가·다) 제거
    strict = cr.select_personalized(words, [], [], [1], n_words=2, strict=True)
    got = {w["word"] for w in strict["words"]}
    assert got <= {"바", "마"} and len(got) == 2
    # 표적 적중이 요청수보다 적으면 정렬 폴백(항상 반환)
    fallback = cr.select_personalized(words, [], [], [1], n_words=4, strict=True)
    assert len(fallback["words"]) == 4  # 부족 → 무적중 포함 폴백


def test_select_personalized_sort_only_default():
    words = [{"word": "바", "tier": 1}, {"word": "가", "tier": 1}]
    r = cr.select_personalized(words, [], [], [1], n_words=2, strict=False)
    assert len(r["words"]) == 2  # 정렬만 — 둘 다 반환


# ── 축 I: 동형 사전/사후 폼 + 음소별 오류 프로파일 ────────────────────────
def test_progression_forms_homogeneous():
    words = [w["word"] for w in cur.WORD_BANK]
    forms = asmt.build_progression_forms(words, n=6)
    assert len(forms["A"]) > 0 and len(forms["B"]) > 0
    da = [i["difficulty"] for i in forms["A"]]
    db = [i["difficulty"] for i in forms["B"]]
    # 난이도 분포가 매칭돼야 동형(평균차 작음)
    assert abs(sum(da) / len(da) - sum(db) / len(db)) < 0.12


def test_score_placement_has_phoneme_errors():
    words = [w["word"] for w in cur.WORD_BANK]
    items = asmt.build_placement_items(words, n=6)
    # 일부러 다 오답(첫 보기 선택)으로 오류 프로파일 생성
    resp = {it["id"]: it["options"][0] if it["options"][0] != it["word"] else it["options"][-1]
            for it in items}
    r = asmt.score_placement(items, resp)
    assert "error_phonemes" in r and isinstance(r["error_phonemes"], list)
    for e in r["error_phonemes"]:
        assert "phoneme" in e and "count" in e and e["count"] >= 1


# ── 축 B: AV 후기융합 — 음향 불확실성↑ → 영상 가중↑ ──────────────────────
def test_av_fusion_weights_visual_by_uncertainty():
    low_unc = dgop.fuse_audio_visual(50.0, 0.1, 80.0)
    high_unc = dgop.fuse_audio_visual(50.0, 0.9, 80.0)
    # 불확실성이 높을수록 visual_weight가 커진다
    assert high_unc["visual_weight"] > low_unc["visual_weight"]
    # visual_score 없으면 audio 그대로
    none_v = dgop.fuse_audio_visual(50.0, 0.5, None)
    assert none_v["score"] == 50.0 and none_v["visual_weight"] == 0.0


# ── 축 A4: audio2face 폴백(torch 없어도 모듈 로드·graceful) ───────────────
def test_audio2face_graceful_without_torch():
    import audio2face
    # is_available()는 예외 없이 bool 반환(로컬 무torch면 False)
    assert isinstance(audio2face.is_available(), bool)
    # env 오버라이드 경로 탐색이 예외 없이 동작
    import os
    os.environ.pop("LIPLAB_A4_CKPT", None)
    assert audio2face._find_ckpt() is None or isinstance(audio2face._find_ckpt(), str)
