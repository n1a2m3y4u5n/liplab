"""데모용 더미 학습 기록 시드.
데모 계정이 비어 있을 때만 채운다(이미 기록이 있으면 건드리지 않음 → 실사용 데이터 보호).
대시보드 통계·활동 캘린더·독화 분석(취약 입모양/음소 혼동)·말하기 분석·단계 진행을 모두 채운다.
"""
import random
from datetime import datetime, timedelta

# (문장, 사용자 답, 점수) — 일부는 오답으로 음소 혼동 유발(독화 분석)
SENTENCES = [
    ("바다가 넓어요", "바다가 넓어요", 96),
    ("밥 먹었어요", "밥 먹었어요", 88),
    ("커피 주세요", "커피 두세요", 72),
    ("병원이 어디예요", "병원이 어디예요", 91),
    ("사과 두 개 주세요", "사가 두 개 주세요", 68),
    ("학교에 가요", "학교에 가요", 84),
    ("고맙습니다", "고맙습니다", 93),
    ("파도가 쳐요", "바도가 쳐요", 64),
    ("물 좀 주세요", "물 좀 두세요", 70),
    ("안녕하세요", "안녕하세요", 90),
    ("얼마예요", "얼마예요", 82),
    ("맛있어요", "마시써요", 75),
]

# (목표, 전사, 점수, loudness, pitch_range, 혼동)
SPEAK_ITEMS = [
    ("바다", "바다", 95, 55, 32, []),
    ("파도", "바도", 62, 40, 14, [{"correct": "ㅍ", "confused_as": "ㅂ"}]),
    ("사과", "사과", 88, 60, 28, []),
    ("학교", "학꾜", 71, 48, 20, [{"correct": "ㄱ", "confused_as": "ㄲ"}]),
    ("엄마", "엄마", 92, 58, 35, []),
    ("다리", "타리", 66, 42, 16, [{"correct": "ㄷ", "confused_as": "ㅌ"}]),
    ("나무", "나무", 85, 52, 30, []),
    ("우유", "우유", 90, 57, 33, []),
]


