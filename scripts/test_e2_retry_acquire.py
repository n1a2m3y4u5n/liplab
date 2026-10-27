"""네트워크 없이 tar 조각 경계와 잘린 마지막 멤버를 검증한다."""
import io
import tarfile

from e2_retry_acquire import extract_target


def archive(items):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, data in items:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return out.getvalue()


def test_split_boundary_and_truncated_member(tmp_path):
    raw = archive([('first.mp4', b'a' * 3000), ('target.mp4', b'b' * 4000)])
    dest = tmp_path / 'source.mp4'
    split = archive([('x.tar.part0', raw[:2048]), ('x.tar.part1', raw[2048:])])
    result, _ = extract_target(io.BytesIO(split), 'target.mp4', dest)
    assert result and dest.read_bytes() == b'b' * 4000
    dest.unlink()
    result, _ = extract_target(io.BytesIO(split), 'target.mp4', dest, front_only=True)
    assert result is None and not dest.exists()
    truncated = archive([('x.tar.part0', raw[:6000])])
    result, _ = extract_target(io.BytesIO(truncated), 'target.mp4', dest)
    assert result is None and not dest.exists()
    assert not dest.with_suffix('.partial').exists()
    result, _ = extract_target(io.BytesIO(truncated), 'first.mp4', dest)
    assert result and dest.read_bytes() == b'a' * 3000


if __name__ == '__main__':
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        test_split_boundary_and_truncated_member(Path(directory))
    print('PASS: split boundary, truncated last member, earlier complete member')
