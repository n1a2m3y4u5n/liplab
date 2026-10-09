/**
 * 소리 듣기 흐름의 순수 계산. 화면은 components/listen/, 재생은 lib/listenAudio.js, 소리 계산은 lib/listenMix.js.
 * 과제 컴포넌트(소리 구별·낱말 고르기·문장·대화)는 단계 레슨, 연습 모드, 오늘의 듣기, 복습에서 함께 쓴다. 들어온 곳마다 다른 것은
 * 묶음 끝 버튼, 답에 붙는 연습 표시(practice_mode), 이어지는 방식(엔드리스·블록)뿐이라 그 차이를 여기서 정한다.
 *  - 묶음 끝 버튼: completeActions(단계 레슨), practiceActions(연습 모드)
 *  - 연습 모드: PRACTICE_MODES, practiceQuery(주소 → API 질의), practiceTask(응답 → 과제 종류), normalizeStair
 *  - 오늘의 듣기: blockData(블록 n문항), todayTotals(15분 목표 대비 요약)
 *  - 소리 교실: lipDiffers(입모양이 다른 짝인가), alternate(A-B 번갈아 듣기 순서)
 *  - 분석 탭: listenOverview(분석 요약 또는 결과 요약 → 듣기 칸 세 값)
 */

export const pct = (c, n) => (n ? `${Math.round((c / n) * 100)}%` : '–')
export const skippedNote = (n) => (n > 0 ? `소리를 받지 못한 ${n}문제는 세지 않고 넘겼어요.` : null)

/**
 * 단계 레슨 묶음 끝의 버튼. 0단계(소리 확인)는 소리 구별로, 이번에 숙달했으면 다음 단계로, 아니면 한 묶음 더.
 * 반환: {primary, secondary} (각 {label, onClick})
 */
export function completeActions({ stage, mastered, reload, onExit, onStage, exitLabel = '학습 화면으로' }) {
  const secondary = { label: exitLabel, onClick: onExit }
  if (stage === 0) return { primary: { label: '소리 구별 하러 가기', onClick: () => onStage(1) }, secondary }
  if (mastered && stage < 5) return { primary: { label: '다음 단계로', onClick: () => onStage(stage + 1) }, secondary }
  return { primary: { label: '한 묶음 더 하기', onClick: reload }, secondary }
}

/**
 * 연습 모드(연습 탭 '소리 듣기' 묶음). 답은 practice_mode를 붙여 보내고 단계 숙달에는 넣지 않는다(백엔드 계약,
 * docs/listen-integration-api-2026-10.md). choose: 시작 전에 고르는 것(없으면 바로 시작), endless: 묶음이 끝나면 다음 묶음을 저절로 받는다.
 */
export const PRACTICE_MODES = {
  contrast: { title: '소리 짝 집중 연습', desc: '헷갈리는 소리 짝만 골라 들어요', choose: 'kind', chooseAgain: '다른 소리 짝 고르기' },
  dictation: { title: '받아쓰기', desc: '문장을 듣고 쓰기를 원하는 만큼 이어 해요', endless: true },
  noise_endless: { title: '소음 속 듣기', desc: '맞히면 소음이 커지고 놓치면 작아져요', endless: true },
  scenario: { title: '상황별 대화 듣기', desc: '병원·가게 같은 장소를 골라 들어요', choose: 'place', chooseAgain: '다른 장소 고르기' },
  conditions: { title: '듣기 조건 연습', desc: '전화·울리는 방·잡음 속 말소리를 들어요', choose: 'condition', chooseAgain: '다른 조건 고르기' },
}
export const PRACTICE_KEYS = Object.keys(PRACTICE_MODES)

/**
 * 연습 모드 묶음 끝의 버튼: 한 묶음 더 / 다른 것 고르기(고르는 모드) 또는 연습 탭으로.
 * 반환: {primary, secondary}
 */
