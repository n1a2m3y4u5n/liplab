import { GROUPS, TABS } from './guide/guideContent'
import { useEffect, useRef, useState } from 'react'
import { ModalClose } from './Modal'
import useFocusTrap from '../hooks/useFocusTrap'
import TeamAvatar from './TeamAvatar'
import { TEAM, REPO_URL } from '../config/team'
import { TeamMemberDetail, ContactLine } from './TeamMemberDetail'
import { ShotSet, useAnnotLink } from './guide/GuideDemo'

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
 *  - 내용(Body 766px)은 탭마다 다섯 가지 꼴이다.
 *    · overview(01): 화면 축소본 766×404 + 아래 주석 2열(338:273)
 *    · screens(02·03·04·06~10): 화면 축소본 + 오른쪽 주석(Screen guide). 03·04는 축소본 2장에 작은 주석.
 *      축소본은 9/28부터 PNG 대신 코드로 그린 목업이다(guide/GuideMockups, shots의 mock 키). src를 주면 예전처럼 이미지를 그린다.
 *  - 주석 셋째 값은 목업 안 영역 키다. 주석을 가리키거나 누르면 그 영역이 강조되고, 목업의 번호 배지를 눌러도 주석이 강조된다.
 *    demo가 있는 탭(03·04)은 목업이 짧은 시연을 반복한다(guide/GuideDemo, 동작 최소화면 멈춘 마지막 장면).
 *    · tips(05): 번호 + 요령 + 작은 예시, 2열 3행(340:249)
 *    · notes: 사진 없이 주석 2열 + 단계 목록(처음 시작하기·말하기 6단계, 9/28 추가, Figma 프레임 없음)
 *    · team(11): 팀원 5명 + 소스 코드(342:530). 역할 '개1발'(372:121)은 Figma 오타로 보고 '개발'로 쓴다.
 *  - more는 사진에 없는 기능을 본문 아래 구분선 뒤 주석 2열로 덧붙인다(9/28 가이드 점검에서 빠진 내용).
 *  - initialKey로 처음 열 탭을, context로 '지금 내 상태' 카드(학습 경로에서 연 경우)를 받는다. 카드는 context.tab 탭 맨 위에 뜬다.
 */

// 주석(Annot, 345:295) — 점(10×20 에셋) + 소제목 + 설명. small = 03·04 레슨 탭(14px·12px, 간격 9).
// 목업 영역(areaKey)과 이어진 주석은 점 대신 번호를 달고 버튼이 된다. 가리키거나(마우스·키보드 포커스) 누르면 목업의 그 영역이
// 강조된다. 여백은 음수 마진으로 상쇄해 점 주석과 같은 자리에 놓인다.
function Annotation({ h, d, small = false, n, areaKey, link }) {
  const text = (
    <div className="flex min-w-0 flex-1 flex-col gap-px">
      <p className={`font-bold leading-figma text-ink ${small ? 'text-[14px]' : 'text-[14.5px]'}`}>{h}</p>
      <p className={`break-keep leading-[1.58] text-ink-muted ${small ? 'text-[12px]' : 'text-[12.5px]'}`}>{d}</p>
    </div>
  )
  const gap = small ? 'gap-[9px]' : 'gap-[10px]'
  if (!areaKey || !link) {
    return (
      <div className={`flex items-start ${gap}`}>
        <img src="/ui/lp-366-91-guide-dot.svg" alt="" aria-hidden className="h-5 w-[10px] shrink-0" />
        {text}
      </div>
    )
  }
  const on = link.active === areaKey
  return (
    <button type="button" id={`guide-annot-${areaKey}`} aria-pressed={link.pinned === areaKey}
      onMouseEnter={() => link.hover(areaKey)} onMouseLeave={() => link.hover(null)}
      onFocus={() => link.hover(areaKey)} onBlur={() => link.hover(null)} onClick={() => link.pick(areaKey)}
      className={`-mx-2 -my-1.5 flex items-start rounded-10 px-2 py-1.5 text-left transition-colors duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 ${gap} ${on ? 'bg-primary-50' : ''}`}>
      <span aria-hidden className={`mt-px flex size-[18px] shrink-0 items-center justify-center rounded-full text-[10.5px] font-bold leading-none transition-colors duration-200 ${
        on ? 'bg-primary-500 text-white' : 'bg-primary-100 text-primary-600'}`}>{n}</span>
      {text}
    </button>
  )
}

// 그룹 → 탭. kind: overview | screens | tips | notes | team. annots = [소제목, 설명, 목업 영역 키] (Figma 원문을 9/28 실제 동작에 맞춰 고침).
// shots = [{ mock: 목업 키(guide/GuideMockups MOCKS), w, h }], demo = 시연 키(DEMOS).
// steps = { label, items: [[제목, 설명, 숙달 기준]] }. 숙달 기준 숫자는 backend main.py _STAGE_RULES·speak_curriculum.py SPEAK_STAGES와 같게.
function CloseButton({ onClose }) {
  return <ModalClose onClose={onClose} />
}

