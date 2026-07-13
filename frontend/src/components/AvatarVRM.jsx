import { Component, Suspense, useEffect, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import {
  VISEME_BLENDSHAPES,
  ACTIVE_MORPH_KEYS,
  VISEME_TONGUE,
  ACTIVE_TONGUE_KEYS,
} from '../lib/visemeShapes'
import MouthFallback2D from './MouthFallback2D'

const VIEW_PRESETS = {
  front: {
    near: { pos: [0, 1.62, 0.45], target: [0, 1.59, 0], fov: 16 },
    far: { pos: [0, 1.55, 1.0], target: [0, 1.52, 0], fov: 40 },
    minAz: -Math.PI / 6,
    maxAz: Math.PI / 6,
  },
  side: {
    near: { pos: [0.95, 1.60, 0.06], target: [0, 1.58, 0.02], fov: 28 },
    far: { pos: [1.35, 1.55, 0.06], target: [0, 1.53, 0.02], fov: 34 },
    minAz: Math.PI / 12,
    maxAz: Math.PI / 2.2,
  },
}

export const DISTANCE_NEAR_M = 0.45
export const DISTANCE_FAR_M = 1.0

const lerp = (a, b, amount) => a + (b - a) * amount
const lerp3 = (a, b, amount) => [
  lerp(a[0], b[0], amount),
  lerp(a[1], b[1], amount),
  lerp(a[2], b[2], amount),
]

function viewForDistance(view, distance = 0) {
  const preset = VIEW_PRESETS[view] || VIEW_PRESETS.front
  const amount = Math.max(0, Math.min(1, distance))
  return {
    pos: lerp3(preset.near.pos, preset.far.pos, amount),
    target: lerp3(preset.near.target, preset.far.target, amount),
    fov: lerp(preset.near.fov, preset.far.fov, amount),
    minAz: preset.minAz,
    maxAz: preset.maxAz,
  }
}

/** 뷰나 거리가 바뀌어도 모프 상태를 유지하며 카메라만 이동한다. */
function CameraRig({ view, distance, controlsRef }) {
  const { camera } = useThree()

  useEffect(() => {
    const config = viewForDistance(view, distance)
    camera.position.set(...config.pos)
    camera.fov = config.fov
    camera.updateProjectionMatrix()

    const controls = controlsRef.current
    if (controls) {
      controls.target.set(...config.target)
      controls.update()
    }
  }, [view, distance, camera, controlsRef])

  return null
}

function easeInOutCubic(amount) {
  return amount < 0.5
    ? 4 * amount * amount * amount
    : 1 - Math.pow(-2 * amount + 2, 3) / 2
}

const BLINK_KEYS = [
  'eyeBlinkLeft',
  'eyeBlinkRight',
  'eyeBlink_L',
  'eyeBlink_R',
  'blink',
  'eyesClosed',
]
const BLINK_DURATION = 0.14
const NECK_CLIP_Y = 1.45
const NECK_CLIP_PLANE = new THREE.Plane(
  new THREE.Vector3(0, 1, 0),
  -NECK_CLIP_Y,
)

/**
 * 한국어 Viseme → 3D 입모양 렌더링
 *
 * 표준 ARKit 블렌드셰이프(jawOpen, mouthPucker, mouthFunnel, mouthClose 등)를
 * 조합한 정밀 매핑(../lib/visemeShapes)으로 원순·개방·폐쇄 등 한국어 조음을
 * 정확히 표현한다. WebGL 미지원 / 모델 로드 실패 시 2D 입모양으로 폴백한다.
 */
function RealisticFace({
  visemeId = 15,
  transitionMs = 30,
  durationMs = 120,
  speed = 1.0,
}) {
  const { scene } = useGLTF('/models/realistic_face.glb')
  const { gl } = useThree()
  const meshesRef = useRef([])
  const tongueMeshRef = useRef(null)
  const currentWeightsRef = useRef({})
  const fromWeightsRef = useRef({})
  const tongueWeightsRef = useRef({})
  const lastVisemeRef = useRef(null)
  const elapsedRef = useRef(0)
  const idleRef = useRef(0)
  const baseRef = useRef(null)
  const nextBlinkRef = useRef(1.5)
  const blinkStartRef = useRef(-1)
  const transitionRef = useRef(transitionMs)
  const durationRef = useRef(durationMs)
  const speedRef = useRef(speed)

  transitionRef.current = transitionMs
  durationRef.current = durationMs
  speedRef.current = speed

  // Find all meshes with morph targets on first render
  if (meshesRef.current.length === 0) {
    gl.localClippingEnabled = true
    scene.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
        meshesRef.current.push(obj)
        const dict = obj.morphTargetDictionary
        // 혀 메시만 가진 모프를 별도로 적용해 얼굴 메시 왜곡을 막는다.
        if ('tongueOut' in dict && !('mouthSmileLeft' in dict)) {
          tongueMeshRef.current = obj
        }
      }

      if (obj.isMesh && obj.material) {
        const materials = Array.isArray(obj.material) ? obj.material : [obj.material]
        for (const material of materials) {
          material.clippingPlanes = [NECK_CLIP_PLANE]
        }
      }
    })

    baseRef.current = {
      rotationX: scene.rotation.x,
      rotationY: scene.rotation.y,
      positionY: scene.position.y,
    }
  }

  useFrame((_, delta) => {
    if (meshesRef.current.length === 0) return

    const target = VISEME_BLENDSHAPES[visemeId] || {}

    if (lastVisemeRef.current !== visemeId) {
      lastVisemeRef.current = visemeId
      const snapshot = {}
      for (const key of ACTIVE_MORPH_KEYS) {
        snapshot[key] = currentWeightsRef.current[key] || 0
      }
      fromWeightsRef.current = snapshot
      elapsedRef.current = 0
    }

    // 전환은 프레임 길이의 60% 안에 끝내 짧은 자음도 목표 입모양에 도달하게 한다.
    const effectiveTransitionMs = Math.min(
      Math.max(transitionRef.current, 8),
      Math.max(durationRef.current * 0.6, 8),
    )
    elapsedRef.current += delta * speedRef.current * 1000
    const transitionProgress = Math.min(1, elapsedRef.current / effectiveTransitionMs)
    const easedProgress = easeInOutCubic(transitionProgress)

    for (const key of ACTIVE_MORPH_KEYS) {
      const from = fromWeightsRef.current[key] || 0
      const tgt = target[key] || 0
      const next = from + (tgt - from) * easedProgress
      currentWeightsRef.current[key] = next

      for (const mesh of meshesRef.current) {
        const idx = mesh.morphTargetDictionary?.[key]
        if (idx !== undefined) {
          mesh.morphTargetInfluences[idx] = next
        }
      }
    }

    const tongue = tongueMeshRef.current
    if (tongue) {
      const targetTongue = VISEME_TONGUE[visemeId] || {}
      const tongueLerp = Math.min(1, delta * 15 * speedRef.current)
      for (const key of ACTIVE_TONGUE_KEYS) {
        const current = tongueWeightsRef.current[key] || 0
        const next = THREE.MathUtils.lerp(current, targetTongue[key] || 0, tongueLerp)
        tongueWeightsRef.current[key] = next
        const index = tongue.morphTargetDictionary?.[key]
        if (index !== undefined) tongue.morphTargetInfluences[index] = next
      }
    }

    // 입모양과 독립된 눈 깜빡임·미세 머리 움직임·호흡을 더한다.
    const idleTime = idleRef.current + delta
    idleRef.current = idleTime

    let blinkWeight = 0
    if (blinkStartRef.current >= 0) {
      const blinkProgress = (idleTime - blinkStartRef.current) / BLINK_DURATION
      if (blinkProgress >= 1) {
        blinkStartRef.current = -1
        nextBlinkRef.current = idleTime + 2.5 + Math.random() * 3.5
      } else {
        blinkWeight = Math.sin(Math.PI * blinkProgress)
      }
    } else if (idleTime >= nextBlinkRef.current) {
      blinkStartRef.current = idleTime
    }

    for (const key of BLINK_KEYS) {
      for (const mesh of meshesRef.current) {
        const index = mesh.morphTargetDictionary?.[key]
        if (index !== undefined) mesh.morphTargetInfluences[index] = blinkWeight
      }
    }

    const base = baseRef.current
    if (base) {
      scene.rotation.y = base.rotationY + Math.sin(idleTime * 0.5) * 0.012
      scene.rotation.x = base.rotationX + Math.sin(idleTime * 0.37) * 0.008
      scene.position.y = base.positionY + Math.sin(idleTime * 0.8) * 0.0025
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

export default function AvatarVRM({
  visemeId = 15,
  transitionMs = 30,
  durationMs = 120,
  speed = 1.0,
  view = 'front',
  distance = 0,
}) {
  const [webglOK] = useState(detectWebGL)
  const controlsRef = useRef()
  const fallback = <MouthFallback2D visemeId={visemeId} />

  if (!webglOK) return <div className="w-full h-full">{fallback}</div>

  const config = viewForDistance(view, distance)
  const initialCamera = viewForDistance('front', distance)

  return (
    <GLErrorBoundary fallback={<div className="w-full h-full">{fallback}</div>}>
      <div className="w-full h-full">
        {/*
          카메라는 Canvas에 직접 지정한다. 예전처럼 <PerspectiveCamera makeDefault>를
          자식으로 두면, OrbitControls가 카메라 위치(입 클로즈업)가 설정되기 전에
          기본 위치 [0,0,5]를 읽어 얼굴 전체(눈)를 비추는 경쟁 조건이 생긴다
          (StrictMode에서 특히 재현). Canvas camera는 렌더러 생성 시점에 확정되므로
          OrbitControls가 항상 올바른 입 클로즈업 위치를 읽는다.
        */}
        <Canvas camera={{ position: initialCamera.pos, fov: initialCamera.fov }}>
          <ambientLight intensity={1.2} />
          <directionalLight position={[1, 2, 2]} intensity={1.0} />
          <directionalLight position={[-1, 0, 1]} intensity={0.4} />

          <Suspense fallback={null}>
            <RealisticFace
              visemeId={visemeId}
              transitionMs={transitionMs}
              durationMs={durationMs}
              speed={speed}
            />
          </Suspense>

          <CameraRig view={view} distance={distance} controlsRef={controlsRef} />
          <OrbitControls
            ref={controlsRef}
            target={config.target}
            enableZoom={false}
            enablePan={false}
            minPolarAngle={Math.PI / 2.2}
            maxPolarAngle={Math.PI / 1.8}
            minAzimuthAngle={config.minAz}
            maxAzimuthAngle={config.maxAz}
          />
        </Canvas>
      </div>
    </GLErrorBoundary>
  )
}

useGLTF.preload('/models/realistic_face.glb')
