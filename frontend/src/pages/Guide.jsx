import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import LearnHeader from '../components/LearnHeader'

// LIPLAB의 세 학습 기둥 — 각 기둥의 사용법.
const PILLARS = [
  {
    key: 'read', icon: '👁️', title: '독화 (입 읽기)',
    color: 'border-sky-400 bg-sky-50', badge: 'bg-sky-100 text-sky-700',
    desc: '상대의 입모양을 보고 말을 이해하는 입력 능력이에요.',
    modes: [
      { name: '① 단계 학습 (0~2단계)', steps: [
        '처음이면 입문·배치로 나에게 맞는 트랙을 정해요.',
        '입모양 학습 → 단어 학습을 3D 애니메이션으로 단계별로 진행해요.',
        '문맥 추론 훈련으로 안 보이는 소리를 추리하는 힘을 길러요.',
      ] },
      { name: '② 문장 학습 (3~4단계)', steps: [
        '상황(카페·병원 등)과 난이도를 골라요.',
        'AI가 만든 문장을 입모양만 보고 맞혀요 (주관식·4지선다·서술형 혼합).',
        '대화 실전은 AI와 주고받으며 실제 대화 흐름을 연습해요.',
      ] },
    ],
    tip: '"정확히 읽기"가 아니라 "가능성 좁히기"예요. AI가 매번 새 문장을 내줘서 같은 문제만 반복하지 않아요.',
  },
  {
    key: 'speak', icon: '🗣️', title: '말하기 (발음)',
    color: 'border-rose-400 bg-rose-50', badge: 'bg-rose-100 text-rose-700',
    desc: '내 발음을 눈으로 보며 다듬는 산출 능력이에요. 마이크로 녹음하면 AI가 채점해요.',
    modes: [
      { name: '6단계 커리큘럼', steps: [
        '발성 → 운율 → 모음 → 자음 → 단어 → 문장·억양 순서로 올라가요.',
        '마이크로 말하면 목소리 크기·억양이 실시간 곡선으로 보여요.',
        'AI가 전사·채점하고 어디를 고치면 좋을지 코칭해줘요.',
      ] },
    ],
    tip: '단어·문장 단계는 AI가 매번 새 문항을 생성해요. 웹캠 거울로 내 입모양도 같이 확인할 수 있어요.',
  },
  {
    key: 'tactile', icon: '🖐️', title: '촉각 (타도마)',
    color: 'border-purple-400 bg-purple-50', badge: 'bg-purple-100 text-purple-700',
    desc: '얼굴 모형의 턱·입술·진동·바람을 손으로 느껴 말을 이해하는 방식이에요. 하드웨어 없이 시뮬레이터로도 체험돼요.',
    modes: [
      { name: '5단계 커리큘럼 퀴즈', steps: [
        '감각(유·무성) → 모음 → 최소대립쌍 → 단어 → 문장 순으로 확장해요.',
        '"느끼기(재생)"로 얼굴 모형/시뮬레이터를 동작시켜 손으로 느껴요.',
        '보기에서 고르거나(객관식) 느낀 말을 직접 입력해요(주관식).',
        '🙈 순수 촉각으로 시뮬레이터를 가리면 손 감각만으로 도전할 수 있어요.',
      ] },
      { name: '자유 체험 · 오픈소스 하드웨어', steps: [
        '아무 낱말·문장이나 골라 재생하며 촉각을 자유롭게 익혀요.',
        '얼굴 모형은 오픈소스 — 3D 파일·부품(BOM)·조립법·펌웨어가 페이지에 공개돼요.',
      ] },
    ],
    tip: 'Web Serial(데스크톱 Chrome·Edge)로 실제 아두이노 얼굴 모형에 연결할 수 있어요.',
  },
]

// 보조 도구 — 기둥과 별개로 언제든 쓰는 기능.
const TOOLS = [
  { icon: '✍️', title: '내 문장 발음 보기', body: '아무 한국어 문장이나 입력하면 3D 입모양으로 어떻게 움직이는지 보여줘요. 궁금한 말의 입 모양을 바로 확인할 때 좋아요.' },
  { icon: '🤟', title: '수어 번역', body: '앱 어디서나 문장을 선택하면 한국수어(KSL) 학습 영상으로 바꿔 보여줘요.' },
  { icon: '🔁', title: '오늘의 복습', body: '독화·말하기·촉각 세 기둥을 각각 예정(간격반복)·틀린 문제·북마크로 나눠 다시 풀어요. 틀리거나 ☆로 저장한 항목이 자동으로 모여요.' },
]

