// roi_parity.mjs: 브라우저 ROI 경로(frontend/src/lib/lipRoi.js, lipreadRoiModel.js)를 파이썬 기준값(roi_parity_dump.py)과 대조한다
// (docs/lipread-roi-2026-10.md 13.2절). 추론은 브라우저와 같은 onnxruntime-web 1.19.2 WASM을 노드에서 돌린다.
//   node roi_parity.mjs --dir D:/liplab/roi/parity --model D:/liplab/roi/web/kr_lipread_roi.web.onnx
// 허용 기준(결과를 보기 전에 정함): 자르기 화소 최대 차 ≤ 1이고 다른 화소 비율 ≤ 0.1%, logits 최대 차 ≤ 1e-3,
// 후보 ctc_ll 최대 차 ≤ 1e-3, 후보 순위(4지 선택) 모두 같음. 하나라도 넘으면 종료 코드 1.
import { readFileSync, readdirSync, existsSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import * as ort from 'onnxruntime-web'
import { landmarkGeometry, extractRoiSequence, roiModelInput, rgbaToGray, ROI_SIZE } from '../../frontend/src/lib/lipRoi.js'
import { runRoiModel, scoreLogits } from '../../frontend/src/lib/lipreadRoiModel.js'

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d }
const DIR = arg('--dir', 'D:/liplab/roi/parity')
const MODEL = arg('--model', 'D:/liplab/roi/web/kr_lipread_roi.web.onnx')
const VOCAB = ['<blank>', ' ', ...[...new Set('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ'.split(''))].sort()]
const TOL = { pxMax: 1, pxFrac: 0.001, logit: 1e-3, ll: 1e-3 }

const u8 = (p) => new Uint8Array(readFileSync(p))
const f32 = (p) => { const b = readFileSync(p); return new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4) }

function cmpPx(a, b) {
  let mx = 0, nd = 0
  for (let i = 0; i < a.length; i++) { const d = Math.abs(a[i] - b[i]); if (d) { nd++; if (d > mx) mx = d } }
  return { max: mx, frac: nd / a.length }
}
function maxDiff(a, b) { let m = 0; for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i] - b[i])); return m }
const flat = (roi) => { const o = new Uint8Array(roi.length * ROI_SIZE * ROI_SIZE); roi.forEach((r, i) => o.set(r, i * r.length)); return o }

function jsSeq(dir) {
  const m = JSON.parse(readFileSync(join(dir, 'meta.json'), 'utf8'))
  const g = u8(join(dir, 'gray.u8')), n = m.W * m.H
  const frames = m.lms.map((l, i) => ({
    t: m.t_ms[i],
    gray: g.subarray(i * n, (i + 1) * n),
    geom: l ? landmarkGeometry(Object.fromEntries(Object.entries(l).map(([k, [x, y]]) => [k, { x, y }])), m.W, m.H) : null,
  }))
  let geomMax = 0
  if (m.py_geom) m.py_geom.forEach((p, i) => { if (p && frames[i].geom) geomMax = Math.max(geomMax, maxDiff(p, frames[i].geom)) })
  return { m, seq: extractRoiSequence(frames, m.W, m.H), geomMax }
}

