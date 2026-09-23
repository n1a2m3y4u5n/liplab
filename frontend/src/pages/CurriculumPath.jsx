import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI, speakAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 58:11 독화 / 171:38 발화). DOKA 마스코트 노드.
 * 독화·발화 두 트랙이 같은 화면을 쓰고 색만 다르다(독화=보라, 발화=분홍). ?track=speak 로 발화 경로를 연다.
 *  - 독화: curriculumAPI.getStages() → 1~4단계(입모양·단어·문장·대화)
 *  - 발화: speakAPI.getCurriculum() → 0~5단계(발성·운율·모음·자음·단어·문장), /learn/speaking?stage=N
 * 상태: 진행중(58:11) · 잠김+건너뛰기 말풍선(78:8) · 건너뛰기 확인(79:5) · 해금(80:6).
 * 건너뛰기는 백엔드 skip API가 없어 프론트 전용(setTrack start_stage로 포인터 이동 + navigate).
 */

// ── 독화 트랙 ─────────────────────────────────────────────────────────────
// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐야 currentScenario가 세팅된 뒤 /practice 레슨이 뜬다.
// 바로 /practice로 보내면 시나리오가 없어 Practice가 되돌려보내므로 /learn/scenario로 진입한다.
const READ_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/conversation' }
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(main.py _STAGEn_MIN_ATTEMPTS와 정합).
const READ_TOTAL = { viseme: 15, word: 12, sentence: 10, conversation: 8 }

// 트랙별 색·DOKA 에셋 — 구조는 같고 색만 다르다.
const THEME = {
  read: {
    primary: '#7d53de', dark: '#5f3ab8', label: '독화',
    nodeDone: '/ui/node-done.svg', nodeCurrent: '/ui/node-current.svg', nodeRing: '/ui/node-ring.svg',
    badge: '/ui/node-check-badge.svg', arrowPrev: '/ui/stage-arrow-prev.svg', arrowNext: '/ui/stage-arrow-next.svg',
  },
  speak: {
    primary: '#ec4899', dark: '#be185d', label: '발화',
    nodeDone: '/ui/lp-171-38-node-done.svg', nodeCurrent: '/ui/lp-171-38-node-current.svg', nodeRing: '/ui/lp-171-38-node-ring.svg',
    badge: '/ui/lp-171-38-node-check-badge.svg', arrowPrev: '/ui/lp-171-38-stage-arrow-prev.svg', arrowNext: '/ui/lp-171-38-stage-arrow-next.svg',
  },
}

/** DOKA 노드 — 76px 슬롯에 SVG가 124%로 오버플로. */
function Node({ status, t }) {
  const overflow = { top: '-7%', left: '-12%', width: '124%', height: '124%' }
  if (status === 'mastered') return (
    <span className="relative block size-[76px]">
      <img src={t.nodeDone} alt="" className="absolute max-w-none" style={overflow} />
      <img src={t.badge} alt="" className="absolute size-[24px]" style={{ left: '55px', top: '54px' }} />
    </span>
  )
  if (status === 'current') return (
    <span className="relative flex size-[87.4px] items-center justify-center">
      <img src={t.nodeRing} alt="" className="pointer-events-none absolute size-[109px] max-w-none" />
      <img src={t.nodeCurrent} alt="" className="absolute max-w-none" style={overflow} />
    </span>
  )
  if (status === 'skip') return (
    <span className="relative block size-[76px]">
      <img src="/ui/lp-78-8-node-skip.svg" alt="" className="absolute max-w-none" style={overflow} />
    </span>
  )
  return (
    <span className="relative block size-[76px]">
      <img src="/ui/node-locked.svg" alt="" className="absolute max-w-none" style={overflow} />
    </span>
  )
}

function StageArrow({ dir, onClick, disabled, t, className = '' }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'}
      className={`hidden size-11 shrink-0 items-center justify-center transition sm:flex ${disabled ? 'opacity-30' : 'hover:opacity-80 active:scale-95'} ${className}`}>
      <img src={dir === 'prev' ? t.arrowPrev : t.arrowNext} alt="" className="size-[58px] max-w-none" />
    </button>
  )
}

/** 두 트랙의 단계 목록을 같은 모양으로 정규화 — { key, stage, no, title, route, status, attempts, total } */
function normalizeRead(stages) {
  return (stages || []).filter((s) => s.stage >= 1 && READ_ROUTE[s.key]).map((s) => ({
    key: s.key, stage: s.stage, no: s.stage, title: s.title, route: READ_ROUTE[s.key],
    status: s.status, attempts: s.attempts ?? 0, total: READ_TOTAL[s.key] || 12,
  }))
}
// 발화는 0단계(발성)부터 싣는다 — 백엔드가 0단계를 항상 열고 N단계는 N-1 숙달 시 해금하므로
// 빼면 새 사용자의 첫 노드가 잠긴 1단계가 된다. 표시 번호(no)는 1부터.
function normalizeSpeak(stages) {
  return (stages || []).map((s, i) => ({
    key: `speak-${s.stage}`, stage: s.stage, no: i + 1, title: s.title, route: `/learn/speaking?stage=${s.stage}`,
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || 8,
  }))
}

