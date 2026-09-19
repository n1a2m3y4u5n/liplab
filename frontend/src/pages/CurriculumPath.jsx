import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 리디자인 02). Duolingo식 세로 단계 경로.
 * 실 데이터: curriculumAPI.getStages()의 단계별 status(mastered/in_progress/unlocked/locked) + attempts.
 * 완료=보라 체크, 현재=별+상세카드(진행률·이어서 학습하기), 잠김=회색 별. 기존 학습 라우트로 이동.
 */
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/practice', conversation: '/conversation' }
const STAGE_DESC = {
  viseme: '입모양(비심) 10개 그룹을 눈으로 익혀요.',
  word: '자음과 모음이 만나 한 글자가 될 때 입모양이 어떻게 바뀌는지 익혀요. 「가·나·다」처럼 기본 조합을 다룹니다.',
  sentence: '상황별 문장을 읽고 따라 말해요.',
  conversation: '여러 상황의 실전 대화를 독화해요.',
}
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(main.py _STAGEn_MIN_ATTEMPTS와 정합).
const STAGE_TOTAL = { viseme: 15, word: 12, sentence: 10, conversation: 8 }

function CheckGlyph() {
  return <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
}
function StarGlyph({ color }) {
  return <svg viewBox="0 0 24 24" className="h-[30px] w-[30px]" fill={color}><path d="M12 2.5l2.9 5.9 6.5.95-4.7 4.58 1.11 6.47L12 17.9l-5.81 3.05 1.11-6.47L2.6 9.9l6.5-.95L12 2.5z" /></svg>
}

