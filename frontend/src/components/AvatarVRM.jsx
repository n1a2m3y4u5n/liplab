import { Component, Suspense, useEffect, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS } from '../lib/visemeShapes'
import MouthFallback2D from './MouthFallback2D'

/**
 * 뷰 프리셋 — 정면/측면. 측면은 얼굴 옆에서 비춰 정면에서 안 보이는
 * 입술 내밀기(원순음 ㅜ/ㅗ, 양순음 ㅂ의 protrusion)를 드러낸다(독화 학습 포인트).
 * 각 뷰마다 OrbitControls 회전 허용 범위(azimuth)를 달리해 시점 이탈을 막는다.
 */
/**
 * 뷰 프리셋 — 사용자가 조절하는 거리값 distance(0~1)에 따라 near(근접)→far(원거리)로 보간한다.
 * distance가 커질수록 카메라가 얼굴에서 멀어지고 화각(fov)이 넓어져 얼굴이 점점 작게 보인다.
 *   near(0): 가장 가까운 클로즈업, far(1): 약 1m(실제 대화 거리).
 */
const VIEW_PRESETS = {
  // 정면: distance 0은 입 클로즈업(0.45m, fov16), 1은 대화 거리(~1m, fov40)로 얼굴 전체+어깨선.
  front: {
    near:  { pos: [0, 1.62, 0.45], target: [0, 1.59, 0], fov: 16 },
    far:   { pos: [0, 1.55, 1.00], target: [0, 1.52, 0], fov: 40 },
    minAz: -Math.PI / 6, maxAz: Math.PI / 6,
  },
  // 측면: 옆 얼굴 프로필. distance가 커지면 함께 멀어진다.
  side: {
    near:  { pos: [0.95, 1.60, 0.06], target: [0, 1.58, 0.02], fov: 28 },
    far:   { pos: [1.35, 1.55, 0.06], target: [0, 1.53, 0.02], fov: 34 },
    minAz: Math.PI / 12, maxAz: Math.PI / 2.2,
  },
}

// 슬라이더 distance(0~1)를 대략적인 실제 거리(m)로 환산해 UI에 표시하기 위한 값(정면 기준).
export const DISTANCE_NEAR_M = 0.45
export const DISTANCE_FAR_M = 1.0

const lerp = (a, b, t) => a + (b - a) * t
const lerp3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]

/** distance(0~1)를 near~far 사이 보간 비율로 써서 뷰 설정을 만든다. */
function viewForDistance(view, distance = 0) {
  const p = VIEW_PRESETS[view] || VIEW_PRESETS.front
  const t = Math.max(0, Math.min(1, distance))
  return {
    pos: lerp3(p.near.pos, p.far.pos, t),
    target: lerp3(p.near.target, p.far.target, t),
    fov: lerp(p.near.fov, p.far.fov, t),
    minAz: p.minAz, maxAz: p.maxAz,
  }
}

/** 뷰/거리 변경 시 카메라 위치·타깃·화각을 리마운트 없이 이동시킨다(모프 상태 보존). */
function CameraRig({ view, distance, controlsRef }) {
  const { camera } = useThree()
  useEffect(() => {
    const cfg = viewForDistance(view, distance)
    camera.position.set(cfg.pos[0], cfg.pos[1], cfg.pos[2])
    if (camera.fov !== cfg.fov) {
      camera.fov = cfg.fov            // 거리/뷰별 화각(가까울수록 좁게, 멀수록 넓게)
      camera.updateProjectionMatrix()
    }
    const ctrl = controlsRef.current
    if (ctrl) {
      ctrl.target.set(cfg.target[0], cfg.target[1], cfg.target[2])
      ctrl.update()
    }
  }, [view, distance, camera, controlsRef])
  return null
}

/**
 * 한국어 Viseme → 3D 입모양 렌더링
 *
 * 표준 ARKit 블렌드셰이프(jawOpen, mouthPucker, mouthFunnel, mouthClose 등)를
 * 조합한 정밀 매핑(../lib/visemeShapes)으로 원순·개방·폐쇄 등 한국어 조음을
 * 정확히 표현한다. WebGL 미지원 / 모델 로드 실패 시 2D 입모양으로 폴백한다.
 */
/** easeInOutCubic — 전환 시작·끝을 부드럽게(입술이 스르륵 열리고 닫히는 느낌). */
function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

