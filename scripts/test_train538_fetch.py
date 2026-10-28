"""네트워크·키 없이 train538 받기의 tar 조각 연결·잘림·중단·재개·양보를 검증한다(가짜 Stream)."""
import io
import json
import tarfile

import pytest

import e2_retry_acquire as E2
import train538_fetch as T


def archive(items):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, data in items:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return out.getvalue()


def split(raw, at=2048):
    """서버 tar: 내부 tar를 .partN으로 나눈 바깥 tar."""
    return archive([('x.tar.part0', raw[:at]), ('x.tar.part1', raw[at:])])


def label(name, person, n=20):
    return json.dumps([{'Video_info': {'video_Name': name}, 'speaker_info': {'speaker_ID': person, 'Gender': 'F', 'Age': 3},
                        'Audio_env': {'Noise': 'N'}, 'Sentence_info': [
                            {'ID': i, 'sentence_text': f'문장{i}', 'start_time': i * 2.0, 'end_time': i * 2.0 + 1.0} for i in range(n)]}]).encode()


VIDEO = archive([('d/lip_J_1_F_04_C900_A_001.mp4', b'x' * 1500),      # 제외 인물
                 ('d/lip_J_1_F_04_C111_A_001.mp4', b'a' * 3000),
                 ('d/lip_J_1_F_04_C111_A_002.mp4', b'b' * 3000),
                 ('d/lip_J_1_F_04_C111_B_001.mp4', b'c' * 3000),      # 정면 아님
                 ('d/lip_J_1_F_04_C222_A_001.mp4', b'd' * 3000)])
LABEL = archive([('l/lip_J_1_F_04_C111_A_001.json', label('lip_J_1_F_04_C111_A_001.mp4', 'C111')),
                 ('l/lip_J_1_F_04_C111_A_002.json', label('lip_J_1_F_04_C111_A_002.mp4', 'C111')),
                 ('l/zzz.json', b'{}')])


class FakeStream:
    blobs = {}
    opened = []

    def __init__(self, r, cap):
        data = self.blobs[r['video_file']]
        if isinstance(data, Exception):
            raise data
        self.buf = io.BytesIO(data[:cap]); self.n = 0
        FakeStream.opened.append(r['video_file'])

    def read(self, n=-1):
        b = self.buf.read(n); self.n += len(b); return b

    def close(self):
        pass


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(T, 'DATA', tmp_path / 'train538')
    monkeypatch.setattr(T, 'RAW', tmp_path / 'raw')
    monkeypatch.setattr(T, 'E2_ROOT', tmp_path / 'e2')
    monkeypatch.setattr(E2, 'Stream', FakeStream)
    monkeypatch.setattr(T, 'disk_ok', lambda: (True, 0, 0))
    (tmp_path / 'train538').mkdir(); (tmp_path / 'e2').mkdir()
    FakeStream.blobs = {}; FakeStream.opened = []
    return tmp_path


def row(spk, n):
    return {'spk': spk, 'video_file': f'TS{n}.tar', 'video_fileSn': str(n), 'label_file': f'TL{n}.tar', 'label_fileSn': str(1000 + n)}


def fake_cut(sources, labels, row, person, ff):
    return [{'clip': f'{s.stem}_{i}', 'text': f'문장{i}', 'start': 0.0, 'duration': 1.0, 'sentence_ID': i}
            for s in sources for i in range(10)]


def fetch(r, eligible, budget, connections):
    return T.fetch_speaker(r, eligible, budget, cut=fake_cut, connections=connections)


class NoYield:
    baseline = None

    def check(self):
        return True


def test_front_split_boundary_exclusion_and_angle(tmp_path):
    person, saved = T.extract_front(io.BytesIO(split(VIDEO)), lambda p: p != 'C900', tmp_path)
    assert person == 'C111'
    assert [p.name for p in saved] == ['lip_J_1_F_04_C111_A_001.mp4', 'lip_J_1_F_04_C111_A_002.mp4']
    assert saved[1].read_bytes() == b'b' * 3000
    assert not list(tmp_path.glob('*C900*')) and not list(tmp_path.glob('*_B_*'))


