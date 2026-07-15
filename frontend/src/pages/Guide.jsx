import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import LearnHeader from '../components/LearnHeader'

// 기둥별 강조색
const ACCENT = {
  sky: { bar: 'border-sky-400', chip: 'bg-sky-50', tip: 'bg-sky-50 text-sky-900', hover: 'hover:border-sky-300', eyebrow: 'text-sky-600' },
  rose: { bar: 'border-rose-400', chip: 'bg-rose-50', tip: 'bg-rose-50 text-rose-900', hover: 'hover:border-rose-300', eyebrow: 'text-rose-600' },
  violet: { bar: 'border-violet-400', chip: 'bg-violet-50', tip: 'bg-violet-50 text-violet-900', hover: 'hover:border-violet-300', eyebrow: 'text-violet-600' },
  slate: { bar: 'border-slate-300', chip: 'bg-slate-100', tip: 'bg-slate-100 text-slate-800', hover: 'hover:border-slate-300', eyebrow: 'text-slate-600' },
}

// ── 독화 ──────────────────────────────────────────────
const READING_ACTIVITIES = [
  { icon: '👄', name: '입모양 학습', to: '/learn/viseme', body: '자음·모음의 기본 입모양을 3D 아바타로 익혀요. 독화의 출발점이에요.' },
  { icon: '🔤', name: '단어 학습', to: '/learn/word', body: '비슷해 보이는 입모양을 단어 단위로 구별하는 훈련이에요.' },
  { icon: '💬', name: '문장 학습', to: '/learn/scenario', body: '상황(카페·병원 등)과 난이도를 골라요. AI가 만든 문장을 입모양만 보고 맞히고(주관식·선택형·서술형), "AI 대화"로 실시간 대화 독화까지 연습해요.' },
  { icon: '🧩', name: '문맥 추론', to: '/learn/closure', body: '같아 보이는 소리를 앞뒤 맥락으로 좁혀 맞혀요. 독화의 절반은 추리예요.' },
  { icon: '✍️', name: '내 문장 발음 보기', to: '/pronounce', body: '아무 한국어 문장이나 입력하면 3D 입모양으로 어떻게 움직이는지 보여줘요.' },
  { icon: '🔁', name: '독화 복습', to: '/review/mistakes', body: '틀린 문장·예정(간격반복)·북마크를 다시 풀어요.' },
]

// 독화 '기술' 자체의 요령
const STRATEGIES = [
  { icon: '👀', title: '똑같이 보이는 소리가 있다 (동구형이음)', body: 'ㅂ·ㅁ·ㅍ는 입술이 닫혀 똑같이 보이고, ㄱ·ㄷ·ㅈ·ㅅ처럼 입 안쪽 소리도 구별이 거의 안 돼요. "정확히 읽기"가 아니라 "가능성 좁히기"로 생각하세요.' },
  { icon: '🧩', title: '문맥으로 메꾼다', body: '입모양이 애매하면 앞뒤 말과 상황으로 판단해요. "___ 마셔요"에서 물/불로 보여도 마시는 건 물이죠.' },
  { icon: '⚓', title: '모음을 닻으로 삼는다', body: '자음보다 모음(ㅏ·ㅣ·ㅗ·ㅜ)이 훨씬 잘 보여요. 모음 뼈대를 먼저 잡고 자음을 채우세요.' },
  { icon: '🎯', title: '첫 소리에 집중', body: '단어의 첫 입모양(초성·첫 모음)이 정보가 가장 많아요. 시작을 놓치면 뒤가 다 흔들려요.' },
  { icon: '💡', title: '화자·환경을 고른다', body: '밝은 곳에서 얼굴이 정면으로 보이고 천천히 말할 때 잘 돼요. "천천히, 마주 보고" 요청하는 것도 실력이에요.' },
  { icon: '🔁', title: '못 알아들으면 되묻기', body: '전부 완벽히 읽을 필요 없어요. 핵심 단어만 확인하거나 "○○ 말씀이세요?"로 좁혀가세요.' },
]

