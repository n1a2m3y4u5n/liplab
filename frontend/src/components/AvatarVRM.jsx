import { Component, Suspense, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS, VISEME_TONGUE, ACTIVE_TONGUE_KEYS } from '../lib/visemeShapes'
import { MIRROR_KEYS } from '../lib/mouthMirror'
import MouthFallback2D from './MouthFallback2D'

const EMPTY = {}

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
function RealisticFace({ visemeId = 15, mirrorRef = null }) {
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

    // 거울 모드(축 F): 웹캠 계수가 있으면 그것이 목표, 없으면 viseme 매핑이 목표.
    const mirror = mirrorRef?.current || null
    const target = mirror || VISEME_BLENDSHAPES[visemeId] || EMPTY
    const LERP = Math.min(1, delta * 22) // ~45ms transition (자음 프레임 내 충분히 도달)

    /*
      보간할 키 집합. mirrorRef를 받은 인스턴스는 **항상** MIRROR_KEYS(=ACTIVE_MORPH_KEYS의
      상위집합)를 돈다. 목표 맵에 없는 키는 0으로 읽히므로, 거울 모드를 끄면 거울에서만
      쓰던 모프(jawForward·cheekPuff 등)가 자동으로 0으로 복귀한다.
      — 개발일지 3절의 함정: 매 프레임 '사용 키 목록'만 보간하면, 목록에서 빠진 키는
        아무도 0으로 되돌리지 않아 직전 값이 얼굴에 남는다.
      mirrorRef가 없는 기존 호출부는 종전과 동일하게 ACTIVE_MORPH_KEYS만 돈다(동작 불변).
    */
    const morphKeys = mirrorRef ? MIRROR_KEYS : ACTIVE_MORPH_KEYS

    // 얼굴·턱 모프 — 모든 메시에 이름으로 일괄 적용 (jawOpen은 혀도 함께 따라감)
    for (const key of morphKeys) {
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

export default function AvatarVRM({ visemeId = 15, mirrorRef = null }) {
  const [webglOK] = useState(detectWebGL)
  const fallback = <MouthFallback2D visemeId={visemeId} />

  if (!webglOK) return <div className="w-full h-full">{fallback}</div>

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
        <Canvas camera={{ position: [0, 1.62, 0.45], fov: 16 }}>
          <ambientLight intensity={1.2} />
          <directionalLight position={[1, 2, 2]} intensity={1.0} />
          <directionalLight position={[-1, 0, 1]} intensity={0.4} />

          <Suspense fallback={null}>
            <RealisticFace visemeId={visemeId} mirrorRef={mirrorRef} />
          </Suspense>

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
    </GLErrorBoundary>
  )
}

useGLTF.preload('/models/realistic_face.glb')
