import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

/**
 * LipSyncPlayer Component
 * Renders viseme animation sequence with smooth transitions using Framer Motion
 *
 * Props:
 * - visemes: Array of {viseme, duration_ms, transition_ms}
 * - isPlaying: Boolean to control animation playback
 * - onComplete: Callback when animation finishes
 * - loop: Whether to loop animation
 */
export default function LipSyncPlayer({
  visemes = [],
  isPlaying = false,
  onComplete = () => {},
  loop = false,
}) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAnimating, setIsAnimating] = useState(false)
  const timeoutRef = useRef(null)
  const startTimeRef = useRef(null)

  const currentViseme = visemes[currentIndex]

  useEffect(() => {
    if (isPlaying && visemes.length > 0) {
      playAnimation()
    } else {
      stopAnimation()
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
    }
  }, [isPlaying, visemes])

  const playAnimation = () => {
    setIsAnimating(true)
    setCurrentIndex(0)
    startTimeRef.current = Date.now()
    playNextFrame(0)
  }

  const playNextFrame = (index) => {
    if (!visemes || index >= visemes.length) {
      // Animation complete
      setIsAnimating(false)
      if (loop && isPlaying) {
        // Restart animation
        setTimeout(() => {
          if (isPlaying) {
            playAnimation()
          }
        }, 500)
      } else {
        onComplete()
      }
      return
    }

    const frame = visemes[index]
    setCurrentIndex(index)

    // Schedule next frame
    timeoutRef.current = setTimeout(() => {
      if (isPlaying) {
        playNextFrame(index + 1)
      }
    }, frame.duration_ms)
  }

  const stopAnimation = () => {
    setIsAnimating(false)
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }

  const restartAnimation = () => {
    stopAnimation()
    setTimeout(() => {
      playAnimation()
    }, 100)
  }

  if (!visemes || visemes.length === 0) {
    return (
      <div className="w-full aspect-square bg-gray-100 rounded-2xl flex items-center justify-center">
        <p className="text-gray-400">텍스트를 입력하세요</p>
      </div>
    )
  }

  return (
    <div className="relative w-full">
      {/* Viseme Display */}
      <div className="relative w-full aspect-square bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl overflow-hidden shadow-lg">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentIndex}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{
              duration: (currentViseme?.transition_ms || 50) / 1000,
              ease: 'easeInOut',
            }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <img
              src={`/visemes/${currentViseme?.viseme || 1}.svg`}
              alt={`Viseme ${currentViseme?.viseme}`}
              className="w-full h-full object-contain"
              onError={(e) => {
                // Fallback to colored placeholder if image not found
                e.target.style.display = 'none'
                e.target.nextSibling.style.display = 'flex'
              }}
            />
            {/* Fallback placeholder */}
            <div
              className="absolute inset-0 items-center justify-center"
              style={{ display: 'none' }}
            >
              <div
                className="w-48 h-48 rounded-full flex items-center justify-center text-white text-6xl font-bold shadow-2xl"
                style={{
                  backgroundColor: getVisemeColor(currentViseme?.viseme || 1),
                }}
              >
                {currentViseme?.viseme || 1}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Animation indicator */}
        {isAnimating && (
          <div className="absolute top-4 right-4">
            <div className="bg-green-500 text-white px-3 py-1 rounded-full text-xs font-medium flex items-center">
              <span className="w-2 h-2 bg-white rounded-full mr-2 animate-pulse" />
              재생 중
            </div>
          </div>
        )}
      </div>

      {/* Progress Bar */}
      <div className="mt-4 bg-gray-200 rounded-full h-2 overflow-hidden">
        <motion.div
          className="bg-primary-500 h-full"
          initial={{ width: '0%' }}
          animate={{
            width: `${((currentIndex + 1) / visemes.length) * 100}%`,
          }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Frame Info */}
      <div className="mt-2 flex justify-between items-center text-sm text-gray-600">
        <span>
          프레임: {currentIndex + 1} / {visemes.length}
        </span>
        <span>Viseme ID: {currentViseme?.viseme || '-'}</span>
      </div>

      {/* Controls */}
      <div className="mt-4 flex space-x-2">
        {!isPlaying && (
          <button
            onClick={playAnimation}
            className="btn-primary flex-1"
          >
            ▶ 재생
          </button>
        )}
        {isPlaying && (
          <button
            onClick={stopAnimation}
            className="btn-secondary flex-1"
          >
            ⏸ 일시정지
          </button>
        )}
        <button
          onClick={restartAnimation}
          className="btn-secondary px-4"
          title="다시 재생"
        >
          ↻
        </button>
      </div>
    </div>
  )
}

/**
 * Generate distinct colors for each viseme type
 */
function getVisemeColor(visemeId) {
  const colors = [
    '#EF4444', // Red
    '#F59E0B', // Amber
    '#10B981', // Green
    '#3B82F6', // Blue
    '#8B5CF6', // Purple
    '#EC4899', // Pink
    '#14B8A6', // Teal
    '#F97316', // Orange
    '#6366F1', // Indigo
    '#84CC16', // Lime
    '#06B6D4', // Cyan
    '#A855F7', // Violet
    '#F43F5E', // Rose
    '#64748B', // Slate
    '#78716C', // Stone
  ]

  return colors[(visemeId - 1) % colors.length]
}