ort.env.wasm.numThreads = 1
ort.env.logLevel = 'error'
const sess = await ort.InferenceSession.create(new Uint8Array(readFileSync(MODEL)), { executionProviders: ['wasm'] })
const rows = []
let ok = true
for (const c of readdirSync(DIR).sort()) {
  const d = join(DIR, c)
  if (c.startsWith('_') || !existsSync(join(d, 'meta.json'))) continue
  const { m, seq, geomMax } = jsSeq(d)
  const roiJs = flat(seq.roi), roiPy = u8(join(d, 'roi_py.u8')), roiNpz = u8(join(d, 'roi_npz.u8'))
  const px = roiJs.length === roiPy.length ? cmpPx(roiJs, roiPy) : { max: 999, frac: 1 }
  const pxNpz = roiJs.length === roiNpz.length ? cmpPx(roiJs, roiNpz) : { max: 999, frac: 1 }
  const rg = u8(join(d, 'rgba.u8')), gr = u8(join(d, 'gray_rgba.u8'))
  const grayMax = maxDiff(rgbaToGray(rg, gr.length), gr)
  const V = m.V
  const { data, T } = roiModelInput(seq.roi)
  const t0 = performance.now()
  const lj = await runRoiModel(sess, data, T, ort)
  const ms = performance.now() - t0
  const lpy = f32(join(d, 'logits_full.f32'))
  const w75 = roiModelInput(seq.roi.slice(0, 75))
  const t1 = performance.now()
  const lj75 = await runRoiModel(sess, w75.data, w75.T, ort)
  const ms75 = performance.now() - t1
  const lpy75 = f32(join(d, 'logits_w75.f32'))
  const sc = JSON.parse(readFileSync(join(d, 'scores.json'), 'utf8'))
  const sJ = scoreLogits(lj, T, V, VOCAB, sc.cands), sJ75 = scoreLogits(lj75, 75, V, VOCAB, sc.cands)
  const llJ = sc.cands.map((w) => sJ.ranked.find((r) => r.word === w).score)
  const llJ75 = sc.cands.map((w) => sJ75.ranked.find((r) => r.word === w).score)
  const argmax = (a) => a.indexOf(Math.max(...a))
  const rankSame = (a, b) => JSON.stringify(a.map((_, i) => i).sort((x, y) => (a[y] - a[x]) || (x - y))) ===
    JSON.stringify(b.map((_, i) => i).sort((x, y) => (b[y] - b[x]) || (x - y)))
  const r = {
    clip: c, W: m.W, H: m.H, T, side: m.side, geom_maxdiff: geomMax, gray_maxdiff: grayMax,
    crop_vs_py: px, crop_vs_train_npz: pxNpz,
    logit_maxdiff: maxDiff(lj, lpy), logit_maxdiff_w75: maxDiff(lj75, lpy75),
    logit_maxdiff_vs_graphnorm: maxDiff(lj, f32(join(d, 'logits_graphnorm.f32'))),   // 참고(기준 아님)
    ll_maxdiff: Math.max(maxDiff(llJ, sc.ctc_ll), maxDiff(llJ75, sc.w75)),
    choice_same: argmax(llJ) === argmax(sc.ctc_ll) && argmax(llJ75) === argmax(sc.w75),
    rank_same: rankSame(llJ, sc.ctc_ll) && rankSame(llJ75, sc.w75),
    ms_full: Math.round(ms), ms_w75: Math.round(ms75),
  }
  r.pass = r.crop_vs_py.max <= TOL.pxMax && r.crop_vs_py.frac <= TOL.pxFrac && r.logit_maxdiff <= TOL.logit &&
    r.logit_maxdiff_w75 <= TOL.logit && r.ll_maxdiff <= TOL.ll && r.rank_same && r.gray_maxdiff === 0
  ok = ok && r.pass
  rows.push(r)
  console.log('PARITY', JSON.stringify(r))
}
const fp = join(DIR, '_float_path')
if (existsSync(join(fp, 'meta.json'))) {
  const { m, seq } = jsSeq(fp)
  const px = cmpPx(flat(seq.roi), u8(join(fp, 'roi_py.u8')))
  const r = { clip: '_float_path', W: m.W, H: m.H, side: m.side, k: Math.ceil(m.side / 88 / 1.5), crop_vs_py: px,
    pass: px.max <= TOL.pxMax && px.frac <= TOL.pxFrac }
  ok = ok && r.pass
  rows.push(r)
  console.log('PARITY', JSON.stringify(r))
}
writeFileSync(join(DIR, '_parity.json'), JSON.stringify({ tol: TOL, ort_web: ort.env.versions?.web, rows, pass: ok }, null, 1))
console.log(ok ? `PARITY_OK n=${rows.length}` : `PARITY_FAIL n=${rows.length}`)
process.exit(ok ? 0 : 1)
