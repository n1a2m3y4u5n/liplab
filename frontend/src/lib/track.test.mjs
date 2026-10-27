import test from 'node:test'
import assert from 'node:assert/strict'
import { initTrack, track, flushTrack, trackRoute, requestTrackedMedia, startUsage, endUsage } from './track.js'

test('이용 기록: 인증·끄기·50개 묶음·민감 필드·장치 오류·beacon', async () => {
  const original = { fetch: globalThis.fetch, window: globalThis.window, document: globalThis.document, navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'), interval: globalThis.setInterval }
  let token = null, enabled = true
  const sent = [], beacons = [], listeners = {}, sessionEnds = []
  try {
    globalThis.window = { location: { pathname: '/learn/word' }, addEventListener: (k, fn) => { listeners[k] = fn }, dispatchEvent: e => sessionEnds.push(e.type) }
    globalThis.document = { addEventListener() {} }
    globalThis.setInterval = () => 0
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { sendBeacon: (...args) => { beacons.push(args); return true }, mediaDevices: { getUserMedia: async () => { throw Object.assign(Error('private@example.com'), { name: 'NotAllowedError' }) } } } })
    globalThis.fetch = async (url, options) => {
      if (options) sent.push(JSON.parse(options.body))
      return { ok: true, json: async () => ({ enabled }) }
    }
    initTrack(() => token)
    await new Promise(resolve => setImmediate(resolve))
    track('route'); await flushTrack(); assert.equal(sent.length, 0)
    token = 'first-user'
    trackRoute('/learn/word?answer=private')
    startUsage('lesson', 'word'); endUsage(true)
    assert.deepEqual(sessionEnds, ['liplab:session-complete'])
    startUsage('lesson', 'word'); endUsage(false)
    assert.equal(sessionEnds.length, 1)
    for (let i = 0; i < 55; i++) track('control', { action: 'volume', email: 'private@example.com', answer: 'private' })
    await assert.rejects(requestTrackedMedia({ video: true }), { name: 'NotAllowedError' })
    await flushTrack()
    assert.equal(sent[0].events.length, 50)
    assert.ok(sent[0].events.some(e => e.event === 'lesson_complete'))
    assert.ok(sent[0].events.every(e => e.route === '/learn/word'))
    assert.ok(!JSON.stringify(sent).includes('private'))
    await flushTrack(true); assert.equal(beacons.length, 1)
    track('route'); token = 'second-user'; await flushTrack(); assert.equal(sent.length, 1)
    track('route'); enabled = false; await flushTrack()
    track('route'); await flushTrack(); assert.equal(sent.length, 2)
  } finally {
    globalThis.fetch = original.fetch; globalThis.window = original.window; globalThis.document = original.document; globalThis.setInterval = original.interval
    if (original.navigator) Object.defineProperty(globalThis, 'navigator', original.navigator)
    else delete globalThis.navigator
  }
})

test('기기 UUID는 계정·재접속 뒤에도 유지하고 접속 UUID는 페이지마다 새로 만든다', async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  const storage = new Map()
  try {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v) } })
    const first = await import('./track.js?session=first')
    const second = await import('./track.js?session=second')
    const a = first.usageHeaders(), b = second.usageHeaders()
    assert.match(a['X-Usage-Device-ID'], /^[a-f0-9-]{36}$/)
    assert.equal(a['X-Usage-Device-ID'], b['X-Usage-Device-ID'])
    assert.notEqual(a['X-Usage-Session-ID'], b['X-Usage-Session-ID'])
    assert.deepEqual(a, first.usageHeaders())
  } finally {
    if (original) Object.defineProperty(globalThis, 'localStorage', original)
    else delete globalThis.localStorage
  }
})

test('로그인 전 허용 기록은 로그인 뒤에도 익명으로 전송하며 기기·접속 식별자는 유지한다', async () => {
  const original = { fetch: globalThis.fetch, window: globalThis.window, document: globalThis.document, interval: globalThis.setInterval }
  let token = null
  const sent = []
  try {
    globalThis.window = { location: { pathname: '/' }, addEventListener() {} }
    globalThis.document = { addEventListener() {} }
    globalThis.setInterval = () => 0
    globalThis.fetch = async (url, options) => {
      if (options) sent.push({ ...options, payload: JSON.parse(options.body) })
      return { ok: true, json: async () => ({ enabled: true }) }
    }
    const t = await import('./track.js?session=anonymous')
    t.initTrack(() => token)
    await new Promise(resolve => setImmediate(resolve))
    t.trackRoute('/login')
    t.track('signup_view')
    t.track('demo_start')
    t.track('frontend_error', { message: 'TypeError' })
    t.track('lesson_start')
    const before = t.usageHeaders()
    token = 'account-one'
    t.track('lesson_start')
    await t.flushTrack()
    assert.equal(sent.length, 2)
    const anonymous = sent[0], authenticated = sent[1]
    assert.deepEqual(anonymous.payload.events.map(e => e.event), ['landing_view', 'login_view', 'signup_view', 'demo_start'])
    assert.equal(anonymous.headers.Authorization, undefined)
    assert.equal(anonymous.payload.token, undefined)
    assert.equal(anonymous.credentials, 'omit')
    assert.equal(authenticated.headers.Authorization, 'Bearer account-one')
    assert.deepEqual(authenticated.payload.events.map(e => e.event), ['lesson_start'])
    for (const request of sent) for (const event of request.payload.events) {
      assert.equal(event.device_id, before['X-Usage-Device-ID'])
      assert.equal(event.anon_session_id, before['X-Usage-Session-ID'])
    }
    token = null
    assert.deepEqual(t.usageHeaders(), before)
    t.track('demo_start')
    token = 'account-one'
    t.startUsage('lesson', 'old-account')
    token = 'account-two'
    t.endUsage(false)
    t.track('route')
    await t.flushTrack()
    assert.deepEqual(t.usageHeaders(), before)
    assert.equal(sent[2].payload.token, undefined)
    assert.equal(sent[3].payload.token, 'account-two')
    assert.deepEqual(sent[3].payload.events.map(e => e.event), ['route'])
    token = null
    for (let i = 0; i < 13; i++) t.track('demo_start')
    await t.flushTrack()
    assert.equal(sent[4].payload.events.length, 10)
    assert.equal(sent[4].headers.Authorization, undefined)
    token = 'account-three'
    await t.flushTrack()
    assert.equal(sent[5].payload.events.length, 3)
    assert.equal(sent[5].payload.token, undefined)
    assert.equal(sent[5].headers.Authorization, undefined)
    await t.flushTrack()
    assert.equal(sent.length, 6)
  } finally {
    Object.assign(globalThis, { fetch: original.fetch, window: original.window, document: original.document, setInterval: original.interval })
  }
})
