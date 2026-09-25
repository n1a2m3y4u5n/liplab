import { useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import Logo from '../components/Logo'

/**
 * 랜딩 (Figma "02. Landing" 9:12 Landing, Desktop 1440). 로그인하지 않은 사람이 "/"에 오면 보인다(App.jsx AuthGate).
 * 시작하기 → /signup(회원가입), 계정이 이미 있습니다 → /login. 데모 '둘러보기'는 로그인 화면에 그대로 있다.
 *
 * Figma에는 데스크톱 프레임만 있다. xl(1280) 이상은 Figma 좌표를 그대로 쓰고, 그보다 좁으면 같은 요소를
 * 세로로 쌓고 그림은 zoom으로 줄인다(그림 안 좌표는 Figma 값 그대로).
 * 히어로 제목 글꼴은 Figma가 Josefin Sans(한글은 대체 글꼴)라 Noto Sans KR로 쓴다. 64px에서 줄 폭이 거의 같다.
 * 한글 문단은 Figma처럼 어절 단위로 줄을 바꾼다(break-keep).
 * 히어로 버튼(46:2)은 Figma에서 내용 상자 밖에 겹쳐 있어, xl에서는 글을 섹션 위에서 185px(내용 상자 145 + 안쪽 여백 40)에
 * 두고 버튼을 글 아래 19px에 둔다.
 */

const OVERFLOW = { top: '-7%', left: '-12%', width: '124%', height: '124%' }   // 마스코트 SVG 그림자 여백(Figma inset)
const CARD_OVERFLOW = { top: '-4.14%', left: '-11.3%', width: '122.6%', height: '117.93%' }   // 그림 카드 SVG(54:11·54:38)

// 회전한 요소: 바깥 상자 = 회전 뒤 경계(Figma 좌표), 안쪽 = 원래 크기. Figma가 내보낸 배치를 그대로 옮긴다.
function Rotated({ left, top, box, rotate, children }) {
  return (
    <div className="absolute flex items-center justify-center" style={{ left, top, width: box[0], height: box[1] }}>
      <div className="flex-none" style={{ transform: `rotate(${rotate}deg)` }}>{children}</div>
    </div>
  )
}

function Mascot({ src, size }) {
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <img src={src} alt="" className="absolute block max-w-none" style={OVERFLOW} />
    </div>
  )
}

function CardImage({ src }) {
  return (
    <div className="relative h-[290px] w-[230px]">
      <img src={src} alt="" className="absolute block max-w-none" style={CARD_OVERFLOW} />
    </div>
  )
}

// 히어로 마스코트 무리(17:2, 590×620) — [파일, 크기, 회전, 바깥 상자, left, top]
const CLUSTER = [
  ['/ui/lp-19-42-mascot-sky.svg', 125, -8, 141.18, 300, 95],
  ['/ui/lp-19-56-mascot-purple.svg', 96, -18, 120.967, 440, 20],
  ['/ui/lp-19-70-mascot-amber.svg', 70, -26, 93.602, 495, 215],
  ['/ui/lp-19-63-mascot-rose.svg', 76, 14, 92.129, 18, 250],
  ['/ui/lp-19-49-mascot-cyan.svg', 88, 22, 114.558, 85, 75],
  ['/ui/lp-19-77-mascot-emerald.svg', 64, 9, 73.224, 195, 8],
]

function HeroArt() {
  return (
    <div aria-hidden className="relative h-[636px] w-[594px]">
      <div className="absolute left-[2px] top-[8px] h-[620px] w-[590px]">
        {/* Device / iPad (19:37) */}
        <Rotated left={118} top={185} box={[381.506, 410.788]} rotate={-30}>
          <div className="relative h-[330px] w-[250px] overflow-hidden rounded-[26px] border-[3px] border-landing-device bg-white shadow-device">
            <div className="absolute left-[9px] top-[9px] h-[306px] w-[226px] rounded-18 bg-[linear-gradient(134.56deg,theme(colors.primary.300)_0%,theme(colors.primary.500)_71.429%)]" />
            <div className="absolute left-[31px] top-[49px] h-[14px] w-[140px] rounded-[7px] bg-white/85" />
            <div className="absolute left-[31px] top-[75px] h-[14px] w-[110px] rounded-[7px] bg-white/50" />
            <div className="absolute left-[31px] top-[101px] h-[14px] w-[90px] rounded-[7px] bg-white/50" />
          </div>
        </Rotated>
        {CLUSTER.map(([src, size, rotate, box, left, top]) => (
          <Rotated key={src} left={left} top={top} box={[box, box]} rotate={rotate}>
            <Mascot src={src} size={size} />
          </Rotated>
        ))}
      </div>
    </div>
  )
}

