"""Safari의 fragmented MP4/AAC 녹음을 서버가 수신·해독하는지 확인한다."""
import asyncio
import io

import pytest


def test_safari_fragmented_mp4_upload_and_decode():
    av = pytest.importorskip('av')
    np = pytest.importorskip('numpy')
    from starlette.datastructures import Headers, UploadFile
    from main import _read_audio_limited
    from formants import decode_mono16k
    from audio2face import _to_mono16k

    buffer = io.BytesIO()
    with av.open(buffer, mode='w', format='mp4', options={'movflags': 'frag_keyframe+empty_moov'}) as container:
        stream = container.add_stream('aac', rate=48000)
        stream.layout = 'mono'
        wave = (0.1 * np.sin(2 * np.pi * 440 * np.arange(48000) / 48000)).astype('float32')[None, :]
        frame = av.AudioFrame.from_ndarray(wave, format='fltp', layout='mono')
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    payload = buffer.getvalue()
    upload = UploadFile(io.BytesIO(payload), filename='speech.m4a', headers=Headers({'content-type': 'audio/mp4'}))
    assert asyncio.run(_read_audio_limited(upload)) == payload
    for decode in (decode_mono16k, _to_mono16k):
        samples = decode(payload)
        assert samples is not None and 15000 <= len(samples) <= 17000
        assert np.isfinite(samples).all() and np.max(np.abs(samples)) > 0.01