def test_front_truncated_last_member_dropped(tmp_path):
    # 서버가 둘째 mp4 도중 연결을 끊음(바깥 tar의 .part1 중간에서 잘림). 내부 tar는 10KiB 단위로 읽으므로 크게 만든다.
    raw = archive([('lip_J_1_F_04_C111_A_001.mp4', b'a' * 30000), ('lip_J_1_F_04_C111_A_002.mp4', b'b' * 30000)])
    person, saved = T.extract_front(io.BytesIO(split(raw, 40000)[:50000]), lambda p: True, tmp_path)
    assert person == 'C111' and [p.name for p in saved] == ['lip_J_1_F_04_C111_A_001.mp4']
    assert not list(tmp_path.glob('*.partial')) and not (tmp_path / 'lip_J_1_F_04_C111_A_002.mp4').exists()


def test_labels_stop_when_found():
    found = T.extract_labels(io.BytesIO(split(LABEL)), {'lip_J_1_F_04_C111_A_001.json'})
    assert list(found) == ['lip_J_1_F_04_C111_A_001.json']
    assert found['lip_J_1_F_04_C111_A_001.json']['speaker_info']['speaker_ID'] == 'C111'


def test_cut_uses_label_sentences(env, monkeypatch):
    calls = []
    monkeypatch.setattr(T.subprocess, 'run', lambda cmd, **k: calls.append(cmd))
    src = env / 'lip_J_1_F_04_C111_A_001.mp4'
    labels = {'lip_J_1_F_04_C111_A_001.json': json.loads(label(src.name, 'C111', 40))[0]}
    clips = T.cut_clips([src], labels, row('spk1', 1), 'C111', 'ffmpeg')
    assert len(clips) == T.CLIPS == len(calls) and clips[0]['clip'] == 'lip_J_1_F_04_C111_A_001_0'
    with pytest.raises(AssertionError):
        T.cut_clips([src], labels, row('spk1', 1), 'C222', 'ffmpeg')


