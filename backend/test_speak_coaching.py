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


def test_conversation_turn_retries_when_too_long(monkeypatch):
    # 1단계 대화 턴은 9자 이하(지시 5~7자에 30% 여유). 넘으면 한 번 다시 받고, 그래도 넘으면 짧은 쪽을 쓴다
    replies = iter(['{"text": "안녕하세요. 어디가 아프세요?"}', '{"text": "어디 아프세요?"}'])
    seen = []

    class _Msg:
        def __init__(self, t):
            self.content = [type("B", (), {"text": t, "type": "text"})()]

    class _Fake:
        class messages:
            @staticmethod
            async def create(*a, **k):
                seen.append(k["messages"])
                return _Msg(next(replies))
    monkeypatch.setattr(llm_service, "anthropic_client", _Fake)
    r = asyncio.run(llm_service.generate_conversation_turn("병원", 1, []))
    assert r["text"] == "어디 아프세요?" and len(seen) == 2
    assert "자라 이 난이도에 너무 깁니다" in seen[1][-1]["content"]
    assert llm_service.conv_turn_ok("어서오세요!", 1) and not llm_service.conv_turn_ok("Hello 안녕", 3)
    assert llm_service.conv_turn_ok("아주 긴 문장이라도 5단계는 상한이 없습니다", 5)


def test_silent_linking_h_is_not_coached():
    # 많이·않아·괜찮으세요의 ㅎ은 표준 발음에서 내지 않는데 채점 라벨에 남아(자체 모델 학습 라벨과 맞추려 그대로 둠),
    # 약한 소리로 코칭됐다(538 음성 40개 중 9개). 코칭·칩·기록에서 뺀다
    import jamo_vocab as J
    assert J.silent_linking_h("많이") == [3] and J.silent_linking_h("괜찮으세요?") == [6]
    assert J.silent_linking_h("좋아") == [] and J.silent_linking_h("학교") == []
    phones = [{"token": "o:ㅁ", "aligned": True, "scorable": True, "dgop": 0.9},
              {"token": "n:ㅏ", "aligned": True, "scorable": True, "dgop": 0.9},
              {"token": "c:ㄴ", "aligned": True, "scorable": True, "dgop": 0.8},
              {"token": "o:ㅎ", "aligned": True, "scorable": True, "dgop": 0.0, "silent_h": True},
              {"token": "n:ㅣ", "aligned": True, "scorable": True, "dgop": 0.1}]
    assert [w["label"] for w in main._weak_phones({"phones": phones})] == ["ㅣ"]


def test_engine_h_delete_param_keeps_label_path_default():
    import engine
    assert engine.to_pronounced_syllables("많이", phonetic=True)[1][0] == "ㅎ"          # 채점 라벨은 그대로
    assert engine.to_pronounced_syllables("많이", phonetic=True, h_delete=True)[1][0] == "ㄴ"
    assert engine.to_pronounced_syllables("많이")[1][0] == "ㄴ"                        # 입모양 경로는 탈락


def test_conversation_marks_transcription_and_avoids_repeats(monkeypatch):
    # 학습자 입력은 대답이 아니라 직전 문장을 읽고 적은 글. 예전에는 그대로 사용자 턴으로 넘겨 모델이 같은 문장을 되풀이하거나
    # 역할을 바꿨다(카페 직원이 첫 문장 반복 뒤 손님이 됨). 앞에서 한 문장이 나오면 한 번 다시 받는다
    replies = iter(['{"text": "어서오세요, 뭘 드릴까요?"}', '{"text": "따뜻한 걸로 드릴까요?"}'])
    seen = []

    class _Msg:
        def __init__(self, t):
            self.content = [type("B", (), {"text": t, "type": "text"})()]

    class _Fake:
        class messages:
            @staticmethod
            async def create(*a, **k):
                seen.append(k["messages"])
                return _Msg(next(replies))
    monkeypatch.setattr(llm_service, "anthropic_client", _Fake)
    hist = [{"role": "assistant", "content": "어서오세요, 뭘 드릴까요?"}, {"role": "user", "content": "어서오세요 뭘 드릴까요"}]
    r = asyncio.run(llm_service.generate_conversation_turn("카페", 3, hist))
    assert r["text"] == "따뜻한 걸로 드릴까요?" and len(seen) == 2
    user_turns = [m["content"] for m in seen[0] if m["role"] == "user"]
    assert any("읽었습니다" in u and "대답이 아닙니다" in u for u in user_turns)
    assert "이미 한 말" in seen[1][-1]["content"]


def test_sentence_intonation_uses_final_syllable_and_skips_wh_questions():
    # 5단계 문장 억양(docs/sentence-intonation.md): 기준·끝 음높이가 오면 그것으로, 없으면 예전 앞·뒤 30% 평균으로 판정
    import speak_curriculum as sc
    stg = sc.get_stage(5)
    for it in stg["items"]:
        assert sc.expected_intonation(it["target"]) == it["intonation"], it   # 의문사 의문문은 '올림' 문항에 없다
    rise = {"pitch_start": 210, "pitch_end": 212, "pitch_ref": 200, "pitch_final": 230}
    _, _, note = sc.score_attempt(5, "밥 먹었어요?", "밥 먹었어요", rise, sim_score=90)
    assert note == "억양 방향도 맞았어요!"
    old = {"pitch_start": 210, "pitch_end": 212}
    _, _, note = sc.score_attempt(5, "밥 먹었어요?", "밥 먹었어요", old, sim_score=90)
    assert "평평" in note
    assert sc.expected_intonation("이름이 뭐예요?") is None and sc.expected_intonation("괜찮으세요?") == "rise"
    assert sc.expected_intonation("정말 맛있어요!") == "fall"


def test_ai_sentences_get_intonation_verdict():
    # AI 생성 문장(고정 16문항에 없음)도 문장 부호로 기대 억양을 정해 판정한다. 예전에는 올림·내림 모두 note가 ''였다
    import speak_curriculum as sc
    up = {"pitch_ref": 200, "pitch_final": 240}
    down = {"pitch_ref": 200, "pitch_final": 170}
    fixed = {it["target"] for it in sc.get_stage(5)["items"]}
    for t in ("내일 시간 있어요?", "점심 같이 먹을래요?"):
        assert t not in fixed
        assert sc.score_attempt(5, t, t, up, sim_score=80)[2] == "억양 방향도 맞았어요!"
        assert sc.score_attempt(5, t, t, down, sim_score=80)[2] == "억양 방향이 반대예요. 끝을 올려보세요."
    assert sc.score_attempt(5, "오늘 좀 피곤해요.", "오늘 좀 피곤해요", down, sim_score=80)[2] == "억양 방향도 맞았어요!"
    assert sc.score_attempt(5, "오늘 좀 피곤해요.", "오늘 좀 피곤해요", up, sim_score=80)[2] == "억양 방향이 반대예요. 끝을 내려보세요."
    # 의문사 의문문은 끝이 대개 내려가 판정하지 않는다(코칭 쪽 억양 안내로 넘어간다)
    assert sc.score_attempt(5, "어디 가요?", "어디 가요", up, sim_score=80)[2] == ""
