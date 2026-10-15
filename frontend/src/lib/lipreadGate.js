/**
 * 웹캠 '기계 확인'(LipReadCheck, 축 D)을 어디에 보일지 정하는 빌드 플래그(2026-10-15, V1 판정 뒤 준비).
 *
 * VITE_LIPREAD_CHECK
 *   'on'(기본, 지금과 같음)  단어 레슨 결과 화면에 늘 보인다.
 *   'research'              연구 빌드(VITE_LIPLAB_RESEARCH=1)에서만 보이고, 문구를 '연구 기능'으로 바꾼다.
 *   'off'                   보이지 않는다.
 * 근거: 처음 보는 사람의 입모양에서 4지선다가 우연 수준이다(docs/d-bench-v2.md 8절, docs/lipread-v1-2026-10.md).
 * 기본값을 'research'로 바꾸는 것은 제안으로만 둔다(배포 판단은 사용자).
 */
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}

export function lipreadCheckMode(env = ENV) {
  const v = String(env.VITE_LIPREAD_CHECK || 'on').trim().toLowerCase()
  return v === 'research' || v === 'off' ? v : 'on'
}

/** 이 빌드에서 칸을 보일지. research 모드는 연구 빌드에서만 보인다. */
export function lipreadCheckVisible(env = ENV) {
  const m = lipreadCheckMode(env)
  if (m === 'off') return false
  if (m === 'research') return env.VITE_LIPLAB_RESEARCH === '1'
  return true
}

/** 머리글 꼬리표와 결과 아래 안내 문구. */
export function lipreadCheckCopy(env = ENV) {
  if (lipreadCheckMode(env) === 'research') {
    return {
      tag: '(연구 기능)',
      note: '연구용 기능이에요. 처음 보는 사람의 입모양은 아직 거의 읽지 못해서(네 개 중 하나를 고르는 문제에서 어림짐작과 비슷해요), 결과를 내 입모양 점수로 보지 마세요.',
    }
  }
  return {
    tag: '(축 D · 실험)',
    note: '소형 실증 모델이라 자주 틀립니다. 입모양만으로 단어를 읽는 어려움을 보여주는 실험이에요.',
  }
}
