"""kmsav_fetch 시험: 429·봇 확인에서 멈춤, 건너뛴 영상 사유 기록, 재개, E2 양보. 네트워크를 쓰지 않는다."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kmsav_fetch as K  # noqa: E402


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(K, 'RAW', tmp_path / 'raw')
    monkeypatch.setattr(K, 'DATA', tmp_path / 'data')
    return argparse.Namespace(pause_min=0, pause_max=0, max_videos=0)


def Q(*ids):
    return [{'id': i, 'sec': 10, 'domain': 'x', 'split': 'train'} for i in ids]


class NoYield:
    baseline = None

    def check(self):
        pass


def test_classify():
    assert K.classify('ERROR: HTTP Error 429: Too Many Requests') == 'FATAL'
    assert K.classify('Sign in to confirm you’re not a bot') == 'FATAL'
    assert K.classify('Video unavailable. This video has been removed') == 'removed'
    assert K.classify('Private video') == 'private'
    assert K.classify('message about something else') == 'error'


def test_stop_on_bot_check_and_resume(tmp_path, monkeypatch):
    a = setup(tmp_path, monkeypatch)
    calls = []

    def dl(vid, args):
        calls.append(vid)
        if vid == 'b':
            return 'FATAL', 'Sign in to confirm'
        (K.RAW / f'{vid}.mp4').write_bytes(b'x' * 10)
        return 'ok', 10

    assert K.run(Q('a', 'b', 'c'), a, dl=dl, yielder=NoYield(), sleep=lambda s: None) == 2
    assert calls == ['a', 'b'] and (K.DATA / 'KMSAV_STOP').exists()
    # 사람이 지우기 전에는 시작하지 않는다
    assert K.run(Q('a', 'b', 'c'), a, dl=dl, yielder=NoYield(), sleep=lambda s: None) == 2 and calls == ['a', 'b']
    (K.DATA / 'KMSAV_STOP').unlink()
    ok = lambda v, args: (K.RAW.joinpath(f'{v}.mp4').write_bytes(b'y'), ('ok', 1))[1]  # noqa: E731
    assert K.run(Q('a', 'b', 'c'), a, dl=ok, yielder=NoYield(), sleep=lambda s: None) == 0
    st = json.loads((K.DATA / 'state.json').read_text())
    assert st['done'] == ['a', 'b', 'c']


def test_skip_reasons_and_max_videos(tmp_path, monkeypatch):
    a = setup(tmp_path, monkeypatch)
    a.max_videos = 1

    def dl(vid, args):
        if vid == 'gone':
            return 'removed', 'Video unavailable'
        (K.RAW / f'{vid}.mp4').write_bytes(b'x')
        return 'ok', 1

    assert K.run(Q('gone', 'a', 'b'), a, dl=dl, yielder=NoYield(), sleep=lambda s: None) == 0
    st = json.loads((K.DATA / 'state.json').read_text())
    assert st['skipped']['gone']['reason'] == 'removed' and st['done'] == ['a']


def test_yield_on_e2_slowdown(tmp_path):
    tr = tmp_path / 't.jsonl'
    row = lambda bps: json.dumps({'bytes': bps * 100, 'seconds': 100}) + '\n'  # noqa: E731
    tr.write_text(row(1000) * 5)
    waits = []

    def sleep(s):
        waits.append(s)
        with tr.open('a') as f:   # 양보 사이 E2 속도가 회복됨
            f.write(row(1000) * 3)

    y = K.Yielder(path=tr, sleep=sleep, wait=1800)
    with tr.open('a') as f:
        f.write(row(600) * 3)   # 40% 하락
    K.DATA = tmp_path / 'data'
    K.DATA.mkdir()
    y.check()
    assert waits == [1800]


def test_no_yield_when_within_30_percent(tmp_path):
    tr = tmp_path / 't.jsonl'
    tr.write_text((json.dumps({'bytes': 100000, 'seconds': 100}) + '\n') * 5)
    y = K.Yielder(path=tr, sleep=lambda s: (_ for _ in ()).throw(AssertionError))
    with tr.open('a') as f:
        f.write((json.dumps({'bytes': 80000, 'seconds': 100}) + '\n') * 3)
    y.check()
