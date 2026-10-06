"""S7 말 빠르기 단서(speak_cues, docs/speak-visual-cues.md). 합성 파형과 정렬 흉내로 모델 없이 본다."""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

import speak_cues as S

SR = 16000


def _vowel(d):
    t = np.arange(int(d * SR)) / SR
    return sum(np.sin(2 * np.pi * 150 * k * t) / k for k in range(1, 12)) * 0.3


def _sil(d, seed=0):
    return np.random.default_rng(seed).normal(0, 1e-4, int(d * SR))


def _phones(onsets):
    """모음 토큰(n:ㅏ)을 주어진 시각에 하나씩 놓은 정렬 흉내. 토큰은 20ms짜리 점이다."""
    return [{"token": "n:ㅏ", "aligned": True, "t0": t, "t1": round(t + 0.02, 3)} for t in onsets]


def test_rate_counts_vowel_tokens_over_aligned_span():
    y = _vowel(2.0)
    r = S.rate_pause(y, _phones([0.0, 0.5, 1.0, 1.48]))   # 구간 0.0~1.5초, 음절 4개
    assert r["n_syll"] == 4 and abs(r["span"] - 1.5) < 1e-9
    assert abs(r["rate"] - 4 / 1.5) < 1e-3
    assert r["pause"] == 0.0 and r["pause_ratio"] == 0.0


def test_pause_of_400ms_is_found_and_short_gap_is_not():
    y = np.concatenate([_vowel(0.6), _sil(0.4), _vowel(0.6)])
    r = S.rate_pause(y, _phones([0.0, 0.3, 1.1, 1.58]))
    assert 0.35 <= r["pause"] <= 0.45
    assert r["artic"] > r["rate"]
    y2 = np.concatenate([_vowel(0.6), _sil(0.12), _vowel(0.6)])   # 파열음 폐쇄 정도의 짧은 무음은 쉼이 아니다
    assert S.rate_pause(y2, _phones([0.0, 0.3, 0.8, 1.3]))["pause"] == 0.0


def test_too_short_or_too_few_syllables_gives_none():
    y = _vowel(1.0)
    assert S.rate_pause(y, _phones([0.0, 0.5])) is None            # 음절 2개
    assert S.rate_pause(y, _phones([0.0, 0.1, 0.2])) is None       # 구간 0.22초
    assert S.rate_pause(y, []) is None
    # 어절 경계와 정렬 안 된 토큰은 구간·음절 수에 넣지 않는다
    ph = _phones([0.0, 0.5, 1.0]) + [{"token": "|", "aligned": True, "t0": 1.5, "t1": 1.6},
                                     {"token": "n:ㅏ", "aligned": False}]
    assert S.rate_pause(_vowel(2.0), ph)["n_syll"] == 3


def test_rate_cue_flags_only_slow_side_and_is_reference():
    slow = S.rate_cue({"rate": 3.1})
    assert slow["slow"] is True and slow["message"] == S.RATE_SLOW_MSG and slow["reference"] is True
    assert slow["range"] == [S.RATE_P10, S.RATE_P90] and slow["unit"] == "음절/초" and slow["value"] == 3.1
    assert S.rate_cue({"rate": 5.3})["slow"] is False and S.rate_cue({"rate": 5.3})["message"] is None
    assert S.rate_cue({"rate": 9.0})["slow"] is False          # 빠른 쪽은 안내하지 않는다(사전 등록 4절)
    assert S.rate_cue(None) is None and S.rate_cue({"rate": None}) is None


def test_thresholds_match_preregistered_538_percentiles():
    # docs/speak-visual-cues.md 7절: 538 탐색 절반 10·50·90백분위 4.0831·5.2665·6.8181
    assert (S.RATE_P10, S.RATE_P50, S.RATE_P90) == (4.08, 5.27, 6.82)
    assert "—" not in S.RATE_SLOW_MSG


_SCENARIO = r'''
import json
from fastapi.testclient import TestClient
import dgop_acoustic
import main

def fake_assess(data, target, aligner_id=None, scorer_id=None, **kw):
    phones = [{"token": "n:ㅏ", "t0": 0.1 * i, "t1": 0.1 * i + 0.02, "dgop": 0.5, "aligned": True, "scorable": True}
              for i in range(6)]
    return {"score": 70.0, "raw_score": 7.0, "uncertainty": 0.3, "phones": phones,
            "rate": {"n_syll": 6, "span": 2.0, "pause": 0.0, "rate": 3.0, "pause_ratio": 0.0, "artic": 3.0}}

dgop_acoustic.HAS_ACOUSTIC = True
dgop_acoustic.assess_text = fake_assess
out = {}
with TestClient(main.app) as c:
    r = c.post("/api/auth/register", json={"email": "s7@example.com", "username": "빠르기시험", "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    def assess(target, stage):
        res = c.post("/api/speak/assess", data={"target": target, "stage": str(stage), "loudness": "50", "duration": "2"},
                     files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")}, headers=h)
        return res.status_code, res.json().get("sound_cue")
    out["sentence"] = assess("오늘 날씨가 좋아요.", 5)
    out["consonant"] = assess("사", 3)
    out["word"] = assess("바다", 4)
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def test_assess_returns_rate_cue_only_in_sentence_stage():
    here = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   DGOP_ALIGNER_ID="fake/aligner", ANTHROPIC_API_KEY="", LIPLAB_AV_FUSION="0")
        p = subprocess.run([sys.executable, "-c", _SCENARIO], cwd=here, env=env, capture_output=True, text=True, timeout=180)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line, f"시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}"
    r = json.loads(line[len("RESULT "):])
    code, cue = r["sentence"]
    assert code == 200 and cue["kind"] == "rate" and cue["slow"] is True and cue["reference"] is True
    assert r["consonant"] == [200, None] and r["word"] == [200, None]