export function practiceActions({ mode, reload, onChoose, onExit }) {
  const m = PRACTICE_MODES[mode]
  return {
    primary: { label: '한 묶음 더 하기', onClick: reload },
    secondary: m?.chooseAgain && onChoose ? { label: m.chooseAgain, onClick: onChoose } : { label: '연습 탭으로', onClick: onExit },
  }
}

/** 주소 질의 → 고른 것의 이름(위 제목 줄). 소리 짝 종류 이름은 목록(kinds: [{kind, label}])에서 찾는다. */
export function choiceLabel(mode, query, kinds = []) {
  if (mode === 'contrast') {
    if (query?.weak) return '자주 헷갈린 짝'
    return (kinds || []).find((k) => k.kind === query?.kind)?.label || null
  }
  if (mode === 'scenario') return query?.place || null
  if (mode === 'conditions') {
    const c = CONDITIONS.find((x) => x.key === query?.condition)
    if (!c) return null
    if (c.key !== 'noise') return c.label
    return NOISE_TYPES.find((n) => n.key === query.noise)?.label || c.label
  }
  return null
}

/** 장소 목록 응답(문자열 또는 {key|place, label, n}) → [{key, label, n}] */
export function normalizePlaces(list) {
  const src = Array.isArray(list) ? list : Array.isArray(list?.places) ? list.places : []
  return src.map((p) => (typeof p === 'string' ? { key: p, label: p, n: null }
    : { key: p?.key || p?.place || p?.label, label: p?.label || p?.place || p?.key, n: p?.n ?? null })).filter((p) => p.key)
}

/** 연습 모드 목록 응답([{key, available, reason}]) → {key: {available, reason}}. 응답이 없거나 깨졌으면 빈 객체(모두 '알 수 없음'). */
export function modeAvailability(list) {
  const out = {}
  for (const m of Array.isArray(list) ? list : []) {
    if (m && typeof m.key === 'string') out[m.key] = { available: m.available !== false, reason: m.reason || null }
  }
  return out
}

/**
 * 주소의 질의(URLSearchParams 또는 객체) → 연습 API 질의와 '고를 것이 남았는가'.
 *  - contrast: kind(소리 짝 종류), contrast(대조 그대로, 'onset:ㅂ:ㅍ' 꼴) 또는 weak=1(내가 자주 헷갈린 짝)
 *  - scenario: place
 *  - conditions: condition(phone | room | noise), noise일 때 noise(잡음 종류)
 * 반환: {ready, query}. ready가 false면 고르는 화면을 먼저 보인다.
 */
export const CONDITIONS = [
  { key: 'phone', label: '전화', desc: '말소리의 높고 낮은 쪽이 잘려 좁게 들려요' },
  { key: 'room', label: '울리는 방', desc: '벽에 부딪힌 소리가 뒤따라와 끝이 번져요' },
  { key: 'noise', label: '잡음 속', desc: '다른 사람 말소리나 웅웅 소리가 함께 나요' },
]
export const NOISE_TYPES = [
  { key: 'babble', label: '여러 사람 소리' },
  { key: 'talker1_f', label: '여자 한 명 말소리' },
  { key: 'talker1_m', label: '남자 한 명 말소리' },
  { key: 'ssn', label: '웅웅 소리' },
]
const COND_KEYS = new Set(CONDITIONS.map((c) => c.key))
const NOISE_KEYS = new Set(NOISE_TYPES.map((n) => n.key))

