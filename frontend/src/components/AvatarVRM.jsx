import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js'

const MODEL_URL = '/models/realistic_face.glb'
// 새 아바타(CC 모델)는 EXT_meshopt_compression 압축이라 meshopt 디코더를 붙여야 로드됨.
const withMeshopt = (loader) => loader.setMeshoptDecoder(MeshoptDecoder)
// CC(Character Creator) 모델은 ARKit jawOpen 모프가 피부를 거의 움직이지 않는다(실측 −0.5mm).
// 입 벌림은 턱 뼈(CC_Base_JawRoot)가 담당한다 — 이 뼈에 아래 이·혀·턱 피부가 스키닝돼 있어
// 로컬 Z축 +회전이 곧 벌림이다(20° 회전 시 아랫입술 −1.1cm·턱 −1.9cm 실측). 그래서 jawOpen
// 가중치(0~1)를 이 각도로 옮겨 뼈를 돌린다. 뼈가 없는 모델이면 모프만 적용한다.
const JAW_BONE_NAME = 'CC_Base_JawRoot'
const JAW_OPEN_MAX_RAD = THREE.MathUtils.degToRad(30)
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS, VISEME_TONGUE, ACTIVE_TONGUE_KEYS } from '../lib/visemeShapes'
import { MIRROR_KEYS } from '../lib/mouthMirror'
import MouthFallback2D from './MouthFallback2D'
import { markContextLost } from '../lib/gpuBudget'
import { guardRendererFactory } from '../lib/safeRenderer'
import { transitionProgress } from '../lib/visemeTiming'
import { talkerShapes } from '../lib/talkers'
import { coartShape, coartWeight } from '../lib/coarticulation'
import { mapRawFrame } from '../lib/rigMap'

const EMPTY = {}
const ACTIVE_KEY_SET = new Set(ACTIVE_MORPH_KEYS)
const MIRROR_KEY_SET = new Set(MIRROR_KEYS)
// GLB 로드가 실패하면 이만큼 기다렸다가 다시 시도한다(회차마다 늘린다). 네트워크가 잠깐 끊긴 경우를 되살린다.
const GLB_RETRY_MS = 3000
const GLB_RETRY_MAX = 2
// 음성 구동·웹캠 거울(bsFrameRef)의 원본 MediaPipe 계수를 CC 두상에 맞게 고쳐 넣는다(lib/rigMap, V15 5절). 비교할 때만
// VITE_RIG_MAP=0으로 빌드해 끈다. 손거울(mirrorRef)은 자체 증폭·데드존(lib/mouthMirror)을 거친 값이라 여기에 넣지 않는다.
const RIG_MAP_ON = import.meta.env?.VITE_RIG_MAP !== '0'

/**
 * 한국어 Viseme → 3D 입모양 렌더링
 *
 * 표준 ARKit 블렌드셰이프(jawOpen, mouthPucker, mouthFunnel, mouthClose 등) 정밀
 * 매핑(../lib/visemeShapes)에 더해, 혀(tongue) 전용 모프까지 적용해 한국어 조음을
 * 정확히 표현한다. WebGL 미지원 / 모델 로드 실패 시 2D 입모양으로 폴백한다.
 *
 * mirrorRef(축 F)가 주어지면 웹캠에서 읽은 사용자 입모양 계수로 아바타를 구동한다
 * (거울 모드). ref로 받는 이유는 웹캠이 초당 30프레임으로 값을 갱신하기 때문 —
 * 상태로 올리면 매 프레임 리렌더가 발생한다.
 *
 * (병합 메모: 혀 렌더링[YMJ]과 WebGL 폴백·카메라 경쟁조건 수정[feat/curriculum]이
 *  깨진 머지로 파일에 두 벌 복제돼 빌드가 깨져 있었다 → 두 기능을 모두 살려 단일화.)
 */
