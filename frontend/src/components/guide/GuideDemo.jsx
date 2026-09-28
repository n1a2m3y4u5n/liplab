import { useEffect, useRef, useState } from 'react'
import GuideMock, { DEMOS } from './GuideMockups'

/**
 * 사용법 가이드의 동적 요소(9/28): 주석 ↔ 목업 영역 연동, 시연 루프, 재생·일시정지.
 *  - useAnnotLink: 가리킨 영역(hover·focus)과 누른 영역(pin). 가리킨 것이 우선이다.
 *  - useDemo: 탭의 시연(DEMOS)을 틱마다 넘긴다. 탭이 화면에 보이고, 창이 보이고, 사용자가 멈추지 않았고,
 *    영역을 강조해 장면을 붙잡지 않았을 때만 돈다. 동작 최소화면 돌지 않고 마지막 장면(final)을 보인다.
 *  - ShotSet: 탭의 사진 상자들 + 재생·일시정지 버튼.
 * 타이머는 setInterval 하나이고, 탭을 떠나 본문이 사라지거나 조건이 풀리면 정리된다.
 */

function readReduced() {
  if (typeof window === 'undefined') return false
  const media = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  return !!media || document.documentElement.classList.contains('a11y-reduce-motion')
}

// 동작 최소화: OS 설정(prefers-reduced-motion) 또는 앱 접근성 설정(html.a11y-reduce-motion)
export function useReducedMotion() {
  const [reduced, setReduced] = useState(readReduced)
  useEffect(() => {
    const sync = () => setReduced(readReduced())
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    mq?.addEventListener?.('change', sync)
    const mo = typeof MutationObserver !== 'undefined' ? new MutationObserver(sync) : null
    mo?.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => {
      mq?.removeEventListener?.('change', sync)
      mo?.disconnect()
    }
  }, [])
  return reduced
}

export function useAnnotLink() {
  const [hovered, setHovered] = useState(null)
  const [pinned, setPinned] = useState(null)
  return {
    active: hovered ?? pinned,
    pinned,
    hover: setHovered,
    pick: (k) => setPinned((p) => (p === k ? null : k)),
  }
}

const total = (demo) => demo.steps.reduce((s, [, n]) => s + n, 0)
function sceneAt(demo, tick) {
  let t = tick % total(demo)
  for (const [scene, n] of demo.steps) {
    if (t < n) return scene
    t -= n
  }
  return demo.steps[0][0]
}
function startOf(demo, scene) {
  let t = 0
  for (const [s, n] of demo.steps) {
    if (s === scene) return t
    t += n
  }
  return 0
}

export function useDemo(demoKey, active, ref) {
  const demo = DEMOS[demoKey] || null
  const reduced = useReducedMotion()
  const [tick, setTick] = useState(0)
  const [paused, setPaused] = useState(false)
  const [inView, setInView] = useState(typeof IntersectionObserver === 'undefined')
  const [pageShown, setPageShown] = useState(() => typeof document === 'undefined' || !document.hidden)

  useEffect(() => {
    const el = ref.current
    if (!demo || !el || typeof IntersectionObserver === 'undefined') return undefined
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.25 })
    io.observe(el)
    return () => io.disconnect()
  }, [demo, ref])

  useEffect(() => {
    const sync = () => setPageShown(!document.hidden)
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [])

  const held = demo && active ? demo.areaScene[active] || null : null
  const running = !!demo && !reduced && !paused && inView && pageShown && !held

  useEffect(() => {
    if (!running) return undefined
    const id = setInterval(() => setTick((t) => t + 1), demo.tick)
    return () => clearInterval(id)
  }, [running, demo])

  // 강조로 장면을 붙잡으면 그 장면 처음으로 옮겨 두어, 놓았을 때 그 장면부터 잇는다
  useEffect(() => {
    if (held) setTick(startOf(demo, held))
  }, [held, demo])

  const scene = !demo ? null : reduced ? demo.final : held || sceneAt(demo, tick)
  return { hasDemo: !!demo, scene, tick, running, reduced, paused, toggle: () => setPaused((p) => !p) }
}

function PlayIcon({ paused }) {
  return paused ? (
    <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true"><path d="M3 1.8v8.4c0 .5.5.8.9.5l6.3-4.2c.4-.3.4-.8 0-1L3.9 1.3c-.4-.3-.9 0-.9.5Z" fill="currentColor" /></svg>
  ) : (
    <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true"><rect x="2.5" y="1.5" width="2.6" height="9" rx="1" fill="currentColor" /><rect x="6.9" y="1.5" width="2.6" height="9" rx="1" fill="currentColor" /></svg>
  )
}

/**
 * 탭의 사진 상자들. 사진 두 장이면 모바일은 2열 격자, md 이상은 가로로 붙인다(ScreensBody와 같은 배치).
 * mock이 있으면 목업을, src만 있으면 예전처럼 이미지를 그린다.
 */
export function ShotSet({ tab, link, two = false, className = '' }) {
  const ref = useRef(null)
  const demo = useDemo(tab.demo, link.active, ref)
  const numbers = {}
  const labels = {}
  ;(tab.annots || []).forEach(([h, , areaKey], i) => {
    if (areaKey) { numbers[areaKey] = i + 1; labels[areaKey] = h }
  })
  const pick = (k) => {
    link.pick(k)
    document.getElementById(`guide-annot-${k}`)?.scrollIntoView?.({ block: 'nearest', behavior: demo.reduced ? 'auto' : 'smooth' })
  }
  return (
    <div ref={ref} className={`flex flex-col gap-2.5 ${className}`}>
      <div className={two ? 'grid grid-cols-2 gap-[14px] md:flex' : ''}>
        {(tab.shots || []).map((s) => (s.mock ? (
          <GuideMock key={s.mock} name={s.mock} w={s.w} h={s.h}
            scene={demo.scene} tick={demo.tick} running={demo.running} motion={!demo.reduced}
            active={link.active} numbers={numbers} labels={labels} onPick={pick} onHover={link.hover} />
        ) : (
          <img key={s.src} src={s.src} alt="" width={s.w} height={s.h} className="h-auto w-full shrink-0" style={{ maxWidth: s.w }} />
        )))}
      </div>
      {demo.hasDemo && !demo.reduced && (
        <button type="button" onClick={demo.toggle} aria-pressed={demo.paused}
          className="flex items-center gap-1.5 self-start rounded-full border-1.5 border-line bg-white px-2.5 py-1 text-[12px] font-bold leading-figma text-ink-muted transition-colors hover:bg-surface-muted">
          <PlayIcon paused={demo.paused} />
          {demo.paused ? '시연 재생' : '시연 멈춤'}
        </button>
      )}
    </div>
  )
}