// 섹션 그림(460×380). 카드는 모두 (120, 60)에서 회전하고 마스코트는 (250, 40)에 있다.
const STEPS = [[26, 210, 46, 'bg-primary-200'], [72, 178, 78, 'bg-landing-step2'], [118, 144, 112, 'bg-landing-step3'], [164, 106, 150, 'bg-landing-step4']]
const DAYS = ['11100', '11110', '11111', '11011']   // 54:18~54:37, 1 = 한 날(Day done)

function StepsCard() {
  return (
    <div className="relative h-[290px] w-[230px] overflow-hidden rounded-24 bg-primary-100 shadow-art">
      {STEPS.map(([left, top, height, color]) => (
        <div key={left} className={`absolute w-[34px] rounded-10 ${color}`} style={{ left, top, height }} />
      ))}
    </div>
  )
}

function DaysCard() {
  return (
    <div className="relative h-[290px] w-[230px] overflow-hidden rounded-24 bg-pastel-amber shadow-art">
      {DAYS.map((row, r) => [...row].map((d, c) => (
        <div key={`${r}-${c}`} className={`absolute size-[28px] rounded-[9px] ${d === '1' ? 'bg-landing-done' : 'bg-landing-day'}`}
          style={{ left: 21 + c * 40, top: 71 + r * 40 }} />
      )))}
    </div>
  )
}

const SECTIONS = [
  {
    id: '48:13', title: ['입모양부터', '차근차근'], artLeft: false,
    body: '자음·모음 입모양을 먼저 익히고, 단어와 문장, 상황별 대화로 넓혀가요. 순서대로 열리는 커리큘럼이라 어디서부터 시작할지 고민할 필요가 없어요.',
    card: { box: [285.268, 331.482], rotate: 12, el: <StepsCard /> },
    mascot: { src: '/ui/lp-48-6-mascot.svg', size: 150, box: 164.858, rotate: -6 },
  },
  {
    id: '48:26', title: ['소리 내어', '말해보세요'], artLeft: true,
    body: '아바타의 입모양을 보고 따라 말하면 발음 정확도를 바로 확인할 수 있어요. 어떤 소리가 잘 안 나오는지 항목별로 알려드려요.',
    card: { box: [293.325, 337.028], rotate: -14, el: <CardImage src="/ui/lp-54-11-card-voice.svg" /> },
    mascot: { src: '/ui/lp-48-19-mascot.svg', size: 130, box: 144.874, rotate: 7 },
  },
  {
    id: '48:39', title: ['매일 조금씩,', '습관이 돼요'], artLeft: false,
    body: '오늘의 과제와 연속 학습 기록으로 하루 5분을 이어가요. 틀린 항목은 잊어버릴 때쯤 다시 나와서, 외우려 애쓰지 않아도 남아요.',
    card: { box: [301.025, 342.162], rotate: 16, el: <DaysCard /> },
    mascot: { src: '/ui/lp-48-32-mascot.svg', size: 140, box: 158.122, rotate: -8 },
  },
  {
    id: '48:52', title: ['늘고 있다는 걸', '눈으로 확인해요'], artLeft: true,
    body: '어떤 입모양을 얼마나 맞혔는지, 지난주보다 얼마나 나아졌는지 기록으로 남아요. 막연한 느낌 대신 숫자로 보이니까 계속할 힘이 생겨요.',
    card: { box: [285.268, 331.482], rotate: -12, el: <CardImage src="/ui/lp-54-38-card-growth.svg" /> },
    mascot: { src: '/ui/lp-48-45-mascot.svg', size: 135, box: 148.372, rotate: 6 },
  },
]

function FeatureSection({ s }) {
  return (
    <section className="overflow-hidden bg-white">
      <div className={`mx-auto flex max-w-[1440px] items-center gap-8 px-4 py-16 sm:px-8 lg:flex-row lg:gap-12 lg:px-16 lg:py-20 xl:gap-20 xl:px-[120px] xl:py-24 ${s.artLeft ? 'flex-col-reverse' : 'flex-col'}`}>
        {s.artLeft && <SectionArt s={s} />}
        <div className="flex w-full min-w-0 flex-col gap-5 lg:flex-1">
          <h2 className="text-[30px] font-bold leading-[1.35] tracking-[-0.025em] text-primary-500 sm:text-[36px] xl:text-[44px]">
            {s.title[0]}<br />{s.title[1]}
          </h2>
          <p className="break-keep text-[16px] leading-[1.8] text-ink-muted xl:text-[18px]">{s.body}</p>
        </div>
        {!s.artLeft && <SectionArt s={s} />}
      </div>
    </section>
  )
}

function SectionArt({ s }) {
  const m = s.mascot
  return (
    <div aria-hidden className="shrink-0 [zoom:0.7] sm:[zoom:0.85] xl:[zoom:1]">
      <div className="relative h-[380px] w-[460px]">
        <Rotated left={120} top={60} box={s.card.box} rotate={s.card.rotate}>{s.card.el}</Rotated>
        <Rotated left={250} top={40} box={[m.box, m.box]} rotate={m.rotate}><Mascot src={m.src} size={m.size} /></Rotated>
      </div>
    </div>
  )
}

