import { useCallback, useEffect, useRef, useState } from 'react'
import { learningAPI } from '../api'

/**
 * 레슨 문항 북마크를 서버(/api/bookmarks)에 저장한다 — 복습 탭·/review/saved에 그대로 나온다.
 * 같은 문장·트랙이 이미 북마크돼 있으면 켜진 상태로 시작한다(목록은 페이지마다 한 번 읽고, 저장·삭제 뒤 다시 읽는다).
 *
 *   const [saved, toggle] = useBookmark(text, { situation: '단어 독화', domain: 'read' })
 */
export default function useBookmark(text, { situation = '', level = 1, domain = 'read' } = {}) {
  const [id, setId] = useState(null)
  const listRef = useRef(null)          // 이 페이지에서 읽은 북마크 목록(Promise)
  const busyRef = useRef(false)
  // 지금 보고 있는 문항(트랙·문장). 저장·삭제 응답이 늦게 오면 그 사이 다음 문항으로 넘어갔을 수 있어, 응답이 온 뒤
  // 문항이 그대로일 때만 표시를 바꾼다. 예전에는 빨리 계속하기를 누르면 다음 문항이 저장된 것으로 보였고,
  // 거기서 끄면 앞 문항의 북마크가 지워졌다.
  const keyRef = useRef('')
  keyRef.current = `${domain}\u0000${text ?? ''}`

  useEffect(() => {
    let on = true
    setId(null)
    if (!text) return undefined
    if (!listRef.current) listRef.current = learningAPI.getBookmarks(domain).catch(() => [])
    listRef.current.then((list) => {
      const arr = Array.isArray(list) ? list : (list?.items || [])
      const hit = arr.find((b) => b.sentence === text)
      if (on && hit) setId(hit.id)
    })
    return () => { on = false }
  }, [text, domain])

  const toggle = useCallback(async () => {
    if (!text || busyRef.current) return
    busyRef.current = true
    const key = `${domain}\u0000${text}`
    try {
      if (id != null) {
        await learningAPI.removeBookmark(id)
        if (keyRef.current === key) setId(null)
      } else {
        const r = await learningAPI.addBookmark(text, situation, level, domain)
        if (keyRef.current === key) setId(r?.id ?? null)
      }
    } catch { /* 저장 실패는 표시를 바꾸지 않는다 */ } finally {
      listRef.current = null             // 목록이 바뀌었으니 다음 문항에서 다시 읽는다
      busyRef.current = false
    }
  }, [text, id, situation, level, domain])

  return [id != null, toggle]
}
