// 말하기 소리 단서(S7 말 빠르기) 화면 계산. 값과 판정은 서버(backend/speak_cues.rate_cue)가 내고, 여기서는 막대 위치와 문구만 정한다.
// 근거: docs/speak-visual-cues.md. 608 감음신경성 대 538 정상 문장 AUC 0.863이지만 사람 유창성 평가와의 상관은 아직 재지 않아 '참고'로 보인다.
// 분광그림은 보이지 않고 지표 하나만 보인다(계획 9절).

export const RATE_AXIS = [0, 9]   // 막대 눈금(초당 음절). 538 문장 10~90백분위(4.1~6.8)가 가운데쯤 오게 둔다

const clampPct = (v, [lo, hi]) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))

/** sound_cue → 막대 그림과 문구. 알 수 없는 단서나 값이 없으면 null(아무것도 그리지 않는다). */
export function rateCueView(cue) {
  if (!cue || cue.kind !== 'rate' || typeof cue.value !== 'number' || !Array.isArray(cue.range)) return null
  const [lo, hi] = cue.range
  return {
    title: `${cue.label || '말 빠르기'}${cue.reference ? ' · 참고' : ''}`,
    valueText: `초당 ${cue.value.toFixed(1)}음절`,
    markerPct: clampPct(cue.value, RATE_AXIS),
    bandLeftPct: clampPct(lo, RATE_AXIS),
    bandWidthPct: clampPct(hi, RATE_AXIS) - clampPct(lo, RATE_AXIS),
    slow: !!cue.slow,
    message: cue.slow ? cue.message : null,
    note: `색 띠는 정상 화자 낭독 문장의 가운데 80%(초당 ${lo.toFixed(1)}~${hi.toFixed(1)}음절)예요. 짧은 문장은 값이 흔들릴 수 있어요.`,
  }
}
