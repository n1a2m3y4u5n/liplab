import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { VISEME_BLENDSHAPES } from './visemeShapes.js'
import { TALKERS, talkerShapes } from './talkers.js'
import {
  COART_E_ENABLED, COART_TARGETS, COART_W, COART_W_MAX, LIP_KEYS, applyCoarticulation, blendLip, coartShape, coartWeight,
} from './coarticulation.js'
import { buildExport } from './visemeShapesExport.js'

const seq = (vs) => vs.map((v, i) => ({ viseme: v, duration_ms: 100, transition_ms: 30, text_index: i }))
const R = (s) => (s.mouthFunnel || 0) + (s.mouthPucker || 0)

test('플래그는 기본으로 꺼져 있고, 꺼져 있으면 프레임을 그대로 돌려준다', () => {
  assert.equal(COART_E_ENABLED, false)
  const f = seq([6, 4, 6, 4, 6])
  assert.equal(applyCoarticulation(f), f)
  assert.equal(applyCoarticulation(f, false), f)
})

test('수술 [6,4,6,4,6]: ㅅ·ㄹ이 원순을 유지한다(단어 끝 받침은 앞 모음을 잇는다)', () => {
  const f = seq([6, 4, 6, 4, 6])
  const out = applyCoarticulation(f, true)
  assert.deepEqual(out.map((x) => x.coart_v ?? null), [4, null, 4, null, 4])
  // viseme·시간·음절 번호는 그대로(입모양 열 서명과 채점이 바뀌지 않는다)
  assert.deepEqual(out.map((x) => x.viseme), [6, 4, 6, 4, 6])
  assert.deepEqual(out.map((x) => [x.duration_ms, x.transition_ms, x.text_index]), f.map((x) => [x.duration_ms, x.transition_ms, x.text_index]))
  const s = coartShape(VISEME_BLENDSHAPES, 6, 4, COART_W)
  assert.ok(R(s) >= COART_W * R(VISEME_BLENDSHAPES[4]) - 1e-9, '자음 프레임에서도 입술이 둥글다')
  assert.equal(R(VISEME_BLENDSHAPES[6]), 0, '예전(꺼짐)에는 자음마다 둥글림이 0으로 돌아갔다')
})

test('턱·양순 폐쇄·그 밖의 모프는 자음 값 그대로, 입술 모프만 섞인다', () => {
  for (const c of COART_TARGETS) {
    for (const v of [2, 3, 4, 5, 9]) {
      const base = VISEME_BLENDSHAPES[c]
      const s = coartShape(VISEME_BLENDSHAPES, c, v, COART_W)
      for (const k of new Set([...Object.keys(base), ...Object.keys(s)])) {
        if (LIP_KEYS.includes(k)) {
          const b = base[k] || 0
          const want = Math.max(b, (1 - COART_W) * b + COART_W * (VISEME_BLENDSHAPES[v][k] || 0))
          assert.ok(Math.abs((s[k] || 0) - want) < 1e-12, `${c}←${v} ${k}`)
        } else {
          assert.equal(s[k], base[k], `${c}←${v} ${k}는 바뀌면 안 된다`)
        }
      }
    }
  }
})

test('양순(1)·양순 전환(11)·모음·쉼에는 붙이지 않고, 쉼(14)을 넘어 섞지 않는다', () => {
  const out = applyCoarticulation(seq([7, 4, 7, 11, 1, 4, 6, 14, 6, 2]), true)
  assert.deepEqual(out.map((x) => x.coart_v ?? null), [4, null, 4, null, null, null, 4, null, 2, null])
  // 모음이 하나도 없는 조각(쉼만, 자음만)은 그대로
  const lone = seq([14, 6, 14])
  assert.equal(applyCoarticulation(lone, true), lone)
  // 이중모음은 활음 프레임(원순 4)을 앞 자음이 미리 만든다: 사과 [6,2,7,4,2]. 정지 모양 9가 들어와도 원순(4)으로 섞는다.
  assert.deepEqual(applyCoarticulation(seq([6, 2, 7, 4, 2]), true).map((x) => x.coart_v ?? null), [2, null, 4, null, null])
  assert.deepEqual(applyCoarticulation(seq([7, 9]), true).map((x) => x.coart_v ?? null), [4, null])
})

test('섞은 모양은 표마다 한 번만 만든다(화면마다 새로 계산하지 않음), 섞을 모음이 없으면 표의 모양 그대로', () => {
  assert.equal(coartShape(VISEME_BLENDSHAPES, 6, 4), coartShape(VISEME_BLENDSHAPES, 6, 4))
  assert.equal(coartShape(VISEME_BLENDSHAPES, 6, null), VISEME_BLENDSHAPES[6])
  assert.equal(coartShape(VISEME_BLENDSHAPES, 1, 4), VISEME_BLENDSHAPES[1])
  const t = talkerShapes(TALKERS[0])
  assert.equal(coartShape(t, 7, 3, coartWeight(TALKERS[0])), coartShape(t, 7, 3, coartWeight(TALKERS[0])))
  assert.deepEqual(blendLip({}, {}, 0.6), {})
})

test('자음 자기 입술 모양은 줄지 않는다: 자 [10,2]의 ㅈ은 내밂·당김을 그대로 둔다', () => {
  const s = coartShape(VISEME_BLENDSHAPES, 10, 2, COART_W)
  assert.deepEqual(s, VISEME_BLENDSHAPES[10])
  const t = coartShape(VISEME_BLENDSHAPES, 10, 3, COART_W)
  assert.equal(t.mouthFunnel, VISEME_BLENDSHAPES[10].mouthFunnel)
  assert.ok(t.mouthSmileLeft > VISEME_BLENDSHAPES[10].mouthSmileLeft)
})

test('가상 화자의 동시조음 강도가 섞는 비율에 곱해진다(상한 안)', () => {
  assert.equal(coartWeight(null), COART_W)
  for (const t of TALKERS) {
    const w = coartWeight(t)
    assert.ok(w > 0.3 && w <= COART_W_MAX, `${t.id} w=${w}`)
  }
})

test('파드 스크립트용 JSON(scripts/viseme_shapes.json)이 지금 표·규칙과 같다(다르면 node scripts/export_viseme_shapes.mjs)', () => {
  const path = fileURLToPath(new URL('../../../scripts/viseme_shapes.json', import.meta.url))
  const saved = JSON.parse(readFileSync(path, 'utf8'))
  assert.deepEqual(saved, JSON.parse(JSON.stringify(buildExport())))
})
