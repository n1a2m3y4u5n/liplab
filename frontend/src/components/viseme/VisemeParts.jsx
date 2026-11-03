import { useState, useEffect } from 'react'
import AvatarVRM from '../AvatarVRM'
import VocalTract from '../VocalTract'
import VocalTractVTL from '../VocalTractVTL'
import { visemeCycleSteps } from '../../lib/visemeCycle'
import { applyTalkerCycle } from '../../lib/talkers'
import TalkerChip from '../TalkerChip'

const VIS_BADGE = {
  high:   { label: '잘 보임',      cls: 'bg-good-tint text-good-text border-good-line' },
  medium: { label: '보통',        cls: 'bg-warn-tint text-warn-text border-warn/40' },
  low:    { label: '거의 안 보임', cls: 'bg-surface-sunken text-ink-muted border-line' },
}

// 최소대립쌍은 승인 콘텐츠 병합으로 100쌍 넘게 불어난다. 학습 화면에서는 전부 나열하는 대신
// '같아 보임(●) 3 + 다르게 보임(○) 2'로 맛보기만 보여준다 — 개념 체감이 목적이고,
// 실제 드릴은 2단계(단어)에서 전량을 쓴다.
const PAIR_PREVIEW_SAME = 3
const PAIR_PREVIEW_DIFF = 2

const pickPairPreview = (pairs = []) => [
  ...pairs.filter((m) => m.same_looking).slice(0, PAIR_PREVIEW_SAME),
  ...pairs.filter((m) => !m.same_looking).slice(0, PAIR_PREVIEW_DIFF),
]

const lessonLabel = (lesson) => {
  const phonemes = lesson?.phonemes?.join(', ')
  return phonemes ? `${lesson.name}(${phonemes})` : lesson?.name || ''
}

// neutral(15) ↔ target 반복 → 입모양이 '만들어지는' 움직임을 보여준다(학습 자료). 투명 두상·성도 단면 토글이 붙는다.
// 퀴즈는 MouthAvatar를 쓴다(QuizPanel).
function VisemeAvatar({ visemeId, height = 300, className = '', talker = null, talkerSeed = 0 }) {
  const [vid, setVid] = useState(15)
  const [tm, setTm] = useState({ t: undefined, d: undefined })   // 이번 입모양의 전환·머무는 시간(ms)
  const [xray, setXray] = useState(false)        // 투명 두상: 피부 반투명 → 혀·치아 노출(계획서 F)
  const [showTract, setShowTract] = useState(false)  // 성도 단면(측면) 도식(계획서 E)
  useEffect(() => {
    let on = true
    let t
    // 목표 ↔ 중립 반복. 이중모음은 원순 → 개방으로 미끄러지는 움직임(lib/visemeCycle)
    const steps = applyTalkerCycle(visemeCycleSteps(visemeId), talker, talkerSeed)
    const step = (i) => {
      if (!on) return
      const s = steps[i % steps.length]
      setVid(s.v)
      setTm({ t: s.t, d: s.ms })
      t = setTimeout(() => step(i + 1), s.ms)
    }
    setVid(15)
    t = setTimeout(() => step(0), 250)
    return () => { on = false; clearTimeout(t) }
  }, [visemeId, talker, talkerSeed])
  return (
    <div className={className}>
      <div className={`relative w-full overflow-hidden rounded-2xl bg-surface-inverse ${height == null ? 'h-full' : ''}`}
           style={height != null ? { height } : undefined}>
        <AvatarVRM visemeId={vid} xray={xray} transitionMs={tm.t} durationMs={tm.d} talker={talker} />
        <TalkerChip talker={talker} />
        {showTract && (
          <div className="absolute bottom-2 right-2 w-36 sm:w-44 bg-surface-inverse/85 border border-ink-muted rounded-xl p-1 backdrop-blur-sm">
            <VocalTract visemeId={vid} vtl />
          </div>
        )}
      </div>
      {/* 안 보이는 조음(혀·치아) 시각화 토글 — 독화 교육 핵심 */}
      <div className="mt-2 flex gap-2">
        <button onClick={() => setXray((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg font-bold transition-colors ${xray ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}
          title="피부를 반투명하게 해 안 보이는 혀·치아를 드러냄">투명 두상</button>
        <button onClick={() => setShowTract((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg font-bold transition-colors ${showTract ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}
          title="옆에서 자른 입 안 그림으로 혀·입술·턱 움직임 보기">성도 옆모습</button>
      </div>
    </div>
  )
}

// 성도 단면(계획서 E-6): 같은 입모양 그룹 안에서 밖으로 안 보이는 차이(혀 높이·앞뒤, 연구개)를
// VocalTractLab으로 미리 계산한 윤곽으로 나란히 보여 준다. 자산은 이 블록이 보일 때만 받는다.
function GroupTract({ group }) {
  const n = group.ids.length
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex items-baseline justify-between gap-2">
        <b className="text-sm text-ink">성도 옆모습</b>
        <span className="text-[10px] text-ink-faint">VocalTractLab으로 미리 계산</span>
      </div>
      <div className={`mt-2 grid gap-3 ${n === 1 ? 'grid-cols-1 max-w-[260px]' : 'grid-cols-2'}`}>
        {group.ids.map((id) => <VocalTractVTL key={id} phoneme={id} caption />)}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-ink-muted">{group.note}</p>
    </div>
  )
}

const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
// 레슨 시작 전 트랙 로딩(§4-10 223:30)을 최소 이만큼은 보인다 — 데이터가 빨리 와도 한 번 번쩍이고 끝나지 않게.
const INTRO_MS = 1000

export { VIS_BADGE, PAIR_PREVIEW_SAME, PAIR_PREVIEW_DIFF, pickPairPreview, lessonLabel, VisemeAvatar, GroupTract, shuffle, INTRO_MS }
