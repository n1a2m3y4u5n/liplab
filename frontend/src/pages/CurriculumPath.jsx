import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI, speakAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 리디자인 02). Duolingo식 세로 단계 경로.
 * 독화·발화 두 트랙이 같은 화면을 쓰고 색만 다르다(독화=보라 primary, 발화=로즈).
 *  - 독화: curriculumAPI.getStages() → 1~4단계(입모양·단어·문장·대화)
 *  - 발화: speakAPI.getCurriculum() → 0~5단계(발성·운율·모음·자음·단어·문장), /learn/speaking?stage=N
 * 완료=체크, 현재=별+상세카드(진행률·이어서 학습하기), 잠김=회색 별. ?track=speak 로 발화 경로를 연다.
 */

// ── 독화 트랙 ─────────────────────────────────────────────────────────────
// 문장 단계는 시나리오 선택(ScenarioHub)을 거쳐야 currentScenario가 세팅된 뒤 /practice 레슨이 뜬다.
// 바로 /practice로 보내면 시나리오가 없어 Practice가 되돌려보내므로 /learn/scenario로 진입한다.
const READ_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/conversation' }
const READ_DESC = {
  viseme: '입모양(비심) 10개 그룹을 눈으로 익혀요.',
  word: '자음과 모음이 만나 한 글자가 될 때 입모양이 어떻게 바뀌는지 익혀요. 「가·나·다」처럼 기본 조합을 다룹니다.',
  sentence: '상황별 문장을 읽고 따라 말해요.',
  conversation: '여러 상황의 실전 대화를 독화해요.',
}
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(main.py _STAGEn_MIN_ATTEMPTS와 정합).
const READ_TOTAL = { viseme: 15, word: 12, sentence: 10, conversation: 8 }

// ── 발화 트랙 ─────────────────────────────────────────────────────────────
// 단계 설명은 speak_curriculum.py의 desc/guide를 쓰되, 경로 카드용으로 한 문장씩 정리했다.
const SPEAK_DESC = {
  0: '배에 숨을 담고 「아—」를 2초 이상 곧게. 원할 때 목소리를 내고 길게 유지하는 연습이에요.',
  1: '같은 소리를 크게·작게·길게, 끝을 올리고 내리며. 목소리의 크기·길이·높낮이를 눈으로 확인해요.',
  2: '아·어·오·우·으·이·애·에 — 입 모양만 봐도 구별되는 기본 모음 8개를 또렷하게.',
  3: '마·바·파, 불/풀, 달/탈처럼 같은 자리에서 나는 소리를 입 모양과 바람으로 구별해 발음해요.',
  4: '한 음절에서 여러 음절로. 받침(끝소리)까지 살려 또박또박 말해요.',
  5: '평서문은 끝을 내리고 의문문은 끝을 올려요. 문장 억양까지 살려 말해요.',
}

// 트랙별 색 — 구조는 같고 색만 다르다.
const THEME = {
  read: {
    label: '독화',
    node: 'bg-primary-500', nodeShadow: 'shadow-[0_8px_20px_-4px_rgba(125,83,222,0.5)]', ring: 'ring-primary-200',
    header: 'bg-primary-500 shadow-[0_10px_28px_-8px_rgba(125,83,222,0.55)]',
    text: 'text-primary-500', bar: 'bg-primary-500', btn: 'btn-primary', arrow: '#7d53de', arrowHover: 'hover:border-primary-300',
    switch: 'text-primary-500',
  },
  speak: {
    label: '발화',
    node: 'bg-rose-500', nodeShadow: 'shadow-[0_8px_20px_-4px_rgba(244,63,94,0.5)]', ring: 'ring-rose-200',
    header: 'bg-rose-500 shadow-[0_10px_28px_-8px_rgba(244,63,94,0.55)]',
    text: 'text-rose-500', bar: 'bg-rose-500', btn: 'btn-speak', arrow: '#f43f5e', arrowHover: 'hover:border-rose-300',
    switch: 'text-rose-500',
  },
}

function CheckGlyph() {
  return <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
}
function StarGlyph({ color }) {
  return <svg viewBox="0 0 24 24" className="h-[30px] w-[30px]" fill={color}><path d="M12 2.5l2.9 5.9 6.5.95-4.7 4.58 1.11 6.47L12 17.9l-5.81 3.05 1.11-6.47L2.6 9.9l6.5-.95L12 2.5z" /></svg>
}

function Node({ status, t }) {
  if (status === 'mastered') return <div className={`flex h-[72px] w-[72px] items-center justify-center rounded-full ${t.node}`}><CheckGlyph /></div>
  if (status === 'current') return (
    <div className={`relative flex h-[72px] w-[72px] items-center justify-center rounded-full ${t.node} ${t.nodeShadow}`}>
      <span className={`absolute -inset-[6px] rounded-full ring-4 ${t.ring}`} />
      <StarGlyph color="#fff" />
    </div>
  )
  return <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-[#eceaf3]"><StarGlyph color="#c9c4dc" /></div>
}

function NavArrow({ dir, onClick, disabled, t }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={dir === 'prev' ? '이전 단계' : '다음 단계'}
      className={`hidden h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line bg-white shadow-sm transition sm:flex ${disabled ? 'opacity-30' : `${t.arrowHover} active:scale-95`}`}>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke={t.arrow} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d={dir === 'prev' ? 'M15 6l-6 6 6 6' : 'M9 6l6 6-6 6'} />
      </svg>
    </button>
  )
}

