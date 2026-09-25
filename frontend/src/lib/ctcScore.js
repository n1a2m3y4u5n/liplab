/**
 * 후보 단어 채점(축 D 립리딩): 후보 자모열 전체의 CTC 전방 로그우도를 길이^α로 나눠 순위를 낸다.
 *
 * 지금 제품은 그리디 해독 결과와 후보의 자모 편집거리로 고른다(lipreadModel.js). P3 사전등록
 * (liplab-lab/notes/p3_score_prereg_2026-09-25.md)이 통과하면 이 함수로 바꾼다. 파이썬 벤치의 d_bench.ctc_loglik_multi·rank_ctc와
 * 같은 값을 내야 하며, ctcScore.test.mjs가 파이썬으로 만든 합성 기준값(ctcScore.fixture.json)과 대조한다.
 */

// 학습 때와 동일한 자모 분해(호환 자모). train_lipread.decompose와 일치해야 한다.
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'.split('')
const JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'.split('')
const JONG = 'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'.split('')

/** 한글 문자열 → 자모(호환) 배열. 학습 라벨과 같은 규칙(초·중·종, 공백 포함). */
export function decomposeToJamo(text) {
  const out = []
  for (const ch of (text || '')) {
    const o = ch.codePointAt(0)
    if (o >= 0xac00 && o <= 0xd7a3) {
      const s = o - 0xac00
      out.push(CHO[Math.floor(s / 588)])
      out.push(JUNG[Math.floor((s % 588) / 28)])
      const jong = s % 28
      if (jong) out.push(JONG[jong - 1])
    } else if (ch === ' ') {
      out.push(' ')
    }
  }
  return out
}


const NEG = -Infinity

function logAddExp(a, b) {
  if (a === NEG) return b
  if (b === NEG) return a
  const m = a > b ? a : b
  return m + Math.log(Math.exp(a - m) + Math.exp(b - m))
}

/** logits(길이 T*V, 행 우선) → 프레임별 log-softmax(Float64Array). */
export function logSoftmaxRows(logits, T, V) {
  const out = new Float64Array(T * V)
  for (let t = 0; t < T; t++) {
    let m = NEG
    for (let v = 0; v < V; v++) m = Math.max(m, logits[t * V + v])
    let s = 0
    for (let v = 0; v < V; v++) s += Math.exp(logits[t * V + v] - m)
    const z = m + Math.log(s)
    for (let v = 0; v < V; v++) out[t * V + v] = logits[t * V + v] - z
  }
  return out
}

/** 한 후보 자모 id열의 CTC 로그우도(blank 기본 0). logp는 logSoftmaxRows 결과. */
export function ctcLogLik(logp, T, V, labels, blank = 0) {
  const S = 2 * labels.length + 1
  const ext = new Int32Array(S).fill(blank)
  for (let i = 0; i < labels.length; i++) ext[2 * i + 1] = labels[i]
  const allow2 = new Uint8Array(S)
  for (let s = 2; s < S; s++) allow2[s] = ext[s] !== blank && ext[s] !== ext[s - 2] ? 1 : 0
  let alpha = new Float64Array(S).fill(NEG)
  let next = new Float64Array(S)
  alpha[0] = logp[ext[0]]
  if (S > 1) alpha[1] = logp[ext[1]]
  for (let t = 1; t < T; t++) {
    const row = t * V
    for (let s = 0; s < S; s++) {
      let a = alpha[s]
      if (s >= 1) a = logAddExp(a, alpha[s - 1])
      if (allow2[s]) a = logAddExp(a, alpha[s - 2])
      next[s] = a === NEG ? NEG : a + logp[row + ext[s]]
    }
    const tmp = alpha; alpha = next; next = tmp
  }
  return logAddExp(alpha[S - 1], S >= 2 ? alpha[S - 2] : NEG)
}

/** 후보들의 순위. 점수 = 로그우도 / max(길이,1)^α, 높은 순. 동점은 후보 순서(파이썬 안정 정렬과 같음). */
export function rankByCtc(logp, T, V, candLabels, alpha = 1) {
  const ll = candLabels.map((l) => ctcLogLik(logp, T, V, l))
  const scores = ll.map((v, i) => v / Math.pow(Math.max(candLabels[i].length, 1), alpha))
  const order = scores.map((_, i) => i).sort((a, b) => (scores[b] - scores[a]) || (a - b))
  return { order, scores, ll }
}
