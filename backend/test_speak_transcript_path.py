"""말하기 채점 API의 전사 경로(D-GOP 없음, 전시앱·로컬·D-GOP 실패 폴백) 통합 테스트. Whisper와 LLM은 가짜로 바꿔 모델·네트워크 없이 본다.

- 소리 없는 녹음(프론트 micIssue: 크기 0·이어 낸 소리 0초)은 전사하지 않고 불합격, LLM 코칭도 부르지 않는다.
- 모음·자음 단계는 초점 자모(모음 단계 중성, 자음 단계 첫소리·받침)가 전사와 같아야 합격이다.

test_calendar_review.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import llm_service
import speak_service
import main

calls = {"asr": 0, "llm": 0}
heard = {"text": ""}

async def fake_transcribe(data):
    calls["asr"] += 1
    return heard["text"]

class _Boom:
    class messages:
        @staticmethod
        async def create(*a, **k):
            calls["llm"] += 1
            raise RuntimeError("no network in tests")

speak_service.transcribe = fake_transcribe
speak_service.is_available = lambda: True
llm_service.anthropic_client = _Boom

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "asr@example.com", "username": "전사경로", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}

    def assess(target, stage, text, loud, vd):
        heard["text"] = text
        before = dict(calls)
        res = c.post("/api/speak/assess", headers=h, files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")},
                     data={"target": target, "stage": str(stage), "loudness": str(loud), "duration": "1.0",
                           "voiced_duration": str(vd)})
        body = res.json()
        return {"status": res.status_code, "score": body.get("score"), "passed": body.get("passed"),
                "note": body.get("note"), "transcript": body.get("transcript"), "coaching": body.get("coaching"),
                "method": body.get("assessment_method"),
                "asr": calls["asr"] - before["asr"], "llm": calls["llm"] - before["llm"]}

    out["silent"] = assess("아", 2, "시청해 주셔서 감사합니다.", 0, 0)
    out["wrong_vowel"] = assess("아", 2, "이", 50, 0.6)
    out["right_vowel"] = assess("아", 2, "아.", 50, 0.6)
    out["wrong_onset"] = assess("풀", 3, "불", 50, 0.6)
    out["word_silent"] = assess("사과", 4, "사과", 0, 0)
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_API_KEY="")
        for k in ("DGOP_ALIGNER_ID", "DGOP_SCORER_ID", "DGOP_MODEL_ID", "LIPLAB_AV_FUSION"):
            env.pop(k, None)
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_transcript_path_verdicts():
    import speak_curriculum as S
    r = _run()
    for k, v in r.items():
        assert v["status"] == 200 and v["method"] == "asr_transcript", (k, v)
    # 소리 없음: 전사·LLM을 부르지 않고 0점 불합격(예전에는 무음에서 나온 문장이 2단계 8/8 합격)
    for k in ("silent", "word_silent"):
        v = r[k]
        assert (v["asr"], v["llm"], v["score"], v["passed"], v["transcript"]) == (0, 0, 0.0, False, ""), (k, v)
        assert v["note"] == S.NO_VOICE_NOTE and v["coaching"] == S.NO_VOICE_NOTE
    # 초점 자모가 다르면 점수가 합격선을 넘어도 불합격(아→이 69점, 풀→불 91점)
    assert r["wrong_vowel"]["passed"] is False and r["wrong_vowel"]["score"] == 69.0 and "'ㅏ'" in r["wrong_vowel"]["note"]
    assert r["wrong_onset"]["passed"] is False and r["wrong_onset"]["score"] == 91.0 and "'ㅍ'" in r["wrong_onset"]["note"]
    assert r["wrong_vowel"]["note"] in r["wrong_vowel"]["coaching"]
    assert r["right_vowel"]["passed"] is True and r["right_vowel"]["note"] == "" and r["right_vowel"]["asr"] == 1


def test_collapse_whisper_repetition_loops():
    # Whisper가 잡음·발화 끝에 지어내는 반복 루프를 한 번으로 접는다(잡음 전사 5단계 합격 28% → 0%, 9/28)
    from speak_service import collapse_repeats as c
    assert c("이 영상은 영상에서 영상에서 영상에서 영상에서") == "이 영상은 영상에서"
    assert c("수 있습니다. 고기, 고기, 고기, 고기,") == "수 있습니다. 고기,"
    assert c("나무에는 3마리가 쪘고 2마리가 쪘고, 2마리가 쪘고, 2마리가 쪘고,") == "나무에는 3마리가 쪘고 2마리가 쪘고,"
    # 두 번 반복과 보통 문장은 그대로
    assert c("하하 하하 좋아") == "하하 하하 좋아"
    assert c("아니 아니 아니야") == "아니 아니 아니야"
    assert c("밥 먹었어요") == "밥 먹었어요" and c("") == ""
