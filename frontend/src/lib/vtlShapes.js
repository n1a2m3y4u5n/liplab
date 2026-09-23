/**
 * VocalTractLab(VTL) 사전계산 자산 조회 (계획서 E-6). React·DOM에 기대지 않는 순수 함수와 지연 로더.
 *
 * 자산은 scripts/vtl_build_assets.py가 오프라인에서 VTL을 실행해 만든 public/vtl/*.json이다.
 * 앱은 VTL 코드를 번들하거나 호출하지 않고 좌표만 읽는다(VTL은 GPL-3.0, docs/e6-vocaltractlab.md).
 *   shapes.json      음소별 윤곽(o)·포먼트(f)·목표값(target)
 *   vowel_grid.json  모음 사이를 보간한 성도 상태들. 상태마다 VTL 포먼트 f=[F1,F2,F3], 입술 층 r(0 펴짐,
 *                    1 둥글림), 윤곽 o. vowels는 모음 8개의 앱 목표값(target)과 VTL 포먼트(vtl) 대응.
 * 윤곽 o는 폴리라인 배열(parts 순서)이고 각 폴리라인은 [x0,y0,x1,y1,...] 정수(0.01 cm, y 아래가 +)다.
 * 모든 상태의 점 개수가 같아서 상태 사이를 점별로 섞을 수 있다.
 *
 * 추정 조음: 포먼트(F1·F2 Hz)로 격자에서 가장 가까운 상태를 고른다. 거리는 Bark 척도 유클리드 거리.
 * normalize(기본 켬)는 앱 목표값 기준 좌표를 VTL 화자 좌표로 옮긴 뒤 찾는다. 모음 8개마다 목표값과 VTL
 * 포먼트가 조금씩 달라서, 옮기지 않으면 목표 모음 위에 있어도 이웃 모음과 섞인 상태가 골라진다. 옮김은
 * 모음 8개의 변위를 거리 제곱 역수로 가중 평균한 것(Shepard 보간)이라 목표 모음 위에서는 그 모음이 된다.
 * 포먼트에서 성도 모양은 여러 개가 가능하므로(다대일) 결과는 그럴듯한 한 가지 예시이지 진단이 아니다.
 */

/** Traunmüller(1990) Bark 척도. 빌드 스크립트의 bark()와 같은 식. */
export const bark = (f) => (26.81 * f) / (1960 + f) - 0.53

/** 한국어 단모음 → 자산 id(국어의 로마자 표기법). */
export const VOWEL_IDS = { 'ㅣ': 'i', 'ㅔ': 'e', 'ㅐ': 'ae', 'ㅏ': 'a', 'ㅓ': 'eo', 'ㅗ': 'o', 'ㅜ': 'u', 'ㅡ': 'eu' }

/**
 * engine.py 비심(1~15) → shapes.json 음소 id. 비심 하나에 여러 소리가 있으면 대표 하나를 쓴다
 * (1 양순 → ㅂ, 6 치경 → ㄷ, 7 연구개 → ㄱ, 10 경구개 → ㅈ). 8(ㅎ)은 성도 모양이 뒤 모음을 따라 중립,
 * 9(이중모음)는 시작 자세 ㅗ, 11~13(전환)은 해당 자음, 14·15(휴지·중립)는 입 다문 쉼 자세.
 */
export const VISEME_TO_VTL = {
  1: 'b', 2: 'a', 3: 'i', 4: 'u', 5: 'eo', 6: 'd', 7: 'g', 8: 'schwa', 9: 'o', 10: 'j',
  11: 'b', 12: 'd', 13: 'g', 14: 'rest', 15: 'rest',
}

/**
 * 입모양 그룹(비심 1~10)별로 성도 단면을 나란히 보여 줄 음소와 설명. 같은 입모양 안에서 밖으로 안 보이는
 * 차이(혀 높이·앞뒤, 연구개)를 짚는다. 설명은 shapes.json 형상과 맞춰 썼다(docs/e6-vocaltractlab.md).
 */
export const VISEME_GROUP_VTL = {
  1: { ids: ['b', 'm'], note: '두 소리 모두 입술을 똑같이 닫아요. ㅁ은 연구개가 내려가 코로 공기가 나가요. 입모양으로는 구별되지 않는 차이예요.' },
  2: { ids: ['a', 'ae'], note: '둘 다 입을 벌리지만 ㅐ는 혀의 가장 높은 곳이 더 앞쪽에 있어요.' },
  3: { ids: ['i', 'e'], note: '입술 모양은 비슷하고 ㅔ가 혀를 조금 더 내려요.' },
  4: { ids: ['o', 'u'], note: '둘 다 입술을 둥글게 내밀어요. ㅜ가 혀 뒤쪽을 더 높이 올려요.' },
  5: { ids: ['eo', 'eu'], note: '둘 다 입술이 펴져 있어요. ㅡ는 혀 뒤쪽이 높고 ㅓ는 낮아요.' },
  6: { ids: ['d', 'n', 's', 'l'], note: '혀끝이 윗잇몸에 닿거나(ㄷ·ㄴ·ㄹ) 가까이 가요(ㅅ). ㄴ은 연구개도 내려가요. 입 밖에서는 거의 보이지 않아요.' },
  7: { ids: ['g', 'ng'], note: '혀 뒤쪽이 연구개에 닿아요. 받침 ㅇ은 연구개가 내려가 코로 소리가 나요.' },
  10: { ids: ['j'], note: '혀가 입천장 앞쪽에 닿았다가 떨어져요. 모형에는 가까운 후치경 폐쇄로 그렸어요.' },
}

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v)
const IDW_EPS = 0.05            // k-최근접 섞기의 거리 여유(Bark). 0이면 격자점 위에서 무게가 무한대가 된다.

