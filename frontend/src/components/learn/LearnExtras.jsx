import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CardIcon, LISTEN_CARDS } from './LearnCard'
import { Row, RowList, SectionTitle } from './LearnRows'
import { sectionCards } from '../../lib/learnSections'
import { curriculumAPI, listenAPI } from '../../api'
import { modeAvailability } from '../../lib/listenFlow'

/**
 * 학습 탭 아래(데스크톱은 오른쪽 열)의 '자유 연습'과 '자료'(11/03). 예전에는 하위 탭 두 개였고 각 탭에 카드가 2~3장뿐이라
 * 화면 대부분이 비었다. 같은 카드 목록(lib/learnSections · LISTEN_CARDS)과 열림 조건을 그대로 쓰고 모양만 행 목록으로 바꿨다.
 * id="learn-free"·"learn-res"는 ?section=free·res 링크가 스크롤해 오는 자리다.
 */
export default function LearnExtras({ track }) {
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

  const groups = [
    { id: 'learn-free', title: '자유 연습', cards: track === 'listen' ? LISTEN_CARDS.filter((c) => c.key !== 'classroom') : sectionCards(track, 'free', wordOpen) },
    { id: 'learn-res', title: '자료', cards: track === 'listen' ? LISTEN_CARDS.filter((c) => c.key === 'classroom') : sectionCards(track, 'res', wordOpen) },
  ]

  return groups.map((g) => (
    <section key={g.id} aria-labelledby={g.id} className="flex scroll-mt-6 flex-col gap-2.5">
      <SectionTitle id={g.id}>{g.title}</SectionTitle>
      {track === 'listen' && g.id === 'learn-free' && shared != null && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-14 bg-surface-sunken px-4 py-3">
          <p className="text-sm text-ink-muted">{shared || '지금은 열 수 없어요.'}</p>
          {/소리 확인/.test(shared) && <button type="button" className="btn-secondary min-h-11 px-4" onClick={() => navigate('/learn/listening?stage=0')}>소리 확인 하러 가기</button>}
        </div>
      )}
      <RowList label={g.title}>
        {g.cards.map((c) => {
          const off = track === 'listen' ? offReason(c.key) : null
          return (
            <Row key={c.key}
              lead={<span className={`flex size-10 shrink-0 items-center justify-center ${off ? 'opacity-40 grayscale' : ''}`}><CardIcon card={c} /></span>}
              title={c.title}
              desc={typeof off === 'string' ? off : c.desc}
              meta={off ? '잠김' : null}
              metaClass="text-ink-faint"
              onClick={off ? undefined : () => navigate(c.to)} />
          )
        })}
      </RowList>
    </section>
  ))
}
