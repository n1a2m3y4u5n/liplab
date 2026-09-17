"""
OLKAVS 전처리 순수 로직 검증. ffmpeg 없이 돌아가는 부분만 다룬다.

실행: python scripts/test_preprocess_olkavs.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preprocess_olkavs import union_square_box, index_media, _load_label, _clip_jobs  # noqa: E402


def _ok(cond, msg):
    assert cond, "FAIL: " + msg


def test_union_square_box():
    # 두 프레임의 입술 박스를 감싸는 정사각형. margin 0.35가 붙는다.
    box = union_square_box([[100, 100, 140, 120], [110, 105, 150, 130]], 640, 480)
    x, y, w, h = box
    _ok(w == h, "정사각형이어야 함")
    _ok(w % 2 == 0, "ffmpeg를 위해 짝수 치수")
    _ok(x >= 0 and y >= 0 and x + w <= 640 and y + h <= 480, "프레임 밖으로 나가지 않음")
    # 원래 입술 영역(100~150, 100~130)을 실제로 덮는지
    _ok(x <= 100 and y <= 100 and x + w >= 150 and y + h >= 130, "입술 영역을 모두 포함해야 함")


def test_union_square_box_edge_cases():
    _ok(union_square_box([], 640, 480) is None, "박스가 없으면 None")
    _ok(union_square_box([None, [1, 2]], 640, 480) is None, "형식이 깨진 박스는 무시")
    # 프레임보다 큰 박스를 요구해도 프레임 안으로 잘려야 한다
    box = union_square_box([[0, 0, 640, 480]], 640, 480)
    x, y, w, h = box
    _ok(x + w <= 640 and y + h <= 480, "프레임 크기를 넘지 않음")


def test_index_media_single_walk():
    """
    인덱싱이 파일명→경로를 제대로 만드는지. 예전 구현은 JSON마다 전체 폴더를 다시
    훑어(O(n²)) 실제 규모에서 끝나지 않았다 — 이 함수가 그 병목을 대체한다.
    """
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "a", "b"))
        os.makedirs(os.path.join(d, "c"))
        for p in ["a/x.json", "a/b/y.json", "c/z.json"]:
            open(os.path.join(d, p), "w").close()
        for p in ["a/v1.mp4", "a/b/v2.mp4", "c/v3.mp4"]:
            open(os.path.join(d, p), "w").close()
        open(os.path.join(d, "readme.txt"), "w").close()

        jsons, mp4s = index_media(d)
        _ok(len(jsons) == 3, f"JSON 3개를 찾아야 함 (찾음: {len(jsons)})")
        _ok(set(mp4s) == {"v1.mp4", "v2.mp4", "v3.mp4"}, f"mp4 인덱스가 틀림: {set(mp4s)}")
        _ok(mp4s["v2.mp4"].endswith(os.path.join("a", "b", "v2.mp4")), "중첩 폴더 경로가 정확해야 함")
        _ok(all(p.endswith(".json") for p in jsons), "JSON만 담겨야 함")


def test_load_label_tolerates_broken_files():
    with tempfile.TemporaryDirectory() as d:
        good = os.path.join(d, "good.json")
        with open(good, "w", encoding="utf-8") as f:
            json.dump([{"Video_info": {"video_Name": "v.mp4"}}], f)
        _ok(_load_label(good)["Video_info"]["video_Name"] == "v.mp4", "정상 라벨 로드")

        bad = os.path.join(d, "bad.json")
        with open(bad, "w") as f:
            f.write("{ 깨진 json")
        _ok(_load_label(bad) is None, "깨진 JSON은 None (배치를 멈추지 않음)")
        _ok(_load_label(os.path.join(d, "없음.json")) is None, "없는 파일은 None")


def _sample_label():
    return {
        "Video_info": {"video_Name": "vid001.mp4", "FPS": "30", "Resolution": "640x480"},
        "Bounding_box_info": {"Lip_bounding_box": {
            "xtl_ytl_xbr_ybr": [[100, 100, 140, 120]] * 100}},
        "Sentence_info": [
            {"ID": 1, "start_time": 0.0, "end_time": 1.0, "sentence_text": "안녕하세요"},
            {"ID": 2, "start_time": 1.0, "end_time": 2.0, "sentence_text": "반갑습니다"},
        ],
    }


def test_clip_jobs_modes():
    with tempfile.TemporaryDirectory() as out:
        d = _sample_label()

        jobs, rows = _clip_jobs(d, "in.mp4", out, "video", 0, None)
        _ok(len(rows) == 2 and len(jobs) == 2, "video 모드: 문장 2개 → 작업 2개")
        _ok(all("clip" in r for r in rows), "video 모드는 clip 경로를 남긴다")
        _ok(all("audio" not in r for r in rows), "video 모드는 오디오를 만들지 않는다")
        _ok(all("-an" in j[0] for j in jobs), "립 클립은 무음이어야 함")
        _ok(any("crop=" in a for a in jobs[0][0]), "크롭 필터가 있어야 함")

        # 오디오 모드는 원본 영상이 아니라 미리 뽑은 전체 오디오에서 잘라야 한다
        jobs, rows = _clip_jobs(d, "in.mp4", out, "audio", 0, "/tmp/full.flac")
        _ok(all("audio" in r for r in rows), "audio 모드는 audio 경로를 남긴다")
        _ok(all("/tmp/full.flac" in j[0] for j in jobs), "문장별로 원본 영상을 다시 열면 안 됨")

        jobs, rows = _clip_jobs(d, "in.mp4", out, "both", 0, "/tmp/full.flac")
        _ok(len(jobs) == 4, "both 모드: 클립 2 + 오디오 2")
        _ok(all("clip" in r and "audio" in r for r in rows), "both는 둘 다 남긴다")


def test_clip_jobs_skips_existing_output():
    """며칠 걸리는 작업이라 중단 후 이어서 돌릴 수 있어야 한다."""
    with tempfile.TemporaryDirectory() as out:
        os.makedirs(os.path.join(out, "clips"))
        open(os.path.join(out, "clips", "vid001_1.mp4"), "w").close()  # 이미 만든 산출물

        jobs, rows = _clip_jobs(_sample_label(), "in.mp4", out, "video", 0, None)
        _ok(len(rows) == 2, "라벨은 두 문장 모두 남아야 함")
        _ok(len(jobs) == 1, f"이미 있는 클립은 다시 만들지 않아야 함 (작업 {len(jobs)}개)")
        _ok("vid001_2.mp4" in jobs[0][1], "남은 작업은 아직 없는 문장이어야 함")


def test_clip_jobs_respects_max_sentences():
    with tempfile.TemporaryDirectory() as out:
        _jobs, rows = _clip_jobs(_sample_label(), "in.mp4", out, "video", 1, None)
        _ok(len(rows) == 1, "--max 1이면 문장 1개만")


def test_clip_jobs_tolerates_missing_metadata():
    with tempfile.TemporaryDirectory() as out:
        broken = {"Video_info": {"video_Name": "v.mp4"}}  # FPS·Resolution 없음
        jobs, rows = _clip_jobs(broken, "in.mp4", out, "video", 0, None)
        _ok(jobs == [] and rows == [], "메타데이터가 없으면 조용히 건너뛴다")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
