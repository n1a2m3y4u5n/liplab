"""다자 대화 시나리오(축 H) 테스트 — 폴백 결정성·클램프·부실응답 방어."""
import asyncio

import conversation_scenario as cs


def test_fallback_structure_and_speaker_rotation():
    conv = cs._fallback_conversation(2, 6, "카페")
    assert conv["scene"] == "카페"
    assert conv["speakers"] == 2
    assert conv["fallback"] is True
    assert len(conv["turns"]) == 6
    # 화자는 0..speakers-1 안에서 번갈아
    assert [t["speaker"] for t in conv["turns"]] == [0, 1, 0, 1, 0, 1]
    assert all(t["text"] for t in conv["turns"])


def test_fallback_three_speakers_rotation():
    conv = cs._fallback_conversation(3, 6, "학교 교실")
    assert [t["speaker"] for t in conv["turns"]] == [0, 1, 2, 0, 1, 2]


def test_fallback_unknown_scene_uses_default_lines():
    conv = cs._fallback_conversation(2, 4, "존재하지 않는 장면")
    assert len(conv["turns"]) == 4
    assert all(t["text"] for t in conv["turns"])


def test_generate_clamps_speakers_and_turns_via_fallback():
    # 로컬엔 anthropic 키가 없어 LLM 경로가 실패 → 폴백. 폴백도 클램프를 지켜야 한다.
    conv = asyncio.run(cs.generate_multi_conversation(speakers=9, turns=99, scene="카페"))
    assert 2 <= conv["speakers"] <= 3
    assert 3 <= len(conv["turns"]) <= 10
    assert all(0 <= t["speaker"] < conv["speakers"] for t in conv["turns"])


def test_generate_min_clamp():
    conv = asyncio.run(cs.generate_multi_conversation(speakers=1, turns=1, scene="카페"))
    assert conv["speakers"] == 2       # 최소 2명
    assert len(conv["turns"]) >= 3     # 최소 3턴
