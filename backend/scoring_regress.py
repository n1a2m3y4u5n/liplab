"""
채점 회귀 점검(계획 O4, docs/master-plan-2026-10.md 트랙 O, 사용법 docs/scoring-regression-2026-10.md).

네 층의 대표 입력과 그때의 출력을 고정해 두고(기준 파일 scoring_regress_golden.json), 코드를 고친 뒤 같은 입력의 출력이
달라졌는지 사람이 읽을 수 있는 차이 보고로 낸다.

  lipread   독화 이해 채점(scoring.calculate_score 입모양 v2·발음 전사 경로, viseme_confusions)
  dictation 받아쓰기 낱말 판정(sentence_feedback.consonant_feedback, listen_curriculum.word_score)
  speak     말하기 판정 규칙(단계 상수, score_attempt, speak_hold, D-GOP 보정 앵커, 이동 평균 숙달, 개인 향상 경로, 확인 낱말)
  engine    발음 규칙 엔진(engine.to_pronounced_syllables 입모양·소리 경로, text_to_visemes)
  speak_api 말하기·독화 채점 API 경로(/api/speak/assess, /api/progress). D-GOP 음향 모델과 Whisper는 가짜로 바꿔 점수 입력을 고정한다

D-GOP 음향 모델(wav2vec2)은 불러오지 않는다. 음소별 D-GOP 값이나 보정된 문장 점수를 입력으로 고정하고, 그 뒤의 규칙 층(문장 집계,
보정 앵커, 합격선 65, 판정 보류 ±SEM, 숙달 68)만 본다.

검사는 두 겹이다.
  1) 기준 파일과의 차이(스냅숏). 의도한 변경이면 scripts/scoring_regress.py --update로 기준을 다시 쓴다.
  2) 고정 기대(PINNED). 규칙 문서에 적힌 값(합격선 65에서 합격, ±7.5 경계 등)이라 --update로 바뀌지 않는다. 바꾸려면 이 파일을 고친다.

순수 함수만 부르는 층은 0.5초 안팎, speak_api 층은 임시 DB를 쓰는 별도 프로세스라 10초 안팎 걸린다.
"""
import asyncio
import json
import math
import os
import subprocess
import sys
import tempfile
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_PATH = os.path.join(HERE, "scoring_regress_golden.json")
LAYERS = ("lipread", "dictation", "speak", "engine", "speak_api")
LAYER_KO = {
    "lipread": "독화 이해 채점",
    "dictation": "받아쓰기 낱말 판정",
    "speak": "말하기 판정 규칙",
    "engine": "발음 규칙 엔진",
    "speak_api": "채점 API 경로(모의 D-GOP·전사)",
}
_TOL = 1e-6   # 숫자는 이만큼 안의 차이를 같다고 본다(출력은 이미 소수 둘째·넷째 자리에서 반올림된다)


# ─────────────────────────────── 1. 독화 이해 채점 ───────────────────────────────
# (정답, 답). 앞 묶음은 test_scoring_v2.py·test_sentence_feedback.py의 성질 검사 입력, 뒤 묶음은 그 사이를 메우는 대표 사례다.
LIPREAD_PAIRS: List[Tuple[str, str]] = [
    ("물 좀 주세요", "물 좀 주세요"),
    ("굳이 가야 해요", "구지 가야 해요"),
    ("케이크가 다 팔렸대요", "다음 역에서 내리세요"),
    ("영수증 드릴까요", "영수증 드릴까요 몸조리 잘하세요"),
    ("바다가 넓어요", "마다가 넓어요"),
    ("바다가 넓어요", "가다가 넓어요"),
    ("오늘 저녁에 같이 밥 먹을래요", "오늘 저녁에 밥 먹을래요"),
    ("오늘 저녁에 같이 밥 먹을래요", "오늘 밥 먹을래요"),
    ("물 좀 주세요", "   "),
    ("옷 입어", "옷　입어"),        # 전각 공백
    ("옷 입어", "옷 입어"),    # 줄 바꿈 없는 공백
    ("옷 입어", "옷,입어"),
    ("물 좀 주세요", unicodedata.normalize("NFD", "물 좀 주세요")),
    ("같이 가요", "가치 가요"),
    ("학교에 가요", "학꾜에 가요"),
    ("안녕하세요", "안녕하세여"),
    ("고맙습니다", "감사합니다"),
    ("세 시에 만나요", "3시에 만나요"),
    ("창문 좀 열어 주세요", "창문 열어 주세요"),
    ("빨간 꽃잎이 떨어졌어요", "빨간 꼰니피 떨어져써요"),
    ("내일 다시 올게요", "내일다시 올께요"),
    ("버스", "퍼스"),
    ("아", "바"),
    ("책", "채"),
    ("밥 먹었어요", "밥 먹었어요 정말 맛있어요"),
    ("병원에 가야 해요", "병원 가야 해요"),
]

# (목표 낱말, 고른 보기): 1·2단계 보기 혼동 설명
CONFUSION_PAIRS: List[Tuple[str, str]] = [
    ("바다", "마다"), ("달", "탈"), ("아이", "바이"), ("닭", "달"), ("가다", "다다"), ("사과", "자과"), ("오리", "우리"),
]


def _lipread_layer() -> Dict[str, Any]:
    from scoring import calculate_score, viseme_confusions
    out: Dict[str, Any] = {}
    for correct, answer in LIPREAD_PAIRS:
        for mode in ("visual", "phonological"):
            r = asyncio.run(calculate_score(correct, answer, mode=mode))
            out[f"{mode} | {correct} ← {answer!r}"] = {
                "score": r["score"],
                "precision": r.get("precision"),
                "recall": r.get("recall"),
                "phoneme_accuracy": r["phoneme_accuracy"],
                "viseme_errors": r["viseme_errors"],
                "feedback_level": (r.get("feedback") or {}).get("level"),
                "specific_tip": (r.get("feedback") or {}).get("specific_tip"),
            }
    for target, chosen in CONFUSION_PAIRS:
        out[f"confusion | {target} ← {chosen}"] = [
            f"{c['position']} {c['target']}→{c['read']} viseme={c['viseme']} {c['viseme_name_ko']} same={c['same_viseme']}"
            for c in viseme_confusions(target, chosen)]
    return out


