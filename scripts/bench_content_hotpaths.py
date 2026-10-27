"""콘텐츠 반복 경로의 로컬 CPU·파일 읽기 벤치(네트워크·DB 사용 없음)."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import assessment as A
import content_rules as R
import curriculum as C


def measure(fn, repeats):
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        for _ in range(repeats):
            result = fn()
        samples.append((time.perf_counter() - start) * 1000 / repeats)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
    return {"median_ms": statistics.median(samples), "samples_ms": samples,
            "result_count": len(result), "sha256": hashlib.sha256(payload.encode()).hexdigest()}


if __name__ == "__main__":
    words = [w["word"] for w in C.WORD_BANK]
    print(json.dumps({
        "discover_pairs": measure(lambda: R.discover_pairs(words), 1),
        "test_only_words": measure(lambda: sorted(A.test_only_words()), 100),
    }, indent=2))