export function practiceQuery(mode, params) {
  const get = (k) => (typeof params?.get === 'function' ? params.get(k) : params?.[k]) || null
  if (mode === 'contrast') {
    if (get('weak') === '1') return { ready: true, query: { weak: 1 } }
    const contrast = get('contrast')
    if (contrast) return { ready: true, query: { contrast } }
    const kind = get('kind')
    return kind ? { ready: true, query: { kind } } : { ready: false, query: {} }
  }
  if (mode === 'scenario') {
    const place = get('place')
    return place ? { ready: true, query: { place } } : { ready: false, query: {} }
  }
  if (mode === 'conditions') {
    const condition = get('condition')
    if (!COND_KEYS.has(condition)) return { ready: false, query: {} }
    if (condition !== 'noise') return { ready: true, query: { condition } }
    const noise = NOISE_KEYS.has(get('noise')) ? get('noise') : 'babble'
    return { ready: true, query: { condition, noise } }
  }
  return { ready: PRACTICE_KEYS.includes(mode), query: {} }
}

/**
 * 화면 질의 → 연습 API 질의(docs/listen-integration-api-2026-10.md 1절). 소리 짝은 contrast(종류는 'kind:<종류>', 자주 헷갈린 짝은 비움),
 * 듣기 조건은 cond·noise, 장면은 place.
 */
export function practiceApiParams(mode, query = {}) {
  if (mode === 'contrast') {
    if (query.weak) return {}
    if (query.contrast) return { contrast: query.contrast }
    return query.kind ? { contrast: `kind:${query.kind}` } : {}
  }
  if (mode === 'conditions') return query.condition ? { cond: query.condition, ...(query.noise ? { noise: query.noise } : {}) } : {}
  if (mode === 'scenario') return query.place ? { place: query.place } : {}
  return {}
}

/**
 * 소리 짝 연습 문항(같다·다르다 type 'ax' · 낱말 고르기 type 'word'가 섞여 옴) → 과제별 묶음 [{task, items}]. 처음 나온 순서대로 종류를 묶는다.
 * type이 없으면 문항 모양으로 정한다.
 */
export function contrastSegments(items) {
  const order = []
  const by = {}
  for (const it of items || []) {
    const t = it?.type === 'word' || (it?.type == null && it?.target != null && Array.isArray(it?.options)) ? 'word_id'
      : it?.type === 'ax' || (it?.first != null && it?.second != null) ? 'ax' : null
    if (!t) continue
    if (!by[t]) { by[t] = []; order.push(t) }
    by[t].push(it)
  }
  return order.map((task) => ({ task, items: by[task] }))
}

/**
 * 연습 응답이 어느 과제 화면으로 풀리는가. 응답의 task(또는 mode가 과제 이름이면 그것)를 먼저 보고, 없으면 첫 문항 모양으로 정한다:
 * first·second → 'ax'(같다·다르다), target·options → 'word_id', line → 'convo', text → 소음 연습이면 'noise', 아니면 'sentence'.
 * 정할 수 없으면 null.
 */
const TASKS = new Set(['ax', 'word_id', 'sentence', 'noise', 'convo'])
export function practiceTask(mode, res) {
  for (const t of [res?.task, res?.mode]) if (TASKS.has(t)) return t
  const it = res?.items?.[0]
  if (!it) return null
  if (it.first != null && it.second != null) return 'ax'
  if (it.target != null && Array.isArray(it.options)) return 'word_id'
  if (it.line != null) return 'convo'
  if (it.text != null) return mode === 'noise_endless' ? 'noise' : 'sentence'
  return null
}

/**
 * 소음 계단 응답을 화면이 쓰는 꼴 {조건: {next_db, ...}} 로 맞춘다. 단계 응답은 {ao, av}, 소음 속 듣기 연습은 {practice_ao}이고,
 * 계단 하나({next_db, ...})만 오면 ao로 둔다. 없으면 null.
 */
export function normalizeStair(stair) {
  if (!stair || typeof stair !== 'object') return null
  if (stair.next_db != null) return { ao: stair }
  // {ao, av}(4단계) 또는 {practice_ao}(소음 속 듣기 연습)처럼 조건 이름 → 계단
  const keys = Object.keys(stair).filter((k) => stair[k] && typeof stair[k] === 'object' && 'next_db' in stair[k])
  return keys.length ? stair : null
}

