// 말하기 억양 판정. 음높이 방향을 보는 연습(운율 '올리기'·'내리기')에서만 판정하고, 기준은 서버
// (backend/speak_curriculum.py _score_prosody)와 같다: 뒤 30% 평균이 앞 30% 평균보다 15Hz 이상 높으면(내리기는 낮으면) 통과.
// 발성(길게 '아—')과 크기·길이 연습은 음높이가 고른 게 자연스러워 억양을 지적하지 않는다. 예전에는 모든 지표 모드에서
// 억양 폭이 25Hz 미만이면 '끝을 올리거나 내려보세요'라고 했고, 폭만 봐서 올리기 연습에서 끝을 내려도 '잘 살아있어요'가 떴다.
export const TONE_STEP_HZ = 15

/** 억양 방향을 판정할 연습이면 'rise'|'fall', 아니면 null. */
export function toneDirection(mode, drill) {
  return mode === 'prosody' && (drill === 'rise' || drill === 'fall') ? drill : null
}

/** 방향 연습에서 끝이 목표 방향으로 15Hz 이상 움직이지 않았으면 true. 음높이를 못 쟀으면(0) 판정하지 않는다. */
export function toneMissed(summary, dir) {
  if (!dir || !summary?.pitchStart || !summary?.pitchEnd) return false
  const d = summary.pitchEnd - summary.pitchStart
  return dir === 'rise' ? d < TONE_STEP_HZ : -d < TONE_STEP_HZ
}