/** 앱 목표값 좌표(F1, F2 Hz) → VTL 화자 좌표 [Bark F1, Bark F2]. 모음 대응의 Shepard 보간(거듭제곱 2). */
export function warpToVtl(grid, f1, f2) {
  const z1 = bark(f1)
  const z2 = bark(f2)
  let n1 = 0
  let n2 = 0
  let den = 0
  for (const v of grid.vowels) {
    const a1 = bark(v.target[0])
    const a2 = bark(v.target[1])
    const b1 = bark(v.vtl[0])
    const b2 = bark(v.vtl[1])
    const d = Math.hypot(z1 - a1, z2 - a2)
    if (d < 1e-9) return [b1, b2]
    const w = 1 / (d * d)
    n1 += w * (b1 - a1)
    n2 += w * (b2 - a2)
    den += w
  }
  return [z1 + n1 / den, z2 + n2 / den]
}

/**
 * 격자 상태를 가까운 순서로. layer를 주면 그 입술 층(0 펴짐, 1 둥글림)만 본다.
 * 반환: [{ index, state, distance }] (distance는 Bark). 거리가 같으면 번호가 작은 쪽이 먼저다.
 */
export function rankStates(grid, f1, f2, { layer = null, normalize = true } = {}) {
  const [q1, q2] = normalize ? warpToVtl(grid, f1, f2) : [bark(f1), bark(f2)]
  const out = []
  grid.states.forEach((state, index) => {
    if (layer != null && state.r !== layer) return
    out.push({ index, state, distance: Math.hypot(q1 - bark(state.f[0]), q2 - bark(state.f[1])) })
  })
  out.sort((a, b) => a.distance - b.distance || a.index - b.index)
  return out
}

/**
 * 가장 가까운 격자 상태 하나. round(0~1)를 주면 0.5 이상은 둥글림 층, 미만은 펴짐 층에서 찾는다.
 * 반환: { index, state, distance, outline } 또는 격자가 비었으면 null.
 */
export function nearestGridState(grid, f1, f2, { round = null, normalize = true } = {}) {
  const layer = round == null ? null : (clamp01(round) >= 0.5 ? 1 : 0)
  const best = rankStates(grid, f1, f2, { layer, normalize })[0]
  return best ? { ...best, outline: best.state.o } : null
}

/** 같은 구조의 윤곽 여러 개를 무게대로 점별 평균한다(무게는 정규화). */
export function blendOutlines(outlines, weights) {
  const sum = weights.reduce((a, b) => a + b, 0)
  if (!outlines.length || !(sum > 0)) return null
  const w = weights.map((x) => x / sum)
  return outlines[0].map((poly, k) => poly.map((_, j) => {
    let v = 0
    for (let i = 0; i < outlines.length; i += 1) v += w[i] * outlines[i][k][j]
    return v
  }))
}

function blendNearest(ranked, k) {
  const top = ranked.slice(0, Math.max(1, k))
  if (!top.length) return null
  if (top[0].distance < 1e-6) return { outline: top[0].state.o, distance: 0, used: [top[0]] }
  const ws = top.map((r) => 1 / (r.distance + IDW_EPS) ** 2)
  return { outline: blendOutlines(top.map((r) => r.state.o), ws), distance: top[0].distance, used: top }
}

/**
 * 학습자 포먼트에서 그릴 윤곽을 추정한다. 가장 가까운 k개 상태를 거리 역수 제곱으로 섞어 격자 사이를
 * 부드럽게 잇는다. round(0~1)를 주면 두 입술 층을 각각 찾은 뒤 round 비율로 섞는다(입술 모양이 원순
 * 조작을 따라가게). round가 없으면 두 층을 함께 본다(원순을 모르는 녹음 추정용).
 * 반환: { outline, distance, used: [{index, state, distance}] } 또는 null.
 */
