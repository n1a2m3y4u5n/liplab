import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI } from '../api'
import { retentionPromptVisible, localDay } from '../lib/measurement'

const DISMISS_KEY = 'liplab.retentionPrompt.dismissedOn'

function readDismissed() {
  try { return window.localStorage.getItem(DISMISS_KEY) } catch { return null }
}

/**
 * 지연 유지 검사(C7) 안내 — 사후 검사 뒤 정해진 날수(서버 LIPLAB_RETENTION_DAYS, 기본 28일)가 지나면 학습 경로 위에 조용히 띄운다.
 * 막지 않는다. '나중에'를 누르면 그날은 숨긴다(이 기기에서만). 상태를 받지 못하면 아무것도 그리지 않는다.
 */
export default function RetentionPrompt() {
  const navigate = useNavigate()
  const [status, setStatus] = useState(null)
  const [dismissed, setDismissed] = useState(readDismissed)
  useEffect(() => { curriculumAPI.getRetention().then(setStatus).catch(() => {}) }, [])

  const today = localDay()
  if (!retentionPromptVisible(status, dismissed, today)) return null
  const later = () => {
    try { window.localStorage.setItem(DISMISS_KEY, today) } catch { /* 저장 못 해도 이번 화면에서는 숨긴다 */ }
    setDismissed(today)
  }
  return (
    <div role="status" className="flex w-full flex-col gap-2.5 rounded-16 border-2 border-line bg-white px-4 py-3.5 sm:flex-row sm:items-center lg:rounded-18 lg:px-5">
      <p className="flex-1 text-[13px] leading-relaxed text-ink-muted lg:text-[14px]">
        사후 검사를 본 지 {status.days_since_post}일이 지났어요. 배운 것이 얼마나 남아 있는지 보는 유지 검사를 볼 수 있어요.
        사후 검사와 같은 24문항, 5분 안팎이에요.
      </p>
      <div className="flex shrink-0 gap-2">
        <button type="button" onClick={later} className="btn-secondary whitespace-nowrap !py-2.5 px-4 text-[14px]">나중에</button>
        <button type="button" onClick={() => navigate('/learn/placement?form=R')} className="btn-primary whitespace-nowrap !py-2.5 px-4 text-[14px]">유지 검사 보기</button>
      </div>
    </div>
  )
}
