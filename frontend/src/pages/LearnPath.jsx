import { lazy, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import useStore from '../store/useStore'
import { saveLastTrack } from '../lib/lastTrack'
const CurriculumPath = lazy(() => import('./CurriculumPath'))
const ListenPath = lazy(() => import('./ListenPath'))
const LearnSection = lazy(() => import('../components/learn/LearnSection'))
export default function LearnPath() {
  const [params] = useSearchParams()
  const uid = useStore((s) => s.user?.id)
  const track = ['speak', 'listen'].includes(params.get('track')) ? params.get('track') : 'read'
  const section = ['free', 'res'].includes(params.get('section')) ? params.get('section') : 'path'
  useEffect(() => { saveLastTrack(uid, track) }, [uid, track])
  return section !== 'path' ? <LearnSection track={track} section={section} /> : track === 'listen' ? <ListenPath /> : <CurriculumPath />
}
