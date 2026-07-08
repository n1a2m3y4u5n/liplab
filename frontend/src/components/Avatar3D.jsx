import { useRef, useEffect, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'

/**
 * 3D Avatar Head Component
 * Renders a simple 3D face with animated mouth shapes for each viseme
 */

// Viseme mouth shape configurations (15 visemes)
const VISEME_SHAPES = {
  1: { // Bilabial (ㅂ, ㅍ, ㅁ) - lips closed
    mouthWidth: 0.3,
    mouthHeight: 0.05,
    mouthDepth: 0.1,
    lipsClosed: true,
    color: 0xef4444,
  },
  2: { // Open vowels (ㅏ, ㅐ) - jaw drop
    mouthWidth: 0.4,
    mouthHeight: 0.35,
    mouthDepth: 0.25,
    lipsClosed: false,
    color: 0xf59e0b,
  },
  3: { // Front vowels (ㅣ, ㅔ) - lips spread
    mouthWidth: 0.5,
    mouthHeight: 0.15,
    mouthDepth: 0.15,
    lipsClosed: false,
    color: 0x10b981,
  },
  4: { // Rounded vowels (ㅗ, ㅜ) - lips rounded
    mouthWidth: 0.25,
    mouthHeight: 0.3,
    mouthDepth: 0.2,
    lipsClosed: false,
    color: 0x3b82f6,
  },
  5: { // Central vowels (ㅓ, ㅡ) - neutral
    mouthWidth: 0.35,
    mouthHeight: 0.2,
    mouthDepth: 0.18,
    lipsClosed: false,
    color: 0x8b5cf6,
  },
  6: { // Alveolar (ㄷ, ㅌ, ㄴ) - tongue tip
    mouthWidth: 0.3,
    mouthHeight: 0.2,
    mouthDepth: 0.15,
    lipsClosed: false,
    showTongue: true,
    color: 0xec4899,
  },
  7: { // Velar (ㄱ, ㅋ, ㅇ) - mouth slightly open
    mouthWidth: 0.35,
    mouthHeight: 0.25,
    mouthDepth: 0.2,
    lipsClosed: false,
    color: 0x14b8a6,
  },
  8: { // Glottal (ㅎ) - throat
    mouthWidth: 0.35,
    mouthHeight: 0.3,
    mouthDepth: 0.25,
    lipsClosed: false,
    color: 0xf97316,
  },
  9: { // Diphthongs (ㅘ, ㅝ) - transition
    mouthWidth: 0.3,
    mouthHeight: 0.25,
    mouthDepth: 0.2,
    lipsClosed: false,
    color: 0x6366f1,
  },
  10: { // Palatal (ㅈ, ㅊ) - tongue blade
    mouthWidth: 0.32,
    mouthHeight: 0.22,
    mouthDepth: 0.17,
    lipsClosed: false,
    color: 0x84cc16,
  },
  11: { // Transition to bilabial
    mouthWidth: 0.32,
    mouthHeight: 0.1,
    mouthDepth: 0.12,
    lipsClosed: false,
    color: 0x06b6d4,
  },
  12: { // Transition to alveolar
    mouthWidth: 0.33,
    mouthHeight: 0.18,
    mouthDepth: 0.16,
    lipsClosed: false,
    color: 0xa855f7,
  },
  13: { // Transition to velar
    mouthWidth: 0.34,
    mouthHeight: 0.22,
    mouthDepth: 0.19,
    lipsClosed: false,
    color: 0xf43f5e,
  },
  14: { // Silence - rest position
    mouthWidth: 0.3,
    mouthHeight: 0.08,
    mouthDepth: 0.1,
    lipsClosed: true,
    color: 0x64748b,
  },
  15: { // Neutral
    mouthWidth: 0.32,
    mouthHeight: 0.15,
    mouthDepth: 0.15,
    lipsClosed: false,
    color: 0x78716c,
  },
}

/**
 * Face mesh component with animated mouth
 */
function FaceAvatar({ visemeId = 1, transitionSpeed = 0.15 }) {
  const groupRef = useRef()
  const mouthRef = useRef()
  const upperLipRef = useRef()
  const lowerLipRef = useRef()
  const tongueRef = useRef()

  const targetShape = useMemo(() => VISEME_SHAPES[visemeId] || VISEME_SHAPES[1], [visemeId])

  // Smooth animation using lerp
  useFrame(() => {
    if (!mouthRef.current) return

    const current = mouthRef.current.scale
    const target = new THREE.Vector3(
      targetShape.mouthWidth,
      targetShape.mouthHeight,
      targetShape.mouthDepth
    )

    current.lerp(target, transitionSpeed)

    // Animate lips
    if (upperLipRef.current && lowerLipRef.current) {
      if (targetShape.lipsClosed) {
        upperLipRef.current.position.y = THREE.MathUtils.lerp(
          upperLipRef.current.position.y,
          0.05,
          transitionSpeed
        )
        lowerLipRef.current.position.y = THREE.MathUtils.lerp(
          lowerLipRef.current.position.y,
          -0.05,
          transitionSpeed
        )
      } else {
        upperLipRef.current.position.y = THREE.MathUtils.lerp(
          upperLipRef.current.position.y,
          0.15,
          transitionSpeed
        )
        lowerLipRef.current.position.y = THREE.MathUtils.lerp(
          lowerLipRef.current.position.y,
          -0.15,
          transitionSpeed
        )
      }
    }

    // Show/hide tongue
    if (tongueRef.current) {
      const targetOpacity = targetShape.showTongue ? 1 : 0
      tongueRef.current.material.opacity = THREE.MathUtils.lerp(
        tongueRef.current.material.opacity,
        targetOpacity,
        transitionSpeed
      )
    }
  })

  return (
    <group ref={groupRef}>
      {/* Head */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshStandardMaterial color="#fdd" roughness={0.7} />
      </mesh>

      {/* Eyes */}
      <mesh position={[-0.3, 0.2, 0.8]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial color="#333" />
      </mesh>
      <mesh position={[0.3, 0.2, 0.8]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial color="#333" />
      </mesh>

      {/* Eyebrows */}
      <mesh position={[-0.3, 0.35, 0.85]} rotation={[0, 0, -0.2]}>
        <boxGeometry args={[0.2, 0.04, 0.02]} />
        <meshStandardMaterial color="#654" />
      </mesh>
      <mesh position={[0.3, 0.35, 0.85]} rotation={[0, 0, 0.2]}>
        <boxGeometry args={[0.2, 0.04, 0.02]} />
        <meshStandardMaterial color="#654" />
      </mesh>

      {/* Nose */}
      <mesh position={[0, 0, 1]}>
        <coneGeometry args={[0.08, 0.15, 8]} />
        <meshStandardMaterial color="#fcc" />
      </mesh>

      {/* Mouth cavity */}
      <mesh ref={mouthRef} position={[0, -0.3, 0.85]} scale={[0.3, 0.15, 0.15]}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial color="#511" roughness={0.9} />
      </mesh>

      {/* Upper lip */}
      <mesh ref={upperLipRef} position={[0, 0.15, 0.92]} scale={[0.4, 0.06, 0.1]}>
        <sphereGeometry args={[1, 16, 8]} />
        <meshStandardMaterial color="#d99" />
      </mesh>

      {/* Lower lip */}
      <mesh ref={lowerLipRef} position={[0, -0.15, 0.92]} scale={[0.4, 0.08, 0.1]}>
        <sphereGeometry args={[1, 16, 8]} />
        <meshStandardMaterial color="#d99" />
      </mesh>

      {/* Tongue (visible for certain visemes) */}
      <mesh ref={tongueRef} position={[0, -0.25, 0.9]} scale={[0.2, 0.08, 0.15]}>
        <sphereGeometry args={[1, 16, 8]} />
        <meshStandardMaterial
          color="#e88"
          transparent
          opacity={0}
          roughness={0.8}
        />
      </mesh>

      {/* Highlight current viseme with colored ring */}
      <mesh position={[0, 0, 0]} rotation={[0, 0, 0]}>
        <torusGeometry args={[1.3, 0.02, 16, 100]} />
        <meshStandardMaterial color={targetShape.color} emissive={targetShape.color} emissiveIntensity={0.5} />
      </mesh>
    </group>
  )
}

/**
 * Main 3D Avatar Canvas Component
 */
export default function Avatar3D({ visemeId = 1, className = '' }) {
  return (
    <div className={`w-full h-full ${className}`}>
      <Canvas>
        {/* Camera */}
        <PerspectiveCamera makeDefault position={[0, 0, 4]} fov={50} />

        {/* Lights */}
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 5, 5]} intensity={0.8} castShadow />
        <directionalLight position={[-5, -5, -5]} intensity={0.3} />
        <pointLight position={[0, 2, 3]} intensity={0.5} color="#fff" />

        {/* Avatar */}
        <FaceAvatar visemeId={visemeId} transitionSpeed={0.15} />

        {/* Controls */}
        <OrbitControls
          enableZoom={true}
          enablePan={false}
          minDistance={2}
          maxDistance={6}
          minPolarAngle={Math.PI / 4}
          maxPolarAngle={Math.PI / 1.5}
        />
      </Canvas>
    </div>
  )
}