/**
 * 소음 계단 흐름의 점 좌표(소음 속 듣기 연습의 작은 그림). trace: [{snr, correct}] 오래된 순, 최근 max개만 쓴다.
 * 세로는 SNR(위가 큰 SNR = 소음이 작음), 범위가 6 dB보다 좁으면 6 dB로 넓혀 작은 흔들림을 과장하지 않는다.
 * 반환: [{x, y, correct}] (0 ≤ x ≤ w, 0 ≤ y ≤ h)
 */
export function stairPoints(trace, w = 160, h = 36, max = 16) {
  const list = (trace || []).filter((t) => Number.isFinite(Number(t?.snr))).slice(-max)
  if (!list.length) return []
  const vals = list.map((t) => Number(t.snr))
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (hi - lo < 6) { const mid = (lo + hi) / 2; lo = mid - 3; hi = mid + 3 }
  const step = list.length > 1 ? w / (list.length - 1) : 0
  return list.map((t, i) => ({
    x: Math.round((list.length > 1 ? i * step : w / 2) * 10) / 10,
    y: Math.round((h - ((Number(t.snr) - lo) / (hi - lo)) * h) * 10) / 10,
    correct: !!t.correct,
  }))
}

/**
 * 오늘의 듣기 블록 하나의 문항. 단계 응답에서 앞의 n문항만 쓴다(n이 문항보다 많으면 있는 만큼). 소리 확인(0단계)은 점검 순서를
 * 그대로 쓴다(소리 없는 차례가 섞여 있어 자르면 점검이 깨진다).
 */
export function blockData(data, n) {
  if (!data) return data
  if (data.mode === 'ling' || !Array.isArray(data.items)) return data
  const k = Number.isFinite(Number(n)) && Number(n) > 0 ? Number(n) : data.items.length
  return { ...data, items: data.items.slice(0, k) }
}

/**
 * 오늘의 듣기 요약. results: 블록 결과([{n, c, elapsed(초)}]), done: 오늘 서버 기록({n, minutes}, 끝난 뒤 다시 받은 값이 있으면 그것),
 * before: 시작 전 서버 기록. 서버 분이 있으면 그것을 오늘 분으로 쓰고, 없으면 시작 전 분 + 이번 회기 걸린 시간으로 어림한다.
 * 반환: {minutes, sessionMinutes, n, c, accuracy, goalPct, reached, left}. left는 목표까지 남은 분(보이는 내림 분 기준, 0 이상).
 */
export function todayTotals(results, { done = null, before = null, targetMin = 15 } = {}) {
  const list = results || []
  const n = list.reduce((a, r) => a + (r?.n || 0), 0)
  const c = list.reduce((a, r) => a + (r?.c || 0), 0)
  const sec = list.reduce((a, r) => a + (r?.elapsed || 0), 0)
  const sessionMinutes = Math.round(sec / 6) / 10
  const server = Number.isFinite(done?.minutes) ? done.minutes : null
  const minutes = server != null ? Math.round(server * 10) / 10
    : Math.round(((Number.isFinite(before?.minutes) ? before.minutes : 0) + sessionMinutes) * 10) / 10
  const goal = Number(targetMin) > 0 ? Number(targetMin) : 15
  return { minutes, sessionMinutes, n, c, accuracy: n ? c / n : null, goalPct: Math.min(100, Math.round((minutes / goal) * 100)), reached: minutes >= goal,
    left: Math.max(0, goal - goalMinutes(minutes)) }
}

/** 분 표시: 0.4 → '1분 미만', 6.24 → '6분'. */
export function fmtMinutes(m) {
  const v = Number(m)
  if (!Number.isFinite(v) || v <= 0) return '0분'
  if (v < 1) return '1분 미만'
  return `${Math.round(v)}분`
}

/**
 * 15분 목표와 견주는 오늘 분(정수). 과제 '소리 듣기 15분'(backend daily_tasks.progress)과 같이 내림한다: 14.6 → 14.
 * 예전에는 화면이 반올림해 14.6분이면 '15 / 15분'인데 과제는 14 / 15(미달)였다.
 */
