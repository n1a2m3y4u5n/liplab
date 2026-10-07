import { useCallback, useEffect, useState } from 'react'
import useStore from '../store/useStore'
import useLearnerInfo from './useLearnerInfo'

// 소리 조건(C17) 켜기. 기본은 끔이고 학습자가 켠다. 보청기·인공와우를 답한 학습자에게만 권한다(learnerDefaults.soundCondition).
// 학습자 정보처럼 이 기기에만 계정마다 둔다. 권하기를 '괜찮아요'로 닫으면 다시 권하지 않는다.
const EVT = 'liplab:sound-condition'
const key = (uid) => `liplab_sound_condition:${uid}`

function load(uid) {
  try {
    const raw = globalThis.localStorage?.getItem(key(uid))
    if (raw) {
      const v = JSON.parse(raw)
      return { enabled: v?.enabled === true, dismissed: v?.dismissed === true }
    }
  } catch { /* 저장소 차단 */ }
  return { enabled: false, dismissed: false }
}

function save(uid, v) {
  try { globalThis.localStorage?.setItem(key(uid), JSON.stringify(v)) } catch { /* 이 창에서만 */ }
}

export default function useSoundCondition() {
  const uid = useStore((s) => s.user?.id ?? 'guest')
  const { defaults } = useLearnerInfo()
  const [state, setState] = useState(() => load(uid))
  useEffect(() => {
    setState(load(uid))
    const reload = () => setState(load(uid))
    const onStorage = (e) => { if (!e.key || e.key === key(uid)) reload() }
    window.addEventListener(EVT, reload)
    window.addEventListener('storage', onStorage)
    return () => { window.removeEventListener(EVT, reload); window.removeEventListener('storage', onStorage) }
  }, [uid])
  const update = useCallback((patch) => {
    const next = { ...load(uid), ...patch }
    save(uid, next)
    setState(next)
    window.dispatchEvent(new Event(EVT))
  }, [uid])
  return {
    enabled: state.enabled,
    dismissed: state.dismissed,
    recommended: !!defaults.soundCondition,
    setEnabled: (v) => update({ enabled: !!v }),
    dismiss: () => update({ dismissed: true }),
  }
}
