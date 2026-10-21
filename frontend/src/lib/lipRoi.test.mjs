import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  roundHalfEven, fillGaps, planCrops, cropFrame, gridSources, rgbaToGray, roiModelInput, extractRoiSequence,
  landmarkGeometry, LIP_OUTER,
} from './lipRoi.js'
import { scoreLogits, wordLabels } from './lipreadRoiModel.js'
import { lipreadRoiOn } from './lipreadGate.js'

// 기준값은 데스크탑 cv2 4.9 + lip_roi_extract.py로 만들었다(scripts/lipread_roi/roi_fixture.py). 실제 클립 대조는 roi_parity.mjs
const fx = JSON.parse(readFileSync(new URL('./lipRoi.fixture.json', import.meta.url), 'utf8'))
const b64 = (s) => new Uint8Array(Buffer.from(s, 'base64'))
const img = b64(fx.img_b64)

test('반올림은 cvRound·파이썬 round처럼 가운데 값을 짝수 쪽으로', () => {
  assert.deepEqual([0.5, 1.5, 2.5, -0.5, -1.5, 2.4, 2.6].map(roundHalfEven), [0, 2, 2, -0, -2, 2, 3])
})

test('공백 채우기가 build_cd 규칙(양쪽 검출, 3프레임 이하)과 같다', () => {
  assert.deepEqual(fillGaps(fx.fill_in), fx.fill_out)
})

test('자르기 계획(보간·이동평균·unwrap·중앙값 한 변)이 파이썬과 같다', () => {
  for (const c of fx.cases) {
    const p = planCrops(fx.geom, { margin: c.margin })
    for (let i = 0; i < fx.geom.length; i++) {
      assert.ok(Math.abs(p.cx[i] - c.cx[i]) < 1e-9 && Math.abs(p.cy[i] - c.cy[i]) < 1e-9 && Math.abs(p.theta[i] - c.theta[i]) < 1e-9, `프레임 ${i}`)
    }
    assert.ok(Math.abs(p.side - c.side) < 1e-9)
  }
})

test('자르기 화소가 cv2.warpAffine(8U, k=1)·과표본(float, k>1)과 같다', () => {
  for (const c of fx.cases) {
    c.frames.forEach((i, j) => {
      const got = cropFrame(img, fx.W, fx.H, c.cx[i], c.cy[i], c.theta[i], c.side)
      const want = b64(c.roi_b64[j])
      let mx = 0
      for (let q = 0; q < got.length; q++) mx = Math.max(mx, Math.abs(got[q] - want[q]))
      assert.equal(mx, 0, `k=${c.k} 프레임 ${i}`)
    })
  }
})

test('30 fps 격자(같은 칸은 마지막, 빈 칸은 가까운 프레임)가 grid_sources와 같다', () => {
  for (const g of fx.grids) {
    const { src, exact } = gridSources(g.t_ms)
    assert.deepEqual(src, g.src, `fps ${g.fps}`)
    assert.deepEqual(exact, g.exact)
  }
})

test('흑백 변환이 OpenCV 4.x BGR2GRAY 정수식과 같다', () => {
  const rgba = new Uint8Array([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 10, 200, 37, 255])
  assert.deepEqual([...rgbaToGray(rgba, 4)], [76, 150, 29, 125])
})

test('랜드마크 기하: 무게중심·61↔291 너비·눈꼬리 각도', () => {
  const lms = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }))
  LIP_OUTER.forEach((k, j) => { lms[k] = { x: 0.4 + 0.01 * j, y: 0.7 } })
  lms[33] = { x: 0.3, y: 0.4 }; lms[263] = { x: 0.7, y: 0.4 }
  const [cx, cy, w, th] = landmarkGeometry(lms, 100, 100)
  assert.ok(Math.abs(cx - (49.5 - 0.5)) < 1e-9 && Math.abs(cy - 69.5) < 1e-9)
  assert.ok(Math.abs(w - 10) < 1e-9 && Math.abs(th) < 1e-12)
})

test('모델 입력: 가운데 80×80, 75프레임까지 가장자리로 채움, float64 z-정규화', () => {
  const fr = (v) => { const a = new Uint8Array(88 * 88).fill(v); a[4 * 88 + 4] = 255; return a }
  const { data, T } = roiModelInput([fr(10), fr(20), fr(30)])
  assert.equal(T, 75)
  let s = 0, s2 = 0
  for (const v of data) { s += v; s2 += v * v }
  assert.ok(Math.abs(s / data.length) < 1e-6 && Math.abs(s2 / data.length - 1) < 1e-5)
  assert.ok(data[0] > data[1])                         // 왼쪽 위 255 화소가 가운데 자르기의 (0,0)
  assert.equal(data[6400 * 0 + 1], data[6400 * 36 + 1])    // 앞 36프레임은 첫 프레임(10) 반복
  assert.ok(data[6400 * 37 + 1] > data[6400 * 36 + 1])      // 37번이 원래 둘째 프레임(20)
  const flat = roiModelInput(Array(75).fill(new Uint8Array(88 * 88).fill(7)))
  assert.ok(flat.data.every((v) => v === 0))           // 표준편차 하한 1e-2(학습과 같음)
})

test('녹화 프레임 → ROI 시퀀스: 얼굴 없는 프레임도 보간 위치에서 자르고 유효 표시는 공백 규칙', () => {
  const frames = fx.geom.map((g, i) => ({ t: Math.round(i * 1000 / 30), gray: img, geom: g }))
  const s = extractRoiSequence(frames, fx.W, fx.H)
  assert.equal(s.roi.length, fx.geom.length)
  assert.deepEqual(s.valid, fillGaps(fx.geom.map(Boolean)))
  const c = fx.cases[0]
  assert.deepEqual([...s.roi[9]], [...b64(c.roi_b64[1])])
  assert.equal(extractRoiSequence(frames.map((f) => ({ ...f, geom: null })), fx.W, fx.H), null)
})

test('ctc_ll 채점: 정답 자모열을 내는 logits면 그 후보를 고르고, 순위 동점은 후보 순서', () => {
  const vocab = JSON.parse(readFileSync(new URL('../../public/models/kr_d_lipread.meta.json', import.meta.url), 'utf8')).vocab
  const V = vocab.length, cands = ['사과', '바다', '사자', '가지']
  const lab = wordLabels('사자', vocab)
  const T = 30, logits = new Float32Array(T * V).fill(-5)
  for (let t = 0; t < T; t++) {
    const k = Math.floor(t / (T / (2 * lab.length + 1)))
    logits[t * V + (k % 2 ? lab[(k - 1) / 2] : 0)] = 8
  }
  const r = scoreLogits(logits, T, V, vocab, cands)
  assert.equal(r.matched, '사자')
  assert.equal(r.jamo, 'ㅅㅏㅈㅏ')
  const flat = scoreLogits(new Float32Array(T * V), T, V, vocab, ['가', '나'])
  assert.equal(flat.matched, '가')
})

test('빌드 플래그 VITE_LIPREAD_ROI는 1일 때만 켜진다(기본 끔)', () => {
  assert.equal(lipreadRoiOn({}), false)
  assert.equal(lipreadRoiOn({ VITE_LIPREAD_ROI: '0' }), false)
  assert.equal(lipreadRoiOn({ VITE_LIPREAD_ROI: '1' }), true)
})
