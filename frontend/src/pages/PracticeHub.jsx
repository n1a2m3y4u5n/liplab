import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { listenAPI } from '../api'
import { PRACTICE_MODES, modeAvailability } from '../lib/listenFlow'

/**
 * 연습 탭 허브 (Figma 96:14 · 모바일 238:34) — 단계와 무관하게 자유롭게 고르는 연습 모드 카드.
 * 각 카드는 기존 연습 화면으로 연결한다. 탭 제목 아래 설명 문구는 없다(§4-05).
 * 9/26 변경 내역 §2·§4-4: 다자 대화 카드를 뺐다(카드 4개 + 공사 중 자리). 여러 명 대화는 상황별 시나리오의 'AI 대화 → 여러 명 대화'로
 * 들어간다. 수어 카드 제목은 데스크톱 96:14·기능 화면 226:32의 "수어 보기"를 따른다(모바일 238:34는 아직 "수어 함께 보기").
 * 카드: lg 이상은 세로형(96:125 — 52px 칩·19px 제목·설명), lg 미만은 가로 행(238:125 — 44px 칩·제목/설명·화살표).
 * 6번째 칸은 Figma의 '공사 중' 자리(98:15)에 '입모양 교실'을 둔다 — 웹캠 따라 하기·조음 교정·아바타 거울·
 * 성도 실험(축 D·E·F·K)이 모인 입모양 학습 자료(/learn/viseme?tab=learn)로, 다른 진입점이 없던 화면이다.
 *
 * 10월: 아래에 '소리 듣기' 묶음을 더했다(Figma 밖, 같은 카드 틀). 소리 짝 집중 연습·받아쓰기·소음 속 듣기·상황별 대화 듣기·
 * 듣기 조건 연습(/listen/practice/:mode)과 소리 교실(/listen/classroom). 칩은 트랙색 청록 하나로 맞춘다.
 * 서버가 연습 모드 목록(GET /api/listen/practice/modes)에서 available:false를 주면 그 카드는 '잠김'으로 흐리게 둔다. 이유가 여러 카드에서 같으면
 * (소리 확인을 한 번도 안 한 경우 등) 묶음 위에 한 줄로 한 번만 적고, 소리 확인이 필요하면 그리 가는 버튼을 둔다. 이유가 카드마다 다르면 카드에 적는다.
 * 목록을 못 받으면(아직 없는 API 등) 카드는 열어 두고, 들어간 화면이 '준비 중'을 알린다.
 */
const CARDS = [
  { key: 'free', title: '자유 발화', desc: '내가 쓴 문장을 소리 내어 확인해요', icon: '/ui/card-free.svg', chip: 'bg-pastel-pink', to: '/pronounce' },
  { key: 'scenario', title: '상황별 시나리오', desc: '카페·병원 등 상황을 골라 연습해요', icon: '/ui/card-scenario.svg', chip: 'bg-pastel-amber', to: '/learn/scenario' },
  { key: 'sign', title: '수어 보기', desc: '문장을 수어로도 확인할 수 있어요', icon: '/ui/card-sign.svg', chip: 'bg-pastel-mint', to: '/learn/sign' },
  { key: 'endless', title: '엔드리스 학습', desc: '틀렸던 유형이 계속 나와요', icon: '/ui/tab-card-endless.svg', chip: 'bg-pastel-indigo', to: '/learn/endless' },
  { key: 'mouth', title: '입모양 교실', desc: '웹캠으로 따라 하고 안 보이는 혀 위치도 확인해요', icon: '/ui/nav-learn.svg', chip: 'bg-pastel-violet', to: '/learn/viseme?tab=learn' },
]

// 소리 듣기 카드 그림(24px 선 그림, 청록). 그림 파일 대신 currentColor로 그려 트랙색을 따른다
const LISTEN_ICON = {
  contrast: <><path d="M4 9v6M8 6v12M12 9v6" /><path d="M16 7v10M20 10v4" opacity="0.55" /></>,
  dictation: <><path d="M4 18h9M4 13h12M4 8h16" /><path d="m17 19 4-4-2-2-4 4v2z" /></>,
  noise_endless: <><path d="M3 12h2l2-5 3 10 3-8 2 5 2-2h4" /></>,
  scenario: <><path d="M12 21s-6-5.5-6-10.5a6 6 0 0 1 12 0C18 15.5 12 21 12 21z" /><circle cx="12" cy="10.5" r="2" /></>,
  conditions: <><path d="M6 4h3l1.5 4-2 1.5a10 10 0 0 0 6 6l1.5-2 4 1.5V18a2 2 0 0 1-2 2A15 15 0 0 1 4 6a2 2 0 0 1 2-2z" /></>,
  classroom: <><path d="M4 6.5C4 5.7 4.7 5 5.5 5H11v14H5.5A1.5 1.5 0 0 1 4 17.5zM20 6.5c0-.8-.7-1.5-1.5-1.5H13v14h5.5c.8 0 1.5-.7 1.5-1.5z" /></>,
}
const LISTEN_CARDS = [
  ...['contrast', 'dictation', 'noise_endless', 'scenario', 'conditions'].map((k) => ({ key: k, title: PRACTICE_MODES[k].title, desc: PRACTICE_MODES[k].desc, to: `/listen/practice/${k}` })),
  { key: 'classroom', title: '소리 교실', desc: '소리 짝을 여러 목소리로 들어 봐요', to: '/listen/classroom' },
]