async def run(user, db):
    """데모 계정에 더미 기록을 넣는다. 이미 기록이 있으면 False 반환(스킵)."""
    from database import (Progress, WeakViseme, StageProgress,
                          SpeakStageProgress, SpeakAttempt, LearningProfile,
                          TactileStageProgress)
    from sqlalchemy import select

    # ── 촉각 진행도 백필(독립·멱등) — 이미 시드된 기존 데모 계정에도 뒤늦게 채워준다.
    # (촉각 기능은 나중에 추가돼서 Progress 게이트만으론 기존 계정이 비어버리므로 분리 처리)
    rt = await db.execute(select(TactileStageProgress.id).where(TactileStageProgress.user_id == user.id).limit(1))
    if rt.scalar_one_or_none() is None:
        db.add(TactileStageProgress(user_id=user.id, stage=0, status="mastered", mastery_score=88.0, attempts=8, correct=7))
        db.add(TactileStageProgress(user_id=user.id, stage=1, status="in_progress", mastery_score=60.0, attempts=5, correct=3))
        await db.commit()

    r = await db.execute(select(Progress.id).where(Progress.user_id == user.id).limit(1))
    if r.scalar_one_or_none() is not None:
        return False   # 이미 데이터 있음 → 스킵

    now = datetime.utcnow()
    situations = ["카페", "병원", "식당", "학교", "은행"]

    # ── 독화 테스트 기록(Progress) — 최근 90일 분산 ──
    n = 0
    for day in range(0, 90, 2):
        for _ in range(random.choice([0, 0, 1, 1, 1, 2])):
            s, ua, sc = random.choice(SENTENCES)
            db.add(Progress(
                user_id=user.id, scenario_id=f"seed_{n}", sentence=s, user_answer=ua,
                score=float(sc), time_spent_seconds=random.randint(20, 90),
                difficulty_level=random.randint(1, 3), situation=random.choice(situations),
                created_at=now - timedelta(days=day, hours=random.randint(0, 20)),
                viseme_errors=[], phoneme_accuracy={},
            ))
            n += 1

    # ── 취약 입모양(WeakViseme) ──
    for vid, feat, err, tot in [(1, "bilabial", 12, 30), (5, "dental", 8, 26), (9, "velar", 5, 24)]:
        db.add(WeakViseme(user_id=user.id, viseme_id=vid, error_count=err,
                          total_attempts=tot, phonological_feature=feat))

    # ── 독화 단계 진행 ──
    db.add(StageProgress(user_id=user.id, stage=1, status="mastered", mastery_score=86.0, attempts=18, correct=15))
    db.add(StageProgress(user_id=user.id, stage=2, status="in_progress", mastery_score=64.0, attempts=11, correct=7))

    # ── 발화 단계 진행 ──
    db.add(SpeakStageProgress(user_id=user.id, stage=0, status="mastered", mastery_score=100.0, attempts=6, correct=6))
    db.add(SpeakStageProgress(user_id=user.id, stage=1, status="mastered", mastery_score=90.0, attempts=10, correct=9))
    db.add(SpeakStageProgress(user_id=user.id, stage=2, status="in_progress", mastery_score=58.0, attempts=12, correct=7))
    # (촉각 진행도는 함수 상단에서 독립 백필됨)

    # ── 발화 시도(SpeakAttempt) — 말하기 분석 ──
    for t, tr, sc, ld, pr, conf in SPEAK_ITEMS * 2:
        db.add(SpeakAttempt(
            user_id=user.id, stage=random.choice([2, 3, 4]),
            mode=random.choice(["phoneme", "word", "sentence"]),
            target=t, transcript=tr, score=float(sc), passed=sc >= 65,
            loudness=float(ld), pitch_range=float(pr), duration=round(random.uniform(0.8, 2.2), 1),
            pitch_start=float(random.randint(110, 140)), pitch_end=float(random.randint(110, 160)),
            confusions=conf, created_at=now - timedelta(days=random.randint(0, 20), hours=random.randint(0, 20)),
        ))

    # ── 촉각 시도(TactileAttempt) — 타도마 복습 '틀림' 채우기 ──
    from database import TactileAttempt, ReviewItem, Bookmark
    from datetime import date as _d, timedelta as _td
    for tgt, ok in [("바다", True), ("파도", False), ("포도", False), ("사과", True), ("구두", False)]:
        db.add(TactileAttempt(user_id=user.id, stage=3, target=tgt, correct=ok,
                              created_at=now - timedelta(days=random.randint(0, 10))))

    # ── 독화 오답 문장(<60) — 독화 '틀린 문제' 채우기 ──
    for s, ua, sc in [("커피 주세요", "커피 두세요", 52), ("파도가 쳐요", "바도가 쳐요", 47)]:
        db.add(Progress(
            user_id=user.id, scenario_id=f"seed_wrong_{sc}", sentence=s, user_answer=ua,
            score=float(sc), time_spent_seconds=40, difficulty_level=2, situation="복습",
            created_at=now - timedelta(days=random.randint(0, 8)),
            viseme_errors=[], phoneme_accuracy={},
        ))

    # ── SRS 예정(ReviewItem) — 세 기둥 '오늘 예정' 채우기 ──
    _today = _d.today().isoformat()
    for kind, ref in [("viseme", "1"), ("viseme", "5"), ("word", "사과"),
                      ("speak", "학교"), ("speak", "다리"), ("tactile", "파도"), ("tactile", "구두")]:
        db.add(ReviewItem(user_id=user.id, kind=kind, ref=ref, due_date=_today, interval_days=1))

    # ── 북마크(도메인별) — 세 기둥 '북마크' 채우기 ──
    db.add(Bookmark(user_id=user.id, sentence="여기 앉아도 될까요?", situation="독화", level=2, domain="read"))
    db.add(Bookmark(user_id=user.id, sentence="고맙습니다.", situation="말하기", level=1, domain="speak"))
    db.add(Bookmark(user_id=user.id, sentence="안녕하세요", situation="촉각", level=1, domain="tactile"))

    # ── 게이미피케이션 ──
    user.total_xp = 640
    user.current_level = 4
    user.streak_count = 5

    # ── 배치(트랙) 완료 ──
    r2 = await db.execute(select(LearningProfile).where(LearningProfile.user_id == user.id))
    prof = r2.scalar_one_or_none()
    if prof is None:
        prof = LearningProfile(user_id=user.id)
        db.add(prof)
    prof.track = "perception"
    prof.placed = True
    prof.current_stage = 2

    await db.commit()
    return True
