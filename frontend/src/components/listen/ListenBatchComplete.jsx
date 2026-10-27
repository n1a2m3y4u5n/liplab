import { useEffect, useRef, useState } from 'react'
import { authAPI, listenAPI, tasksAPI } from '../../api'
import useStore from '../../store/useStore'
import { quotaView, batchNext } from '../../lib/listenQuota'
import { QuotaBar, QuotaRing } from './QuotaProgress'
import { useListenKeys } from './usePlayer'

export default function ListenBatchComplete({ result, data, onExit, onMore, onStage }) {
  const [fresh, setFresh] = useState(null)
  const [task, setTask] = useState(null)
  const heading = useRef(null)
  const user = useStore((s) => s.user)
  useEffect(() => {
    heading.current?.focus()
    let live = true
    listenAPI.getCurriculum().then((d) => { if (live) setFresh(d.stages?.find((s) => s.stage === data.stage)?.quota) }).catch(() => {})
    tasksAPI.get().then((d) => { if (live) setTask((d.daily || d.tasks || []).find((t) => t.key === 'listen_15')) }).catch(() => {})
    authAPI.getMe().then((u) => { if (u) useStore.getState().updateUser(u) }).catch(() => {})
    return () => { live = false }
  }, [data.stage])
  const quota = result.reward?.quota || fresh || data.quota
  const q = quotaView(quota)
  const action = batchNext({ quota, stage: data.stage, mastered: result.mastered })
  const next = { label: action.label, onClick: action.kind === 'stage' ? () => onStage(action.stage) : action.kind === 'exit' ? onExit : onMore }
  useListenKeys({ onEnter: next.onClick })
  return <div className="fixed inset-0 z-50 overflow-auto bg-page" data-track="listen">
    <div className="mx-auto flex min-h-[100dvh] max-w-[640px] flex-col items-center gap-5 px-[18px] py-10 lg:justify-center">
      <div role="img" aria-label={`오늘 몫 ${q.done}/${q.total}`} className="relative size-[136px] shrink-0"><QuotaRing quota={quota} className="absolute inset-0 size-full" /><img src="/ui/listen-node-current.svg" alt="" className="absolute inset-4 size-[104px]" />{q.met && <img src="/ui/listen-node-check-badge.svg" alt="완료" className="absolute bottom-1 right-1 size-9" />}</div>
      <div className="text-center"><p className="text-[15px] font-bold text-track-dark">{data.title}</p><h1 tabIndex={-1} ref={heading} className="mt-1 text-[30px] font-black outline-none">오늘 몫 {q.filled} / {q.total}</h1></div>
      <div className="grid w-full grid-cols-3 gap-2">
        {[['맞힌 문제', result.summary ? `${result.summary.heard?.length || 0} / 6` : `${result.c} / ${result.n}`, 'text-ink'], ['경험치', `★ +${result.reward?.xp || 0}`, 'text-stat-xp'], ['연속 학습', `♨ ${result.reward?.streak ?? user?.streak_count ?? 0}일`, 'text-stat-streak']].map(([label, value, color]) => <div key={label} className="rounded-18 border-2 border-line bg-white px-1 py-4 text-center"><p className="text-[12px] font-bold text-ink-muted">{label}</p><p className={`mt-1 text-[21px] font-bold ${color}`}>{value}</p></div>)}
      </div>
      <div className="flex w-full flex-col gap-3 rounded-18 border-2 border-line bg-white p-4"><div className="flex items-center justify-between text-[14px] font-bold"><span>소리 듣기 오늘 몫</span><span>{task?.cur ?? '–'} / {task?.total ?? 2}</span></div>{task && <QuotaBar quota={{ today_n: task.cur, quota_n: task.total }} />}</div>
      {result.mastered && <p className="rounded-14 bg-track-tint px-4 py-3 text-[16px] font-bold text-track-dark">✓ {data.title} 숙달</p>}
      {result.skipped > 0 && <p role="status" className="text-[14px] text-ink-muted">소리 미수신 {result.skipped}문제</p>}
      <div className="mt-auto flex w-full flex-col gap-2.5 pt-5 lg:mt-0"><button className="btn-primary btn-lg w-full" onClick={next.onClick}>{next.label}</button><button className="btn-secondary btn-lg w-full text-track-dark" onClick={q.met ? onMore : onExit}>{q.met ? '한 묶음 더 하기' : '학습 화면으로'}</button></div>
    </div>
  </div>
}
