import { useEffect, useRef } from 'react'

/**
 * 하단 고정 바(독화 레슨 130:17 · 94:133 · 94:175와 같은 틀). tone: null(문제) | 'good' | 'bad'.
 * 바 높이를 --listen-bar-h로 알려 페이지가 그만큼 아래 여백을 둔다(글자 크게 설정으로 바가 높아져도 내용·안내문이 바 뒤로 숨지 않는다).
 */
const BAR_TONE = { good: 'border-good bg-good-tint lg:border-good/35', bad: 'border-bad bg-bad-tint lg:border-bad/35' }
const BAR_BTN = 'btn-bar w-full shrink-0 max-lg:py-4 max-lg:text-[16px] lg:w-auto'

export default function BottomBar({ active = true, tone = null, title, sub, hint, alert, primary, secondary }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    const root = document.documentElement
    if (!el) return undefined
    const set = () => root.style.setProperty('--listen-bar-h', `${el.offsetHeight + 12}px`)
    set()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(set) : null
    ro?.observe(el)
    return () => { ro?.disconnect(); root.style.setProperty('--listen-bar-h', '0px') }
  }, [active])
  if (!active) return null
  const textTone = tone === 'good' ? 'text-good-text' : tone === 'bad' ? 'text-bad-text' : 'text-ink'
  const btnTone = tone === 'good' ? 'btn-good' : tone === 'bad' ? 'btn-bad' : 'btn-primary'
  return (
    <div ref={ref} className={`fixed inset-x-0 bottom-0 z-40 border-t-2 ${BAR_TONE[tone] || 'border-line bg-white'}`}>
      <div className="mx-auto flex max-w-[676px] flex-col items-stretch gap-3 px-[18px] pb-[calc(18px+env(safe-area-inset-bottom))] pt-4 lg:min-h-[110px] lg:flex-row lg:items-center lg:justify-between lg:gap-4 lg:py-4">
        <div role="status" aria-live="polite" className={`flex min-w-0 flex-col gap-[3px] leading-figma lg:gap-1 ${textTone} ${title || alert ? '' : 'max-lg:hidden'}`}>
          {alert ? (
            <p role="alert" className="text-[15px] font-bold leading-snug text-bad-text">{alert}</p>
          ) : title ? (
            <>
              <p className="text-[19px] font-bold tracking-[-0.38px] lg:text-[22px] lg:tracking-[-0.44px]">{title}</p>
              {sub && <p className="break-keep text-[13px] font-bold leading-snug opacity-80 lg:text-[14px]">{sub}</p>}
            </>
          ) : hint ? <span className="text-[15px] text-ink-faint">{hint}</span> : null}
        </div>
        {(primary || secondary) && (
          <div className="flex gap-2 max-lg:flex-col-reverse lg:shrink-0">
            {secondary && (
              <button type="button" onClick={secondary.onClick} disabled={secondary.disabled} className={`btn-secondary ${BAR_BTN} max-lg:py-3`}>{secondary.label}</button>
            )}
            {primary && (
              <button type="button" onClick={primary.onClick} disabled={primary.disabled} className={`${btnTone} ${BAR_BTN} disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text`}>{primary.label}</button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
