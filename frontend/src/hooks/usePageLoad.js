import { useEffect, useState } from 'react'

/** 화면 조회의 대기·실패·재시도와 떠난 화면의 응답 무시.
 * 요청 묶음과 결과 반영은 화면이 정한다. 캐시·자동 재시도·추가 요청은 하지 않는다.
 * deps가 바뀌거나 retry를 누를 때만 다시 실행한다.
 */
export default function usePageLoad(load, onData, deps = []) {
  const [loadState, setLoadState] = useState('loading')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let on = true
    setLoadState('loading')
    load().then((data) => {
      if (!on) return
      onData(data)
      setLoadState('ready')
    }).catch(() => { if (on) setLoadState('error') })
    return () => { on = false }
  }, [reload, ...deps])
  const retry = () => setReload((n) => n + 1)
  return { loadState, retry }
}