function RealisticFace({ visemeId = 15, xray = false, bsFrameRef = null, mirrorRef = null, modelUrl = MODEL_URL,
  transitionMs, durationMs, speed = 1, talker = null, lipVowel = null }) {
  const { scene: shared } = useGLTF(modelUrl, false, false, withMeshopt)
  // useGLTF는 캐시된 같은 scene 객체를 돌려준다. three.js 객체는 부모를 하나만 가질 수 있어, 그대로
  // <primitive>로 쓰면 한 화면에 아바타가 둘 이상일 때(다자 대화·웹캠 거울) 마지막 것만 보였다.
  // 인스턴스마다 뼈대까지 복제하고(형상은 공유) 재질도 복제해 투명 두상 토글이 서로 번지지 않게 한다.
  const scene = useMemo(() => {
    const c = cloneSkinned(shared)
    c.traverse((o) => {
      if (o.isMesh && o.material) o.material = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone()
    })
    return c
  }, [shared])
  const meshesRef = useRef([])
  const tongueMeshRef = useRef(null)
  const jawRef = useRef(null)          // { bone, restZ } — 턱 뼈와 기본 각도
  const currentWeightsRef = useRef({})
  const extraKeysRef = useRef(new Set())   // 기본 키 집합 밖에서 원본 프레임이 움직인 모프(0으로 돌아올 때까지 보간)
  const tongueWeightsRef = useRef({})
  // 텍스트 입모양 전환(lib/visemeTiming): 입모양이 바뀐 순간의 가중치(출발점)와 그 뒤 흐른 시간
  const fromWeightsRef = useRef({})
  const lastVisemeRef = useRef(null)
  const elapsedRef = useRef(0)
  const timingRef = useRef({ transitionMs, durationMs, speed })
  timingRef.current = { transitionMs, durationMs, speed }
  // 가상 화자(lib/talkers, 계획 2-2): 입 벌림·입술 폭·돌출·동시조음 배율을 곱한 목표 표. 화자마다 한 번 만들어 두고 화면마다 읽기만 한다.
  const shapesRef = useRef(VISEME_BLENDSHAPES)
  shapesRef.current = talkerShapes(talker)
  // 선행 동시조음(lib/coarticulation, 3D 모션 E): 입 안쪽 자음 프레임이면 입술 모프만 섞을 모음(lipVowel) 쪽으로 섞은 목표.
  // 입모양이 바뀔 때(렌더) 한 번 캐시에서 읽고, 화면마다는 이 목표를 읽기만 한다. lipVowel이 없으면 표의 모양 그대로다.
  const textTargetRef = useRef(EMPTY)
  textTargetRef.current = coartShape(shapesRef.current, visemeId, lipVowel, coartWeight(talker)) || EMPTY
  // 전환 출발점을 다시 잡는 기준: 같은 입모양이라도 섞을 모음이 바뀌면 목표가 달라진다.
  const shapeKey = lipVowel == null ? visemeId : `${visemeId}|${lipVowel}`
  const skinMatsRef = useRef([])   // 투명(X-ray) 모드에서 반투명화할 피부 재질
  const xrayAppliedRef = useRef(null)

  // Find all meshes with morph targets on first render
  if (meshesRef.current.length === 0) {
    scene.traverse((obj) => {
      if (!obj.isMesh) return
      // 피부 재질 수집(투명 두상용): 겉면(body/skin)만. 혀·치아·눈(안구=high-poly 메시)은 제외.
      // 이 GLB에서 high-poly 메시는 eyeLook 모프 8개만 가진 안구라, 포함하면 xray 시 눈이 투명해진다.
      const mats = Array.isArray(obj.material) ? obj.material : (obj.material ? [obj.material] : [])
      const mn = ((obj.name || '') + ' ' + (mats[0]?.name || '')).toLowerCase()
      if (/(^|[.\s_])(body|skin)/.test(mn) && !/teeth|tongue|eye|cornea|high-poly/.test(mn)) {
        for (const m of mats) skinMatsRef.current.push({ m, op0: m.opacity, tr0: m.transparent, dw0: m.depthWrite })
      }
      if (obj.morphTargetDictionary && obj.morphTargetInfluences) {
        meshesRef.current.push(obj)
        // 혀 메시 식별: tongueOut은 있고 mouthSmileLeft(얼굴 전용)는 없는 메시.
        // (얼굴=둘 다 있음, 치아=둘 다 없음, 혀=tongueOut만 있음 → 유일하게 구분됨)
        const dict = obj.morphTargetDictionary
        if ('tongueOut' in dict && !('mouthSmileLeft' in dict)) {
          tongueMeshRef.current = obj
        }
      }
    })
    const jawBone = scene.getObjectByName(JAW_BONE_NAME)
    if (jawBone) jawRef.current = { bone: jawBone, restZ: jawBone.rotation.z }
  }

  // 텍스트 입모양은 쉴 때 그리지 않는다(Canvas frameloop="demand"). 입모양·시간·투명 모드가 바뀌면 여기서 깨우고, 전환이 끝나
  // 모든 가중치가 목표에 닿으면 useFrame이 다음 화면을 더 요청하지 않는다. 예전에는 멈춰 있어도 초당 60번 다시 그렸다.
  const invalidate = useThree((st) => st.invalidate)
  useEffect(() => { invalidate() }, [visemeId, lipVowel, xray, transitionMs, durationMs, speed, talker, invalidate])

  // 아이들 모션 D(9/28): 눈 깜빡임. 쉴 때 그리지 않는 원칙(frameloop demand)을 지키려고 호흡처럼 계속 움직이는 모션은 넣지 않고,
  // 2.5~6초마다 깜빡이는 약 0.19초 동안만 화면을 요청한다. 텍스트 입모양에만 적용(음성구동·거울은 원본 계수를 그대로 쓴다).
  const blinkRef = useRef({ t: -1, w: 0 })
  useEffect(() => {
    if (bsFrameRef || mirrorRef) return undefined
    let timer
    const schedule = () => {
      timer = setTimeout(() => { blinkRef.current.t = 0; invalidate(); schedule() }, 2500 + Math.random() * 3500)
    }
    schedule()
    return () => clearTimeout(timer)
  }, [bsFrameRef, mirrorRef, invalidate])

  useFrame((state, rawDelta) => {
    // 쉬었다 다시 그리는 첫 화면은 경과 시간이 길다(마지막 화면 뒤 전부). 그대로 쓰면 보간이 한 번에 목표로 튀므로 자른다.
    const delta = Math.min(rawDelta, 0.05)
    // 투명 두상 토글 — 피부만 반투명화해 안쪽 혀·치아를 드러냄(계획서 F). 상태 바뀔 때만 적용.
    if (xrayAppliedRef.current !== xray) {
      xrayAppliedRef.current = xray
      for (const s of skinMatsRef.current) {
        if (xray) { s.m.transparent = true; s.m.opacity = 0.26; s.m.depthWrite = false }
        else { s.m.transparent = s.tr0; s.m.opacity = s.op0; s.m.depthWrite = s.dw0 }
        s.m.needsUpdate = true
      }
    }
    if (meshesRef.current.length === 0) return

    // 목표 블렌드셰이프의 우선순위(병합 메모):
    //   ① 음성구동(A4)·웹캠 실시간 프레임 bsFrameRef: 원본 52 블렌드셰이프를 리그 보정 사상(lib/rigMap)으로 고쳐 적용
    //   ② 웹캠 거울(축 F) mirrorRef — 사용자 입모양 계수가 목표
    //   ③ 텍스트→비심 매핑 VISEME_BLENDSHAPES(가상 화자면 그 배율을 곱한 표, 동시조음이 켜져 있으면 입술을 섞은 모양)
    const rawFrame = bsFrameRef?.current ? (RIG_MAP_ON ? mapRawFrame(bsFrameRef.current) : bsFrameRef.current) : null
    const mirror = !rawFrame ? (mirrorRef?.current || null) : null
    const target = rawFrame || mirror || textTargetRef.current
    // A4 프레임은 이미 30fps 시퀀스라 빠르게 따라가고, 나머지는 부드럽게 전환(~45ms).
    const LERP = Math.min(1, delta * (rawFrame ? 34 : 22))
    // 텍스트 입모양(음성구동·거울이 아닐 때)은 프레임의 전환 시간으로 옮긴다: 입모양이 바뀌면 지금 가중치를 출발점으로 잡고,
    // transition_ms(프레임 길이의 60% 이하, 재생 속도 반영) 동안 이징으로 목표까지 간 뒤 멈춘다. 시간이 없으면 예전 방식.
    let eased = null
    if (!rawFrame && !mirror) {
      if (lastVisemeRef.current !== shapeKey) {
        lastVisemeRef.current = shapeKey
        fromWeightsRef.current = { ...currentWeightsRef.current }
        elapsedRef.current = 0
      } else {
        elapsedRef.current += delta * 1000
      }
      const tm = timingRef.current
      eased = transitionProgress(elapsedRef.current, tm.transitionMs, tm.durationMs, tm.speed)
    } else {
      lastVisemeRef.current = null   // 음성구동·거울이 끝나고 텍스트로 돌아오면 그때 가중치에서 새로 출발
    }
    const nextWeight = (key, tgt) => (eased == null
      ? THREE.MathUtils.lerp(currentWeightsRef.current[key] || 0, tgt, LERP)
      : (fromWeightsRef.current[key] || 0) + (tgt - (fromWeightsRef.current[key] || 0)) * eased)

    /*
      보간할 키 집합. mirrorRef를 받은 인스턴스는 **항상** MIRROR_KEYS(=ACTIVE_MORPH_KEYS의 상위집합)를,
      아니면 ACTIVE_MORPH_KEYS를 돈다. 목표 맵에 없는 키는 0으로 읽히므로, 거울 모드를 끄면 거울에서만
      쓰던 모프(jawForward·cheekPuff 등)가 자동으로 0으로 복귀한다.
      — 개발일지 3절의 함정: 매 프레임 '사용 키 목록'만 보간하면, 목록에서 빠진 키는
        아무도 0으로 되돌리지 않아 직전 값이 얼굴에 남는다.
      원본 프레임(음성구동 A4·웹캠 bsFrameRef)은 이 집합 밖의 모프(눈 찡그림·눈썹 등)도 움직인다. 그런 키는
      extraKeysRef에 모아 두고, 프레임이 멈추거나 키가 빠져도 0에 닿을 때까지 보간한다(예전에는 재생이
      끝나면 마지막 값으로 얼굴에 굳었다).
    */
    const baseKeys = mirrorRef ? MIRROR_KEYS : ACTIVE_MORPH_KEYS
    const baseSet = mirrorRef ? MIRROR_KEY_SET : ACTIVE_KEY_SET
    const extra = extraKeysRef.current
    if (rawFrame) for (const key in rawFrame) if (!baseSet.has(key)) extra.add(key)

    // 얼굴·턱 모프 — 모든 메시에 이름으로 일괄 적용 (jawOpen은 혀도 함께 따라감)
    const applyMorph = (key, value) => {
      currentWeightsRef.current[key] = value
      for (const mesh of meshesRef.current) {
        const idx = mesh.morphTargetDictionary?.[key]
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = value
        }
      }
    }
    for (const key of baseKeys) {
      applyMorph(key, nextWeight(key, target[key] || 0))
    }
    for (const key of extra) {
      const tgt = target[key] || 0
      const next = THREE.MathUtils.lerp(currentWeightsRef.current[key] || 0, tgt, LERP)
      if (tgt === 0 && Math.abs(next) < 1e-3) { applyMorph(key, 0); extra.delete(key) }   // 제자리로 돌아왔다
      else applyMorph(key, next)
    }

    // 턱 뼈 — 보간된 jawOpen 가중치를 그대로 각도로 옮긴다(모프와 같은 타이밍으로 움직인다).
    const jaw = jawRef.current
    if (jaw) {
      jaw.bone.rotation.z = jaw.restZ + JAW_OPEN_MAX_RAD * (currentWeightsRef.current.jawOpen || 0)
    }

    // 혀 전용 모프 — 혀 메시에만 적용해 얼굴 왜곡을 방지 (mesh-scoped)
    // 혀는 얼굴보다 살짝 느리게 보간해 '이동'이 눈에 띄도록 한다 (~65ms).
    const TONGUE_LERP = Math.min(1, delta * 15)
    const tongue = tongueMeshRef.current
    if (tongue && !rawFrame) {
      // 거울 모드에선 혀를 중립으로 — 웹캠은 혀를 추적하지 못하므로(입 안이 안 보임)
      // 직전 viseme의 혀 위치를 그대로 두면 사용자 입모양과 어긋난 조음이 표시된다.
      const tTarget = mirror ? EMPTY : (VISEME_TONGUE[visemeId] || EMPTY)
      for (const key of ACTIVE_TONGUE_KEYS) {
        const tgt = tTarget[key] || 0
        const cur = tongueWeightsRef.current[key] || 0
        const next = THREE.MathUtils.lerp(cur, tgt, TONGUE_LERP)
        tongueWeightsRef.current[key] = next

        const idx = tongue.morphTargetDictionary?.[key]
        if (idx !== undefined) {
          tongue.morphTargetInfluences[idx] = next
        }
      }
    }

    // 눈 깜빡임: 닫힘 70ms → 잠깐 머묾 20ms → 뜸 100ms. 진행 중이면 다음 화면을 요청한다.
    const blink = blinkRef.current
    let blinking = false
    if (!rawFrame && !mirror && blink.t >= 0) {
      blink.t += delta * 1000
      const t = blink.t
      const w = t < 70 ? t / 70 : t < 90 ? 1 : t < 190 ? 1 - (t - 90) / 100 : 0
      const eased2 = w * w * (3 - 2 * w)
      for (const mesh of meshesRef.current) {
        const d = mesh.morphTargetDictionary
        if (d?.eyeBlinkLeft !== undefined) mesh.morphTargetInfluences[d.eyeBlinkLeft] = eased2
        if (d?.eyeBlinkRight !== undefined) mesh.morphTargetInfluences[d.eyeBlinkRight] = eased2
      }
      if (t >= 190) blink.t = -1
      else blinking = true
    }

    // 아직 움직이는 중이면 다음 화면을 요청한다(음성구동·거울은 Canvas가 늘 그리므로 해당 없음).
    if (!rawFrame && !mirror) {
      let moving = blinking || extra.size > 0 || (eased != null && eased < 1)
      if (!moving) {
        for (const key of baseKeys) {
          if (Math.abs((currentWeightsRef.current[key] || 0) - (target[key] || 0)) > 1e-3) { moving = true; break }
        }
      }
      if (!moving && tongue) {
        const tT = VISEME_TONGUE[visemeId] || EMPTY
        for (const key of ACTIVE_TONGUE_KEYS) {
          if (Math.abs((tongueWeightsRef.current[key] || 0) - (tT[key] || 0)) > 1e-3) { moving = true; break }
        }
      }
      if (moving) state.invalidate()
    }
  })

  return <primitive object={scene} />
}