// 눈 깜빡임에 쓸 후보 모프 키(모델별 명명 차이 대응). 존재하는 것만 적용된다.
const BLINK_KEYS = ['eyeBlinkLeft', 'eyeBlinkRight', 'eyeBlink_L', 'eyeBlink_R', 'blink', 'eyesClosed']
const BLINK_DURATION = 0.14   // 한 번 깜빡이는 데 걸리는 시간(초)

// 몸 전체가 하나의 스킨드 메시(base)라 손/팔만 따로 숨길 수 없다.
// 대신 목 아래(y < NECK_CLIP_Y)를 클리핑 평면으로 잘라 어깨·팔·손을 제거한다.
// 평면은 normal·point + constant >= 0 을 남기므로 normal=(0,1,0), constant=-NECK_CLIP_Y.
const NECK_CLIP_Y = 1.45
const NECK_CLIP_PLANE = new THREE.Plane(new THREE.Vector3(0, 1, 0), -NECK_CLIP_Y)

function RealisticFace({ visemeId = 15, transitionMs = 30, durationMs = 120, speed = 1.0 }) {
  const { scene } = useGLTF('/models/realistic_face.glb')
  const { gl } = useThree()
  const meshesRef = useRef([])
  const currentWeightsRef = useRef({})     // 현재 화면에 반영된 가중치
  const fromWeightsRef = useRef({})        // 이번 전환의 시작점(스냅샷)
  const lastVisemeRef = useRef(null)       // 목표 viseme 변화 감지용
  const elapsedRef = useRef(0)             // 이번 전환 경과(ms)
  // 아이들 모션(입모양과 독립): 시간 누적·기본 자세·다음 깜빡임 시각.
  const idleRef = useRef(0)
  const baseRef = useRef(null)             // 모델 기본 회전/위치(최초 1회 캡처)
  const nextBlinkRef = useRef(1.5)         // 다음 깜빡임 시작 시각(초)
  const blinkStartRef = useRef(-1)         // 진행 중 깜빡임 시작 시각(-1이면 없음)
  // 프레임별 값을 useFrame(순수 함수) 안에서 최신값으로 읽기 위한 ref.
  const transitionRef = useRef(transitionMs)
  const durationRef = useRef(durationMs)
  const speedRef = useRef(speed)
  transitionRef.current = transitionMs
  durationRef.current = durationMs
  speedRef.current = speed

  // Find all meshes with morph targets on first render
  if (meshesRef.current.length === 0) {
    // 목 아래(어깨·팔·손)를 잘라내는 클리핑 평면을 모든 재질에 적용.
    gl.localClippingEnabled = true
    scene.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
        meshesRef.current.push(obj)
      }
      if (obj.isMesh && obj.material) {
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
        for (const m of mats) m.clippingPlanes = [NECK_CLIP_PLANE]
      }
    })
    // 아이들 흔들림/호흡의 기준이 될 원래 자세를 저장(이후 여기에 미세 오프셋만 더한다).
    baseRef.current = {
      rx: scene.rotation.x, ry: scene.rotation.y,
      px: scene.position.x, py: scene.position.y,
    }
  }

  useFrame((_, delta) => {
    if (meshesRef.current.length === 0) return

    const target = VISEME_BLENDSHAPES[visemeId] || {}

    // 목표 viseme이 바뀌면: 현재 가중치를 시작점으로 스냅샷하고 전환 타이머를 리셋.
    if (lastVisemeRef.current !== visemeId) {
      lastVisemeRef.current = visemeId
      const snap = {}
      for (const key of ACTIVE_MORPH_KEYS) snap[key] = currentWeightsRef.current[key] || 0
      fromWeightsRef.current = snap
      elapsedRef.current = 0
    }

    // 전환 시간은 프레임 길이의 60%를 넘지 않게 제한한다.
    // → 짧은 자음 프레임(ㅂ/ㅁ 폐쇄 등)도 목표 입모양에 '실제로 도달'한 뒤 남은 시간 동안 유지된다.
    const effTransMs = Math.min(Math.max(transitionRef.current, 8), Math.max(durationRef.current * 0.6, 8))
    elapsedRef.current += delta * speedRef.current * 1000
    const t = Math.min(1, elapsedRef.current / effTransMs)   // 진행도 0~1 (t=1이면 목표 도달 보장)
    const eased = easeInOutCubic(t)

    for (const key of ACTIVE_MORPH_KEYS) {
      const from = fromWeightsRef.current[key] || 0
      const tgt = target[key] || 0
      const next = from + (tgt - from) * eased
      currentWeightsRef.current[key] = next

      for (const mesh of meshesRef.current) {
        const idx = mesh.morphTargetDictionary?.[key]
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = next
        }
      }
    }

    // ── 아이들 모션 (재생 속도와 무관하게 실시간으로 진행) ──────────────────
    const idle = idleRef.current + delta
    idleRef.current = idle

    // 눈 깜빡임: nextBlink 시각이 되면 시작, sin으로 0→1→0(감았다 뜸) 후 다음 깜빡임 예약.
    let blinkW = 0
    if (blinkStartRef.current >= 0) {
      const bt = (idle - blinkStartRef.current) / BLINK_DURATION
      if (bt >= 1) {
        blinkStartRef.current = -1
        nextBlinkRef.current = idle + 2.5 + Math.random() * 3.5   // 2.5~6초 뒤 다시
      } else {
        blinkW = Math.sin(Math.PI * bt)
      }
    } else if (idle >= nextBlinkRef.current) {
      blinkStartRef.current = idle
    }
    for (const key of BLINK_KEYS) {
      for (const mesh of meshesRef.current) {
        const idx = mesh.morphTargetDictionary?.[key]
        if (idx !== undefined) mesh.morphTargetInfluences[idx] = blinkW
      }
    }

    // 미세 머리 흔들림 + 호흡: 기본 자세에 아주 작은 sin 오프셋만 더한다(입이 화면 밖으로 나가지 않게 소폭).
    const base = baseRef.current
    if (base) {
      scene.rotation.y = base.ry + Math.sin(idle * 0.5) * 0.012
      scene.rotation.x = base.rx + Math.sin(idle * 0.37) * 0.008
      scene.position.y = base.py + Math.sin(idle * 0.8) * 0.0025   // 호흡 상하 미동
    }
  })

  return <primitive object={scene} />
}

