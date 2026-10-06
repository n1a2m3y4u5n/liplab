// V2·V13·V14 렌더 하네스(docs/avatar-validity-2026-10.md). 앱 코드는 바꾸지 않고 앱의 모듈을 그대로 가져와 쓴다.
//
// - 입모양 표·혀 표: frontend/src/lib/visemeShapes.js
// - 가상 화자 배율·타이밍: frontend/src/lib/talkers.js (talkerShapes, applyTalkerTiming, talkerById)
// - 선행 동시조음: frontend/src/lib/coarticulation.js (빌드 플래그 VITE_COART_E가 없으면 앱처럼 꺼진다)
// - 전환 이징: frontend/src/lib/visemeTiming.js (transitionProgress)
// - 얼굴: frontend/public/models/realistic_face.glb (턱 뼈 CC_Base_JawRoot, jawOpen 1 = 30°)
//
// 한 화면마다 하는 일은 AvatarVRM.jsx의 RealisticFace.useFrame을 줄 단위로 옮긴 것이다(눈 깜빡임만 뺐다. 앱은 2.5~6초마다 무작위로
// 깜빡여 재현이 안 된다). 앱과 다른 점은 시계뿐이다. 앱은 requestAnimationFrame(약 60Hz)과 setTimeout으로 시간을 보내고, 여기서는
// 1/60초 눈금을 결정론적으로 돌리며 두 눈금마다(30fps) 한 장을 찍는다. 카메라는 MediaPipe가 얼굴 전체를 보도록 정면 전신 얼굴로
// 바꿨다(앱은 입 클로즈업). 538 정면 영상(640×360)과 눈꼬리 사이 거리가 비슷하도록 맞춘다.
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS, VISEME_TONGUE, ACTIVE_TONGUE_KEYS } from '@app/lib/visemeShapes.js'
import { transitionProgress } from '@app/lib/visemeTiming.js'
import { talkerShapes, talkerById, applyTalkerTiming, TALKERS, DEFAULT_TALKER } from '@app/lib/talkers.js'
import { applyCoarticulation, coartShape, coartWeight, COART_E_ENABLED } from '@app/lib/coarticulation.js'
import glbUrl from '@front/public/models/realistic_face.glb?url'

const JAW_BONE_NAME = 'CC_Base_JawRoot'
const JAW_OPEN_MAX_RAD = THREE.MathUtils.degToRad(30)
const ACTIVE_KEY_SET = new Set(ACTIVE_MORPH_KEYS)
const EMPTY = {}
const TICK_S = 1 / 60

const S = { renderer: null, scene: null, camera: null, canvas: null, meshes: [], tongue: null, jaw: null, cfg: null }

function gradientBackground() {
  // 앱 무대 배경(bg-gradient-to-b from-slate-800 to-slate-900)
  const c = document.createElement('canvas')
  c.width = 4; c.height = 256
  const g = c.getContext('2d')
  const gr = g.createLinearGradient(0, 0, 0, 256)
  gr.addColorStop(0, '#1e293b'); gr.addColorStop(1, '#0f172a')
  g.fillStyle = gr; g.fillRect(0, 0, 4, 256)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

export async function init(cfg = {}) {
  const w = cfg.w || 640, h = cfg.h || 360
  S.cfg = { w, h, fov: cfg.fov || 16, camPos: cfg.camPos || [0, 1.66, 1.6], target: cfg.target || [0, 1.66, 0] }
  const canvas = document.createElement('canvas')
  canvas.width = w; canvas.height = h
  document.body.appendChild(canvas)
  // R3F Canvas 기본값과 같게: antialias, sRGB 출력, ACES 톤매핑. preserveDrawingBuffer는 캡처용.
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(1)
  renderer.setSize(w, h, false)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  const scene = new THREE.Scene()
  scene.background = gradientBackground()
  scene.add(new THREE.AmbientLight(0xffffff, 1.2))
  const d1 = new THREE.DirectionalLight(0xffffff, 1.0); d1.position.set(1, 2, 2); scene.add(d1)
  const d2 = new THREE.DirectionalLight(0xffffff, 0.4); d2.position.set(-1, 0, 1); scene.add(d2)
  const camera = new THREE.PerspectiveCamera(S.cfg.fov, w / h, 0.1, 1000)
  camera.position.set(...S.cfg.camPos)
  camera.lookAt(new THREE.Vector3(...S.cfg.target))
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder)
  const gltf = await loader.loadAsync(glbUrl)
  scene.add(gltf.scene)
  S.meshes = []; S.tongue = null
  gltf.scene.traverse((o) => {
    if (o.isMesh && o.morphTargetDictionary && o.morphTargetInfluences) {
      S.meshes.push(o)
      const dct = o.morphTargetDictionary
      if ('tongueOut' in dct && !('mouthSmileLeft' in dct)) S.tongue = o
    }
  })
  const jb = gltf.scene.getObjectByName(JAW_BONE_NAME)
  S.jaw = jb ? { bone: jb, restZ: jb.rotation.z } : null
  Object.assign(S, { renderer, scene, camera, canvas })
  const gl = renderer.getContext()
  const dbg = gl.getExtension('WEBGL_debug_renderer_info')
  return {
    meshes: S.meshes.length, tongue: !!S.tongue, jaw: !!S.jaw, coartE: COART_E_ENABLED,
    glRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    talkers: TALKERS.map((t) => t.id),
  }
}

