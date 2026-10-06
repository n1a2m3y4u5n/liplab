import { useCallback, useEffect, useRef, useState } from 'react'
import { curriculumAPI } from '../api'
import { probeInsertAfter, shouldOpenProbes } from '../lib/measurement'

/**
 * 숙달 지연 탐침(C16)을 레슨에 끼우는 훅. 레슨을 시작할 때 서버에서 오늘 이 레슨 몫(비율 상한 안)의 탐침을 받아 두고,
 * 레슨 가운데 문항 뒤에 한 번 연다. 탐침이 없거나 받지 못하면 아무것도 하지 않는다(레슨을 막지 않는다).
 *
 *   const probes = useMasteryProbes(QUIZ_LEN)
 *   const next = () => { if (probes.take(qNum)) return; advance() }      // 계속하기
 *   if (probes.open) return <MasteryProbeBlock items={probes.items} onDone={() => { probes.finish(); advance() }} />
 *   const restart = () => { probes.reload(); ... }                          // 새 레슨
 */
export default function useMasteryProbes(lessonLen) {
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const shownRef = useRef(false)
  const seqRef = useRef(0)
  const insertAfter = probeInsertAfter(lessonLen)

  const reload = useCallback(() => {
    shownRef.current = false
    setOpen(false)
    setItems([])
    const seq = ++seqRef.current
    curriculumAPI.getMasteryProbes(lessonLen)
      .then((d) => { if (seq === seqRef.current) setItems(Array.isArray(d?.items) ? d.items : []) })
      .catch(() => {})
  }, [lessonLen])

  useEffect(() => { reload() }, [reload])

  /** qNum 문항을 마친 뒤 탐침을 열면 true(호출부는 다음 문항으로 넘어가지 않는다). */
  const take = useCallback((qNum) => {
    if (!shouldOpenProbes({ qNum, insertAfter, count: items.length, shown: shownRef.current })) return false
    shownRef.current = true
    setOpen(true)
    return true
  }, [insertAfter, items.length])

  const finish = useCallback(() => setOpen(false), [])

  return { items, open, take, finish, reload, insertAfter }
}