const SYSTEM_INFO = [
  {
    title: 'LIPLAB의 세 기둥',
    icon: '🏛️',
    content:
      'LIPLAB은 청각장애인의 의사소통을 독화(입 읽기·입력)·말하기(발음·산출)·촉각(타도마·손으로 이해)의 세 축으로 함께 훈련합니다. AI와 3D 시각화, 오픈소스 하드웨어로 각 축에 맞는 방법을 제공합니다.',
  },
  {
    title: '독화(Speechreading)란?',
    icon: '👁️',
    content:
      '독화는 상대방의 입술 움직임(입모양)을 보고 말을 이해하는 기술입니다. 청각장애인이나 난청인이 소통하는 데 핵심적인 능력입니다. LIPLAB은 AI를 활용해 한국어 독화 훈련을 체계적으로 제공합니다.',
  },
  {
    title: '입모양 분류 시스템',
    icon: '🔬',
    content:
      'LIPLAB은 한국어 음소를 10개의 입모양 그룹으로 분류합니다: 양순음(ㅂ/ㅍ/ㅁ), 개방모음(ㅏ/ㅐ), 전설모음(ㅣ/ㅔ), 원순모음(ㅗ/ㅜ), 중설모음(ㅓ/ㅡ), 치경음(ㄷ/ㄴ/ㄹ/ㅅ), 연구개음(ㄱ/ㅇ), 성문음(ㅎ), 이중모음, 경구개음(ㅈ/ㅊ).',
  },
  {
    title: '점수 계산 방식',
    icon: '🧮',
    content:
      '단순 정오 채점이 아닌 음운 유사도 기반 부분 점수를 줍니다. 예: "밥"을 "팝"으로 답했다면 양순음(ㅂ↔ㅍ)의 시각적 유사성을 인정해 높은 점수를 부여합니다. 점수가 높을수록 더 많은 경험치(XP)를 얻습니다.',
  },
  {
    title: '연속 학습 보너스(스트릭)',
    icon: '🔥',
    content:
      '매일 연속으로 연습하면 경험치 보너스를 받습니다. 연속 일수가 늘어날수록 보너스가 커지며 최대 3배까지 XP를 얻을 수 있습니다. 하루라도 빠지면 스트릭이 초기화되니 꾸준히 연습하세요!',
  },
]

// 독화라는 '기술' 자체의 요령 — 기능 사용법보다 먼저 알아야 할 핵심 전략.
const STRATEGIES = [
  { icon: '👀', title: '똑같이 보이는 소리가 있다 (동구형이음)', body: 'ㅂ·ㅁ·ㅍ는 입술이 닫혀 똑같이 보이고, ㄱ·ㄷ·ㅈ·ㅅ처럼 입 안쪽에서 나는 소리도 서로 구별이 거의 안 됩니다. "정확히 읽는다"가 아니라 "가능성을 좁힌다"고 생각하세요.' },
  { icon: '🧩', title: '문맥으로 메꾼다', body: '입모양이 애매하면 앞뒤 말과 상황으로 판단합니다. "___ 마셔요"에서 입모양이 물/불로 보여도 마시는 건 물이죠. 독화의 절반은 추리입니다.' },
  { icon: '⚓', title: '모음을 닻으로 삼는다', body: '자음보다 모음(ㅏ·ㅣ·ㅗ·ㅜ)이 훨씬 잘 보입니다. 문장의 모음 뼈대를 먼저 잡고 자음을 채워 넣으세요.' },
  { icon: '🎯', title: '첫 소리에 집중', body: '단어의 첫 입모양(초성·첫 모음)이 가장 정보가 많습니다. 시작을 놓치면 뒤가 다 흔들려요.' },
  { icon: '💡', title: '화자·환경을 고른다', body: '밝은 곳에서 얼굴이 정면으로 보이고 너무 빠르지 않게 말할 때 독화가 잘 됩니다. "천천히, 마주 보고" 요청하는 것도 실력입니다.' },
  { icon: '🔁', title: '못 알아들으면 되묻기', body: '전부 완벽히 읽을 필요는 없습니다. 핵심 단어만 확인하거나 "○○ 말씀이세요?"로 좁혀가세요.' },
]

// 한눈에 보는 학습 흐름 — '빠른 시작' 탭 상단.
const FLOW = [
  { n: '1', title: '기둥을 고른다', body: '독화·말하기·촉각 중 지금 훈련할 축을 선택해요.' },
  { n: '2', title: '단계별로 학습한다', body: '기초부터 실전까지, 나에게 맞는 단계를 순서대로 밟아요.' },
  { n: '3', title: '복습하고 분석한다', body: '틀린 문제·예정 항목을 다시 풀고, 분석에서 약점을 확인해요.' },
]

const TABS = [
  { key: 'start', label: '빠른 시작' },
  { key: 'features', label: '기능별 사용법' },
  { key: 'strategy', label: '독화 전략' },
  { key: 'system', label: '원리 · 시스템' },
]

