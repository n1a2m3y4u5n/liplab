import { useEffect, useState } from 'react'
import { ModalClose } from './Modal'
import useFocusTrap from '../hooks/useFocusTrap'
import TeamAvatar from './TeamAvatar'
import { TEAM, REPO_URL } from '../config/team'

/**
 * 사용법 가이드 모달 (Figma "09. 사용법 가이드" 338:57 ~ 342:348).
 * 딤 오버레이 + 중앙 큰 흰 카드(rounded-24, 큰 그림자). 좌측 그룹형 세로 탭 + 우측 컨텐츠.
 * 배경 클릭·ESC로 닫힌다. 모바일에서는 좌측 탭이 상단 가로 스크롤 탭으로 폴백한다(Figma에 모바일 가이드 없음).
 *
 * Figma 스펙:
 *  - 카드 w-[1080px] h-[680px] rounded-24 shadow-modal · 오버레이 overlay 50%
 *  - Guide nav w-[248px] bg-surface-nav border-r-1.5 pt-28 pb-24 px-16 gap-2
 *    · 제목 20px bold tracking-[-.4px] / 그룹 라벨 11.5px bold ink-hint tracking-[.345px]
 *    · 탭 14.5px bold, 활성 = primary-tint 배경 + primary 텍스트, 비활성 = ink-muted
 *  - Guide content pl-36 pr-30 py-30 gap-22 / 제목 26px bold tracking-[-.65px] / 닫기 36px(338:237)
 *  - 내용(Body 766px)은 탭마다 네 가지 꼴이다.
 *    · overview(01): 화면 축소본 766×404 + 아래 주석 2열(338:273)
 *    · screens(02·03·04·06~10): 화면 축소본 + 오른쪽 주석(Screen guide). 축소본은 Figma "Mini screen" 노드를
 *      PNG 2배로 내보낸 이미지다(핸드오프 §0-9, public/ui/lp-<노드>-guide-*.png). 03·04는 축소본 2장에 작은 주석.
 *    · tips(05): 번호 + 요령 + 작은 예시, 2열 3행(340:249)
 *    · team(11): 팀원 5명 + 소스 코드(342:530). 역할 '개1발'(372:121)은 Figma 오타로 보고 '개발'로 쓴다.
 */

// 주석(Annot, 345:295) — 점(10×20 에셋) + 소제목 + 설명. small = 03·04 레슨 탭(14px·12px, 간격 9).
function Annotation({ h, d, small = false }) {
  return (
    <div className={`flex items-start ${small ? 'gap-[9px]' : 'gap-[10px]'}`}>
      <img src="/ui/lp-366-91-guide-dot.svg" alt="" aria-hidden className="h-5 w-[10px] shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-px">
        <p className={`font-bold leading-figma text-ink ${small ? 'text-[14px]' : 'text-[14.5px]'}`}>{h}</p>
        <p className={`break-keep leading-[1.58] text-ink-muted ${small ? 'text-[12px]' : 'text-[12.5px]'}`}>{d}</p>
      </div>
    </div>
  )
}

// 화면 축소본 — Figma에서 내보낸 PNG(2배). 너비는 Figma 값, 좁은 화면에서는 칸에 맞춰 줄어든다.
function Shot({ src, w, h }) {
  return <img src={src} alt="" width={w} height={h} className="h-auto w-full shrink-0" style={{ maxWidth: w }} />
}