// ── RealisticFace 상태(인스턴스 하나) ──
function freshState() {
  return { cur: {}, from: {}, lastKey: null, elapsed: 0, tongue: {}, extra: new Set() }
}

function resetFace() {
  for (const m of S.meshes) m.morphTargetInfluences.fill(0)
  if (S.jaw) S.jaw.bone.rotation.z = S.jaw.restZ
}

function applyMorph(st, key, value) {
  st.cur[key] = value
  for (const mesh of S.meshes) {
    const idx = mesh.morphTargetDictionary?.[key]
    if (idx !== undefined) mesh.morphTargetInfluences[idx] = value
  }
}

// AvatarVRM.jsx RealisticFace.useFrame과 같은 계산. props: {visemeId, transitionMs, durationMs, speed, talker, lipVowel} 또는 rawFrame.
function step(st, delta, props) {
  const rawFrame = props.rawFrame || null
  const shapes = talkerShapes(props.talker)
  const textTarget = coartShape(shapes, props.visemeId, props.lipVowel, coartWeight(props.talker)) || EMPTY
  const shapeKey = props.lipVowel == null ? props.visemeId : `${props.visemeId}|${props.lipVowel}`
  const target = rawFrame || textTarget
  const LERP = Math.min(1, delta * (rawFrame ? 34 : 22))
  let eased = null
  if (!rawFrame) {
    if (st.lastKey !== shapeKey) {
      st.lastKey = shapeKey
      st.from = { ...st.cur }
      st.elapsed = 0
    } else {
      st.elapsed += delta * 1000
    }
    eased = transitionProgress(st.elapsed, props.transitionMs, props.durationMs, props.speed)
  } else {
    st.lastKey = null
  }
  const nextWeight = (key, tgt) => (eased == null
    ? THREE.MathUtils.lerp(st.cur[key] || 0, tgt, LERP)
    : (st.from[key] || 0) + (tgt - (st.from[key] || 0)) * eased)
  if (rawFrame) for (const key in rawFrame) if (!ACTIVE_KEY_SET.has(key)) st.extra.add(key)
  for (const key of ACTIVE_MORPH_KEYS) applyMorph(st, key, nextWeight(key, target[key] || 0))
  for (const key of st.extra) {
    const tgt = target[key] || 0
    const next = THREE.MathUtils.lerp(st.cur[key] || 0, tgt, LERP)
    if (tgt === 0 && Math.abs(next) < 1e-3) { applyMorph(st, key, 0); st.extra.delete(key) } else applyMorph(st, key, next)
  }
  if (S.jaw) S.jaw.bone.rotation.z = S.jaw.restZ + JAW_OPEN_MAX_RAD * (st.cur.jawOpen || 0)
  const TONGUE_LERP = Math.min(1, delta * 15)
  if (S.tongue && !rawFrame) {
    const tT = VISEME_TONGUE[props.visemeId] || EMPTY
    for (const key of ACTIVE_TONGUE_KEYS) {
      const next = THREE.MathUtils.lerp(st.tongue[key] || 0, tT[key] || 0, TONGUE_LERP)
      st.tongue[key] = next
      const idx = S.tongue.morphTargetDictionary?.[key]
      if (idx !== undefined) S.tongue.morphTargetInfluences[idx] = next
    }
  }
}

function grab(q) {
  S.renderer.render(S.scene, S.camera)
  return S.canvas.toDataURL('image/jpeg', q)
}

/**
 * 엔진 프레임 재생(LipSyncPlayer3D와 같은 순서: applyTalkerTiming → applyCoarticulation, 프레임 길이는 duration_ms / speed).
 * 반환: images(30fps JPEG data URL), schedule([{v, t0, t1, i}] 영상 시각 ms), speech [t0, t1].
 */
