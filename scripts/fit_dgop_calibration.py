#!/usr/bin/env python
"""
D-GOP 표시용 점수 보정 앵커 맞추기 — 축 A A-4.

A-3이 남긴 한계 ②: 원점수는 변별력이 충분한데도 스케일이 압축돼 있다(깨끗한 발화 9.51/100).
학습자에게 보여줄 숫자를 따로 만들어야 한다. 여기서는 기준 발화 집합에 severity 0~4를 걸어
**severity별 원점수 중앙값**을 재고, 그것을 표시 목표(dgop.DISPLAY_TARGETS_BY_SEVERITY)에
잇는 앵커를 만들어 JSON으로 남긴다. 앱은 그 JSON을 읽어 점수를 편다(dgop_acoustic.load_calibration).

중앙값을 쓰는 이유: 평균은 발화 몇 개의 극단값에 끌려간다. 앵커가 흔들리면 같은 발음에
다른 점수가 나온다.

보정은 단조 증가 변환이라 A-3 변별력 지표(순위상관·AUC)는 보정 전후가 같다 —
이 스크립트는 변별력을 만들어내지 않고, 이미 있는 변별력을 읽을 수 있는 눈금에 옮긴다.

  # 배관 검증 — 모델·데이터셋 없이 CPU에서 (GPU를 켜기 전에 여기부터)
  python scripts/fit_dgop_calibration.py --smoke

  # 축 A 산출물로 앵커를 맞춘다(모델을 바꾸면 반드시 다시 돌린다)
  python scripts/fit_dgop_calibration.py \
    --aligner /workspace/ckpt/aligner --scorer /workspace/ckpt/scorer \
    --limit 50 --out backend/data/dgop_calibration.json
"""
import argparse
import datetime
import json
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "backend"))
sys.path.insert(0, _HERE)

import dgop as D                     # noqa: E402
import dgop_acoustic as DA           # noqa: E402
import deaf_speech_synthesis as DSS  # noqa: E402
import hf_audio                      # noqa: E402
# A-3 평가와 같은 채점 경로를 쓴다 — 앵커를 잰 방식과 합격을 판정한 방식이 어긋나면 안 된다.
import eval_dgop_discrimination as E  # noqa: E402

DEFAULT_OUT = os.path.join(_HERE, "..", "backend", "data", "dgop_calibration.json")


