"""대화 되묻기 '다른 말로'(docs/curriculum-roadmap.md 1-4)."""
import asyncio

import llm_service as L


class _Resp:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text, "type": "text"})()]


def _run(monkeypatch, reply, text="따뜻한 아메리카노 한 잔 드릴까요?", level=3):
    async def fake(**kw):
        if isinstance(reply, Exception):
            raise reply
        return _Resp(reply)
    monkeypatch.setattr(L.anthropic_client.messages, "create", fake)
    return asyncio.run(L.rephrase_turn(text, "카페", level))


def test_rephrase_returns_new_korean_sentence(monkeypatch):
    assert _run(monkeypatch, '{"text": "뜨거운 커피 하나 드릴까요?"}') == "뜨거운 커피 하나 드릴까요?"


def test_rephrase_rejects_same_english_long_or_failed(monkeypatch):
    assert _run(monkeypatch, '{"text": "따뜻한 아메리카노 한 잔 드릴까요?"}') is None      # 원문 그대로
    assert _run(monkeypatch, '{"text": "Americano 드릴까요?"}') is None                  # 영문
    assert _run(monkeypatch, '{"text": "' + "가" * 40 + '"}', level=1) is None           # 난이도 길이 초과
    assert _run(monkeypatch, RuntimeError("budget")) is None                             # 한도·오류
    assert _run(monkeypatch, '{"text": "x"}', text="") is None                          # 빈 원문


def test_rephrase_endpoint_without_key_returns_null():
    import os, subprocess, sys, tempfile, json
    here = os.path.dirname(os.path.abspath(__file__))
    code = r'''
import json
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "rp@example.com", "username": "rpu", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    x = c.post("/api/conversation/rephrase", json={"text": "안녕하세요", "situation": "카페", "level": 9}, headers=h)
    print("RESULT " + json.dumps([x.status_code, x.json()]))
'''
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", code], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, p.stderr[-2000:]
    assert json.loads(line[7:]) == [200, {"text": None}]
