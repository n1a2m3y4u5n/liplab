// 말하기 억양 판정. 음높이 방향을 보는 연습(운율 '올리기'·'내리기')에서만 판정하고, 기준은 서버
// (backend/speak_curriculum.py _score_prosody)와 같다: 끝 음높이가 시작 음높이보다 1.65반음 이상 높으면(내리기는 낮으면) 통과.
// 시작·끝 음높이는 riseFallTone이 이상값을 걸러 낸다.
// 반음(로그 척도)이라 목소리 높이와 상관없이 같은 기준이다(예전 15Hz는 남성 2.0반음, 여성 1.1반음이었다).
// 발성(길게 '아—')과 크기·길이 연습은 음높이가 고른 게 자연스러워 억양을 지적하지 않는다. 예전에는 모든 지표 모드에서
// 억양 폭이 25Hz 미만이면 '끝을 올리거나 내려보세요'라고 했고, 폭만 봐서 올리기 연습에서 끝을 내려도 '잘 살아있어요'가 떴다.
export const TONE_STEP_ST = 1.65

export const semitones = (from, to) => (from > 0 && to > 0 ? 12 * Math.log2(to / from) : 0)

/** 억양 방향을 판정할 연습이면 'rise'|'fall', 아니면 null. */
export function toneDirection(mode, drill) {
  return mode === 'prosody' && (drill === 'rise' || drill === 'fall') ? drill : null
}

/** 방향 연습에서 끝이 목표 방향으로 1.65반음 이상 움직이지 않았으면 true. 음높이를 못 쟀으면(0) 판정하지 않는다. */
export function toneMissed(summary, dir) {
  if (!dir || !summary?.pitchStart || !summary?.pitchEnd) return false
  const d = semitones(summary.pitchStart, summary.pitchEnd)
  return dir === 'rise' ? d < TONE_STEP_ST : -d < TONE_STEP_ST
}

const median = (a) => {
  const s = [...a].sort((x, y) => x - y)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** 문장 끝 억양용 기준·끝 음높이(Hz). 유성 프레임 음높이 목록 ps(약 67ms 간격)를 3프레임 중앙값으로 다듬어(옥타브 튐 제거)
 * 전체 중앙값(ref)과 마지막 3프레임 중앙값(final)을 준다. 서버 speak_curriculum.sentence_direction이 둘의 반음 차로 판정한다.
 * 예전 앞 30% 대 뒤 30% 평균은 마지막 음절의 상승을 앞 음절과 섞어 묻었다(docs/sentence-intonation.md). 4프레임 미만이면 0. */
export function finalTone(ps) {
  if (!ps || ps.length < 4) return { ref: 0, final: 0 }
  const q = ps.map((_, i) => median(ps.slice(Math.max(0, i - 1), i + 2)))
  return { ref: Math.round(median(q)), final: Math.round(median(q.slice(-3))) }
}

// 운율 올리기·내리기용 시작·끝 음높이. 예전에는 유성 프레임 앞 30% 평균과 뒤 30% 평균을 그대로 비교해, 200Hz로 평평하게 낸 '아'
// 끝에 옥타브 튐 한 프레임(400Hz)만 있어도 '올리기' 100점, 끝에 반 옥타브 아래로 잘못 잡힌 두 프레임이면 '내리기' 합격이었다.
// 5단계 finalTone처럼 중앙값 필터로 튐을 거르고, 소리가 끝나며 갈라지는 마지막 약 100ms를 빼고, 유성 프레임이 모자라면 판정하지 않는다.
// 필터는 5프레임(연속 두 프레임 튐까지 제거, 한 방향으로 오르거나 내리는 곡선은 그대로 둔다)이고, 시작은 앞 30% 중앙값,
// 끝은 마지막 3프레임 중앙값이다(끝 음절 상승을 앞 구간과 섞어 묻지 않도록, docs/sentence-intonation.md).
export const TONE_TAIL_DROP_S = 0.1
export const TONE_MIN_FRAMES = 6
export const TONE_STEP_S = 1 / 15   // 녹음 루프의 음높이 간격(약 67ms). trace에 시간이 없을 때만 쓴다.

/** trace: [{t(초), hz}] 녹음 루프 표본(hz가 없으면 무성) 또는 유성 음높이 배열. {start, end, n}(Hz, n = 판정에 쓴 유성 프레임 수).
 * 유성 프레임이 TONE_MIN_FRAMES 미만이면 start·end는 0이다. */
export function riseFallTone(trace) {
  const pts = (trace || [])
    .map((p, i) => (typeof p === 'number' ? { t: i * TONE_STEP_S, hz: p } : p))
    .filter((p) => p && p.hz > 0 && Number.isFinite(p.t))
  const hz = pts.map((p) => p.hz)
  const tEnd = pts.length ? pts[pts.length - 1].t : 0
  // 필터를 먼저 걸고(잘라 낼 끝 프레임도 이웃으로 써서 경계 튐까지 거른다) 끝 약 100ms를 뺀다
  const q = hz.map((_, i) => median(hz.slice(Math.max(0, i - 2), i + 3)))
    .filter((_, i) => pts[i].t <= tEnd - TONE_TAIL_DROP_S + 1e-6)
  const n = q.length
  if (n < TONE_MIN_FRAMES) return { start: 0, end: 0, n }
  const head = q.slice(0, Math.max(1, Math.round(n * 0.3)))
  return { start: Math.round(median(head)), end: Math.round(median(q.slice(-3))), n }
}
