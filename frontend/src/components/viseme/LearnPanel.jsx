import { useState, useMemo, lazy, Suspense } from 'react'
import { useSearchParams } from 'react-router-dom'
import VocalTractSimulator from '../VocalTractSimulator'
import { VISEME_GROUP_VTL } from '../../lib/vtlShapes'
import CueBadges, { CueLegend } from '../CueBadges'
import { plainVisemeLabel } from '../../lib/visemeLabels'
import { VIS_BADGE, pickPairPreview, lessonLabel, VisemeAvatar, GroupTract } from './VisemeParts'
// MediaPipe 번들이 커서 펼칠 때만 로드(초기 번들 보호)
const WebcamMouthCheck = lazy(() => import('../WebcamMouthCheck'))

function LearnPanel({ data }) {
  const { lessons, homophene_clusters, minimal_pairs } = data
  const [params] = useSearchParams()
  const _tv = parseInt(params.get('v'), 10)
  const [sel, setSel] = useState(lessons.find((l) => l.viseme_id === _tv) || lessons[0])
  const pairPreview = useMemo(() => pickPairPreview(minimal_pairs), [minimal_pairs])
  const [showCam, setShowCam] = useState(false)
  const badge = VIS_BADGE[sel.visibility] || VIS_BADGE.medium

  return (
    <div className="space-y-6">
      {/* 10그룹 칩 */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {lessons.map((l) => {
          const b = VIS_BADGE[l.visibility] || VIS_BADGE.medium
          const active = sel.viseme_id === l.viseme_id
          return (
            <button key={l.viseme_id} onClick={() => setSel(l)}
              className={`p-3 rounded-14 border text-center transition-all ${active ? 'border-primary-500 bg-primary-50' : 'border-line bg-white hover:border-primary-300'}`}>
              <div className="text-xs font-bold leading-snug text-ink sm:text-sm">{lessonLabel(l)}</div>
              <div className={`mt-1 inline-block text-[10px] px-1.5 py-0.5 rounded-full border ${b.cls}`}>{b.label}</div>
            </button>
          )
        })}
      </div>

      {/* 상세 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <VisemeAvatar visemeId={sel.viseme_id} />
        </div>
        <div className="card flex flex-col gap-3">
          <div className="flex items-center flex-wrap gap-2">
            <h3 className="text-xl font-bold text-ink">{sel.name}</h3>
            <span className={`text-xs px-2 py-0.5 rounded-full border ${badge.cls}`}>{badge.label}</span>
            {data.anchors?.includes(sel.viseme_id) && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700">닻(뚜렷)</span>
            )}
          </div>
          {/* 퀴즈 보기에 쓰는 쉬운 이름(lib/visemeLabels). 위 전문 이름과 아래 음소 목록은 학습 자료에서만 보인다 */}
          {plainVisemeLabel(sel.viseme_id) && <p className="text-sm font-bold text-ink">{plainVisemeLabel(sel.viseme_id)}</p>}
          <p className="text-sm text-ink-muted">{sel.phonemes.join('  ·  ')}</p>
          <div className="p-3 bg-surface-muted rounded-lg text-sm text-ink"><b>입모양</b> — {sel.look}</div>
          <div className="p-3 bg-warn-tint border border-warn/30 rounded-lg text-sm text-warn-text"><b>독화 포인트</b> — {sel.teach}</div>
          {sel.articulation && (
            <div className="p-3 bg-pastel-sky border border-bookmark-line rounded-lg text-sm text-bookmark-dark">
              <div className="flex items-center gap-1.5 mb-0.5">
                <b>소리 내는 법</b>
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-pastel-sky text-stat-level">{sel.articulation.place}</span>
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-pastel-sky text-stat-level">{sel.articulation.manner}</span>
                {sel.articulation.nasal && <span className="text-[11px] px-1.5 py-0.5 rounded bg-primary-100 text-primary-700">비음</span>}
              </div>
              <span className="text-stat-level">밖에서 안 보이는 혀·목 움직임 — {sel.articulation.guide}</span>
            </div>
          )}
          {VISEME_GROUP_VTL[sel.viseme_id] && <GroupTract group={VISEME_GROUP_VTL[sel.viseme_id]} />}
          <div>
            <p className="text-xs text-ink-faint mb-1">예시 단어 · 안 보이는 소리를 기호로</p>
            <div className="flex flex-wrap items-end gap-2">
              {sel.example_words.map((w) => (
                <CueBadges key={w} text={w} />
              ))}
            </div>
            <div className="mt-2"><CueLegend /></div>
          </div>
        </div>
      </div>

      {/* 웹캠으로 따라하기 (축 D) — 펼칠 때만 MediaPipe 로드 */}
      {showCam ? (
        <Suspense fallback={<div className="card text-sm text-ink-muted">카메라 준비 중…</div>}>
          <WebcamMouthCheck visemeId={sel.viseme_id} visemeName={sel.name} articulationGuide={sel.articulation?.guide} />
        </Suspense>
      ) : (
        <button type="button" onClick={() => setShowCam(true)}
          className="w-full rounded-14 border border-dashed border-line py-3 text-sm font-bold text-ink-muted transition hover:border-primary-300 hover:bg-white">
          웹캠으로 내 입모양 확인하기
        </button>
      )}

      {/* 성도 실험실 (축 E) — 혀 위치↔소리를 귀로 잇는 인터랙티브 조음 교구 */}
      <div className="card">
        <h3 className="text-base font-bold text-ink mb-1">성도 실험실 — 조음과 소리 잇기</h3>
        <p className="text-sm text-ink-muted mb-3">밖에서 안 보이는 <b>혀 위치</b>를 직접 움직이면 소리가 어떻게 바뀌는지 들어봅니다. 모음마다 혀가 어디에 있어야 하는지 귀로 익힙니다.</p>
        <VocalTractSimulator />
      </div>

      {/* 동구형이음 교육 */}
      <div className="card">
        <h3 className="text-base font-bold text-ink mb-1">같아 보이는 입모양 (동구형이음)</h3>
        <p className="text-sm text-ink-muted mb-3">독화의 핵심 — 어떤 소리들은 입모양이 똑같아서 <b>문맥으로 판단</b>해야 합니다.</p>
        <div className="space-y-2">
          {homophene_clusters.map((c) => (
            <div key={c.id} className="p-3 bg-surface-muted rounded-lg text-sm">
              <b className="text-ink">{c.name}</b>
              <span className="text-ink-muted ml-1">
                ({c.viseme_ids.map((id) => lessons.find((l) => l.viseme_id === id)?.name).filter(Boolean).join(', ')})
              </span>
              <p className="text-ink-muted mt-1">{c.note}</p>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <p className="text-xs text-ink-faint mb-1.5">한 소리만 다른 단어 짝 — 같아 보이는(●) / 다르게 보이는(○) 짝</p>
          <div className="flex flex-wrap gap-2">
            {pairPreview.map((m, i) => (
              <span key={i} title={m.note}
                className={`px-2.5 py-1 rounded-lg text-sm border ${m.same_looking ? 'bg-bad-tint border-bad-line text-bad-text' : 'bg-good-tint border-good-line text-good-text'}`}>
                {m.same_looking ? '●' : '○'} {m.a} / {m.b}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default LearnPanel
