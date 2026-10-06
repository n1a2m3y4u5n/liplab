// 측정 기록(10/6)의 화면 쪽 순수 함수: 숙달 지연 탐침(C16) 끼우는 자리, 레슨별 정신적 노력(C14) 세션 id·척도, 유지 검사(C7) 안내 표시.
// 판정·저장은 서버(backend/mastery_probe.py·mental_effort.py·retention.py)가 한다.
import { plainVisemeLabel } from './visemeLabels.js'

/** 탐침을 끼울 자리: 레슨 가운데 문항을 마친 뒤(12문항이면 6번 뒤). 처음이나 끝에 몰아 두면 '검사 시간'으로 읽히기 쉽다. */
export function probeInsertAfter(lessonLen) {
  const n = Math.max(1, Math.floor(Number(lessonLen) || 0))
  return Math.max(1, Math.floor(n / 2))
}

/** 지금 문항(qNum, 1부터)을 마친 뒤 탐침을 열지. 레슨에서 한 번만 연다. */
export function shouldOpenProbes({ qNum, insertAfter, count, shown }) {
  return !shown && count > 0 && qNum === insertAfter
}

/** 탐침 보기 이름. 1단계(입모양 무리)는 퀴즈와 같은 쉬운 이름('입술 닫힘 (바·마)'), 나머지는 서버가 준 글 그대로. */
export function probeOptionLabel(item, opt) {
  if (item?.kind === 'viseme') return plainVisemeLabel(opt?.viseme_id) || opt?.label || ''
  return opt?.label || ''
}

/** 레슨 세션 id(서버 형식 ^[A-Za-z0-9_-]{6,40}$). 화면이 레슨 끝 화면을 열 때마다 하나 만든다. */
export function newSessionId(random = Math.random, now = Date.now) {
  let tail = ''
  for (let i = 0; i < 10; i += 1) tail += Math.floor(random() * 36).toString(36)
  return `ls-${now().toString(36)}-${tail}`
}

// Paas 9점 정신적 노력 척도의 쉬운 말 기준점(backend/mental_effort.py ANCHORS와 같다)
export const EFFORT_POINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
export const EFFORT_ANCHORS = { 1: '아주 아주 조금', 3: '조금', 5: '보통', 7: '많이', 9: '아주 아주 많이' }

/** 유지 검사 안내를 띄울지: 볼 때(state 'due')이고 오늘 '나중에'를 누르지 않았을 때. */
export function retentionPromptVisible(status, dismissedOn, today) {
  return status?.state === 'due' && dismissedOn !== today
}

/** 기기 날짜(YYYY-MM-DD). '나중에'를 하루 동안 기억하는 키에 쓴다. */
export function localDay(d = new Date()) {
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
