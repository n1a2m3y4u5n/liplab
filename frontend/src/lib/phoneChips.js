/**
 * 말하기 결과의 소리별 칩(S2 음소 피드백 신뢰도 지도, docs/phoneme-feedback-reliability-2026-10.md).
 *
 * 서버가 음소마다 reliable을 붙여 보내면(acoustic_dgop.reliability_map) 믿을 만한 소리만 초록·주황·빨강으로 확정해 칠하고,
 * 나머지(믿을 근거가 부족한 소리, 문장 끝 음절)는 색 없는 회색 '참고' 칩으로 둔다. 표가 없는 서버(예전 응답)는 예전처럼 모든 칩을
 * 색으로 칠하고 전체를 참고로 안내한다(S14 카파 0.39).
 */
import { scoreLevel, scoreTone } from './scoreTone.js'

// 참고 칩: 중립 회색. 색 체계(초록·주황·빨강 + 회색)를 늘리지 않고 은은하게 둔다.
const REFERENCE = { level: 'reference', text: 'text-ink-faint', chip: 'border-line bg-surface-muted text-ink-faint', color: 'var(--ink-faint)' }

/** 칩 표시 값(0~100): Math.round(dgop × 100). */
export const phoneValue = (p) => Math.round((p?.dgop ?? 0) * 100)

/** 음소 하나의 칩 색. reliable === false면 참고(회색), 그 밖(true 또는 표 없음)은 점수 색. */
export function phoneTone(p) {
  if (p && p.reliable === false) return REFERENCE
  return scoreTone(phoneValue(p), 'phone')
}

/**
 * 칩 묶음 보기. map: 서버가 신뢰도 표를 썼는가. sure: 확정으로 칠하는 칩 수, sureGood: 그중 초록 수.
 * note: 칩 아래 안내 한 줄.
 */
export function phoneChipView(phones, reliabilityMap = false) {
  const list = Array.isArray(phones) ? phones : []
  const map = !!reliabilityMap && list.some((p) => p && p.reliable != null)
  const sureList = map ? list.filter((p) => p.reliable) : list
  const sureGood = sureList.filter((p) => scoreLevel(phoneValue(p), 'phone') === 'good').length
  const note = !list.length ? null
    : !map ? '소리별 색은 참고용이에요. 같은 말을 다시 해도 색이 바뀔 수 있어요.'
      : sureList.length ? '색이 있는 소리만 확정이에요. 회색 소리는 참고로만 보세요.'
        : '이번 문장의 소리는 모두 참고로만 보세요.'
  return { map, sure: sureList.length, sureGood, note, title: map ? '소리별 발음 정확도' : '소리별 발음 정확도(참고)' }
}
