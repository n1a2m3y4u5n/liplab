import test from 'node:test'
import assert from 'node:assert/strict'
import { startRecorder } from './speakRecorder.js'
import { mediaErrorMessage } from './mediaError.js'

test('녹음기 미지원·생성 실패를 삼키지 않는다', () => {
  for (const Recorder of [null, class { constructor() { throw Error('unsupported') } }]) {
    assert.throws(() => startRecorder({}, () => {}, () => {}, Recorder), { name: 'RecordingError' })
  }
  assert.equal(mediaErrorMessage({ name: 'RecordingError' }, 'mic'), '녹음 시작 실패')
})
test('시작 실패 때 부분 녹음기를 닫고 잘못된 채점을 막는다', () => {
  let stopped = false, rec
  class Recorder {
    constructor() { rec = this; this.state = 'recording' }
    start() { throw Error('start failed') }
    stop() { stopped = true; this.onstop?.() }
  }
  assert.throws(() => startRecorder({}, () => assert.fail('data'), () => assert.fail('assess'), Recorder), { name: 'RecordingError' })
  assert.equal(stopped, true)
  assert.equal(rec.onstop, null)
  assert.equal(rec.ondataavailable, null)
})
test('정상 시작은 스트림과 콜백을 유지한다', () => {
  const stream = {}, data = () => {}, stop = () => {}
  class Recorder {
    constructor(s) { assert.equal(s, stream) }
    start() { this.state = 'recording' }
  }
  const rec = startRecorder(stream, data, stop, Recorder)
  assert.equal(rec.state, 'recording')
  assert.equal(rec.ondataavailable, data)
  assert.equal(rec.onstop, stop)
})