export function goalMinutes(m) {
  const v = Number(m)
  return Number.isFinite(v) && v > 0 ? Math.floor(v) : 0
}

/** 목표 대비 분 표시(내림): 0.4 → '1분 미만', 14.6 → '14분'. */
export function fmtGoalMinutes(m) {
  const v = Number(m)
  if (!Number.isFinite(v) || v <= 0) return '0분'
  if (v < 1) return '1분 미만'
  return `${goalMinutes(v)}분`
}

/**
 * 소리 짝의 입모양이 다른가(소리 교실 표시). 서버가 짝이나 종류에 표시를 주면 그것을 쓰고(짝 lip_same, 종류 lip 'same'·'differs', 'mixed'는 모름),
 * 없으면 두 말의 입모양 프레임(/api/viseme)을 비교한다. 전환 프레임(11~13)과 이어지는 같은 입모양은 하나로 본다.
 * 반환: true(다름) | false(같음) | null(모름)
 */
export function lipDiffers(pair, kind, frames = null) {
  for (const src of [pair, kind]) {
    if (!src) continue
    if (typeof src.lip_differs === 'boolean') return src.lip_differs
    if (typeof src.lip_same === 'boolean') return !src.lip_same
    if (typeof src.same_mouth === 'boolean') return !src.same_mouth
    if (src.lip === 'differs' || src.lip === 'same') return src.lip === 'differs'
  }
  if (!frames || !frames.a || !frames.b) return null
  const seq = (fs) => {
    const out = []
    for (const f of fs || []) {
      const v = Number(f?.viseme)
      if (!Number.isFinite(v) || (v >= 11 && v <= 13)) continue
      if (out[out.length - 1] !== v) out.push(v)
    }
    return out.join(',')
  }
  const a = seq(frames.a)
  const b = seq(frames.b)
  if (!a || !b) return null
  return a !== b
}

/**
 * 소리 교실 짝(A·B)의 소리를 받지 못했을 때. a·b는 useClip 상태({state, reason}). 이유(lib/listenAudio.loadClipResult)마다 글을 달리하고,
 * 서버에 아직 없는 소리(not_prepared)가 아니면 다시 받기를 보인다. 예전에는 연결이 끊겨도 '아직 준비되지 않았어요'만 적고 다시 받을 길이 없었다.
 * 반환: {missing, reason, text, canRetry}
 */
const PAIR_MISSING_TEXT = {
  not_prepared: '이 짝의 소리는 아직 준비되지 않았어요',
  network: '인터넷 연결이 끊겨 소리를 받지 못했어요',
  decode: '이 브라우저에서 소리 파일을 열지 못했어요',
}
export function pairMissing(a, b) {
  const m = [a, b].find((c) => c?.state === 'missing')
  if (!m) return { missing: false, reason: null, text: null, canRetry: false }
  // 둘 다 못 받았으면 다시 받을 수 있는 이유를 먼저 본다(한쪽만 서버에 없어도 다른 쪽은 다시 받으면 될 수 있다)
  const reasons = [a, b].filter((c) => c?.state === 'missing').map((c) => c.reason || 'not_prepared')
  const reason = reasons.find((r) => r !== 'not_prepared') || 'not_prepared'
  return { missing: true, reason, text: PAIR_MISSING_TEXT[reason] || PAIR_MISSING_TEXT.not_prepared, canRetry: reason !== 'not_prepared' }
}

/** 번갈아 듣기 순서: alternate('A', 'B', 2) → ['A', 'B', 'A', 'B']. */
export function alternate(a, b, times = 2) {
  const out = []
  for (let i = 0; i < Math.max(1, times); i += 1) out.push(a, b)
  return out
}