// 그룹 → 탭. kind: overview | screens | tips | team. annots = [소제목, 설명] (Figma 원문).
const GROUPS = [
  {
    label: '시작',
    tabs: [
      {
        key: 'tour', title: '화면 둘러보기', kind: 'overview',
        shots: [{ src: '/ui/lp-338-274-guide-overview.png', w: 766, h: 404 }],
        annots: [
          ['내 기록', '불꽃은 연속 학습 일수, 별은 XP, 육각형은 레벨이에요. 사진을 누르면 프로필로 가요.'],
          ['오른쪽 패널', '오늘의 과제와 복습할 오답·북마크 수를 어느 탭에서든 확인해요.'],
        ],
      },
    ],
  },
  {
    label: '학습',
    tabs: [
      {
        key: 'learn', title: '학습 탭', kind: 'screens',
        shots: [{ src: '/ui/lp-345-147-guide-learn.png', w: 446, h: 560 }],
        annots: [
          ['트랙 전환', '독화 · 발화를 골라요. 트랙마다 경로와 진도가 따로 저장돼요.'],
          ['가이드', '이 단계에서 무엇을 배우는지 미리 봐요.'],
          ['레슨 노드', '연한 DOKA는 끝낸 레슨, 링을 두른 큰 DOKA는 지금 할 레슨, 잠든 DOKA는 아직 열리지 않은 레슨이에요.'],
          ['단계 이동', '좌우 화살표로 이전 · 다음 단계를 둘러봐요. 잠긴 단계도 한 번 더 확인을 받고 들어갈 수 있어요.'],
          ['레슨 카드', '지금 할 레슨을 누르면 떠요. 진행률을 보고 이어서 학습하기로 시작해요.'],
        ],
      },
      {
        key: 'reading', title: '독화 레슨', kind: 'screens', small: true,
        shots: [{ src: '/ui/lp-348-81-guide-read-q.png', w: 238, h: 358 }, { src: '/ui/lp-348-135-guide-read-wrong.png', w: 238, h: 358 }],
        annots: [
          ['북마크', '다시 보고 싶은 문제를 저장해요.'],
          ['입모양 영상', '3D 아바타의 입모양이 계속 반복돼요. 알아볼 때까지 보면 돼요.'],
          ['보기 고르기', '글자를 누르거나 숫자 키 1~4로 골라요.'],
          ['결과 바', '맞히면 초록, 틀리면 빨강이에요. 틀리면 정답을 함께 보여주고 복습 목록에 담아요.'],
        ],
      },
      {
        key: 'speaking', title: '발화 레슨', kind: 'screens', small: true,
        shots: [{ src: '/ui/lp-348-233-guide-speak-before.png', w: 238, h: 358 }, { src: '/ui/lp-348-268-guide-speak-result.png', w: 238, h: 358 }],
        annots: [
          ['입모양 따라 하기', '아바타의 입모양을 보고 그대로 따라 해요.'],
          ['마이크', '누르고 말한 뒤 다시 누르면 끝나요.'],
          ['발음 정확도', '목표 발음에 얼마나 가까웠는지 %로 보여줘요.'],
          ['소리별 결과', '초록은 잘했어요, 주황은 조금 더, 빨강은 다시 연습이에요.'],
          ['자세히 보기', '들린 발음, 소리와 입모양을 합친 점수, DOKA의 한마디를 봐요.'],
        ],
      },
      { key: 'strategy', title: '독화 요령', kind: 'tips' },
    ],
  },
  {
    label: '탭 안내',
    tabs: [
      {
        key: 'practice', title: '연습', kind: 'screens',
        shots: [{ src: '/ui/lp-346-77-guide-practice.png', w: 446, h: 560 }],
        annots: [
          ['자유 발화', '내가 쓴 문장을 입력하면 3D 입모양과 혀 위치 같은 소리 내는 법을 보여줘요.'],
          ['상황별 시나리오', '카페 · 병원 · 학교 같은 장소와 난이도를 골라 문장 테스트나 AI 대화로 연습해요.'],
          ['수어 함께 보기', '문장을 수어 영상과 입모양 아바타로 나란히 봐요.'],
          ['엔드리스 학습', '숙달도가 낮은 유형만 골라 끝없이 나와요. 원할 때 멈추면 돼요.'],
        ],
      },
      {
        key: 'task', title: '과제', kind: 'screens',
        shots: [{ src: '/ui/lp-346-291-guide-task.png', w: 470, h: 407 }],
        annots: [
          ['오늘의 과제', '매일 새로 주어져요. 1 / 2처럼 채운 만큼 보여주고, 오늘 남은 시간도 함께 보여요.'],
          ['특별 과제', '일주일 단위의 조금 긴 도전이에요.'],
          ['배지', '조건을 채우면 모여요. 누르면 크게 보고, 전체 학습자 중 몇 %가 가졌는지 알 수 있어요. 회색은 아직 받지 못한 배지예요.'],
        ],
      },
      {
        key: 'review', title: '복습', kind: 'screens',
        shots: [{ src: '/ui/lp-346-516-guide-review.png', w: 446, h: 560 }],
        annots: [
          ['오답 복습', '레슨에서 틀린 문제가 자동으로 모여요. 잊어버릴 때쯤 다시 나오도록 순서를 맞춰줘요.'],
          ['북마크 복습', '레슨 중 북마크 버튼으로 저장한 문제예요.'],
          ['항목', '언제 몇 번 틀렸는지 보여주고, 누르면 그 문제로 가요.'],
          ['지우기', '누르면 항목마다 체크박스가 생겨요. 골라서 한 번에 지워요.'],
        ],
      },
      {
        key: 'analysis', title: '분석', kind: 'screens',
        shots: [{ src: '/ui/lp-347-79-guide-analysis.png', w: 446, h: 560 }],
        annots: [
          ['맨 위 세 칸', '총 학습 시간 · 평균 정확도 · 연속 학습 일수예요.'],
          ['학습시간 추이', '최근 7주 동안 주마다 얼마나 공부했는지 막대로 보여줘요.'],
          ['정확도 추이', '주별 정답률이 어떻게 변했는지 선으로 보여줘요.'],
          ['활동 캘린더', '공부한 날이 잔디처럼 칠해져요. 진할수록 많이 한 날이에요.'],
          ['회차 히스토리', '레슨마다 정답률을 보고, 누르면 문제별로 어떻게 들렸는지까지 봐요.'],
          ['전체 통계', '가입 후 총 학습 회차, 푼 문제, 배지, 트랙별 진도를 모아 봐요.'],
        ],
      },
      {
        key: 'profile', title: '프로필', kind: 'screens',
        shots: [{ src: '/ui/lp-347-294-guide-profile.png', w: 446, h: 560 }],
        annots: [
          ['자가진단 다시 하기', '시작 단계를 새로 추천받아요. 지금까지의 기록은 그대로 남아요.'],
          ['계정 설정', '이름 · 이메일 · 비밀번호와 사진을 바꾸고, 로그아웃도 여기서 해요.'],
          ['학습 초기화', '기록을 모두 지워요. 되돌릴 수 없어서 "초기화"를 직접 입력해야 진행돼요.'],
        ],
      },
    ],
  },
  {
    label: '더 알아보기',
    tabs: [{ key: 'about', title: '개발자 소개', kind: 'team' }],
  },
]

