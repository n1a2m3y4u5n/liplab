"""LLM 하루 한도(llm_budget)와 추론 대기열 상한."""
import asyncio
import json
import os

import pytest

import llm_budget


def _reset(monkeypatch, tmp_path, daily="3", per_client="2"):
    monkeypatch.setenv("LIPLAB_LLM_DAILY_MAX", daily)
    monkeypatch.setenv("LIPLAB_LLM_CLIENT_DAILY_MAX", per_client)
    monkeypatch.setenv("LIPLAB_LLM_BUDGET_FILE", str(tmp_path / "b.json"))
    llm_budget._state.update(date=None, total=0, clients={})


def test_per_client_then_global_cap(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path)
    llm_budget.charge("a")
    llm_budget.charge("a")
    with pytest.raises(llm_budget.BudgetExceeded):
        llm_budget.charge("a")          # IP당 2회
    llm_budget.charge("b")              # 서버 전체 3회째
    with pytest.raises(llm_budget.BudgetExceeded):
        llm_budget.charge("c")          # 새 IP여도 서버 전체 한도
    assert json.load(open(tmp_path / "b.json"))["total"] == 3


def test_global_count_survives_restart(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path, daily="5", per_client="5")
    for _ in range(4):
        llm_budget.charge("a")
    llm_budget._state.update(date=None, total=0, clients={})   # 기계 재시작
    llm_budget.charge("z")
    with pytest.raises(llm_budget.BudgetExceeded):
        llm_budget.charge("z")


def test_guard_blocks_before_calling_api(monkeypatch, tmp_path):
    _reset(monkeypatch, tmp_path, daily="1", per_client="1")
    calls = []

    class _Msgs:
        async def create(self, **k):
            calls.append(k)
            return "ok"

    class _Client:
        messages = _Msgs()

    c = llm_budget.guard(_Client())
    llm_budget.guard(c)                 # 두 번 걸어도 한 번만 센다
    token = llm_budget.current_client.set("ip1")
    try:
        assert asyncio.run(c.messages.create(model="m")) == "ok"
        with pytest.raises(llm_budget.BudgetExceeded):
            asyncio.run(c.messages.create(model="m"))
    finally:
        llm_budget.current_client.reset(token)
    assert len(calls) == 1


def test_real_clients_are_guarded():
    import llm_service
    assert getattr(llm_service.anthropic_client.messages, "_liplab_budget", False)


def test_ml_queue_rejects_when_full(monkeypatch):
    # 추론 대기열: 실행 중 + 대기가 동시 실행 수 + 대기 상한에 닿으면 받기 전에 503
    os.environ.setdefault("JWT_SECRET", "test-only-budget-secret")
    import main
    from fastapi import HTTPException
    monkeypatch.setattr(main, "_ML_INFLIGHT", main._ML_CONCURRENCY + main._ML_QUEUE_MAX - 1)
    main._ml_admit()
    monkeypatch.setattr(main, "_ML_INFLIGHT", main._ML_CONCURRENCY + main._ML_QUEUE_MAX)
    with pytest.raises(HTTPException) as e:
        main._ml_admit()
    assert e.value.status_code == 503

    async def run():
        monkeypatch.setattr(main, "_ML_INFLIGHT", 0)
        async with main._ml_slot():
            assert main._ML_INFLIGHT == 1
        return main._ML_INFLIGHT
    assert asyncio.run(run()) == 0


def test_origin_lock_off_by_default_and_trusts_cf_ip_only_with_secret(monkeypatch):
    import ratelimit

    class _Req:
        def __init__(self, h):
            self.headers = h
            self.client = None
    monkeypatch.delenv("LIPLAB_ORIGIN_SECRET", raising=False)
    r = _Req({"fly-client-ip": "1.1.1.1", "cf-connecting-ip": "9.9.9.9"})
    assert ratelimit.origin_ok(r) and ratelimit._client_key(r) == "1.1.1.1"   # 설정 전: 지금과 같다
    monkeypatch.setenv("LIPLAB_ORIGIN_SECRET", "s3cret")
    assert not ratelimit.origin_ok(r)                                          # 비밀 헤더 없음 → 막힘
    ok = _Req({"fly-client-ip": "104.16.0.1", "cf-connecting-ip": "9.9.9.9", "x-origin-auth": "s3cret"})
    assert ratelimit.origin_ok(ok) and ratelimit._client_key(ok) == "9.9.9.9"
