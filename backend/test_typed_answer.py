"""2단계 주관식(단어 입력) 채점(커리큘럼 개선 계획 1-2, visual_difficulty.typed_word_verdict).

정리 규칙(선택): NFC로 맞추고 한글 음절만 남긴다. 그래서 띄어쓰기('바 다')와 문장부호('바다.')는 보지 않는다.
받침 오타는 따로 봐주지 않고 입모양 규칙을 그대로 따른다. 입모양이 같으면(값/갑) '입모양은 맞음' 0.5, 입모양이 바뀌면(밥/반) 오답.
"""
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("JWT_SECRET", "test-only-typed-secret")
import visual_difficulty as vd   # noqa: E402


def v(target, typed):
    return vd.typed_word_verdict(target, typed)


def test_exact():
    r = v("바다", "바다")
    assert r["verdict"] == "correct" and r["credit"] == 1.0


def test_homophene_is_partial():
    # ㅂ·ㅍ·ㅁ은 같은 입모양(양순음)이라 '파다'는 '바다'와 입모양이 똑같다
    assert vd.viseme_sequence("파다") == vd.viseme_sequence("바다")
    r = v("바다", "파다")
    assert r["verdict"] == "homophene" and r["credit"] == 0.5


def test_different_viseme_is_wrong():
    r = v("바다", "모자")
    assert r["verdict"] == "wrong" and r["credit"] == 0.0


def test_empty():
    for typed in ("", "   ", "?!", "abc"):
        r = v("바다", typed)
        assert r["verdict"] == "empty" and r["credit"] == 0.0


def test_spacing_and_punctuation_ignored():
    assert v("바다", " 바 다 ")["verdict"] == "correct"
    assert v("바다", "바다.")["verdict"] == "correct"
    assert v("바다", "바다")["verdict"] == "correct"   # 풀어 쓴 자모(NFD)도 같은 글로 본다


def test_coda_typo_follows_mouth_shape():
    # 받침 ㅄ/ㅂ은 소리와 입모양이 같다: 입모양은 맞음(정답 인정은 아님)
    assert v("값", "갑")["verdict"] == "homophene"
    # 받침 ㅂ → ㄴ은 입을 다물지 않아 입모양이 달라진다: 오답
    assert v("밥", "반")["verdict"] == "wrong"


_FLOW = r'''
import json
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "ty@example.com", "username": "tyu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    out = []
    for typed in ("바 다", "파다", "모자"):
        rr = c.post("/api/curriculum/word-answer", json={"word": "바다", "correct": True, "chosen": typed, "mode": "typed"},
                    headers=h).json()
        out.append([rr["verdict"], rr["correct"], rr["mastery_score"]])
    ev = c.get("/api/eval/summary", headers=h)
    types = [x["item_type"] for x in ev.json().get("by_item_type", [])] if ev.status_code == 200 else None
print("RESULT " + json.dumps({"out": out, "types": types}))
'''


def test_typed_answer_endpoint():
    import main
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   LIPLAB_UNLOCK_ALL="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=240)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert [x[0] for x in r["out"]] == ["correct", "homophene", "wrong"]
    assert [x[1] for x in r["out"]] == [True, False, False]
    # 숙달 추정은 정답 1, 입모양은 맞음 0.5, 오답 0을 차례로 넣은 값(선다형 정답과 같은 무게)
    est = 0.0
    for i, credit in enumerate([1.0, 0.5, 0.0]):
        est = main._ewma_mastery(est, i, credit)
        assert abs(r["out"][i][2] - round(est, 1)) < 1e-9
    assert r["types"] and "word_typed" in r["types"]   # 학습 효과 리포트에 '단어 주관식'이 따로 나온다
