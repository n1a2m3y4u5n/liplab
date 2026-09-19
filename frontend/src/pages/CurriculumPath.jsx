import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 리디자인 node 58:11, 데스크톱 1440 기준 픽셀 이식).
 * Duolingo식 세로 단계 경로. 노드 SVG는 Figma export(/ui/node-*.svg)를 그대로 사용.
 * 실 데이터: curriculumAPI.getStages()의 단계별 status(mastered/in_progress/unlocked/locked) + attempts.
 * 완료=보라 체크, 현재=별+링+상세카드(진행률·이어서 학습하기), 잠김=회색 별. 기존 학습 라우트로 이동.
 */
// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐야 currentScenario가 세팅된 뒤 /practice 레슨이 뜬다.
// 바로 /practice로 보내면 시나리오가 없어 Practice가 되돌려보내므로 /learn/scenario로 진입한다.
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/conversation' }
const STAGE_DESC = {
  viseme: '입모양(비심) 10개 그룹을 눈으로 익혀요.',
  word: '자음과 모음이 만나 한 글자가 될 때 입모양이 어떻게 바뀌는지 익혀요. 「가·나·다」처럼 기본 조합을 다룹니다.',
  sentence: '상황별 문장을 읽고 따라 말해요.',
  conversation: '여러 상황의 실전 대화를 독화해요.',
}
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(main.py _STAGEn_MIN_ATTEMPTS와 정합).
const STAGE_TOTAL = { viseme: 15, word: 12, sentence: 10, conversation: 8 }

// Figma "Button / Primary" — 3D 하단테두리(brand/primary-dark) 스타일. index.css btn-primary는 flat이라 인라인 적용.
const BTN_3D =
  'flex w-full items-center justify-center rounded-[16px] border-2 border-b-[6px] border-primary-700 bg-primary-500 py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white transition hover:bg-primary-600 active:translate-y-[2px] active:border-b-2 disabled:opacity-50'

// 노드 — Figma export SVG(76px). 현재 노드는 94px 링(opacity 0.45)을 뒤에 겹친다.
function Node({ status }) {
  if (status === 'mastered') return <img src="/ui/node-done.svg" alt="" className="h-[76px] w-[76px]" />
  if (status === 'current') return (
    <span className="relative flex h-[76px] w-[76px] items-center justify-center">
      <img src="/ui/node-ring.svg" alt="" className="pointer-events-none absolute h-[94px] w-[94px] max-w-none" />
      <img src="/ui/node-current.svg" alt="" className="relative h-[76px] w-[76px]" />
    </span>
  )
  return <img src="/ui/node-locked.svg" alt="" className="h-[76px] w-[76px]" />
}

