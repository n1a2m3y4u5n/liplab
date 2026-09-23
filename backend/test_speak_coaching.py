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
