import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import AvatarVRM from './AvatarVRM'
import VocalTract from './VocalTract'
import { CueGlyph } from './CueBadges'
import { curriculumAPI } from '../api'

/**
 * 3D LipSync Player - VRM-based avatar with full playback controls
 * - Auto play / pause
 * - Frame-by-frame navigation
 * - Speed control (0.5x ~ 2x)
 * - Replay bug fixed (uses internal ref, not prop)
 * showControls=false면 아바타 무대만 남긴다(상태 배지·'Viseme N'·진행바·재생/프레임/속도·조음 토글 숨김).
 * 레슨 입모양 카드처럼 "무한 반복 재생, 다시 보기 없음"(핸드오프 §3.4)인 자리에서 쓴다. 기본값은 기존 그대로(true).
 */
export default function LipSyncPlayer3D({
  visemes = [],
  isPlaying = false,
  onComplete = () => {},
  onFrameChange = () => {},
  loop = false,
  restartKey = 0,
  cueText = null,   // 주면 재생 중 현재 음절의 시각증강 기호(축 J)를 입 근처에 겹쳐 표시
  showControls = true,
  stageHeight = 360,   // 아바타 무대 높이(px). 컨트롤을 숨긴 카드에서는 카드 높이에 맞춰 넘긴다.
}) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [speed, setSpeed] = useState(1.0)
  const [isPaused, setIsPaused] = useState(false)
  const [xray, setXray] = useState(false)       // 투명 두상(피부 반투명 → 혀·치아 노출)
  const [showTract, setShowTract] = useState(false)  // 성도 단면(측면) 도식
  const [cues, setCues] = useState([])          // 축 J: 안 보이는 자질 기호(음절별)

  // Refs to avoid stale closure issues
  const timeoutRef = useRef(null)
  const isPlayingRef = useRef(false)
  const indexRef = useRef(0)
  const speedRef = useRef(1.0)
  const loopRef = useRef(loop)
  const onCompleteRef = useRef(onComplete)
  const onFrameChangeRef = useRef(onFrameChange)
  const previousRestartKeyRef = useRef(restartKey)

  const currentViseme = visemes[currentIndex] || null

  loopRef.current = loop
  onCompleteRef.current = onComplete
  onFrameChangeRef.current = onFrameChange

  // Sync speed ref
  useEffect(() => {
    speedRef.current = speed
  }, [speed])

  // 축 J: 재생할 텍스트의 시각증강 기호를 미리 받아 둔다(현재 음절에 맞춰 입 근처 표시).
  useEffect(() => {
    let on = true
    if (!cueText) { setCues([]); return undefined }
    curriculumAPI.getCues(cueText)
      .then((d) => { if (on) setCues(d.cues || []) })
      .catch(() => { if (on) setCues([]) })
    return () => { on = false }
  }, [cueText])

  const clearTimer = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
  }, [])

  const emitFrameChange = useCallback((index, options = {}) => {
    const frame = visemes[index] || null
    const progress = options.progress ?? (
      visemes.length > 0 ? Math.min(1, (index + 1) / visemes.length) : 0
    )

    onFrameChangeRef.current({
      index,
      total: visemes.length,
      frame,
      textIndex: Number.isInteger(frame?.text_index) ? frame.text_index : null,
      progress,
      completed: Boolean(options.completed),
      cycleComplete: Boolean(options.cycleComplete),
    })
  }, [visemes])

  const scheduleNext = useCallback((index) => {
    if (!visemes || index >= visemes.length) {
      isPlayingRef.current = false
      setIsPaused(false)
      if (loopRef.current) {
        emitFrameChange(-1, { progress: 0, cycleComplete: true })
        timeoutRef.current = setTimeout(() => {
          if (isPlayingRef.current) return
          startFromIndex(0)
        }, 400)
      } else {
        emitFrameChange(visemes.length - 1, { progress: 1, completed: true })
        onCompleteRef.current()
      }
      return
    }

    const frame = visemes[index]
    indexRef.current = index
    setCurrentIndex(index)
    emitFrameChange(index)

    timeoutRef.current = setTimeout(() => {
      if (!isPlayingRef.current) return
      scheduleNext(index + 1)
    }, frame.duration_ms / speedRef.current)
  }, [visemes, emitFrameChange])

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

  // Restart an active cycle when the parent reveals the timed subtitle.
  useEffect(() => {
    if (previousRestartKeyRef.current === restartKey) return
    previousRestartKeyRef.current = restartKey

    if (visemes.length > 0) startFromIndex(0)
  }, [restartKey])

  // Frame-by-frame navigation
  const goToFrame = useCallback((idx) => {
    stopPlayback()
    const clamped = Math.max(0, Math.min(idx, visemes.length - 1))
    indexRef.current = clamped
    setCurrentIndex(clamped)
    emitFrameChange(clamped)
  }, [visemes.length, stopPlayback, emitFrameChange])

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

  // 현재 프레임의 음절(text_index)에 해당하는 시각증강 기호 — cue.syllable_index와 동일 인덱스 공간(engine)
  const curSyl = Number.isInteger(currentViseme?.text_index) ? currentViseme.text_index : null
  const activeCues = curSyl != null ? cues.filter((c) => c.syllable_index === curSyl) : []

  return (
    <div className="relative w-full">
      {/* VRM Avatar Viewport */}
      <div className="relative w-full rounded-2xl overflow-hidden shadow-2xl bg-gradient-to-b from-slate-800 to-slate-900 [container-type:size]"
        style={{ height: `${stageHeight}px` }}
      >
        <AvatarVRM
          visemeId={currentViseme?.viseme ?? 15}
          xray={xray}
        />

        {/* 시각증강 기호(축 J) — 현재 음절의 안 보이는 자질(기식·긴장·비음)을 입 근처에 겹쳐 표시 */}
        {activeCues.length > 0 && (
          <div className="pointer-events-none absolute left-[calc(50%+30cqh)] top-[68%] -translate-y-1/2 flex gap-1">
            {activeCues.map((c, j) => (
              <span
                key={j}
                title={c.cue}
                style={{ opacity: c.strength ?? 1 }}
                className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/90 shadow-md ring-1 ring-black/5"
              >
                <CueGlyph cue={c.cue} size={16} />
              </span>
            ))}
          </div>
        )}

        {/* 성도 단면 오버레이(계획서 E) — 혀·입술·턱 조음을 측면 도식으로 */}
        {showTract && (
          <div className="absolute bottom-2 right-2 w-28 sm:w-32 bg-slate-900/85 border border-slate-700 rounded-xl p-1 backdrop-blur-sm">
            <VocalTract visemeId={currentViseme?.viseme ?? 15} />
          </div>
        )}

        {/* Status badge */}
        {showControls && isRunning && (
          <div className="absolute top-3 right-3 bg-green-500/90 text-white px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 backdrop-blur-sm">
            <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
            재생 중
          </div>
        )}

        {/* Frame info overlay */}
        {showControls && (
          <div className="absolute bottom-3 left-3 bg-black/50 backdrop-blur-sm text-white px-3 py-1.5 rounded-lg text-xs">
            <span className="font-medium">Viseme {currentViseme?.viseme ?? '-'}</span>
            <span className="text-gray-400 ml-2">{currentViseme?.duration_ms ?? 0}ms</span>
          </div>
        )}
      </div>

      {showControls && (<>
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
          aria-label="이전 프레임"
        >
          <span aria-hidden="true">◀◀</span>
        </button>

        {/* Play/Pause */}
        <button
          onClick={togglePause}
          className="flex-1 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white font-medium transition-colors"
        >
          {isRunning ? '일시정지' : '재생'}
        </button>

        {/* Next frame */}
        <button
          onClick={nextFrame}
          disabled={currentIndex >= visemes.length - 1}
          className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-gray-700"
          title="다음 프레임"
          aria-label="다음 프레임"
        >
          <span aria-hidden="true">▶▶</span>
        </button>

        {/* Replay */}
        <button
          onClick={replay}
          className="p-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors text-gray-700"
          title="처음부터 재생"
          aria-label="처음부터 재생"
        >
          <span aria-hidden="true">↺</span>
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

      {/* 조음 시각화 토글 — 투명 두상 + 성도 단면(계획서 F·E) */}
      <div className="mt-2 flex gap-2">
        <button
          onClick={() => setXray((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg transition-colors ${xray ? 'bg-violet-600 text-white font-semibold' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          title="피부를 반투명하게 해 안 보이는 혀·치아를 드러냄"
        >
          투명 두상
        </button>
        <button
          onClick={() => setShowTract((v) => !v)}
          className={`flex-1 py-1.5 text-xs rounded-lg transition-colors ${showTract ? 'bg-violet-600 text-white font-semibold' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
          title="측면 성도 단면으로 혀·입술·턱 조음 보기"
        >
          성도 단면
        </button>
      </div>
      </>)}
    </div>
  )
}
