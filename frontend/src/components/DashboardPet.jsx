import { useLayoutEffect, useRef, useState } from 'react'

/**
 * DashboardPet — 대시보드 히어로의 빈 공간에서 사는 마스코트 펫.
 *
 * · 슬라이드(학습/문장실전/말하기/촉각)마다 색·응원 대사가 바뀐다.
 * · 클릭 → 응원 말풍선, 드래그 → 이동, 세게 튕기면 회전하며 컬링처럼 미끄러진다.
 * · 벽(히어로 카드 안쪽)에 닿으면 튕기고, 가만히 두면 아주 조금씩 랜덤하게 배회한다.
 * · 텍스트 카피 블록([data-hero-copy])은 장애물 → 그 위로는 못 올라가고 튕겨난다.
 *
 * 성능: 매 프레임 DOM transform을 직접 갱신(리렌더 없음). 위치/속도는 ref로 관리.
 */
const PET_THEMES = {
  viseme: {
    grad: 'from-sky-300 via-sky-400 to-sky-600',
    cheers: [
      '천천히 해도 괜찮아요!', '입모양 하나씩, 잘하고 있어요', '오늘도 시작이 반이에요 ✨', '눈으로 듣는 연습, 멋져요!',
      '조금씩, 하지만 꾸준히 💙', '어제보다 한 걸음 더!', '입술을 잘 보고 있네요 👀', '실수해도 괜찮아, 다시 해봐요',
      '집중력이 대단해요!', '오늘의 나, 응원할게요 ✨', '눈이 점점 밝아지고 있어요', '잘하고 있어, 믿어요!',
    ],
  },
  scenario: {
    grad: 'from-cyan-300 via-cyan-400 to-blue-500',
    cheers: [
      '실전 문장, 자신 있게!', '상황 속으로 뛰어들어요', '한 문장씩 정복해요 💪', '오늘의 대화도 파이팅!',
      '문맥을 읽는 눈, 최고예요', '틀려도 배움이 남아요', '실전 감각이 자라고 있어요 🌱', '한 걸음씩 대화 고수로!',
      '차분하게, 끝까지 읽어봐요', '이 상황, 이제 익숙하죠?', '멋진 도전이에요 👏', '문장이 눈에 들어오기 시작해요!',
    ],
  },
  speaking: {
    grad: 'from-rose-300 via-rose-400 to-pink-500',
    cheers: [
      '또박또박 좋아요!', '소리 내는 게 용기예요', '억양까지 완벽해요 🎵', '입을 크게, 자신 있게!',
      '숨 고르고, 천천히 말해요', '목소리에 자신감이 붙었어요', '한 음절씩 또렷하게 🌟', '떨려도 괜찮아, 잘하고 있어요',
      '오늘 발음, 정말 좋아졌어요', '입 모양이 살아있네요 👄', '조금 더 크게, 좋아요!', '용기 내줘서 고마워요 💗',
    ],
  },
  tactile: {
    grad: 'from-violet-300 via-violet-400 to-purple-600',
    cheers: [
      '손끝의 감각을 믿어요', '느낌으로 익혀봐요', '촉각 마스터 가자! ✋', '진동까지 느껴봐요',
      '손끝이 점점 예민해져요 ✨', '작은 떨림도 놓치지 마요', '천천히, 느낌에 집중해요', '이 감각, 기억해두세요 💜',
      '손으로 듣는 당신, 대단해요', '조금씩 또렷해지고 있어요', '오늘도 한 걸음 나아갔어요', '느낌표가 켜지는 중! 💡',
    ],
  },
}

const SIZE = 64            // 펫 크기(px)
const FRICTION = 0.986     // 선형 마찰(작을수록 빨리 멈춤) — 컬링처럼 길게 미끄러지게
const ANG_FRICTION = 0.96  // 회전 마찰
const RESTITUTION = 0.7    // 반발 계수(튕김 강도)
const MAX_SPEED = 46       // 프레임당 최대 이동(터널링 방지)
const PAD = 8              // 카드 안쪽 여백

