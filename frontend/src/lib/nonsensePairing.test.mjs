import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { consonantFrame } from './consonantSkeleton.js'
import { SHAPES, SHAPE_IDS } from './nonsenseShapes.js'
import {
  seededShuffle, trialOrder, gridOrder, kstDay, usedToday, saveUsedToday, timeUp, blockSummary,
} from './nonsensePairing.js'

const DATA = JSON.parse(readFileSync(new URL('../../../backend/data/nonsense_words.json', import.meta.url), 'utf8'))
const PY = readFileSync(new URL('../../../backend/nonsense_words.py', import.meta.url), 'utf8')

test('자음 골격은 서버 생성 결과와 같다(받침 포함, 모음 자리는 _)', () => {
  assert.equal(consonantFrame('바록'), 'ㅂ_ㄹ_ㄱ')
  assert.equal(consonantFrame('아이'), '__')
  assert.equal(consonantFrame('바다?'), 'ㅂ_ㄷ_')
  for (const s of DATA.sets) for (const w of s.words) assert.equal(consonantFrame(w.word), w.skeleton, w.word)
})

test('도형 이름은 서버 SHAPES와 같고, 쓰인 도형은 모두 그릴 수 있다', () => {
  const py = PY.match(/^SHAPES = \(([^)]*)\)/m)[1].match(/"([a-z]+)"/g).map((s) => s.slice(1, -1))
  assert.deepEqual(SHAPE_IDS, py)
  for (const s of DATA.sets) for (const w of s.words) assert.ok(SHAPES[w.shape], w.shape)
  for (const id of SHAPE_IDS) assert.match(SHAPES[id].d, /^M/)
})

test('섞기는 씨앗이 같으면 같고, 순열이다', () => {
  const w = ['가', '나', '다', '라', '마', '바']
  assert.deepEqual(seededShuffle(w, 'x'), seededShuffle(w, 'x'))
  assert.deepEqual([...seededShuffle(w, 'x')].sort(), [...w].sort())
  assert.notDeepEqual(seededShuffle(w, 'ns01:1:grid'), seededShuffle(w, 'ns01:2:grid'))
})

test('이어 하면 남은 낱말만 같은 순서로', () => {
  const words = DATA.sets[0].words.map((x) => x.word)
  const full = trialOrder(words, words, 'ns01', 1)
  assert.equal(full.length, 6)
  const rest = trialOrder(words, full.slice(2), 'ns01', 1)
  assert.deepEqual(rest, full.slice(2))
  assert.deepEqual([...gridOrder(words, 'ns01', 3)].sort(), [...words].sort())
})

test('하루 시간: 한국 날짜로 더하고, 지난 날 기록은 지운다', () => {
  const store = new Map()
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k), key: (i) => [...store.keys()][i], get length() { return store.size },
  }
  const d1 = new Date('2026-10-06T14:00:00Z')   // KST 10/6 23시
  const d2 = new Date('2026-10-06T15:30:00Z')   // KST 10/7 0시 30분
  assert.equal(kstDay(d1), '2026-10-06')
  assert.equal(kstDay(d2), '2026-10-07')
  saveUsedToday(storage, 120000, d1)
  assert.equal(usedToday(storage, d1), 120000)
  assert.equal(usedToday(storage, d2), 0)
  saveUsedToday(storage, 5000, d2)
  assert.equal(store.size, 1)
  assert.equal(timeUp(600000, 10), true)
  assert.equal(timeUp(599999, 10), false)
  // 저장소를 못 쓰면 0(던져도 화면은 돈다)
  const broken = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') }, length: 0 }
  assert.equal(usedToday(broken), 0)
  saveUsedToday(broken, 1)
})

test('블록 안내 문장', () => {
  assert.match(blockSummary({ hint: true, correct: 4, size: 6 }), /골격 없이 확인/)
  assert.match(blockSummary({ hint: false, correct: 5, size: 6 }), /다시 골격을 보며/)
  assert.match(blockSummary({ hint: false, correct: 6, size: 6, setDone: true }), /끝났어요/)
})