export default function CurriculumPath() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const track = searchParams.get('track') === 'speak' ? 'speak' : 'read'
  const t = THEME[track]
  const [data, setData] = useState({ read: null, speak: null })
  const [skipTarget, setSkipTarget] = useState(null)  // 건너뛰기 확인 중인 단계 key

  // 두 트랙을 한 번에 받아 두면 스위처 전환이 즉시 된다.
  useEffect(() => {
    curriculumAPI.getStages().then((d) => setData((p) => ({ ...p, read: normalizeRead(d.stages) }))).catch(() => setData((p) => ({ ...p, read: [] })))
    speakAPI.getCurriculum().then((d) => setData((p) => ({ ...p, speak: normalizeSpeak(d.stages) }))).catch(() => setData((p) => ({ ...p, speak: [] })))
  }, [])
  useEffect(() => { setSkipTarget(null) }, [track])

  const learn = data[track]
  const list = learn || []
  const currentIdx = list.findIndex((s) => s.status === 'in_progress' || s.status === 'unlocked')
  const nextLockedIdx = currentIdx >= 0 ? currentIdx + 1 : list.findIndex((s) => s.status === 'locked')
  const nodeStatus = (s, i) => {
    if (s.status === 'mastered') return 'mastered'
    if (i === currentIdx) return 'current'
    if (i === nextLockedIdx && s.status === 'locked') return 'skip'   // 다음 잠긴 단계 = 건너뛰기 후보
    return 'locked'
  }
  const cur = list[currentIdx] || list[0]
  const prevRoute = currentIdx > 0 ? list[currentIdx - 1].route : null
  const progTotal = cur?.total || 12
  const progCur = Math.min(progTotal, cur?.attempts ?? 0)

  const switchTrack = (k) => setSearchParams(k === 'speak' ? { track: 'speak' } : {}, { replace: true })
  const doSkip = async (s) => {
    if (track === 'read') { try { await curriculumAPI.setTrack('perception', s.stage) } catch { /* 무시 */ } }
    setSkipTarget(null)
    navigate(s.route)
  }

  // 3D 버튼(테마색)
  const btn3d = (extra = '') => `flex w-full items-center justify-center rounded-[16px] border-2 border-b-[6px] py-[18px] text-[20px] font-bold tracking-[-0.2px] text-white transition active:translate-y-[2px] active:border-b-2 ${extra}`

  return (
    <AppShell active="learn">
      <div className="mx-auto flex w-full max-w-[752px] flex-col items-center gap-6">
        {/* 트랙 스위처 (171:18) */}
        <div className="flex gap-1 rounded-[14px] bg-[#f1f1f5] p-1">
          {[['read', '독화'], ['speak', '발화']].map(([k, label]) => (
            <button key={k} type="button" onClick={() => switchTrack(k)}
              className={`rounded-[10px] px-[26px] py-2.5 text-[15px] font-bold transition ${track === k ? 'bg-white shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]' : 'text-[#8a8a9b]'}`}
              style={track === k ? { color: t.primary } : undefined}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더 (61:12) — 3D 하단테두리 */}
        <div className="flex w-full items-center gap-3.5 rounded-[18px] border-b-[5px] py-5 pl-[26px] pr-5 text-white"
          style={{ background: t.primary, borderColor: t.dark }}>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-bold opacity-[0.85]">{t.label} · {cur ? `${cur.no}단계` : '학습'}</span>
            <span className="text-[24px] font-bold tracking-[-0.48px]">{cur?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => navigate('/guide')}
            className="shrink-0 rounded-[12px] border-2 border-white/40 bg-white/[0.18] px-[18px] py-3 text-[14px] font-bold text-white transition hover:bg-white/30">가이드</button>
        </div>

        {/* 경로 (61:18) */}
        {!learn ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="relative flex w-full flex-col items-center py-2">
            <StageArrow dir="prev" t={t} disabled={!prevRoute} onClick={() => prevRoute && navigate(prevRoute)} className="absolute left-0 top-1/2 -translate-y-1/2" />
            <StageArrow dir="next" t={t} disabled onClick={() => {}} className="absolute right-0 top-1/2 -translate-y-1/2" />

            {list.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              const onClick = () => {
                if (st === 'skip') setSkipTarget(s.key)
                else if (clickable) navigate(s.route)
              }
              return (
                <div key={s.key} className="flex flex-col items-center">
                  {i > 0 && <div className="h-[58px] w-1.5 rounded-[3px]" style={{ background: list[i - 1].status === 'mastered' ? t.primary : '#e4e4ec' }} />}
                  <div className="relative">
                    <button type="button" disabled={!clickable} onClick={onClick}
                      className={clickable ? 'block cursor-pointer' : 'block cursor-not-allowed'}>
                      <Node status={st} t={t} />
                    </button>

                    {/* 건너뛰기 말풍선 (78:8) — 노드 위, 아래 방향 꼬리 */}
                    {st === 'skip' && skipTarget !== s.key && (
                      <button type="button" onClick={() => setSkipTarget(s.key)}
                        className="absolute bottom-full left-1/2 z-10 mb-3 hidden -translate-x-1/2 whitespace-nowrap rounded-[14px] border-2 border-line bg-white px-5 py-3 text-[15px] font-bold shadow-[0px_6px_16px_-2px_rgba(26,13,64,0.1)] sm:block"
                        style={{ color: t.dark }}>
                        여기로 건너뛸까요?
                        <span className="absolute left-1/2 top-full h-3 w-3 -translate-x-1/2 -translate-y-1/2 rotate-45 border-b-2 border-r-2 border-line bg-white" />
                      </button>
                    )}

                    {/* 건너뛰기 확인 팝오버 (79:5) — 앰버 테두리 */}
                    {st === 'skip' && skipTarget === s.key && (
                      <div className="absolute left-full top-1/2 z-20 ml-[28px] hidden w-[360px] max-w-[52vw] -translate-y-1/2 flex-col gap-[14px] rounded-[20px] border-2 border-[#f7b733] bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] sm:flex">
                        <span className="absolute -left-[9px] top-1/2 h-4 w-4 -translate-y-1/2 rotate-45 border-b-2 border-l-2 border-[#f7b733] bg-white" />
                        <p className="text-[21px] font-bold tracking-[-0.42px] text-ink">정말로 건너뛰시겠어요?</p>
                        <div className="flex gap-2.5">
                          <button type="button" onClick={() => setSkipTarget(null)}
                            className="flex-1 rounded-[14px] border-2 border-b-[5px] border-line bg-white py-[15px] text-center text-[16px] font-bold text-ink-muted transition active:translate-y-[1px] active:border-b-2">아니오</button>
                          <button type="button" onClick={() => doSkip(s)}
                            className="flex-1 rounded-[14px] border-2 border-b-[5px] py-[15px] text-center text-[16px] font-bold text-white transition active:translate-y-[1px] active:border-b-2"
                            style={{ background: t.primary, borderColor: t.dark }}>예, 건너뛸게요</button>
                        </div>
                      </div>
                    )}

                    {/* 상세 카드 (75:12) — 현재 노드 오른쪽, 설명 없음 */}
                    {st === 'current' && (
                      <div className="absolute left-full top-1/2 z-10 ml-[28px] hidden w-[360px] max-w-[52vw] -translate-y-1/2 flex-col gap-[14px] rounded-[20px] border-2 border-line bg-white px-6 py-[22px] shadow-[0px_10px_28px_-4px_rgba(26,13,64,0.12)] sm:flex">
                        <span className="absolute -left-[9px] top-1/2 h-4 w-4 -translate-y-1/2 rotate-45 border-b-2 border-l-2 border-line bg-white" />
                        <p className="text-[22px] font-bold tracking-[-0.44px] text-ink">{s.title}</p>
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center justify-between text-[13px] font-bold">
                            <span className="text-ink-muted">진행률</span>
                            <span style={{ color: t.primary }}>{progCur} / {progTotal}</span>
                          </div>
                          <div className="h-[10px] overflow-hidden rounded-full bg-[#ededf3]">
                            <div className="h-full rounded-full" style={{ width: `${(progCur / progTotal) * 100}%`, background: t.primary }} />
                          </div>
                        </div>
                        <button type="button" onClick={() => navigate(s.route)} className={btn3d()} style={{ background: t.primary, borderColor: t.dark }}>이어서 학습하기</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* 상세 바텀시트 (모바일) */}
        {cur && (
          <div className="fixed inset-x-0 bottom-[62px] z-20 rounded-t-[22px] border-t border-line bg-white px-5 pb-4 pt-4 shadow-[0_-8px_24px_-8px_rgba(26,13,64,0.12)] sm:hidden">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[16px] font-bold text-ink">{cur.title}</p>
              <span className="text-[12.5px] font-bold" style={{ color: t.primary }}>{progCur} / {progTotal}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#ededf3]">
              <div className="h-full rounded-full" style={{ width: `${(progCur / progTotal) * 100}%`, background: t.primary }} />
            </div>
            <button type="button" onClick={() => navigate(cur.route)}
              className="mt-3 w-full rounded-[14px] border-2 border-b-[5px] py-3.5 text-[17px] font-bold text-white active:translate-y-[1px] active:border-b-2"
              style={{ background: t.primary, borderColor: t.dark }}>이어서 학습하기</button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
