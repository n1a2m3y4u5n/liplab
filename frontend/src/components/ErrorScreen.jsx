/**
 * 에러 화면 (Figma "10. 로딩 · 에러", 404 438:83 / 모바일 438:123, 문제 발생 438:103 / 모바일 438:143, 변경 내역 §1).
 * 셸 없이 흰 화면 가운데에 눈이 X자인 DOKA(6° 기울임) + 제목 + 설명 (+ 404 코드) + 버튼.
 *  - 모바일: 가운데 칸 322(좌우 34) · 간격 18 · DOKA 118 · 제목 24 · 설명 14 · 버튼은 전체 폭으로 세로로 쌓는다.
 *  - lg 이상: 가운데 칸 440 · 간격 22 · DOKA 160 · 제목 30 · 설명 15.5 · 버튼은 가로 가운데.
 *  - 문제 발생의 설명 둘째 줄('계속 안 되면 새로고침을 해보세요.')은 데스크톱 프레임에만 있다.
 * 버튼 동작은 부르는 쪽이 준다(App의 ErrorBoundary는 라우터 밖이라 주소를 직접 바꾼다).
 */
const MASCOT_INSET = { top: '-7%', left: '-12%', right: '-12%', bottom: '-17%' }   // DOKA 그림자 여백(Figma inset)

function Mascot() {
  return (
    <div aria-hidden className="grid size-[130px] shrink-0 place-items-center lg:size-[176px]">
      <div className="relative size-[118px] rotate-6 lg:size-40">
        <img src="/ui/lp-438-125-error-doka-m.svg" alt="" className="absolute max-w-none lg:hidden"
          style={{ ...MASCOT_INSET, width: '124%', height: '124%' }} />
        <img src="/ui/lp-438-85-error-doka.svg" alt="" className="absolute hidden max-w-none lg:block"
          style={{ ...MASCOT_INSET, width: '124%', height: '124%' }} />
      </div>
    </div>
  )
}

export default function ErrorScreen({ kind = 'error', onRetry, onHome, children }) {
  const notFound = kind === 'notfound'
  return (
    <div className="flex min-h-[100dvh] w-full items-center justify-center bg-white px-[34px] py-10">
      <div className="flex w-full max-w-[322px] flex-col items-center gap-[18px] text-center lg:max-w-[440px] lg:gap-[22px]">
        <Mascot />
        <h1 className="text-[24px] font-bold leading-[1.65] tracking-[-0.6px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
          {notFound ? '페이지를 찾을 수 없어요' : '문제가 생겼어요'}
        </h1>
        <p className="text-[14px] leading-[1.65] text-ink-muted lg:text-[15.5px]">
          {notFound ? '주소가 바뀌었거나 없는 페이지예요.' : (
            <>
              <span className="block">잠시 후 다시 시도해 주세요.</span>
              <span className="hidden lg:block">계속 안 되면 새로고침을 해보세요.</span>
            </>
          )}
        </p>
        {notFound && <p className="text-[12.5px] font-bold leading-figma text-ink-faint">404</p>}
        <div className="flex w-full flex-col gap-2.5 pt-1.5 lg:flex-row lg:justify-center">
          {!notFound && (
            <button type="button" onClick={onRetry} className="btn-primary px-7 py-[15px] text-[16px]">다시 시도</button>
          )}
          <button type="button" onClick={onHome}
            className={notFound ? 'btn-primary px-7 py-[15px] text-[16px]' : 'btn-secondary px-7 py-[15px] text-[16px] text-primary-500'}>
            학습으로 돌아가기
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
