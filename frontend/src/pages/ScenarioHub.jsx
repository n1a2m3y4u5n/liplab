import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'

/**
 * 상황별 시나리오 (Figma 225:183 AI 대화 · 407:140 문장 테스트) — 셸 안의 피커.
 * 상황을 직접 적고(407:82 '어떤 상황인가요?') 난이도(407:88)와 연습 방법(407:103)을 고른 뒤 '시작하기'(407:138)로 들어간다.
 *  - 문장 테스트: 기존 문장 학습(/practice). AI 대화: 1:1이면 기존 대화 실전(/conversation), 여러 명이면 다자 대화
 *    (/learn/conversation-multi?speakers=2~4&situation=)로 — 인원은 나를 뺀 상대 수(407:131).
 *  - 잠금은 예전과 같다: 문장 테스트는 3단계, 1:1 대화는 4단계가 열려야 한다. 다자 대화는 연습 탭처럼 잠그지 않는다.
 *  - 회차 히스토리 등에서 ?situation=은행 으로 들어오면 그 상황을 입력칸에 채워 이어서 연습하게 한다.
 */
const QUESTION_TYPES = ['test', 'test-multiple', 'essay']
// 카드 틀(407:82) — 2px 테두리, r18, p20, 머리-본문 14
const CARD = 'flex w-full flex-col gap-3.5 rounded-18 border-2 border-line bg-white p-[18px] lg:p-5'
const LOCK_HINT = { practice: '단어 학습을 완료하면 문장 학습이 열려요.', conversation: '문장 학습을 완료하면 대화 실전이 열려요.' }
const MODES = [
  { key: 'practice', title: '문장 테스트', sub: '정해진 문장을 읽고 답해요' },
  { key: 'conversation', title: 'AI 대화', sub: '상황에 맞춰 실시간으로 대화해요' },
]
const PARTNERS = [{ key: 'one', label: '1 : 1 대화' }, { key: 'multi', label: '여러 명 대화' }]
// 선택 버튼(난이도 407:93 / 인원 407:134): 고른 것은 틴트+2.5px 보라 테두리, 나머지는 흰 바탕+3D 하단 테두리
const PICK_ON = 'border-[2.5px] border-primary-500 bg-primary-100 text-primary-700'
const PICK_OFF = 'border-2 border-b-5 border-line bg-white text-ink transition-all hover:border-primary-300 active:translate-y-[1px] active:border-b-2'

function shuffledTypes(length) {
  return Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length])
    .sort(() => Math.random() - 0.5)
}