// 주석 2열(overview 아래 주석과 같은 간격 28). 사진 없는 탭과 more가 같이 쓴다. link가 있으면 목업 영역과 잇는다.
function AnnotGrid({ items, link }) {
  if (!items?.length) return null
  return (
    <div className="grid gap-x-7 gap-y-[13px] sm:grid-cols-2">
      {items.map(([h, d, areaKey], i) => <Annotation key={h} h={h} d={d} n={i + 1} areaKey={areaKey} link={link} />)}
    </div>
  )
}

// 사진에 없는 기능(more). 본문 아래 구분선 뒤에 주석 2열로 붙인다(독화 요령의 행 구분선과 같은 fill 선).
function MoreNotes({ items }) {
  if (!items?.length) return null
  return (
    <div className="mt-[22px] flex flex-col gap-[13px] border-t border-fill pt-[22px]">
      <p className="text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">더 알아두기</p>
      <AnnotGrid items={items} />
    </div>
  )
}

// 01 화면 둘러보기(338:273) — 축소본 아래 주석 2열(간격 28)
function OverviewBody({ tab }) {
  const link = useAnnotLink()
  return (
    <div className="flex flex-col gap-5">
      {tab.shots?.length > 0 && <ShotSet tab={tab} link={link} />}
      <AnnotGrid items={tab.annots} link={link} />
      <MoreNotes items={tab.more} />
    </div>
  )
}

// 02·03·04·06~10(Screen guide) — 축소본(1~2장) + 오른쪽 주석. 축소본 사이 14, 주석까지 24(2장이면 14, 주석 안쪽 8)
// 사진이 없으면 주석만 한 열로 그린다(사진을 다시 찍는 동안 칸이 비어도 깨지지 않게).
function ScreensBody({ tab }) {
  const link = useAnnotLink()
  const shots = tab.shots || []
  const two = shots.length > 1
  return (
    <div className="flex flex-col">
      <div className={`flex flex-col md:flex-row md:items-start ${two ? 'gap-[14px]' : 'gap-6'}`}>
        {shots.length > 0 && <ShotSet tab={tab} link={link} two={two} className="md:shrink-0" />}
        <div className={`flex min-w-0 flex-1 flex-col ${tab.small ? 'gap-[11px] md:pl-2' : 'gap-[13px]'}`}>
          {(tab.annots || []).map(([h, d, areaKey], i) => (
            <Annotation key={h} h={h} d={d} small={tab.small} n={i + 1} areaKey={areaKey} link={link} />
          ))}
        </div>
      </div>
      <MoreNotes items={tab.more} />
    </div>
  )
}