const TABS = GROUPS.flatMap((g) => g.tabs)

function CloseButton({ onClose }) {
  return <ModalClose onClose={onClose} />
}

// 01 화면 둘러보기(338:273) — 축소본 아래 주석 2열(간격 28)
function OverviewBody({ tab }) {
  return (
    <div className="flex flex-col gap-5">
      {tab.shots.map((s) => <Shot key={s.src} {...s} />)}
      <div className="grid gap-x-7 gap-y-[13px] sm:grid-cols-2">
        {tab.annots.map(([h, d]) => <Annotation key={h} h={h} d={d} />)}
      </div>
    </div>
  )
}

// 02·03·04·06~10(Screen guide) — 축소본(1~2장) + 오른쪽 주석. 축소본 사이 14, 주석까지 24(2장이면 14, 주석 안쪽 8)
function ScreensBody({ tab }) {
  const two = tab.shots.length > 1
  return (
    <div className={`flex flex-col md:flex-row md:items-start ${two ? 'gap-[14px]' : 'gap-6'}`}>
      <div className={two ? 'grid grid-cols-2 gap-[14px] md:flex md:shrink-0' : 'md:shrink-0'}>
        {tab.shots.map((s) => <Shot key={s.src} {...s} />)}
      </div>
      <div className={`flex min-w-0 flex-1 flex-col ${tab.small ? 'gap-[11px] md:pl-2' : 'gap-[13px]'}`}>
        {tab.annots.map(([h, d]) => <Annotation key={h} h={h} d={d} small={tab.small} />)}
      </div>
    </div>
  )
}