export default function DashboardPet({ slideId = 'viseme', obstacleSelector = '[data-hero-copy]', bottomReserve = 60 }) {
  const theme = PET_THEMES[slideId] || PET_THEMES.viseme
  const themeRef = useRef(theme)
  themeRef.current = theme

  const petRef = useRef(null)
  const bodyRef = useRef(null)
  const pos = useRef({ x: 0, y: 0 })
  const vel = useRef({ x: 0, y: 0 })
  const angle = useRef(0)
  const angVel = useRef(0)

  const dragging = useRef(false)
  const pointerId = useRef(null)
  const dragOffset = useRef({ x: 0, y: 0 })
  const lastPointer = useRef({ x: 0, y: 0, t: 0 })
  const pointerVel = useRef({ x: 0, y: 0 })
  const movedDist = useRef(0)

  const initialized = useRef(false)
  const idleTimer = useRef(60)
  const rafRef = useRef(0)
  const cheerTimeout = useRef(null)
  const [cheer, setCheer] = useState(null)

  const metrics = () => {
    const el = petRef.current
    const container = el?.offsetParent
    if (!container) return null
    const cw = container.clientWidth
    const ch = container.clientHeight
    const nodes = container.querySelectorAll(obstacleSelector)
    const obstacles = []
    if (nodes.length) {
      const cRect = container.getBoundingClientRect()
      nodes.forEach((node) => {
        const r = node.getBoundingClientRect()
        if (r.width && r.height) obstacles.push({ x: r.left - cRect.left, y: r.top - cRect.top, w: r.width, h: r.height })
      })
    }
    return { cw, ch, obstacles }
  }

  // 펫이 장애물 사각형과 겹치면 최소 침투축으로 밀어내고(그리고 드래그가 아니면) 튕긴다.
  const resolveObstacle = (o, isDrag) => {
    const px = pos.current.x
    const py = pos.current.y
    const m = 4
    const ox = o.x - m
    const oy = o.y - m
    const ow = o.w + m * 2
    const oh = o.h + m * 2
    if (px + SIZE <= ox || px >= ox + ow || py + SIZE <= oy || py >= oy + oh) return
    const overlapLeft = px + SIZE - ox
    const overlapRight = ox + ow - px
    const overlapTop = py + SIZE - oy
    const overlapBottom = oy + oh - py
    const min = Math.min(overlapLeft, overlapRight, overlapTop, overlapBottom)
    if (min === overlapLeft) { pos.current.x = ox - SIZE; if (!isDrag) vel.current.x = -Math.abs(vel.current.x) * RESTITUTION }
    else if (min === overlapRight) { pos.current.x = ox + ow; if (!isDrag) vel.current.x = Math.abs(vel.current.x) * RESTITUTION }
    else if (min === overlapTop) { pos.current.y = oy - SIZE; if (!isDrag) vel.current.y = -Math.abs(vel.current.y) * RESTITUTION }
    else { pos.current.y = oy + oh; if (!isDrag) vel.current.y = Math.abs(vel.current.y) * RESTITUTION }
    if (!isDrag) angVel.current += (Math.random() - 0.5) * 3
  }

  const clampSpeed = () => {
    const s = Math.hypot(vel.current.x, vel.current.y)
    if (s > MAX_SPEED) {
      vel.current.x *= MAX_SPEED / s
      vel.current.y *= MAX_SPEED / s
    }
  }

  const step = () => {
    const el = petRef.current
    if (el) {
      const m = metrics()
      if (m) {
        const minX = PAD
        const minY = PAD
        const maxX = Math.max(minX, m.cw - SIZE - PAD)
        const maxY = Math.max(minY, m.ch - SIZE - bottomReserve)

        if (!dragging.current) {
          clampSpeed()
          pos.current.x += vel.current.x
          pos.current.y += vel.current.y
          vel.current.x *= FRICTION
          vel.current.y *= FRICTION
          angle.current += angVel.current
          angVel.current *= ANG_FRICTION

          // 가만히 있을 때 아주 조금씩 랜덤 방향으로 배회
          const speed = Math.hypot(vel.current.x, vel.current.y)
          idleTimer.current -= 1
          if (speed < 0.22 && idleTimer.current <= 0) {
            const a = Math.random() * Math.PI * 2
            const p = 0.3 + Math.random() * 0.45
            vel.current.x += Math.cos(a) * p
            vel.current.y += Math.sin(a) * p
            idleTimer.current = 90 + Math.floor(Math.random() * 150)
          }

          // 벽 튕김
          if (pos.current.x < minX) { pos.current.x = minX; vel.current.x = Math.abs(vel.current.x) * RESTITUTION; angVel.current += (Math.random() - 0.5) * 4 }
          if (pos.current.x > maxX) { pos.current.x = maxX; vel.current.x = -Math.abs(vel.current.x) * RESTITUTION; angVel.current += (Math.random() - 0.5) * 4 }
          if (pos.current.y < minY) { pos.current.y = minY; vel.current.y = Math.abs(vel.current.y) * RESTITUTION; angVel.current += (Math.random() - 0.5) * 4 }
          if (pos.current.y > maxY) { pos.current.y = maxY; vel.current.y = -Math.abs(vel.current.y) * RESTITUTION; angVel.current += (Math.random() - 0.5) * 4 }

          for (const o of m.obstacles) resolveObstacle(o, false)
        }

        pos.current.x = Math.max(minX, Math.min(maxX, pos.current.x))
        pos.current.y = Math.max(minY, Math.min(maxY, pos.current.y))
        el.style.transform = `translate(${pos.current.x}px, ${pos.current.y}px)`
        if (bodyRef.current) bodyRef.current.style.transform = `rotate(${angle.current}deg)`
      }
    }
    rafRef.current = requestAnimationFrame(step)
  }

  const showCheer = () => {
    const list = themeRef.current.cheers
    setCheer(list[Math.floor(Math.random() * list.length)])
    clearTimeout(cheerTimeout.current)
    cheerTimeout.current = setTimeout(() => setCheer(null), 2600)
    // 기뻐서 살짝 폴짝
    vel.current.y -= 3.2
    angVel.current += (Math.random() - 0.5) * 6
  }

  const onPointerDown = (e) => {
    e.stopPropagation()
    const el = petRef.current
    const container = el?.offsetParent
    if (!container) return
    dragging.current = true
    pointerId.current = e.pointerId
    try { el.setPointerCapture(e.pointerId) } catch { /* noop */ }
    movedDist.current = 0
    vel.current = { x: 0, y: 0 }
    angVel.current = 0
    const cRect = container.getBoundingClientRect()
    dragOffset.current = { x: e.clientX - cRect.left - pos.current.x, y: e.clientY - cRect.top - pos.current.y }
    lastPointer.current = { x: e.clientX, y: e.clientY, t: performance.now() }
    pointerVel.current = { x: 0, y: 0 }
  }

  const onPointerMove = (e) => {
    if (!dragging.current || e.pointerId !== pointerId.current) return
    const el = petRef.current
    const container = el?.offsetParent
    if (!container) return
    const cRect = container.getBoundingClientRect()
    pos.current.x = e.clientX - cRect.left - dragOffset.current.x
    pos.current.y = e.clientY - cRect.top - dragOffset.current.y
    const m = metrics()
    if (m?.obstacles) for (const o of m.obstacles) resolveObstacle(o, true)
    const now = performance.now()
    const dt = Math.max(1, now - lastPointer.current.t)
    pointerVel.current = { x: ((e.clientX - lastPointer.current.x) / dt) * 16, y: ((e.clientY - lastPointer.current.y) / dt) * 16 }
    movedDist.current += Math.hypot(e.clientX - lastPointer.current.x, e.clientY - lastPointer.current.y)
    lastPointer.current = { x: e.clientX, y: e.clientY, t: now }
  }

  const onPointerUp = (e) => {
    if (!dragging.current || e.pointerId !== pointerId.current) return
    dragging.current = false
    try { petRef.current?.releasePointerCapture(e.pointerId) } catch { /* noop */ }
    if (movedDist.current < 6) {
      // 거의 안 움직였으면 클릭 → 응원
      vel.current = { x: 0, y: 0 }
      angVel.current = 0
      showCheer()
      return
    }
    // 튕기기: 손가락 속도를 그대로 넘겨받고, 가로 속도 비례로 회전(빙글빙글)
    vel.current = { x: pointerVel.current.x, y: pointerVel.current.y }
    clampSpeed()
    const flick = Math.hypot(pointerVel.current.x, pointerVel.current.y)
    angVel.current = Math.max(-24, Math.min(24, pointerVel.current.x * 0.85 + (Math.random() - 0.5) * flick * 0.4))
    idleTimer.current = 120
  }

  useLayoutEffect(() => {
    const el = petRef.current
    const container = el?.offsetParent
    if (container && !initialized.current) {
      pos.current = { x: container.clientWidth * 0.58, y: container.clientHeight * 0.28 }
      el.style.transform = `translate(${pos.current.x}px, ${pos.current.y}px)`
      initialized.current = true
    }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
    rafRef.current = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(rafRef.current)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      clearTimeout(cheerTimeout.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={petRef}
      onPointerDown={onPointerDown}
      role="button"
      aria-label="응원 펫 — 클릭하면 응원해주고 드래그하면 옮길 수 있어요"
      className="absolute left-0 top-0 z-[16] hidden h-16 w-16 cursor-grab touch-none select-none active:cursor-grabbing lg:block"
      style={{ willChange: 'transform' }}
    >
      {cheer && (
        <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-2xl bg-white px-3 py-1.5 text-[11px] font-black text-slate-800 shadow-lg">
          {cheer}
          <span className="absolute -bottom-1 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rotate-45 bg-white" />
        </div>
      )}
      <div ref={bodyRef} style={{ willChange: 'transform' }} className={`relative h-16 w-16 rounded-[48%_44%_50%_46%] bg-gradient-to-br ${theme.grad} shadow-xl`}>
        <span className="absolute left-[19px] top-[25px] h-2.5 w-2.5 rounded-full bg-slate-900" />
        <span className="absolute left-[35px] top-[25px] h-2.5 w-2.5 rounded-full bg-slate-900" />
        <span className="absolute left-[21px] top-[35px] h-3.5 w-[22px] rounded-b-full border-b-[5px] border-white/90" />
      </div>
    </div>
  )
}
