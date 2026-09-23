import { useState, useEffect } from 'react'
import AvatarVRM from './AvatarVRM'
import { CueGlyph } from './CueBadges'
import { curriculumAPI } from '../api'

/**
 * 입모양만 재생하는 경량 아바타 (오버레이·컨트롤 없음 → 퀴즈에서 정답 미노출).
 *  - frames: [{viseme, duration_ms}] 시퀀스를 반복 재생(단어용).
 *  - visemeId: 단일 그룹이면 neutral(15) ↔ target 반복(입모양 인지용).
 *  - height: 픽셀 높이(기본 300). null이면 인라인 높이를 주지 않는다 — 부모 카드가 반응형 높이를
 *    정할 때(레슨 입모양 카드 모바일 214 / lg 370, Figma 235:45 · 91:22) className="h-full"과 함께 쓴다.
 *  - cueText: 주면 재생 중인 음절의 시각증강 기호(축 J — 기식·긴장·비음)를 입 근처에 겹친다(J-3).
 *    기호 세기는 서버(/api/cues)가 숙달도로 낮춘다(페이딩). 글자는 보이지 않아 정답이 드러나지 않는다.
 *  - cueFocus: true면 학습자의 약한 표적 입모양 음절에만 기호를 남긴다(필요한 순간에만 — /api/cues focus).
 * LipSyncPlayer3D는 'Viseme N' 오버레이가 있어 퀴즈에 부적합해 별도 컴포넌트로 둔다.
 */
export default function MouthAvatar({ frames, visemeId, height = 300, className = '', cueText = null, cueFocus = false }) {
  const [vid, setVid] = useState(15)
  const [syl, setSyl] = useState(null)      // 재생 중 프레임의 음절 번호(text_index)
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

    if (frames && frames.length) {
      let i = 0
      const step = () => {
        if (!on) return
        setVid(frames[i]?.viseme ?? 15)
        setSyl(Number.isInteger(frames[i]?.text_index) ? frames[i].text_index : null)
        const dur = Math.max(frames[i]?.duration_ms || 180, 120)
        i += 1
        if (i >= frames.length) {
          // 한 단어 끝 → 잠깐 중립으로 쉬었다가 반복
          i = 0
          t = setTimeout(() => { setVid(15); setSyl(null); t = setTimeout(step, 500) }, dur)
          return
        }
        t = setTimeout(step, dur)
      }
      setVid(15)
      setSyl(null)
      t = setTimeout(step, 300)
    } else {
      const target = visemeId ?? 15
      const cycle = (toTarget) => {
        if (!on) return
        setVid(toTarget ? target : 15)
        t = setTimeout(() => cycle(!toTarget), toTarget ? 850 : 450)
      }
      setVid(15)
      t = setTimeout(() => cycle(true), 250)
    }

    return () => { on = false; clearTimeout(t) }
  }, [frames, visemeId])

  const active = syl != null ? cues.filter((c) => c.syllable_index === syl && (c.strength ?? 1) > 0.05) : []
  return (
    <div className={`relative w-full rounded-2xl overflow-hidden shadow-xl bg-gradient-to-b from-slate-800 to-slate-900 [container-type:size] ${className}`}
         style={height != null ? { height } : undefined}>
      <AvatarVRM visemeId={vid} />
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