def _smoke_rows(n: int = 6):
    """
    --smoke용 합성 기준 집합. 모델도 데이터셋도 없이 배관(저하 증강 → 채점 루프 →
    중앙값 → 앵커 적합 → JSON 저장)만 확인한다.

    GPU 세션 한 번이 20분·$1이다. 인자 오타나 배관 오류를 Pod에서 처음 만나면 그 값을
    통째로 버린다 — 그래서 로컬에서 먼저 여기를 돌린다.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    return [{"audio": rng.standard_normal(16000).astype(np.float32) * 0.1,
             "text": "안녕하세요"} for _ in range(n)]


def _smoke_score(wave, text, aligner_id, scorer_id, _sev_of=None):
    """
    합성 채점기 — 저하 강도에 따라 대략 기하급수로 떨어지는 원점수를 흉내 낸다
    (A-3 실측 9.51 → 2.74 → 1.49 → 0.61 → 0.30과 같은 모양).
    실제 채점 경로는 GPU에서 E.score_one이 맡는다.
    """
    import numpy as np
    energy = float(np.abs(wave).mean())
    return 10.0 * energy / 0.08, None, 1.0


def measure(ds, severities, aligner, scorer, score_one, rng):
    """severity별 원점수를 모은다. 실측 루프를 main에서 떼어내 --smoke가 같은 경로를 탄다."""
    raws = {s: [] for s in severities}
    for i, row in enumerate(ds):
        clean = hf_audio.to_waveform(row["audio"])
        for sev in severities:
            wave = clean if sev == 0 else DSS.simulate_deaf_speech(
                clean, E.SAMPLE_RATE, sev, rng=rng)
            dg, _naive, _ar = score_one(wave, row["text"], aligner, scorer)
            if dg is not None:
                raws[sev].append(dg)
        if (i + 1) % 10 == 0:
            print(f"  … {i + 1}/{len(ds)}")
    return raws


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aligner", default=DA.DEFAULT_MODEL_ID)
    ap.add_argument("--scorer", default=None, help="생략 시 정렬기와 동일(단일 모델 동작)")
    ap.add_argument("--limit", type=int, default=50, help="기준 발화 수")
    ap.add_argument("--out", default=DEFAULT_OUT, help="앵커 JSON 저장 경로")
    ap.add_argument("--smoke", action="store_true",
                    help="합성 발화·합성 채점기로 배관만 검증(모델·데이터셋 불필요)")
    args = ap.parse_args()

    if args.smoke:
        if not DSS.HAS_SYNTHESIS:
            print("librosa 미설치 — backend/requirements-ml.txt 설치 필요", file=sys.stderr)
            return 2
        ds = _smoke_rows()
        score_one = _smoke_score
    else:
        if not DA.HAS_ACOUSTIC or not DSS.HAS_SYNTHESIS:
            print("torch/transformers/librosa 미설치 — backend/requirements-ml.txt 설치 필요",
                  file=sys.stderr)
            return 2
        import datasets as ds_lib
        from datasets import load_dataset

        ds = load_dataset(E.DATASET, split="test").cast_column(
            "audio", ds_lib.Audio(sampling_rate=E.SAMPLE_RATE))
        ds = ds.select(range(min(args.limit, len(ds))))
        score_one = E.score_one

    import numpy as np
    # A-3과 같은 시드 — 같은 저하 표본에서 재고 판정한다.
    rng = np.random.default_rng(0)

    print(f"정렬기 {args.aligner}\n채점기 {args.scorer or args.aligner}\n"
          f"기준 발화 {len(ds)}건 × severity {E.SEVERITIES}"
          f"{'  [smoke — 합성 채점기]' if args.smoke else ''}\n")
    raws = measure(ds, E.SEVERITIES, args.aligner, args.scorer, score_one, rng)

    if any(not raws[s] for s in E.SEVERITIES):
        empty = [s for s in E.SEVERITIES if not raws[s]]
        print(f"\n채점된 발화가 없는 severity가 있습니다: {empty} — 앵커를 만들 수 없습니다",
              file=sys.stderr)
        return 1

    medians = [round(statistics.median(raws[s]), 4) for s in E.SEVERITIES]
    print(f"severity별 원점수 중앙값: {medians}")

    # 앵커 적합이 실패해도 실측값은 반드시 남긴다 — GPU 20분을 다시 태우지 않기 위함이다.
    try:
        cal = D.fit_calibration(
            medians,
            source=f"{os.path.basename(args.scorer or args.aligner)}/"
                   f"{datetime.date.today().isoformat()} {E.DATASET} test {len(ds)}발화 severity 중앙값")
    except ValueError as e:
        dump = os.path.splitext(args.out)[0] + ".medians.json"
        os.makedirs(os.path.dirname(os.path.abspath(dump)), exist_ok=True)
        with open(dump, "w", encoding="utf-8") as f:
            json.dump({"severity_medians": medians, "error": str(e),
                       "aligner": args.aligner, "scorer": args.scorer or args.aligner},
                      f, ensure_ascii=False, indent=2)
        print(f"\n앵커를 만들지 못했습니다: {e}\n"
              f"실측 중앙값은 {dump}에 남겼습니다 — 다시 측정할 필요는 없습니다.",
              file=sys.stderr)
        return 1

    cal.update({
        "fitted_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "aligner": args.aligner,
        "scorer": args.scorer or args.aligner,
        "dataset": "smoke(합성)" if args.smoke else E.DATASET,
        "utterances": len(ds),
        "severity_medians": medians,
        "display_targets": D.DISPLAY_TARGETS_BY_SEVERITY[:len(medians)],
    })

    print("\n severity |  n  | 원점수 중앙값 | 보정 점수 | 목표")
    print(" ---------+-----+---------------+-----------+------")
    for s, med in zip(E.SEVERITIES, medians):
        print(f"     {s}    | {len(raws[s]):3d} |    {med:8.3f}   |"
              f"   {D.calibrate_score(med, cal):5.1f}   | {D.DISPLAY_TARGETS_BY_SEVERITY[s]:5.1f}")

    if cal["dropped_severities"]:
        print(f"\n⚠️  원점수가 severity를 거스른 구간이 있어 앵커에서 제외했습니다: "
              f"{cal['dropped_severities']} — 이 모델은 그 구간을 구별하지 못한다는 뜻이다.")

    if args.smoke:
        print("\n[smoke] 배관 정상 — 실제 앵커는 체크포인트로 다시 돌려야 한다. 저장하지 않는다.")
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n앵커 {len(cal['anchors'])}개를 저장했습니다 → {args.out}")
    print("앱에 연결: DGOP_CALIBRATION=<이 경로> (기본 경로에 두면 환경변수 없이도 읽는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
