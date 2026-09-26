import { Fragment, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'

/**
 * 상황별 시나리오 (Figma 225:183 AI 대화 · 407:140 문장 테스트): 셸 안의 설정 폼 하나 + 시작 버튼 하나.
 * 9/26 변경 내역 §5: 카드 하나(447:82) 안에 구분선으로 '어떤 상황인가요? → 난이도 → 어떻게 연습할까요?'를 나누고,
 * 카드 아래 전체 폭 '시작하기'(407:138)로 들어간다. 상황 입력이 비어 있으면 시작 버튼은 비활성이다.
 *  - 난이도는 1~5 정수에만 멈추는 슬라이더(449:85). 제목 줄 오른쪽에 'N단계 · 라벨', 아래 양 끝에 '짧고 쉬운 문장'↔'길고 빠른 대화'.
 *    (라벨·양끝 문구·아래 안내 두 줄은 변경 내역 문구다. 9/26 Figma 프레임에는 'N단계'만 있다.)
 *  - 연습 방식은 문장 테스트 / AI 대화 2개, 고른 것은 오른쪽 위 체크 동그라미(407:115). AI 대화일 때만 대화 상대(1:1 / 여러 명)가
 *    펼쳐지고, 여러 명이면 인원(2~4명, 나를 뺀 상대 수, 407:131)을 고른다. 문장 테스트면 이 영역을 렌더링하지 않는다.
 *  - 문장 테스트: 기존 문장 학습(/practice). AI 대화: 1:1이면 기존 대화 실전(/conversation), 여러 명이면 여러 명 대화 화면
 *    (/learn/conversation-multi?speakers=2~4&situation=). 연습 탭의 다자 대화 기능을 이것이 대신한다(§2).
 *  - 잠금은 예전과 같다: 문장 테스트는 3단계, 1:1 대화는 4단계가 열려야 한다. 여러 명 대화는 잠그지 않는다.
 *  - 난이도는 추천 단계(/curriculum/recommended-level)로 시작하고, 사용자가 움직이면 추천값이 덮어쓰지 않는다.
 *  - 회차 히스토리 등에서 ?situation=은행 으로 들어오면 그 상황을 입력칸에 채워 이어서 연습하게 한다.
 *  - ?mode=conversation 이면 연습 방법을 'AI 대화'로 골라 둔다(학습 경로 4단계 '학습 시작하기'가 여기로 온다).
 */
const QUESTION_TYPES = ['test', 'test-multiple', 'essay']
const LOCK_HINT = { practice: '단어 학습을 완료하면 문장 학습이 열려요.', conversation: '문장 학습을 완료하면 대화 실전이 열려요.' }
const MODES = [{ key: 'practice', title: '문장 테스트' }, { key: 'conversation', title: 'AI 대화' }]
const PARTNERS = [{ key: 'one', label: '1 : 1 대화' }, { key: 'multi', label: '여러 명 대화' }]
const LEVEL_LABEL = { 1: '아주 쉬움', 2: '쉬움', 3: '보통', 4: '어려움', 5: '아주 어려움' }

// 선택 카드(연습 방식 407:107/112, 인원 407:132/134): 고른 것은 틴트 + 2.5px 보라 테두리, 나머지는 흰 바탕 + 3D 하단 테두리.
// 고르면 하단 테두리가 5 → 2.5px로 얇아지므로 위 패딩을 2px 더해 높이를 맞춘다(변경 내역 §0-4).
const MODE_ON = 'border-[2.5px] border-primary-500 bg-primary-100 pb-4 pt-[18px]'
const MODE_OFF = 'border-2 border-b-5 border-line bg-white py-4 transition-colors hover:border-primary-300'
const PEOPLE_ON = 'border-[2.5px] border-primary-500 bg-primary-100 pb-[13px] pt-[15px] text-primary-700'
const PEOPLE_OFF = 'border-2 border-b-5 border-line bg-white py-[13px] text-ink transition-colors hover:border-primary-300'

function shuffledTypes(length) {
  return Array.from({ length }, (_, index) => QUESTION_TYPES[index % QUESTION_TYPES.length])
    .sort(() => Math.random() - 0.5)
}

const Divider = () => <div className="h-[1.5px] w-full shrink-0 bg-line" />

/** 난이도 슬라이더(449:85): 트랙·채움·눈금 5개·숫자·손잡이는 그림이고, 실제 입력은 투명한 range(1~5, step 1)가 받는다. */
function LevelSlider({ value, onChange }) {
  const at = (n) => `calc(16px + (100% - 32px) * ${(n - 1) / 4})`
  return (
    <div className="relative h-14 w-full">
      <div className="absolute inset-x-4 top-[18px] h-2 rounded-full bg-fill" />
      <div className="absolute left-4 top-[18px] h-2 rounded-full bg-primary-500"
        style={{ width: `max(8px, calc((100% - 32px) * ${(value - 1) / 4}))` }} />
      {[1, 2, 3, 4, 5].map((n) => (
        <Fragment key={n}>
          <img src={n <= value ? '/ui/lp-449-88-slider-tick-on.svg' : '/ui/lp-449-90-slider-tick-off.svg'} alt=""
            className="absolute top-[17px] size-2.5 -translate-x-1/2" style={{ left: at(n) }} />
          <span aria-hidden className={`absolute top-10 -translate-x-1/2 text-[12.5px] font-bold leading-figma ${n <= value ? 'text-primary-500' : 'text-ink-tick'}`}
            style={{ left: at(n) }}>{n}</span>
        </Fragment>
      ))}
      <input type="range" min={1} max={5} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))}
        aria-label="난이도" aria-valuetext={`${value}단계 · ${LEVEL_LABEL[value]}`}
        className="peer absolute inset-x-0 top-0 z-10 h-11 w-full cursor-pointer opacity-0" />
      <span aria-hidden className="pointer-events-none absolute top-[7px] size-[30px] -translate-x-1/2 rounded-full border-3 border-primary-500 bg-white shadow-knob transition-[left] duration-150 peer-focus-visible:ring-4 peer-focus-visible:ring-primary-200"
        style={{ left: at(value) }} />
    </div>
  )
}