export default function ScenarioHub() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const [situation, setSituation] = useState((searchParams.get('situation') || '').trim())
  const [level, setLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [recommended, setRecommended] = useState(null)
  const [locks, setLocks] = useState({ practice: false, conversation: false })
  const [mode, setMode] = useState('practice')
  const [partner, setPartner] = useState('one')
  const [people, setPeople] = useState(2)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')   // 브라우저 alert 대신 쓰는 인앱 안내(맥락 유지)
  const inputRef = useRef(null)

  const levelTouched = useRef(false)   // 유저가 난이도를 직접 고르면 추천값이 덮어쓰지 않게

  useEffect(() => {
    if (!notice) return undefined
    const t = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  useEffect(() => {
    curriculumAPI.getRecommendedLevel()
      .then((result) => {
        setRecommended(result.recommended_level)
        if (!levelTouched.current) setLevel(result.recommended_level)
      })
      .catch(() => {})
    curriculumAPI.getStages()
      .then((data) => {
        const stages = data?.stages || []
        const locked = (number) => {
          const stage = stages.find((item) => item.stage === number)
          return !!stage && ['locked', 'coming_soon'].includes(stage.status)
        }
        setLocks({ practice: locked(3), conversation: locked(4) })
      })
      .catch(() => {})
  }, [])

  const start = async () => {
    const text = situation.trim()
    if (!text) {
      setNotice('어떤 상황인지 적어 주세요.')
      inputRef.current?.focus()
      return
    }
    if (mode === 'conversation' && partner === 'multi') {
      navigate(`/learn/conversation-multi?speakers=${people}&situation=${encodeURIComponent(text)}`)
      return
    }
    if (locks[mode]) {
      setNotice(LOCK_HINT[mode])
      return
    }
    setLoading(true)
    try {
      const scenario = await learningAPI.getScenario(text, level)
      if (mode === 'practice') scenario.qTypes = shuffledTypes(scenario.sentences.length)
      setScenario(scenario, 'test')
      navigate(mode === 'practice' ? '/practice' : '/conversation')
    } catch (error) {
      console.error(error)
      setNotice('실전 문장을 준비하지 못했어요. 다시 시도해주세요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppShell active="practice" title="상황별 시나리오" description="상황을 고르면 그에 맞는 문장이 나와요">
      {notice && (
        <div role="status" aria-live="polite"
          className="fixed left-1/2 top-4 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 shadow-lg">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice('')} aria-label="안내 닫기" className="text-amber-500 hover:text-amber-700">✕</button>
        </div>
      )}
      {/* 어떤 상황인가요? (407:82) */}
      <section className={CARD}>
        <label htmlFor="scenario-situation" className="text-[17px] font-bold leading-figma text-ink">어떤 상황인가요?</label>
        <input id="scenario-situation" ref={inputRef} value={situation} onChange={(e) => setSituation(e.target.value)} maxLength={30}
          onKeyDown={(e) => { if (e.key === 'Enter') start() }} placeholder="예: 카페에서 음료 주문하기"
          className="h-14 w-full rounded-14 border-2 border-line bg-white px-4 text-[15.5px] text-ink outline-none transition placeholder:text-ink-ghost focus:border-primary-500" />
        <p className="text-[13px] leading-figma text-ink-muted">상황을 적으면 그 상황에 맞는 문장과 대화를 만들어드려요.</p>
      </section>

      {/* 난이도 (407:88) */}
      <section className={CARD}>
        <div className="flex items-center justify-between font-bold leading-figma">
          <p className="text-[17px] text-ink">난이도</p>
          <span className="text-[13px] text-primary-500">추천 {recommended || level}단계</span>
        </div>
        <div className="flex gap-2.5" role="radiogroup" aria-label="난이도">
          {[1, 2, 3, 4, 5].map((item) => (
            <button key={item} type="button" role="radio" aria-checked={level === item} aria-label={`${item}단계`}
              onClick={() => { levelTouched.current = true; setLevel(item) }}
              className={`flex-1 rounded-14 py-[15px] text-[17px] font-bold leading-figma ${level === item ? PICK_ON : PICK_OFF}`}>
              {item}
            </button>
          ))}
        </div>
      </section>

      {/* 어떻게 연습할까요? (407:103) — 모드는 라디오 카드(407:107 / 407:112), AI 대화면 상대·인원 옵션(407:119) */}
      <section className={CARD}>
        <p className="text-[17px] font-bold leading-figma text-ink">어떻게 연습할까요?</p>
        <div className="flex flex-col gap-3 sm:flex-row" role="radiogroup" aria-label="연습 방법">
          {MODES.map((m) => {
            const active = mode === m.key
            const locked = m.key === 'practice' && locks.practice
            return (
              <button key={m.key} type="button" role="radio" aria-checked={active} disabled={locked}
                title={locked ? LOCK_HINT.practice : undefined} onClick={() => setMode(m.key)}
                className={`flex flex-1 flex-col gap-1.5 rounded-16 px-[18px] py-4 text-left leading-figma disabled:opacity-50 ${active ? PICK_ON : PICK_OFF}`}>
                <span className="flex w-full items-center justify-between">
                  <span className={`text-[16.5px] font-bold ${active ? 'text-primary-700' : 'text-ink'}`}>{m.title}</span>
                  {active
                    ? <img src="/ui/lp-407-115-radio-on.svg" alt="" className="size-5 shrink-0" />
                    : <span className="size-5 shrink-0 rounded-full border-2 border-line" />}
                </span>
                <span className={`text-[12.5px] ${active ? 'text-primary-700 opacity-80' : 'text-ink-muted'}`}>
                  {locked ? LOCK_HINT.practice : m.sub}
                </span>
              </button>
            )
          })}
        </div>

        {mode === 'conversation' && (
          <>
            <div className="h-[1.5px] w-full bg-line" />
            <div className="flex flex-col gap-2.5">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 leading-figma">
                <span className="text-[14.5px] font-bold text-ink">대화 상대</span>
                <span className="text-[12.5px] text-ink-muted">여러 명이면 누가 말하는지도 함께 찾아야 해요</span>
              </p>
              <div className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1" role="radiogroup" aria-label="대화 상대">
                {PARTNERS.map((p) => (
                  <button key={p.key} type="button" role="radio" aria-checked={partner === p.key} onClick={() => setPartner(p.key)}
                    className={`flex-1 rounded-10 py-[11px] text-[14.5px] font-bold leading-figma transition ${
                      partner === p.key ? 'bg-white text-primary-500 shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]' : 'text-ink-muted'}`}>
                    {p.label}
                  </button>
                ))}
              </div>
              {partner === 'one' && locks.conversation && (
                <p className="text-[12.5px] leading-figma text-ink-muted">{LOCK_HINT.conversation}</p>
              )}
              {partner === 'multi' && (
                <>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pt-1 leading-figma">
                    <span className="text-[14.5px] font-bold text-ink">인원</span>
                    <span className="text-[12.5px] text-ink-muted">나를 포함하지 않은 상대 수예요</span>
                  </p>
                  <div className="flex gap-2.5" role="radiogroup" aria-label="인원">
                    {[2, 3, 4].map((n) => (
                      <button key={n} type="button" role="radio" aria-checked={people === n} onClick={() => setPeople(n)}
                        className={`flex-1 rounded-13 py-[13px] text-[15.5px] font-bold leading-figma ${people === n ? PICK_ON : PICK_OFF}`}>
                        {n}명
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </section>

      {/* 시작하기 (407:138) */}
      <button type="button" onClick={start} disabled={loading} aria-busy={loading}
        className="btn-primary btn-lg w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]">
        {loading ? '준비 중…' : '시작하기'}
      </button>
    </AppShell>
  )
}
