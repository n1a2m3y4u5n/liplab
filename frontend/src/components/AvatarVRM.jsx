import { Component, Suspense, useRef, useState } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { VISEME_BLENDSHAPES, ACTIVE_MORPH_KEYS } from '../lib/visemeShapes'
import MouthFallback2D from './MouthFallback2D'

/**
 * 한국어 Viseme → 3D 입모양 렌더링
 *
 * 표준 ARKit 블렌드셰이프(jawOpen, mouthPucker, mouthFunnel, mouthClose 등)를
 * 조합한 정밀 매핑(../lib/visemeShapes)으로 원순·개방·폐쇄 등 한국어 조음을
 * 정확히 표현한다. WebGL 미지원 / 모델 로드 실패 시 2D 입모양으로 폴백한다.
 */
function RealisticFace({ visemeId = 15 }) {
  const { scene } = useGLTF('/models/realistic_face.glb')
  const meshesRef = useRef([])
  const currentWeightsRef = useRef({})

  // Find all meshes with morph targets on first render
  if (meshesRef.current.length === 0) {
    scene.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetInfluences) {
        meshesRef.current.push(obj)
      }
    })
  }

  useFrame((_, delta) => {
    if (meshesRef.current.length === 0) return

    const target = VISEME_BLENDSHAPES[visemeId] || {}
    const LERP = Math.min(1, delta * 22) // ~45ms transition (자음 프레임 내 충분히 도달)

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

export default function AvatarVRM({ visemeId = 15 }) {
  const [webglOK] = useState(detectWebGL)
  const fallback = <MouthFallback2D visemeId={visemeId} />

  if (!webglOK) return <div className="w-full h-full">{fallback}</div>

  return (
    <GLErrorBoundary fallback={<div className="w-full h-full">{fallback}</div>}>
      <div className="w-full h-full">
        <Canvas>
          {/* Close-up on mouth area for lip reading */}
          <PerspectiveCamera makeDefault position={[0, 1.62, 0.45]} fov={16} />
          <ambientLight intensity={1.2} />
          <directionalLight position={[1, 2, 2]} intensity={1.0} />
          <directionalLight position={[-1, 0, 1]} intensity={0.4} />

          <Suspense fallback={null}>
            <RealisticFace visemeId={visemeId} />
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
