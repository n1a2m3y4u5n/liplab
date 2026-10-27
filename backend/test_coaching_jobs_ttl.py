"""추가 녹음이 없어도 조회 시 TTL을 적용한다. DB 저장 작업은 취소하지 않는다."""
import asyncio
from types import SimpleNamespace

import pytest
import main


def test_get_ttl_boundary_and_capacity(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: now[0])
    jobs = main._CoachingJobs(ttl_s=10, total=2)
    first = {"t": 100.0, "user": 1, "task": object()}
    second = {"t": 101.0, "user": 2, "task": object()}
    jobs._jobs = {"first": first, "second": second}
    now[0] = 109.999
    assert jobs.get("first", 1) is first
    assert jobs.get("first", 2) is None
    assert jobs.get(None, 1) is None
    assert len(jobs._jobs) == 2  # 꽉 차 있어도 조회가 유효한 결과를 지우지 않는다
    now[0] = 110.0
    assert jobs.get("first", 1) is None
    assert jobs.get("second", 2) is second
    now[0] = 111.0
    assert jobs.get("missing", 1) is None
    assert jobs._jobs == {}


def test_expired_endpoint_404_without_cancelling_save(monkeypatch):
    async def run():
        now = [0.0]
        monkeypatch.setattr(main.time, "monotonic", lambda: now[0])
        jobs = main._CoachingJobs(ttl_s=10, total=1)
        ready = asyncio.Event()
        async def coach(attempt_id, args):
            await ready.wait()
            return "잘했어요."
        monkeypatch.setattr(jobs, "_run", coach)
        monkeypatch.setattr(main, "_COACH_JOBS", jobs)
        cid = jobs.start(1, None, {})
        task = jobs.get(cid, 1)["task"]
        now[0] = 10.0
        with pytest.raises(main.HTTPException) as exc:
            await main.speak_coaching(cid, current_user=SimpleNamespace(id=1))
        assert exc.value.status_code == 404
        assert not task.cancelled()
        ready.set()
        assert await task == "잘했어요."
    asyncio.run(run())


def test_start_reserves_capacity_and_results_can_be_read_again(monkeypatch):
    async def run():
        jobs = main._CoachingJobs(ttl_s=10, total=1)
        async def coach(attempt_id, args):
            return "잘했어요."
        monkeypatch.setattr(jobs, "_run", coach)
        monkeypatch.setattr(main, "_COACH_JOBS", jobs)
        cid = jobs.start(1, None, {})
        await jobs.get(cid, 1)["task"]
        for _ in range(2):
            assert await main.speak_coaching(cid, current_user=SimpleNamespace(id=1)) == {"coaching": "잘했어요."}
        newer = jobs.start(1, None, {})
        assert jobs.get(cid, 1) is None
        assert len(jobs._jobs) == 1
        await jobs.get(newer, 1)["task"]
    asyncio.run(run())
