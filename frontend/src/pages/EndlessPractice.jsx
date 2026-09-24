import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'
import LoadingScreen from '../components/LoadingScreen'

/**
 * 엔드리스 학습 (Figma 리디자인 09 연습기능) — 약한 유형만 골라 무한 연습.
 * 숙달도 낮은 음소/입모양이 계속 출제된다. 단어 레슨(약점 가중 표집, 오답 보기는 최소대립 단어 우선)과
 * 문맥 레슨(약한 입모양이 든 문항부터)이 12문항씩 번갈아 이어진다(?endless=1, G-6).
 * 지금 출제될 약점 유형은 curriculumAPI.getNext()의 추천(targets: 이름·데모음절·숙달도)에서 읽어
 * Figma의 "지금 출제되는 유형" 진행바(숙달도 낮은 순)로 보여준다.
 */
const VIS_NAME = {
  1: '양순음', 2: '개방모음', 3: '전설모음', 4: '원순모음', 5: '중설모음',
  6: '치경음', 7: '연구개음', 8: '성문음', 9: '이중모음', 10: '경구개음',
}

export default function EndlessPractice() {
  const navigate = useNavigate()
  const [targets, setTargets] = useState(null)  // [{viseme_id,name,demo_syllable,mastery}]
  useEffect(() => {
    curriculumAPI.getNext()
      .then((d) => {
        // 추천 targets(이름·숙달도) 우선. 구형 응답(약점 id 배열)도 안전하게 흡수한다.
        if (Array.isArray(d?.targets) && d.targets.length) { setTargets(d.targets); return }
        const ids = d?.weak_visemes || d?.target_visemes || d?.visemes || []
        setTargets(ids.map((v) => ({ viseme_id: v, name: VIS_NAME[v] || String(v), mastery: null })))
      })
      .catch(() => setTargets([]))
  }, [])

  return (
    <AppShell active="practice" title="엔드리스 학습" description="틀렸던 유형이 계속 나와요">
      {/* 엔드리스 시작 — Figma 인디고 그라데이션 히어로(3D 하단테두리) */}
      <section className="relative w-full overflow-hidden rounded-[20px] border-2 border-b-[5px] border-endless-dark p-6 sm:p-[26px]"
        style={{ backgroundImage: 'linear-gradient(166deg, var(--endless-light) 0%, var(--endless) 71%)' }}>
        <div className="flex items-center justify-between gap-5">
          <div className="flex flex-col items-start gap-[18px] text-white">
            <p className="text-[24px] font-bold leading-tight tracking-[-0.48px]">약한 유형만 골라서 무한 연습</p>
            <p className="text-[14px] leading-relaxed opacity-85">숙달도가 낮은 음소가 계속 출제돼요. 단어 문제와 문맥 문제가 번갈아 나오고, 원할 때 멈출 수 있어요.</p>
            <button type="button" onClick={() => navigate('/learn/word?endless=1')}
              className="inline-flex items-center rounded-[13px] border-2 border-b-4 border-endless-line bg-white px-[30px] py-[14px] text-[16px] font-bold text-endless-dark transition active:translate-y-[1px] active:border-b-2">
              시작하기 →
            </button>
          </div>
          <img src="/ui/prac-endless.svg" alt="" className="hidden h-20 w-20 shrink-0 opacity-90 sm:block" />
        </div>
      </section>

      {/* 문맥 추론 이어 하기 — 입모양이 같은 단어를 문장 흐름으로 고른다. 약한 입모양이 든 문항부터 나온다(축 G-6). */}
      <section className="card-flat flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-[17px] font-bold text-ink">문맥으로 풀기</p>
          <p className="text-[14px] text-ink-muted">입모양이 같은 단어 중에서 문장 흐름에 맞는 것을 골라요. 약한 입모양이 든 문제부터 나와요.</p>
        </div>
        <button type="button" onClick={() => navigate('/learn/closure')} className="btn-secondary shrink-0 px-5 py-2.5 text-[15px]">
          문맥 추론 시작
        </button>
      </section>

      {/* 지금 출제되는 유형 — 숙달도 낮은 순 진행바(Figma) */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">지금 출제되는 유형</p>
          <span className="text-[13px] text-ink-muted">숙달도 낮은 순</span>
        </div>
        {targets == null ? (
          <LoadingScreen variant="section" />
        ) : targets.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">약점이 뚜렷하지 않아요. 다양한 유형이 골고루 나와요.</p>
        ) : (
          <div className="mt-4 flex flex-col gap-4">
            {targets.map((t) => {
              const pct = t.mastery == null ? null : Math.round(t.mastery * 100)
              const fill = pct == null ? 'bg-primary-300' : pct < 50 ? 'bg-endless-low' : 'bg-endless-high'  // 낮으면 분홍, 높으면 앰버
              const label = t.demo_syllable ? `${t.name} (${t.demo_syllable})` : t.name
              return (
                <div key={t.viseme_id} className="flex items-center gap-[14px]">
                  <p className="w-[140px] shrink-0 text-[14px] font-bold text-ink sm:w-[160px]">{label}</p>
                  <div className="h-3 min-w-0 flex-1 overflow-hidden rounded-full bg-fill">
                    <div className={`h-3 rounded-full ${fill}`} style={{ width: `${pct ?? 40}%` }} />
                  </div>
                  <p className="w-[44px] shrink-0 text-right text-[13px] font-bold text-ink-muted">{pct == null ? '—' : `${pct}%`}</p>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </AppShell>
  )
}
