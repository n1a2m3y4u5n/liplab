import test from 'node:test'
import assert from 'node:assert/strict'
import { todayNext } from './todayNext.js'
import { legacyTarget } from './legacyRoutes.js'
import { loadLastTrack, saveLastTrack } from './lastTrack.js'
const stages = { placed: true, stages: [{ stage: 1, key: 'viseme', title: '입모양', status: 'in_progress', attempts: 0 }] }
const base = { stages, due: {}, tasks: {}, lastTrack: 'read' }
test('today rule 1: failed stages', () => assert.equal(todayNext({}).retry, true))
test('today rule 2: placement', () => assert.equal(todayNext({ stages: { placed: false } }).to, '/onboarding'))
test('today rule 3: sound check only for listen', () => { assert.equal(todayNext({ ...base, lastTrack: 'listen', listen: { recommended: 0 } }).to, '/learn/listening?stage=0'); assert.equal(todayNext(base).to, '/learn/viseme') })
test('today rule 4: studied then review', () => assert.equal(todayNext({ ...base, due: { speak_count: 1 }, tasks: { daily: [{ key: 'two_sessions', cur: 1 }] } }).to, '/review/speaking'))
const listen = { recommended: 1, stages: [{ stage: 1, quota: { target_batches: 1, done_batches: 1 } }] }
test('today rules 5 and 6: quota', () => {
  const input = { ...base, lastTrack: 'listen', listen: { recommended: 1, stages: [{ stage: 1, quota: { quota_n: 2, today_n: 2 } }] } }
  assert.equal(todayNext({ ...input, due: { listen_count: 2 } }).to, '/listen/review')
  assert.equal(todayNext(input).label, '한 묶음 더 하기')
})
test('today rules 7 and 8: all mastered', () => { const input = { ...base, stages: { placed: true, stages: [{ ...stages.stages[0], status: 'mastered' }] } }; assert.equal(todayNext({ ...input, due: { count: 1 } }).review, true); assert.equal(todayNext(input).label, '자유 연습 하기') })
test('today rules 9 and 10: start or continue', () => { assert.equal(todayNext(base).label, '학습 시작하기'); assert.equal(todayNext({ ...base, stages: { ...stages, stages: [{ ...stages.stages[0], attempts: 2 }] } }).label, '이어서 학습하기') })
test('redirect preserves query and destination priority', () => assert.equal(legacyTarget('/records?track=listen', '?track=speak&source=old'), '/records?track=listen&source=old'))
test('track memory is per account and bare path never uses memory', () => { const data = new Map(); const storage = { setItem: (k,v) => data.set(k,v), getItem: (k) => data.get(k) }; saveLastTrack(1, 'listen', storage); assert.equal(loadLastTrack(1, {}, storage), 'listen'); assert.equal(loadLastTrack(2, {}, storage), 'read') })
