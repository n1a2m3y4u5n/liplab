import { useEffect, useState } from 'react'
import { ModalClose } from './Modal'

/**
 * 사용법 가이드 모달 (Figma node 338:57 — Modal / 사용법 가이드).
 * 딤 오버레이 + 중앙 큰 흰 카드(rounded-24, 큰 그림자). 좌측 그룹형 세로 탭 + 우측 컨텐츠.
 * 컨텐츠는 화면을 상징하는 안내 카드(page 배경색) + 주석 불릿으로 구성한다(실제 스크린샷 미사용).
 * 배경 클릭·ESC로 닫힌다. 모바일에서는 좌측 탭이 상단 가로 스크롤 탭으로 폴백한다.
 *
 * Figma 스펙(값 추측 없이 반영):
 *  - 카드 w-[1080px] h-[680px] rounded-24 shadow-modal · 오버레이 overlay 50%
 *  - Guide nav w-[248px] bg-surface-nav border-r-1.5 pt-28 pb-24 px-16 gap-2
 *    · 제목 20px bold tracking-[-.4px] / 그룹 라벨 11.5px bold ink-hint tracking-[.345px]
 *    · 탭 14.5px bold, 활성 = primary-tint 배경 + primary 텍스트, 비활성 = ink-muted
 *  - Guide content pl-36 pr-30 py-30 gap-22 / 제목 26px bold tracking-[-.65px]
 *    · 닫기 = Figma Close 에셋 36px(338:237, Modal.jsx ModalClose) / 안내 카드 bg-page border-1.5 rounded-14
 *    · 주석 = ● + 소제목 14.5px bold(ink) + 설명 12.5px(ink-muted) leading-1.6
 */

// 화면 안내 카드 아이콘 — public/ui의 nav·기능 아이콘을 primary 색으로 마스크 틴트(브랜드 통일, index.css .mask-icon).
function MaskIcon({ src, className = '' }) {
  return <span aria-hidden="true" className={`mask-icon text-primary-500 ${className}`} style={{ '--icon': `url(${src})` }} />
}

