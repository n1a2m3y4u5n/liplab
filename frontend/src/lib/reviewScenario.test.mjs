// reviewScenario 검사. 실행: npm test (node --test)
import test from 'node:test'
import assert from 'node:assert/strict'
import { mistakeReviewScenario, sentenceLevel, sentenceReviewSubmission } from './reviewScenario.js'

const items = [
  { sentence: '따뜻한 아메리카노 한 잔 주세요', situation: '카페', difficulty_level: 4 },
  { sentence: '', situation: '카페', difficulty_level: 2 },
  { sentence: '영수증은 버려 주세요', situation: '마트', difficulty_level: 5 },
  { sentence: '내일 봐요', situation: '인사', difficulty_level: null },
]

test('mistakeReviewScenario: 문장마다 원래 난이도를 담고, 빈 문장은 문장·난이도에서 함께 뺀다', () => {
  const s = mistakeReviewScenario(items, (n) => Array(n).fill('test'), 123)
  assert.deepEqual(s.sentences, ['따뜻한 아메리카노 한 잔 주세요', '영수증은 버려 주세요', '내일 봐요'])
  assert.deepEqual(s.levels, [4, 5, 1])
  assert.equal(s.scenario_id, 'mistake_review_123')
  assert.equal(s.qTypes.length, 3)
})

test('sentenceLevel: 복습은 문장별 난이도, 일반 레슨·북마크는 세션 난이도', () => {
  const s = mistakeReviewScenario(items, null, 1)
  assert.deepEqual([0, 1, 2].map((i) => sentenceLevel(s, i)), [4, 5, 1])
  assert.equal(sentenceLevel({ level: 3, sentences: ['a', 'b'] }, 1), 3)
  assert.equal(sentenceLevel({ level: 2, levels: [], sentences: ['a'] }, 0), 2)
  assert.equal(sentenceLevel({ level: 9 }, 0), 5)
  assert.equal(sentenceLevel(null, 0), 1)
})

test('sentenceReviewSubmission: srs_review_ 세션 id, 레슨 기록의 상황·난이도, 없으면 기본값', () => {
  const item = { kind: 'sentence', ref: '창가 자리에 앉을게요', situation: '카페', difficulty_level: 4 }
  assert.deepEqual(sentenceReviewSubmission(item, '  창가 자리  ', 12.4, 'srs_review_77'), {
    scenario_id: 'srs_review_77', sentence: '창가 자리에 앉을게요', user_answer: '창가 자리',
    time_spent_seconds: 12, situation: '카페', difficulty_level: 4,
  })
  const bare = sentenceReviewSubmission({ ref: '내일 봐요' }, '내일', -3, 5)
  assert.equal(bare.scenario_id, 'srs_review_5')
  assert.equal(bare.situation, '문장 복습')
  assert.equal(bare.difficulty_level, 1)
  assert.equal(bare.time_spent_seconds, 0)
})