# ─────────────────────────────── 2. 받아쓰기 낱말 판정 ───────────────────────────────
DICTATION_PAIRS: List[Tuple[str, str]] = [
    ("물 좀 주세요.", "물 좀 주세요"),
    ("물 좀 주세요", "불 좀 주세요"),
    ("같이 가요", "가치 가요"),
    ("오늘 날씨 좋네요", "좋네요 오늘"),
    ("오늘 날씨 좋네요", ""),
    # 소리로 가르지 못하는 모음 표기
    ("물 좀 주세요", "물 좀 주새요"), ("저는 학생이에요", "저는 학생이예요"), ("이건 의자예요", "이건 의자에요"),
    ("아니에요", "아니예요"), ("안 돼요", "안 되요"), ("계속 가요", "게속 가요"), ("우리의 집", "우리이 집"),
    # 낱말 첫머리 모음은 갈린다
    ("예", "에"), ("의사", "이사"), ("물 좀 주세요", "물 좀 주시요"),
    # 띄어쓰기 무시
    ("가을 산에서 밤을 주웠어", "가을산에서 밤을 주웠어"), ("물 좀 주세요", "물좀 주세요"),
    ("내일 다시 올게요", "내일다시 올께요"), ("같이 갈 수 있어요", "같이 갈수 있어요"),
    ("책을 읽고 있어요", "책을 읽고있어요"), ("국물이 짜요", "궁물이 짜요"),
    # 순서·빠진 낱말
    ("물 좀 주세요", "좀 물 주세요"), ("오늘 날씨가 좋아요", "날씨가"),
    # 숫자
    ("여섯 시 오십 분까지 극장 앞으로 와", "6시 50분까지 극장 앞으로 와"), ("회의는 삼 층 큰 방에서 해요", "회의는 3층 큰 방에서 해요"),
    ("부산행 기차는 칠 번 타는 곳에서 출발합니다", "부산행 기차는 7번 타는 곳에서 출발합니다"),
    ("하루 세 번 드세요", "하루 3번 드세요"), ("물 한 잔 주세요", "물 1잔 주세요"), ("오 분 빨라요", "6분 빨라요"),
    # 경계 사례(지금 동작을 기록)
    ("갈비 먹자", "갈삐 먹자"), ("커피 두 잔 주세요", "커피 두잔 주세요"), ("지하철 이 호선", "지하철 2호선"),
    ("케이티엑스 타요", "KTX 타요"), ("병원에 가요", "병원에 가여"), ("손을 씻어요", "소늘 씨서요"),
]


def _dictation_layer() -> Dict[str, Any]:
    from listen_curriculum import word_score
    out: Dict[str, Any] = {}
    for correct, answer in DICTATION_PAIRS:
        r = word_score(correct, answer)
        fb = r["feedback"]
        out[f"{correct} ← {answer!r}"] = {
            "proportion": r["proportion"],
            "correct_words": fb["correct_words"],
            "total_words": fb["total_words"],
            "words": " | ".join(("○ " + w["text"]) if w["correct"] else ("× " + "".join(w["skeleton"] or []))
                                for w in fb["words"]),
        }
    return out


# ─────────────────────────────── 3. 말하기 판정 규칙 ───────────────────────────────
HOLD_SCORES = [50.0, 57.5, 57.6, 60.0, 64.9, 65.0, 68.0, 72.4, 72.5, 80.0]
ATTEMPT_SCORES = [0.0, 49.9, 50.0, 57.5, 64.9, 65.0, 68.0, 72.5, 90.0]
# 음소별 D-GOP(0~1) 입력. 음향 모델 대신 이 값을 고정해 문장 집계·보정·합격 판정만 본다.
DGOP_PHONE_SETS = {
    "모두 0.95": [0.95] * 8,
    "모두 0.80": [0.80] * 8,
    "모두 0.60": [0.60] * 8,
    "모두 0.40": [0.40] * 8,
    "모두 0.10": [0.10] * 8,
    "섞임(약한 소리 둘)": [0.95, 0.9, 0.9, 0.2, 0.85, 0.9, 0.1, 0.95],
    "한 소리만 0": [0.9] * 7 + [0.0],
    "빈 목록": [],
}
CAL_RAW_GRID = [0.0, 1.0, 3.8, 10.0, 25.0, 40.0, 50.9, 60.0, 70.0, 82.45, 90.0, 100.0]
# 시간순 합격(1)·불합격(0). 이동 평균 숙달(_ewma_mastery, a 0.08)과 문턱 68의 도달 시점을 본다.
EWMA_SEQS = {
    "모두 합격": [1] * 30,
    "합격 73%(11번 중 8번)": [1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1] * 3,
    "번갈아": [1, 0] * 15,
    "처음 5번 불합격 뒤 합격": [0] * 5 + [1] * 25,
    "합격 60%": [1, 1, 0, 1, 0] * 6,
}
GAIN_SEQS = {
    "19번: 시도 부족": [40] * 10 + [60] * 9,
    "+20": [40] * 10 + [60] * 10,
    "+12: 향상 부족": [40] * 10 + [52] * 10,
    "처음 중앙값 40 → 58": [30, 40, 50] * 4 + [58] * 10,
    "늘 40": [40] * 30,
    "+20이지만 최근 40": [20] * 10 + [40] * 10,
    "기준선 0, 늘 30": [0] * 10 + [30] * 10,
    "하한 50에 딱 닿음": [30] * 10 + [50] * 10,
}
INTONATION_METRICS = {
    "끝 올림 +3반음": {"loudness": 50, "pitch_ref": 200.0, "pitch_final": 238.0},
    "끝 내림 −3반음": {"loudness": 50, "pitch_ref": 200.0, "pitch_final": 168.2},
    "평평 +1반음": {"loudness": 50, "pitch_ref": 200.0, "pitch_final": 211.9},
    "예전 클라이언트(시작·끝만) 올림": {"loudness": 50, "pitch_start": 180.0, "pitch_end": 220.0},
}
PROSODY_CASES = [
    ("loud", {"loudness": 65}), ("loud", {"loudness": 40}),
    ("soft", {"loudness": 30}), ("soft", {"loudness": 55}), ("soft", {"loudness": 5}),
    ("long", {"loudness": 40, "voiced_duration": 2.3}), ("long", {"loudness": 40, "duration": 3.0, "voiced_duration": 1.0}),
    ("rise", {"pitch_start": 180.0, "pitch_end": 205.0, "pitch_frames": 12}),
    ("rise", {"pitch_start": 180.0, "pitch_end": 190.0, "pitch_frames": 12}),
    ("fall", {"pitch_start": 220.0, "pitch_end": 190.0, "pitch_frames": 12}),
    ("rise", {"pitch_start": 180.0, "pitch_end": 240.0, "pitch_frames": 3}),
]
VOICING_CASES = [{"loudness": 40, "voiced_duration": 1.5}, {"loudness": 40, "voiced_duration": 0.8},
                 {"loudness": 15, "voiced_duration": 2.5}]
