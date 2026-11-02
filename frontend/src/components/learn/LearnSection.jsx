import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../AppShell'
import LearnHeader from './LearnHeader'
import { LearnCard, LISTEN_CARDS } from './LearnCard'
import { sectionCards } from '../../lib/learnSections'
import { curriculumAPI, listenAPI } from '../../api'
import { modeAvailability } from '../../lib/listenFlow'
import { TRACK_LABEL } from '../../lib/iaLabels'
export default function LearnSection({ track, section }) {
  const navigate = useNavigate()
  const [avail, setAvail] = useState({})
  const [wordOpen, setWordOpen] = useState(false)
  useEffect(() => {
    let on = true
    if (track === 'listen') listenAPI.practiceModes().then((m) => { if (on) setAvail(modeAvailability(Array.isArray(m) ? m : m?.modes)) }).catch(() => {})
    if (track === 'read') curriculumAPI.getStages().then((d) => { if (on) setWordOpen((d.stages || []).some((s) => s.stage === 2 && !['locked', 'coming_soon'].includes(s.status))) }).catch(() => {})
    return () => { on = false }
  }, [track])
  const offList = LISTEN_CARDS.filter((c) => avail[c.key] && !avail[c.key].available)
  const reasons = [...new Set(offList.map((c) => avail[c.key].reason || ''))]
  const shared = offList.length > 1 && reasons.length === 1 ? reasons[0] : null   // 같은 이유면 묶음 위에 한 번만
  const offReason = (key) => (avail[key] && !avail[key].available ? (shared != null ? true : avail[key].reason || '곧 열려요') : null)
  const cards = track === 'listen' ? LISTEN_CARDS.filter((c) => section === 'res' ? c.key === 'classroom' : c.key !== 'classroom') : sectionCards(track, section, wordOpen)
  return <AppShell active="learn"><div data-track={track} className="mx-auto flex w-full max-w-[752px] flex-col gap-4">
    <LearnHeader /><h1 className="sr-only">{TRACK_LABEL[track]} · {section === 'res' ? '자료' : '자유 연습'}</h1>
    {track === 'listen' && section === 'free' && shared != null && <div className="flex flex-wrap items-center justify-between gap-2 rounded-14 bg-surface-sunken px-4 py-3"><p className="text-sm text-ink-muted">{shared || '지금은 열 수 없어요.'}</p>{/소리 확인/.test(shared) && <button className="btn-secondary min-h-11 px-4" onClick={() => navigate('/learn/listening?stage=0')}>소리 확인 하러 가기</button>}</div>}
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{cards.map((c) => <LearnCard key={c.key} card={c} off={track === 'listen' ? offReason(c.key) : null} onClick={() => navigate(c.to)} />)}</div>
  </div></AppShell>
}
