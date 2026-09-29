// 파드 스크립트(scripts/coart_pod_eval.py)가 읽는 입모양 표·동시조음 규칙 묶음. scripts/export_viseme_shapes.mjs가 JSON으로 쓰고,
// coarticulation.test.mjs가 저장된 JSON과 지금 코드가 같은지 확인한다. 앱 번들에는 들어가지 않는다(가져다 쓰는 화면이 없다).
import { VISEME_BLENDSHAPES } from './visemeShapes.js'
import {
  COART_TARGETS, COART_VOWELS, COART_STOPS, LIP_KEYS, COART_W, COART_W_MAX, applyCoarticulation, coartShape,
} from './coarticulation.js'

// 파이썬 이식이 같은 답을 내는지 볼 표본(프레임 입모양 열). 수술, 국물, 아수, 사과(이중모음 활음), 두 단어(쉼 경계), 단어 끝 받침.
const FIXTURE_SEQS = [
  [6, 4, 6, 4, 6],
  [7, 4, 7, 11, 1, 4, 6],
  [2, 6, 4],
  [6, 2, 7, 4, 2],
  [6, 3, 14, 7, 5, 6, 13],
  [8, 2, 7, 12, 6, 3],
]

export function buildExport() {
  const w = COART_W
  const fixtures = FIXTURE_SEQS.map((seq) => {
    const frames = applyCoarticulation(seq.map((v) => ({ viseme: v })), true)
    const lip = frames.map((f) => f.coart_v ?? null)
    return { visemes: seq, coart_v: lip, shapes: frames.map((f) => coartShape(VISEME_BLENDSHAPES, f.viseme, f.coart_v, w) || {}) }
  })
  return {
    source: 'frontend/src/lib/visemeShapes.js + coarticulation.js (scripts/export_viseme_shapes.mjs)',
    blendshapes: VISEME_BLENDSHAPES,
    coart: {
      targets: [...COART_TARGETS], vowels: [...COART_VOWELS], stops: [...COART_STOPS], lip_keys: LIP_KEYS, w, w_max: COART_W_MAX,
    },
    fixtures,
  }
}