# 전사 경로(모음·자음 단계의 초점 자모, 소리 없음)
TRANSCRIPT_CASES = [
    (2, "아", "이", 50.15, {"loudness": 50, "voiced_duration": 0.6}),
    (2, "아", "아.", 100.0, {"loudness": 50, "voiced_duration": 0.6}),
    (2, "애", "에", 100.0, {"loudness": 50, "voiced_duration": 0.6}),
    (3, "풀", "불", 91.0, {"loudness": 50, "voiced_duration": 0.6}),
    (3, "달", "달", 100.0, {"loudness": 50, "voiced_duration": 0.6}),
    (3, "달", "다", 80.0, {"loudness": 50, "voiced_duration": 0.6}),
    (2, "아", "시청해 주셔서 감사합니다.", 0.0, {"loudness": 0, "voiced_duration": 0}),
    (4, "사과", "사과", 100.0, {"loudness": 50, "voiced_duration": 0.6}),
]


def _calibrations() -> Dict[str, Dict]:
    """보정 앵커들. dgop_acoustic.load_calibration은 torch를 함께 불러오므로 같은 파일을 직접 읽는다(파일이 깨졌으면 내장값과 같은 규칙)."""
    import dgop
    cals = {"내장 기본값(축 A 9/9)": dgop.DEFAULT_CALIBRATION}
    for name, fn in (("dgop_calibration.json(팀원 채점기)", "dgop_calibration.json"),
                     ("dgop_calibration_kresnik.json(공개 kresnik)", "dgop_calibration_kresnik.json"),
                     ("dgop_calibration_ours.json(배포 자체 채점기)", "dgop_calibration_ours.json")):
        p = os.path.join(HERE, "data", fn)
        try:
            with open(p, encoding="utf-8") as f:
                c = json.load(f)
            cals[name] = c if c.get("anchors") else dgop.DEFAULT_CALIBRATION
        except Exception:
            cals[name] = None
    return cals


