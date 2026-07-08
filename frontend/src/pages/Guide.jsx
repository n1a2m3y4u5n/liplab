import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'

const MODES = [
  {
    icon: '📖',
    title: '학습 모드',
    color: 'border-green-400 bg-green-50',
    badge: 'bg-green-100 text-green-700',
    steps: [
      '상황(카페, 병원 등)과 난이도를 선택하세요.',
      '3D 입모양 애니메이션이 재생됩니다.',
      '화면에 표시된 문장을 보면서 입모양을 익히세요.',
      '충분히 익혔으면 "다음 문장"을 눌러 진행하세요.',
    ],
    tip: '채점 없이 반복 재생되므로 처음 독화를 배우는 분에게 적합합니다.',
  },
  {
    icon: '✏️',
    title: '주관식 테스트',
    color: 'border-blue-400 bg-blue-50',
    badge: 'bg-blue-100 text-blue-700',
    steps: [
      '입모양 애니메이션을 보고 무슨 말인지 직접 타이핑합니다.',
      '힌트 버튼을 누르면 글자 수 → 첫 글자 → 전체 순서로 힌트를 받을 수 있습니다.',
      '제출 후 점수와 오답 분석을 확인하세요.',
      '어려운 문장은 ☆ 북마크 버튼으로 저장해두세요.',
    ],
    tip: '정확히 타이핑하지 않아도 음운 유사도를 계산해 부분 점수를 줍니다.',
  },
  {
    icon: '🔢',
    title: '4지선다 테스트',
    color: 'border-purple-400 bg-purple-50',
    badge: 'bg-purple-100 text-purple-700',
    steps: [
      '입모양 애니메이션을 보고 4개 보기 중 하나를 선택합니다.',
      '보기는 같은 시나리오의 문장들로 구성됩니다.',
      '클릭 즉시 정답/오답을 확인할 수 있습니다.',
      '타이핑 없이 빠르게 많은 문장을 연습할 수 있습니다.',
    ],
    tip: '주관식보다 쉽지만 보기를 통해 비슷한 문장을 구분하는 연습이 됩니다.',
  },
  {
    icon: '🔁',
    title: '복습 모드',
    color: 'border-amber-400 bg-amber-50',
    badge: 'bg-amber-100 text-amber-700',
    steps: [
      '이전 테스트에서 60점 미만을 받은 문장들이 자동으로 모입니다.',
      '별도 상황/난이도 선택 없이 바로 시작됩니다.',
      '틀린 문장 위주로 집중 연습할 수 있습니다.',
      '복습 후 분석 페이지에서 개선 여부를 확인하세요.',
    ],
    tip: '틀린 문장이 없으면 복습 모드가 활성화되지 않습니다. 먼저 테스트를 진행하세요.',
  },
  {
    icon: '💬',
    title: '대화 연습',
    color: 'border-sky-400 bg-sky-50',
    badge: 'bg-sky-100 text-sky-700',
    steps: [
      'AI가 선택한 상황에 맞는 대화 상대가 됩니다.',
      'AI의 입모양 애니메이션을 보고 무슨 말인지 파악하세요.',
      '텍스트로 답변하면 AI가 맥락에 맞는 다음 대화를 이어갑니다.',
      '실제 대화 흐름에 맞춰 자연스러운 독화를 연습할 수 있습니다.',
    ],
    tip: 'Claude AI가 상황에 맞는 자연스러운 한국어 대화를 생성합니다.',
  },
]

const SYSTEM_INFO = [
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

export default function Guide() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">사용법 안내</h1>
            <p className="text-sm text-gray-500">LIPLAB의 모든 기능과 학습 방법을 알아보세요</p>
          </div>
          <button onClick={() => navigate(-1)} className="text-gray-500 hover:text-gray-800 text-sm">
            ← 뒤로
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-8">

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

        {/* 모드별 사용 방법 */}
        <motion.section initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <h2 className="text-xl font-bold text-gray-900 mb-4">모드별 사용 방법</h2>
          <div className="space-y-4">
            {MODES.map((m, i) => (
              <div
                key={i}
                className={`card border-l-4 ${m.color}`}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-2xl">{m.icon}</span>
                  <h3 className="text-lg font-bold text-gray-900">{m.title}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${m.badge}`}>
                    모드
                  </span>
                </div>
                <ol className="space-y-1.5 mb-3">
                  {m.steps.map((step, si) => (
                    <li key={si} className="flex gap-2 text-sm text-gray-700">
                      <span className="text-primary-500 font-bold shrink-0">{si + 1}.</span>
                      {step}
                    </li>
                  ))}
                </ol>
                <div className="p-3 bg-white bg-opacity-60 rounded-lg">
                  <p className="text-xs text-gray-500">
                    <span className="font-semibold text-primary-600">TIP</span> {m.tip}
                  </p>
                </div>
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