// 시작하기 섹션의 장식 마스코트(48:65·48:72 왼쪽, 48:79·48:86 오른쪽) — 1440 기준 좌표, 오른쪽 것은 오른쪽 끝에서 잰다.
const DECO = [
  { src: '/ui/lp-48-65-deco-mascot.svg', size: 96, box: 120.967, rotate: 18, left: 60, top: 80 },
  { src: '/ui/lp-48-72-deco-mascot.svg', size: 72, box: 93.729, rotate: -22, left: 175, top: 330 },
  { src: '/ui/lp-48-79-deco-mascot.svg', size: 88, box: 108.847, rotate: -16, right: 101.153, top: 60 },
  { src: '/ui/lp-48-86-deco-mascot.svg', size: 104, box: 126.071, rotate: 14, right: 23.929, top: 320 },
]

export default function Landing() {
  const navigate = useNavigate()
  const buttons = (width) => (
    <>
      <Button size="lg" className={width} onClick={() => navigate('/signup')}>시작하기</Button>
      <Button variant="secondary" size="lg" accent className={width} onClick={() => navigate('/login')}>계정이 이미 있습니다</Button>
    </>
  )

  return (
    <div className="flex min-h-[100dvh] flex-col bg-page">
      {/* Hero, above the fold (14:2) */}
      <div className="overflow-hidden bg-page">
        <div className="relative mx-auto max-w-[1440px] px-4 pb-16 sm:px-8 lg:px-16 xl:min-h-[1024px] xl:pb-0 xl:pl-[128px] xl:pr-[160px]">
          <header className="flex pt-[17px] [zoom:0.67] sm:[zoom:1] xl:ml-[92px]">
            <Logo size={48} />
          </header>
          <section className="mt-8 flex flex-col items-center gap-10 lg:flex-row lg:gap-12 xl:mt-[22px] xl:items-start xl:gap-16">
            <div className="flex w-full min-w-0 flex-col gap-8 lg:flex-1 lg:py-10 xl:gap-[19px] xl:pb-0 xl:pt-[185px]">
              {/* Text(14:5) — Figma에서도 512px 상자가 내용 칸(494)보다 조금 넓다 */}
              <div className="flex flex-col gap-6 xl:w-[512px]">
                <h1 className="text-[34px] font-bold leading-none tracking-[-0.1em] text-black sm:text-[48px] xl:text-[64px]">
                  독화를 가장 편리하게<br />배우는 방법
                </h1>
                <p className="break-keep text-[16px] font-medium leading-[1.6] tracking-[-0.01em] text-black/55 sm:text-[20px]">
                  입모양을 읽는 독화부터 소리 내어 말하는 발화까지
                </p>
              </div>
              <div className="flex w-full max-w-[470px] flex-col gap-[14px]">{buttons('w-full')}</div>
            </div>
            <div className="shrink-0 [zoom:0.55] sm:[zoom:0.8] lg:[zoom:0.66] xl:[zoom:1]">
              <HeroArt />
            </div>
          </section>
        </div>
      </div>

      {SECTIONS.map((s) => <FeatureSection key={s.id} s={s} />)}

      {/* 시작하기 (48:56) */}
      <section className="overflow-hidden bg-primary-100">
        <div className="relative mx-auto max-w-[1440px] xl:h-[540px]">
          <div className="relative z-10 flex flex-col items-center gap-7 px-4 py-20 text-center sm:px-8 xl:py-0 xl:pt-[130px]">
            <h2 className="text-[34px] font-bold leading-[1.4] tracking-[-0.025em] text-primary-500 sm:text-[40px] xl:text-[48px]">
              언제 어디서나<br />입모양 연습을
            </h2>
            <p className="break-keep text-[16px] leading-figma text-ink-muted sm:text-[18px]">설치 없이 브라우저에서 바로. 지금 바로 첫 레슨을 열어보세요.</p>
            <div className="flex w-full flex-col items-center gap-4 sm:w-auto sm:flex-row">{buttons('w-full max-w-[340px] sm:w-[340px]')}</div>
          </div>
          {DECO.map((d) => (
            <div key={d.src} aria-hidden className="hidden lg:block">
              <div className="absolute" style={{ left: d.left, right: d.right, top: d.top, width: d.box, height: d.box }}>
                <Rotated left={0} top={0} box={[d.box, d.box]} rotate={d.rotate}><Mascot src={d.src} size={d.size} /></Rotated>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer (9:56) */}
      <footer className="bg-white">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-4 py-6 sm:px-8 lg:px-16 lg:py-9">
          <Logo size={22} />
          <p className="text-[14px] leading-figma text-ink-muted">© 2026 LIPLAB</p>
        </div>
      </footer>
    </div>
  )
}