/**
 * 분석 탭 듣기 칸. ov: /api/analysis/overview의 listen(최근 검사 역치, 없으면 훈련 역치 · 7일 분 · 소리 구별 정답률, 계약 6절),
 * summary: /api/listen/summary(overview에 listen 칸이 아예 없는 예전 서버일 때만 대신).
 * 반환: {srt, weekMinutes, axAccuracy, has} (값을 모르면 null). has는 하나라도 기록이 있는가.
 */
export function listenOverview(ov, summary = null) {
  const l = ov?.listen || null
  const num = (v) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v))
  let srt = null
  let weekMinutes = null
  let axAccuracy = null
  if (l) {
    srt = num(l.test_srt_db ?? l.training_srt_db ?? l.srt_db)
    weekMinutes = num(l.week_minutes ?? l.minutes_week ?? l.minutes)
    axAccuracy = num(l.ax_accuracy ?? l.discrimination_accuracy ?? l.accuracy)
  } else if (summary) {
    const tests = (summary.tests || []).filter((t) => t?.srt_db != null)
    srt = num(summary.training?.srt_ao_db) ?? (tests.length ? num(tests[tests.length - 1].srt_db) : null)
    const days = summary.days || []
    weekMinutes = days.some((d) => Number.isFinite(d?.minutes)) ? Math.round(days.reduce((a, d) => a + (d.minutes || 0), 0)) : null
    const kinds = summary.ax_kinds || []
    const n = kinds.reduce((a, k) => a + (k.n || 0), 0)
    axAccuracy = n ? kinds.reduce((a, k) => a + (k.correct || 0), 0) / n : null
  }
  return { srt, weekMinutes, axAccuracy, has: srt != null || (weekMinutes || 0) > 0 || axAccuracy != null }
}

/** 과제 이름(블록·전환 화면). 단계 응답의 mode 기준. */
export const TASK_TITLE = { ling: '소리 확인', ax: '소리 구별', word_id: '낱말 고르기', sentence: '문장 알아듣기', noise: '소음 속 듣기', convo: '대화 듣기' }

/** 받침에 맞는 조사: josa('낱말 고르기', '을', '를') → '낱말 고르기를'. 한글이 아니면 받침 없음으로 본다. */
export function josa(word, withFinal, withoutFinal) {
  const s = String(word || '')
  const code = s.charCodeAt(s.length - 1) - 0xac00
  const has = code >= 0 && code <= 11171 && code % 28 !== 0
  return `${s}${has ? withFinal : withoutFinal}`
}

/** Ling 6소리 이름. */
export const LING_LABEL = { m: '음', u: '우', a: '아', i: '이', sh: '쉬', s: '스' }

/**
 * 소리 확인(Ling) 결과 안내. summary: /api/listen/ling 응답의 summary({heard, missed, dropped, reliable, false_alarms}).
 * 반환: {sub, notes}. notes에는 false가 섞여 있어 화면이 filter(Boolean)으로 거른다.
 */
export function lingNotes(summary) {
  const s = summary || {}
  const heard = s.heard || []
  const missed = s.missed || []
  const dropped = s.dropped || []
  return {
    sub: missed.length === 0 ? '여섯 소리가 모두 들렸어요.' : `여섯 소리 중 ${heard.length}개가 들렸어요.`,
    notes: [
      dropped.length > 0 && `지난번에 들리던 ${dropped.map((x) => LING_LABEL[x]).join('·')} 소리가 오늘은 안 들렸어요. 배터리와 기기 상태를 확인해 보세요. 계속 안 들리면 청능사나 병원에 알려요.`,
      !s.reliable && `소리가 없을 때도 '들렸어요'를 ${s.false_alarms}번 눌렀어요. 다음에는 확실히 들릴 때만 눌러 보세요.`,
      missed.length > 0 && dropped.length === 0 && '안 들린 소리가 있어도 괜찮아요. 남은 청력에 맞춰 다음 단계에서 연습해요.',
    ],
  }
}
