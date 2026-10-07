// V15 표와 V5 재선정 가상 화자에 판별 기준 (a)(b)(c)(d)(docs/talker-variation.md 7·8절)를 걸고, 어긋나면 4절 규칙으로 줄인다:
// 위반한 쌍(입모양 v, 넘어간 무리 u)의 두 기본 목표 가운데 0이 아닌 키를 바꾸는 매개변수만, 1에서 벗어난 폭을 원래 폭의 5%씩 줄인다.
//   node scripts/v15_talker_shrink.mjs <talkers.json>     (V5 선정값 {id: {amp, protrusion, rate}}) → 줄인 값과 최소 여백을 출력
import { readFileSync } from 'node:fs'
import { VISEME_BLENDSHAPES_V15, ACTIVE_MORPH_KEYS } from '../frontend/src/lib/visemeShapes.js'
import { TALKERS_V1, scaleShape, AMP_KEYS, WIDTH_KEYS, PROTRUSION_KEYS, TRANSITION_VISEMES } from '../frontend/src/lib/talkers.js'
import { COART_TARGETS, coartShape, coartWeight } from '../frontend/src/lib/coarticulation.js'

const T = VISEME_BLENDSHAPES_V15
const CLASSES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
const QUIZ = [1, 2, 3, 4, 5, 9]
const LOW = [6, 7, 8, 10]
const ALLOWED = { 11: [11, 1, 6, 7], 12: [12, 13, 1, 6, 7], 13: [13, 12, 1, 6, 7] }
const ROUND = [4, 9]
const COART_V = [2, 3, 4, 5]
const vec = (sh) => ACTIVE_MORPH_KEYS.map((k) => sh[k] || 0)
const dist = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]))
const D = Object.fromEntries(CLASSES.map((v) => [v, vec(T[v])]))
const nearest = (t, set) => set.reduce((best, u) => { const x = dist(t, D[u]); return x < best[0] ? [x, u] : best }, [Infinity, null])

function violations(tk) {
  const out = []
  for (const v of CLASSES.filter((x) => x !== 14)) {
    const t = vec(scaleShape(T[v], tk, v))
    const ok = QUIZ.includes(v) ? [v] : LOW.includes(v) ? LOW : ALLOWED[v]
    const bad = LOW.includes(v) ? QUIZ : CLASSES.filter((u) => !ok.includes(u))
    const m = nearest(t, bad)[0] - nearest(t, ok)[0]
    out.push({ v, rival: nearest(t, bad)[1], margin: m, rule: 'abc' })
  }
  const table = Object.fromEntries(Object.entries(T).map(([v, sh]) => [v, scaleShape(sh, tk, Number(v))]))
  const w = coartWeight(tk)
  for (const c of COART_TARGETS) {
    for (const V of COART_V) {
      const t = vec(coartShape(table, c, V, w))
      const ok = [...new Set([...LOW, ...(ALLOWED[c] || []), V, ...(ROUND.includes(V) ? ROUND : [])])]
      const bad = CLASSES.filter((u) => !ok.includes(u))
      out.push({ v: c, V, rival: nearest(t, bad)[1], margin: nearest(t, bad)[0] - nearest(t, ok)[0], rule: 'd' })
    }
  }
  return out
}

function paramsFor(v, u) {
  const keys = new Set([...Object.keys(T[v] || {}), ...Object.keys(T[u] || {})].filter((k) => (T[v]?.[k] || 0) > 0 || (T[u]?.[k] || 0) > 0))
  const ps = new Set()
  for (const k of keys) {
    if (AMP_KEYS.includes(k)) ps.add('amp')
    if (WIDTH_KEYS.includes(k)) ps.add('width')
    if (PROTRUSION_KEYS.includes(k)) ps.add('protrusion')
  }
  if (TRANSITION_VISEMES.has(v) || TRANSITION_VISEMES.has(u)) ps.add('coart')
  return ps
}

const sel = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const result = []
for (const old of TALKERS_V1) {
  const tk = { ...old, ...(sel[old.id] ? { amp: sel[old.id].amp, protrusion: sel[old.id].protrusion, rate: sel[old.id].rate } : {}) }
  const orig = { ...tk }
  let steps = 0
  for (;;) {
    const bad = violations(tk).filter((m) => m.margin <= 0)
    if (!bad.length || steps > 40) break
    const ps = new Set()
    for (const m of bad) for (const p of paramsFor(m.v, m.rival)) ps.add(p)
    for (const p of ps) tk[p] = Math.round((tk[p] - Math.sign(tk[p] - 1) * Math.abs(orig[p] - 1) * 0.05) * 1000) / 1000
    steps += 1
  }
  const vs = violations(tk)
  const worst = vs.reduce((a, b) => (b.margin < a.margin ? b : a))
  result.push({ id: tk.id, amp: tk.amp, width: tk.width, protrusion: tk.protrusion, coart: tk.coart, rate: tk.rate, steps,
    changed: Object.fromEntries(['amp', 'width', 'protrusion', 'coart'].filter((k) => tk[k] !== orig[k]).map((k) => [k, [orig[k], tk[k]]])),
    min_margin: Number(worst.margin.toFixed(4)), at: `${worst.rule} ${worst.v}${worst.V ? '←' + worst.V : ''} 대 ${worst.rival}` })
}
console.log(JSON.stringify(result, null, 1))