// ── 말하기 6단계 ──────────────────────────────────────
const SPEAKING_STAGES = [
  { icon: '🗣️', name: '발성', to: '/learn/speaking?stage=0', body: '원할 때 목소리 내기 · 길게 유지' },
  { icon: '🎚️', name: '운율 조절', to: '/learn/speaking?stage=1', body: '크기 · 길이 · 높낮이 바꾸기' },
  { icon: '👄', name: '모음', to: '/learn/speaking?stage=2', body: '기본 모음 8개 — 가장 잘 보이는 소리' },
  { icon: '🅿️', name: '자음', to: '/learn/speaking?stage=3', body: '입술소리부터 · 최소대립쌍' },
  { icon: '🔤', name: '음절·단어', to: '/learn/speaking?stage=4', body: '짧은 단어부터 여러 음절까지' },
  { icon: '💬', name: '문장·억양', to: '/learn/speaking?stage=5', body: '평서문은 내림, 의문문은 올림' },
]
const SPEAKING_HOW = [
  '마이크로 말하면 목소리 크기·억양이 실시간 곡선으로 보여요.',
  'AI가 전사·채점하고 어디를 고치면 좋을지 코칭해줘요.',
  '📷 웹캠 미러로 내 입모양을 아바타와 나란히 확인할 수 있어요.',
  '단어·문장 단계는 AI가 매번 새 문항을 생성해 같은 문제만 반복하지 않아요.',
]

// ── 촉각 5단계 ────────────────────────────────────────
const TACTILE_LEVELS = [
  { icon: '〰️', name: '감각 (유·무성)', body: '진동이 있고 없음을 손끝으로 구별' },
  { icon: '👄', name: '모음', body: '턱 벌림·입술 모양의 차이를 느끼기' },
  { icon: '⚖️', name: '최소대립쌍', body: '눈으론 같아도 촉각으론 다른 소리 (핵심)' },
  { icon: '🔤', name: '단어', body: '촉각 단서를 종합해 낱말 인식' },
  { icon: '💬', name: '문장', body: '연속된 말의 흐름을 촉각으로 따라가기' },
]
const TACTILE_HOW = [
  '"느끼기(재생)"로 얼굴 모형/시뮬레이터를 동작시켜 손으로 느껴요.',
  '보기에서 고르거나(객관식) 느낀 말을 직접 입력해요(주관식).',
  '🙈 순수 촉각 모드로 시뮬레이터를 가리면 손 감각만으로 도전할 수 있어요.',
  '자유 체험 모드로 아무 낱말·문장이나 골라 재생하며 촉각을 익혀요.',
]

// ── 도구 · 원리 ───────────────────────────────────────
const TOOLS = [
  { icon: '🤟', title: '수어 번역', body: '앱 어디서나 한국어 문장을 드래그하면 "수어로 보기" 버튼이 떠요. 누르면 그 자리에서 한국수어(KSL) 영상으로 바꿔 보여줘요.' },
  { icon: '✍️', title: '내 문장 발음 보기', body: '궁금한 문장을 입력하면 3D 입모양이 어떻게 움직이는지 바로 확인해요.' },
  { icon: '🔁', title: '오늘의 복습', body: '독화·말하기·촉각을 각각 예정(간격반복)·틀린 문제·북마크로 나눠 다시 풀어요.' },
  { icon: '📊', title: '학습 분석', body: '평균 점수·취약 입모양·학습 흐름을 보고, AI가 다음에 무엇을 연습하면 좋을지 제안해요.' },
]
const SYSTEM_INFO = [
  { icon: '🔬', title: '입모양 분류 시스템', body: '한국어 음소를 양순음(ㅂ/ㅍ/ㅁ)·개방모음·원순모음·치경음·연구개음 등 10개 입모양 그룹으로 분류해 학습·채점의 기준으로 삼아요.' },
  { icon: '🧮', title: '음운 유사도 채점', body: '단순 정오가 아니라 부분 점수를 줘요. "밥"을 "팝"으로 답하면 양순음(ㅂ↔ㅍ)의 시각적 유사성을 인정해 높은 점수를 주죠. 점수가 높을수록 XP도 더 많이 받아요.' },
  { icon: '🔥', title: '연속 학습 보너스(스트릭)', body: '매일 연속으로 연습하면 XP 보너스가 커져요(최대 3배). 하루 빠지면 초기화되니 꾸준히!' },
]

