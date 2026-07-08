import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import AvatarVRM from './AvatarVRM'

/**
 * 3D LipSync Player - VRM-based avatar with full playback controls
 * - Auto play / pause
 * - Frame-by-frame navigation
 * - Speed control (0.5x ~ 2x)
 * - Replay bug fixed (uses internal ref, not prop)
 */
export default function LipSyncPlayer3D({
  visemes = [],
  isPlaying = false,
  onComplete = () => {},
  loop = false,
}) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [speed, setSpeed] = useState(1.0)
  const [isPaused, setIsPaused] = useState(false)

  // Refs to avoid stale closure issues
  const timeoutRef = useRef(null)
  const isPlayingRef = useRef(false)
  const indexRef = useRef(0)
  const speedRef = useRef(1.0)

  const currentViseme = visemes[currentIndex] || null

  // Sync speed ref
  useEffect(() => {
    speedRef.current = speed
  }, [speed])

  const clearTimer = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  const scheduleNext = useCallback((index) => {
    if (!visemes || index >= visemes.length) {
      isPlayingRef.current = false
      setIsPaused(false)
      if (loop) {
        setTimeout(() => {
          if (isPlayingRef.current) return
          startFromIndex(0)
        }, 400)
      } else {
        onComplete()
      }
      return
    }

    const frame = visemes[index]
    indexRef.current = index
    setCurrentIndex(index)

    timeoutRef.current = setTimeout(() => {
      if (!isPlayingRef.current) return
      scheduleNext(index + 1)
    }, frame.duration_ms / speedRef.current)
  }, [visemes, loop, onComplete])

  const startFromIndex = useCallback((fromIndex = 0) => {
    clearTimer()
    isPlayingRef.current = true
    setIsPaused(false)
    indexRef.current = fromIndex
    setCurrentIndex(fromIndex)
    scheduleNext(fromIndex)
  }, [clearTimer, scheduleNext])

  const stopPlayback = useCallback(() => {
    clearTimer()
    isPlayingRef.current = false
    setIsPaused(true)
  }, [clearTimer])

  // Respond to external isPlaying prop
  useEffect(() => {
    if (isPlaying && visemes.length > 0) {
      startFromIndex(0)
    } else if (!isPlaying) {
      clearTimer()
      isPlayingRef.current = false
    }
    return clearTimer
  }, [isPlaying, visemes])

  // Frame-by-frame navigation
  const goToFrame = useCallback((idx) => {
    stopPlayback()
    const clamped = Math.max(0, Math.min(idx, visemes.length - 1))
    indexRef.current = clamped
    setCurrentIndex(clamped)
  }, [visemes.length, stopPlayback])

  const prevFrame = () => goToFrame(currentIndex - 1)
  const nextFrame = () => goToFrame(currentIndex + 1)

  const replay = () => startFromIndex(0)

  const togglePause = () => {
    if (isPlayingRef.current) {
      stopPlayback()
    } else {
      startFromIndex(currentIndex)
    }
  }

  if (!visemes || visemes.length === 0) {
    return (
      <div className="w-full aspect-square bg-gradient-to-br from-gray-900 to-gray-700 rounded-2xl flex items-center justify-center">
        <p className="text-gray-400 text-sm">텍스트를 입력하면 여기에 입모양이 나타납니다</p>
      </div>
    )
  }

  const progress = visemes.length > 0 ? ((currentIndex + 1) / visemes.length) * 100 : 0
  const isRunning = isPlayingRef.current && !isPaused

  return (
    <div className="relative w-full">
      {/* VRM Avatar Viewport */}
      <div className="relative w-full rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-b from-slate-800 to-slate-900"
        style={{ height: '360px' }}
      >
        <AvatarVRM
          visemeId={currentViseme?.viseme ?? 15}
          modelUrl="/models/avatar.vrm"
        />

        {/* Status badge */}
        {isRunning && (
          <div className="absolute top-3 right-3 bg-green-500/90 text-white px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 backdrop-blur-sm">
            <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
            재생 중
          </div>
        )}

        {/* Frame info overlay */}
        <div className="absolute bottom-3 left-3 bg-black/50 backdrop-blur-sm text-white px-3 py-1.5 rounded-lg text-xs">
          <span className="font-medium">Viseme {currentViseme?.viseme ?? '-'}</span>
          <span className="text-gray-400 ml-2">{currentViseme?.duration_ms ?? 0}ms</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-3 bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <motion.div
          className="bg-gradient-to-r from-blue-500 to-purple-500 h-full rounded-full"
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.2 }}
        />
      </div>

      {/* Frame counter */}
      <div className="mt-1.5 flex justify-between items-center text-xs text-gray-500">
        <span>프레임 {currentIndex + 1} / {visemes.length}</span>
        <span>속도 {speed}x</span>
      </div>

      {/* Main controls */}
      <div className="mt-3 flex items-center gap-2">
        {/* Prev frame */}
        <button
          onClick={prevFrame}
          disabled={currentIndex === 0}
          className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-gray-700"
          title="이전 프레임"
        >
          ◀◀
        </button>

        {/* Play/Pause */}
        <button
          onClick={togglePause}
          className="flex-1 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white font-medium transition-colors"
        >
          {isRunning ? '⏸ 일시정지' : '▶ 재생'}
        </button>

        {/* Next frame */}
        <button
          onClick={nextFrame}
          disabled={currentIndex >= visemes.length - 1}
          className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-gray-700"
          title="다음 프레임"
        >
          ▶▶
        </button>

        {/* Replay */}
        <button
          onClick={replay}
          className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors text-gray-700"
          title="처음부터 재생"
        >
          ↺
        </button>
      </div>

      {/* Speed control */}
      <div className="mt-3 flex items-center gap-3">
        <span className="text-xs text-gray-500 shrink-0">재생 속도</span>
        <div className="flex gap-1 flex-1">
          {[0.5, 0.75, 1.0, 1.5, 2.0].map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`flex-1 py-1 text-xs rounded transition-colors ${
                speed === s
                  ? 'bg-primary-500 text-white font-semibold'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