def _speak_layer() -> Dict[str, Any]:
    import dgop
    import speak_curriculum as sc
    from main import _SPEAK_SEM, _STAGE12_EWMA_ALPHA, _STAGE3_MASTERY, _STAGE3_PASS, _ewma_mastery, speak_hold
    out: Dict[str, Any] = {}

    # 3-1 단계 상수
    for s in sc.SPEAK_STAGES:
        out[f"상수 | 단계 {s['stage']} {s['title']}"] = {
            "mode": s["mode"], "pass": s.get("pass"), "mastery": s["mastery"], "min_attempts": s["min_attempts"],
            "gain": s.get("gain"), "probe": s.get("probe"), "items": len(s["items"])}
    out["상수 | 판정·이동 평균"] = {
        "_SPEAK_SEM": _SPEAK_SEM, "EWMA_alpha": _STAGE12_EWMA_ALPHA, "STAGE3_PASS": _STAGE3_PASS,
        "STAGE3_MASTERY": _STAGE3_MASTERY, "SENTENCE_DIR_ST": sc.SENTENCE_DIR_ST, "RISE_FALL_ST": sc.RISE_FALL_ST,
        "PROBE_DGOP_MIN": getattr(sc, "PROBE_DGOP_MIN", None)}

    # 3-2 판정 보류(합격선 ± SEM)
    for mode, stage_pass in (("word", 65.0), ("sentence", 65.0), ("phoneme", 50.0)):
        grid = {}
        for s in HOLD_SCORES:
            grid[f"{s:g}"] = speak_hold(s, stage_pass, mode, s >= stage_pass)
        out[f"판정 보류 | {mode} 합격선 {stage_pass:g}"] = grid
    out["판정 보류 | 확인 낱말·합격선 없음"] = {
        "probe": speak_hold(65, 65, "sentence", True, is_probe=True),
        "no_pass": speak_hold(65, None, "sentence", True),
        "voicing": speak_hold(65, 65, "voicing", True)}

    # 3-3 D-GOP 경로 문장·낱말 단계 판정(transcript None, 보정된 점수 입력)
    for stage in (2, 3, 4, 5):
        stg = sc.get_stage(stage)
        tgt = stg["items"][0]["target"]
        res = {}
        for s in ATTEMPT_SCORES:
            score, passed, note = sc.score_attempt(stage, tgt, None, {"loudness": 50}, None, s)
            res[f"{s:g}"] = {"score": score, "passed": passed,
                             "hold": speak_hold(score, stg.get("pass"), stg["mode"], passed), "note": note}
        out[f"D-GOP 판정 | 단계 {stage} '{tgt}'"] = res

    # 3-4 문장 억양 안내(문장 단계, 점수 70 고정)
    for target in ("밥 먹었어요.", "밥 먹었어요?", "어디 가요?", "새 문장이에요?"):
        res = {}
        for name, m in INTONATION_METRICS.items():
            score, passed, note = sc.score_attempt(5, target, None, m, None, 70.0)
            res[name] = {"passed": passed, "note": note}
        out[f"억양 | {target}"] = {"expected": sc.expected_intonation(target), **res}

    # 3-5 발성·운율
    for m in VOICING_CASES:
        score, passed, note = sc.score_attempt(0, "아", None, m)
        out[f"발성 | {json.dumps(m, ensure_ascii=False)}"] = {"score": score, "passed": passed, "note": note}
    for drill, m in PROSODY_CASES:
        score, passed, note = sc.score_attempt(1, "아", None, m, drill)
        out[f"운율 | {drill} {json.dumps(m, ensure_ascii=False)}"] = {"score": score, "passed": passed, "note": note}

    # 3-6 전사 경로(초점 자모·소리 없음)
    for stage, tgt, heard, sim, m in TRANSCRIPT_CASES:
        score, passed, note = sc.score_attempt(stage, tgt, heard, m, None, sim)
        out[f"전사 판정 | 단계 {stage} {tgt} ← {heard!r} sim {sim:g}"] = {"score": score, "passed": passed, "note": note}

    # 3-7 D-GOP 문장 집계와 보정 앵커(음소 값 고정 → 원점수 → 표시 점수 → 4·5단계 판정)
    cals = _calibrations()
    for name, vals in DGOP_PHONE_SETS.items():
        per_phone = [dgop.dgop_phone(v, [v, 1 - v]) for v in vals]
        agg = dgop.sentence_dgop(per_phone)
        row = {"raw": agg["score"], "uncertainty": agg["uncertainty"]}
        for cname, cal in cals.items():
            disp = dgop.calibrate_score(agg["score"], cal) if cal else None
            if disp is None:
                row[cname] = None
                continue
            _, passed, _ = sc.score_attempt(5, "밥 먹었어요.", None, {"loudness": 50}, None, disp)
            row[cname] = {"score": disp, "passed": passed, "hold": speak_hold(disp, 65.0, "sentence", passed)}
        out[f"D-GOP 집계 | {name}"] = row
    for cname, cal in cals.items():
        out[f"보정 앵커 | {cname}"] = (
            {f"{r:g}": dgop.calibrate_score(r, cal) for r in CAL_RAW_GRID} if cal else None)

    # 3-8 이동 평균 숙달(4·5단계 문턱 68, 최소 시도 8·6)
    for name, seq in EWMA_SEQS.items():
        est, traj, reached = 0.0, [], {}
        for n, ok in enumerate(seq):
            est = _ewma_mastery(est, n, bool(ok))
            traj.append(round(est, 2))
            for stage in (4, 5):
                stg = sc.get_stage(stage)
                if stage not in reached and n + 1 >= stg["min_attempts"] and est >= stg["mastery"]:
                    reached[stage] = n + 1
        out[f"이동 평균 숙달 | {name}"] = {
            "after_5": traj[4], "after_10": traj[9], "after_20": traj[19], "final": traj[-1],
            "reach_68_stage4_at": reached.get(4), "reach_68_stage5_at": reached.get(5)}

    # 3-9 개인 향상 경로·소리 잡힌 시도·확인 낱말 창
    g = sc.get_stage(4)["gain"]
    for name, seq in GAIN_SEQS.items():
        out[f"향상 경로 | {name}"] = {"no_floor": sc.gain_mastered(seq, g), "floor_65": sc.gain_mastered(seq, g, 65.0)}
    out["향상 경로 | gain 없음·점수 없음"] = {"no_gain": sc.gain_mastered([40] * 30, None),
                                       "none_scores": sc.gain_mastered([None] * 25, g)}
    out["소리 잡힌 시도"] = {
        "D-GOP 크기 50 점수 30": sc.voiced_attempt(50, None, 30), "전사 크기 50 '사과' 80": sc.voiced_attempt(50, "사과", 80),
        "크기 0": sc.voiced_attempt(0, "사과", 80), "크기 없음": sc.voiced_attempt(None, None, 40),
        "전사 빈 문자열 0점": sc.voiced_attempt(50, "", 0), "전사 빈 문자열 5점": sc.voiced_attempt(50, "", 5)}
    probe_cfg = sc.get_stage(2)["probe"]
    out["확인 낱말 창(3번 중 2번)"] = {
        "".join("o" if p else "x" for p in ps): sc.probes_ok(ps, probe_cfg)
        for ps in ([True, True], [True, False, True], [False, False, True], [True, True, False, False], [False] * 3, [])}
    return out