export function renderText({ frames, talker = 'default', seed = 0, speed = 1, leadMs = 400, tailMs = 400, q = 0.95, maxImages = 0 }) {
  const tk = talker === 'default' ? DEFAULT_TALKER : talkerById(talker)
  const vis = applyCoarticulation(applyTalkerTiming(frames, tk, seed))
  const sched = []
  let t = leadMs
  vis.forEach((f, i) => {
    const len = (Number(f.duration_ms) || 0) / speed
    sched.push({ i, v: f.viseme, t0: t, t1: t + len, tr: f.transition_ms, dur: f.duration_ms, lv: f.coart_v ?? null })
    t += len
  })
  const endMs = t
  const total = endMs + tailMs
  resetFace()
  const st = freshState()
  const images = []
  const nTicks = Math.ceil(total / (TICK_S * 1000)) + 1
  let j = 0
  for (let n = 0; n < nTicks; n++) {
    const now = n * TICK_S * 1000
    let props
    if (now < leadMs) {
      props = { visemeId: 15, transitionMs: undefined, durationMs: undefined, speed, talker: tk, lipVowel: null }
    } else {
      while (j + 1 < sched.length && sched[j + 1].t0 <= now) j++
      const s = sched[Math.min(j, sched.length - 1)]
      props = { visemeId: s.v, transitionMs: s.tr, durationMs: s.dur, speed, talker: tk, lipVowel: s.lv }
    }
    step(st, TICK_S, props)
    if (n % 2 === 0) {
      images.push(grab(q))
      if (maxImages && images.length >= maxImages) break
    }
  }
  return { images, schedule: sched.map(({ i, v, t0, t1, lv }) => ({ i, v, t0, t1, lv })), speech: [leadMs, endMs], fps: 30 }
}

/**
 * 52계수 시퀀스 재생(음성구동 A4·웹캠 거울과 같은 bsFrameRef 경로: 원본 계수를 목표로 LERP 34/s). frames: [[값...]], names: [이름].
 * 계수 시퀀스는 fps로 표본을 잡고(Audio2FaceAvatar: idx = floor(t·fps)), 얼굴이 잡히지 않은 칸(null)은 앞 값을 이어 쓴다.
 */
export function renderRaw({ names, frames, fps = 30, leadMs = 0, tailMs = 0, q = 0.95 }) {
  resetFace()
  const st = freshState()
  const images = []
  const durMs = (frames.length / fps) * 1000
  const nTicks = Math.ceil((leadMs + durMs + tailMs) / (TICK_S * 1000))
  let last = null
  const objs = frames.map((row) => {
    if (!row) return null
    const o = {}
    for (let i = 0; i < names.length; i++) if (names[i] && names[i][0] !== '_') o[names[i]] = row[i]
    return o
  })
  for (let n = 0; n < nTicks; n++) {
    const now = n * TICK_S * 1000 - leadMs
    let raw = null
    if (now >= 0 && now < durMs) {
      const idx = Math.min(objs.length - 1, Math.floor((now / 1000) * fps))
      raw = objs[idx] || last
      if (objs[idx]) last = objs[idx]
    }
    if (raw) step(st, TICK_S, { rawFrame: raw, visemeId: 15 })
    else step(st, TICK_S, { visemeId: 15, transitionMs: undefined, durationMs: undefined, speed: 1, talker: DEFAULT_TALKER, lipVowel: null })
    if (n % 2 === 0) images.push(grab(q))
  }
  return { images, fps: 30, leadMs }
}

/** 정지 자세 한 장(카메라 맞추기·점검용). */
export function still(visemeId = 15, q = 0.95) {
  resetFace()
  const st = freshState()
  for (let n = 0; n < 30; n++) step(st, TICK_S, { visemeId, transitionMs: undefined, durationMs: undefined, speed: 1, talker: DEFAULT_TALKER, lipVowel: null })
  return grab(q)
}

export function setCamera({ camPos, target, fov }) {
  if (fov) { S.camera.fov = fov; S.camera.updateProjectionMatrix() }
  if (camPos) S.camera.position.set(...camPos)
  if (target) S.camera.lookAt(new THREE.Vector3(...target))
  S.cfg = { ...S.cfg, ...(camPos ? { camPos } : {}), ...(target ? { target } : {}), ...(fov ? { fov } : {}) }
  return S.cfg
}

window.__v2 = { init, renderText, renderRaw, still, setCamera, VISEME_BLENDSHAPES }
window.__v2ready = true
