import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import LoadingScreen from '../components/LoadingScreen'
import { LoadFailed } from '../components/ErrorScreen'
import useChoiceKeys from '../lib/useChoiceKeys'

/**
 * 디지털 독화 배치검사(축 I) — 난이도가 통제된 입모양→단어 4지선다로 현재 수준을 진단한다.
 * 문항마다 정답을 즉시 공개하지 않는다. 적응형 진단 로직(문항 선택·채점·시작 단계 추천)은 그대로다(핸드오프 §4-01).
 * 화면: 문항 385:82(모바일 385:120) — 독화 레슨 템플릿과 같은 틀, 북마크 없음.
 *       결과(배치 모드) 85:9(모바일 244:99) — 마스코트 + "학습 준비가 다 되었어요!" + 버튼 2개.
 *       사전·사후 평가(A/B)의 결과 리포트는 §4-01에 따라 예전 리포트를 유지한다.
 */
const VIS_NAME = {
  1: '양순음', 2: '개방모음', 3: '전설모음', 4: '원순모음', 5: '중설모음',
  6: '치경음', 7: '연구개음', 8: '성문음', 9: '이중모음', 10: '경구개음',
}

// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐 currentScenario를 세팅한 뒤 /practice로 진입한다.
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario' }
const STAGE_NUM = { viseme: 1, word: 2, sentence: 3, conversation: 4 }  // 추천 단계 배지 숫자

const MODE_LABEL = { placement: '배치검사', A: '사전검사', B: '사후검사' }
const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
// 결과 버튼 — 데스크톱 75:23(btn-lg), lg 미만 244:129(r14·b5, py16, 16px)
const RESULT_BTN = 'w-full max-lg:rounded-14 max-lg:border-b-5 max-lg:py-4 max-lg:text-[16px]'

// 사전·사후 동형검사는 /learn/placement?form=A|B 로 들어온다(학습 효과 리포트의 시작 버튼).
// 문항 화면의 모드 전환기는 Figma 385:82에 맞춰 없앴으므로 진입은 주소로만 한다(핸드오프 §4-01).
function initialMode() {
  const f = new URLSearchParams(window.location.search).get('form')
  return f === 'A' || f === 'B' ? f : 'placement'
}

