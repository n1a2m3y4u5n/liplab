"""P18: 관리자 영상별 CC 검수. 다운로드·미디어 제공은 하지 않는다."""
import os
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse, parse_qs
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from auth import get_current_user
from database import KmsavReview, get_db

router = APIRouter()

def gate(user):
    if os.getenv('LIPLAB_KMSAV_REVIEW', '0') != '1':
        raise HTTPException(404, '사용하지 않는 기능이에요.')
    from main import _admin_email_gate
    _admin_email_gate(user)

class Review(BaseModel):
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    source: str = Field(min_length=1, max_length=500)
    license_label: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=1, max_length=1000)
    decision: Literal['pending', 'usable', 'rejected']

    @model_validator(mode='after')
    def validate_source(self):
        url = urlparse(self.source)
        expected = (url.hostname in ('www.youtube.com', 'youtube.com') and url.path == '/watch'
                    and parse_qs(url.query).get('v') == [self.video_id]) or (
                    url.hostname == 'youtu.be' and url.path == '/' + self.video_id)
        if url.scheme != 'https' or url.username or url.password or not expected:
            raise ValueError('영상 ID와 일치하는 HTTPS YouTube 출처가 필요해요.')
        if not self.license_label.strip() or not self.evidence.strip():
            raise ValueError('라이선스와 검수 근거가 필요해요.')
        if self.decision == 'usable' and not self.license_label.strip().upper().startswith('CC '):
            raise ValueError('사용 가능 판정에는 확인한 CC 표기가 필요해요.')
        return self

def record(row):
    return {k: getattr(row, k) for k in ('video_id', 'source', 'license_label', 'evidence', 'decision')} | {
        'updated_at': row.updated_at.isoformat() + 'Z'}

@router.get('/api/admin/kmsav')
async def reviews(user=Depends(get_current_user), db=Depends(get_db)):
    gate(user)
    rows = (await db.execute(select(KmsavReview).order_by(KmsavReview.video_id).limit(1000))).scalars()
    return {'records': [record(row) for row in rows]}

@router.put('/api/admin/kmsav')
async def save(data: Review, user=Depends(get_current_user), db=Depends(get_db)):
    gate(user)
    row = await db.get(KmsavReview, data.video_id)
    if row is None:
        row = KmsavReview(video_id=data.video_id)
        db.add(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value.strip())
    row.user_id, row.updated_at = user.id, datetime.utcnow()
    await db.commit()
    return record(row)