/** WebGL 지원 여부 감지 (컨텍스트 생성 실패 시 false) */
function detectWebGL() {
  if (typeof document === 'undefined') return true
  try {
    const canvas = document.createElement('canvas')
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    )
  } catch {
    return false
  }
}

/** 3D 렌더/로드 중 오류를 잡아 2D 폴백으로 전환하는 경계 */
class GLErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export default function AvatarVRM({ visemeId = 15, transitionMs = 30, durationMs = 120, speed = 1.0, view = 'front', distance = 0 }) {
  const [webglOK] = useState(detectWebGL)
  const controlsRef = useRef()
  const fallback = <MouthFallback2D visemeId={visemeId} />

  if (!webglOK) return <div className="w-full h-full">{fallback}</div>

  const cfg = viewForDistance(view, distance)
  // Canvas의 초기 카메라(렌더러 생성 시 1회 확정) — 기본 뷰(정면) + 현재 거리 기준.
  const initCam = viewForDistance('front', distance)

  return (
    <GLErrorBoundary fallback={<div className="w-full h-full">{fallback}</div>}>
      <div className="w-full h-full">
        {/*
          카메라는 Canvas에 직접 지정한다. 예전처럼 <PerspectiveCamera makeDefault>를
          자식으로 두면, OrbitControls가 카메라 위치(입 클로즈업)가 설정되기 전에
          기본 위치 [0,0,5]를 읽어 얼굴 전체(눈)를 비추는 경쟁 조건이 생긴다
          (StrictMode에서 특히 재현). Canvas camera는 렌더러 생성 시점에 확정되므로
          OrbitControls가 항상 올바른 입 클로즈업 위치를 읽는다.
          뷰(정면/측면) 전환은 CameraRig가 카메라를 이동시켜 처리한다.
        */}
        <Canvas camera={{ position: initCam.pos, fov: initCam.fov }}>
          <ambientLight intensity={1.2} />
          <directionalLight position={[1, 2, 2]} intensity={1.0} />
          <directionalLight position={[-1, 0, 1]} intensity={0.4} />

          <Suspense fallback={null}>
            <RealisticFace visemeId={visemeId} transitionMs={transitionMs} durationMs={durationMs} speed={speed} />
          </Suspense>

          <CameraRig view={view} distance={distance} controlsRef={controlsRef} />
          <OrbitControls
            ref={controlsRef}
            target={cfg.target}
            enableZoom={false}
            enablePan={false}
            minPolarAngle={Math.PI / 2.2}
            maxPolarAngle={Math.PI / 1.8}
            minAzimuthAngle={cfg.minAz}
            maxAzimuthAngle={cfg.maxAz}
          />
        </Canvas>
      </div>
    </GLErrorBoundary>
  )
}