export default function ScenarioHub() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const user = useStore((state) => state.user)
  const setScenario = useStore((state) => state.setScenario)
  const [situation, setSituation] = useState((searchParams.get('situation') || '').trim())
  const [level, setLevel] = useState(Math.min(user?.current_level || 1, 5))
  const [locks, setLocks] = useState({ practice: false, conversation: false })
  const [mode, setMode] = useState(searchParams.get('mode') === 'conversation' ? 'conversation' : 'practice')
  const [partner, setPartner] = useState('one')
  const [people, setPeople] = useState(2)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState('')   // 브라우저 alert 대신 쓰는 인앱 안내(맥락 유지)

  const levelTouched = useRef(false)   // 유저가 난이도를 직접 고르면 추천값이 덮어쓰지 않게
  const canStart = situation.trim().length > 0 && !loading

  useEffect(() => {
    if (!notice) return undefined
    const t = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  useEffect(() => {
    curriculumAPI.getRecommendedLevel()
      .then((result) => {
        if (!levelTouched.current && result?.recommended_level) setLevel(Math.min(Math.max(result.recommended_level, 1), 5))
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
    if (!text || loading) return
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
    <AppShell active="practice" title="상황별 시나리오" closeTo="/practice/hub">
      {notice && (
        <div role="status" aria-live="polite"
          className="fixed left-1/2 top-4 z-50 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 shadow-lg">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice('')} aria-label="안내 닫기" className="text-amber-500 hover:text-amber-700">✕</button>
        </div>
      )}

      {/* Card / 시나리오 설정 (447:82): 테두리 하나 안에 구분선으로 세 구역 */}
      <section className="flex w-full flex-col gap-5 rounded-18 border-2 border-line bg-white p-[18px] lg:p-[22px]">
        {/* 어떤 상황인가요? (407:82) */}
        <div className="flex flex-col gap-3.5">
          <label htmlFor="scenario-situation" className="text-[17px] font-bold leading-figma text-ink">어떤 상황인가요?</label>
          <input id="scenario-situation" value={situation} onChange={(e) => setSituation(e.target.value)} maxLength={30}
            onKeyDown={(e) => { if (e.key === 'Enter') start() }} placeholder="예: 카페에서 음료 주문하기"
            className="h-14 w-full rounded-14 border-2 border-line bg-white px-4 text-[15.5px] text-ink outline-none transition placeholder:text-placeholder focus:border-primary-500" />
        </div>

        <Divider />

        {/* 난이도 (407:88) */}
        <div className="flex flex-col gap-3.5">
          <div className="flex items-center justify-between text-[17px] font-bold leading-figma">
            <p className="text-ink">난이도</p>
            <p className="text-primary-500">{level}단계 · {LEVEL_LABEL[level]}</p>
          </div>
          <div className="flex flex-col gap-1">
            <LevelSlider value={level} onChange={(v) => { levelTouched.current = true; setLevel(v) }} />
            <div className="flex justify-between text-[12.5px] leading-figma text-ink-muted">
              <span>짧고 쉬운 문장</span>
              <span>길고 빠른 대화</span>
            </div>
          </div>
        </div>

        <Divider />

        {/* 어떻게 연습할까요? (407:103) */}
        <div className="flex flex-col gap-3.5">
          <p className="text-[17px] font-bold leading-figma text-ink">어떻게 연습할까요?</p>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch" role="radiogroup" aria-label="연습 방법">
            {MODES.map((m) => {
              const active = mode === m.key
              const locked = m.key === 'practice' && locks.practice
              return (
                <button key={m.key} type="button" role="radio" aria-checked={active} aria-label={m.title} disabled={locked}
                  title={locked ? LOCK_HINT.practice : undefined} onClick={() => setMode(m.key)}
                  className={`flex flex-1 items-center justify-between rounded-16 px-[18px] text-left disabled:opacity-50 ${active ? MODE_ON : MODE_OFF}`}>
                  <span className={`text-[16.5px] font-bold leading-[1.5] ${active ? 'text-primary-700' : 'text-ink'}`}>{m.title}</span>
                  {active
                    ? <img src="/ui/lp-407-115-radio-on.svg" alt="" className="size-5 shrink-0" />
                    : <span className="size-5 shrink-0 rounded-full border-2 border-line" />}
                </button>
              )
            })}
          </div>
          {locks.practice && <p className="text-[12.5px] leading-figma text-ink-muted">{LOCK_HINT.practice}</p>}

          {mode === 'conversation' && (
            <>
              <Divider />
              {/* AI options (407:119) */}
              <div className="flex flex-col gap-2.5">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 leading-figma">
                  <span className="text-[14.5px] font-bold text-ink">대화 상대</span>
                  <span className="text-[12.5px] text-ink-muted">여러 명이면 누가 말하는지도 함께 찾아야 해요</span>
                </p>
                <div className="flex w-full gap-1 rounded-13 bg-inactive-bg p-1" role="radiogroup" aria-label="대화 상대">
                  {PARTNERS.map((p) => (
                    <button key={p.key} type="button" role="radio" aria-checked={partner === p.key} onClick={() => setPartner(p.key)}
                      className={`flex-1 rounded-10 py-[11px] text-[14.5px] font-bold leading-[1.5] transition ${
                        partner === p.key ? 'bg-white text-primary-500 shadow-seg' : 'text-ink-muted'}`}>
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
                          className={`flex-1 rounded-13 text-[15.5px] font-bold leading-[1.5] ${people === n ? PEOPLE_ON : PEOPLE_OFF}`}>
                          {n}명
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      {/* 시작하기 (407:138): 카드 아래 전체 폭 버튼 하나. 상황이 비어 있으면 비활성 */}
      <button type="button" onClick={start} disabled={!canStart} aria-busy={loading}
        className="btn-primary w-full rounded-15 py-[17px] text-[17px]">
        {loading ? '준비 중…' : '시작하기'}
      </button>
    </AppShell>
  )
}
