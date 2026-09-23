"""다자 대화 시나리오(축 H) 테스트 — 폴백 결정성·클램프·부실응답 방어."""
import asyncio

import conversation_scenario as cs


def test_fallback_structure_and_speaker_rotation():
    conv = cs._fallback_conversation(2, 6, "카페")
    assert conv["scene"] == "카페"
    assert conv["speakers"] == 2
    assert conv["fallback"] is True
    assert len(conv["turns"]) == 6
    # 화자는 0..speakers-1 안에서 모두 나오되, 순서만 보고 맞히지 못하게 규칙적으로 번갈지 않는다(H-2)
    seq = [t["speaker"] for t in conv["turns"]]
    assert set(seq) == {0, 1} and seq != [0, 1, 0, 1, 0, 1]
    assert all(t["text"] for t in conv["turns"])


def test_fallback_three_speakers_rotation():
    conv = cs._fallback_conversation(3, 6, "학교 교실")
    seq = [t["speaker"] for t in conv["turns"]]
    assert set(seq) == {0, 1, 2} and seq != [0, 1, 2, 0, 1, 2]


def test_fallback_unknown_scene_uses_default_lines():
    conv = cs._fallback_conversation(2, 4, "존재하지 않는 장면")
    assert len(conv["turns"]) == 4
    assert all(t["text"] for t in conv["turns"])


def test_generate_clamps_speakers_and_turns_via_fallback():
    # 로컬엔 anthropic 키가 없어 LLM 경로가 실패 → 폴백. 폴백도 클램프를 지켜야 한다.
    conv = asyncio.run(cs.generate_multi_conversation(speakers=9, turns=99, scene="카페"))
    assert 2 <= conv["speakers"] <= 4
    assert 3 <= len(conv["turns"]) <= 10
    assert all(0 <= t["speaker"] < conv["speakers"] for t in conv["turns"])


def test_generate_min_clamp():
    conv = asyncio.run(cs.generate_multi_conversation(speakers=1, turns=1, scene="카페"))
    assert conv["speakers"] == 2       # 최소 2명
    assert len(conv["turns"]) >= 3     # 최소 3턴


def test_fallback_four_speakers_rotation():
    conv = cs._fallback_conversation(4, 8, "카페")
    seq = [t["speaker"] for t in conv["turns"]]
    assert set(seq) == {0, 1, 2, 3} and seq != [i % 4 for i in range(8)]


def test_custom_scene_keeps_label_and_uses_generic_lines():
    # 상황별 시나리오에서 적은 상황 — 목록에 없어도 장면 이름은 그대로, 대사는 어느 자리에나 맞는 인사로(카페 대사 X)
    conv = asyncio.run(cs.generate_multi_conversation(speakers=4, turns=6, scene="  은행 창구에서\n통장 만들기 "))
    assert conv["scene"] == "은행 창구에서 통장 만들기"
    assert conv["speakers"] == 4
    if conv.get("fallback"):
        assert {t["text"] for t in conv["turns"]} <= set(cs._GENERIC_LINES)


def test_clean_scene():
    assert cs.clean_scene(None) is None and cs.clean_scene("   ") is None
    assert cs.clean_scene('카페 "주문" {x}') == "카페 주문 x"
    assert len(cs.clean_scene("가" * 100)) == 30

