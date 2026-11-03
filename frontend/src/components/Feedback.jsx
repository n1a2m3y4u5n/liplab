import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation } from 'react-router-dom'
import api from '../api'
import useStore from '../store/useStore'
import { SUS_QUESTIONS, SUS_LABELS, screenName } from '../lib/feedback'
import Modal from './Modal'

const context = () => ({ route: window.location.pathname, width: Math.min(20000, window.innerWidth), height: Math.min(20000, window.innerHeight) })

export default function Feedback() {
  const { pathname } = useLocation()
  const token = useStore(s => s.token)
  const [enabled, setEnabled] = useState(false)
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [state, setState] = useState('')
  const [busy, setBusy] = useState(false)
  const [slots, setSlots] = useState([])
  useEffect(() => { api.get('/events/status').then(r => setEnabled(r.data.enabled)).catch(() => {}) }, [])
  useEffect(() => { setOpen(false); setText(''); setState('') }, [pathname, token])
  // 셸이 늦게 나타나는 경로에서도 버튼은 헤더/메뉴 안에 둔다.
  useEffect(() => {
    if (!enabled || !token) return undefined
    const update = () => {
      const next = [...document.querySelectorAll('[data-feedback-slot]')]
      setSlots(prev => prev.length === next.length && prev.every((el, i) => el === next[i]) ? prev : next)
    }
    update()
    const observer = new MutationObserver(update)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [enabled, token, pathname])
  if (!enabled || !token || pathname.startsWith('/admin/')) return null
  const send = async e => {
    e.preventDefault(); setBusy(true)
    try {
      const r = await api.post('/feedback', { kind: 'report', text, ...context() })
      if (!r.data.accepted) throw new Error()
      setOpen(false); setText(''); setState('피드백을 보냈어요.')
    } catch { setState('보내지 못했어요. 다시 시도해 주세요.') }
    finally { setBusy(false) }
  }
  const trigger = <div className="inline-flex min-w-0 flex-col gap-1">
    <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open} aria-haspopup="dialog" className="min-h-11 rounded-full px-3 py-2 text-[13px] font-medium text-ink-muted hover:bg-surface-sunken hover:text-ink">피드백</button>
    {!open && state && <span role="status" className="max-w-[12em] text-xs text-ink-muted">{state}</span>}
  </div>
  return <><SusCheck />
    {slots.length ? slots.map((slot, i) => createPortal(trigger, slot, `feedback-${i}`)) : <aside className="flex justify-end px-4 pb-[calc(var(--tabbar-h)+18px+env(safe-area-inset-bottom))] pt-3 lg:pb-4">{trigger}</aside>}
    <Modal open={open} onClose={() => setOpen(false)} title="피드백">
      <form onSubmit={send} className="flex min-w-0 flex-col gap-3 text-sm">
      <label htmlFor="feedback-text">피드백 · {screenName(pathname)}</label>
      <textarea id="feedback-text" autoFocus required maxLength={500} value={text} onChange={e => setText(e.target.value)} placeholder="개인정보는 쓰지 마세요 (최대 500자)" className="border p-2" />
      <p role="status">{state}</p>
      <button disabled={busy || !text.trim()} type="submit" className="btn-primary">보내기</button>
      <button type="button" onClick={() => setOpen(false)} className="btn-secondary">닫기</button>
      </form>
    </Modal>
  </>
}

export function SusCheck() {
  const token = useStore(s => s.token)
  const [shown, setShown] = useState(false)
  const [answers, setAnswers] = useState(Array(10).fill(0))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const requested = useRef('')
  const dialog = useRef(null)
  useEffect(() => { if (shown) dialog.current?.showModal() }, [shown])
  useEffect(() => {
    const claim = () => {
      const day = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
      const key = `${token}:${day}`
      if (requested.current === key) return
      requested.current = key
      api.post('/feedback', { kind: 'prompt', ...context() }).then(r => {
        if (r.data.accepted && useStore.getState().token === token) setShown(true)
      }).catch(() => { requested.current = '' })
    }
    setShown(false); setAnswers(Array(10).fill(0)); setError('')
    window.addEventListener('liplab:session-complete', claim)
    return () => window.removeEventListener('liplab:session-complete', claim)
  }, [token])
  if (!shown) return null
  const send = async kind => {
    if (kind === 'skip') {
      setShown(false)
      api.post('/feedback', { kind, ...context() }).catch(() => {})
      return
    }
    setBusy(true); setError('')
    try {
      await api.post('/feedback', { kind, ...(kind === 'sus' ? { answers } : {}), ...context() })
      setShown(false)
    } catch { setError('보내지 못했어요. 다시 시도해 주세요.') }
    finally { setBusy(false) }
  }
  return <dialog ref={dialog} aria-labelledby="sus-title" onCancel={e => { e.preventDefault(); send('skip') }} className="max-h-[85vh] w-[95vw] max-w-[640px] overflow-y-auto rounded-xl border bg-white p-4 backdrop:bg-black/30">
    <h2 id="sus-title" className="font-bold">오늘의 앱 사용 경험</h2>
    <form onSubmit={e => { e.preventDefault(); send('sus') }}>
      {SUS_QUESTIONS.map((question, i) => <fieldset key={question} className="my-4">
        <legend>{i + 1}. {question}</legend>
        <div className="flex flex-wrap gap-3">{SUS_LABELS.map((label, j) => <label key={label} className="text-sm">
          <input type="radio" required name={`sus-${i}`} value={j + 1} checked={answers[i] === j + 1}
            onChange={() => setAnswers(v => v.map((n, k) => k === i ? j + 1 : n))} /> {j + 1} {label}
        </label>)}</div>
      </fieldset>)}
      <p role="status">{error}</p>
      <button type="submit" disabled={busy || answers.some(v => !v)} className="mr-5">보내기</button>
      <button type="button" disabled={busy} onClick={() => send('skip')}>건너뛰기</button>
    </form>
  </dialog>
}
