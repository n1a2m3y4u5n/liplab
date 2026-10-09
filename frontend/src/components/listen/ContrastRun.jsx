import { useCallback, useMemo, useState } from 'react'
import { pct, skippedNote } from '../../lib/listenFlow'
import { fmtDuration } from '../../lib/listenView'
import AxDrill from './AxDrill'
import { TaskEnd } from './ListenComplete'
import WordId from './WordId'

/**
 * 소리 짝 집중 연습 한 묶음. 서버가 같다·다르다와 낱말 고르기를 섞어 주므로(계약 1.1절) 종류별로 묶어(lib/listenFlow.contrastSegments)
 * 같다·다르다 → 낱말 고르기 순서로 잇고, 끝에 합친 결과를 보인다. 묶음 사이에는 전환 화면 없이 바로 넘어간다(같은 대조라 한 연습이다).
 * 진행바는 묶음 전체 문항 기준이다.
 */
const TASK = { ax: AxDrill, word_id: WordId }

export default function ContrastRun({ segments, data, label, onProgress, finish, ...task }) {
  const [idx, setIdx] = useState(0)
  const [results, setResults] = useState([])
  const total = segments.reduce((a, s) => a + s.items.length, 0)
  const offset = segments.slice(0, idx).reduce((a, s) => a + s.items.length, 0)
  const progress = useCallback((cur, _n, lbl = null) => onProgress(offset + cur, total, lbl), [onProgress, offset, total])
  const next = useMemo(() => ({ onDone: (r) => { setResults((rs) => [...rs, r]); setIdx((i) => i + 1) } }), [])
  if (idx >= segments.length) {
    const n = results.reduce((a, r) => a + (r?.n || 0), 0)
    const c = results.reduce((a, r) => a + (r?.c || 0), 0)
    const skipped = results.reduce((a, r) => a + (r?.skipped || 0), 0)
    const elapsed = results.reduce((a, r) => a + (r?.elapsed || 0), 0)
    return (
      <TaskEnd finish={finish} result={{ stage: null, n, c, skipped, mastered: false, elapsed }}
        title={n ? '이번 묶음을 마쳤어요' : '소리가 아직 준비되지 않았어요'} sub={label ? `${label} 대조를 연습했어요.` : null}
        stats={n ? [{ label: '정답률', value: pct(c, n), note: `${n}문제 중 ${c}문제`, main: true }, { label: '걸린 시간', value: fmtDuration(elapsed) }] : []}
        notes={[skippedNote(skipped)]} />
    )
  }
  const seg = segments[idx]
  const Task = TASK[seg.task]
  return <Task key={idx} {...task} data={{ ...data, items: seg.items, levels: undefined, level: seg.items[0]?.level }} onProgress={progress} finish={next} />
}
