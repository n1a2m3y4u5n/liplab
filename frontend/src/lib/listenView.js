/**
 * 소리 듣기 화면(pages/ListeningPractice.jsx)의 순수 계산. 재생은 lib/listenAudio.js, 소리 계산은 lib/listenMix.js.
 *  - 키보드: 스페이스 = 듣기, 숫자 = 보기 고르기, Enter = 확인·계속하기(listenKeyAction)
 *  - 재생 상태 표시: 예상 재생 길이(playbackMs)와 상태 문구(soundStatusText)
 *  - 표시 문구: dB, 걸린 시간, 수준 변화, 검사 앞 연습 문장 진행
 */

const TYPING_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT'])
const CONTROL_TAGS = new Set(['BUTTON', 'A', 'SUMMARY'])

/**
 * 키 하나를 화면 동작으로 바꾼다. 반환: {type:'play'} | {type:'pick', index} | {type:'enter'} | null.
 * ev: {key, code, repeat, altKey, ctrlKey, metaKey, targetTag, editable}
 * ctx: {canPlay, optionCount, canPick, canEnter}
 *  - 글을 쓰는 칸(입력·선택 상자·편집 영역)에서는 아무것도 가로채지 않는다(Enter는 폼 제출로 확인된다).
 *  - 버튼에 초점이 있으면 스페이스·Enter는 그 버튼이 받는다(키보드 사용자의 기본 동작을 지킨다). 숫자는 버튼 위에서도 고른다.
 *  - 길게 눌러 반복되는 키와 조합키(⌘·Ctrl·Alt)는 무시한다.
 */
export function listenKeyAction(ev, ctx = {}) {
  if (!ev || ev.repeat || ev.altKey || ev.ctrlKey || ev.metaKey) return null
  const tag = String(ev.targetTag || '').toUpperCase()
  if (TYPING_TAGS.has(tag) || ev.editable) return null
  const onControl = CONTROL_TAGS.has(tag)
  const isSpace = ev.key === ' ' || ev.key === 'Spacebar' || ev.code === 'Space'
  if (isSpace) return !onControl && ctx.canPlay ? { type: 'play' } : null
  if (ev.key === 'Enter') return !onControl && ctx.canEnter ? { type: 'enter' } : null
  if (/^[1-9]$/.test(ev.key || '')) {
    const index = Number(ev.key) - 1
    return ctx.canPick && index < (ctx.optionCount || 0) ? { type: 'pick', index } : null
  }
  return null
}

/**
 * 소리 하나를 트는 데 걸릴 시간(ms). 상태 막대가 이 시간 동안 찬다(실제 끝남은 재생 약속이 알린다).
 * opts: {leadMs, rate, noise, snrDb}. 소음을 섞으면 앞 0.5초(leadMs 기본)와 뒤 약 0.45초가 소음만이다(listenAudio.playClip).
 */
export function playbackMs(clip, opts = {}) {
  const dur = Number(clip?.duration_ms) || (clip?.buffer?.duration ? clip.buffer.duration * 1000 : 0) || 1400
  const noisy = !!opts.noise && opts.snrDb != null
  const lead = Number.isFinite(opts.leadMs) ? opts.leadMs : noisy ? 500 : 0
  const rate = Number(opts.rate) > 0 ? Number(opts.rate) : 1
  return Math.round(lead + dur / rate + (noisy ? 450 : 0))
}

/** 여러 소리를 차례로 틀 때의 전체 시간(사이 쉼 gapMs). steps: [{clip, opts} | {silenceMs}] */
export function sequenceMs(steps, gapMs = 600) {
  const list = steps || []
  const each = list.map((s) => (s?.silenceMs != null ? s.silenceMs : playbackMs(s?.clip, s?.opts)))
  return each.reduce((a, b) => a + b, 0) + Math.max(0, list.length - 1) * gapMs
}

/**
 * 소리 상태 문구. phase: 'loading'(소리 받는 중) | 'idle'(아직 안 들음) | 'playing' | 'done'(끝남) | 'missing'(준비 전) | 'limit'(듣기 횟수 다 씀)
 * part·parts: 두 소리를 차례로 틀 때 지금 몇 번째인지.
 */
export function soundStatusText(phase, { part = 1, parts = 1 } = {}) {
  if (phase === 'loading') return '소리를 준비하고 있어요'
  if (phase === 'missing') return '이 소리는 아직 준비되지 않았어요'
  if (phase === 'playing') {
    if (parts === 2) return part === 1 ? '첫 번째 소리가 나오고 있어요' : '두 번째 소리가 나오고 있어요'
    return '소리가 나오고 있어요'
  }
  if (phase === 'done') return '소리가 끝났어요'
  if (phase === 'limit') return '들을 수 있는 횟수를 다 썼어요'
  return '버튼을 누르면 소리가 나와요'
}

/** dB 값 표시(+3 dB, -2.5 dB, 0 dB). 값이 없으면 '–'. */
export function fmtDb(v) {
  if (v == null || !Number.isFinite(Number(v))) return '–'
  const x = Math.round(Number(v) * 10) / 10
  return `${x > 0 ? '+' : ''}${x} dB`
}

/** 걸린 시간(초) → '3분 5초' · '45초'. */
export function fmtDuration(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0))
  const m = Math.floor(s / 60)
  return m ? `${m}분 ${s % 60}초` : `${s}초`
}

/** 수준 변화 문구. 같으면 null. */
export function levelChangeText(before, after, levels) {
  if (before == null || after == null || before === after) return null
  return `${after > before ? '수준이 올라갔어요' : '수준이 내려갔어요'} · 지금 ${after} / ${levels}`
}

/**
 * 소음 속 듣기 검사의 문항 k(0부터)가 연습인지, 몇 번째인지. items: test/start 응답의 items(맨 앞 n_practice개가 연습).
 * 반환: {practice, no, total, nPractice}. practice면 연습 no / 연습 수, 아니면 검사 no / 검사 문장 수.
 */
export function testStep(items, k) {
  const list = items || []
  const nPrac = list.filter((it) => it?.practice).length
  const it = list[k]
  if (!it) return { practice: false, no: Math.max(0, list.length - nPrac), total: list.length - nPrac, nPractice: nPrac }
  if (it.practice) return { practice: true, no: k + 1, total: nPrac, nPractice: nPrac }
  return { practice: false, no: k - nPrac + 1, total: list.length - nPrac, nPractice: nPrac }
}
