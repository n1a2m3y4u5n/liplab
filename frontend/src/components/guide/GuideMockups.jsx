import { ReadMock, SpeakMock } from './LessonMocks'
import { USER, area, KEYFRAMES, MaskIcon, Node, Connector, TailLeft, StageArrow, MobileShell, SIDE, RailTask } from './MockPrimitives'
import { Fragment, useCallback, useLayoutEffect, useRef, useState } from 'react'
import Logo from '../Logo'
import { WatermarkDeco } from '../WatermarkCard'

/**
 * 사용법 가이드 화면 목업(9/28). 스크린샷 대신 실제 앱 화면을 단순화해 코드로 그린다.
 * 색·반경·글자 크기는 앱과 같은 토큰을 쓰고, 값은 정적 예시(이름 '게스트', 단어 '바다' 등)다.
 * 각 목업은 고정 설계 크기(design)로 그린 뒤 transform scale로 가이드의 사진 상자(w×h)에 맞춰 줄인다.
 * 앱 컴포넌트의 lg: 반응형 클래스는 뷰포트 기준이라 가이드 안에서는 크기가 어긋나므로, 모바일 화면은 모바일 값을 직접 쓴다.
 * 3D 아바타 칸은 WebGL을 띄우지 않고 어두운 무대 위 얼굴 일러스트(FaceStage)로 그린다.
 *
 * 동적 요소
 *  - 영역: 목업 안 요소에 data-area를 달고, 가이드 주석(GROUPS annots의 셋째 값)과 같은 키로 잇는다.
 *    강조 중인 영역은 링을 두르고 나머지는 흰 막으로 살짝 흐린다. 번호 배지는 목업이 가진 영역(MOCKS areas)에만 단다.
 *  - 시연: scene(장면)과 tick(틱 수)을 받아 그린다. 장면 순서는 DEMOS, 재생은 GuideDemo의 useDemo가 맡는다.
 * 안쪽은 장식(aria-hidden, 포인터 막음)이고 스크린리더에는 sr-only 설명을 읽힌다. 안쪽에는 버튼 대신 span·div만 쓴다.
 */

// 예시 값. 레벨 4 = XP 900~1,600 구간(lib/level.js), 1,240이면 340 / 700.
function OverviewMock() {
  return <div className="flex h-full bg-page text-ink"><div className="flex w-[256px] shrink-0 flex-col gap-2 border-r border-line bg-white p-6"><span {...area('logo')}><Logo size={30} /></span>{SIDE.map((n) => <span key={n.key} className={`side-item ${n.key === 'today' ? 'side-item-active' : ''}`}><MaskIcon src={n.icon} className="size-6" />{n.label}</span>)}<div {...area('stats')} className="mt-auto flex gap-3 font-bold"><span>🔥 {USER.streak}</span><span>★ {USER.xp}</span><span>Lv.{USER.level}</span></div></div><div className="mx-auto flex w-[816px] flex-col gap-5 p-8"><h2 className="text-[30px] font-bold">오늘</h2><div className="card-flat"><p className="mb-3">입모양 읽기 · 3단계 문장</p><span className="btn-primary btn-lg flex justify-center">이어서 학습하기</span></div><div {...area('rail')} className="card-flat"><h3 className="mb-4 text-xl font-bold">오늘 복습 5개</h3><span className="btn-secondary btn-md">복습 시작하기</span></div><div className="card-flat"><h3 className="mb-4 text-xl font-bold">오늘의 과제</h3><RailTask label="입모양 읽기 1회" cur={1} total={1} /><RailTask label="학습 2회 채우기" cur={1} total={2} /></div></div></div>
}

