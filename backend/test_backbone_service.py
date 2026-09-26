"""공용 음성 백본 서비스(A-9) 테스트 — 모델을 받지 않고 적재 함수를 바꿔 캐시·공유·상태·위임만 본다."""
import backbone_service as bb


class _FakeModel:
    def parameters(self):
        return iter([])


def _with_fake_loaders(fn):
    calls = []

    def fake(kind):
        def load(model_id, device):
            calls.append((model_id, kind, device))
            return (f"proc:{model_id}" if kind == "ctc" else None), _FakeModel()
        return load

    old = dict(bb._LOADERS)
    bb.clear()
    bb._LOADERS.update({"base": fake("base"), "ctc": fake("ctc")})
    try:
        return fn(calls)
    finally:
        bb._LOADERS.clear()
        bb._LOADERS.update(old)
        bb.clear()


def test_loads_once_and_shares_the_same_object():
    def run(calls):
        a = bb.load("m/wavlm", "base", "cpu")
        b = bb.load("m/wavlm", "base", "cpu")
        assert a is b and calls == [("m/wavlm", "base", "cpu")]
        bb.load("m/wavlm", "base", "cuda")            # 장치가 다르면 따로 올린다
        bb.load("m/ctc", "ctc", "cpu")
        st = bb.status()
        rows = {(r["model_id"], r["kind"], r["device"]): r for r in st["loaded"]}
        assert rows[("m/wavlm", "base", "cpu")]["uses"] == 2
        assert len(rows) == 3 and len(calls) == 3
        assert set(st["consumers"]) == {"a4_audio2face", "b_dgop"}
    _with_fake_loaders(run)


def test_unknown_kind_is_rejected():
    try:
        bb.load("m/x", "video")
    except ValueError:
        return
    raise AssertionError("알 수 없는 종류는 거부해야 한다")


def test_dgop_acoustic_loads_through_the_service():
    import dgop_acoustic as da

    def run(calls):
        old = da.HAS_ACOUSTIC
        da.HAS_ACOUSTIC = True
        try:
            proc, _ = da._load("m/ctc", device="cpu")
            again, _ = da._load("m/ctc", device="cpu")
        finally:
            da.HAS_ACOUSTIC = old
        assert proc == "proc:m/ctc" and again == proc
        assert calls == [("m/ctc", "ctc", "cpu")]      # 정렬기·채점기가 같으면 한 번만 적재
    _with_fake_loaders(run)


def test_status_does_not_load_anything():
    def run(calls):
        st = bb.status()
        assert st["loaded"] == [] and calls == []
    _with_fake_loaders(run)


def test_status_answers_while_a_model_is_loading():
    """적재 중에도 status()가 기다리지 않고 '올리는 중'을 보여야 한다(비동기 엔드포인트가 서버를 멈추지 않게)."""
    import threading
    started, release = threading.Event(), threading.Event()

    def slow(model_id, device):
        started.set()
        release.wait(5)
        return None, _FakeModel()

    bb.available()   # torch 첫 불러오기(1초 넘게 걸리기도 한다)는 잠금과 무관하니 재는 구간 밖에서 끝내 둔다
    old = dict(bb._LOADERS)
    bb.clear()
    bb._LOADERS["base"] = slow
    t = threading.Thread(target=bb.load, args=("m/slow", "base", "cpu"))
    try:
        t.start()
        assert started.wait(5)
        done = threading.Event()
        box = {}
        threading.Thread(target=lambda: (box.setdefault("st", bb.status()), done.set())).start()
        assert done.wait(1), "적재 중 status()가 막혔다"
        assert [r["model_id"] for r in box["st"]["loading"]] == ["m/slow"] and box["st"]["loaded"] == []
        release.set()
        t.join(5)
        st = bb.status()
        assert st["loading"] == [] and st["loaded"][0]["uses"] == 1
    finally:
        release.set()
        if t.is_alive():
            t.join(5)   # 실패해도 적재 스레드가 끝난 뒤에 비워야 캐시에 m/slow가 다시 들어가지 않는다
        bb._LOADERS.clear()
        bb._LOADERS.update(old)
        bb.clear()
