import { lazy, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import useStore from '../store/useStore'
import { saveLastTrack } from '../lib/lastTrack'
const CurriculumPath = lazy(() => import('./CurriculumPath'))
const ListenPath = lazy(() => import('./ListenPath'))
// 11/03: 단계·자유 연습·자료를 한 화면에 둔다. ?section=free|res로 들어오면 그 섹션으로 스크롤만 한다(예전 링크 그대로 동작).
export default function LearnPath() {
  const [params] = useSearchParams()
  const uid = useStore((s) => s.user?.id)
  const track = ['speak', 'listen'].includes(params.get('track')) ? params.get('track') : 'read'
  const section = ['free', 'res'].includes(params.get('section')) ? params.get('section') : null
  useEffect(() => { saveLastTrack(uid, track) }, [uid, track])
  useEffect(() => {
    if (!section) return undefined
    let tries = 0
    // 단계 목록을 받는 동안에는 섹션이 아직 없어 잠깐 기다렸다가 옮긴다
    const t = setInterval(() => {
      const el = document.getElementById(`learn-${section}`)
      if (el || ++tries > 20) { clearInterval(t); el?.scrollIntoView({ block: 'start' }) }
    }, 100)
    return () => clearInterval(t)
  }, [section, track])
  return track === 'listen' ? <ListenPath /> : <CurriculumPath />
}
