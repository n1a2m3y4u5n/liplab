"""축 E 조음 가이드 엔진 테스트 — 결정론적(모델·DB 비의존)."""
import articulation as art


def test_target_basic():
    t = art.articulation_target(6)  # 치경 ㄷㄴㄹㅅ
    assert t["place"] == "치경"
    assert t["params"]["tip"] > 0.5           # 혀끝 들림
    assert "혀끝" in t["hidden_guide"]


def test_target_nasal_flag():
    assert art.articulation_target(7)["nasal"] is True   # 연구개 파열·비음(받침 ㅇ)
    assert art.articulation_target(3)["nasal"] is False  # 전설모음


def test_target_unknown_falls_neutral():
    t = art.articulation_target(999)
    assert t["viseme"] == 15 and t["place"] == "중립"


def test_correction_needs_more_jaw():
    # 목표는 개방모음(jaw≈0.92)인데 입을 거의 안 벌림 → "더 벌리세요"
    c = art.articulation_correction(2, {"jaw": 0.1, "round": 0.0, "close": 0.0})
    assert not c["ok"]
    assert "벌리" in c["primary"]
    assert c["cues"][0]["dim"] == "jaw" and c["cues"][0]["gap"] > 0


def test_correction_round_over():
    # 목표 원순 없음(전설모음)인데 입술을 오므림 → "오므림을 푸세요"
    c = art.articulation_correction(3, {"jaw": 0.16, "round": 0.8, "close": 0.0})
    assert any(cue["dim"] == "round" and cue["gap"] < 0 for cue in c["cues"])


def test_correction_ok_when_close():
    c = art.articulation_correction(2, {"jaw": 0.9, "round": 0.0, "close": 0.0})
    assert c["ok"] and "유지" in c["primary"]
    assert c["hidden_guide"]  # 관찰이 맞아도 내부 조음 안내는 항상 제공


def test_guide_decomposes_syllables():
    g = art.articulation_guide("바다")
    assert g["n_syllables"] == 2
    first = g["syllables"][0]
    assert first["syllable"] == "바"
    jamos = [j["jamo"] for j in first["jamo"]]
    assert "ㅂ" in jamos and "ㅏ" in jamos


def test_guide_skips_silent_initial_ieung():
    # '아' 초성 ㅇ은 무음이라 조음 항목에서 빠지고 중성 ㅏ만 남는다
    g = art.articulation_guide("아")
    jamos = [j["jamo"] for j in g["syllables"][0]["jamo"]]
    assert "ㅏ" in jamos
    assert not any(j["jamo"] == "ㅇ" and j["position"] == "초성" for j in g["syllables"][0]["jamo"])


def test_guide_ignores_non_hangul():
    g = art.articulation_guide("A1 가!")
    assert g["n_syllables"] == 1 and g["syllables"][0]["syllable"] == "가"


def _jamo(g, syl, jamo):
    for s in g["syllables"]:
        if s["syllable"] == syl:
            for j in s["jamo"]:
                if j["jamo"] == jamo:
                    return j
    return None


def test_guide_double_final_normalized():
    # 겹받침은 대표음으로 정규화되어 종성이 유실되지 않아야 한다(값→ㅂ, 닭→ㄱ, 삶→ㅁ)
    g = art.articulation_guide("값")
    jamos = [j["jamo"] for j in g["syllables"][0]["jamo"]]
    assert "ㅂ" in jamos, f"값의 종성 ㅄ→ㅂ 누락: {jamos}"
    # 삶(ㄻ→ㅁ)은 비음 종성이라 nasal + 코울림 안내가 살아야 한다
    sam = _jamo(art.articulation_guide("삶"), "삶", "ㅁ")
    assert sam is not None and sam["nasal"] is True


def test_correction_nonnumeric_observed_no_crash():
    c = art.articulation_correction(2, {"jaw": "bad", "round": None, "close": 0.0})
    assert "cues" in c  # 크래시 없이 처리


def test_guide_nasal_per_jamo_not_per_viseme():
    # 비심7 그룹의 ㄱ(초성)은 비음이 아니어야 한다(과거 버그: 그룹 단위라 True로 오부여)
    g = art.articulation_guide("가방")
    k = _jamo(g, "가", "ㄱ")
    assert k is not None and k["nasal"] is False
    assert "코로 울림" not in k["guide"]
    # 종성 ㅇ(강)·ㅁ(밤)·ㄴ(반)은 실제 비음이라 True + 코 울림 안내
    assert _jamo(art.articulation_guide("강"), "강", "ㅇ")["nasal"] is True
    m = _jamo(art.articulation_guide("밤"), "밤", "ㅁ")
    assert m["nasal"] is True and "코로 울림" in m["guide"]
