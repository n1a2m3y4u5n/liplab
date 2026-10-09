#!/usr/bin/env python3
"""
채점 회귀 점검 실행기(계획 O4). CI가 없어 이 스크립트 하나로 돈다. 자세한 설명은 docs/scoring-regression-2026-10.md.

  # 저장소 뿌리에서(백엔드 가상환경의 파이썬으로)
  ~/Downloads/liplab/backend/.venv/bin/python scripts/scoring_regress.py
      기준(backend/scoring_regress_golden.json)과 지금 출력을 비교해 차이 보고를 찍고, 관련 성질 검사(pytest)도 돌린다.
      차이·고정 기대 위반·검사 실패가 하나라도 있으면 종료 코드 1.

  옵션
    --quick            API 경로 층(별도 프로세스, 약 10초)과 pytest를 건너뛴다(순수 함수 층만, 1초 안팎)
    --layers a,b       층만 고른다(lipread, dictation, speak, engine, speak_api)
    --no-pytest        관련 성질 검사를 돌리지 않는다
    --report FILE      차이 보고(마크다운)를 파일로도 쓴다
    --max-rows N       보고에 찍을 최대 변경 줄 수(기본 400)
    --update           지금 출력을 새 기준으로 쓴다. 의도한 변경일 때만 쓰고, 커밋에 보고를 함께 남긴다.
                       고정 기대(PINNED) 위반이 있으면 쓰지 않는다(규칙 문서 값은 scoring_regress.py를 고쳐서 바꾼다)

무거운 모델(D-GOP wav2vec2, Whisper)은 불러오지 않는다. API 층은 그 둘을 가짜로 바꾸고 점수 입력을 고정한다.
"""
import argparse
import datetime as _dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("LIPLAB_CONTENT_WARMUP", "0")
os.environ["ANTHROPIC_API_KEY"] = ""   # 회귀 점검은 유료 API를 부르지 않는다

# 채점 규칙의 의도(성질)를 적은 기존 검사. 스냅숏이 '무엇이' 바뀌었는지 보이면 이 검사는 '왜 틀렸는지' 보인다.
RELATED_TESTS = [
    "test_scoring.py", "test_scoring_v2.py", "test_choice_scoring.py", "test_typed_answer.py",
    "test_sentence_feedback.py", "test_engine.py", "test_phonetic_rules.py", "test_korean_numbers.py",
    "test_speak_mastery_gain.py", "test_speak_transcript_path.py", "test_speak_probe.py", "test_dgop.py",
    "test_dgop_tail_trim.py", "test_mastery_ewma.py",
]


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="채점 회귀 점검(O4)")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--layers", default="")
    ap.add_argument("--no-pytest", action="store_true")
    ap.add_argument("--report", default="")
    ap.add_argument("--max-rows", type=int, default=400)
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args()

    os.chdir(BACKEND)
    import scoring_regress as R

    layers = [x.strip() for x in a.layers.split(",") if x.strip()] or list(R.LAYERS)
    if a.quick:
        layers = [x for x in layers if x != "speak_api"]
    unknown = [x for x in layers if x not in R.LAYERS]
    if unknown:
        print(f"모르는 층: {unknown} (가능: {', '.join(R.LAYERS)})")
        return 2

    current = R.compute(layers)
    pinned_bad = R.check_pinned(current)
    golden = R.load_golden() if os.path.exists(R.GOLDEN_PATH) else {"meta": {}, "cases": {}}
    d = R.diff(golden.get("cases", {}), current)
    report = R.format_report(d, pinned_bad, golden.get("meta"), max_rows=a.max_rows)
    print(report)
    if a.report:
        with open(os.path.join(ROOT, a.report) if not os.path.isabs(a.report) else a.report, "w", encoding="utf-8") as f:
            f.write(report)

    changed = any(x["changed"] or x["added"] or x["removed"] for x in d.values())
    if a.update:
        if pinned_bad:
            print("고정 기대 위반이 있어 기준을 쓰지 않았다. 규칙 값을 바꾸는 것이면 backend/scoring_regress.py의 PINNED를 먼저 고친다.")
            return 1
        meta = {"updated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "commit": _git("rev-parse", "--short", "HEAD"),
                "branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "python": sys.version.split()[0],
                "layers": {k: len(v) for k, v in current.items()}}
        R.write_golden(current, meta, base=golden)
        print(f"기준을 다시 썼다: {os.path.relpath(R.GOLDEN_PATH, ROOT)} ({'바뀐 사례 있음' if changed else '내용 같음'})")
        return 0

    rc = 1 if (changed or pinned_bad) else 0
    if not a.quick and not a.no_pytest:
        tests = [t for t in RELATED_TESTS if os.path.exists(os.path.join(BACKEND, t))]
        print(f"관련 성질 검사 {len(tests)}개 파일을 돌린다.")
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=BACKEND)
        rc = rc or (1 if p.returncode else 0)
    print("회귀 점검: " + ("통과" if rc == 0 else "차이 또는 실패 있음(위 보고 참고)"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
