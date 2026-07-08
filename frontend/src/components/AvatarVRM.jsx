import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, useGLTF } from '@react-three/drei'
import * as THREE from 'three'

/**
 * Oculus OVR LipSync viseme → Korean phoneme mapping
 * Maps our 15 Korean viseme IDs to Oculus morph target weights.
 *
 * 자음 morph target(DD, kk, CH 등)이 모델에 없을 경우를 대비해
 * 모음 계열 morph target(aa, E, I)을 보조로 함께 사용.
 * 이렇게 하면 입모양이 완전히 멈추지 않고 해당 조음 위치에 가까운
 * 형태를 시각적으로 보여줄 수 있음.
 */
const KOREAN_TO_OCULUS = {
  1:  { viseme_PP: 0.95 },                               // bilabial: ㅂ/ㅍ/ㅁ (lips pressed)
  2:  { viseme_aa: 0.95 },                               // open vowel: ㅏ/ㅐ
  3:  { viseme_I: 0.85 },                                // front vowel: ㅣ/ㅔ
  4:  { viseme_O: 0.6, viseme_U: 0.5 },                  // rounded: ㅗ/ㅜ
  5:  { viseme_E: 0.75 },                                // central: ㅓ/ㅡ
  6:  { viseme_DD: 0.7, viseme_nn: 0.4, viseme_E: 0.3 }, // alveolar: ㄷ/ㄴ/ㄹ/ㅅ (tongue-teeth + slight open)
  7:  { viseme_kk: 0.7, viseme_aa: 0.2 },               // velar: ㄱ/ㅇ (back throat + slight open)
  8:  { viseme_SS: 0.65, viseme_aa: 0.35 },             // glottal: ㅎ (open breath)
  9:  { viseme_aa: 0.55, viseme_I: 0.45 },              // diphthong
  10: { viseme_CH: 0.8, viseme_I: 0.3 },                // palatal: ㅈ/ㅊ (front + lip spread)
  11: { viseme_PP: 0.2 },                               // transition bilabial
  12: { viseme_DD: 0.25, viseme_E: 0.15 },              // transition alveolar
  13: { viseme_kk: 0.25, viseme_aa: 0.1 },              // transition velar
  14: {},                                               // silence
  15: {},                                               // neutral
}

const ALL_VISEME_KEYS = [
  'viseme_sil', 'viseme_PP', 'viseme_FF', 'viseme_TH', 'viseme_DD',
  'viseme_kk', 'viseme_CH', 'viseme_SS', 'viseme_nn', 'viseme_RR',
  'viseme_aa', 'viseme_E', 'viseme_I', 'viseme_O', 'viseme_U',
]

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

    const target = KOREAN_TO_OCULUS[visemeId] || {}
    const LERP = Math.min(1, delta * 22) // ~45ms transition (자음 80ms 프레임 내 충분히 도달)

    for (const key of ALL_VISEME_KEYS) {
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