function CardIcon({ card }) {
  if (card.icon) return <img src={card.icon} alt="" className="size-[22px] lg:size-6" />
  return (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className="size-[22px] text-listen-dark lg:size-6">
      {LISTEN_ICON[card.key]}
    </svg>
  )
}

function PracticeCard({ card, onClick, off = null }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!!off}
      className="flex items-center gap-3.5 rounded-16 border-2 border-b-5 border-line bg-white p-4 text-left transition-transform enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed lg:flex-col lg:items-start lg:rounded-20 lg:px-[22px] lg:py-6"
    >
      <span className={`icon-chip-sm lg:icon-chip ${card.chip || 'bg-listen-tint'} ${off ? 'opacity-50 grayscale' : ''}`}>
        <CardIcon card={card} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[3px] leading-figma lg:gap-3.5">
        <span className={`text-[16px] font-bold lg:text-[19px] lg:tracking-[-0.38px] ${off ? 'text-ink-muted' : 'text-ink'}`}>
          {card.title}{off && <span className="ml-2 align-middle text-[12px] font-bold text-ink-faint lg:text-[13px]">잠김</span>}
        </span>
        <span className="text-[12.5px] text-ink-muted lg:text-[14px] lg:leading-[1.65]">{typeof off === 'string' ? off : card.desc}</span>
      </span>
      {/* 모바일 행 화살표(238:131 = review-arrow, 6×12 칸에 8×14 에셋) */}
      <span aria-hidden className={`relative h-3 w-1.5 shrink-0 lg:hidden ${off ? 'opacity-0' : ''}`}>
        <img src="/ui/review-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
      </span>
    </button>
  )
}

export default function PracticeHub() {
  const navigate = useNavigate()
  const [avail, setAvail] = useState({})
  useEffect(() => {
    let on = true
    listenAPI.practiceModes().then((m) => { if (on) setAvail(modeAvailability(Array.isArray(m) ? m : m?.modes)) }).catch(() => {})
    return () => { on = false }
  }, [])
  const offList = LISTEN_CARDS.filter((c) => avail[c.key] && !avail[c.key].available)
  const reasons = [...new Set(offList.map((c) => avail[c.key].reason || ''))]
  const shared = offList.length > 1 && reasons.length === 1 ? reasons[0] : null   // 같은 이유면 묶음 위에 한 번만
  const offReason = (key) => (avail[key] && !avail[key].available ? (shared != null ? true : avail[key].reason || '곧 열려요') : null)
  return (
    <AppShell active="practice" title="연습">
      <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2 lg:gap-4">
        {CARDS.map((c) => (
          <PracticeCard key={c.key} card={c} onClick={() => navigate(c.to)} />
        ))}
      </div>
      <section aria-labelledby="practice-listen" data-track="listen" className="mt-2 flex flex-col gap-2.5 lg:mt-3 lg:gap-4">
        <div className="flex items-baseline justify-between gap-3 leading-figma">
          <h2 id="practice-listen" className="text-[18px] font-bold tracking-[-0.36px] text-ink lg:text-[21px]">소리 듣기</h2>
          <span className="text-[12px] text-ink-muted lg:text-[13px]">보청기·인공와우로 말소리 듣기</span>
        </div>
        {shared != null && (
          <div className="flex flex-col gap-2.5 rounded-14 bg-surface-sunken px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="break-keep text-[13px] leading-[1.6] text-ink-muted lg:text-[14px]">{shared || '지금은 열 수 없어요.'}</p>
            {/소리 확인/.test(shared) && (
              <button type="button" onClick={() => navigate('/learn/listening?stage=0')} className="btn-primary min-h-[44px] shrink-0 px-4 py-2 text-[14px]">소리 확인 하러 가기</button>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2 lg:gap-4">
          {LISTEN_CARDS.map((c) => (
            <PracticeCard key={c.key} card={c} off={offReason(c.key)} onClick={() => navigate(c.to)} />
          ))}
        </div>
      </section>
    </AppShell>
  )
}
