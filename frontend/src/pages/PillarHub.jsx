import { useParams, useNavigate, Navigate } from 'react-router-dom'

// 기둥(독화·말하기·촉각)별 하위 학습·테스트·복습 메뉴 모음.
// 대시보드 캐러셀에서 기둥을 누르면 바로 활동으로 가지 않고 이 허브로 온다.
// ※ 공용 DomainPageShell(학습/복습/분석 전역 탭)은 쓰지 않는다 — 그 탭들이
//    기둥 맥락을 잃고 엉뚱한 곳(독화 입모양)으로 튀는 혼란을 막기 위함.
const PILLARS = {
  reading: {
    accent: 'sky',
    title: '독화 (입모양 읽기)',
    description: '상대의 입모양을 보고 말을 이해하는 훈련이에요. 입모양 학습부터 문장 학습까지 골라 진행하세요.',
    items: [
      { label: '입모양 학습', desc: '자음·모음의 입모양 학습', to: '/learn/viseme', icon: '👄' },
      { label: '단어 학습', desc: '비슷한 입모양 구별 학습', to: '/learn/word', icon: '🔤' },
      { label: '문장 학습', desc: '상황별 독화 + AI 대화 학습', to: '/learn/scenario', icon: '💬' },
      { label: '문맥 추론', desc: '앞뒤 맥락으로 뜻 찾기', to: '/learn/closure', icon: '🧩' },
      { label: '내 문장 발음 보기', desc: '아무 글이나 입모양 확인', to: '/pronounce', icon: '✍️' },
      { label: '독화 복습', desc: '틀린 문장·예정 다시 풀기', to: '/review/mistakes', icon: '🔁' },
    ],
  },
  speaking: {
    accent: 'rose',
    title: '말하기 (발음)',
    description: '내 발음을 눈으로 보며 다듬는 훈련이에요. 마이크로 녹음하면 AI가 전사·채점하고 코칭해줘요.',
    items: [
      { label: '말하기 학습', desc: '발성부터 문장 억양까지 6단계', to: '/learn/speaking', icon: '🎤' },
      { label: '말하기 복습', desc: '저조했던 발음 다시 연습', to: '/review/speaking', icon: '🔁' },
    ],
  },
  tactile: {
    accent: 'violet',
    title: '촉각 (타도마)',
    description: '얼굴 모형의 턱·입술·진동·바람을 손으로 느껴 말을 이해하는 훈련이에요. 하드웨어 없이 시뮬레이터로도 체험할 수 있어요.',
    items: [
      { label: '촉각 학습', desc: '5단계 커리큘럼 + 자유 체험', to: '/learn/tactile', icon: '🖐️' },
      { label: '촉각 복습', desc: '취약 항목 다시 풀기', to: '/review/tactile', icon: '🔁' },
    ],
  },
}

const ACCENTS = {
  sky: { eyebrow: 'text-sky-700', panel: 'from-sky-50 to-white', mark: 'bg-sky-500', hover: 'hover:border-sky-300', chip: 'bg-sky-50' },
  rose: { eyebrow: 'text-rose-700', panel: 'from-rose-50 to-white', mark: 'bg-rose-500', hover: 'hover:border-rose-300', chip: 'bg-rose-50' },
  violet: { eyebrow: 'text-violet-700', panel: 'from-violet-50 to-white', mark: 'bg-violet-500', hover: 'hover:border-violet-300', chip: 'bg-violet-50' },
}

export default function PillarHub() {
  const { id } = useParams()
  const navigate = useNavigate()
  const pillar = PILLARS[id]
  if (!pillar) return <Navigate to="/dashboard" replace />
  const a = ACCENTS[pillar.accent] || ACCENTS.sky

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-950">
      <main className="mx-auto max-w-[1180px] px-4 py-7 sm:px-6 sm:py-10">
        <section className={`relative overflow-hidden rounded-[28px] border border-slate-200 bg-gradient-to-br ${a.panel} px-5 py-7 sm:px-8 sm:py-9`}>
          <span aria-hidden="true" className={`absolute left-0 top-0 h-full w-1.5 ${a.mark}`} />
          <p className={`text-xs font-black tracking-[0.14em] ${a.eyebrow}`}>LEARN</p>
          <h1 className="mt-2 text-3xl font-black tracking-[-0.04em] sm:text-4xl">{pillar.title}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">{pillar.description}</p>
        </section>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {pillar.items.map((it) => (
            <button
              key={it.to}
              type="button"
              onClick={() => navigate(it.to)}
              className={`flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:-translate-y-0.5 ${a.hover} hover:shadow-md focus:outline-none focus:ring-2 focus:ring-sky-400`}
            >
              <span aria-hidden="true" className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${a.chip} text-xl`}>{it.icon}</span>
              <span className="min-w-0 pt-0.5">
                <span className="block font-black text-slate-900">{it.label}</span>
                <span className="mt-1 block text-sm leading-relaxed text-slate-500">{it.desc}</span>
              </span>
            </button>
          ))}
        </div>
      </main>
    </div>
  )
}