/** 두 트랙의 단계 목록을 같은 모양으로 정규화 — { key, no, title, desc, route, status, attempts, total } */
function normalizeRead(stages) {
  return (stages || []).filter((s) => s.stage >= 1 && READ_ROUTE[s.key]).map((s) => ({
    key: s.key, no: s.stage, title: s.title, desc: READ_DESC[s.key], route: READ_ROUTE[s.key],
    status: s.status, attempts: s.attempts ?? 0, total: READ_TOTAL[s.key] || 12,
  }))
}
function normalizeSpeak(stages) {
  return (stages || []).map((s, i) => ({
    key: `speak-${s.stage}`, no: i + 1, title: s.title, desc: SPEAK_DESC[s.stage] || s.desc, route: `/learn/speaking?stage=${s.stage}`,
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || 8,
  }))
}

export default function CurriculumPath() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const track = searchParams.get('track') === 'speak' ? 'speak' : 'read'
  const t = THEME[track]
  const [data, setData] = useState({ read: null, speak: null })

  // 두 트랙을 한 번에 받아 두면 스위처 전환이 즉시 된다.
  useEffect(() => {
    curriculumAPI.getStages().then((d) => setData((p) => ({ ...p, read: normalizeRead(d.stages) }))).catch(() => setData((p) => ({ ...p, read: [] })))
    speakAPI.getCurriculum().then((d) => setData((p) => ({ ...p, speak: normalizeSpeak(d.stages) }))).catch(() => setData((p) => ({ ...p, speak: [] })))
  }, [])

  const learn = data[track]
  const list = learn || []
  const currentIdx = list.findIndex((s) => s.status === 'in_progress' || s.status === 'unlocked')
  const nodeStatus = (s, i) => {
    if (s.status === 'mastered') return 'mastered'
    if (i === currentIdx) return 'current'
    return 'locked'
  }
  const cur = list[currentIdx] || list[0]
  const prevRoute = currentIdx > 0 ? list[currentIdx - 1].route : null
  const progTotal = cur?.total || 12
  const progCur = Math.min(progTotal, cur?.attempts ?? 0)

  const switchTrack = (k) => setSearchParams(k === 'speak' ? { track: 'speak' } : {}, { replace: true })

  return (
    <AppShell active="learn">
      <div className="mx-auto flex w-full max-w-[680px] flex-col items-center gap-6">
        {/* 트랙 스위처 */}
        <div className="flex gap-1 rounded-[14px] bg-gray-100 p-1">
          {[['read', '독화'], ['speak', '발화']].map(([k, label]) => (
            <button key={k} type="button" onClick={() => switchTrack(k)}
              className={`rounded-[10px] px-8 py-2.5 text-[15px] font-bold transition ${track === k ? `bg-white ${THEME[k].switch} shadow-sm` : 'text-gray-400'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더 */}
        <div className={`flex w-full items-center gap-3.5 rounded-[20px] py-5 pl-7 pr-5 text-white ${t.header}`}>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-bold opacity-80">{t.label} · {cur ? `${cur.no}단계` : '학습'}</span>
            <span className="text-[26px] font-bold tracking-[-0.52px]">{cur?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => navigate('/guide')}
            className="shrink-0 rounded-full bg-white/20 px-4 py-2 text-[13.5px] font-bold text-white hover:bg-white/30">가이드</button>
        </div>

        {/* 경로 */}
        {!learn ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="relative flex w-full flex-col items-center">
            {list.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              return (
                <div key={s.key} className="flex w-full flex-col items-center">
                  {i > 0 && <div className={`h-14 w-1.5 rounded ${list[i - 1].status === 'mastered' ? t.bar : 'bg-[#eceaf3]'}`} />}
                  <div className="flex w-full items-center justify-center gap-3">
                    {st === 'current' && <NavArrow dir="prev" t={t} disabled={!prevRoute} onClick={() => prevRoute && navigate(prevRoute)} />}
                    <button type="button" disabled={!clickable}
                      onClick={() => clickable && navigate(s.route)}
                      className={clickable ? 'cursor-pointer' : 'cursor-not-allowed'}>
                      <Node status={st} t={t} />
                    </button>
                    {st === 'current' ? (
                      <>
                        {/* 상세 카드 (데스크톱: 노드 옆, 왼쪽 삼각 포인터) */}
                        <div className="relative hidden w-[340px] max-w-[58vw] rounded-[20px] border border-line bg-white p-5 shadow-[0_10px_28px_-6px_rgba(26,13,64,0.12)] sm:block">
                          <span className="absolute -left-2 top-9 h-4 w-4 rotate-45 border-b border-l border-line bg-white" />
                          <p className="text-[20px] font-bold tracking-[-0.4px] text-ink">{s.title}</p>
                          <p className="mt-2 text-[13.5px] leading-relaxed text-ink-muted">{s.desc}</p>
                          <div className="mt-4 flex items-center justify-between text-[12.5px] font-bold">
                            <span className="text-ink-muted">진행률</span>
                            <span className={t.text}>{progCur} / {progTotal}</span>
                          </div>
                          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#eceaf3]">
                            <div className={`h-full rounded-full ${t.bar}`} style={{ width: `${(progCur / progTotal) * 100}%` }} />
                          </div>
                          <button type="button" onClick={() => navigate(s.route)}
                            className={`${t.btn} mt-4 w-full !py-3.5 text-[17px]`}>이어서 학습하기</button>
                        </div>
                        <NavArrow dir="next" t={t} disabled onClick={() => {}} />
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
              <span className={`text-[12.5px] font-bold ${t.text}`}>{progCur} / {progTotal}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#eceaf3]">
              <div className={`h-full rounded-full ${t.bar}`} style={{ width: `${(progCur / progTotal) * 100}%` }} />
            </div>
            <button type="button" onClick={() => navigate(cur.route)}
              className={`${t.btn} mt-3 w-full !py-3.5 text-[17px]`}>이어서 학습하기</button>
          </div>
        )}
      </div>
    </AppShell>
  )
}