export function estimateOutline(grid, f1, f2, { round = null, k = 3, normalize = true } = {}) {
  if (!grid?.states?.length || !Number.isFinite(f1) || !Number.isFinite(f2)) return null
  if (round == null) return blendNearest(rankStates(grid, f1, f2, { normalize }), k)
  const r = clamp01(round)
  const l0 = r < 1 ? blendNearest(rankStates(grid, f1, f2, { layer: 0, normalize }), k) : null
  const l1 = r > 0 ? blendNearest(rankStates(grid, f1, f2, { layer: 1, normalize }), k) : null
  if (!l0) return l1
  if (!l1) return l0
  return {
    outline: blendOutlines([l0.outline, l1.outline], [1 - r, r]),
    distance: (1 - r) * l0.distance + r * l1.distance,
    used: [...l0.used, ...l1.used],
  }
}

/** shapes.json에서 음소 하나. */
export const phonemeById = (shapes, id) => shapes?.phonemes?.find((p) => p.id === id) || null

// ── 그리기 보조(순수) ────────────────────────────────────────────────────────────────

/** 폴리라인 이름 → 윤곽 안의 평탄 배열. */
export const part = (meta, outline, name) => outline[meta.parts.indexOf(name)]

/** segments 표의 해부 구간(예: 'upperLip')을 평탄 배열로 잘라 낸다. 양끝 점 포함. */
export function segment(meta, outline, name) {
  const [partName, from, to] = meta.segments[name]
  return part(meta, outline, partName).slice(from * 2, to * 2 + 2)
}

/** 평탄 배열 → SVG polyline points 문자열(소수 한 자리). */
export const toPoints = (flat) => {
  const out = []
  for (let i = 0; i + 1 < flat.length; i += 2) out.push(`${flat[i].toFixed(1)},${flat[i + 1].toFixed(1)}`)
  return out.join(' ')
}

/**
 * 혀를 닫힌 도형으로: 혀 윤곽(혀뿌리 → 혀끝) 뒤에, 혀끝에서 가장 가까운 구강 바닥 점부터 바닥을 거꾸로
 * 따라 혀뿌리 쪽으로 돌아온다. 혀뿌리와 바닥의 첫 점은 후두덮개 뿌리의 같은 자리다.
 */
export function tonguePolygon(meta, outline) {
  const t = part(meta, outline, 'tongue')
  const floor = segment(meta, outline, 'floor')
  const tx = t[t.length - 2]
  const ty = t[t.length - 1]
  let m = 0
  let best = Infinity
  for (let i = 0; i < floor.length; i += 2) {
    const d = Math.hypot(floor[i] - tx, floor[i + 1] - ty)
    if (d < best) { best = d; m = i }
  }
  const back = []
  for (let i = m; i >= 0; i -= 2) back.push(floor[i], floor[i + 1])
  return [...t, ...back]
}

/** 닫힌 다각형의 넓이 중심(신발끈 공식). 넓이가 0이면 점 평균. */
export function centroid(flat) {
  let a = 0
  let cx = 0
  let cy = 0
  const n = flat.length / 2
  for (let i = 0; i < n; i += 1) {
    const x1 = flat[2 * i]
    const y1 = flat[2 * i + 1]
    const x2 = flat[(2 * i + 2) % flat.length]
    const y2 = flat[(2 * i + 3) % flat.length]
    const c = x1 * y2 - x2 * y1
    a += c
    cx += (x1 + x2) * c
    cy += (y1 + y2) * c
  }
  if (Math.abs(a) < 1e-9) {
    let sx = 0
    let sy = 0
    for (let i = 0; i < n; i += 1) { sx += flat[2 * i]; sy += flat[2 * i + 1] }
    return [sx / n, sy / n]
  }
  return [cx / (3 * a), cy / (3 * a)]
}

/**
 * 연구개 통로(코로 가는 길) 위치: 목젖의 가장 뒤 점과 인두 뒷벽 맨 윗점의 가운데.
 * 비음처럼 연구개가 내려갔을 때 화살표를 여기서 위로 그린다.
 */
export function velicPort(meta, outline) {
  const uv = part(meta, outline, 'uvula')
  const wall = part(meta, outline, 'wall')
  let bx = Infinity
  let by = 0
  for (let i = 0; i < uv.length; i += 2) if (uv[i] < bx) { bx = uv[i]; by = uv[i + 1] }
  const wx = wall[wall.length - 2]
  const wy = wall[wall.length - 1]
  return [(bx + wx) / 2, Math.min(by, wy)]
}

// ── 지연 로더 ────────────────────────────────────────────────────────────────────────
// 성도 단면을 보여 주는 화면에서만 JSON을 받는다(초기 번들·다른 화면에는 비용 없음). 같은 주소는 한 번만 받는다.
const cache = new Map()

export function loadVtlAsset(name, base = '/vtl') {
  const url = `${base}/${name}`
  if (!cache.has(url)) {
    const p = fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${url} ${r.status}`)
      return r.json()
    })
    p.catch(() => cache.delete(url))   // 실패는 다음 시도에서 다시 받게
    cache.set(url, p)
  }
  return cache.get(url)
}

export const loadVtlShapes = (base) => loadVtlAsset('shapes.json', base)
export const loadVtlGrid = (base) => loadVtlAsset('vowel_grid.json', base)
export const vtlWavUrl = (id, base = '/vtl') => `${base}/vowels/${id}.wav`