// 측면 보기 F(9/28 다시 구현): 원순 모음·입술 내밂처럼 정면에서 잘 안 보이는 앞뒤 움직임을 옆에서 본다. 카메라를 얼굴 둘레(반경 그대로)로
// 옆 70°까지 이징으로 돌리고, 도는 동안만 화면을 요청한다(쉴 때 그리지 않는 원칙). 사용자가 손으로 돌리는 범위도 측면까지 넓힌다.
const ORBIT_TARGET = new THREE.Vector3(0, 1.652, 0)
const SIDE_AZIMUTH = (70 * Math.PI) / 180

function CameraRig({ view }) {
  const camera = useThree((st) => st.camera)
  const invalidate = useThree((st) => st.invalidate)
  const goal = useRef(0)
  useEffect(() => { goal.current = view === 'side' ? SIDE_AZIMUTH : 0; invalidate() }, [view, invalidate])
  useFrame((state, rawDelta) => {
    const off = camera.position.clone().sub(ORBIT_TARGET)
    const r = Math.hypot(off.x, off.z)
    const az = Math.atan2(off.x, off.z)
    const d = goal.current - az
    if (Math.abs(d) < 0.002) return
    const next = az + d * Math.min(1, Math.min(rawDelta, 0.05) * 7)
    camera.position.set(ORBIT_TARGET.x + r * Math.sin(next), camera.position.y, ORBIT_TARGET.z + r * Math.cos(next))
    camera.lookAt(ORBIT_TARGET)
    state.invalidate()
  })
  return null
}

