import { useEffect, useState } from 'react'
import { curriculumAPI, speakAPI } from '../../../api'
import { getTrack } from '../../../config/tracks'
import { mergeLessonStatus } from './trackProgress'

// config/tracks.js의 apiNamespace 문자열 → api.js의 실제 객체(스펙 8장의 동적 매핑).
const API_NAMESPACES = { curriculumAPI, speakAPI }

/**
 * useTrackLessons — 트랙 정의에 단계 API의 사용자별 상태를 합쳐 돌려준다.
 * 독화·말하기가 서로 다른 API를 쓰는 차이는 여기서 흡수한다(컴포넌트는 트랙 id만 넘긴다).
 * 조회에 실패하면 status를 null로 두어 잠그지 않는다(StageGate와 같은 가용성 우선).
 */
export default function useTrackLessons(trackId) {
  const track = getTrack(trackId)
  const [stages, setStages] = useState(null)   // null = 불러오는 중
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!track) return undefined
    let active = true
    setStages(null)
    setFailed(false)
    Promise.resolve()
      .then(() => API_NAMESPACES[track.apiNamespace][track.stagesMethod]())
      .then((data) => { if (active) setStages(data?.stages || []) })
      .catch(() => { if (active) { setStages([]); setFailed(true) } })
    return () => { active = false }
  }, [trackId])

  return {
    track,
    loading: !!track && stages === null,
    failed,
    lessons: track ? mergeLessonStatus(track.lessons, stages) : [],
    practice: track ? track.practice : [],
  }
}