// 단계 목록(처음 시작하기·말하기 6단계). 번호는 독화 요령의 번호색(primary-faint)을 작게, 오른쪽 칩은 숙달 기준.
function StepList({ steps }) {
  return (
    <div className="flex flex-col">
      <p className="pb-2 text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">{steps.label}</p>
      {steps.items.map(([h, d, rule], i) => (
        <div key={h} className={`flex items-start gap-4 py-[14px] ${i > 0 ? 'border-t border-fill' : ''}`}>
          <p className="w-7 shrink-0 text-[22px] font-bold leading-figma tracking-[-0.66px] text-primary-faint">{String(i + 1).padStart(2, '0')}</p>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[15px] font-bold leading-figma text-ink">{h}</p>
              {rule && <span className={`${CHIP} shrink-0 whitespace-nowrap bg-primary-100 text-primary-700`}>{rule}</span>}
            </div>
            <p className="break-keep text-[12.5px] leading-[1.58] text-ink-muted">{d}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// 사진 없는 탭(notes): 안내 한 줄 + 주석 2열 + 단계 목록 + 더 알아두기
function NotesBody({ tab }) {
  return (
    <div className="flex flex-col gap-5">
      {tab.intro && <p className="break-keep text-[14px] leading-[1.6] text-ink-muted">{tab.intro}</p>}
      <AnnotGrid items={tab.annots} />
      {tab.steps && <StepList steps={tab.steps} />}
      <MoreNotes items={tab.more} />
    </div>
  )
}

// '지금 내 상태' 숙달 기준 문장. 숫자는 학습 경로가 받은 단계 목록(서버 _STAGE_RULES·SPEAK_STAGES)에서 온다.
function ruleText(c) {
  if (!c.minAttempts || c.mastery == null) return null
  const verb = c.track === 'speak' ? '말하고' : c.pass != null ? '답하고' : '풀고'
  const rate = c.pass != null ? `${c.pass}점 이상을 통과로 세어 최근 통과율이` : c.track === 'speak' ? '최근 통과율이' : '최근 정답률이'
  const head = `${c.minAttempts}번 이상 ${verb} ${rate} ${c.mastery}%`
  // 말하기 모음·자음은 낱말 속 소리 확인(probe), 4·5단계는 개인 향상 경로(gain)가 더 있다(speak_curriculum)
  if (c.probe) return `${head}에 닿은 뒤, 그 소리가 든 낱말을 최근 ${c.probe.n}번 중 ${c.probe.need}번 합격하면 숙달이에요.`
  const base = `${head} 이상이면 숙달이에요.`
  if (c.gain) return `${base} ${c.gain.min_attempts}번 이상 말하고 최근 ${c.gain.recent}번 점수가 처음 ${c.gain.first}번보다 ${c.gain.delta}점 이상 올라도 숙달이에요.`
  return base
}

function nextText(n) {
  if (!n) return '마지막 단계예요.'
  const note = n.open ? '열려 있어요.' : n.skip ? '이 단계를 숙달하면 열려요. 학습 화면에서 건너뛸 수도 있어요.' : '앞 단계를 숙달하면 열려요.'
  return `${n.no}단계 ${n.title}. ${note}`
}

// '지금 내 상태' 카드(9/28, Figma 프레임 없음). 학습 경로의 가이드 버튼으로 열면 보고 있는 단계를 레슨 탭 맨 위에 보여 준다.
// 색은 트랙 토큰이라 말하기 학습에서는 분홍이 된다(AppShell data-track 안에서 열린다).
function StatusCard({ c }) {
  const rule = ruleText(c)
  const line = 'break-keep text-[12.5px] leading-[1.58] text-ink-muted'
  return (
    <section aria-label="지금 내 상태" className="mb-[22px] flex flex-col gap-3 rounded-18 border border-line bg-surface-muted p-5">
      <div className="flex items-center justify-between gap-3 font-bold leading-figma">
        <span className="text-[11.5px] tracking-[0.345px] text-ink-hint">지금 내 상태</span>
        <span className="shrink-0 rounded-full bg-track-tint px-2.5 py-1 text-[12px] text-track">{c.statusLabel}</span>
      </div>
      <div className="flex flex-col gap-1 leading-figma">
        <p className="text-[12.5px] font-bold text-track">{c.trackLabel} · {c.no}단계</p>
        <p className="text-[19px] font-bold tracking-[-0.38px] text-ink">{c.title}</p>
        {c.desc && <p className={line}>{c.desc}</p>}
      </div>
      {c.open && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[13px] font-bold leading-figma">
            <span className="text-ink-muted">진행률</span>
            <span className="text-track">{c.progLabel}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-fill">
            <div className="h-full rounded-full bg-track" style={{ width: `${c.progPct}%` }} />
          </div>
        </div>
      )}
      {/* 앱 핵심 용어 '숙달'은 바꾸지 않고 처음 보이는 곳에 짧은 풀이를 붙인다(docs/easy-korean-rebase-2026-10.md 7절) */}
      {rule && <p className={line}><b className="text-ink">숙달</b> 다음 단계가 열릴 만큼 충분히 익혔다는 뜻이에요.</p>}
      {rule && <p className={line}><b className="text-ink">숙달 기준</b> {rule}</p>}
      {c.guide && <p className={line}><b className="text-ink">이렇게 해 보세요</b> {c.guide}</p>}
      <p className={`${line} border-t border-fill pt-3`}><b className="text-ink">다음 단계</b> {nextText(c.next)}</p>
    </section>
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
  ['06', '모르면 되물어요', '전부 읽을 필요는 없어요. 핵심만 되물어 확인해요. 대화 연습의 되묻기 버튼으로 연습해 봐요.', (
    <div className="flex items-center gap-1.5">
      {['다시', '천천히', '다른 말로'].map((t) => (
        <span key={t} className="rounded-[10px] border border-line bg-white px-2.5 py-1 text-[12.5px] font-bold leading-figma text-ink">{t}</span>
      ))}
    </div>
  )],
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
// 누르면 그 줄 아래에 상세가 펼쳐진다(9/28, 가이드 자체가 모달이라 모달을 겹치지 않는다).
function Member({ m, open, onToggle, index }) {
  return (
    <button type="button" onClick={onToggle} aria-expanded={open}
      className={`flex items-center gap-4 rounded-14 p-1 text-left transition hover:bg-primary-50 md:w-[361px] md:shrink-0 ${open ? 'bg-primary-50' : ''}`}>
      <TeamAvatar m={m} index={index} />
      <div className="flex min-w-0 flex-col gap-1 whitespace-nowrap leading-figma">
        <p className="text-[17px] font-bold text-ink">{m.name}</p>
        <p className="text-[13.5px] text-ink-muted">{m.role}</p>
        {m.handle
          ? <p className="text-[12.5px] font-bold text-primary-500">{m.handle}</p>
          : null}
      </div>
    </button>
  )
}

function TeamBody() {
  const [open, setOpen] = useState(null)
  const rows = [TEAM.slice(0, 2), TEAM.slice(2, 4), TEAM.slice(4)]
  return (
    <div className="flex flex-col">
      <p className="pb-2 text-[15px] leading-[1.6] text-ink-muted">LIPLAB을 함께 만든 사람들이에요. 이름을 누르면 자세히 볼 수 있어요.</p>
      <ContactLine className="pb-[22px]" />
      {rows.map((row, i) => {
        const shown = row.find((m) => m.name === open)
        return (
          <div key={row[0].name} className={`flex flex-col gap-4 ${i === 0 ? 'pb-5 pt-1' : 'border-t border-fill py-5'}`}>
            <div className="flex flex-col gap-5 md:flex-row md:gap-11">
              {row.map((m) => <Member key={m.name} m={m} index={TEAM.indexOf(m)} open={open === m.name} onToggle={() => setOpen(open === m.name ? null : m.name)} />)}
            </div>
            {shown && <div className="rounded-14 bg-primary-50 px-4 py-4"><TeamMemberDetail m={shown} /></div>}
          </div>
        )
      })}
      <p className="flex items-center gap-[10px] whitespace-nowrap border-t border-fill pt-5 font-bold leading-figma">
        <span className="text-[13px] text-ink-faint">소스 코드</span>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-[14px] text-primary-500 hover:underline">
          {REPO_URL.replace('https://', '')}
        </a>
      </p>
    </div>
  )
}

const BODY = { overview: OverviewBody, screens: ScreensBody, tips: TipsBody, notes: NotesBody, team: TeamBody }

// initialKey: 처음 열 탭(없거나 모르는 키면 첫 탭). context: '지금 내 상태' 카드 내용({ tab, … }, CurriculumPath가 만든다).
export default function GuideModal({ open, onClose, initialKey, context }) {
  const startKey = TABS.some((t) => t.key === initialKey) ? initialKey : TABS[0].key
  const [activeKey, setActiveKey] = useState(startKey)
  // 포커스 가두기·ESC 닫기·닫으면 연 버튼으로 포커스 복원(hooks/useFocusTrap)
  const dialogRef = useFocusTrap(open, onClose)
  const stripRef = useRef(null)   // 모바일 가로 탭 줄. 처음 연 탭이 화면 밖이면 보이게 민다
  const contentRef = useRef(null)  // 오른쪽 내용. 탭을 바꾸면 맨 위부터 보이게 한다(긴 탭을 내려 본 뒤 다른 탭이 중간부터 보이던 것)

  // 열릴 때 처음 열 탭(initialKey, 없으면 첫 탭)으로 리셋 + 배경 스크롤 잠금. onClose에 기대지 않아, 부모가 다시 그려져도
  // 보던 탭이 처음 탭으로 돌아가지 않는다(startKey는 문자열이라 렌더마다 바뀌지 않는다).
  useEffect(() => {
    if (!open) return undefined
    setActiveKey(startKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open, startKey])

  // 모바일 가로 탭 줄에서 고른 탭이 화면 밖에 있으면 가운데로 민다(처음 연 탭이 오른쪽 끝일 때). 데스크톱에서는 줄이 숨어 있다.
  useEffect(() => {
    if (!open) return
    stripRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest', inline: 'center' })
    if (contentRef.current) contentRef.current.scrollTop = 0
  }, [open, activeKey])

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
          <div ref={stripRef} className="flex gap-2 overflow-x-auto px-4 pb-3 pt-3">
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
        <div ref={contentRef} className="flex min-w-0 flex-1 flex-col overflow-y-auto px-6 py-6 md:py-[30px] md:pl-9 md:pr-[30px]">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-[22px] font-bold leading-figma tracking-[-0.65px] text-ink md:text-[26px]">{active.title}</h2>
            {/* 데스크톱 닫기(모바일은 상단 탭 헤더에 있음) */}
            <span className="hidden md:flex"><CloseButton onClose={onClose} /></span>
          </div>

          <div className="mt-[22px]">
            {context && context.tab === active.key && <StatusCard c={context} />}
            {/* 탭마다 새로 마운트해 강조·시연 상태를 탭 사이에 넘기지 않는다 */}
            <Body key={active.key} tab={active} />
          </div>
        </div>
      </div>
    </div>
  )
}
