/**
 * 텍스트 입모양 재생의 시간 기반 전환(CLAUDE.md 3D 모션 A·B, 7/13 ee5366f 설계를 지금 아바타에 다시 옮김).
 *
 * 엔진(/api/viseme)은 프레임마다 입모양(viseme), 머무는 시간(duration_ms), 앞 입모양에서 넘어오는 시간(transition_ms)을 준다.
 * 예전에는 이 시간을 쓰지 않고 매 화면 고정 비율로 따라가서(시상수 약 45ms), 짧은 프레임이나 빠른 재생(1.5·2배)에서는
 * 목표 입모양에 닿기 전에 다음 프레임으로 넘어갔다(2배속 40ms 프레임이면 약 59%까지만 감).
 * 이제 전환을 transition_ms 동안(프레임 길이의 60%를 넘지 않게, 재생 속도로 나눔) ease-in-out으로 옮긴 뒤 목표에서 멈춘다.
 */

/** easeInOutCubic: 시작과 끝을 부드럽게(입술이 스르륵 열리고 닫힌다). t는 0~1. */
export function easeInOutCubic(t) {
  const x = Math.max(0, Math.min(1, t))
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}

export const MIN_TRANSITION_MS = 16      // 한 화면(60Hz)보다 짧게는 옮기지 않는다
export const MAX_TRANSITION_SHARE = 0.6  // 전환은 프레임 길이의 60% 안에 끝낸다(나머지는 목표 입모양 유지)

/** 이번 프레임의 전환 시간(ms, 실제 경과 기준). 값이 없으면 null(호출부가 예전 방식으로 따라간다). */
export function transitionTime(transitionMs, durationMs, speed = 1) {
  if (!Number.isFinite(transitionMs)) return null
  const s = speed > 0 ? speed : 1
  const cap = Number.isFinite(durationMs) && durationMs > 0 ? durationMs * MAX_TRANSITION_SHARE : transitionMs
  return Math.max(MIN_TRANSITION_MS, Math.min(transitionMs, cap)) / s
}

/** 전환 진행률(0~1, 이징 적용). elapsedMs는 이번 프레임이 시작된 뒤 흐른 시간. */
export function transitionProgress(elapsedMs, transitionMs, durationMs, speed = 1) {
  const t = transitionTime(transitionMs, durationMs, speed)
  if (t == null) return null
  return easeInOutCubic(elapsedMs / t)
}
