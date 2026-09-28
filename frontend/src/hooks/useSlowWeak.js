import { useEffect, useMemo, useState } from 'react'
import { learningAPI } from '../api'
import { pickSlowVisemes, slowWeakFrames } from '../lib/visemeTiming'

// 약한 입모양 집합은 세션에 한 번만 받아 여러 화면이 나눠 쓴다(연습 화면 전용, lib/visemeTiming의 약점 기반 적응 템포).
let cached = null
function loadWeak() {
  if (!cached) {
    cached = learningAPI.getStatistics()
      .then((s) => pickSlowVisemes(s?.weak_visemes))
      .catch(() => { cached = null; return new Set() })
  }
  return cached
}

/** frames를 약한 입모양만 천천히 보이게 바꿔 돌려준다. 약점을 받기 전이나 실패하면 원래 frames. */
export default function useSlowWeak(frames) {
  const [weak, setWeak] = useState(null)
  useEffect(() => {
    let alive = true
    loadWeak().then((w) => { if (alive) setWeak(w) })
    return () => { alive = false }
  }, [])
  return useMemo(() => slowWeakFrames(frames, weak), [frames, weak])
}
