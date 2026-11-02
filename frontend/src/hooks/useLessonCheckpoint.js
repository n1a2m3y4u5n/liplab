import { useLayoutEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import useStore from '../store/useStore'
import { checkpointKey, readCheckpoint, writeCheckpoint } from '../lib/lessonCheckpoint'

export default function useLessonCheckpoint(kind) {
  const uid = useStore((s) => s.user?.id ?? 'guest')
  const location = useLocation()
  // 공유 듣기 과제의 자유 연습·검사 묶음은 이 단계 레슨 복원에 섞지 않는다.
  const enabled = !kind.startsWith('listen-') || location.pathname === '/learn/listening'
  const key = checkpointKey(uid, `${kind}:${location.pathname}${location.search}`)
  const initial = useRef(undefined)
  if (initial.current === undefined) initial.current = enabled ? readCheckpoint(key) : null
  const latest = useRef(null)
  const previous = useRef(null)
  const sentKey = `${key}:sent`
  const sent = useRef(enabled ? readCheckpoint(sentKey) : null)
  const save = (value) => { latest.current = value }
  // 브라우저가 다음 이벤트를 받기 전에 한 번의 상태 묶음으로 저장한다.
  useLayoutEffect(() => {
    const value = latest.current
    if (!enabled || !value) return
    // 볼륨 표시·재생 프레임처럼 저장 대상이 안 바뀐 렌더에서는 디스크를 쓰지 않는다.
    if (previous.current && Object.keys(value).every(field => value[field] === previous.current[field])) return
    if (writeCheckpoint(key, value)) previous.current = value
  })
  const clear = (wholeRoute = false) => {
    latest.current = null
    try {
      if (wholeRoute) {
        const suffix = `:${location.pathname}${location.search}`
        for (let i = localStorage.length - 1; i >= 0; i--) {
          const storedKey = localStorage.key(i)
          if (storedKey?.startsWith(checkpointKey(uid, '')) && (storedKey.endsWith(suffix) || storedKey.endsWith(`${suffix}:sent`))) localStorage.removeItem(storedKey)
        }
      } else localStorage.removeItem(key)
    } catch {}
  }
  const begin = (answer) => {
    if (sent.current) return false
    const value = { answer, at: Date.now(), lesson: kind, question: latest.current?.qNum ?? latest.current?.sentence }
    sent.current = value
    if (enabled) writeCheckpoint(sentKey, value)
    return true
  }
  const finish = () => { sent.current = null; try { localStorage.removeItem(sentKey) } catch {} }
  return [initial.current, save, clear, { sent: sent.current, begin, finish }]
}
