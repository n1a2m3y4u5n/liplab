/**
 * 집중 모드 레슨 헤더의 접근성 설정 진입점(F6). 폰 레슨에서는 떠 있는 Aa 버튼을 하단 바가 가리지 않게 숨기므로
 * (A11ySettings.hideMobile), 글자 크게·고대비를 열 길이 없었다. 헤더에 작은 버튼을 두고 같은 패널을 연다.
 * 데스크톱(lg 이상)은 왼쪽 아래 떠 있는 버튼이 그대로라 여기서는 숨긴다.
 */
export default function LessonA11yButton() {
  return (
    <button type="button" aria-label="접근성 설정" title="접근성 설정"
      onClick={() => window.dispatchEvent(new Event('liplab:a11y-toggle'))}
      className="grid size-8 shrink-0 place-items-center rounded-full text-[14px] font-semibold tracking-tight text-ink-muted hover:bg-surface-sunken lg:hidden">
      Aa
    </button>
  )
}