# ─────────────────────────────── 4. 발음 규칙 엔진 ───────────────────────────────
ENGINE_WORDS = [
    # test_engine.py CASES·test_phonetic_rules.py와 같은 낱말
    "값", "닭", "앉", "아이", "굳이", "같이", "밥을", "옷이", "꽃이", "한국어", "닭이", "좋아", "좋다", "많다", "놓고", "입학",
    "국화", "축하", "닫히다", "강아지", "많이", "싫어", "괜찮아요", "꽃", "몇 시", "옷", "앞", "밖", "솥", "국물", "닫는", "밥물",
    "밭만", "신라", "설날", "종로", "백리", "학교", "있다", "먹었다", "안녕하세요", "붙여", "밥 먹자", "좋다!",
    # ㄴ 첨가·-ㄹ 뒤 된소리
    "꽃잎", "담요", "색연필", "나뭇잎", "서울역", "유럽여행을", "집안일", "식용유", "해야 할 일이", "빨간 꽃잎이", "할게요",
    "할 수 있어", "갈 거야",
    # 그 밖의 대표 낱말·문장
    "읽고", "넓어요", "흙이", "닳는", "끓이다", "맑다", "밟다", "의사", "희망", "늴리리", "밥 먹었어요", "같이 갈래요?",
    "물 좀 주세요", "3시 30분", "5,000원", "괜찮으세요?",
]
VISEME_TEXTS = ["밥 먹었어요", "와", "의", "뭐", "꽃잎", "물 좀 주세요", "안녕하세요"]

_ONS = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_NUC = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_COD = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")


def _compose(tokens) -> str:
    """[초, 중, 종] 열을 읽을 수 있는 음절 글자로(무음 초성은 ㅇ). 조합할 수 없는 자모는 [초중종]으로 남긴다."""
    out = []
    for t in tokens:
        if not isinstance(t, (list, tuple)):
            out.append(t)
            continue
        try:
            out.append(chr(0xAC00 + _ONS.index(t[0] or "ㅇ") * 588 + _NUC.index(t[1]) * 28 + _COD.index(t[2])))
        except ValueError:
            out.append("[" + "".join(t) + "]")
    return "".join(out)


def _engine_layer() -> Dict[str, Any]:
    from engine import text_to_visemes, to_pronounced_syllables
    out: Dict[str, Any] = {}
    for w in ENGINE_WORDS:
        out[f"발음 | {w}"] = {
            "입모양 경로": _compose(to_pronounced_syllables(w)),
            "소리 경로(phonetic)": _compose(to_pronounced_syllables(w, phonetic=True)),
            "소리+ㅎ탈락+ㄴ첨가": _compose(to_pronounced_syllables(w, phonetic=True, h_delete=True, n_insert=True)),
            "입모양+ㄹ뒤 된소리": _compose(to_pronounced_syllables(w, l_tensify=True)),
        }
    for t in VISEME_TEXTS:
        frames = asyncio.run(text_to_visemes(t))
        out[f"입모양 프레임 | {t}"] = {
            "visemes": " ".join(str(f["viseme"]) for f in frames),
            "duration_ms": sum(int(f.get("duration_ms") or 0) for f in frames),
            "frames": len(frames)}
    return out


# ─────────────────────────────── 5. 채점 API 경로 ───────────────────────────────
# 별도 프로세스·임시 DB에서 돈다(다른 API 통합 테스트와 같은 방식). D-GOP assess_text·Whisper·LLM은 가짜다.
SPEAK5_SCORES = [70.0, 64.9, 65.0, 57.5, 57.6, 72.4, 72.5, 80.0, 90.0, 68.0, 66.0, 75.0]
SPEAK4_GAIN_SCORES = [40.0] * 10 + [60.0] * 10
_API_SCENARIO = r'''
import json, sys
from fastapi.testclient import TestClient
import dgop_acoustic, llm_service, ratelimit, speak_service
import main

cases = json.loads(sys.argv[1])
fixed = {"score": None}
heard = {"text": ""}

def fake_assess(data, target, aligner_id=None, scorer_id=None, **kw):
    if fixed["score"] is None:
        return {"score": None, "raw_score": None, "uncertainty": 1.0, "phones": []}
    s = float(fixed["score"])
    phones = [{"token": "o:ㅂ", "t0": 0.0, "t1": 0.2, "dgop": round(s / 100, 3), "aligned": True, "scorable": True}]
    return {"score": s, "raw_score": s, "uncertainty": 0.3, "phones": phones, "rate": None}

async def fake_transcribe(data):
    return heard["text"]

class _NoLLM:
    class messages:
        @staticmethod
        async def create(*a, **k):
            raise RuntimeError("no network in regression")

dgop_acoustic.HAS_ACOUSTIC = True
dgop_acoustic.assess_text = fake_assess
speak_service.transcribe = fake_transcribe
speak_service.is_available = lambda: True
llm_service.anthropic_client = _NoLLM

def user(c, tag):
    ratelimit._hits.clear()
    r = c.post("/api/auth/register", json={"email": f"{tag}@example.com", "username": tag, "password": "pw-123456",
                                           "agree_terms": True, "age_confirmed": True})
    return {"Authorization": "Bearer " + r.json()["access_token"]}

def assess(c, h, target, stage, dgop_score=None, text="", loud=50, vd=0.8, extra=None):
    ratelimit._hits.clear()
    fixed["score"], heard["text"] = dgop_score, text
    data = {"target": target, "stage": str(stage), "loudness": str(loud), "duration": "1.0", "voiced_duration": str(vd)}
    data.update(extra or {})
    res = c.post("/api/speak/assess", headers=h, files={"audio": ("a.webm", b"\x00" * 2048, "audio/webm")}, data=data)
    b = res.json()
    p = b.get("progress") or {}
    return {"status": res.status_code, "method": b.get("assessment_method"), "score": b.get("score"), "passed": b.get("passed"),
            "pass_score": b.get("pass_score"), "hold": b.get("hold"), "note": b.get("note"), "transcript": b.get("transcript"),
            "attempts": p.get("attempts"), "mastery_score": p.get("mastery_score"), "mastered": p.get("mastered")}

out = {}
with TestClient(main.app) as c:
    h = user(c, "rg5")
    for i, s in enumerate(cases["speak5"]):
        out[f"문장 단계 D-GOP | {i + 1:02d}번째 {s:g}점"] = assess(c, h, "밥 먹었어요.", 5, dgop_score=s,
                                                             extra={"pitch_ref": "200", "pitch_final": "168"})
    h = user(c, "rg4")
    for i, s in enumerate(cases["speak4"]):
        r = assess(c, h, "사과", 4, dgop_score=s)
        if i in (9, 18, 19):
            out[f"낱말 단계 향상 경로 | {i + 1:02d}번째 {s:g}점"] = r
    h = user(c, "rgt")
    for stage, target, text, loud, vd in [(2, "아", "이", 50, 0.6), (2, "아", "아.", 50, 0.6), (3, "풀", "불", 50, 0.6),
                                          (3, "풀", "풀", 50, 0.6), (2, "아", "시청해 주셔서 감사합니다.", 0, 0),
                                          (5, "밥 먹었어요.", "밥 먹었어요", 50, 1.2), (4, "사과", "사가", 50, 0.8)]:
        out[f"전사 경로 | 단계 {stage} {target} ← {text!r}"] = assess(c, h, target, stage, dgop_score=None, text=text,
                                                                  loud=loud, vd=vd)
    h = user(c, "rgp")
    for sentence, answer, mode in [("물 좀 주세요.", "물 좀 주세요", "typed"), ("물 좀 주세요.", "불 좀 주세요", "typed"),
                                   ("오늘 저녁에 같이 밥 먹을래요", "오늘 밥 먹을래요", "typed"),
                                   ("케이크가 다 팔렸대요", "다음 역에서 내리세요", "typed"),
                                   ("물 좀 주세요.", "물 좀 주세요!", "choice"), ("물 좀 주세요.", "불 좀 주세요", "choice")]:
        ratelimit._hits.clear()
        body = {"scenario_id": "regress", "sentence": sentence, "user_answer": answer, "answer_mode": mode,
                "time_spent_seconds": 5, "situation": "식당", "difficulty_level": 1}
        b = c.post("/api/progress", json=body, headers=h).json()
        wf = b.get("word_feedback")
        out[f"독화 진행 | {mode} {sentence} ← {answer}"] = {
            "score": b.get("score"), "passed": b.get("passed"), "level": (b.get("feedback") or {}).get("level"),
            "word_feedback": None if wf is None else f"{wf['correct_words']}/{wf['total_words']}"}
print("RESULT " + json.dumps(out, ensure_ascii=False))
'''