function NavArrow({ dir, onClick, disabled, className = '' }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'}
      className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line bg-white shadow-[0_4px_10px_-3px_rgba(26,13,64,0.15)] transition sm:flex ${disabled ? 'opacity-30' : 'hover:border-primary-300 active:scale-95'} ${className}`}>
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
      <div className="mx-auto flex w-full max-w-[752px] flex-col items-center gap-6">
        {/* 트랙 스위처 (Figma 171:18) */}
        <div className="flex gap-1 rounded-[14px] bg-[#f1f1f5] p-1">
          {[['read', '독화'], ['speak', '발화']].map(([k, label]) => (
            <button key={k} type="button"
              onClick={() => (k === 'speak' ? navigate('/learn/speaking') : setTrack('read'))}
              className={`rounded-[10px] px-[26px] py-2.5 text-[15px] font-bold transition ${track === k ? 'bg-white text-primary-500 shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]' : 'text-[#8a8a9b]'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더 (Figma 61:12) — 3D 하단테두리 */}
        <div className="flex w-full items-center gap-3.5 rounded-[18px] border-b-[5px] border-primary-700 bg-primary-500 py-5 pl-[26px] pr-5 text-white">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-bold opacity-[0.85]">독화 · {cur ? `${cur.stage}단계` : '학습'}</span>
            <span className="text-[24px] font-bold tracking-[-0.48px]">{cur?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => navigate('/guide')}
            className="shrink-0 rounded-[12px] border-2 border-white/40 bg-white/[0.18] px-[18px] py-3 text-[14px] font-bold text-white transition hover:bg-white/30">가이드</button>
        </div>

        {/* 경로 (Figma 61:18) — 데스크톱은 좌측 정렬 노드열 + 우측 상세카드, 모바일은 중앙 정렬 */}
        {!stages ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="relative flex w-full flex-col items-center sm:items-start sm:pl-[130px]">
            {learn.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              return (
                <div key={s.key} className="flex flex-col items-center">
                  {i > 0 && <div className={`h-[58px] w-1.5 rounded-[3px] ${learn[i - 1].status === 'mastered' ? 'bg-primary-500' : 'bg-[#e4e4ec]'}`} />}
                  <div className="relative">
                    <button type="button" disabled={!clickable}
                      onClick={() => clickable && navigate(STAGE_ROUTE[s.key])}
                      className={clickable ? 'block cursor-pointer' : 'block cursor-not-allowed'}>
                      <Node status={st} />
                    </button>

                    {st === 'current' && (
                      <>
                        {/* 이전/다음 단계 화살표 (Figma 145:18 / 145:20) — 노드 기준 절대배치, 데스크톱만 */}
                        <NavArrow dir="prev" disabled={!prevRoute} onClick={() => prevRoute && navigate(prevRoute)}
                          className="absolute right-full top-1/2 -translate-y-1/2 !mr-[30px]" />
                        <NavArrow dir="next" disabled onClick={() => {}}
                          className="absolute left-[526px] top-1/2 -translate-y-1/2" />

                        {/* 상세 카드 (Figma 75:12) — 노드 오른쪽, 왼쪽 삼각 포인터 */}
                        <div className="absolute left-[104px] top-1/2 hidden w-[360px] max-w-[58vw] -translate-y-1/2 flex-col gap-[14px] rounded-[20px] border-2 border-line bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] sm:flex">
                          <span className="absolute -left-2 top-1/2 h-4 w-4 -translate-y-1/2 rotate-45 border-b-2 border-l-2 border-line bg-white" />
                          <p className="text-[22px] font-bold tracking-[-0.44px] text-ink">{s.title}</p>
                          <p className="text-[14px] leading-[1.75] text-ink-muted">{STAGE_DESC[s.key]}</p>
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center justify-between text-[13px] font-bold">
                              <span className="text-ink-muted">진행률</span>
                              <span className="text-primary-500">{progCur} / {progTotal}</span>
                            </div>
                            <div className="h-[10px] overflow-hidden rounded-full bg-[#ededf3]">
                              <div className="h-full rounded-full bg-primary-500" style={{ width: `${(progCur / progTotal) * 100}%` }} />
                            </div>
                          </div>
                          <button type="button" onClick={() => navigate(STAGE_ROUTE[s.key])} className={BTN_3D}>이어서 학습하기</button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
            {/* 마스코트 — 우하단 플로팅(데스크톱), Figma 61:35 rotate 6° */}
            <img src="/ui/mascot.svg" alt="" className="pointer-events-none absolute bottom-4 right-4 hidden h-24 w-24 rotate-6 opacity-95 sm:block" />
          </div>
        )}

        {/* 상세 바텀시트 (모바일: 탭 바 위 고정) */}
        {cur && (
          <div className="fixed inset-x-0 bottom-[62px] z-20 rounded-t-[22px] border-t border-line bg-white px-5 pb-4 pt-4 shadow-[0_-8px_24px_-8px_rgba(26,13,64,0.12)] sm:hidden">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[16px] font-bold text-ink">{cur.title}</p>
              <span className="text-[12.5px] font-bold text-primary-500">{progCur} / {progTotal}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#ededf3]">
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
