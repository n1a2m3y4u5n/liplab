"""상황별 문장 생성이 실패했을 때의 대체 경로(llm_service._fallback_scenario, 9/27).

예전에는 단계와 상관없이 2~4어절 문장만 나가 5단계 학습자도 "안녕하세요."를 받았다. 이제 같은 상황·단계의 저장 문장을
지금 게이트로 다시 걸러 쓰고, 없으면 단계 길이에 맞춘 대체 문장을 쓴다.
"""
import json
import os
import subprocess
import sys
import tempfile

from content_rules import check_sentence
from llm_service import FALLBACK_BY_LEVEL, SCENARIO_MAX_CHARS

_RANGE = {1: (5, 8), 2: (7, 10), 3: (10, 13), 4: (12, 15), 5: (15, 40)}   # level_instructions의 어절 수


def test_level_bank_matches_level_length_and_passes_gate():
    for level, sents in FALLBACK_BY_LEVEL.items():
        lo, hi = _RANGE[level]
        assert len(sents) >= 5
        for s in sents:
            assert lo <= len(s.split()) <= hi, (level, s, len(s.split()))
            assert check_sentence(s, max_chars=SCENARIO_MAX_CHARS[level])[0], (level, s)


_FLOW = r'''
import asyncio, json
import database, llm_service
from database import ScenarioCache

async def main():
    await database.init_db()
    good = ["다음 주 월요일에 회의가 있으니까 자료를 미리 준비해 두면 좋겠어요.",
            "은행에 가서 통장을 새로 만들려면 신분증을 꼭 가지고 가야 해요.",
            "버스를 타고 가다가 내릴 정류장을 놓쳐서 한 정거장 더 갔어요."]
    async with database.AsyncSessionLocal() as db:
        db.add(ScenarioCache(situation="카페", difficulty_level=3, target_visemes=[],
                             sentences=good + ["Wi-Fi 비밀번호가 뭐예요?"], use_count=1))
        await db.commit()
        out = {}
        out["cache"] = await llm_service._fallback_scenario("카페", 3, db)
        out["static4"] = await llm_service._fallback_scenario("카페", 4, db)
        out["static1"] = await llm_service._fallback_scenario("카페", 1, db)
        out["good"] = good
    print("RESULT " + json.dumps(out, ensure_ascii=False))

asyncio.run(main())
'''


def test_fallback_prefers_regated_cache_then_level_bank():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        p = subprocess.run([sys.executable, "-c", _FLOW], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    assert r["cache"]["fallback"] == "cache"
    assert sorted(r["cache"]["sentences"]) == sorted(r["good"]), "영문이 든 저장 문장은 지금 게이트로 걸러야 한다"
    assert r["static4"]["fallback"] == "static" and set(r["static4"]["sentences"]) <= set(FALLBACK_BY_LEVEL[4])
    assert len(r["static4"]["sentences"]) == 5
    assert "아메리카노 한 잔 주세요." in r["static1"]["sentences"]     # 1단계는 상황별 기본 문장
