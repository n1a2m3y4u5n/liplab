import { lazy } from 'react'
import { useSearchParams } from 'react-router-dom'
const CurriculumPath = lazy(() => import('./CurriculumPath'))
const ListenPath = lazy(() => import('./ListenPath'))

export default function LearnPath() {
  const [params] = useSearchParams()
  return params.get('track') === 'listen' ? <ListenPath /> : <CurriculumPath />
}