const TABS = [
  { key: 'start', label: '시작하기' },
  { key: 'reading', label: '독화' },
  { key: 'speaking', label: '말하기' },
  { key: 'tactile', label: '촉각' },
  { key: 'more', label: '도구 · 원리' },
]

// ── 재사용 컴포넌트 ───────────────────────────────────
function SectionTitle({ eyebrow, children, sub, accent = 'slate' }) {
  return (
    <div className="mb-4">
      {eyebrow && <p className={`text-xs font-black tracking-[0.14em] ${ACCENT[accent].eyebrow}`}>{eyebrow}</p>}
      <h2 className="mt-1 text-lg font-black text-slate-900">{children}</h2>
      {sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}
    </div>
  )
}

// 클릭하면 해당 학습으로 이동하는 활동 카드
function ActivityCard({ icon, name, body, to, accent, onGo }) {
  const a = ACCENT[accent]
  return (
    <button
      type="button"
      onClick={() => to && onGo(to)}
      className={`group flex w-full items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${a.hover} focus:outline-none focus:ring-2 focus:ring-slate-300`}
    >
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl text-xl ${a.chip}`}>{icon}</span>
      <span className="min-w-0 pt-0.5">
        <span className="flex items-center gap-1 font-black text-slate-900">{name}
          {to && <span className="text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500">→</span>}
        </span>
        <span className="mt-1 block text-sm leading-relaxed text-slate-600">{body}</span>
      </span>
    </button>
  )
}

function Tip({ accent, children }) {
  return (
    <div className={`mt-4 rounded-xl px-4 py-3 text-sm leading-relaxed ${ACCENT[accent].tip}`}>
      <span className="font-black">TIP · </span>{children}
    </div>
  )
}

export default function Guide() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('start')
  const go = (to) => navigate(to)

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <LearnHeader
        title="사용법 안내"
        description="LIPLAB의 기능과 학습 방법을 한곳에서 알아보세요."
        accent="etc"
        onExit={() => navigate('/dashboard')}
      />

      <main className="mx-auto max-w-4xl px-4 py-7 sm:py-9">
        {/* 탭 바 */}
        <div className="sticky top-2 z-10 mb-7 flex gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white/90 p-1 shadow-sm backdrop-blur">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-current={tab === t.key ? 'page' : undefined}
              className={`flex-1 whitespace-nowrap rounded-xl px-3 py-2.5 text-sm font-bold transition ${
                tab === t.key ? 'bg-slate-900 text-white shadow' : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>

          {/* ── 시작하기 ── */}
          {tab === 'start' && (
            <div className="space-y-8">
              <section>
                <SectionTitle eyebrow="한눈에">학습은 이렇게 흘러가요</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    { n: '1', title: '기둥을 고른다', body: '독화·말하기·촉각 중 지금 훈련할 축을 선택해요.' },
                    { n: '2', title: '단계별로 학습한다', body: '기초부터 실전까지, 나에게 맞는 활동·단계를 밟아요.' },
                    { n: '3', title: '복습하고 분석한다', body: '틀린 문제·예정 항목을 다시 풀고, 분석에서 약점을 확인해요.' },
                  ].map((f) => (
                    <div key={f.n} className="rounded-2xl border border-slate-200 bg-white p-5">
                      <div className="mb-3 grid h-9 w-9 place-items-center rounded-full bg-slate-900 text-sm font-black text-white">{f.n}</div>
                      <h3 className="font-bold text-slate-900">{f.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">{f.body}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="메뉴 사용법" sub="원하는 활동으로 바로 갈 수 있어요.">어디서 시작하나요</SectionTitle>
                <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-700">
                  <p>· <b>위쪽 메뉴바</b>(독화▾ · 말하기▾ · 촉각▾ · 기타▾)에서 세부 활동을 바로 골라요.</p>
                  <p>· <b>오른쪽 위</b>의 복습·사용법, 그리고 문장을 드래그하면 뜨는 <b>🤟 수어 번역</b>도 어디서나 쓸 수 있어요.</p>
                  <p>· 대시보드 가운데 <b>캐러셀</b>에서 세 기둥을 넘겨 보며 시작해도 돼요.</p>
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="세 기둥">무엇을 훈련하나요</SectionTitle>
                <div className="space-y-3">
                  {[
                    { key: 'reading', icon: '👁️', title: '독화 (입 읽기)', accent: 'sky', desc: '상대의 입모양을 보고 말을 이해하는 입력 능력이에요.' },
                    { key: 'speaking', icon: '🗣️', title: '말하기 (발음)', accent: 'rose', desc: '내 발음을 눈으로 보며 다듬는 산출 능력이에요.' },
                    { key: 'tactile', icon: '🖐️', title: '촉각 (타도마)', accent: 'violet', desc: '얼굴 모형의 턱·입술·진동·바람을 손으로 느껴 말을 이해해요.' },
                  ].map((p) => (
                    <button key={p.key} type="button" onClick={() => setTab(p.key)}
                      className={`flex w-full items-start gap-4 rounded-2xl border-l-4 bg-white p-5 text-left transition hover:shadow-md ${ACCENT[p.accent].bar}`}>
                      <span className="text-3xl">{p.icon}</span>
                      <span>
                        <span className="block font-black text-slate-900">{p.title}</span>
                        <span className="mt-1 block text-sm leading-relaxed text-slate-600">{p.desc}</span>
                      </span>
                      <span className="ml-auto self-center text-slate-300">→</span>
                    </button>
                  ))}
                </div>
              </section>
            </div>
          )}

          {/* ── 독화 ── */}
          {tab === 'reading' && (
            <div className="space-y-8">
              <section>
                <SectionTitle eyebrow="독화 · 입 읽기" accent="sky"
                  sub="상대의 입모양을 보고 말을 이해하는 훈련이에요. 카드를 누르면 바로 시작돼요.">활동별 사용법</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {READING_ACTIVITIES.map((it) => (
                    <ActivityCard key={it.name} {...it} accent="sky" onGo={go} />
                  ))}
                </div>
                <Tip accent="sky">"정확히 읽기"가 아니라 "가능성 좁히기"예요. AI가 매번 새 문장을 내줘서 같은 문제만 반복하지 않아요.</Tip>
              </section>

              <section>
                <SectionTitle eyebrow="핵심 전략" accent="sky"
                  sub="기능 사용법 이전에, 독화라는 '기술' 자체의 요령이에요.">독화, 이렇게 하세요</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {STRATEGIES.map((s) => (
                    <div key={s.title} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                      <span className="shrink-0 text-2xl">{s.icon}</span>
                      <div>
                        <h3 className="font-bold text-slate-900">{s.title}</h3>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          {/* ── 말하기 ── */}
          {tab === 'speaking' && (
            <div className="space-y-8">
              <section>
                <SectionTitle eyebrow="말하기 · 발음" accent="rose"
                  sub="내 발음을 눈으로 보며 다듬는 훈련이에요. 마이크로 녹음하면 AI가 채점·코칭해요.">어떻게 하나요</SectionTitle>
                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <ol className="space-y-2">
                    {SPEAKING_HOW.map((s, i) => (
                      <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-slate-700">
                        <span className="shrink-0 font-black text-slate-300">{i + 1}</span><span>{s}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="6단계 커리큘럼" accent="rose"
                  sub="상단 '말하기▾' 메뉴에서 단계를 바로 고를 수 있어요. 카드를 눌러 시작하세요.">발성부터 문장 억양까지</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {SPEAKING_STAGES.map((s, i) => (
                    <ActivityCard key={s.name} icon={s.icon} name={`${i + 1}. ${s.name}`} body={s.body} to={s.to} accent="rose" onGo={go} />
                  ))}
                </div>
                <Tip accent="rose">단어·문장 단계는 AI가 매번 새 문항을 생성해요. 잠긴 단계는 앞 단계를 숙달하면 열려요.</Tip>
              </section>
            </div>
          )}

          {/* ── 촉각 ── */}
          {tab === 'tactile' && (
            <div className="space-y-8">
              <section>
                <SectionTitle eyebrow="촉각 · 타도마" accent="violet"
                  sub="얼굴 모형의 턱·입술·진동·바람을 손으로 느껴 말을 이해해요. 하드웨어 없이 시뮬레이터로도 체험돼요.">어떻게 하나요</SectionTitle>
                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                  <ol className="space-y-2">
                    {TACTILE_HOW.map((s, i) => (
                      <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-slate-700">
                        <span className="shrink-0 font-black text-slate-300">{i + 1}</span><span>{s}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="5단계 커리큘럼" accent="violet"
                  sub="감각에서 문장까지 위계적으로 확장해요.">무엇을 익히나요</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {TACTILE_LEVELS.map((lv, i) => (
                    <div key={lv.name} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4">
                      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-50 text-xl">{lv.icon}</span>
                      <div className="pt-0.5">
                        <p className="font-black text-slate-900">{i + 1}. {lv.name}</p>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">{lv.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="직접 만들기" accent="violet"
                  sub="얼굴 모형은 오픈소스예요.">하드웨어 조립 설명서</SectionTitle>
                <button type="button" onClick={() => go('/hardware/build')}
                  className="group flex w-full items-center gap-4 rounded-2xl bg-gradient-to-br from-violet-600 to-purple-500 p-5 text-left text-white shadow-lg shadow-violet-200 transition hover:brightness-105">
                  <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/20 text-2xl">🛠️</span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-black">얼굴 모형 조립 설명서 보기</span>
                    <span className="mt-0.5 block text-sm text-violet-50">3D 프린팅 파일 · 부품(BOM) · 조립 순서 · 배선도 · 펌웨어까지 실제 제작 사진과 함께 안내해요.</span>
                  </span>
                  <span className="text-2xl transition group-hover:translate-x-1">→</span>
                </button>
                <Tip accent="violet">실제 얼굴 모형 연결(Web Serial)은 <b>데스크톱 Chrome·Edge</b>에서만 동작해요. 아두이노 IDE 창은 닫아야 웹이 포트에 연결할 수 있어요.</Tip>
              </section>
            </div>
          )}

          {/* ── 도구 · 원리 ── */}
          {tab === 'more' && (
            <div className="space-y-8">
              <section>
                <SectionTitle eyebrow="보조 도구" sub="세 기둥과 별개로 언제든 쓰는 기능이에요.">이런 것도 있어요</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {TOOLS.map((t) => (
                    <div key={t.title} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                      <span className="shrink-0 text-2xl">{t.icon}</span>
                      <div>
                        <h3 className="font-bold text-slate-900">{t.title}</h3>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">{t.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <SectionTitle eyebrow="원리" sub="학습을 뒷받침하는 방식이에요.">LIPLAB은 어떻게 동작하나요</SectionTitle>
                <div className="grid gap-3 sm:grid-cols-2">
                  {SYSTEM_INFO.map((s) => (
                    <div key={s.title} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                      <span className="shrink-0 text-2xl">{s.icon}</span>
                      <div>
                        <h3 className="font-bold text-slate-900">{s.title}</h3>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

        </motion.div>
      </main>
    </div>
  )
}