// 05 독화 요령(340:249) — 번호(30px, primary-faint) + 제목 16 + 설명 13 + 예시. 2열 3행, 행 사이 구분선.
const CHIP = 'rounded-[8px] px-[10px] py-1 text-[13px] font-bold leading-figma'
const BUBBLE = 'rounded-[12px] rounded-bl-[3px] bg-inactive-bg px-3 py-1.5 text-[12.5px] leading-figma text-ink'
const TIPS = [
  ['01', '똑같이 보이는 소리가 있어요', 'ㅂ · ㅁ · ㅍ는 입술이 닫혀 똑같이 보여요. 정확히 읽기보다 가능성을 좁힌다고 생각해요.', (
    <div className="flex items-center gap-[10px]">
      {['ㅂ', 'ㅁ', 'ㅍ'].map((j) => (
        <div key={j} className="flex flex-col items-center gap-[3px]">
          <img src="/ui/lp-370-90-guide-lips.svg" alt="" aria-hidden className="h-[18px] w-[34px]" />
          <span className="text-[11.5px] font-bold leading-figma text-ink-muted">{j}</span>
        </div>
      ))}
      <span className="text-[12px] leading-figma text-ink-faint">모두 같은 입모양</span>
    </div>
  )],
  ['02', '문맥으로 메꿔요', '입모양이 애매하면 앞뒤 말과 상황으로 판단해요.', (
    <div className="flex items-center gap-2">
      <span className="text-[14px] font-bold leading-figma text-ink">___ 마셔요</span>
      <span className={`${CHIP} bg-primary-100 text-primary-700`}>물</span>
      <span className={`${CHIP} bg-inactive-bg text-ink-hint line-through`}>불</span>
    </div>
  )],
  ['03', '모음을 닻으로 삼아요', '자음보다 모음이 훨씬 잘 보여요. 모음 뼈대를 먼저 잡고 자음을 채워요.', (
    <div className="flex items-center gap-1.5">
      {['ㅏ', 'ㅣ', 'ㅗ', 'ㅜ'].map((v) => <span key={v} className={`${CHIP} bg-primary-100 text-primary-700`}>{v}</span>)}
    </div>
  )],
  ['04', '첫 소리에 집중해요', '단어의 첫 입모양에 정보가 가장 많아요. 시작을 놓치면 뒤가 다 흔들려요.', (
    <p className="flex items-baseline gap-px font-bold leading-figma">
      <span className="text-[22px] text-primary-500">사</span><span className="text-[16px] text-ink-pale">과</span>
    </p>
  )],
  ['05', '보기 좋은 환경을 골라요', '밝은 곳에서 얼굴이 정면으로 보이고 천천히 말할 때 잘 보여요.', <span className={BUBBLE}>천천히, 마주 보고 말해 주세요</span>],
  ['06', '모르면 되물어요', '전부 읽을 필요는 없어요. 핵심 단어만 확인해도 충분해요.', <span className={BUBBLE}>○○ 말씀이세요?</span>],
]

