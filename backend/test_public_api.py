"""공개 인터페이스(§6.3) — 로그인 없이 자원·채점을 쓰고, 입력 길이를 제한한다."""
from fastapi.testclient import TestClient

import main


def test_public_resources_and_score_without_login():
    with TestClient(main.app) as c:
        r = c.get("/api/public/resources")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["license"] == "CC BY 4.0" and meta["semver"]
        s = c.post("/api/public/score", json={"target": "밥 먹었어요", "answer": "맘 먹었어요"})
        assert s.status_code == 200
        body = s.json()
        assert 0 <= body["score"] < 100 and body["confusions"], "ㅂ/ㅁ 혼동이 잡혀야 한다"
        same = c.post("/api/public/score", json={"target": "굳이", "answer": "구지"}).json()
        assert same["score"] >= 99, "소리가 같으면 표기가 달라도 만점"
        assert c.post("/api/public/score", json={"target": "가" * 101, "answer": "가"}).status_code == 400
        assert c.post("/api/public/score", json={"target": "", "answer": "가"}).status_code == 400
