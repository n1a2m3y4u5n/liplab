import { useState, useEffect, useMemo } from 'react'
import AvatarVRM from './AvatarVRM'
import TalkerChip from './TalkerChip'
import { CueGlyph } from './CueBadges'
import { curriculumAPI } from '../api'
import { visemeCycleSteps } from '../lib/visemeCycle'
import { applyTalkerTiming, applyTalkerCycle } from '../lib/talkers'
import { applyCoarticulation } from '../lib/coarticulation'
import { recordLateness } from '../lib/frameClock'

/**
 * 입모양만 재생하는 경량 아바타 (오버레이·컨트롤 없음 → 퀴즈에서 정답 미노출).
 *  - frames: [{viseme, duration_ms}] 시퀀스를 반복 재생(단어용).
 *  - visemeId: 단일 그룹이면 neutral(15) ↔ target 반복(입모양 인지용).
 *  - height: 픽셀 높이(기본 300). null이면 인라인 높이를 주지 않는다 — 부모 카드가 반응형 높이를
 *    정할 때(레슨 입모양 카드 모바일 214 / lg 370, Figma 235:45 · 91:22) className="h-full"과 함께 쓴다.
 *  - cueText: 주면 재생 중인 음절의 시각증강 기호(축 J — 기식·긴장·비음)를 입 근처에 겹친다(J-3).
 *    기호 세기는 서버(/api/cues)가 숙달도로 낮춘다(페이딩). 글자는 보이지 않아 정답이 드러나지 않는다.
 *  - cueFocus: true면 학습자의 약한 표적 입모양 음절에만 기호를 남긴다(필요한 순간에만 — /api/cues focus).
 *  - speed: 재생 배속(기본 1). 숙달한 단계의 엔드리스·복습에서 1.25배 '빠른 말'로 쓴다(docs/curriculum-roadmap.md 1-1).
 *  - talker·talkerSeed: 가상 화자(lib/talkers, 계획 2-2). 말 속도·흔들림·동시조음을 프레임에 입히고 입모양 배율을 아바타에 넘긴다.
 *    speed는 그 위에 곱해진다. showTalker가 true면 왼쪽 위에 화자 이름을 작게 보인다.
 *  - flat: true면 3D 캔버스 없이 2D 입모양으로 그린다(여러 명 대화의 저사양 모드, lib/gpuBudget).
 *  - once: true면 프레임을 한 번만 재생하고 중립에서 멈춘다(소리 듣기의 소리+입모양 시행, 소리와 함께 한 번). frames가 바뀌면 다시 한 번.
 *    처음 300ms 중립 뒤 첫 프레임이 나오므로 소리는 300ms 뒤에 튼다(listenAudio.playClip leadMs).
 *  - 선행 동시조음(lib/coarticulation, 플래그 VITE_COART_E): 켜져 있으면 입 안쪽 자음 프레임이 입술을 섞을 모음(coart_v)을 아바타에 넘긴다.
 * LipSyncPlayer3D는 'Viseme N' 오버레이가 있어 퀴즈에 부적합해 별도 컴포넌트로 둔다.
 * 문항이 바뀌어도 key로 다시 마운트하지 않는다. frames가 바뀌면 재생을 처음부터 다시 하고, 다시 마운트하면 캔버스·WebGL
 * 컨텍스트·셰이더·모델 버퍼를 새로 만든다(9/27 측정: 문항마다 컨텍스트가 새로 생기고 첫 그리기까지 0.1~1.1초).
 */