/** WebGL 지원 여부 감지 (컨텍스트 생성 실패 시 false). 페이지에서 한 번만 재고 시험용 컨텍스트는 바로 놓는다.
 * 예전에는 아바타가 마운트될 때마다 시험용 컨텍스트를 새로 만들고 놓지 않아(문항마다 하나), 렌더러 컨텍스트와 함께
 * 브라우저의 활성 WebGL 컨텍스트 한도(크롬 16)로 쌓였다. */
let webglSupported = null
function detectWebGL() {
  if (webglSupported !== null) return webglSupported
  if (typeof document === 'undefined') return true
  try {
    const canvas = document.createElement('canvas')
    const gl = window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    webglSupported = !!gl
    gl?.getExtension?.('WEBGL_lose_context')?.loseContext()
  } catch {
    webglSupported = false
  }
  return webglSupported
}

/**
 * 3D 렌더/로드 중 오류를 잡아 2D 폴백으로 전환하는 경계.
 * GLB 로드 실패는 useGLTF(suspend-react) 캐시에 오류째 남아, 그대로 두면 새로고침 전까지 모든 3D 아바타가
 * 같은 오류를 곧바로 다시 던진다. 그래서 로드 실패를 잡으면 그 URL을 캐시에서 지우고 잠시 뒤 다시 시도한다
 * (GLB_RETRY_MAX번까지). URL이 바뀌면 경계를 새로 시작하고, 새로 마운트되는 아바타는 지운 캐시로 다시 받는다.
 */
class GLErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
    this.retries = 0
    this.retryTimer = null
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error) {
    // useLoader는 로더 오류를 'Could not load <url>: …'로 감싸 던진다. 렌더 오류라면 멀쩡한 캐시는 두고 다시 시도하지 않는다.
    if (!/^Could not load/.test(error?.message || '')) return
    if (this.props.url) { try { useGLTF.clear(this.props.url) } catch { /* noop */ } }
    if (this.retries < GLB_RETRY_MAX) {
      this.retries += 1
      clearTimeout(this.retryTimer)
      this.retryTimer = setTimeout(() => this.setState({ failed: false }), GLB_RETRY_MS * this.retries)
    }
  }
  componentDidUpdate(prevProps) {
    if (prevProps.url !== this.props.url) {
      this.retries = 0
      clearTimeout(this.retryTimer)
      if (this.state.failed) this.setState({ failed: false })
    }
  }
  componentWillUnmount() {
    clearTimeout(this.retryTimer)
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

// modelUrl: 다른 얼굴 GLB(같은 CC 두상 규격 — ARKit 52 + 혀 모프 + CC_Base_JawRoot). 다자 대화가 화자마다 다르게 준다(H-6).
// talker: 가상 화자(lib/talkers). 텍스트 입모양에만 쓰고 음성구동·거울 프레임은 그대로 둔다.
// lipVowel: 선행 동시조음(lib/coarticulation)에서 이 프레임이 입술을 섞을 모음 입모양(프레임의 coart_v). 없으면 섞지 않는다.
// flat: true면 캔버스를 만들지 않고 2D 입모양만 그린다(여러 명 대화의 저사양 모드, lib/gpuBudget).
export default function AvatarVRM({ visemeId = 15, xray = false, bsFrameRef = null, mirrorRef = null, modelUrl = MODEL_URL,
  transitionMs, durationMs, speed, view = 'front', talker = null, lipVowel = null, flat = false }) {
  const [webglOK] = useState(detectWebGL)
  // GPU 메모리가 모자라 브라우저가 컨텍스트를 거두면 캔버스가 까맣게 멈춘다. 그때는 이 아바타를 2D로 바꾸고
  // (캔버스를 내려 남은 GPU 메모리도 돌려준다) 여러 캔버스를 띄우는 화면이 2D로 가도록 알린다.
  const [ctxLost, setCtxLost] = useState(false)
  // 시험용 컨텍스트는 됐는데 실제 렌더러(WebGL 컨텍스트) 생성이 실패하면 R3F가 오류 경계로 넘기지 않아 검은 상자만 남았다.
  // 생성기를 감싸 실패를 받으면 2D로 바꾸고, 이 페이지의 다음 아바타는 처음부터 2D로 그린다(lib/safeRenderer).
  const [glFailed, setGlFailed] = useState(false)
  const glFactory = useMemo(() => guardRendererFactory(
    (props) => new THREE.WebGLRenderer(props),
    () => { webglSupported = false; setGlFailed(true); markContextLost() },
  ), [])
  const onCreated = ({ gl }) => {
    gl.domElement.addEventListener('webglcontextlost', () => {
      setCtxLost(true)
      markContextLost()
    }, { once: true })
  }
  const fallback = <MouthFallback2D visemeId={visemeId} />

  if (!webglOK || ctxLost || glFailed || flat) return <div className="w-full h-full">{fallback}</div>

  return (
    <GLErrorBoundary url={modelUrl} fallback={<div className="w-full h-full">{fallback}</div>}>
      <div className="w-full h-full">
        {/*
          카메라는 Canvas에 직접 지정한다. 예전처럼 <PerspectiveCamera makeDefault>를
          자식으로 두면, OrbitControls가 카메라 위치(입 클로즈업)가 설정되기 전에
          기본 위치 [0,0,5]를 읽어 얼굴 전체(눈)를 비추는 경쟁 조건이 생긴다
          (StrictMode에서 특히 재현). Canvas camera는 렌더러 생성 시점에 확정되므로
          OrbitControls가 항상 올바른 입 클로즈업 위치를 읽는다.
          touch-action: OrbitControls가 연결하면서 이벤트 요소(Canvas 바깥 div)에 인라인으로 none을 걸어,
          휴대폰에서 아바타 위에서 시작한 스와이프가 페이지를 스크롤하지 못했다. !important 클래스로 pan-y를
          앞세워 세로 스와이프는 페이지 스크롤, 가로 드래그와 마우스 드래그는 그대로 회전이 되게 한다.
        */}
        {/* dpr 상한 1.5: 레티나(2~3배)에서 그리기 버퍼가 4~9배로 커지는데, 입 클로즈업은 1.5배로도 차이가 거의 없다 */}
        <Canvas className="![touch-action:pan-y]" camera={{ position: [0, 1.68, 0.45], fov: 16 }} dpr={[1, 1.5]} gl={glFactory}
          onCreated={onCreated} frameloop={mirrorRef || bsFrameRef ? 'always' : 'demand'}>
          <ambientLight intensity={1.2} />
          <directionalLight position={[1, 2, 2]} intensity={1.0} />
          <directionalLight position={[-1, 0, 1]} intensity={0.4} />

          <Suspense fallback={null}>
            <RealisticFace visemeId={visemeId} xray={xray} bsFrameRef={bsFrameRef} mirrorRef={mirrorRef} modelUrl={modelUrl}
              transitionMs={transitionMs} durationMs={durationMs} speed={speed} talker={talker} lipVowel={lipVowel} />
          </Suspense>

          <CameraRig view={view} />
          <OrbitControls
            target={[0, 1.652, 0]}
            enableZoom={false}
            enablePan={false}
            minPolarAngle={Math.PI / 2.2}
            maxPolarAngle={Math.PI / 1.8}
            minAzimuthAngle={-Math.PI / 6}
            maxAzimuthAngle={SIDE_AZIMUTH + Math.PI / 12}
          />
        </Canvas>
      </div>
    </GLErrorBoundary>
  )
}

useGLTF.preload(MODEL_URL, false, false, withMeshopt)
