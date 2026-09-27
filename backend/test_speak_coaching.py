"""말하기 코칭에 D-GOP 약한 소리를 넣는다(축 B-9) — 선별 규칙과 규칙 폴백 문구."""
import asyncio
import os

import main
import llm_service


def test_weak_phones_picks_lowest_below_mean():
    res = {"phones": [
        {"token": "안", "aligned": True, "scorable": True, "dgop": 0.60},
        {"token": "녕", "aligned": True, "scorable": True, "dgop": 0.05},
        {"token": "|", "aligned": True, "scorable": False, "dgop": 0.01},   # 어절 경계는 뺀다
        {"token": "하", "aligned": True, "scorable": True, "dgop": 0.55},
        {"token": "세", "aligned": False, "scorable": True, "dgop": 0.0},   # 정렬 안 된 음소도 뺀다
    ]}
    weak = main._weak_phones(res)
    assert [w["label"] for w in weak] == ["녕"]
    assert main._weak_phones(None) == [] and main._weak_phones({"phones": []}) == []


def test_weak_phones_strips_jamo_prefix():
    res = {"phones": [{"token": "o:ㄱ", "aligned": True, "scorable": True, "dgop": 0.02},
                      {"token": "n:ㅏ", "aligned": True, "scorable": True, "dgop": 0.7}]}
    assert main._weak_phones(res)[0]["label"] == "ㄱ"


def test_coaching_fallback_mentions_weak_phone(monkeypatch):
    class _Boom:
        class messages:
            @staticmethod
            async def create(*a, **k):
                raise RuntimeError("no key")
    monkeypatch.setattr(llm_service, "anthropic_client", _Boom)
    text = asyncio.run(llm_service.generate_speaking_coaching(
        "안녕", "안녕", 80, [], {"loudness": 70, "pitch_range": 40}, weak_phones=[{"label": "녕", "dgop": 0.05}]))
    assert "'녕'" in text


def test_flat_tone_only_for_sentences(monkeypatch):
    # 한 음절·단어는 음높이가 고른 게 자연스럽다: 억양 폭이 작아도 '톤이 평평'이라 하지 않는다(문장에서만)
    class _Boom:
        class messages:
            @staticmethod
            async def create(*a, **k):
                raise RuntimeError("no key")
    monkeypatch.setattr(llm_service, "anthropic_client", _Boom)
    m = {"loudness": 70, "pitch_range": 5}
    word = asyncio.run(llm_service.generate_speaking_coaching("사과", "사과", 90, [], m))
    sent = asyncio.run(llm_service.generate_speaking_coaching("밥 먹었어요?", "밥 먹었어요", 90, [], m, intonation=True))
    assert "평평" not in word and "평평" in sent


def test_coaching_prompt_leaves_out_pitch_unless_asked(monkeypatch):
    seen = []

    class _Rec:
        class messages:
            @staticmethod
            async def create(*a, **k):
                seen.append(k["messages"][0]["content"])
                raise RuntimeError("stop")
    monkeypatch.setattr(llm_service, "anthropic_client", _Rec)
    asyncio.run(llm_service.generate_speaking_coaching("아", "아", 90, [], {"loudness": 70, "pitch_range": 5}))
    assert "억양 변화 5Hz" not in seen[0] and "25Hz" not in seen[0]


def test_fallback_explains_how_to_make_the_confused_sound(monkeypatch):
    # 'ㅅ이 ㄷ로 들렸어요. 입모양을 더 또렷하게'는 입 안의 차이(마찰/파열)에 맞지 않았다 → 자모별 조음 문장
    class _Rec:
        prompts = []

        class messages:
            @staticmethod
            async def create(*a, **k):
                _Rec.prompts.append(k["messages"][0]["content"])
                raise RuntimeError("no key")
    monkeypatch.setattr(llm_service, "anthropic_client", _Rec)
    text = asyncio.run(llm_service.generate_speaking_coaching(
        "사과", "다과", 60, [{"correct": "ㅅ", "confused_as": "ㄷ"}], {"loudness": 70}))
    assert "닿지 않게" in text and "입모양을 더 또렷하게" not in text
    assert "조음 참고" in _Rec.prompts[0] and "닿지 않게" in _Rec.prompts[0]