// 그룹 → 탭. 각 탭: title(사이드/헤더 공용), screen(안내 카드; 없으면 텍스트만), bullets(주석).
const GROUPS = [
  {
    label: '시작',
    tabs: [
      {
        key: 'tour', title: '화면 둘러보기',
        screen: { icon: '/ui/nav-learn.svg', name: '대시보드 둘러보기' },
        bullets: [
          { h: '내 기록', d: '불꽃은 연속 학습 일수, 별은 XP, 육각형은 레벨이에요. 사진을 누르면 프로필로 가요.' },
          { h: '오른쪽 패널', d: '오늘의 과제와 복습할 오답·북마크 수를 어느 탭에서든 확인해요.' },
          { h: '왼쪽 탭', d: '학습·연습·과제·복습·분석으로 바로 이동하고, 모바일에서는 아래쪽 탭 바를 써요.' },
        ],
      },
    ],
  },
  {
    label: '학습',
    tabs: [
      {
        key: 'learn', title: '학습 탭',
        screen: { icon: '/ui/nav-learn.svg', name: '학습 · 커리큘럼 경로' },
        bullets: [
          { h: '트랙 선택', d: '독화(입 읽기)와 발화(발음) 중 지금 훈련할 축을 골라요.' },
          { h: '단계별 경로', d: '기초부터 실전까지 레슨을 순서대로 밟고, 앞 단계를 익히면 다음이 열려요.' },
          { h: '이어서 학습', d: '현재 레슨을 누르면 진행률과 함께 바로 이어서 시작해요.' },
        ],
      },
      {
        key: 'reading', title: '독화 레슨',
        screen: { icon: '/ui/card-scenario.svg', name: '독화 학습' },
        bullets: [
          { h: '입모양부터 문장까지', d: '자음·모음 입모양, 단어, 상황별 문장을 3D 아바타로 단계별로 익혀요.' },
          { h: '문맥 추론', d: '같아 보이는 소리를 앞뒤 맥락으로 좁혀 맞히는 훈련이에요.' },
          { h: 'AI 문항', d: 'AI가 매번 새 문장을 내줘서 같은 문제만 반복하지 않아요.' },
        ],
      },
      {
        key: 'speaking', title: '발화 레슨',
        screen: { icon: '/ui/speak-mic.svg', name: '발화 학습' },
        bullets: [
          { h: '6단계 커리큘럼', d: '발성부터 운율·모음·자음·단어·문장 억양까지 순서대로 연습해요.' },
          { h: '실시간 피드백', d: '마이크로 말하면 크기·억양이 곡선으로 보이고, AI가 전사·채점·코칭해요.' },
          { h: '웹캠 미러', d: '내 입모양을 아바타와 나란히 두고 비교할 수 있어요.' },
        ],
      },
      {
        key: 'strategy', title: '독화 요령',
        screen: { icon: '/ui/card-retest.svg', name: '독화 전략' },
        bullets: [
          { h: '가능성 좁히기', d: 'ㅂ·ㅁ·ㅍ처럼 똑같이 보이는 소리가 많아요. 정확히 읽기보다 후보를 좁혀요.' },
          { h: '모음을 닻으로', d: '모음이 자음보다 잘 보여요. 모음 뼈대를 먼저 잡고 자음을 채워요.' },
          { h: '문맥으로 메꾸기', d: '입모양이 애매하면 앞뒤 말과 상황으로 판단해요.' },
        ],
      },
    ],
  },
  {
    label: '탭 안내',
    tabs: [
      {
        key: 'practice', title: '연습',
        screen: { icon: '/ui/nav-practice.svg', name: '연습 허브' },
        bullets: [
          { h: '자유 연습', d: '단계와 상관없이 다자 대화·상황별 시나리오·엔드리스 학습을 골라 풀어요.' },
          { h: '자유 발화', d: '내가 쓴 문장을 소리 내어 발음을 확인해요.' },
          { h: '수어 함께 보기', d: '문장을 한국수어(KSL) 영상으로도 확인할 수 있어요.' },
        ],
      },
      {
        key: 'task', title: '과제',
        screen: { icon: '/ui/nav-task.svg', name: '오늘의 과제' },
        bullets: [
          { h: '오늘의 과제', d: '매일 주어지는 작은 목표를 채우면 XP 보상을 받아요.' },
          { h: '주간 도전', d: '이번 주 목표를 이어가면 큰 보너스가 쌓여요.' },
          { h: '배지', d: '조건을 달성하면 배지를 모을 수 있어요.' },
        ],
      },
      {
        key: 'review', title: '복습',
        screen: { icon: '/ui/nav-review.svg', name: '복습' },
        bullets: [
          { h: '오답·북마크', d: '틀린 문제와 저장한 북마크를 나눠서 다시 풀어요.' },
          { h: '간격 반복', d: '잊어버릴 때쯤 다시 나오도록 예정된 항목을 오늘 것만 가볍게 확인해요.' },
          { h: '정리', d: '필요 없는 항목은 지우기로 목록에서 정리해요.' },
        ],
      },
      {
        key: 'analysis', title: '분석',
        screen: { icon: '/ui/nav-analytics.svg', name: '학습 분석' },
        bullets: [
          { h: '성장 기록', d: '평균 점수와 학습 흐름을 그래프로 확인해요.' },
          { h: '취약 입모양', d: '자주 헷갈리는 입모양을 짚어줘요.' },
          { h: 'AI 제안', d: '다음에 무엇을 연습하면 좋을지 알려줘요.' },
        ],
      },
      {
        key: 'profile', title: '프로필',
        screen: { icon: '/ui/nav-profile.svg', name: '프로필' },
        bullets: [
          { h: '내 정보', d: '레벨·XP·학습한 날·완료한 레슨을 한눈에 봐요.' },
          { h: '계정 설정', d: '이름·이메일·비밀번호를 바꾸고 로그아웃해요.' },
          { h: '다시 시작', d: '자가진단으로 단계를 재추천받거나 학습을 초기화할 수 있어요.' },
        ],
      },
    ],
  },
  {
    label: '더 알아보기',
    tabs: [
      {
        key: 'about', title: '개발자 소개',
        screen: null,
        bullets: [
          { h: 'LIPLAB', d: '청각장애인의 한국어 독화·발화 훈련을 돕는 AI 학습 웹앱이에요.' },
          { h: '만든 이유', d: '입모양 인지부터 실전 대화까지 단계별로 연습할 도구가 마땅치 않아 직접 만들었어요.' },
          { h: '함께 만들기', d: '개선 아이디어나 버그 제보는 언제든 환영해요.' },
        ],
      },
    ],
  },
]

const TABS = GROUPS.flatMap((g) => g.tabs)

function CloseButton({ onClose }) {
  return <ModalClose onClose={onClose} />
}