function TipsBody() {
  const rows = [TIPS.slice(0, 2), TIPS.slice(2, 4), TIPS.slice(4, 6)]
  return (
    <div className="flex flex-col">
      {rows.map((row, i) => (
        <div key={row[0][0]} className={`flex flex-col gap-6 md:flex-row md:gap-11 ${i === 0 ? 'pb-[22px] pt-1' : 'border-t border-fill py-[22px]'}`}>
          {row.map(([n, h, d, ex]) => (
            <div key={n} className="flex gap-4 md:w-[361px] md:shrink-0">
              <p className="w-[42px] shrink-0 text-[30px] font-bold leading-figma tracking-[-0.9px] text-primary-faint">{n}</p>
              <div className="flex min-w-0 flex-1 flex-col items-start gap-1.5">
                <p className="text-[16px] font-bold leading-figma text-ink">{h}</p>
                <p className="break-keep text-[13px] leading-[1.6] text-ink-muted">{d}</p>
                <div className="pt-0.5">{ex}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// 11 개발자 소개(342:530) — 사진(또는 DOKA) 60 + 이름 17 · 역할 13.5 · 핸들 12.5. 팀 정보는 config/team.js(랜딩과 같이 씀).
function Member({ m }) {
  return (
    <div className="flex items-center gap-4 md:w-[361px] md:shrink-0">
      <TeamAvatar m={m} />
      <div className="flex min-w-0 flex-col gap-1 whitespace-nowrap leading-figma">
        <p className="text-[17px] font-bold text-ink">{m.name}</p>
        <p className="text-[13.5px] text-ink-muted">{m.role}</p>
        {m.handle
          ? <p className="text-[12.5px] font-bold text-primary-500">{m.handle}</p>
          : <p className="text-[12px] text-ink-hint">{m.note}</p>}
      </div>
    </div>
  )
}

function TeamBody() {
  const rows = [TEAM.slice(0, 2), TEAM.slice(2, 4), TEAM.slice(4)]
  return (
    <div className="flex flex-col">
      <p className="pb-[22px] text-[15px] leading-[1.6] text-ink-muted">LIPLAB을 함께 만든 사람들이에요.</p>
      {rows.map((row, i) => (
        <div key={row[0].name} className={`flex flex-col gap-5 md:flex-row md:gap-11 ${i === 0 ? 'pb-5 pt-1' : 'border-t border-fill py-5'}`}>
          {row.map((m) => <Member key={m.name} m={m} />)}
        </div>
      ))}
      <p className="flex items-center gap-[10px] whitespace-nowrap border-t border-fill pt-5 font-bold leading-figma">
        <span className="text-[13px] text-ink-faint">소스 코드</span>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-[14px] text-primary-500 hover:underline">
          {REPO_URL.replace('https://', '')}
        </a>
      </p>
    </div>
  )
}

const BODY = { overview: OverviewBody, screens: ScreensBody, tips: TipsBody, team: TeamBody }

export default function GuideModal({ open, onClose }) {
  const [activeKey, setActiveKey] = useState(TABS[0].key)
  // 포커스 가두기·ESC 닫기·닫으면 연 버튼으로 포커스 복원(hooks/useFocusTrap)
  const dialogRef = useFocusTrap(open, onClose)

  // 열릴 때 첫 탭으로 리셋 + 배경 스크롤 잠금. onClose에 기대지 않아, 부모가 다시 그려져도 보던 탭이 첫 탭으로 돌아가지 않는다.
  useEffect(() => {
    if (!open) return undefined
    setActiveKey(TABS[0].key)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  if (!open) return null
  const active = TABS.find((t) => t.key === activeKey) || TABS[0]
  const Body = BODY[active.kind]

  const tabClass = (on) =>
    `w-full rounded-10 px-3 py-[9px] text-left text-[14.5px] font-bold transition-colors ${
      on ? 'bg-primary-100 text-primary-500' : 'text-ink-muted hover:bg-black/[0.03]'
    }`

  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/50 p-4"
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
            <h2 className="text-[22px] font-bold leading-figma tracking-[-0.65px] text-ink md:text-[26px]">{active.title}</h2>
            {/* 데스크톱 닫기(모바일은 상단 탭 헤더에 있음) */}
            <span className="hidden md:flex"><CloseButton onClose={onClose} /></span>
          </div>

          <div className="mt-[22px]">
            <Body tab={active} />
          </div>
        </div>
      </div>
    </div>
  )
}
