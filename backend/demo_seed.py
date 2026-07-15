"""데모용 더미 학습 기록 시드.
데모 계정을 '수개월간 꾸준히 써 온 활성 유저'처럼 보이게 채운다.
대시보드 통계·활동 캘린더·독화 분석(취약 입모양/음소 혼동)·말하기/촉각 분석·단계 진행·복습을 모두 채운다.

재시드 정책(SEED_VERSION):
  - 시드 버전 마커(Progress.scenario_id == SEED_MARKER)가 있으면 최신 → 스킵.
  - 구버전 데이터만 있으면(마커 없음) 데모 계정의 학습 데이터를 싹 지우고 새 값으로 재시드.
    (데모 계정 전용 더미이므로 안전. 실사용 계정은 이 함수 대상이 아님)
"""
import random
from datetime import datetime, timedelta, date as _date

SEED_VERSION = 3
SEED_MARKER = f"seed_marker_v{SEED_VERSION}"

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
    ("천천히 말해 주세요", "천천히 말해 주세요", 87),
    ("이거 얼마예요", "이거 얼마예요", 89),
    ("다시 한 번요", "다시 한 번요", 92),
    ("도와주세요", "도와주세요", 94),
    ("어디에서 만나요", "어디에서 만나요", 83),
    ("괜찮아요", "괜찮아요", 91),
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
    ("포도", "보도", 64, 41, 15, [{"correct": "ㅍ", "confused_as": "ㅂ"}]),
    ("구름", "구름", 87, 54, 29, []),
    ("토끼", "도끼", 68, 44, 18, [{"correct": "ㅌ", "confused_as": "ㄷ"}]),
    ("기차", "기차", 89, 56, 31, []),
]


