"""K→B 융합(K-5) 통합 테스트 — 발음채점 API가 입모양 타임라인의 비음 확률로 ㅁ/ㅂ 같은 짝의 입모양 점수를
조금 조정하는가. D-GOP 모델 대신 정렬 결과를 흉내 낸 함수를 넣어, 모델 없이 경로 전체(파싱·발음 기대·근거·융합)를 본다.

test_assessment_report.py와 같은 방식: 임시 DB를 지정한 별도 프로세스에서 시나리오를 돌리고 결과(JSON)만 검사한다.
"""
import json
import os
import subprocess
import sys
import tempfile

_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import dgop_acoustic
import main

# "밥 마셔": 밥(파열 ㅂ) 0.0~0.4초, 마(비음 ㅁ) 0.5~0.8초, 셔 0.8~1.1초
def fake_assess(data, target, aligner_id=None, scorer_id=None, **kw):
    phones = [{"token": "밥", "t0": 0.0, "t1": 0.4, "dgop": 0.5, "aligned": True, "scorable": True},
              {"token": "|", "t0": 0.4, "t1": 0.5, "dgop": 0.0, "aligned": True, "scorable": False},
              {"token": "마", "t0": 0.5, "t1": 0.8, "dgop": 0.5, "aligned": True, "scorable": True},
              {"token": "셔", "t0": 0.8, "t1": 1.1, "dgop": 0.5, "aligned": True, "scorable": True}]
    return {"score": 50.0, "raw_score": 5.0, "uncertainty": 0.4, "phones": phones}

dgop_acoustic.HAS_ACOUSTIC = True
dgop_acoustic.assess_text = fake_assess

frames = [[round(i / 20, 3)] + [0.6] * 10 for i in range(24)]
def nasal(level_bab, level_ma):
    # 밥 구간은 level_bab, 마 구간은 level_ma, 나머지는 0.2
    out = []
    for i in range(34):
        t = round(i / 30, 3)
        p = level_bab if t <= 0.4 else level_ma if 0.5 <= t <= 0.8 else 0.2
        out.append([t, p])
    return out

out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "k5@example.com", "username": "비음시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}

    def assess(track):
        data = {"target": "밥 마셔", "mouth_confidence": "0.6"}
        if track is not None:
            data["mouth_track"] = json.dumps(track)
        res = c.post("/api/speak/assess", data=data, files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")},
                     headers=h)
        return res.status_code, res.json()

    base = {"visemes": list(range(1, 11)), "frames": frames}
    out["plain"] = assess(base)
    out["agree"] = assess({**base, "nasal": nasal(0.1, 0.5)})      # 밥은 낮고 마는 높음 → 맞음
    out["disagree"] = assess({**base, "nasal": nasal(0.5, 0.1)})   # 거꾸로 → 어긋남
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _run():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   DGOP_ALIGNER_ID="fake/aligner", ANTHROPIC_API_KEY="")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env,
                           capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    return json.loads(line[len("RESULT "):])


def test_nasal_track_nudges_fused_score():
    r = _run()
    for k in ("plain", "agree", "disagree"):
        assert r[k][0] == 200, f"{k}: {r[k]}"
    plain, agree, disagree = (r[k][1]["av_fusion"] for k in ("plain", "agree", "disagree"))
    assert plain["nasal_phones"] == 0
    assert agree["nasal_phones"] == 2 and disagree["nasal_phones"] == 2   # 밥·마만(셔는 해당 없음)
    assert agree["score"] > plain["score"] > disagree["score"]
    # 보조 신호라 조정폭이 작다 — 음소 두 개에 최대 ±8점 × 영상 가중(≤0.9), 세 음소 평균
    assert agree["score"] - plain["score"] <= 2 * 8 * 0.9 / 3 + 0.1
