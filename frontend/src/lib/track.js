// 이용 기록은 메모리에만 모으며 실패가 학습을 막지 않게 한다.
let getToken = () => null, enabled = null, configured = false, pending = []
let device = '', session = '', route = '/', active = null, lastView = ''
const publicEvents = new Set(['landing_view', 'login_view', 'signup_view', 'demo_start'])
const DEVICE_KEY = 'liplab_usage_device_id'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const n = Math.floor(Math.random() * 16)
    return (c === 'x' ? n : (n & 3) | 8).toString(16)
  })
}
export function usageHeaders() {
  try {
    if (!session) session = newId()
    if (!device) {
      try { device = globalThis.localStorage?.getItem(DEVICE_KEY) || '' } catch { /* 저장소 차단 */ }
      if (!UUID.test(device)) {
        device = newId()
        try { globalThis.localStorage?.setItem(DEVICE_KEY, device) } catch { /* 탭 메모리로 유지 */ }
      }
    }
    return { 'X-Usage-Device-ID': device, 'X-Usage-Session-ID': session }
  } catch { return {} }
}
const allowed = new Set(['duration_ms', 'stage', 'lesson_id', 'action', 'value', 'error_kind', 'message'])
export function track(event, props = {}) {
  try {
    const token = getToken()
    if (enabled === false || (!token && !publicEvents.has(event))) return
    if (event.endsWith('_view') && publicEvents.has(event)) {
      const view = `${token || ''}:${route}:${event}`
      if (lastView === view) return
      lastView = view
    }
    const headers = usageHeaders()
    const clean = {}
    for (const [k, v] of Object.entries(props)) if (allowed.has(k) && ['number', 'boolean', 'string'].includes(typeof v)) clean[k] = typeof v === 'string' ? v.slice(0, 80) : v
    pending.push({ token: token || null, item: { event, route, track: route.includes('listen') ? 'listen' : route.includes('speak') ? 'speak' : 'read', device_id: headers['X-Usage-Device-ID'], anon_session_id: headers['X-Usage-Session-ID'], ts: new Date().toISOString(), props: clean, app_version: '1.0.0' } })
    pending = pending.slice(-100)
  } catch { /* 기록 실패는 무시 */ }
}
export async function flushTrack(beacon = false) {
  try {
    const token = getToken()
    if (enabled !== true) { if (enabled === false) pending = []; return }
    // 로그인 전 기록은 익명 자격으로 보내고, 이전 계정의 대기 기록은 다음 계정으로 넘기지 않는다.
    pending = pending.filter(entry => entry.token === null || entry.token === token)
    const groups = [null, ...(token ? [token] : [])].map(credential => {
      const batch = pending.filter(entry => entry.token === credential).slice(0, credential ? 50 : 10)
      const selected = new Set(batch)
      pending = pending.filter(entry => !selected.has(entry))
      return { credential, events: batch.map(entry => entry.item) }
    })
    for (const { credential, events } of groups) {
      if (!events.length || !enabled) continue
      const body = JSON.stringify({ events, ...(credential ? { token: credential } : {}) })
      if (beacon && navigator.sendBeacon?.('/api/events', new Blob([body], { type: 'application/json' }))) continue
      const response = await fetch('/api/events', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json', ...usageHeaders(), ...(credential ? { Authorization: `Bearer ${credential}` } : {}) }, body, keepalive: true })
      if (response.ok && (await response.json()).enabled === false) { enabled = false; pending = [] }
    }
  } catch { /* 재전송하지 않아 메모리와 트래픽을 제한 */ }
}
export function startUsage(kind = 'lesson', id = '') {
  try {
    endUsage(false)
    active = { kind, id, at: Date.now(), token: getToken() || null }
    track(`${kind}_start`, { lesson_id: String(id) })
  } catch { /* 기록 실패는 무시 */ }
}
export function endUsage(complete = false) {
  try {
    if (!active) return
    const old = active; active = null
    if (old.token !== (getToken() || null)) return
    track(`${old.kind}_${complete ? 'complete' : 'interrupt'}`, { lesson_id: String(old.id), duration_ms: Date.now() - old.at })
  } catch { /* 기록 실패는 무시 */ }
}
export function trackRoute(path) {
  try {
    endUsage(false)
    route = path.split('?')[0].slice(0, 160)
    if (route === '/' || route === '/about') track('landing_view')
    else if (route === '/signup') track('signup_view')
    else if (route === '/login') track('login_view')
    track('route')
    track('track_enter')
    if (/learn|practice|review|analysis|tasks|listen/.test(route)) track('feature_open', { action: route })
    if (/learn\//.test(route)) track('stage_enter', { stage: route.split('/').pop() })
  } catch { /* 기록 실패는 무시 */ }
}
export async function requestTrackedMedia(constraints) {
  const event = constraints.video ? 'webcam' : 'recording'
  track(`${event}_start`)
  try { return await navigator.mediaDevices.getUserMedia(constraints) }
  catch (err) { track(`${event}_failure`, { error_kind: errorKind(err) }); throw err }
}
export function errorKind(err) {
  return ['NotAllowedError', 'NotFoundError', 'NotReadableError', 'AbortError', 'SecurityError', 'RecordingError', 'TypeError', 'RangeError', 'SyntaxError'].includes(err?.name) ? err.name : 'Error'
}
export function initTrack(tokenReader) {
  try {
    getToken = tokenReader
    if (configured || typeof window === 'undefined') return
    configured = true
    trackRoute(window.location.pathname)
    fetch('/api/events/status').then(r => r.json()).then(r => { enabled = r.enabled === true; if (!enabled) pending = [] }).catch(() => { enabled = false; pending = [] })
    setInterval(() => { void flushTrack() }, 10000)
    window.addEventListener('pagehide', () => { endUsage(false); void flushTrack(true) })
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') void flushTrack(true) })
    window.addEventListener('error', e => track('frontend_error', { error_kind: errorKind(e.error), message: errorKind(e.error) }))
    window.addEventListener('unhandledrejection', e => track('frontend_error', { error_kind: errorKind(e.reason), message: errorKind(e.reason) }))
    document.addEventListener('click', e => {
      try {
        const button = e.target.closest?.('button, [role="button"]')
        if (!button) return
        const label = button.getAttribute('aria-label') || button.textContent || ''
        const action = /가이드/.test(label) ? 'guide' : /안내|도움말|설명/.test(label) || label.trim() === 'i' ? 'info' : /글자|Aa/.test(label) ? 'font_size' : /소리|볼륨|음량/.test(label) ? 'volume' : null
        if (action) track('control', { action })
      } catch { /* 기록 실패는 무시 */ }
    }, true)
    document.addEventListener('change', e => {
      try {
        const label = `${e.target.getAttribute?.('aria-label') || ''} ${e.target.id || ''}`
        if (/volume|sound|소리|음량|볼륨/i.test(label)) track('control', { action: 'volume' })
      } catch { /* 기록 실패는 무시 */ }
    }, true)
  } catch { /* 기록 실패는 무시 */ }
}
