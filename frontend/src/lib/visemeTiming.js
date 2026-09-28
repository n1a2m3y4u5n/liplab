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

// 약점 기반 적응 템포(CLAUDE.md 트랙 2 백로그, 9/28): 학습자가 자주 틀리는 입모양 프레임만 조금 천천히 보여 준다. 말 속도가 느릴수록
// 독화가 쉬워지므로, 약한 입모양에서만 머무는 시간과 전환 시간을 늘려 그 모양을 눈에 익힐 여유를 준다. 연습 화면에만 쓰고 배치검사·
// 사전사후 검사(표준 검사)에는 쓰지 않는다.
export const WEAK_SLOW_FACTOR = 1.35

/** frames 가운데 입모양이 weak(Set)에 든 프레임의 duration_ms·transition_ms를 factor배로 늘린 새 배열. weak가 비면 그대로. */
export function slowWeakFrames(frames, weak, factor = WEAK_SLOW_FACTOR) {
  if (!Array.isArray(frames) || !weak || weak.size === 0) return frames
  return frames.map((f) => {
    if (!f || !weak.has(f.viseme)) return f
    const out = { ...f, slowed: true }
    if (Number.isFinite(f.duration_ms)) out.duration_ms = Math.round(f.duration_ms * factor)
    if (Number.isFinite(f.transition_ms)) out.transition_ms = Math.round(f.transition_ms * factor)
    return out
  })
}

/** /api/statistics의 weak_visemes(지식추적 순)에서 늦출 입모양: 숙달도 0.7 미만이고 5번 이상 본 것 상위 3개. */
export function pickSlowVisemes(weakVisemes, k = 3) {
  const ids = (weakVisemes || [])
    .filter((w) => Number.isFinite(w?.viseme_id) && (w.attempts ?? 0) >= 5 && (w.mastery ?? 1) < 0.7)
    .slice(0, k)
    .map((w) => w.viseme_id)
  return new Set(ids)
}

// 숙달에 싣는 실제 재생 속도(docs/mastery-ewma.md 7절): 학습자가 고른 속도 × 적응 감속으로 늘어난 만큼(원래 길이 합 / 보인 길이 합).
// 1.0 미만이면 감속해 본 답이라 서버가 숙달 추정에 성공 0.5로 넣는다. 길이를 모르면 학습자 속도만 쓴다.
export function effectiveSpeed(original, shown, learnerSpeed = 1) {
  const sum = (fs) => (Array.isArray(fs) ? fs.reduce((s, f) => s + (Number.isFinite(f?.duration_ms) ? f.duration_ms : 0), 0) : 0)
  const a = sum(original)
  const b = sum(shown)
  const ratio = a > 0 && b > 0 ? a / b : 1
  const s = Number.isFinite(learnerSpeed) && learnerSpeed > 0 ? learnerSpeed : 1
  return Math.round(s * ratio * 1000) / 1000
}

// 숙달한 단계의 엔드리스·복습에서 여는 '빠른 말' 배속(docs/curriculum-roadmap.md 1-1)
export const FAST_SPEECH_SPEED = 1.25