async def run(user, db):
    """데모 계정에 더미 기록을 넣는다. 최신 버전이 이미 있으면 False(스킵)."""
    from database import (Progress, WeakViseme, StageProgress,
                          SpeakStageProgress, SpeakAttempt, LearningProfile,
                          TactileStageProgress, TactileAttempt, ReviewItem, Bookmark)
    from sqlalchemy import select, delete

    # 이미 최신 버전으로 시드됐는지 — 마커 확인
    m = await db.execute(
        select(Progress.id).where(Progress.user_id == user.id,
                                  Progress.scenario_id == SEED_MARKER).limit(1))
    if m.scalar_one_or_none() is not None:
        return False   # 최신 시드 존재 → 스킵

    # 구버전 데이터가 있으면 데모 계정의 학습 데이터를 싹 지우고 재시드
    has_any = await db.execute(select(Progress.id).where(Progress.user_id == user.id).limit(1))
    if has_any.scalar_one_or_none() is not None:
        for M in (Progress, WeakViseme, StageProgress, SpeakStageProgress, SpeakAttempt,
                  TactileStageProgress, TactileAttempt, ReviewItem, Bookmark):
            await db.execute(delete(M).where(M.user_id == user.id))
        await db.commit()

    now = datetime.utcnow()
    situations = ["카페", "병원", "식당", "학교", "은행", "대중교통", "직장"]

    # ── 버전 마커(첫 세션처럼 아주 오래 전 기록으로) ──
    db.add(Progress(
        user_id=user.id, scenario_id=SEED_MARKER, sentence="안녕하세요", user_answer="안녕하세요",
        score=80.0, time_spent_seconds=45, difficulty_level=1, situation="학교",
        created_at=now - timedelta(days=182), viseme_errors=[], phoneme_accuracy={},
    ))

    # ── 독화 테스트 기록(Progress) — 최근 168일(24주) 분산, 최근일수록 활발 ──
    n = 0
    for day in range(0, 168):
        if day < 30:      weights = [0, 1, 1, 2, 2, 3]   # 최근 한 달: 활발
        elif day < 90:    weights = [0, 0, 1, 1, 2]      # 1~3개월 전: 보통
        else:             weights = [0, 0, 0, 1, 1]      # 3~6개월 전: 드문드문
        for _ in range(random.choice(weights)):
            s, ua, sc = random.choice(SENTENCES)
            db.add(Progress(
                user_id=user.id, scenario_id=f"seed_{n}", sentence=s, user_answer=ua,
                score=float(sc), time_spent_seconds=random.randint(20, 90),
                difficulty_level=random.randint(1, 4), situation=random.choice(situations),
                created_at=now - timedelta(days=day, hours=random.randint(0, 20)),
                viseme_errors=[], phoneme_accuracy={},
            ))
            n += 1

    # ── 취약 입모양(WeakViseme) ──
    for vid, feat, err, tot in [(1, "bilabial", 34, 96), (5, "dental", 21, 82),
                                (9, "velar", 14, 70), (10, "palatal", 11, 58)]:
        db.add(WeakViseme(user_id=user.id, viseme_id=vid, error_count=err,
                          total_attempts=tot, phonological_feature=feat))

    # ── 독화 단계 진행 (기초는 숙달, 실전은 진행 중) ──
    db.add(StageProgress(user_id=user.id, stage=1, status="mastered", mastery_score=93.0, attempts=42, correct=38))
    db.add(StageProgress(user_id=user.id, stage=2, status="mastered", mastery_score=84.0, attempts=36, correct=29))
    db.add(StageProgress(user_id=user.id, stage=3, status="in_progress", mastery_score=66.0, attempts=24, correct=15))

    # ── 발화 단계 진행 (6단계 중 4단계까지 숙달) ──
    db.add(SpeakStageProgress(user_id=user.id, stage=0, status="mastered", mastery_score=100.0, attempts=14, correct=14))
    db.add(SpeakStageProgress(user_id=user.id, stage=1, status="mastered", mastery_score=95.0, attempts=22, correct=21))
    db.add(SpeakStageProgress(user_id=user.id, stage=2, status="mastered", mastery_score=88.0, attempts=26, correct=22))
    db.add(SpeakStageProgress(user_id=user.id, stage=3, status="mastered", mastery_score=79.0, attempts=28, correct=21))
    db.add(SpeakStageProgress(user_id=user.id, stage=4, status="in_progress", mastery_score=61.0, attempts=19, correct=11))

    # ── 촉각 단계 진행 (5단계 중 2단계 숙달) ──
    db.add(TactileStageProgress(user_id=user.id, stage=0, status="mastered", mastery_score=92.0, attempts=16, correct=15))
    db.add(TactileStageProgress(user_id=user.id, stage=1, status="mastered", mastery_score=86.0, attempts=18, correct=15))
    db.add(TactileStageProgress(user_id=user.id, stage=2, status="in_progress", mastery_score=63.0, attempts=13, correct=8))

    # ── 발화 시도(SpeakAttempt) — 말하기 분석 (최근 70일에 분산) ──
    for t, tr, sc, ld, pr, conf in SPEAK_ITEMS * 4:
        db.add(SpeakAttempt(
            user_id=user.id, stage=random.choice([2, 3, 4]),
            mode=random.choice(["phoneme", "word", "sentence"]),
            target=t, transcript=tr, score=float(sc), passed=sc >= 65,
            loudness=float(ld), pitch_range=float(pr), duration=round(random.uniform(0.8, 2.2), 1),
            pitch_start=float(random.randint(110, 140)), pitch_end=float(random.randint(110, 160)),
            confusions=conf, created_at=now - timedelta(days=random.randint(0, 70), hours=random.randint(0, 20)),
        ))

    # ── 촉각 시도(TactileAttempt) — 타도마 복습 '틀림' 채우기 ──
    for tgt, ok in [("바다", True), ("파도", False), ("포도", False), ("사과", True),
                    ("구두", False), ("바나나", True), ("단추", False), ("포도", True)]:
        db.add(TactileAttempt(user_id=user.id, stage=random.choice([2, 3]), target=tgt, correct=ok,
                              created_at=now - timedelta(days=random.randint(0, 30))))

    # ── 독화 오답 문장(<60) — 독화 '틀린 문제' 채우기 ──
    for s, ua, sc in [("커피 주세요", "커피 두세요", 52), ("파도가 쳐요", "바도가 쳐요", 47),
                      ("포도 주세요", "보도 주세요", 55), ("토끼가 뛰어요", "도끼가 뛰어요", 49)]:
        db.add(Progress(
            user_id=user.id, scenario_id=f"seed_wrong_{sc}", sentence=s, user_answer=ua,
            score=float(sc), time_spent_seconds=40, difficulty_level=2, situation="복습",
            created_at=now - timedelta(days=random.randint(0, 8)),
            viseme_errors=[], phoneme_accuracy={},
        ))

    # ── SRS 예정(ReviewItem) — 세 기둥 '오늘 예정' 채우기 ──
    _today = _date.today().isoformat()
    for kind, ref in [("viseme", "1"), ("viseme", "5"), ("viseme", "9"),
                      ("word", "사과"), ("word", "포도"),
                      ("speak", "학교"), ("speak", "다리"), ("speak", "토끼"),
                      ("tactile", "파도"), ("tactile", "구두"), ("tactile", "단추")]:
        db.add(ReviewItem(user_id=user.id, kind=kind, ref=ref, due_date=_today, interval_days=random.choice([1, 2, 4])))

    # ── 북마크(도메인별) — 세 기둥 '북마크' 채우기 ──
    for sent, sit, lv, dom in [
        ("여기 앉아도 될까요?", "독화", 2, "read"),
        ("천천히 말씀해 주세요", "독화", 3, "read"),
        ("고맙습니다.", "말하기", 1, "speak"),
        ("다시 만나요", "말하기", 2, "speak"),
        ("안녕하세요", "촉각", 1, "tactile"),
    ]:
        db.add(Bookmark(user_id=user.id, sentence=sent, situation=sit, level=lv, domain=dom))

    # ── 게이미피케이션 (수개월 꾸준히 쓴 유저) ──
    user.total_xp = 6800
    user.current_level = 9           # level = int(sqrt(6800/100))+1 = 9
    user.streak_count = 16

    # ── 배치(트랙) 완료 ──
    r2 = await db.execute(select(LearningProfile).where(LearningProfile.user_id == user.id))
    prof = r2.scalar_one_or_none()
    if prof is None:
        prof = LearningProfile(user_id=user.id)
        db.add(prof)
    prof.track = "perception"
    prof.placed = True
    prof.current_stage = 3

    await db.commit()
    return True
