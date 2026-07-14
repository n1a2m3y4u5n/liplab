import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

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

export default function Guide() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">사용법</h1>
            <p className="text-sm text-gray-500">LIPLAB의 모든 기능과 학습 방법을 알아보세요</p>
          </div>
          <button onClick={() => navigate(-1)} className="text-gray-500 hover:text-gray-800 text-sm">
            ← 뒤로
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-8">

        {/* 독화 전략 코칭 — 기술 자체의 요령 */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
          <h2 className="text-xl font-bold text-gray-900 mb-1">독화, 이렇게 하세요 <span className="text-primary-500">(핵심 전략)</span></h2>
          <p className="text-sm text-gray-500 mb-4">기능 사용법 이전에, 독화라는 '기술' 자체의 요령입니다.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {STRATEGIES.map((s, i) => (
              <div key={i} className="card">
                <div className="flex items-start gap-3">
                  <span className="text-2xl shrink-0">{s.icon}</span>
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-1">{s.title}</h3>
                    <p className="text-sm text-gray-600 leading-relaxed">{s.body}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        {/* LIPLAB 시스템 소개 */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
          <h2 className="text-xl font-bold text-gray-900 mb-4">LIPLAB이란?</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {SYSTEM_INFO.map((info, i) => (
              <div key={i} className="card">
                <div className="flex items-start gap-3">
                  <span className="text-2xl">{info.icon}</span>
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-1">{info.title}</h3>
                    <p className="text-sm text-gray-600 leading-relaxed">{info.content}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        {/* 기둥별 사용 방법 (독화·말하기·촉각) */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <h2 className="text-xl font-bold text-gray-900 mb-1">기능별 사용 방법</h2>
          <p className="text-sm text-gray-500 mb-4">세 학습 기둥을 어떻게 쓰는지 안내해요.</p>
          <div className="space-y-4">
            {PILLARS.map((p) => (
              <div key={p.key} className={`card border-l-4 ${p.color}`}>
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-2xl">{p.icon}</span>
                  <h3 className="text-lg font-bold text-gray-900">{p.title}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${p.badge}`}>기둥</span>
                </div>
                <p className="text-sm text-gray-500 mb-3">{p.desc}</p>
                <div className="space-y-3">
                  {p.modes.map((m, mi) => (
                    <div key={mi}>
                      <p className="text-sm font-bold text-gray-800 mb-1">{m.name}</p>
                      <ol className="space-y-1">
                        {m.steps.map((step, si) => (
                          <li key={si} className="flex gap-2 text-sm text-gray-700">
                            <span className="text-gray-400 font-bold shrink-0">{si + 1}.</span>
                            {step}
                          </li>
                        ))}
                      </ol>
                    </div>
                  ))}
                </div>
                <div className="mt-3 p-3 bg-white bg-opacity-60 rounded-lg">
                  <p className="text-xs text-gray-500">
                    <span className="font-semibold text-primary-600">TIP</span> {p.tip}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        {/* 보조 도구 */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <h2 className="text-xl font-bold text-gray-900 mb-4">보조 도구</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {TOOLS.map((t, i) => (
              <div key={i} className="card">
                <div className="text-2xl mb-1">{t.icon}</div>
                <h3 className="font-semibold text-gray-900 mb-1">{t.title}</h3>
                <p className="text-sm text-gray-600 leading-relaxed">{t.body}</p>
              </div>
            ))}
          </div>
        </motion.section>

        {/* 시작하기 버튼 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="text-center pb-4"
        >
          <button
            onClick={() => navigate('/dashboard')}
            className="btn-primary px-10 py-3.5 text-base"
          >
            학습 시작하기 →
          </button>
        </motion.div>
      </main>
    </div>
  )
}