def _speak_api_layer() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{d}/t.db", PYTHONDONTWRITEBYTECODE="1",
                   DGOP_ALIGNER_ID="fake/aligner", ANTHROPIC_API_KEY="", LIPLAB_AV_FUSION="0",
                   LIPLAB_CONTENT_WARMUP="0", LIPLAB_WARMUP="0")
        env.pop("DGOP_CALIBRATION", None)
        arg = json.dumps({"speak5": SPEAK5_SCORES, "speak4": SPEAK4_GAIN_SCORES})
        p = subprocess.run([sys.executable, "-c", _API_SCENARIO, arg], cwd=HERE, env=env,
                           capture_output=True, text=True, timeout=300)
    line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), None)
    if not line:
        raise RuntimeError(f"API 시나리오 실패:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}")
    return json.loads(line[len("RESULT "):])


_BUILDERS = {"lipread": _lipread_layer, "dictation": _dictation_layer, "speak": _speak_layer,
             "engine": _engine_layer, "speak_api": _speak_api_layer}


def compute(layers: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """층별 {사례 id: 출력}. JSON으로 한 번 왕복해 기준 파일과 같은 모양(튜플 → 목록, 키 → 문자열)으로 맞춘다."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    res = {name: _BUILDERS[name]() for name in (layers or LAYERS)}
    return json.loads(json.dumps(res, ensure_ascii=False))


# ─────────────────────────────── 고정 기대(PINNED) ───────────────────────────────
# (층, 사례 id, 점 경로, 기대값). 규칙 문서·결정에 적힌 값이라 기준 파일을 다시 써도 바뀌지 않는다.
# test_speak_hold.py와 test_speak_mastery_gain.py의 순수 함수 검사를 여기로 옮겼다(10/9).
PINNED: List[Tuple[str, str, str, Any]] = [
    # 단계 상수(docs/curriculum-roadmap.md 2-1, 9/28 결정 68·65, S14 SEM 7.5)
    ("speak", "상수 | 단계 4 음절·단어", "pass", 65.0), ("speak", "상수 | 단계 4 음절·단어", "mastery", 68.0),
    ("speak", "상수 | 단계 5 문장·억양", "pass", 65.0), ("speak", "상수 | 단계 5 문장·억양", "mastery", 68.0),
    ("speak", "상수 | 단계 4 음절·단어", "gain.floor", 15.0), ("speak", "상수 | 판정·이동 평균", "_SPEAK_SEM", 7.5),
    # 합격선에서 합격(이상), 아래는 불합격
    ("speak", "D-GOP 판정 | 단계 5 '밥 먹었어요.'", "65.passed", True),
    ("speak", "D-GOP 판정 | 단계 5 '밥 먹었어요.'", "64\\.9.passed", False),
    ("speak", "D-GOP 판정 | 단계 4 '밥'", "65.passed", True),
    # 판정 보류: 합격선 ± 7.5 안(엄격 부등호), 음절 단계·확인 낱말·합격선 없음은 해당 없음(test_speak_hold.py)
    ("speak", "판정 보류 | sentence 합격선 65", "65", True), ("speak", "판정 보류 | word 합격선 65", "57\\.6", True),
    ("speak", "판정 보류 | sentence 합격선 65", "72\\.4", True), ("speak", "판정 보류 | sentence 합격선 65", "57\\.5", False),
    ("speak", "판정 보류 | sentence 합격선 65", "72\\.5", False), ("speak", "판정 보류 | sentence 합격선 65", "80", False),
    ("speak", "판정 보류 | phoneme 합격선 50", "50", False),
    ("speak", "판정 보류 | 확인 낱말·합격선 없음", "probe", False),
    ("speak", "판정 보류 | 확인 낱말·합격선 없음", "no_pass", False),
    ("speak", "판정 보류 | 확인 낱말·합격선 없음", "voicing", False),
    # 개인 향상 경로(test_speak_mastery_gain.py)
    ("speak", "향상 경로 | 19번: 시도 부족", "no_floor", False), ("speak", "향상 경로 | +20", "no_floor", True),
    ("speak", "향상 경로 | +12: 향상 부족", "no_floor", False), ("speak", "향상 경로 | 처음 중앙값 40 → 58", "no_floor", True),
    ("speak", "향상 경로 | 늘 40", "no_floor", False), ("speak", "향상 경로 | +20이지만 최근 40", "floor_65", False),
    ("speak", "향상 경로 | 기준선 0, 늘 30", "floor_65", False), ("speak", "향상 경로 | 하한 50에 딱 닿음", "floor_65", True),
    ("speak", "향상 경로 | +20", "floor_65", True),
    ("speak", "향상 경로 | gain 없음·점수 없음", "no_gain", False),
    ("speak", "향상 경로 | gain 없음·점수 없음", "none_scores", False),
    ("speak", "소리 잡힌 시도", "D-GOP 크기 50 점수 30", True), ("speak", "소리 잡힌 시도", "전사 크기 50 '사과' 80", True),
    ("speak", "소리 잡힌 시도", "크기 0", False), ("speak", "소리 잡힌 시도", "크기 없음", False),
    ("speak", "소리 잡힌 시도", "전사 빈 문자열 0점", False), ("speak", "소리 잡힌 시도", "전사 빈 문자열 5점", True),
    # 9/27 감사: 틀린 모음·첫소리는 유사도가 합격선을 넘어도 불합격
    ("speak", "전사 판정 | 단계 2 아 ← '이' sim 50.15", "passed", False),
    ("speak", "전사 판정 | 단계 3 풀 ← '불' sim 91", "passed", False),
    # API 경로: 합격선과 보류가 화면 응답까지 그대로 간다
    ("speak_api", "문장 단계 D-GOP | 03번째 65점", "passed", True),
    ("speak_api", "문장 단계 D-GOP | 03번째 65점", "hold", True),
    ("speak_api", "문장 단계 D-GOP | 02번째 64.9점", "passed", False),
    ("speak_api", "문장 단계 D-GOP | 04번째 57.5점", "hold", False),
    ("speak_api", "낱말 단계 향상 경로 | 20번째 60점", "mastered", True),
    ("speak_api", "낱말 단계 향상 경로 | 19번째 60점", "mastered", False),
    # 독화 이해 채점(test_scoring_v2.py·test_sentence_feedback.py의 만점·0점 사례)
    ("lipread", "visual | 물 좀 주세요 ← '물 좀 주세요'", "score", 100.0),
    ("lipread", "visual | 굳이 가야 해요 ← '구지 가야 해요'", "score", 100.0),
    ("lipread", "visual | 물 좀 주세요 ← '   '", "score", 0.0),
    ("lipread", "visual | 옷 입어 ← '옷\\u3000입어'", "score", 100.0),   # 사례 id는 repr라 전각 공백이 　으로 적힌다
    ("lipread", "visual | 옷 입어 ← '옷\\xa0입어'", "score", 100.0),
    ("lipread", "visual | 옷 입어 ← '옷,입어'", "score", 100.0),
    ("lipread", "phonological | 영수증 드릴까요 ← '영수증 드릴까요 몸조리 잘하세요'", "score", 100.0),
    # 받아쓰기(10/7 판정 개선의 대표 사례)
    ("dictation", "내일 다시 올게요 ← '내일다시 올께요'", "correct_words", 3),
    ("dictation", "물 좀 주세요 ← '좀 물 주세요'", "correct_words", 2),
    ("dictation", "의사 ← '이사'", "correct_words", 0),
    # 발음 규칙(표준 발음법)
    ("engine", "발음 | 굳이", "입모양 경로", "구지"), ("engine", "발음 | 국물", "입모양 경로", "국물"),
    ("engine", "발음 | 국물", "소리 경로(phonetic)", "궁물"), ("engine", "발음 | 백리", "소리 경로(phonetic)", "뱅니"),
    ("engine", "발음 | 먹었다", "소리 경로(phonetic)", "머걷따"), ("engine", "발음 | 많이", "입모양 경로", "마니"),
]


def _split_path(path: str) -> List[str]:
    """점 경로를 나눈다. 키 안의 점은 '\\.'로 적는다(예: '64\\.9.passed')."""
    parts, cur, i = [], "", 0
    while i < len(path):
        if path[i] == "\\" and i + 1 < len(path) and path[i + 1] == ".":
            cur += "."
            i += 2
            continue
        if path[i] == ".":
            parts.append(cur)
            cur = ""
        else:
            cur += path[i]
        i += 1
    parts.append(cur)
    return parts


def _get(obj: Any, path: str) -> Any:
    for k in _split_path(path):
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
        elif isinstance(obj, list) and k.isdigit() and int(k) < len(obj):
            obj = obj[int(k)]
        else:
            raise KeyError(path)
    return obj


def check_pinned(current: Dict[str, Dict[str, Any]]) -> List[str]:
    """고정 기대 위반 목록(사람이 읽는 한 줄씩). 계산하지 않은 층은 건너뛴다."""
    bad = []
    for layer, cid, path, want in PINNED:
        if layer not in current:
            continue
        case = current[layer].get(cid)
        if case is None:
            bad.append(f"[{LAYER_KO[layer]}] {cid}: 사례가 없다(기대 {path} = {want!r})")
            continue
        try:
            got = _get(case, path) if path else case
        except KeyError:
            bad.append(f"[{LAYER_KO[layer]}] {cid}: {path} 항목이 없다(기대 {want!r})")
            continue
        if not _same(got, want):
            bad.append(f"[{LAYER_KO[layer]}] {cid}: {path.replace(chr(92) + '.', '.')} = {got!r}, 기대 {want!r}")
    return bad


# ─────────────────────────────── 차이 계산과 보고 ───────────────────────────────
def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k).replace(".", "\\.")
            out.update(_flatten(v, f"{prefix}.{key}" if prefix else key))
        return out or {prefix: {}}
    return {prefix: obj}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b and type(a) is type(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), abs_tol=_TOL)
    return a == b


_VERDICT_KEYS = ("passed", "hold", "mastered", "correct_words", "level", "feedback_level", "reach_68", "no_floor",
                 "floor_65", "expected", "proportion")


def diff(golden: Dict[str, Dict[str, Any]], current: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """층별 {changed: {사례: [(경로, 전, 후)]}, added: [사례], removed: [사례], same: n}. 현재 계산한 층만 비교한다."""
    out = {}
    for layer, cur_cases in current.items():
        old_cases = golden.get(layer, {})
        changed, added, removed, same = {}, [], [], 0
        for cid, cur in cur_cases.items():
            if cid not in old_cases:
                added.append(cid)
                continue
            fo, fc = _flatten(old_cases[cid]), _flatten(cur)
            rows = []
            for k in sorted(set(fo) | set(fc)):
                a, b = fo.get(k, "<없음>"), fc.get(k, "<없음>")
                if not _same(a, b):
                    rows.append((k, a, b))
            if rows:
                changed[cid] = rows
            else:
                same += 1
        removed = [cid for cid in old_cases if cid not in cur_cases]
        out[layer] = {"changed": changed, "added": added, "removed": removed, "same": same, "total": len(cur_cases)}
    return out


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return repr(v) if isinstance(v, str) else str(v)


def _is_verdict(path: str, a: Any = None, b: Any = None) -> bool:
    """판정이 바뀐 항목인가: 참·거짓 값(합격·보류·숙달 등)이거나 판정 이름의 항목(맞힌 낱말 수, 피드백 등급, 숙달 도달 시점 등)."""
    last = _split_path(path)[-1]
    return isinstance(a, bool) or isinstance(b, bool) or last.startswith(_VERDICT_KEYS)


def format_report(d: Dict[str, Dict[str, Any]], pinned_bad: List[str], golden_meta: Optional[Dict] = None,
                  max_rows: int = 400) -> str:
    """사람이 읽는 차이 보고(마크다운). 판정(합격·보류·숙달·맞힌 낱말 수 등)이 바뀐 항목은 앞에 '판정'을 붙인다."""
    lines = ["# 채점 회귀 점검 보고", ""]
    if golden_meta:
        lines.append(f"- 기준: {golden_meta.get('updated_at', '?')} 커밋 {golden_meta.get('commit', '?')}")
    total_changed = sum(len(x["changed"]) + len(x["added"]) + len(x["removed"]) for x in d.values())
    lines.append(f"- 결과: {'차이 없음' if not total_changed else f'바뀐 사례 {total_changed}건'}, "
                 f"고정 기대 위반 {len(pinned_bad)}건")
    lines += ["", "| 층 | 사례 | 같음 | 바뀜 | 새 사례 | 없어진 사례 | 판정 바뀜 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for layer, x in d.items():
        n_verdict = sum(1 for rows in x["changed"].values() if any(_is_verdict(p, a, b) for p, a, b in rows))
        lines.append(f"| {LAYER_KO[layer]} | {x['total']} | {x['same']} | {len(x['changed'])} | {len(x['added'])} | "
                     f"{len(x['removed'])} | {n_verdict} |")
    if pinned_bad:
        lines += ["", "## 고정 기대 위반(규칙 문서 값과 다름, --update로 고쳐지지 않음)", ""]
        lines += [f"- {b}" for b in pinned_bad]
    shown = 0
    for layer, x in d.items():
        if not (x["changed"] or x["added"] or x["removed"]):
            continue
        lines += ["", f"## {LAYER_KO[layer]}", ""]
        num_deltas = []
        for cid, rows in x["changed"].items():
            lines.append(f"- {cid}")
            for p, a, b in rows:
                if shown >= max_rows:
                    break
                tag = "판정 " if _is_verdict(p, a, b) else ""
                delta = ""
                if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
                    delta = f" ({float(b) - float(a):+g})"
                    num_deltas.append(float(b) - float(a))
                lines.append(f"  - {tag}{p.replace(chr(92) + '.', '.')}: {_fmt(a)} → {_fmt(b)}{delta}")
                shown += 1
        for cid in x["added"]:
            lines.append(f"- 새 사례: {cid}")
        for cid in x["removed"]:
            lines.append(f"- 없어진 사례: {cid}")
        if num_deltas:
            lines.append(f"- 숫자 변화 {len(num_deltas)}개: 평균 {sum(num_deltas) / len(num_deltas):+.3f}, "
                         f"절댓값 최대 {max(abs(v) for v in num_deltas):.3f}")
    if shown >= max_rows:
        lines.append(f"\n(항목이 많아 {max_rows}줄에서 끊었다. --max-rows로 늘린다.)")
    return "\n".join(lines) + "\n"


def load_golden(path: str = GOLDEN_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_golden(current: Dict[str, Dict[str, Any]], meta: Dict[str, Any], path: str = GOLDEN_PATH,
                 base: Optional[Dict[str, Any]] = None) -> None:
    """기준 파일을 쓴다. 일부 층만 계산했으면 나머지 층은 base(지금 기준)에서 그대로 둔다."""
    cases = dict((base or {}).get("cases") or {})
    cases.update(current)
    data = {"meta": meta, "cases": {k: cases[k] for k in LAYERS if k in cases}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
