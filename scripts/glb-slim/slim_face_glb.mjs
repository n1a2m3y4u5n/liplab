// 3D 얼굴 GLB(realistic_face.glb)의 GPU 메모리 줄이기 — 저사양 기기용(9/29).
// 캔버스 하나에 약 130MB였고 그중 텍스처가 디코딩 뒤 약 98MB(1024² 17장 + 512² 2장, 밉맵 포함), 모프가 약 22MB였다.
// 1) 입 클로즈업에서 거의 안 보이는 텍스처(몸·팔 피부, 속눈썹, 눈동자·각막 색)를 1024 → 512로 줄인다.
//    얼굴 피부·치아·혀 텍스처와 모든 노멀맵(눈 노멀은 원래 512)은 그대로 둔다.
// 2) 코드가 쓰지 않는 CC 전용 모프(Mouth_Smile 등)를 지운다. ARKit 52종, 혀 메시의 모프 전부,
//    frontend/src 어디에든(주석 포함) 이름이 나오는 모프는 남긴다. 코드는 모프를 이름(morphTargetDictionary)으로만 찾는다.
//
// 실행(저장소 루트에서):
//   npm --prefix scripts/glb-slim install
//   node scripts/glb-slim/slim_face_glb.mjs <원본.glb> <출력.glb>
// 원본은 git 기록에 있다: git show 9f08043:frontend/public/models/realistic_face.glb > /tmp/realistic_face.orig.glb
// 같은 원본에 두 번 돌려도 결과가 같다(이미 줄인 파일에 다시 돌려도 바뀌는 것 없음).
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { NodeIO } from '@gltf-transform/core'
import { ALL_EXTENSIONS } from '@gltf-transform/extensions'
import { textureCompress, prune } from '@gltf-transform/functions'
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer'
import sharp from 'sharp'

const [, , SRC, DST] = process.argv
if (!SRC || !DST) { console.error('사용법: node slim_face_glb.mjs <원본.glb> <출력.glb>'); process.exit(2) }

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const SMALL_TEX = /^Std_(Skin_Body|Skin_Arm|Eyelash|Eye_[LR]_Diffuse|Cornea_[LR])/
const SMALL_SIZE = 512

const ARKIT52 = `browDownLeft browDownRight browInnerUp browOuterUpLeft browOuterUpRight cheekPuff cheekSquintLeft
cheekSquintRight eyeBlinkLeft eyeBlinkRight eyeLookDownLeft eyeLookDownRight eyeLookInLeft eyeLookInRight eyeLookOutLeft
eyeLookOutRight eyeLookUpLeft eyeLookUpRight eyeSquintLeft eyeSquintRight eyeWideLeft eyeWideRight jawForward jawLeft
jawOpen jawRight mouthClose mouthDimpleLeft mouthDimpleRight mouthFrownLeft mouthFrownRight mouthFunnel mouthLeft
mouthLowerDownLeft mouthLowerDownRight mouthPressLeft mouthPressRight mouthPucker mouthRight mouthRollLower mouthRollUpper
mouthShrugLower mouthShrugUpper mouthSmileLeft mouthSmileRight mouthStretchLeft mouthStretchRight mouthUpperUpLeft
mouthUpperUpRight noseSneerLeft noseSneerRight tongueOut`.split(/\s+/)

function srcText(dir) {
  let out = ''
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out += srcText(p)
    else if (/\.(jsx?|mjs)$/.test(name)) out += readFileSync(p, 'utf8') + '\n'
  }
  return out
}
const SRC_TEXT = srcText(join(ROOT, 'frontend', 'src'))
const usedInSrc = (n) => new RegExp(`\\b${n}\\b`).test(SRC_TEXT)

const texMB = (doc) => doc.getRoot().listTextures().reduce((s, t) => {
  const [w, h] = t.getSize() || [0, 0]
  return s + (w * h * 4 * 4) / 3 / 1e6
}, 0)
const morphMB = (doc) => doc.getRoot().listMeshes().reduce((s, m) => s + m.listPrimitives().reduce((a, p) => {
  const n = p.getAttribute('POSITION').getCount()
  const t = p.listTargets()
  return a + n * t.length * (t[0]?.listSemantics().length || 0) * 16 / 1e6   // three.js 모프 텍스처: 속성당 RGBA float
}, 0), 0)

await MeshoptDecoder.ready
await MeshoptEncoder.ready
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
})
const doc = await io.read(SRC)
const before = { tex: texMB(doc), morph: morphMB(doc) }

// 1) 텍스처. 이미 512 이하인 것은 다시 인코딩하지 않는다(손실 압축이 거듭되지 않게)
const big = doc.getRoot().listTextures()
  .filter((t) => SMALL_TEX.test(t.getName()) && Math.max(...(t.getSize() || [0])) > SMALL_SIZE)
  .map((t) => t.getName().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
if (big.length) {
  await doc.transform(textureCompress({
    encoder: sharp, targetFormat: 'webp', resize: [SMALL_SIZE, SMALL_SIZE], pattern: new RegExp(`^(${big.join('|')})$`),
  }))
}

// 2) 모프
const kept = new Set(), dropped = new Set()
for (const mesh of doc.getRoot().listMeshes()) {
  const names = mesh.getExtras()?.targetNames
  if (!Array.isArray(names)) continue
  const isTongue = /Tongue/i.test(mesh.getName())
  const keep = names.map((n) => isTongue || ARKIT52.includes(n) || usedInSrc(n))
  if (keep.every(Boolean)) { names.forEach((n) => kept.add(n)); continue }
  for (const prim of mesh.listPrimitives()) {
    const targets = prim.listTargets()
    if (targets.length !== names.length) throw new Error(`${mesh.getName()}: 모프 수(${targets.length})와 이름 수(${names.length})가 다름`)
    targets.forEach((t, i) => { if (!keep[i]) { prim.removeTarget(t); t.dispose() } })
  }
  const w = mesh.getWeights()
  if (w.length) mesh.setWeights(w.filter((_, i) => keep[i]))
  mesh.setExtras({ ...mesh.getExtras(), targetNames: names.filter((_, i) => keep[i]) })
  names.forEach((n, i) => (keep[i] ? kept : dropped).add(n))
}
await doc.transform(prune())

// 코드가 이름으로 찾는 모프가 하나라도 빠졌으면 멈춘다
const missing = [...dropped].filter((n) => !kept.has(n) && usedInSrc(n))
if (missing.length) throw new Error(`코드가 쓰는 모프가 지워짐: ${missing.join(', ')}`)

await io.write(DST, doc)
const after = { tex: texMB(doc), morph: morphMB(doc) }
const onlyDropped = [...dropped].filter((n) => !kept.has(n))
console.log(`텍스처(디코딩·밉맵) ${before.tex.toFixed(1)} → ${after.tex.toFixed(1)} MB`)
console.log(`모프(three.js 모프 텍스처) ${before.morph.toFixed(1)} → ${after.morph.toFixed(1)} MB`)
console.log(`지운 모프 ${onlyDropped.length}개: ${onlyDropped.join(' ')}`)
console.log(`파일 ${(statSync(SRC).size / 1e6).toFixed(2)} → ${(statSync(DST).size / 1e6).toFixed(2)} MB`)
