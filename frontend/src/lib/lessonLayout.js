// 독화 레슨 템플릿(91:12 · 385:83 / 모바일 235:34) 공통 배치값.
// 1366×768 같은 낮은 데스크톱에서도 질문·입모양·보기가 스크롤 없이 한 화면에 들어오게 한다.
// - 입모양 카드 높이 = 화면 높이 - 나머지 요소(clamp로 상한은 Figma 값 370 / 모바일 214)
// - 데스크톱 보기는 2×2 격자(문맥 추론은 3칸 한 줄)
// - 세로 860px 이하 데스크톱은 위 여백·간격을 줄인다
// Tailwind가 클래스 이름을 읽어야 하므로 문자열을 조합하지 않고 통째로 적는다.

// 본문 열. 모바일 아래 여백은 하단 바 높이(문제 98 / 결과 ~160)에 맞춰 lessonPad로 붙인다.
export const LESSON_COL = 'mx-auto flex w-full max-w-[676px] flex-col px-[18px] pt-[18px] lg:pb-[130px] lg:pt-7 lg:[@media(max-height:860px)]:pt-5'

// 결과 메시지가 뜨면 모바일 하단 바가 높아지므로 그때만 여백을 늘린다.
export const lessonPad = (tall) => (tall ? 'pb-[200px]' : 'pb-[120px]')

// 진행 헤더 아래 질문·카드·보기 묶음
export const LESSON_STACK = 'mt-6 flex flex-col gap-4 lg:mt-5 lg:gap-5 lg:[@media(max-height:860px)]:mt-3.5 lg:[@media(max-height:860px)]:gap-3.5'

// 입모양 카드(560×370 / 모바일 전체 폭×214). 아바타는 부모 높이를 따른다.
export const LESSON_AVATAR = 'mx-auto h-[clamp(150px,calc(100dvh_-_548px),214px)] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[clamp(200px,calc(100dvh_-_464px),370px)] lg:rounded-22'
// 입모양 인지는 보기 이름(이중모음(ㅘ, ㅙ, …))이 격자 한 칸에서 두 줄이 되기도 해 그 두 줄 몫을 남긴다.
export const LESSON_AVATAR_VISEME = 'mx-auto h-[clamp(150px,calc(100dvh_-_596px),214px)] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[clamp(200px,calc(100dvh_-_500px),370px)] lg:rounded-22'
// 문맥 추론은 빈칸 문장 카드가 더 있어 그만큼 낮춘다(보기는 한 줄이라 일부 상쇄).
export const LESSON_AVATAR_CLOSURE = 'mx-auto h-[clamp(150px,calc(100dvh_-_590px),214px)] w-full max-w-[560px] rounded-18 border-2 border-line bg-white p-4 lg:h-[clamp(180px,calc(100dvh_-_476px),370px)] lg:rounded-22'

// 보기 목록. 모바일은 한 줄씩, 데스크톱은 격자(키보드 1~4 순서 = 왼→오, 위→아래).
export const LESSON_OPTIONS = 'flex flex-col gap-2.5 lg:grid lg:grid-cols-2 lg:gap-3'
export const LESSON_OPTIONS_3 = 'flex flex-col gap-2.5 lg:grid lg:grid-cols-3 lg:gap-3'
