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
