import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'

/**
 * 학습 탭 — 커리큘럼 경로 (Figma 리디자인 02). Duolingo식 세로 단계 경로.
 * 실 데이터: curriculumAPI.getStages()의 단계별 status(mastered/in_progress/unlocked/locked).
 * 완료=보라 체크, 현재=강조+상세카드(이어서 학습하기), 잠김=회색 자물쇠. 기존 학습 라우트로 이동.
 */
const STAGE_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/practice', conversation: '/conversation' }
const STAGE_DESC = {
  viseme: '입모양(비심) 10개 그룹을 눈으로 익혀요.',
  word: '음절·단어와 최소대립쌍으로 변별력을 길러요.',
  sentence: '상황별 문장을 읽고 따라 말해요.',
  conversation: '여러 상황의 실전 대화를 독화해요.',
}

function CheckGlyph() {
  return <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7" /></svg>
}
function PlayGlyph() {
  return <svg viewBox="0 0 24 24" className="h-8 w-8" fill="#fff"><path d="M8 5v14l11-7z" /></svg>
}
function LockGlyph() {
  return <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="#a8a8b8" strokeWidth="2.4"><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
}

function Node({ status }) {
  if (status === 'mastered') return <div className="flex h-[76px] w-[76px] items-center justify-center rounded-full border-primary-700 bg-primary-500"><CheckGlyph /></div>
  if (status === 'current') return (
    <div className="relative flex h-[76px] w-[76px] items-center justify-center rounded-full border-primary-700 bg-primary-500 shadow-lg">
      <span className="absolute -inset-2 rounded-full border-4 border-primary-300/70 animate-pulse" />
      <PlayGlyph />
    </div>
  )
  return <div className="flex h-[76px] w-[76px] items-center justify-center rounded-full border border-line bg-gray-100"><LockGlyph /></div>
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

  return (
    <AppShell active="learn">
      <div className="mx-auto flex w-full max-w-[640px] flex-col items-center gap-6">
        {/* 트랙 스위처 */}
        <div className="flex gap-1 rounded-[14px] bg-gray-100 p-1">
          {[['read', '독화'], ['speak', '발화']].map(([k, label]) => (
            <button key={k} type="button"
              onClick={() => (k === 'speak' ? navigate('/learn/speaking') : setTrack('read'))}
              className={`rounded-[10px] px-7 py-2.5 text-[15px] font-bold transition ${track === k ? 'bg-white text-primary-500 shadow-sm' : 'text-gray-400'}`}>
              {label}
            </button>
          ))}
        </div>

        {/* 유닛 헤더 */}
        <div className="flex w-full items-center gap-3.5 rounded-[18px] border-primary-700 bg-primary-500 py-5 pl-6 pr-5 text-white">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-bold opacity-85">독화 · {cur ? `${cur.stage}단계` : '학습'}</span>
            <span className="text-[24px] font-bold tracking-[-0.48px]">{cur?.title || '커리큘럼'}</span>
          </div>
          <button type="button" onClick={() => navigate('/guide')}
            className="shrink-0 rounded-xl border-2 border-white/40 bg-white/20 px-4 py-3 text-[14px] font-bold">가이드</button>
        </div>

        {/* 경로 */}
        {!stages ? (
          <p className="py-16 text-sm text-ink-muted">불러오는 중…</p>
        ) : (
          <div className="flex w-full flex-col items-center">
            {learn.map((s, i) => {
              const st = nodeStatus(s, i)
              const clickable = st !== 'locked'
              return (
                <div key={s.key} className="flex w-full flex-col items-center">
                  {i > 0 && <div className={`h-14 w-1.5 rounded ${learn[i - 1].status === 'mastered' ? 'bg-primary-500' : 'bg-line'}`} />}
                  <div className="flex w-full items-center justify-center gap-5">
                    <button type="button" disabled={!clickable}
                      onClick={() => clickable && navigate(STAGE_ROUTE[s.key])}
                      className={clickable ? 'cursor-pointer' : 'cursor-not-allowed'}>
                      <Node status={st} />
                    </button>
                    {st === 'current' && (
                      <div className="w-[320px] max-w-[60vw] rounded-[20px] border-2 border-line bg-white p-5 shadow-[0_10px_28px_-4px_rgba(26,13,64,0.12)]">
                        <p className="text-[20px] font-bold tracking-[-0.4px] text-ink">{s.title}</p>
                        <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">{STAGE_DESC[s.key]}</p>
                        <button type="button" onClick={() => navigate(STAGE_ROUTE[s.key])}
                          className="btn-primary mt-4 w-full !py-3.5 text-[18px]">이어서 학습하기</button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
            <img src="/ui/mascot.svg" alt="" className="mt-8 h-24 w-24" />
          </div>
        )}
      </div>
    </AppShell>
  )
}
