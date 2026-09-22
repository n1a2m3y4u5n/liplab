import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma node 58:11, 데스크톱 1440 기준 픽셀 이식).
 * 경로 노드는 DOKA 마스코트(완료/현재/잠김) — Figma export(/ui/node-*.svg) 그대로.
 * 실 데이터: curriculumAPI.getStages()의 단계별 status(mastered/in_progress/unlocked/locked) + attempts.
 */
// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐 currentScenario를 세팅한 뒤 /practice로 진입한다.
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/conversation' }
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(main.py _STAGEn_MIN_ATTEMPTS와 정합).
const STAGE_TOTAL = { viseme: 15, word: 12, sentence: 10, conversation: 8 }

// Figma "Button / Primary" (75:23) — 3D 하단테두리(brand + brand-dark).
const BTN_3D =
  'flex w-full items-center justify-center rounded-[16px] border-2 border-b-[6px] border-primary-700 bg-primary-500 py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white transition hover:bg-primary-600 active:translate-y-[2px] active:border-b-2 disabled:opacity-50'

/** DOKA 노드 — 76px 슬롯에 SVG가 오버플로(inset -7% -12% -17% -12% → 124% 폭)로 얹힌다. */
function Node({ status }) {
  if (status === 'mastered') return (
    <span className="relative block size-[76px]">
      <img src="/ui/node-done.svg" alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
      <img src="/ui/node-check-badge.svg" alt="" className="absolute size-[24px]" style={{ left: '55px', top: '54px' }} />
    </span>
  )
  if (status === 'current') return (
    <span className="relative flex size-[87.4px] items-center justify-center">
      <img src="/ui/node-ring.svg" alt="" className="pointer-events-none absolute size-[109px] max-w-none" />
      <img src="/ui/node-current.svg" alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
    </span>
  )
  return (
    <span className="relative block size-[76px]">
      <img src="/ui/node-locked.svg" alt="" className="absolute max-w-none" style={{ top: '-7%', left: '-12%', width: '124%', height: '124%' }} />
    </span>
  )
}

function StageArrow({ dir, onClick, disabled, className = '' }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'}
      className={`hidden size-11 shrink-0 items-center justify-center transition sm:flex ${disabled ? 'opacity-30' : 'hover:opacity-80 active:scale-95'} ${className}`}>
      <img src={dir === 'prev' ? '/ui/stage-arrow-prev.svg' : '/ui/stage-arrow-next.svg'} alt="" className="size-[58px] max-w-none" />
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

        {/* 경로 (Figma 61:18) */}
        {!stages ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="relative flex w-full flex-col items-center py-2">
            {/* 좌우 단계 이동 화살표 (Figma 145:18 / 145:20) — 경로 좌우 끝, 현재 노드 높이 */}
            <StageArrow dir="prev" disabled={!prevRoute} onClick={() => prevRoute && navigate(prevRoute)}
              className="absolute left-0 top-1/2 -translate-y-1/2" />
            <StageArrow dir="next" disabled onClick={() => {}}
              className="absolute right-0 top-1/2 -translate-y-1/2" />

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

                    {/* 상세 카드 (Figma 75:12) — 노드 오른쪽, 왼쪽 삼각 포인터. 설명 문구 없음 */}
                    {st === 'current' && (
                      <div className="absolute left-full top-1/2 z-10 ml-[28px] hidden w-[360px] max-w-[52vw] -translate-y-1/2 flex-col gap-[14px] rounded-[20px] border-2 border-line bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] sm:flex">
                        <span className="absolute -left-[9px] top-1/2 h-4 w-4 -translate-y-1/2 rotate-45 border-b-2 border-l-2 border-line bg-white" />
                        <p className="text-[22px] font-bold tracking-[-0.44px] text-ink">{s.title}</p>
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
                    )}
                  </div>
                </div>
              )
            })}
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