// 주석 불릿 — ● + 소제목 + 설명 (Figma Annot).
function Annotation({ h, d }) {
  return (
    <div className="flex gap-2.5">
      <span className="mt-[6px] h-[9px] w-[9px] shrink-0 rounded-full bg-primary-500" />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-[14.5px] font-bold text-ink">{h}</p>
        <p className="text-[12.5px] leading-[1.6] text-ink-muted">{d}</p>
      </div>
    </div>
  )
}

// 화면을 상징하는 안내 카드(bg-page) — 스크린샷 대체. 아이콘칩 + 화면명.
function ScreenCard({ screen }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-14 border-1.5 border-line bg-page px-6 py-8">
      <span className="flex h-14 w-14 items-center justify-center rounded-15 bg-primary-100">
        <MaskIcon src={screen.icon} className="h-7 w-7" />
      </span>
      <span className="text-[15px] font-bold text-ink">{screen.name}</span>
      <span className="text-[12px] text-ink-muted">이 화면에서 아래 기능을 확인해요</span>
    </div>
  )
}

export default function GuideModal({ open, onClose }) {
  const [activeKey, setActiveKey] = useState(TABS[0].key)

  // 열릴 때 첫 탭으로 리셋 + ESC 닫기 + 배경 스크롤 잠금.
  useEffect(() => {
    if (!open) return undefined
    setActiveKey(TABS[0].key)
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null
  const active = TABS.find((t) => t.key === activeKey) || TABS[0]

  const tabClass = (on) =>
    `w-full rounded-10 px-3 py-[9px] text-left text-[14.5px] font-bold transition-colors ${
      on ? 'bg-primary-100 text-primary-500' : 'text-ink-muted hover:bg-black/[0.03]'
    }`

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/50 p-4"
      onClick={onClose} role="dialog" aria-modal="true" aria-label="사용법 가이드">
      <div
        className="flex h-[680px] max-h-[90vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-24 bg-white shadow-modal md:flex-row"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 좌측 세로 탭 (데스크톱) */}
        <nav className="hidden w-[248px] shrink-0 flex-col gap-[2px] overflow-y-auto border-r-1.5 border-line bg-surface-nav px-4 pb-6 pt-7 leading-figma md:flex" aria-label="가이드 목차">
          <p className="pb-[10px] pl-3 text-[20px] font-bold tracking-[-0.4px] text-ink">사용법 가이드</p>
          {GROUPS.map((g) => (
            <div key={g.label} className="flex flex-col gap-[2px]">
              {/* 그룹 라벨 — Figma 회색 그룹 헤더(ink-hint) */}
              <p className="pb-[6px] pl-3 pt-[14px] text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">{g.label}</p>
              {g.tabs.map((t) => (
                <button key={t.key} type="button" onClick={() => setActiveKey(t.key)}
                  aria-current={t.key === activeKey ? 'true' : undefined}
                  className={tabClass(t.key === activeKey)}>
                  {t.title}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* 상단 가로 스크롤 탭 (모바일 폴백) */}
        <div className="shrink-0 border-b border-line bg-surface-nav md:hidden">
          <div className="flex items-center justify-between px-4 pt-4">
            <p className="text-[18px] font-bold text-ink">사용법 가이드</p>
            <CloseButton onClose={onClose} />
          </div>
          <div className="flex gap-2 overflow-x-auto px-4 pb-3 pt-3">
            {TABS.map((t) => {
              const on = t.key === activeKey
              return (
                <button key={t.key} type="button" onClick={() => setActiveKey(t.key)}
                  aria-current={on ? 'true' : undefined}
                  className={`shrink-0 whitespace-nowrap rounded-full px-3.5 py-2 text-[13.5px] font-bold transition-colors ${
                    on ? 'bg-primary-100 text-primary-500' : 'bg-surface-sunken text-ink-muted'
                  }`}>
                  {t.title}
                </button>
              )
            })}
          </div>
        </div>

        {/* 우측 컨텐츠 */}
        <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-6 py-6 md:py-[30px] md:pl-9 md:pr-[30px]">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-[22px] font-bold tracking-[-0.65px] text-ink md:text-[26px]">{active.title}</h2>
            {/* 데스크톱 닫기(모바일은 상단 탭 헤더에 있음) */}
            <span className="hidden md:block"><CloseButton onClose={onClose} /></span>
          </div>

          <div className="mt-5 flex flex-col gap-5">
            {active.screen && <ScreenCard screen={active.screen} />}
            <div className="grid gap-x-7 gap-y-4 sm:grid-cols-2">
              {active.bullets.map((b) => <Annotation key={b.h} {...b} />)}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