useGLTF.preload('/models/realistic_face.glb')
import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS, VISEME_TONGUE, ACTIVE_TONGUE_KEYS } from '../lib/visemeShapes'

/**
 * 한국어 Viseme → 3D 입모양 렌더링
 *
 * viseme_* (Oculus) 뿐 아니라 ARKit 블렌드셰이프(jawOpen, mouthPucker,
 * mouthFunnel, mouthClose 등)를 조합한 정밀 매핑(../lib/visemeShapes)을 사용해
 * 원순·개방·폐쇄 등 한국어 조음을 정확히 표현한다.
 */
function RealisticFace({ visemeId = 15 }) {
  const { scene } = useGLTF('/models/realistic_face.glb')
  const meshesRef = useRef([])
  const tongueMeshRef = useRef(null)
  const currentWeightsRef = useRef({})
  const tongueWeightsRef = useRef({})

  // Find all meshes with morph targets on first render
  if (meshesRef.current.length === 0) {
    scene.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
        meshesRef.current.push(obj)
        // 혀 메시 식별: tongueOut은 있고 mouthSmileLeft(얼굴 전용)는 없는 메시.
        // (얼굴=둘 다 있음, 치아=둘 다 없음, 혀=tongueOut만 있음 → 유일하게 구분됨)
        const dict = obj.morphTargetDictionary
        if ('tongueOut' in dict && !('mouthSmileLeft' in dict)) {
          tongueMeshRef.current = obj
        }
      }
    })
  }

  useFrame((_, delta) => {
    if (meshesRef.current.length === 0) return

    const target = VISEME_BLENDSHAPES[visemeId] || {}
    const LERP = Math.min(1, delta * 22) // ~45ms transition (자음 80ms 프레임 내 충분히 도달)

    // 얼굴·턱 모프 — 모든 메시에 이름으로 일괄 적용 (jawOpen은 혀도 함께 따라감)
    for (const key of ACTIVE_MORPH_KEYS) {
      const tgt = target[key] || 0
      const cur = currentWeightsRef.current[key] || 0
      const next = THREE.MathUtils.lerp(cur, tgt, LERP)
      currentWeightsRef.current[key] = next

      for (const mesh of meshesRef.current) {
        const idx = mesh.morphTargetDictionary?.[key]
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = next
        }
      }
    }

    // 혀 전용 모프 — 혀 메시에만 적용해 얼굴 왜곡을 방지 (mesh-scoped)
    // 혀는 얼굴보다 살짝 느리게 보간해 '이동'이 눈에 띄도록 한다 (~65ms).
    const TONGUE_LERP = Math.min(1, delta * 15)
    const tongue = tongueMeshRef.current
    if (tongue) {
      const tTarget = VISEME_TONGUE[visemeId] || {}
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
  })

  return <primitive object={scene} />
}

export default function AvatarVRM({ visemeId = 15 }) {
  return (
    <div className="w-full h-full">
      <Canvas>
        {/* Close-up on mouth area for lip reading */}
        <PerspectiveCamera makeDefault position={[0, 1.62, 0.45]} fov={16} />
        <ambientLight intensity={1.2} />
        <directionalLight position={[1, 2, 2]} intensity={1.0} />
        <directionalLight position={[-1, 0, 1]} intensity={0.4} />

        <RealisticFace visemeId={visemeId} />

        <OrbitControls
          target={[0, 1.59, 0]}
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 2.2}
          maxPolarAngle={Math.PI / 1.8}
          minAzimuthAngle={-Math.PI / 6}
          maxAzimuthAngle={Math.PI / 6}
        />
      </Canvas>
    </div>
  )
}

useGLTF.preload('/models/realistic_face.glb')