export default function Placement() {
  const navigate = useNavigate()
  const [items, setItems] = useState(null)
  const [idx, setIdx] = useState(0)
  const [responses, setResponses] = useState({})
  const [frames, setFrames] = useState([])
  const [result, setResult] = useState(null)
  const [delta, setDelta] = useState(null)  // 첫 검사(baseline) 대비 향상도 — 2회차부터(aa28c05, 병합 복원)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [mode] = useState(initialMode)  // placement | A(사전) | B(사후) — 향상도검사(축 I)
  const [n, setN] = useState(8)  // 목표 문항 수(적응형 배치검사)
  const [selected, setSelected] = useState(null)  // 현재 문항에서 고른 보기(다음 눌러 확정)
  const [loadError, setLoadError] = useState(false)      // 문항을 받지 못함(첫 문항·다시 진단) → 다시 시도·나가기
  const [submitError, setSubmitError] = useState(false)  // 답을 보내지 못함 → 하단 바에 안내, 다음으로 다시 보낸다

  // 방금 결과가 서버에 저장됐으니, 첫 검사 대비 향상도(/api/assessment/history의 delta)를 받아 함께 보여준다.
  const loadDelta = () => {
    curriculumAPI.getAssessmentHistory().then((h) => setDelta(h?.delta || null)).catch(() => {})
  }

  const start = useCallback(async (m = mode) => {
    setLoading(true); setResult(null); setDelta(null); setResponses({}); setIdx(0); setSelected(null)
    setLoadError(false); setSubmitError(false)
    try {
      if (m === 'placement') {
        // 적응형: 첫 문항만 받고, 정오답에 따라 다음 문항을 서버가 고른다(축 I).
        const d = await curriculumAPI.nextPlacementItem([], {}, 8)
        setN(d.n || 8)
        setItems(d.item ? [d.item] : [])
      } else {
        // 향상도 동형폼(A 사전 / B 사후)은 통제 비교를 위해 고정 배치 유지.
        const d = await curriculumAPI.getPlacement(8, m)
        setItems(d.items)
      }
    } catch {
      setLoadError(true)   // 예전에는 무시해 items가 비어 로딩 화면에 계속 머물렀다
    } finally { setLoading(false) }
  }, [mode])

  useEffect(() => { start(mode) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!items || !items[idx]) return
    setFrames([])
    learningAPI.getVisemes(items[idx].word).then(setFrames).catch(() => {})
  }, [items, idx])

  // 확정한 답을 기록하고 다음 문항으로 가거나 채점한다. 보내지 못하면 false(안내를 띄우고 confirm이 고른 보기를 되살린다).
  const choose = async (word) => {
    if (submitting || result) return false   // 마지막 문항 중복 클릭 시 이중 채점·저장 방지
    const it = items[idx]
    const next = { ...responses, [it.id]: word }
    setResponses(next)
    setSubmitError(false)
    if (mode === 'placement') {
      // 적응형: 방금 정오답으로 다음 문항을 서버가 고른다. done이면 지금까지 문항으로 채점.
      setSubmitting(true)
      try {
        const d = await curriculumAPI.nextPlacementItem(items, next, n)
        if (d.done || !d.item) {
          const r = await curriculumAPI.scorePlacement(items, next, 'placement')
          setResult(r)
          loadDelta()
        } else {
          setItems([...items, d.item]); setIdx(idx + 1)
        }
        return true
      } catch {
        setSubmitError(true)
        return false
      } finally { setSubmitting(false) }
    }
    // 향상도 동형폼(A/B): 고정 배치 순차 진행 후 일괄 채점.
    if (idx < items.length - 1) {
      setIdx(idx + 1)
      return true
    }
    setSubmitting(true)
    try {
      const r = await curriculumAPI.scorePlacement(items, next, mode)
      setResult(r)
      loadDelta()
      return true
    } catch {
      setSubmitError(true)
      return false
    } finally {
      setSubmitting(false)
    }
  }

  // 보기 클릭은 선택(로컬 state)만, '다음'을 눌러야 기존 채점 로직(choose)으로 확정한다.
  const confirm = async () => {
    if (!selected || submitting || result) return
    const chosen = selected
    setSelected(null)
    if (!(await choose(chosen))) setSelected(chosen)   // 보내지 못했으면 고른 보기를 되살려 다음으로 다시 보낸다
  }

  // 보기 숫자 키 1~4(§4-03 템플릿) — 채점 중·결과 화면에서는 받지 않는다.
  const it = items?.[idx]
  useChoiceKeys(it?.options, (w) => setSelected(w), !!it && !result && !submitting && !loading)

  // 추천 시작 단계로 이동 — 배치 모드는 먼저 그 단계로 배치(setTrack)한다(기존 로직 그대로).
  const goRecommended = async () => {
    if (mode === 'placement') {
      try { await curriculumAPI.setTrack('perception', result.recommended_start?.stage) } catch { /* 배치 실패해도 이동은 함 */ }
    }
    navigate(STAGE_ROUTE[result.recommended_start?.key] || '/learn/viseme')
  }

  // 데이터 로딩 = 기본 로딩(§4-10 256:34 / 모바일 256:48)
  if (loading) return <LoadingScreen />
  const failed = <LoadFailed message="문항을 불러오지 못했어요." onRetry={() => start(mode)} onExit={() => navigate('/learn/path')} />
  if (loadError || !items) return failed

  if (result && mode === 'placement') {
    // 결과(배치 모드) — Figma 85:9 / 모바일 244:99. 이것뿐인 단순 화면(§4-01).
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-[18px] bg-page px-[18px] py-10 lg:gap-6">
        <span className="relative size-[84px] shrink-0 lg:size-24">
          <img src="/ui/lp-84-7-mascot.svg" alt="" className="absolute max-w-none" style={OVERFLOW} />
        </span>
        <h1 className="text-center text-[25px] font-bold leading-figma tracking-[-0.625px] text-ink lg:text-[32px] lg:tracking-[-0.8px]">
          학습 준비가 다 되었어요!
        </h1>
        <div className="flex w-full max-w-[640px] flex-col gap-2.5 lg:gap-3">
          <button type="button" onClick={goRecommended} className={`btn-primary btn-lg ${RESULT_BTN}`}>학습하러 가기</button>
          <button type="button" onClick={() => start(mode)} className={`btn-secondary btn-lg text-track ${RESULT_BTN}`}>다시 진단하기</button>
        </div>
      </div>
    )
  }

  if (result) {
    // 사전·사후 평가(A/B) 결과 리포트 — §4-01에 따라 예전 리포트를 유지한다(색만 토큰으로).
    return (
      <div className="min-h-[100dvh] bg-page">
        <div className="mx-auto flex min-h-[100dvh] max-w-[596px] flex-col justify-center gap-6 px-[18px] py-8">
          {/* 결과 히어로 (그라데이션 카드) */}
          <div className="bg-loading-perception overflow-hidden rounded-22">
            <div className="flex flex-col items-center gap-1.5 px-6 py-8 text-white">
              <img src="/ui/onb-mascot-light.svg" alt="" className="h-16 w-16" />
              <p className="text-[13px] font-bold opacity-85">{MODE_LABEL[mode]} 결과</p>
              <p className="text-[40px] font-black leading-none tracking-[-1px]">Lv.{result.level}</p>
              <p className="text-sm font-bold opacity-90">정확도 {Math.round(result.accuracy * 100)}% ({result.correct}/{result.total})</p>
            </div>
          </div>

          {/* 결과 리포트 카드 */}
          <div className="flex flex-col gap-[22px] rounded-22 border-2 border-line bg-white p-7">
            <div className="flex flex-col gap-3">
              <p className="text-[13px] font-bold text-ink-muted">추천 시작 단계</p>
              <div className="flex flex-col items-center gap-2.5 rounded-16 bg-primary-100 px-4 py-[18px]">
                <p className="text-[12px] font-bold tracking-[0.24px] text-primary-700 opacity-80">독화</p>
                <div className="flex items-center gap-3">
                  <span className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-primary-500 text-[16px] font-bold text-white">{result.recommended_start?.stage ?? STAGE_NUM[result.recommended_start?.key] ?? 1}</span>
                  <p className="text-[19px] font-bold tracking-[-0.38px] text-primary-700">{result.recommended_start?.title || '입모양 인지'}</p>
                </div>
              </div>
            </div>

            {(result.error_visemes?.length > 0 || result.error_phonemes?.length > 0) && (
              <>
                <div className="h-[1.5px] w-full bg-line" />
                <div className="flex flex-col gap-3">
                  <p className="text-[13px] font-bold text-ink-muted">진단 요약</p>
                  {result.error_visemes?.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-xs text-ink-muted">약한 입모양</p>
                      <div className="flex flex-wrap gap-2">
                        {result.error_visemes.map((v) => (
                          <span key={v} className="rounded-full bg-bad-tint px-3 py-1 text-xs font-bold text-bad-text">{VIS_NAME[v] || v}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.error_phonemes?.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-xs text-ink-muted">자주 놓친 소리(음소)</p>
                      <div className="flex flex-wrap gap-2">
                        {result.error_phonemes.map((e) => (
                          <span key={e.phoneme} className="rounded-full bg-warn-tint px-3 py-1 text-xs font-bold text-warn-text">{e.phoneme} ×{e.count}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* 지난 첫 검사 대비 향상도 (aa28c05) — 검사가 2회 이상일 때만 */}
            {delta && (
              <>
                <div className="h-[1.5px] w-full bg-line" />
                <div className="flex flex-col gap-3">
                  <p className="text-[13px] font-bold text-ink-muted">지난 첫 검사 대비 향상도</p>
                  <div className="flex flex-wrap gap-2">
                    <span className={`rounded-full px-3 py-1 text-xs font-bold ${delta.accuracy >= 0 ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                      정확도 {delta.accuracy >= 0 ? '+' : ''}{Math.round(delta.accuracy * 100)}%p
                    </span>
                    <span className={`rounded-full px-3 py-1 text-xs font-bold ${delta.level >= 0 ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                      수준 {delta.level >= 0 ? '+' : ''}{delta.level}
                    </span>
                  </div>
                  {delta.resolved_visemes?.length > 0 && (
                    <p className="text-xs text-good-text">
                      이제 안 틀리는 입모양: {delta.resolved_visemes.map((v) => VIS_NAME[v] || v).join(', ')}
                    </p>
                  )}
                </div>
              </>
            )}

            {/* 노트 */}
            <div className="rounded-13 bg-warn-tint px-4 py-3.5">
              <p className="text-[14px] text-warn-text">언제든 다른 단계로 건너뛰거나 되돌아갈 수 있어요.</p>
            </div>

            <p className="rounded-16 bg-primary-100 px-4 py-3 text-xs text-primary-700">
              {MODE_LABEL[mode]} 결과를 저장했어요. 사전(A)·사후(B)를 모두 마치면 <b>분석 → 전체 통계 → 학습 효과 리포트</b>에서 변화가 보여요.
            </p>
            <button type="button" onClick={() => navigate('/analysis/eval')}
              className="btn-secondary w-full py-3 text-[14px]">학습 효과 리포트 보기</button>
          </div>

          {/* 하단 버튼 (공용 3D 버튼) */}
          <div className="flex flex-col gap-3">
            <button type="button" onClick={goRecommended} className="btn-primary w-full py-4 text-[18px]">
              {result.recommended_start?.title || '입모양 인지'}부터 시작하기
            </button>
            <button type="button" onClick={() => start(mode)} className="btn-secondary w-full py-3.5 text-[15px]">다시 검사</button>
          </div>
        </div>
      </div>
    )
  }

  if (!it) return failed
  const total = mode === 'placement' ? n : items.length
  return (
    <div className="min-h-[100dvh] bg-page">
      <div className="mx-auto flex w-full max-w-[676px] flex-col px-[18px] pb-[160px] pt-[18px] lg:pb-[150px] lg:pt-7">
        {/* 진행 헤더(385:83 / 모바일 385:121) — 나가기 X + 트랙 + n / 전체(채움 = 현재 문항까지) */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={() => navigate('/learn/path')} aria-label="나가기" className="shrink-0">
            <img src="/ui/lp-91-12-close.svg" alt="" className="size-8 lg:size-9" />
          </button>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]">
            <div className="h-full rounded-full bg-track transition-all" style={{ width: `${((idx + 1) / total) * 100}%` }} />
          </div>
          <span className="shrink-0 text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{idx + 1} / {total}</span>
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5">
          {/* 질문(385:89 / 모바일 385:128) — 북마크 없음 */}
          <div className="flex flex-col gap-1.5 font-bold leading-figma lg:gap-2">
            <p className="text-[12px] text-track lg:text-[13px]">자가진단</p>
            <h1 className="text-[21px] tracking-[-0.525px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">이 입모양은 어떤 단어일까요?</h1>
          </div>

          {/* 입모양 카드(385:93 560×370 / 모바일 385:132 전체 폭×214) */}
          <div className="mx-auto h-[214px] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[370px] lg:rounded-22">
            <MouthAvatar frames={frames} height={null} className="h-full" />
          </div>

          {/* 4지선다(385:96 / 모바일 385:135) — 선택(로컬) → 다음 확정 */}
          <div className="flex flex-col gap-2.5 lg:gap-3">
            {it.options.map((w, i) => {
              const on = selected === w
              return (
                <button key={w} type="button" disabled={submitting} onClick={() => setSelected(w)} aria-pressed={on}
                  className={`flex w-full items-center gap-3.5 rounded-14 border-2 border-b-5 px-[18px] py-[15px] text-left transition-colors disabled:opacity-60 enabled:active:scale-[0.99] lg:gap-4 lg:rounded-16 lg:px-5 lg:py-4 ${on ? 'border-track bg-track-tint' : 'border-line bg-white enabled:hover:border-primary-300'}`}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-[7px] bg-fill text-[12px] font-bold leading-figma text-ink-muted lg:size-7 lg:rounded-lg lg:text-[13px]">{i + 1}</span>
                  <span className="flex-1 text-[18px] font-bold leading-figma text-ink lg:text-[20px]">{w}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* 하단 고정 바(385:113 / 모바일 385:152) — 데스크톱: 왼쪽 안내 + 오른쪽 '다음', lg 미만: 안내 없이 전체 폭 '다음' */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-line bg-white">
        <div className="mx-auto flex max-w-[676px] flex-col items-stretch px-[18px] pb-[calc(22px+env(safe-area-inset-bottom))] pt-4 lg:h-[110px] lg:flex-row lg:items-center lg:justify-between lg:py-0">
          {submitError ? (
            <p role="alert" className="mb-3 text-center text-[14px] font-bold leading-figma text-bad-text lg:mb-0 lg:text-left lg:text-[15px]">
              답을 보내지 못했어요. 다음을 다시 눌러 주세요.
            </p>
          ) : (
            <p className="hidden text-[15px] leading-figma text-ink-faint lg:block">정답은 끝나면 결과로 알려드려요</p>
          )}
          <button type="button" onClick={confirm} disabled={!selected || submitting}
            className="btn-primary btn-bar w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto">
            다음
          </button>
        </div>
      </div>
    </div>
  )
}
