import test from 'node:test'
import assert from 'node:assert/strict'
import { initTrack, track, flushTrack, trackRoute, requestTrackedMedia, startUsage, endUsage } from './track.js'

test('이용 기록: 인증·끄기·50개 묶음·민감 필드·장치 오류·beacon', async () => {
  const original = { fetch: globalThis.fetch, window: globalThis.window, document: globalThis.document, navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'), interval: globalThis.setInterval }
  let token = null, enabled = true
  const sent = [], beacons = [], listeners = {}
  try {
    globalThis.window = { location: { pathname: '/learn/word' }, addEventListener: (k, fn) => { listeners[k] = fn } }
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
