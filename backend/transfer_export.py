"""P0: 전이 측정 기록의 가명 내보내기. 파일 경로·답 원문·계정 식별자는 제외한다."""
from sqlalchemy import select
from database import RealFaceProbe, AvComparison, AvComparisonAnswer
from av_comparison import gains

async def export_transfer(db, uid):
    probes = list((await db.execute(select(RealFaceProbe).where(RealFaceProbe.user_id == uid).order_by(RealFaceProbe.created_at))).scalars())
    sessions = list((await db.execute(select(AvComparison).where(AvComparison.user_id == uid).order_by(AvComparison.created_at))).scalars())
    answers = list((await db.execute(select(AvComparisonAnswer).where(AvComparisonAnswer.user_id == uid).order_by(AvComparisonAnswer.id))).scalars())
    comparisons = []
    for session in sessions:
        rows = [r for r in answers if r.session_id == session.id]
        comparisons.append({'version': session.snapshot['version'], 'snr_db': session.snr_db,
            'completed': session.completed, 'headphone_check': session.headphone_check, 'volume_fixed': session.volume_fixed,
            'items': [{'item_id': r.item_id, 'condition': r.condition, 'matched': r.matched, 'total': r.total,
                       'plays': r.plays, 'rt_ms': r.rt_ms} for r in rows],
            **(gains(rows) if session.completed else {})})
    return {'real_face_probes': [{'item_id': r.item_id, 'version': r.version, 'talker': r.snapshot['talker'],
                'answered': r.answered_at is not None, 'correct': r.correct, 'rt_ms': r.rt_ms,
                'day': r.created_at.date().isoformat()} for r in probes], 'av_comparisons': comparisons}