// ── 02 학습 탭(모바일 학습 경로) ─────────────────────────────────────────────
function LearnMock({ motion }) {
  const path = ['mastered', 'current', 'skip', 'locked']
  const cur = 1
  const sheet = (
    <div {...area('sheet')} className="absolute inset-x-0 bottom-[78px] z-20 flex flex-col gap-[11px] rounded-t-22 border-t-2 border-line bg-white px-[18px] pb-5 pt-[18px] shadow-sheet">
      <div className="flex items-center justify-between gap-3 font-bold leading-figma">
        <p className="min-w-0 truncate text-[17px] text-ink">음절·단어</p>
        <span className="shrink-0 text-[13px] text-track">4 / 6</span>
      </div>
      <div className="h-[9px] overflow-hidden rounded-full bg-fill">
        <div className="h-full w-[66%] rounded-full bg-track" />
      </div>
      <span className="btn-primary w-full py-4 text-center text-[16px]">이어서 학습하기</span>
    </div>
  )
  return (
    <MobileShell active="learn" overlay={sheet}>
      <div {...area('switch')} className="flex w-full gap-1 rounded-13 bg-surface-sunken p-1">
        <span className="flex-1 rounded-10 bg-white py-[9px] text-center text-[14px] font-bold leading-figma text-track shadow-[0px_2px_5px_0px_rgba(26,13,64,0.1)]">독화</span>
        <span className="flex-1 rounded-10 py-[9px] text-center text-[14px] font-bold leading-figma text-ink-faint">발화</span>
      </div>
      <div className="flex w-full items-center gap-3.5 rounded-16 border-track-dark bg-track py-[15px] pl-[17px] pr-[13px] text-white">
        <div className="flex min-w-0 flex-1 flex-col gap-[3px] font-bold leading-figma">
          <span className="text-[11px] opacity-[0.85]">독화 · 2단계</span>
          <span className="text-[18px] tracking-[-0.36px]">음절·단어</span>
        </div>
        <span {...area('guideBtn')} className="shrink-0 rounded-10 border-1.5 border-white/35 bg-white/[0.18] px-3 py-[7px] text-[12px] font-bold leading-figma">가이드</span>
      </div>
      <div className="relative w-full py-2">
        <StageArrow src="/ui/lp-232-35-stage-arrow-prev.svg" className="left-0.5 size-[38px]" style={{ top: 8 + cur * 74 + 9 }} />
        <StageArrow src="/ui/lp-232-35-stage-arrow-next.svg" className="right-0.5 size-[38px]" style={{ top: 8 + cur * 74 + 9 }} />
        <div {...area('nodes')} className="mx-auto flex w-[56px] flex-col items-center">
          {path.map((st, i) => (
            <Fragment key={i}>
              {i > 0 && <Connector done={path[i - 1] === 'mastered'} />}
              <div className="relative">
                <Node status={st} glow={motion} />
                {st === 'skip' && (
                  <span className="absolute left-full top-1/2 z-10 ml-4 -translate-y-1/2 whitespace-nowrap rounded-13 border border-line bg-white px-2.5 py-2 text-[12px] font-bold leading-figma text-track-dark shadow-[0px_6px_16px_-2px_rgba(26,13,64,0.1)]">
                    여기로 건너뛸까요?
                    <TailLeft className="left-[-15px] top-1/2 -translate-y-1/2" />
                  </span>
                )}
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </MobileShell>
  )
}

// ── 03·04 레슨 화면(모바일) ─────────────────────────────────────────────────
const PRACTICE = [
  ['free', '내 문장 입모양 보기', '내가 쓴 문장을 소리 내어 확인해요', '/ui/card-free.svg', 'bg-pastel-pink'],
  ['scenario', '상황별 시나리오', '카페·병원 등 상황을 골라 연습해요', '/ui/card-scenario.svg', 'bg-pastel-amber'],
  ['sign', '수어 보기', '문장을 수어로도 확인할 수 있어요', '/ui/card-sign.svg', 'bg-pastel-mint'],
  ['endless', '엔드리스 학습', '틀렸던 유형이 계속 나와요', '/ui/tab-card-endless.svg', 'bg-pastel-indigo'],
  ['mouth', '입모양 교실', '웹캠으로 따라 하고 안 보이는 혀 위치도 확인해요', '/ui/nav-learn.svg', 'bg-pastel-violet'],
]

function PracticeMock() {
 return <MobileShell active="learn" title="학습"><div {...area('scenario')} className="rounded-13 bg-surface-sunken p-3 text-center font-bold">입모양 읽기　말하기　소리 듣기</div><div className="flex justify-around py-3 font-bold"><span>단계</span><span className="text-track">자유 연습</span><span>자료</span></div><div className="card-flat font-bold">상황별 연습</div><div {...area('endless')} className="card-flat font-bold">틀린 유형 계속 풀기</div><div className="card-flat font-bold">뜻 없는 말 짝 맞추기</div><div {...area('mouth')} className="card-flat"><b>자료</b><p>입모양 교실 · 수어 보기</p></div><span {...area('free')} /><span {...area('sign')} /></MobileShell>
}

// ── 07 과제(데스크톱 본문 열) ────────────────────────────────────────────────
function TaskRow({ label, cur, total, xp }) {
  const done = cur >= total
  return (
    <div className="flex items-center gap-3.5">
      {done
        ? <img src="/ui/task-done.svg" alt="" className="size-[26px] shrink-0" />
        : <span className="size-[26px] shrink-0 rounded-full border border-line" />}
      <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
        <div className="flex items-center justify-between font-bold leading-figma">
          <span className="text-[15px] text-ink">{label}</span>
          <span className="text-[13px] text-primary-500">{cur} / {total}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-primary-500" style={{ width: `${(cur / total) * 100}%` }} />
        </div>
      </div>
      <span className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold leading-figma ${done ? 'bg-primary-100 text-primary-700' : 'bg-surface-sunken text-ink-faint'}`}>+{xp} 경험치</span>
    </div>
  )
}

const BADGES = [
  ['첫 걸음', '/ui/medal-0.svg', true], ['7일 연속', '/ui/medal-1.svg', true], ['입모양 마스터', '/ui/medal-2.svg', false],
  ['정답률 90%', null, true], ['100문제 돌파', '/ui/medal-3.svg', true], ['복습왕', '/ui/medal-4.svg', false],
]

function TaskMock() {
 return <div className="flex h-full flex-col gap-5 bg-page p-7 text-ink"><h2 className="text-2xl font-bold">오늘</h2><div className="card-flat"><p className="mb-3">입모양 읽기 · 3단계 문장</p><span className="btn-primary btn-lg flex justify-center">이어서 학습하기</span></div><div {...area('today')} className="card-flat"><h3 className="mb-4 font-bold">오늘의 과제</h3><RailTask label="입모양 읽기 1회" cur={1} total={1} /><RailTask label="학습 2회 채우기" cur={1} total={2} /></div><div {...area('special')} className="card-flat font-bold">특별 과제 · 이번 주 5일 학습하기</div></div>
}

// ── 08 복습 ──────────────────────────────────────────────────────────────────
function ReviewCta({ id, title, sub, btn, card, btnCls }) {
  return (
    <div {...area(id)} className={`h-[150px] min-w-0 flex-1 rounded-18 border px-3.5 pt-[27px] ${card}`}>
      <span className="flex flex-col gap-3">
        <span className="flex flex-col gap-3 leading-figma text-white">
          <span className="text-[17px] font-bold tracking-[-0.34px]">{title}</span>
          <span className="text-[12px] opacity-85">{sub}</span>
        </span>
        <span className={`flex w-full items-center justify-center rounded-[11px] bg-white py-2.5 text-[12.5px] font-bold leading-figma ${btnCls}`}>{btn}</span>
      </span>
    </div>
  )
}

const REVIEW_ITEMS = [
  ['독화', '바다', '오늘 · 2회 틀렸어요'],
  ['독화', '커피 주세요', '어제 · 1회 틀렸어요'],
  ['발화', '나비', '3일 전 · 북마크를 했어요'],
]

function ReviewMock() {
 return <MobileShell active="records" title="기록"><div {...area('ctaWrong')} className="flex justify-around rounded-13 bg-surface-sunken p-3 font-bold"><span>요약</span><span className="text-track">틀린 문장</span><span {...area('ctaMark')}>저장한 문장</span></div><div className="py-3 font-bold">전체　입모양 읽기　말하기</div><div {...area('items')} className="card-flat"><div className="mb-4 flex justify-between font-bold"><span>문장 목록</span><span {...area('erase')}>지우기</span></div><p>입모양 읽기 · 바다에 가요</p><p className="mt-2 text-sm text-ink-muted">1회 틀렸어요</p><hr className="my-4" /><p>말하기 · 안녕하세요</p></div></MobileShell>
}

// ── 09 분석(데스크톱 본문 열, 상세 링크까지 보이게) ─────────────────────────────
const STAT_DECO = {
  clock: { src: '/ui/lp-104-15-deco-clock.svg', size: 124, top: -49.47, right: -47.47 },
  percent: { src: '/ui/lp-104-15-deco-percent.svg', size: 124, top: -49.47, right: -47.47 },
  flame: { src: '/ui/lp-104-15-deco-flame.svg', size: 167, top: -77.02, right: -75.03 },
}
const WEEK_MIN = [40, 25, 55, 35, 60, 45, 72]
const WEEK_ACC = [68, 71, 70, 75, 74, 79, 82]

function ChartCard({ id, title, children }) {
  return (
    <section {...area(id)} className="flex w-full flex-col gap-[18px] rounded-18 border border-line bg-white p-[22px]">
      <div className="flex items-center justify-between font-bold leading-figma">
        <p className="text-[17px] text-ink">{title}</p>
        <span className="text-[13px] text-ink-muted">최근 7주</span>
      </div>
      {children}
    </section>
  )
}

function GridLines() {
  return [38, 75, 113].map((t) => <div key={t} className="absolute left-0 right-[-4px] h-px bg-fill" style={{ top: t }} />)
}

function AnalysisMock() {
  const max = Math.max(...WEEK_MIN)
  const lo = 65, hi = 85
  const y = (v) => 123 - ((v - lo) / (hi - lo)) * 93
  const n = WEEK_ACC.length - 1
  const x = (i) => `calc(10px + ${i} * (100% - 16px) / ${n})`
  return (
    <div className="flex h-full flex-col gap-5 overflow-hidden bg-white px-8 pt-6 text-ink">
      <p className="text-[30px] font-bold leading-figma tracking-[-0.75px] text-ink">분석</p>
      <div {...area('stats')} className="flex w-full gap-3.5">
        {[['clock', '총 학습', '3시간 40분', '지난주보다 +25분', 'text-stat-xp'], ['percent', '평균 정답률', '82%', '지난주 +3%p', 'text-stat-accuracy'],
          ['flame', '연속 학습', `${USER.streak}일`, '최고 기록 15일', 'text-stat-streak']].map(([deco, label, value, delta, color]) => (
          <div key={deco} className="relative isolate flex min-w-0 flex-1 flex-col gap-[7px] overflow-hidden rounded-18 border border-line bg-white p-5 leading-figma">
            <WatermarkDeco {...STAT_DECO[deco]} />
            <span className="text-[13px] font-bold text-ink-soft">{label}</span>
            <span className={`whitespace-nowrap text-[27px] font-bold tracking-[-0.675px] ${color}`}>{value}</span>
            <span className="text-[12px] font-bold text-ink-faint">{delta}</span>
          </div>
        ))}
      </div>
      <ChartCard id="bars" title="학습 시간 변화">
        <div className="relative h-[150px] w-full">
          <GridLines />
          <div className="absolute inset-x-0 bottom-[22px] top-0 flex items-end">
            {WEEK_MIN.map((m, i) => (
              <div key={i} className="flex flex-1 justify-center">
                <div className={`w-[46px] rounded-b-[2px] rounded-t-[8px] ${i === n ? 'bg-primary-500' : 'bg-primary-300'}`} style={{ height: (m / max) * 114 }} />
              </div>
            ))}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex h-[18px] items-start">
            {WEEK_MIN.map((m, i) => (
              <span key={i} className={`flex-1 text-center font-bold leading-figma ${i === n ? 'text-[11.5px] text-primary-700' : 'text-[10.5px] text-ink-ghost'}`}>
                {Math.floor(m / 60)}h {m % 60}m
              </span>
            ))}
          </div>
        </div>
      </ChartCard>
      <ChartCard id="line" title="정답률 변화">
        <div className="relative h-[150px] w-full">
          <GridLines />
          <svg viewBox={`0 0 ${n} 150`} preserveAspectRatio="none" className="absolute left-2.5 top-0 h-[150px] w-[calc(100%-16px)] overflow-visible">
            <path d={WEEK_ACC.map((v, i) => `${i ? 'L' : 'M'}${i} ${y(v).toFixed(1)}`).join(' ')} fill="none" className="stroke-chart-accuracy"
              strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          </svg>
          {WEEK_ACC.map((v, i) => (
            <Fragment key={i}>
              <span className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-chart-accuracy ${i === n ? 'size-4' : 'size-[11px]'}`}
                style={{ left: x(i), top: y(v) }} />
              <span className={`absolute -translate-x-1/2 font-bold leading-figma ${i === n ? 'text-[13px] text-stat-accuracy' : 'text-[11.5px] text-chart-label'}`}
                style={{ left: x(i), top: y(v) - (i === n ? 31.2 : 26.67) }}>{v}</span>
            </Fragment>
          ))}
        </div>
      </ChartCard>
      <div className="flex w-full gap-3">
        {[['calendar', '활동 캘린더'], ['history', '학습 내역'], ['fullStats', '전체 통계']].map(([k, label]) => (
          <span key={k} {...area(k)} className="flex flex-1 items-center justify-between rounded-16 border border-line bg-white py-[18px] pl-5 pr-[18px] text-[15px] font-bold leading-figma text-ink">
            {label}
            <span className="relative h-3.5 w-[7px] shrink-0">
              <img src="/ui/menu-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── 10 프로필 ────────────────────────────────────────────────────────────────
function MenuRow({ id, title, sub, danger, first }) {
  return (
    <div {...area(id)} className={`flex items-center justify-between py-[15px] pl-[18px] pr-4 leading-figma ${first ? '' : 'border-t-1.5 border-line'}`}>
      <span className="flex flex-col gap-[3px]">
        <span className={`text-[15px] font-bold ${danger ? 'text-bad-text' : 'text-ink'}`}>{title}</span>
        <span className="text-[12px] text-ink-muted">{sub}</span>
      </span>
      <span className="relative h-3 w-1.5 shrink-0">
        <img src="/ui/lp-240-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2" />
      </span>
    </div>
  )
}

function ProfileMock() {
  // 접근성 설정 Aa 버튼(A11ySettings). 휴대폰에서는 탭 바 위 왼쪽에 떠 있다
  const aa = (
    <span {...area('a11y')} className="absolute bottom-[94px] left-4 z-40 grid size-11 place-items-center rounded-full bg-surface-inverse text-[15px] font-bold tracking-tight text-white shadow-lg">Aa</span>
  )
  return (
    <MobileShell title="프로필" overlay={aa}>
      <section className="flex h-[150px] w-full items-start gap-3.5 overflow-hidden rounded-18 border border-primary-600 bg-[linear-gradient(156.15deg,var(--brand-light)_0%,var(--brand)_70.92%)] pl-[18px] pr-4 pt-[22px]">
        <div className="flex size-16 shrink-0 items-center justify-center rounded-full border-[3px] border-white/90 bg-white/20 text-2xl font-black text-white">{USER.initial}</div>
        <div className="mt-[19px] flex min-w-0 flex-1 flex-col gap-2 font-bold leading-figma text-white">
          <div className="flex items-center gap-2">
            <span className="truncate text-[20px] tracking-[-0.4px]">{USER.name}</span>
            <span className="shrink-0 rounded-full bg-white/[0.24] px-2.5 py-1 text-[11.5px]">Lv.{USER.level}</span>
          </div>
          <div className="flex justify-between text-[11.5px]">
            <span className="opacity-85">다음 레벨까지</span>
            <span>340 / 700 경험치</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/[0.28]">
            <div className="h-full w-[49%] rounded-full bg-white" />
          </div>
        </div>
      </section>
      <section className="w-full overflow-hidden rounded-16 border border-line bg-white">
        <MenuRow first id="placement" title="시작 단계 다시 정하기" sub="지금 수준으로 단계 재추천" />
        <MenuRow id="account" title="계정 설정" sub="이름 · 이메일 · 비밀번호 · 로그아웃" />
        <MenuRow id="reset" danger title="학습 초기화" sub="기록을 모두 지우고 처음부터" />
      </section>
    </MobileShell>
  )
}

// 목업 목록. design = 설계 크기(px, 가이드 사진 상자와 같은 비율). areas = 이 목업에 번호 배지를 다는 영역.
export const MOCKS = {
  overview: { design: [1440, 760], C: OverviewMock, areas: ['stats', 'rail', 'logo'],
    alt: '오늘 화면 그림. 왼쪽 오늘·학습·기록·내 정보 메뉴, 가운데 이어서 학습과 오늘 복습·과제.' },
  learn: { design: [520, 653], C: LearnMock, areas: ['switch', 'guideBtn', 'nodes', 'arrows', 'sheet'],
    alt: '휴대폰 학습 탭 그림. 입모양 읽기·말하기 전환, 단계 이름과 가이드 버튼, DOKA 단계 노드와 아래 레슨 카드.' },
  readQuestion: { design: [375, 564], C: (p) => <ReadMock {...p} />, areas: ['bookmark', 'stage', 'options'],
    alt: '단어 독화 문제 그림. 왼쪽 위에 가상 인물 이름이 붙은 입모양 영상이 있다. 보기를 고르고 확인을 누르면 초록 결과 바에 \'정답이에요\'가 나온다.' },
  readWrong: { design: [375, 564], C: (p) => <ReadMock wrong {...p} />, areas: ['resultBar'],
    alt: '단어 독화에서 틀렸을 때의 그림. 고른 보기는 빨강, 정답 보기는 초록 테두리. 아래 빨간 결과 바에 정답이 나온다.' },
  speakBefore: { design: [375, 564], C: (p) => <SpeakMock {...p} />, areas: ['stage', 'mic'],
    alt: '발화 문제 그림. 말할 단어와 아바타 입모양, 아래 마이크 버튼. 녹음 중에는 파형이 움직인다.' },
  speakResult: { design: [375, 564], C: (p) => <SpeakMock result {...p} />, areas: ['score', 'chips', 'detail'],
    alt: '발화 결과 그림. 발음 점수 84%, 소리별 칩 네 개 중 ㄷ은 주황, 아래 초록 결과 바 잘했어요.' },
  practice: { design: [520, 653], C: PracticeMock, areas: ['free', 'scenario', 'sign', 'endless', 'mouth'],
    alt: '학습의 자유 연습 그림. 내 문장 입모양 보기, 상황별 시나리오, 수어 보기, 엔드리스 학습, 입모양 교실 카드.' },
  task: { design: [700, 606], C: TaskMock, areas: ['today', 'special'],
    alt: '오늘 그림. 오늘의 과제 세 줄, 특별 과제 카드, 배지 목록.' },
  review: { design: [520, 653], C: ReviewMock, areas: ['ctaWrong', 'ctaMark', 'items', 'erase'],
    alt: '오늘 복습 그림. 틀린 문제·북마크 복습 카드와 복습 목록, 지우기 버튼.' },
  analysis: { design: [640, 804], C: AnalysisMock, areas: ['stats', 'bars', 'line', 'calendar', 'history', 'fullStats'],
    alt: '기록 그림. 맨 위에 총 학습, 평균 정답률, 연속 학습 세 칸. 가운데에 학습 시간과 정답률 변화 그래프. 아래에 활동 캘린더, 학습 내역, 전체 통계 링크.' },
  profile: { design: [520, 653], C: ProfileMock, areas: ['placement', 'account', 'reset', 'a11y'],
    alt: '내 정보 그림. 이름과 레벨 카드. 시작 단계 다시 정하기, 계정 설정, 학습 초기화 메뉴. 왼쪽 아래 접근성 설정 Aa 버튼.' },
}

/**
 * 시연 루프. tick(ms)마다 한 칸씩 steps를 돈다([장면, 칸 수]). final = 동작 최소화일 때 보일 정지 장면.
 * areaScene = 그 영역을 강조할 때 붙잡아 둘 장면(결과 바를 가리키면 결과 장면에서 멈춘다).
 */
export const DEMOS = {
  reading: {
    tick: 350, steps: [['play', 6], ['select', 3], ['confirm', 2], ['result', 8]], final: 'result',
    areaScene: { bookmark: 'play', stage: 'play', options: 'select', resultBar: 'result' },
  },
  speaking: {
    tick: 350, steps: [['idle', 5], ['rec', 8], ['result', 9]], final: 'result',
    areaScene: { stage: 'idle', mic: 'rec', score: 'result', chips: 'result', detail: 'result' },
  },
}

const HOLE_PAD = 4
function roundRect(x, y, w, h, r) {
  return `M${x + r} ${y}H${x + w - r}A${r} ${r} 0 0 1 ${x + w} ${y + r}V${y + h - r}A${r} ${r} 0 0 1 ${x + w - r} ${y + h}`
    + `H${x + r}A${r} ${r} 0 0 1 ${x} ${y + h - r}V${y + r}A${r} ${r} 0 0 1 ${x + r} ${y}Z`
}
const sameRects = (a, b) => JSON.stringify(a) === JSON.stringify(b)

/**
 * 가이드 사진 상자. 폭은 w(좁으면 칸 폭), 높이는 w×h 비율을 따른다. 안쪽 목업은 설계 크기로 그리고
 * 상자 폭 / 설계 폭만큼 줄인다(ResizeObserver). 강조·번호 배지는 줄이지 않은 겉 층에 그린다(배지 크기가 일정하게).
 *
 * scene·tick·running: 시연 상태(GuideDemo useDemo). motion: 동작 최소화가 아니면 true(현재 단계 링 깜빡임).
 * active: 강조 중인 영역 키. numbers·labels: 영역 → 주석 번호·제목. onPick·onHover: 배지를 누름·가리킴.
 */
export default function GuideMock({ name, w, h, scene = null, tick = 0, running = false, motion = false, active = null, numbers = {}, labels = {}, onPick, onHover }) {
  const m = MOCKS[name]
  const outerRef = useRef(null)
  const innerRef = useRef(null)
  const [dw, dh] = m ? m.design : [w, h]
  const [scale, setScale] = useState(w / dw)
  const [box, setBox] = useState({ w, h })
  const [rects, setRects] = useState({})

  // 상자 폭이 바뀌면 배율을 다시 잰다
  useLayoutEffect(() => {
    const el = outerRef.current
    if (!el) return undefined
    const fit = () => {
      if (!el.clientWidth) return
      setScale(el.clientWidth / dw)
      setBox({ w: el.clientWidth, h: el.clientHeight })
    }
    fit()
    if (typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [dw])

  // 영역 위치(겉 층 좌표). 배율·장면이 바뀌면 다시 재고, 전환(300ms)이 끝난 뒤 한 번 더 잰다.
  const own = m?.areas
  const measure = useCallback(() => {
    const outer = outerRef.current
    const inner = innerRef.current
    if (!outer || !inner || !own) return
    const base = outer.getBoundingClientRect()
    const next = {}
    inner.querySelectorAll('[data-area]').forEach((el) => {
      const k = el.getAttribute('data-area')
      if (!own.includes(k)) return
      const r = el.getBoundingClientRect()
      if (!r.width || !r.height) return
      ;(next[k] ||= []).push({ x: Math.round(r.left - base.left), y: Math.round(r.top - base.top), w: Math.round(r.width), h: Math.round(r.height) })
    })
    setRects((prev) => (sameRects(prev, next) ? prev : next))
  }, [own])
  useLayoutEffect(() => {
    measure()
    const t = setTimeout(measure, 380)
    return () => clearTimeout(t)
  }, [measure, scale, scene])
  useLayoutEffect(() => {
    document.fonts?.ready?.then(measure).catch(() => {})
  }, [measure])

  if (!m) return null
  const { C } = m
  const hit = active ? rects[active] : null
  const holes = (hit || []).map((r) => roundRect(r.x - HOLE_PAD, r.y - HOLE_PAD, r.w + HOLE_PAD * 2, r.h + HOLE_PAD * 2, 10)).join(' ')
  const clampX = (v) => Math.max(3, Math.min(box.w - 23, v))
  const clampY = (v) => Math.max(3, Math.min(box.h - 23, v))
  const placed = []
  return (
    <div ref={outerRef} className="relative shrink-0 overflow-hidden rounded-14 bg-page" style={{ width: w, maxWidth: '100%', aspectRatio: `${w} / ${h}` }}>
      <style>{KEYFRAMES}</style>
      <span className="sr-only">{m.alt}</span>
      <div ref={innerRef} aria-hidden="true" className="pointer-events-none absolute left-0 top-0 origin-top-left select-none"
        style={{ width: dw, height: dh, transform: `scale(${scale})` }}>
        <C scene={scene} tick={tick} running={running} motion={motion} />
      </div>

      {/* 강조: 영역 밖을 흰 막으로 흐리고 영역에 링을 두른다. 다른 사진의 영역이면 이 사진 전체를 흐린다. */}
      <svg aria-hidden="true" width={box.w} height={box.h}
        className={`pointer-events-none absolute inset-0 transition-opacity duration-300 ease-out ${active ? 'opacity-100' : 'opacity-0'}`}>
        <path fillRule="evenodd" fill="rgba(255,255,255,0.6)" d={`M0 0H${box.w}V${box.h}H0Z ${holes}`} />
      </svg>
      {(hit || []).map((r, i) => (
        <span key={`${active}-${i}`} aria-hidden="true"
          className="pointer-events-none absolute animate-[gm-fade_250ms_ease-out_both] rounded-[10px] border border-primary-500 shadow-[0_0_0_4px_rgba(125,83,222,0.16)]"
          style={{ left: r.x - HOLE_PAD, top: r.y - HOLE_PAD, width: r.w + HOLE_PAD * 2, height: r.h + HOLE_PAD * 2 }} />
      ))}

      {/* 번호 배지: 누르거나 가리키면 옆 주석이 함께 강조된다 */}
      {onPick && own?.map((k) => {
        const r = rects[k]?.[0]
        const n = numbers[k]
        if (!r || !n) return null
        const on = active === k
        // 영역 왼쪽에 자리가 있으면 영역 밖 왼쪽에(글자를 가리지 않게), 없으면 왼쪽 위 모서리에 걸친다.
        // 작게 줄인 사진에서 배지가 겹치면 앞 배지 오른쪽으로 비켜 놓는다.
        const outside = r.x - 26 >= 3
        let left = clampX(outside ? r.x - 26 : r.x - 8)
        const top = clampY(outside ? r.y + Math.min(4, r.h / 2 - 10) : r.y - 8)
        while (placed.some((p) => Math.abs(p[0] - left) < 22 && Math.abs(p[1] - top) < 22)) left = clampX(left + 24)
        placed.push([left, top])
        return (
          <button key={k} type="button" aria-label={`${n}번 ${labels[k] || ''} 위치`} aria-pressed={on}
            onClick={() => onPick(k)} onMouseEnter={() => onHover?.(k)} onMouseLeave={() => onHover?.(null)}
            onFocus={() => onHover?.(k)} onBlur={() => onHover?.(null)}
            className={`absolute flex size-5 items-center justify-center rounded-full text-[11px] font-bold leading-none text-white shadow-[0_2px_6px_rgba(26,13,64,0.28)] ring-2 ring-white transition-[transform,background-color,opacity] duration-200 ease-out focus:outline-none focus-visible:ring-primary-300 ${
              on ? 'scale-110 bg-primary-700' : 'bg-primary-500 hover:bg-primary-600'} ${active && !on ? 'opacity-50' : ''}`}
            style={{ left, top }}>
            {n}
          </button>
        )
      })}

      {/* 테두리는 위에 덮어 그린다(상자 크기를 바꾸지 않게) */}
      <span aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-14 border-1.5 border-line" />
    </div>
  )
}
