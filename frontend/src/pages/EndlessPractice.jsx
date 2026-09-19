import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { curriculumAPI } from '../api'

/**
 * 엔드리스 학습 (Figma 리디자인 09) — 약한 유형만 골라 무한 연습.
 * 숙달도 낮은 음소/입모양이 계속 출제된다. 엔진은 단어 레슨(약점 가중 표집·무한 루프)을 재사용.
 * 지금 출제될 약점 유형은 curriculumAPI.getNext()의 추천에서 읽어 미리 보여준다.
 */
const VIS_NAME = {
  1: '양순음', 2: '개방모음', 3: '전설모음', 4: '원순모음', 5: '중설모음',
  6: '치경음', 7: '연구개음', 8: '성문음', 9: '이중모음', 10: '경구개음',
}

export default function EndlessPractice() {
  const navigate = useNavigate()
  const [weak, setWeak] = useState(null)
  useEffect(() => {
    curriculumAPI.getNext()
      .then((d) => setWeak(d?.weak_visemes || d?.target_visemes || d?.visemes || []))
      .catch(() => setWeak([]))
  }, [])

  return (
    <AppShell active="practice" title="엔드리스 학습" description="틀렸던 유형이 계속 나와요">
      {/* 엔드리스 시작 — 그라데이션 카드 */}
      <section className="relative w-full overflow-hidden rounded-[22px] border-2 border-b-[5px] border-[#6d3fc4] p-6 sm:p-8"
        style={{ backgroundImage: 'linear-gradient(160deg, #a78bfa 0%, #7d53de 71%)' }}>
        <div className="flex items-center gap-5">
          <img src="/ui/mascot.svg" alt="" className="hidden h-20 w-20 shrink-0 sm:block" />
          <div className="flex-1 text-white">
            <p className="text-[22px] font-bold tracking-[-0.44px]">약한 유형만 골라서 무한 연습</p>
            <p className="mt-1.5 text-[14px] leading-relaxed opacity-90">숙달도가 낮은 음소가 계속 출제돼요. 원할 때 멈출 수 있어요.</p>
            <button type="button" onClick={() => navigate('/learn/word')}
              className="mt-4 inline-flex items-center gap-2 rounded-[14px] border-2 border-b-4 border-white/60 bg-white px-6 py-3 text-[15px] font-bold text-primary-600">
              시작하기 →
            </button>
          </div>
        </div>
      </section>

      {/* 지금 출제되는 유형 */}
      <section className="card-flat w-full">
        <div className="flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">지금 출제되는 유형</p>
          <span className="text-[13px] text-ink-muted">숙달도 낮은 순</span>
        </div>
        {weak == null ? (
          <p className="py-6 text-center text-sm text-ink-muted">불러오는 중…</p>
        ) : weak.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">약점이 뚜렷하지 않아요. 다양한 유형이 골고루 나와요.</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {weak.map((v) => (
              <span key={v} className="rounded-full bg-primary-100 px-3 py-1.5 text-[13px] font-bold text-primary-700">
                {VIS_NAME[v] || v}
              </span>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  )
}