export default function MouthAvatar({ frames: rawFrames, visemeId, height = 300, className = '', cueText = null, cueFocus = false, modelUrl, speed = 1,
  talker = null, talkerSeed = 0, showTalker = true, flat = false, once = false }) {
  const frames = useMemo(() => applyCoarticulation(applyTalkerTiming(rawFrames, talker, talkerSeed)), [rawFrames, talker, talkerSeed])
  const [vid, setVid] = useState(15)
  const [syl, setSyl] = useState(null)      // 재생 중 프레임의 음절 번호(text_index)
  // 이번 입모양의 전환 시간·머무는 시간(ms). AvatarVRM이 이 시간 동안 이징으로 옮긴 뒤 목표에서 멈춘다(lib/visemeTiming, 3D 모션 A·B).
  // 예전에는 넘기지 않아 고정 비율(시상수 약 45ms)로 따라가, 학습자가 읽는 퀴즈 아바타만 전환이 거칠고 짧은 프레임에서 목표에 덜 닿았다.
  const [timing, setTiming] = useState({ t: undefined, d: undefined })
  const [cues, setCues] = useState([])

  useEffect(() => {
    let on = true
    if (!cueText) { setCues([]); return undefined }
    curriculumAPI.getCues(cueText, { focus: cueFocus })
      .then((d) => { if (on) setCues(d.cues || []) })
      .catch(() => { if (on) setCues([]) })
    return () => { on = false }
  }, [cueText, cueFocus])

  useEffect(() => {
    let on = true
    let t
    const k = Number.isFinite(speed) && speed > 0 ? speed : 1   // 배속: 머무는 시간·전환 시간을 k로 나눈다

    if (frames && frames.length) {
      let i = 0
      // 프레임이 예정보다 얼마나 늦게 넘어갔는지 기록만 한다(기기 점검 V20, lib/frameClock). 넘기는 시각은 예전 그대로다
      let dueAt
      const later = (fn, ms) => { dueAt = performance.now() + ms; return setTimeout(fn, ms) }
      const step = () => {
        if (!on) return
        if (Number.isFinite(dueAt)) recordLateness(performance.now() - dueAt)
        const dur = Math.max(frames[i]?.duration_ms || 180, 120) / k
        const tr = frames[i]?.transition_ms
        setVid(frames[i]?.viseme ?? 15)
        setSyl(Number.isInteger(frames[i]?.text_index) ? frames[i].text_index : null)
        setTiming({ t: Number.isFinite(tr) ? tr / k : tr, d: dur, lv: frames[i]?.coart_v })
        i += 1
        if (i >= frames.length) {
          if (once) {   // 한 번만: 마지막 프레임을 다 보인 뒤 중립에서 멈춘다
            t = setTimeout(() => { if (on) { setVid(15); setSyl(null); setTiming({ t: 150, d: 500 }) } }, dur)
            return
          }
          // 한 단어 끝 → 잠깐 중립으로 쉬었다가 반복
          i = 0
          t = setTimeout(() => { setVid(15); setSyl(null); setTiming({ t: 150, d: 500 }); t = later(step, 500) }, dur)
          dueAt = undefined   // 마지막 프레임에서 쉼으로 넘어가는 순간은 재지 않는다(쉼 뒤 첫 프레임은 later가 잰다)
          return
        }
        t = later(step, dur)
      }
      setVid(15)
      setSyl(null)
      setTiming({ t: 150, d: 300 })
      t = later(step, 300)
    } else {
      // 목표 ↔ 중립 반복. 이중모음은 원순 → 개방으로 미끄러지는 움직임(lib/visemeCycle)
      const steps = applyTalkerCycle(visemeCycleSteps(visemeId ?? 15), talker, talkerSeed)
      const cycle = (i) => {
        if (!on) return
        const s = steps[i % steps.length]
        setVid(s.v)
        setTiming({ t: Number.isFinite(s.t) ? s.t / k : s.t, d: s.ms / k })
        t = setTimeout(() => cycle(i + 1), s.ms / k)
      }
      setVid(15)
      setTiming({ t: 150, d: 250 })
      t = setTimeout(() => cycle(0), 250)
    }

    return () => { on = false; clearTimeout(t) }
  }, [frames, visemeId, speed, talker, talkerSeed, once])

  const active = syl != null ? cues.filter((c) => c.syllable_index === syl && (c.strength ?? 1) > 0.05) : []
  return (
    <div className={`relative w-full rounded-2xl overflow-hidden shadow-xl bg-gradient-to-b from-slate-800 to-slate-900 [container-type:size] ${className}`}
         style={height != null ? { height } : undefined}>
      <AvatarVRM visemeId={vid} modelUrl={modelUrl} flat={flat} transitionMs={timing.t} durationMs={timing.d} talker={talker} lipVowel={timing.lv} />
      {showTalker && <TalkerChip talker={talker} />}
      {/* 기호는 오른쪽 입꼬리 옆 — 카메라 세로 화각이 고정이라 입 높이는 캔버스 높이의 약 68%, 입 반폭은 높이의 약 25% */}
      {active.length > 0 && (
        <div className="pointer-events-none absolute left-[calc(50%+30cqh)] top-[68%] flex -translate-y-1/2 gap-1" aria-hidden>
          {active.map((c, j) => (
            <span key={j} style={{ opacity: c.strength ?? 1 }}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/90 shadow-md ring-1 ring-black/5">
              <CueGlyph cue={c.cue} size={16} />
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
