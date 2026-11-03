import { useCallback, useRef, useState } from 'react'
import { learningAPI } from '../api'
import { fetchVisemeFrames, createLatest } from '../lib/visemeLoad'

/**
 * 입모양 받기 + 실패 표시. 화면이 가진 setFrames를 그대로 쓴다.
 *  - load(text): 프레임을 비우고 받는다. 실패하면 error가 true(안내와 '다시 받기'를 보인다). 늦은 응답은 버린다.
 *  - retry(): 마지막 글로 다시 받는다.
 *  - cancel(): 진행 중인 받기를 버린다(화면을 떠나거나 글이 바뀔 때).
 */
export default function useVisemeLoad(setFrames) {
  const [error, setError] = useState(false)
  const latest = useRef(null)
  if (!latest.current) latest.current = createLatest()
  const lastText = useRef(null)

  const load = useCallback(async (text) => {
    const id = latest.current.next()
    lastText.current = text
    setFrames([])
    setError(false)
    const r = await fetchVisemeFrames((t) => learningAPI.getVisemes(t), text)
    if (!latest.current.isCurrent(id)) return
    if (r.ok) setFrames(r.frames)
    else setError(true)
  }, [setFrames])

  const retry = useCallback(() => { if (lastText.current != null) load(lastText.current) }, [load])
  const cancel = useCallback(() => { latest.current.cancel() }, [])
  return { error, load, retry, cancel }
}
