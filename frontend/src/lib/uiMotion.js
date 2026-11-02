// 표현 전용 규격. 검사·자극 제시·응답 대기에는 적용하지 않는다.
export const UI_MOTION = Object.freeze({
  duration: 0.18,
  ease: [0.22, 1, 0.36, 1],
  celebration: 0.28,
})

export function entranceMotion(reduced = false, kind = 'card') {
  if (reduced) return { initial: false, animate: { opacity: 1, y: 0, scale: 1 }, transition: { duration: 0 } }
  return {
    initial: { opacity: 0, y: kind === 'page' ? 6 : 4, scale: kind === 'complete' ? 0.98 : 1 },
    animate: { opacity: 1, y: 0, scale: 1 },
    transition: { duration: kind === 'complete' ? UI_MOTION.celebration : UI_MOTION.duration, ease: UI_MOTION.ease },
  }
}
