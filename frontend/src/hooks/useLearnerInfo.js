import { useCallback, useEffect, useState } from 'react'
import useStore from '../store/useStore'
import { loadAnswers, saveAnswers, clearAnswers, learnerDefaults, BASE_DEFAULTS, storageKey } from '../lib/learnerProfile'

// 학습자 정보(계획 2-6)와 그 기본값. 답은 이 기기에만 계정마다 저장한다(lib/learnerProfile). 서버로 보내지 않는다.
// 같은 창의 다른 화면이 답을 바꾸면 'liplab:learner-info' 이벤트로, 다른 탭이면 storage 이벤트로 다시 읽는다.
const EVT = 'liplab:learner-info'

export default function useLearnerInfo() {
  const uid = useStore((s) => s.user?.id ?? 'guest')
  const [answers, setAnswers] = useState(() => loadAnswers(uid))
  useEffect(() => {
    setAnswers(loadAnswers(uid))
    const reload = () => setAnswers(loadAnswers(uid))
    const onStorage = (e) => { if (!e.key || e.key === storageKey(uid)) reload() }
    window.addEventListener(EVT, reload)
    window.addEventListener('storage', onStorage)
    return () => { window.removeEventListener(EVT, reload); window.removeEventListener('storage', onStorage) }
  }, [uid])
  const save = useCallback((a) => {
    const saved = saveAnswers(uid, a)
    setAnswers(saved)
    window.dispatchEvent(new Event(EVT))
    return saved
  }, [uid])
  const clear = useCallback(() => {
    clearAnswers(uid)
    setAnswers(null)
    window.dispatchEvent(new Event(EVT))
  }, [uid])
  return { answers, defaults: answers ? learnerDefaults(answers) : BASE_DEFAULTS, save, clear }
}