export default function Guide() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('start')

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <LearnHeader
        title="사용법 안내"
        description="LIPLAB의 기능과 학습 방법을 한곳에서 알아보세요."
        accent="reading"
        onExit={() => navigate('/dashboard')}
      />

      <main className="mx-auto max-w-4xl px-4 py-7 sm:py-9">
        {/* 탭 바 */}
        <div className="sticky top-2 z-10 mb-7 flex gap-1 rounded-2xl border border-slate-200 bg-white/90 p-1 shadow-sm backdrop-blur">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-current={tab === t.key ? 'page' : undefined}
              className={`flex-1 rounded-xl px-2 py-2.5 text-sm font-bold transition ${
                tab === t.key ? 'bg-slate-900 text-white shadow' : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>

          {/* ── 빠른 시작 ── */}
          {tab === 'start' && (
            <div className="space-y-8">
              <section>
                <h2 className="mb-1 text-lg font-black">학습은 이렇게 흘러가요</h2>
                <p className="mb-4 text-sm text-slate-500">세 단계만 기억하면 돼요.</p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {FLOW.map((f) => (
                    <div key={f.n} className="rounded-2xl border border-slate-200 bg-white p-5">
                      <div className="mb-3 grid h-9 w-9 place-items-center rounded-full bg-slate-900 text-sm font-black text-white">{f.n}</div>
                      <h3 className="font-bold text-slate-900">{f.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">{f.body}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h2 className="mb-1 text-lg font-black">세 학습 기둥</h2>
                <p className="mb-4 text-sm text-slate-500">필요에 맞는 축을 골라 시작하세요. 자세한 사용법은 '기능별 사용법' 탭에 있어요.</p>
                <div className="space-y-3">
                  {PILLARS.map((p) => (
                    <div key={p.key} className={`flex items-start gap-4 rounded-2xl border-l-4 bg-white p-5 ${p.color}`}>
                      <span className="text-3xl">{p.icon}</span>
                      <div>
                        <h3 className="font-bold text-slate-900">{p.title}</h3>
                        <p className="mt-1 text-sm leading-relaxed text-slate-600">{p.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <div className="pt-2 text-center">
                <button onClick={() => navigate('/dashboard')} className="rounded-xl bg-slate-900 px-8 py-3 text-sm font-bold text-white transition hover:bg-slate-700">
                  대시보드로 가서 시작하기 →
                </button>
              </div>
            </div>
          )}

          {/* ── 기능별 사용법 ── */}
          {tab === 'features' && (
            <div className="space-y-8">
              <section className="space-y-4">
                {PILLARS.map((p) => (
                  <div key={p.key} className={`rounded-2xl border-l-4 bg-white p-5 sm:p-6 ${p.color}`}>
                    <div className="mb-2 flex items-center gap-3">
                      <span className="text-2xl">{p.icon}</span>
                      <h3 className="text-lg font-black text-slate-900">{p.title}</h3>
                    </div>
                    <p className="mb-4 text-sm text-slate-600">{p.desc}</p>
                    <div className="space-y-4">
                      {p.modes.map((m, mi) => (
                        <div key={mi} className="rounded-xl bg-slate-50/70 p-4">
                          <p className="mb-2 text-sm font-black text-slate-800">{m.name}</p>
                          <ol className="space-y-1.5">
                            {m.steps.map((step, si) => (
                              <li key={si} className="flex gap-2.5 text-sm leading-relaxed text-slate-700">
                                <span className="shrink-0 font-black text-slate-400">{si + 1}</span>
                                <span>{step}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ))}
                    </div>
                    <div className={`mt-4 rounded-lg px-3 py-2.5 text-xs leading-relaxed ${p.badge}`}>
                      <span className="font-black">TIP · </span>{p.tip}
                    </div>
                  </div>
                ))}
              </section>

              <section>
                <h2 className="mb-1 text-lg font-black">보조 도구</h2>
                <p className="mb-4 text-sm text-slate-500">기둥과 별개로 언제든 쓰는 기능이에요.</p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {TOOLS.map((t, i) => (
                    <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5">
                      <div className="mb-2 text-2xl">{t.icon}</div>
                      <h3 className="font-bold text-slate-900">{t.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">{t.body}</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          {/* ── 독화 전략 ── */}
          {tab === 'strategy' && (
            <section>
              <h2 className="mb-1 text-lg font-black">독화, 이렇게 하세요</h2>
              <p className="mb-4 text-sm text-slate-500">기능 사용법 이전에, 독화라는 '기술' 자체의 요령이에요.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {STRATEGIES.map((s, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                    <span className="shrink-0 text-2xl">{s.icon}</span>
                    <div>
                      <h3 className="font-bold text-slate-900">{s.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── 원리 · 시스템 ── */}
          {tab === 'system' && (
            <section>
              <h2 className="mb-1 text-lg font-black">LIPLAB은 어떻게 동작하나요</h2>
              <p className="mb-4 text-sm text-slate-500">학습을 뒷받침하는 원리와 채점 방식이에요.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {SYSTEM_INFO.map((info, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-5">
                    <span className="shrink-0 text-2xl">{info.icon}</span>
                    <div>
                      <h3 className="font-bold text-slate-900">{info.title}</h3>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">{info.content}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

        </motion.div>
      </main>
    </div>
  )
}
