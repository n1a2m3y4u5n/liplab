import { useState, useEffect } from 'react'
import AvatarVRM from './AvatarVRM'

/**
 * 입모양만 재생하는 경량 아바타 (오버레이·컨트롤 없음 → 퀴즈에서 정답 미노출).
 *  - frames: [{viseme, duration_ms}] 시퀀스를 반복 재생(단어용).
 *  - visemeId: 단일 그룹이면 neutral(15) ↔ target 반복(입모양 인지용).
 * LipSyncPlayer3D는 'Viseme N' 오버레이가 있어 퀴즈에 부적합해 별도 컴포넌트로 둔다.
 */
export default function MouthAvatar({ frames, visemeId, height = 300 }) {
  const [vid, setVid] = useState(15)

  useEffect(() => {
    let on = true
    let t

    if (frames && frames.length) {
      let i = 0
      const step = () => {
        if (!on) return
        setVid(frames[i]?.viseme ?? 15)
        const dur = Math.max(frames[i]?.duration_ms || 180, 120)
        i += 1
        if (i >= frames.length) {
          // 한 단어 끝 → 잠깐 중립으로 쉬었다가 반복
          i = 0
          t = setTimeout(() => { setVid(15); t = setTimeout(step, 500) }, dur)
          return
        }
        t = setTimeout(step, dur)
      }
      setVid(15)
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

  return (
    <div className="w-full rounded-2xl overflow-hidden shadow-xl bg-gradient-to-b from-slate-800 to-slate-900"
         style={{ height }}>
      <AvatarVRM visemeId={vid} />
    </div>
  )
}