def test_run_resume_budget_and_failure(env):
    FakeStream.blobs = {'TS1.tar': split(VIDEO), 'TL1.tar': split(LABEL),
                        'TS2.tar': split(archive([('lip_J_1_F_04_C111_A_001.mp4', b'a' * 100)])), 'TL2.tar': split(LABEL),
                        'TS3.tar': split(archive([('lip_J_1_F_04_C333_A_001.mp4', b'a' * 100)])), 'TL3.tar': split(archive([]))}
    queue = [row('spk1', 1), row('spk2', 2), row('spk3', 3)]
    st = T.run(queue, {'C900'}, 10, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    assert list(st['done']) == ['spk1'] and st['done']['spk1']['person'] == 'C111'
    assert 'already' not in json.dumps(st['failed'])
    assert set(st['failed']) == {'spk2', 'spk3'}   # spk2: 이미 받은 인물만 있음, spk3: 라벨 없음
    counts = json.loads((T.DATA / 'request-counts.json').read_text())
    assert counts == {'TS1.tar': 1, 'TL1.tar': 1, 'TS2.tar': 1, 'TS3.tar': 1, 'TL3.tar': 1}
    manifest = (T.DATA / 'manifest.tsv').read_text(encoding='utf-8').splitlines()
    assert len(manifest) == 20 and manifest[0].split('\t')[1] == 'spk1'
    assert (T.DATA / 'manifest_meta.tsv').read_text(encoding='utf-8').splitlines()[1].split('\t')[2] == 'C111'
    assert not list(T.RAW.rglob('*.mp4'))   # 원본은 화자마다 지운다
    # 재개: 끝난 화자와 실패 화자는 다시 요청하지 않는다
    FakeStream.opened = []
    T.run(queue, {'C900'}, 10, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    assert FakeStream.opened == []
    # --retry-failed: 두 번째 요청까지만, 세 번째는 상한
    T.run(queue, {'C900'}, 10, retry_failed=True, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    T.run(queue, {'C900'}, 10, retry_failed=True, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    counts = json.loads((T.DATA / 'request-counts.json').read_text())
    assert counts['TS3.tar'] == 2 and counts['TL3.tar'] == 2 and counts['TS2.tar'] == 2
    assert 'request limit' in T.load_state()['failed']['spk3']['error']


def test_auth_stop_e2_file_blocks_requests(env):
    (T.E2_ROOT / 'AUTH_STOP').write_text('x')
    FakeStream.blobs = {'TS1.tar': split(VIDEO), 'TL1.tar': split(LABEL)}
    with pytest.raises(E2.AuthFailure):
        T.run([row('spk1', 1)], set(), 10, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    assert FakeStream.opened == [] and not (T.DATA / 'request-counts.json').exists()


def test_auth_failure_midway_stops_run(env):
    FakeStream.blobs = {'TS1.tar': E2.AuthFailure('authentication failed; stopped'), 'TS2.tar': split(VIDEO)}
    with pytest.raises(E2.AuthFailure):
        T.run([row('spk1', 1), row('spk2', 2)], set(), 10, fetch=fetch, yielder=NoYield(), connections=lambda: 0)
    assert T.load_state()['status'] == 'auth_stop'
    assert json.loads((T.DATA / 'request-counts.json').read_text()) == {'TS1.tar': 1}


def test_connection_limit_waits(env, monkeypatch):
    seen = iter([2, 2, 1, 0, 0])
    sleeps = []
    monkeypatch.setattr(T.time, 'sleep', sleeps.append)
    FakeStream.blobs = {'TS1.tar': split(VIDEO), 'TL1.tar': split(LABEL)}
    st = T.run([row('spk1', 1)], {'C900'}, 10, fetch=fetch, yielder=NoYield(), connections=lambda: next(seen))
    assert list(st['done']) == ['spk1'] and sleeps == [60, 60]


def write_transfers(path, speeds):
    with path.open('a') as f:
        for s in speeds:
            f.write(json.dumps({'file': 'TSx.tar', 'bytes': int(s * 100), 'seconds': 100}) + '\n')


def test_yield_when_e2_slows_then_resume(env):
    path = T.E2_ROOT / 'transfers.jsonl'
    write_transfers(path, [5e6] * 5)
    sleeps = []

    def sleep(sec):
        sleeps.append(sec)
        if len(sleeps) == 1:
            write_transfers(path, [3e6])   # 기다리는 동안에도 느림 → 한 번 더
    y = T.Yielder(path, sleep=sleep)
    assert y.baseline == pytest.approx(5e6)
    write_transfers(path, [4e6])          # 20% 저하: 양보하지 않음
    assert y.slow()[0] is False
    write_transfers(path, [3e6, 3e6])     # 최근 3건 평균 3.33e6 < 3.5e6
    assert y.check() and sleeps == [T.YIELD_WAIT, T.YIELD_WAIT]
    lines = (T.DATA / 'TRAIN_YIELD').read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])['recent_Bps'] < 0.7 * 5e6


def test_yield_between_speakers_only(env):
    calls = []

    class Spy(NoYield):
        def check(self):
            calls.append(len(T.load_state()['done']))
            return True
    FakeStream.blobs = {'TS1.tar': split(VIDEO), 'TL1.tar': split(LABEL)}
    T.run([row('spk1', 1)], {'C900'}, 10, fetch=fetch, yielder=Spy(), connections=lambda: 0)
    assert calls == [1]   # 화자를 마친 뒤에만 확인


def test_queue_excludes_and_interleaves():
    files = {f'TL{n}.tar': (100, str(n)) for n in range(1, 9)} | {f'TS{n}.tar': (10**10, str(100 + n)) for n in range(1, 9)}
    q = T.build_queue(files, {'spk297', 'spk302'}, {'TS4.tar'})
    assert [r['spk'] for r in q] == ['spk298', 'spk301', 'spk304', 'spk299', 'spk303']
    assert T.batch_spk('VL1.tar') == 'spk601'


def test_frozen_queue_respects_registered_exclusions():
    persons, blocked, overlap = T.exclusions()
    q = T.build_queue(T.filetree(), blocked, overlap)
    spks = {r['spk'] for r in q}
    assert not spks & blocked and not {t for r in q for t in (r['video_file'], r['label_file'])} & overlap
    assert len(persons) == 55 and {'C013', 'E261'} <= persons and len(q) == 92