function Node({ status }) {
  if (status === 'mastered') return <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-primary-500"><CheckGlyph /></div>
  if (status === 'current') return (
    <div className="relative flex h-[72px] w-[72px] items-center justify-center rounded-full bg-primary-500 shadow-[0_8px_20px_-4px_rgba(125,83,222,0.5)]">
      <span className="absolute -inset-[6px] rounded-full ring-4 ring-primary-200" />
      <StarGlyph color="#fff" />
    </div>
  )
  return <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-[#eceaf3]"><StarGlyph color="#c9c4dc" /></div>
}

function NavArrow({ dir, onClick, disabled }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'}
      className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line bg-white shadow-sm transition sm:flex ${disabled ? 'opacity-30' : 'hover:border-primary-300 active:scale-95'}`}>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="#7d53de" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d={dir === 'prev' ? 'M15 6l-6 6 6 6' : 'M9 6l6 6-6 6'} />
      </svg>
    </button>
  )
}

export default function CurriculumPath() {
  const navigate = useNavigate()
  const [stages, setStages] = useState(null)
  const [track, setTrack] = useState('read')

  useEffect(() => {
    curriculumAPI.getStages().then((d) => setStages(d.stages || [])).catch(() => setStages([]))
  }, [])

  const learn = (stages || []).filter((s) => s.stage >= 1 && STAGE_ROUTE[s.key])
  const currentIdx = learn.findIndex((s) => s.status === 'in_progress' || s.status === 'unlocked')
  const nodeStatus = (s, i) => {
    if (s.status === 'mastered') return 'mastered'
    if (i === currentIdx) return 'current'
    return 'locked'
  }
  const cur = learn[currentIdx] || learn[0]
  const prevRoute = currentIdx > 0 ? STAGE_ROUTE[learn[currentIdx - 1].key] : null
  const progTotal = cur ? (STAGE_TOTAL[cur.key] || 12) : 12
  const progCur = Math.min(progTotal, cur?.attempts ?? 0)

  return (
    <AppShell active="learn">
      <div className="mx-auto flex w-full max-w-[680px] flex-col items-center gap-6">
        {/* 트랙 스위처 */}
        <div className="flex gap-1 rounded-[14px] bg-gray-100 p-1">
          {[['read', '독화'], ['speak', '발화']].map(([k, label]) => (
            <button key={k} type="button"
              onClick={() => (k === 'speak' ? navigate('/learn/speaking') : setTrack('read'))}
              className={`rounded-[10px] px-8 py-2.5 text-[15px] font-bold transition ${track === k ? 'bg-white text-primary-500 shadow-sm' : 'text-gray-400'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더 */}
        <div className="flex w-full items-center gap-3.5 rounded-[20px] bg-primary-500 py-5 pl-7 pr-5 text-white shadow-[0_10px_28px_-8px_rgba(125,83,222,0.55)]">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-bold opacity-80">독화 · {cur ? `${cur.stage}단계` : '학습'}</span>
            <span className="text-[26px] font-bold tracking-[-0.52px]">{cur?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => navigate('/guide')}
            className="shrink-0 rounded-full bg-white/20 px-4 py-2 text-[13.5px] font-bold text-white hover:bg-white/30">가이드</button>
        </div>

        {/* 경로 */}
        {!stages ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="relative flex w-full flex-col items-center">
            {learn.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              return (
                <div key={s.key} className="flex w-full flex-col items-center">
                  {i > 0 && <div className={`h-14 w-1.5 rounded ${learn[i - 1].status === 'mastered' ? 'bg-primary-500' : 'bg-[#eceaf3]'}`} />}
                  <div className="flex w-full items-center justify-center gap-3">
                    {st === 'current' && <NavArrow dir="prev" disabled={!prevRoute} onClick={() => prevRoute && navigate(prevRoute)} />}
                    <button type="button" disabled={!clickable}
                      onClick={() => clickable && navigate(STAGE_ROUTE[s.key])}
                      className={clickable ? 'cursor-pointer' : 'cursor-not-allowed'}>
                      <Node status={st} />
                    </button>
                    {st === 'current' ? (
                      <>
                        {/* 상세 카드 (데스크톱: 노드 옆, 왼쪽 삼각 포인터) */}
                        <div className="relative hidden w-[340px] max-w-[58vw] rounded-[20px] border border-line bg-white p-5 shadow-[0_10px_28px_-6px_rgba(26,13,64,0.12)] sm:block">
                          <span className="absolute -left-2 top-9 h-4 w-4 rotate-45 border-b border-l border-line bg-white" />
                          <p className="text-[20px] font-bold tracking-[-0.4px] text-ink">{s.title}</p>
                          <p className="mt-2 text-[13.5px] leading-relaxed text-ink-muted">{STAGE_DESC[s.key]}</p>
                          <div className="mt-4 flex items-center justify-between text-[12.5px] font-bold">
                            <span className="text-ink-muted">진행률</span>
                            <span className="text-primary-500">{progCur} / {progTotal}</span>
                          </div>
                          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#eceaf3]">
                            <div className="h-full rounded-full bg-primary-500" style={{ width: `${(progCur / progTotal) * 100}%` }} />
                          </div>
                          <button type="button" onClick={() => navigate(STAGE_ROUTE[s.key])}
                            className="btn-primary mt-4 w-full !py-3.5 text-[17px]">이어서 학습하기</button>
                        </div>
                        <NavArrow dir="next" disabled onClick={() => {}} />
                      </>
                    ) : null}
                  </div>
                </div>
              )
            })}
            {/* 마스코트 — 우하단 플로팅(데스크톱) */}
            <img src="/ui/mascot.svg" alt="" className="pointer-events-none absolute -right-2 bottom-4 hidden h-24 w-24 opacity-95 sm:block sm:right-4" />
          </div>
        )}

        {/* 상세 바텀시트 (모바일: 탭 바 위 고정) */}
        {cur && (
          <div className="fixed inset-x-0 bottom-[62px] z-20 rounded-t-[22px] border-t border-line bg-white px-5 pb-4 pt-4 shadow-[0_-8px_24px_-8px_rgba(26,13,64,0.12)] sm:hidden">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[16px] font-bold text-ink">{cur.title}</p>
              <span className="text-[12.5px] font-bold text-primary-500">{progCur} / {progTotal}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#eceaf3]">
              <div className="h-full rounded-full bg-primary-500" style={{ width: `${(progCur / progTotal) * 100}%` }} />
            </div>
            <button type="button" onClick={() => navigate(STAGE_ROUTE[cur.key])}
              className="btn-primary mt-3 w-full !py-3.5 text-[17px]">이어서 학습하기</button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
