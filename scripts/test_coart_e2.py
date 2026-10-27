"""E2 회귀 및 uniform/stub 합성 스모크. 538 측정 아님."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('coart_eval', Path(__file__).with_name('coart_pod_eval.py'))
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


def test_views_and_envelope():
    for scene in ('C12', 'E274'):
        assert E.VIEW_RE.search(f'clip_{scene}_A_001').group(1) == 'A'
    assert E.lip_envelope(.05, .2, .2, True) == pytest.approx(0)
    assert E.lip_envelope(.125, .2, .2, True) == pytest.approx(.5)
    assert E.lip_envelope(.35, .2, .2) == pytest.approx(1)
    assert E.lip_envelope(.47, .2, .2) == pytest.approx(0)


def test_curve_simulation_preserves_jaw():
    ts = np.arange(0, .6, .01)
    base = (0., 0., .4)
    full = (.6, .3, .4)
    a = E.simulate([(0, full, 30), (.5, base, 30)], ts)
    b = E.simulate([(0, full, 30, (base, .2, .2, True)), (.5, base, 30)], ts)
    np.testing.assert_array_equal(a[:, 2], b[:, 2])
    assert b[10, 0] < a[10, 0]


def test_delta_uses_identical_pairs():
    clips = [{'spk': 'a', 'r': {'off': {'R': [.2]}, 'low': {'R': [.4]}}},
             {'spk': 'b', 'r': {'off': {'R': [.9]}, 'low': {'R': [None]}}}]
    assert E.delta(clips, 'low', 'R', 0) == pytest.approx((.2, 1))


def test_uniform_stub_smoke(tmp_path):
    import cv2
    import soundfile as sf
    root = tmp_path / 'synthetic'
    root.mkdir()
    clip = 'synthetic_E274_A_001'
    video = cv2.VideoWriter(str(root / (clip + '.mp4')), cv2.VideoWriter_fourcc(*'mp4v'), 30, (32, 32))
    for _ in range(90): video.write(np.zeros((32,32,3), dtype=np.uint8))
    video.release()
    sf.write(root / (clip + '.wav'), .2 * np.sin(np.arange(48000) * 2*np.pi*220/16000), 16000)
    config = {'backend': str(Path(__file__).resolve().parents[1] / 'backend'),
              'shapes': str(Path(__file__).with_name('viseme_shapes.json')),
              'align': 'uniform', 'face': 'stub', 'aligner': '', 'experiment': 'e2', 'out': str(tmp_path)}
    r = E.clip_job((str(root / (clip + '.mp4')), clip, 'synthetic-only', '수술', config))
    assert 'error' not in r, r
    assert r['n'] >= 15
    assert set(E.E2_CONDITIONS) <= r['r'].keys()
    assert r['r']['off']['J'] == r['r']['both']['J']
    (Path(__file__).resolve().parents[1] / 'out' / 'e2-smoke.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')


def test_frozen_confirmation_does_not_select_again():
    spk = next(str(i) for i in range(10) if E.half_of(str(i)) == 1)
    r = {c: {f: [.3 if c == 'off' else .4] * len(E.LAGS_MS) for f in E.FEATS}
         for c in ['off','on0.6', *E.E2_CONDITIONS]}
    result = E.summarize([{'spk': spk, 'n': 30, 'face_ratio': 1, 'r': r, 'align': 'uniform'}], 'e2', selection={'condition': 'curve', 'lag_ms': -66})
    assert result['confirm']['condition'] == 'curve'
    assert result['confirm']['lag_ms'] == -66


def test_insufficient_new_speakers_never_confirms():
    result = E.summarize([], 'e2', selection={'condition': 'curve', 'lag_ms': 0})
    assert 'confirm' not in result
    assert 'minimum 15' in result['verdict']
