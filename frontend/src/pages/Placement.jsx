import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'

/**
 * 디지털 독화 배치검사(축 I) — 난이도가 통제된 입모양→단어 4지선다로 현재 수준을 진단한다.
 * 문항마다 정답을 즉시 공개하지 않고, 끝나면 수준·음소별 오류·시작 단계를 리포트로 보여준다.
 * 화면 골격/스타일은 Figma "온보딩 / 자기진단 설문·결과 리포트"를 따르되, 적응형 진단 로직은 그대로 유지한다.
 */
const VIS_NAME = {
  1: '양순음', 2: '개방모음', 3: '전설모음', 4: '원순모음', 5: '중설모음',
  6: '치경음', 7: '연구개음', 8: '성문음', 9: '이중모음', 10: '경구개음',
}

// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐 currentScenario를 세팅한 뒤 /practice로 진입한다.
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario' }
const STAGE_NUM = { viseme: 1, word: 2, sentence: 3, conversation: 4 }  // 추천 단계 배지 숫자

const MODE_LABEL = { placement: '배치검사', A: '사전검사', B: '사후검사' }

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

  // 방금 결과가 서버에 저장됐으니, 첫 검사 대비 향상도(/api/assessment/history의 delta)를 받아 함께 보여준다.
  const loadDelta = () => {
    curriculumAPI.getAssessmentHistory().then((h) => setDelta(h?.delta || null)).catch(() => {})
  }

  const start = useCallback(async (m = mode) => {
    setLoading(true); setResult(null); setDelta(null); setResponses({}); setIdx(0); setSelected(null)
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
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [mode])

  useEffect(() => { start(mode) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!items || !items[idx]) return
    setFrames([])
    learningAPI.getVisemes(items[idx].word).then(setFrames).catch(() => {})
  }, [items, idx])

  const choose = async (word) => {
    if (submitting || result) return   // 마지막 문항 중복 클릭 시 이중 채점·저장 방지
    const it = items[idx]
    const next = { ...responses, [it.id]: word }
    setResponses(next)
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
      } finally { setSubmitting(false) }
      return
    }
    // 향상도 동형폼(A/B): 고정 배치 순차 진행 후 일괄 채점.
    if (idx < items.length - 1) {
      setIdx(idx + 1)
    } else {
      setSubmitting(true)
      try {
        const r = await curriculumAPI.scorePlacement(items, next, mode)
        setResult(r)
        loadDelta()
      } finally {
        setSubmitting(false)
      }
    }
  }

  // 보기 클릭은 선택(로컬 state)만, '다음'을 눌러야 기존 채점 로직(choose)으로 확정한다.
  const confirm = async () => {
    if (!selected || submitting || result) return
    const chosen = selected
    setSelected(null)
    await choose(chosen)
  }

  if (loading || !items) return <div className="p-8 text-center text-gray-400">검사를 준비하는 중…</div>

  if (result) {
    return (
      <div className="mx-auto flex min-h-[100dvh] max-w-[560px] flex-col justify-center gap-6 bg-[#f3f3f3] px-4 py-8">
        {/* 결과 히어로 (그라데이션 카드) */}
        <div className="overflow-hidden rounded-[22px]"
          style={{ backgroundImage: 'linear-gradient(166deg, #a78bfa 0%, #7d53de 71%)' }}>
          <div className="flex flex-col items-center gap-1.5 px-6 py-8 text-white">
            <img src="/ui/onb-mascot-light.svg" alt="" className="h-16 w-16" />
            <p className="text-[13px] font-bold opacity-85">{mode === 'placement' ? '배치검사 결과' : `${MODE_LABEL[mode]} 결과`}</p>
            <p className="text-[40px] font-black leading-none tracking-[-1px]">Lv.{result.level}</p>
            <p className="text-sm font-bold opacity-90">정확도 {Math.round(result.accuracy * 100)}% ({result.correct}/{result.total})</p>
          </div>
        </div>

        {/* 결과 리포트 카드 (Figma "3. 결과 리포트") */}
        <div className="flex flex-col gap-[22px] rounded-[22px] border-2 border-line bg-white p-7">
          <div className="flex flex-col gap-3">
            <p className="text-[13px] font-bold text-ink-muted">추천 시작 단계</p>
            <div className="flex flex-col items-center gap-2.5 rounded-[16px] bg-primary-100 px-4 py-[18px]">
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
                        <span key={v} className="rounded-full bg-rose-50 px-3 py-1 text-xs font-bold text-rose-700">{VIS_NAME[v] || v}</span>
                      ))}
                    </div>
                  </div>
                )}
                {result.error_phonemes?.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs text-ink-muted">자주 놓친 소리(음소)</p>
                    <div className="flex flex-wrap gap-2">
                      {result.error_phonemes.map((e) => (
                        <span key={e.phoneme} className="rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">{e.phoneme} ×{e.count}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* 지난 첫 검사 대비 향상도 (aa28c05) — 검사가 2회 이상일 때만. 첫 배치(온보딩) 결과 화면은 그대로다. */}
          {delta && (
            <>
              <div className="h-[1.5px] w-full bg-line" />
              <div className="flex flex-col gap-3">
                <p className="text-[13px] font-bold text-ink-muted">지난 첫 검사 대비 향상도</p>
                <div className="flex flex-wrap gap-2">
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${delta.accuracy >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                    정확도 {delta.accuracy >= 0 ? '+' : ''}{Math.round(delta.accuracy * 100)}%p
                  </span>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${delta.level >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                    수준 {delta.level >= 0 ? '+' : ''}{delta.level}
                  </span>
                </div>
                {delta.resolved_visemes?.length > 0 && (
                  <p className="text-xs text-emerald-700">
                    이제 안 틀리는 입모양: {delta.resolved_visemes.map((v) => VIS_NAME[v] || v).join(', ')}
                  </p>
                )}
              </div>
            </>
          )}

          {/* 노트 (Figma Note) */}
          <div className="flex items-center gap-2.5 rounded-[12px] bg-[#fff3d6] px-4 py-3.5">
            <span aria-hidden className="text-[14px]">💡</span>
            <p className="flex-1 text-[14px] text-[#92400e]">언제든 다른 단계로 건너뛰거나 되돌아갈 수 있어요.</p>
          </div>

          {mode !== 'placement' && (
            <p className="rounded-2xl bg-primary-100 px-4 py-3 text-xs text-primary-700">
              {MODE_LABEL[mode]} 결과를 저장했어요. 사전(A)·사후(B)를 모두 마치면 <b>분석 → 전체 통계 → 학습 효과 리포트</b>에서 변화가 보여요.
            </p>
          )}
          {mode !== 'placement' && (
            <button type="button" onClick={() => navigate('/analysis/eval')}
              className="btn-secondary w-full !py-3 text-[14px]">학습 효과 리포트 보기</button>
          )}
        </div>

        {/* 하단 버튼 (공용 3D 버튼) */}
        <div className="flex flex-col gap-3">
          <button onClick={async () => {
              if (mode === 'placement') {
                try { await curriculumAPI.setTrack('perception', result.recommended_start?.stage) } catch { /* 배치 실패해도 이동은 함 */ }
              }
              navigate(STAGE_ROUTE[result.recommended_start?.key] || '/learn/viseme')
            }}
            className="btn-primary w-full !py-4 text-[18px]">
            {result.recommended_start?.title || '입모양 인지'}부터 시작하기
          </button>
          <button onClick={() => start(mode)} className="btn-secondary w-full !py-3.5 text-[15px]">다시 검사</button>
        </div>
      </div>
    )
  }

  const it = items[idx]
  if (!it) return <div className="p-8 text-center text-gray-400">문항을 불러오지 못했어요. 다시 시도해 주세요.</div>
  const total = mode === 'placement' ? n : items.length
  return (
    <div className="mx-auto flex min-h-[100dvh] max-w-[640px] flex-col gap-8 bg-[#f3f3f3] px-4 pb-32 pt-8 sm:px-6">
      {/* 진행 헤더 (Figma Progress header) */}
      <div className="flex items-center gap-[18px]">
        <button type="button" onClick={() => navigate('/dashboard')} aria-label="나가기" className="shrink-0">
          <img src="/ui/lp-91-12-close.svg" alt="" className="h-9 w-9" />
        </button>
        <div className="h-[14px] flex-1 overflow-hidden rounded-full bg-[#e4e4ec]">
          <div className="h-full rounded-full bg-primary-500 transition-all" style={{ width: `${(idx / total) * 100}%` }} />
        </div>
        <span className="shrink-0 text-[15px] font-bold text-ink-muted">{idx + 1} / {total}</span>
      </div>

      {/* 질문 (Figma 385:82) */}
      <div className="flex flex-col gap-2">
        <p className="text-[13px] font-bold text-[#7d53de]">자가진단</p>
        <p className="text-[30px] font-bold tracking-[-0.75px] text-[#1a1a2e]">이 입모양은 어떤 단어일까요?</p>
      </div>

      {/* 입모양 */}
      <div className="rounded-[22px] border-2 border-line bg-white p-4">
        <MouthAvatar frames={frames} />
      </div>

      {/* 4지선다 — 선택(로컬)→다음 확정 */}
      <div className="flex flex-col gap-3">
        {it.options.map((w, i) => {
          const on = selected === w
          return (
            <button key={w} type="button" disabled={submitting} onClick={() => setSelected(w)}
              className={`flex items-center gap-4 rounded-[16px] border-2 border-b-[5px] px-5 py-4 text-left transition-all active:scale-[0.99] disabled:opacity-60 ${on ? 'border-[#7d53de] bg-[#efe9fc]' : 'border-[#e2e2e8] bg-white'}`}>
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] bg-[#ededf3] text-[13px] font-bold text-[#5a5a6e]">{i + 1}</span>
              <span className="flex-1 text-[20px] font-bold text-[#1a1a2e]">{w}</span>
            </button>
          )
        })}
      </div>

      {/* 하단 고정 액션 바 (Figma 385:82) */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t-2 border-line bg-white">
        <div className="mx-auto flex max-w-[640px] items-center justify-between px-4 py-6 sm:px-6">
          <p className="text-[15px] text-[#8a8a9b]">정답은 끝나면 결과로 알려드려요</p>
          <button type="button" onClick={confirm} disabled={!selected || submitting}
            className={`rounded-[14px] border-2 border-b-[5px] px-10 py-[15px] text-[17px] font-bold transition ${selected
              ? 'border-[#5f3ab8] bg-[#7d53de] text-white'
              : 'border-[#d2d2de] bg-[#e4e4ec] text-[#a0a0b0]'}`}>
            다음
          </button>
        </div>
      </div>
    </div>
  )
}
