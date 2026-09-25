import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { decomposeToJamo, logSoftmaxRows, ctcLogLik, rankByCtc } from './ctcScore.js'

const fx = JSON.parse(readFileSync(new URL('./ctcScore.fixture.json', import.meta.url), 'utf8'))
const ids = (w) => decomposeToJamo(w).map((j) => fx.vocab.indexOf(j))

test('자모 id열이 파이썬 train_lipread.decompose와 같다', () => {
  for (const c of fx.cases) c.candidates.forEach((w, i) => assert.deepEqual(ids(w), c.labels[i]))
})

test('CTC 로그우도가 파이썬 ctc_loglik_multi와 1e-6 이내로 같다', () => {
  for (const c of fx.cases) {
    const logp = logSoftmaxRows(Float64Array.from(c.logits), c.T, c.V)
    c.candidates.forEach((w, i) => {
      const ll = ctcLogLik(logp, c.T, c.V, ids(w))
      assert.ok(Math.abs(ll - c.ll[i]) < 1e-6, `${w}: ${ll} vs ${c.ll[i]}`)
    })
  }
})

test('α 0·0.5·1 순위가 파이썬 rank_ctc와 같다', () => {
  for (const c of fx.cases) {
    const logp = logSoftmaxRows(Float64Array.from(c.logits), c.T, c.V)
    for (const al of ['0.0', '0.5', '1.0']) {
      const { order } = rankByCtc(logp, c.T, c.V, c.candidates.map(ids), Number(al))
      assert.deepEqual(order.map((k) => c.candidates[k]), c.ranked[al])
    }
  }
})

test('빈 후보와 한 프레임도 계산된다', () => {
  const logp = logSoftmaxRows(Float64Array.from([0, 1, 2]), 1, 3)
  assert.ok(Number.isFinite(ctcLogLik(logp, 1, 3, [])))
  assert.ok(Number.isFinite(ctcLogLik(logp, 1, 3, [2])))
  assert.equal(ctcLogLik(logp, 1, 3, [1, 2]), -Infinity)   // 한 프레임에 두 글자는 불가능
})
