import { useEffect, useRef, useState } from 'react'
import { ModalClose } from './Modal'
import useFocusTrap from '../hooks/useFocusTrap'
import TeamAvatar from './TeamAvatar'
import { TEAM, REPO_URL } from '../config/team'
import { TeamMemberDetail, ContactLine } from './TeamMemberDetail'
import { ShotSet, useAnnotLink } from './guide/GuideDemo'

/**
 * 사용법 가이드 모달 (Figma "09. 사용법 가이드" 338:57 ~ 342:348).
 * 딤 오버레이 + 중앙 큰 흰 카드(rounded-24, 큰 그림자). 좌측 그룹형 세로 탭 + 우측 컨텐츠.
 * 배경 클릭·ESC로 닫힌다. 모바일에서는 좌측 탭이 상단 가로 스크롤 탭으로 폴백한다(Figma에 모바일 가이드 없음).
 *
 * Figma 스펙:
 *  - 카드 w-[1080px] h-[680px] rounded-24 shadow-modal · 오버레이 overlay 50%
 *  - Guide nav w-[248px] bg-surface-nav border-r-1.5 pt-28 pb-24 px-16 gap-2
 *    · 제목 20px bold tracking-[-.4px] / 그룹 라벨 11.5px bold ink-hint tracking-[.345px]
 *    · 탭 14.5px bold, 활성 = primary-tint 배경 + primary 텍스트, 비활성 = ink-muted
 *  - Guide content pl-36 pr-30 py-30 gap-22 / 제목 26px bold tracking-[-.65px] / 닫기 36px(338:237)
 *  - 내용(Body 766px)은 탭마다 다섯 가지 꼴이다.
 *    · overview(01): 화면 축소본 766×404 + 아래 주석 2열(338:273)
 *    · screens(02·03·04·06~10): 화면 축소본 + 오른쪽 주석(Screen guide). 03·04는 축소본 2장에 작은 주석.
 *      축소본은 9/28부터 PNG 대신 코드로 그린 목업이다(guide/GuideMockups, shots의 mock 키). src를 주면 예전처럼 이미지를 그린다.
 *  - 주석 셋째 값은 목업 안 영역 키다. 주석을 가리키거나 누르면 그 영역이 강조되고, 목업의 번호 배지를 눌러도 주석이 강조된다.
 *    demo가 있는 탭(03·04)은 목업이 짧은 시연을 반복한다(guide/GuideDemo, 동작 최소화면 멈춘 마지막 장면).
 *    · tips(05): 번호 + 요령 + 작은 예시, 2열 3행(340:249)
 *    · notes: 사진 없이 주석 2열 + 단계 목록(처음 시작하기·말하기 6단계, 9/28 추가, Figma 프레임 없음)
 *    · team(11): 팀원 5명 + 소스 코드(342:530). 역할 '개1발'(372:121)은 Figma 오타로 보고 '개발'로 쓴다.
 *  - more는 사진에 없는 기능을 본문 아래 구분선 뒤 주석 2열로 덧붙인다(9/28 가이드 점검에서 빠진 내용).
 *  - initialKey로 처음 열 탭을, context로 '지금 내 상태' 카드(학습 경로에서 연 경우)를 받는다. 카드는 context.tab 탭 맨 위에 뜬다.
 */

// 주석(Annot, 345:295) — 점(10×20 에셋) + 소제목 + 설명. small = 03·04 레슨 탭(14px·12px, 간격 9).
// 목업 영역(areaKey)과 이어진 주석은 점 대신 번호를 달고 버튼이 된다. 가리키거나(마우스·키보드 포커스) 누르면 목업의 그 영역이
// 강조된다. 여백은 음수 마진으로 상쇄해 점 주석과 같은 자리에 놓인다.
function Annotation({ h, d, small = false, n, areaKey, link }) {
  const text = (
    <div className="flex min-w-0 flex-1 flex-col gap-px">
      <p className={`font-bold leading-figma text-ink ${small ? 'text-[14px]' : 'text-[14.5px]'}`}>{h}</p>
      <p className={`break-keep leading-[1.58] text-ink-muted ${small ? 'text-[12px]' : 'text-[12.5px]'}`}>{d}</p>
    </div>
  )
  const gap = small ? 'gap-[9px]' : 'gap-[10px]'
  if (!areaKey || !link) {
    return (
      <div className={`flex items-start ${gap}`}>
        <img src="/ui/lp-366-91-guide-dot.svg" alt="" aria-hidden className="h-5 w-[10px] shrink-0" />
        {text}
      </div>
    )
  }
  const on = link.active === areaKey
  return (
    <button type="button" id={`guide-annot-${areaKey}`} aria-pressed={link.pinned === areaKey}
      onMouseEnter={() => link.hover(areaKey)} onMouseLeave={() => link.hover(null)}
      onFocus={() => link.hover(areaKey)} onBlur={() => link.hover(null)} onClick={() => link.pick(areaKey)}
      className={`-mx-2 -my-1.5 flex items-start rounded-10 px-2 py-1.5 text-left transition-colors duration-200 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 ${gap} ${on ? 'bg-primary-50' : ''}`}>
      <span aria-hidden className={`mt-px flex size-[18px] shrink-0 items-center justify-center rounded-full text-[10.5px] font-bold leading-none transition-colors duration-200 ${
        on ? 'bg-primary-500 text-white' : 'bg-primary-100 text-primary-600'}`}>{n}</span>
      {text}
    </button>
  )
}

// 그룹 → 탭. kind: overview | screens | tips | notes | team. annots = [소제목, 설명, 목업 영역 키] (Figma 원문을 9/28 실제 동작에 맞춰 고침).
// shots = [{ mock: 목업 키(guide/GuideMockups MOCKS), w, h }], demo = 시연 키(DEMOS).
// steps = { label, items: [[제목, 설명, 숙달 기준]] }. 숙달 기준 숫자는 backend main.py _STAGE_RULES·speak_curriculum.py SPEAK_STAGES와 같게.
const GROUPS = [
  {
    label: '시작',
    tabs: [
      {
        key: 'start', title: '처음 시작하기', kind: 'notes',
        annots: [
          ['자가진단', '입모양만 보고 어떤 단어인지 고르는 문제를 풀어요. 수준이 분명해지면 5문항 만에도 끝나고, 길어도 12문항이에요. 문항마다 정답은 알려 주지 않아요.'],
          ['나중에 할게요', '자가진단을 건너뛰면 1단계부터 시작해요. 프로필의 자가진단 다시 하기로 언제든 받을 수 있어요.'],
        ],
        steps: {
          label: '독화 4단계',
          items: [
            ['입모양 인지', '10개 입모양 그룹을 구별해요.', '8번 · 85%'],
            ['음절·단어', '입모양이 비슷한 단어 가운데 맞는 것을 골라요.', '6번 · 85%'],
            ['문장 (상황별)', '상황별 문장을 입모양으로 읽고 답해요.', '5번 · 80%'],
            ['대화 실전', 'AI가 하는 말을 입모양으로 읽고 답해요.', '4번 · 75%'],
          ],
        },
        more: [
          ['단계가 열리는 기준', '단계마다 정한 횟수 이상 풀고 최근 정답률이 기준을 넘으면 숙달이에요. 문장은 60점, 대화는 55점 이상을 맞힌 것으로 세요. 숙달하면 다음 단계가 열리고, 한 번 숙달한 단계는 다시 잠기지 않아요.'],
          ['발화 트랙', '말하기 연습은 따로 6단계예요. 학습 탭 위에서 발화를 고르면 돼요. 체험용 앱에서는 모든 단계가 처음부터 열려 있을 수 있어요.'],
        ],
      },
      {
        key: 'tour', title: '화면 둘러보기', kind: 'overview',
        shots: [{ mock: 'overview', w: 766, h: 404 }],
        annots: [
          ['내 기록', '불꽃은 연속 학습 일수, 별은 누적 XP, 육각형은 레벨이에요. 연속으로 공부할수록 같은 문제에서 받는 XP가 늘어요(최대 3배). 휴대폰에서는 오른쪽 위 이름 첫 글자를 누르면 프로필로 가요.', 'stats'],
          ['오른쪽 패널', '넓은 화면(가로 1280px 이상)에서 오른쪽에 보여요. 오늘의 과제, 오늘 다시 풀 입모양·단어 수, 북마크 수를 보여줘요. 과제 탭에서는 레벨 진행, 복습 탭에서는 이번 주에 학습한 날로 바뀌어요.', 'rail'],
          ['로고', '왼쪽 위 LIPLAB 로고를 누르면 서비스 소개 페이지로 가요.', 'logo'],
        ],
      },
    ],
  },
  {
    label: '학습',
    tabs: [
      {
        key: 'learn', title: '학습 탭', kind: 'screens',
        shots: [{ mock: 'learn', w: 446, h: 560 }],
        annots: [
          ['트랙 전환', '독화 · 발화를 골라요. 트랙마다 경로와 진도가 따로 저장돼요.', 'switch'],
          ['가이드', '보고 있는 단계의 설명, 진행률, 숙달 기준과 사용법을 바로 봐요.', 'guideBtn'],
          ['단계 노드', 'DOKA 하나가 한 단계예요. 체크가 붙은 DOKA는 숙달한 단계, 링을 두른 큰 DOKA는 지금 단계, 눈을 뜬 연한 DOKA는 건너뛸 수 있는 다음 단계, 잠든 DOKA는 잠긴 단계예요. 열린 DOKA를 누르면 바로 그 단계를 시작해요.', 'nodes'],
          ['단계 이동', "좌우 화살표로 이전 · 다음 단계를 둘러봐요. 바로 다음 잠긴 단계는 '여기로 건너뛸까요?'를 누르고 한 번 더 확인하면 열려요.", 'arrows'],
          ['레슨 카드', "보고 있는 단계의 진행률이 떠요. 숫자는 숙달 판정에 필요한 최소 시도 수 대비 푼 수예요. 다 채웠는데 정답률이 모자라면 '숙달 중'으로 보여요. 처음이면 학습 시작하기, 이어서라면 이어서 학습하기를 눌러요.", 'sheet'],
        ],
      },
      {
        key: 'reading', title: '독화 레슨', kind: 'screens', small: true,
        shots: [{ mock: 'readQuestion', w: 238, h: 358 }, { mock: 'readWrong', w: 238, h: 358 }], demo: 'reading',
        annots: [
          ['북마크', '다시 보고 싶은 문제를 저장해요.', 'bookmark'],
          ['입모양 영상', '3D 아바타의 입모양이 계속 반복돼요. 알아볼 때까지 보면 돼요.', 'stage'],
          ['보기 고르기', '보기를 누르거나 숫자 키 1~4로 고른 뒤 확인을 눌러요. 1단계는 입모양 그룹을, 2단계는 단어를 골라요. 오답 보기는 화면에서 구별되는 것만 나와요. 문맥 추론은 보기가 3개예요.', 'options'],
          ['결과 바', '맞히면 초록, 틀리면 빨강이에요. 틀리면 정답을 알려 주고, 그 입모양·단어는 다음 날 복습에 다시 나와요. 12문항을 마치면 정답률·XP·걸린 시간이 나와요.', 'resultBar'],
        ],
        more: [
          ['결과 아래 설명', '2단계에서 틀리면 어느 소리를 무엇으로 읽었는지, 입모양이 원래 같은 짝인지 알려 줘요. 단어 뜻은 수어 영상으로도 봐요.'],
          ['안 보이는 소리 기호', '2단계에서 답을 확인하면 입 옆에 작은 기호가 떠요. 바람은 거센소리, 채운 마름모는 된소리, 물결은 코로 울리는 소리예요. 숙달할수록 흐려져요.'],
          ['약한 입모양은 천천히', '자주 틀리는 입모양은 연습할 때 조금 더 천천히(약 1.35배) 보여줘요. 자가진단과 사전·사후 검사는 모두 같은 속도예요.'],
          ['3단계 문장', '힌트는 글자 수, 첫 글자, 발음 자막 순서로 열려요. 발음 자막까지 보고 낸 답은 숙달에 들어가지 않아요.'],
          ['4단계 대화', 'AI가 하는 말을 입모양으로 읽고 답하며 6턴을 이어가요.'],
          ['문장 플레이어', '3·4단계 아바타 아래에서 재생 속도를 바꾸고 투명 두상, 측면 보기, 성도 단면을 켜요. 측면 보기에서는 입술을 내밀거나 둥글게 모으는 움직임이 잘 보여요.'],
        ],
      },
      {
        key: 'speaking', title: '발화 레슨', kind: 'screens', small: true,
        shots: [{ mock: 'speakBefore', w: 238, h: 358 }, { mock: 'speakResult', w: 238, h: 358 }], demo: 'speaking',
        annots: [
          ['입모양 따라 하기', '아바타의 입모양을 보고 따라 해요. 발성·운율 단계는 목소리 크기·높낮이 그래프를 보며 연습해요.', 'stage'],
          ['마이크', '누르고 말한 뒤 다시 누르면 끝나요.', 'mic'],
          ['발음 정확도', '목표 발음에 얼마나 가까웠는지 %로 보여줘요. 발성·운율 단계는 길이·크기나 억양 점수가 나와요.', 'score'],
          ['소리별 결과', '70점 이상은 초록, 45~69점은 주황, 45점 미만은 빨강이에요.', 'chips'],
          ['자세히 보기', '이렇게 들렸어요, 음소별 정확도, DOKA의 한마디를 봐요. 웹캠 미러를 켰다면 입모양 점수가 따로 나오고, 모음 단계는 내 혀 위치를 목표와 겹쳐 보여줘요.', 'detail'],
        ],
      },
      {
        key: 'speak-stages', title: '말하기 6단계', kind: 'notes',
        intro: '앞 단계를 숙달하면 다음 단계가 열려요. 오른쪽 숫자는 숙달에 필요한 최소 횟수와 최근 통과율이에요.',
        steps: {
          label: '발화 6단계',
          items: [
            ['발성', "원할 때 목소리를 내고 길게 유지해요. 배에 숨을 담고 '아' 소리를 2초 이상 곧게 내 보세요.", '5번 · 85%'],
            ['운율 조절', '목소리의 크기·길이·높낮이를 지시대로 바꿔요. 아래 곡선으로 바로 확인해요.', '10번 · 90%'],
            ['모음', '기본 모음 8개예요. 아는 크게, 이·우·으는 작게 벌리고, 오·우는 동그랗게, 이·으는 옆으로 당겨요. 오/우, 어/으는 턱을 벌리는 정도로 구별해요.', '8번 · 85%'],
            ['자음', '입술소리부터 최소대립쌍으로 연습해요. 불/풀, 달/탈처럼 입모양이 같은 짝은 숨의 세기가 달라요. 거센소리는 손바닥을 입 앞에 대고 바람이 세게 닿게 내 보세요.', '8번 · 85%'],
            ['음절·단어', '짧은 단어부터 여러 음절까지 또박또박 말하고, 받침까지 살려요.', '8번 · 90%'],
            ['문장·억양', '평서문은 끝을 내리고, 예/아니오로 답하는 의문문은 마지막 음절을 올려요.', '6번 · 85%'],
          ],
        },
        more: [
          ['실시간 그래프', '말하는 동안 파형, 목소리 크기, 높낮이가 바로 보여요.'],
          ['웹캠 미러', '켜면 내 얼굴이 거울처럼 나와 아바타 입모양과 나란히 비교해요.'],
          ['이 단계 숙달', '문항 아래에 최근 통과율과 시도 수가 보여요. 기준을 넘으면 다음 단계가 열려요.'],
          ['아쉬울 때', '통과하지 못하면 넘어가기와 다시 말하기 중에서 골라요.'],
          ['약한 소리 먼저', '모음·자음·음절·단어 단계는 최근 녹음에서 약하게 나온 소리가 든 문항을 앞쪽에 섞어 내요.'],
        ],
      },
      { key: 'strategy', title: '독화 요령', kind: 'tips' },
    ],
  },
  {
    label: '탭 안내',
    tabs: [
      {
        key: 'practice', title: '연습', kind: 'screens',
        shots: [{ mock: 'practice', w: 446, h: 560 }],
        annots: [
          ['자유 발화', '내가 쓴 문장을 입력하면 3D 입모양과 혀 위치 같은 소리 내는 법을 보여줘요.', 'free'],
          ['상황별 시나리오', "'카페에서 음료 주문하기'처럼 상황을 직접 적고 난이도(1~5)를 정해요. 문장 테스트나 AI 대화(1:1 또는 여러 명)로 연습해요. 문장 테스트는 3단계, 1:1 대화는 4단계가 열려야 할 수 있어요.", 'scenario'],
          ['수어 보기', '문장을 입력하면 한국수어 어순으로 옮기고 단어마다 국립국어원 수어 영상을 보여줘요. 사전에 없는 말은 지문자로 보여요. 공식 통역은 아니에요.', 'sign'],
          ['엔드리스 학습', '약한 입모양이 든 문제가 더 자주 나오는 단어 레슨과 문맥 추론 레슨이 12문항씩 번갈아 이어져요. 지금 나오는 유형을 숙달도 낮은 순으로 보여 주고, 원할 때 멈추면 돼요.', 'endless'],
          ['입모양 교실', '입모양 그룹 10개마다 잘 보이는 정도, 소리 내는 법, 예시 단어를 봐요. 투명 두상을 켜면 혀와 치아가 비쳐 보이고, 성도 단면으로 옆에서 본 혀 위치도 봐요.', 'mouth'],
        ],
        more: [
          ['웹캠으로 내 입모양 확인', '입모양 교실에서 내 입모양을 목표와 비교해 점수와 교정 문구를 바로 보여 주고, 아바타가 내 입을 따라 해요. 영상은 기기 밖으로 나가지 않아요.'],
          ['여러 명 대화', 'AI 대화에서 여러 명을 고르면 2~4명이 번갈아 말해요. 누가 말하는지 먼저 찾고, 입모양이 같은 문장 중 흐름에 맞는 것을 골라요.'],
          ['문맥 추론', '엔드리스 학습의 문맥으로 풀기에서 입모양이 같은 단어 중 문장에 맞는 것을 골라요.'],
          ['음성으로 움직이는 아바타', '자유 발화 아래에서 녹음한 목소리로 아바타 입을 움직여 봐요. 서버에 모델이 없으면 이 칸은 보이지 않아요.'],
        ],
      },
      {
        key: 'task', title: '과제', kind: 'screens',
        shots: [{ mock: 'task', w: 470, h: 407 }],
        annots: [
          ['오늘의 과제', '오늘의 복습 정리, 독화 학습 1회, 학습 2회 채우기를 매일 새로 세요. 1 / 2처럼 채운 만큼 보여주고, 오늘 남은 시간도 함께 보여요. 복습할 항목이 남아 있으면 첫 줄을 눌러 바로 복습해요.', 'today'],
          ['특별 과제', '이번 주에 학습한 날이 5일이 되면 채워져요.', 'special'],
          ['배지', '조건을 채우면 모여요. 누르면 크게 보고, 전체 학습자 중 몇 %가 가졌는지 알 수 있어요. 회색은 아직 받지 못한 배지예요. 휴대폰에서는 분석 › 전체 통계에서 개수를 봐요.', 'badges'],
        ],
      },
      {
        key: 'review', title: '복습', kind: 'screens',
        shots: [{ mock: 'review', w: 446, h: 560 }],
        annots: [
          ['오답 복습', '입모양·단어 레슨에서 틀린 문제는 다음 날 다시 나와요. 맞힐수록 간격이 1일, 6일처럼 벌어지다 목록에서 빠져요. 문장 연습에서 60점 아래로 끝난 문장도 최근 10개까지 모여요.', 'ctaWrong'],
          ['북마크 복습', '레슨 중 북마크 버튼으로 저장한 문제예요.', 'ctaMark'],
          ['항목', '언제 몇 번 틀렸는지 보여 주고, 누르면 그 종류의 복습을 시작해요.', 'items'],
          ['지우기', '누르면 항목마다 체크박스가 생겨요. 골라서 한 번에 지워요. 전체 선택도 돼요. 틀린 문장은 이 화면에서만 숨겨져요.', 'erase'],
        ],
      },
      {
        key: 'analysis', title: '분석', kind: 'screens',
        shots: [{ mock: 'analysis', w: 446, h: 560 }],
        annots: [
          ['맨 위 세 칸', '총 학습 시간 · 평균 정확도 · 연속 학습 일수예요.', 'stats'],
          ['학습시간 추이', '최근 7주 동안 주마다 얼마나 공부했는지 막대로 보여줘요.', 'bars'],
          ['정확도 추이', '주별 정답률이 어떻게 변했는지 선으로 보여줘요.', 'line'],
          ['활동 캘린더', '공부한 날이 잔디처럼 칠해져요. 진할수록 많이 한 날이에요.', 'calendar'],
          ['회차 히스토리', '레슨마다 정답률을 보고, 누르면 문제별로 어떻게 들렸는지까지 봐요.', 'history'],
          ['전체 통계', '가입 후 총 학습 회차, 푼 문제, 배지, 트랙별 진도를 모아 봐요.', 'fullStats'],
        ],
        more: [
          ['약점 입모양·혼동 지도', '전체 통계 아래 링크로 들어가요. 입모양 유형별 점수와 자주 헷갈린 짝을 보여 주고, 원래 같은 입모양인 짝은 따로 표시해요.'],
          ['학습 효과 리포트', '학습곡선, 숙달까지 걸린 시도 수, 처음 대비 향상도를 봐요. 사전·사후 검사(각 24문항)를 모두 하면 같은 난이도로 전후를 비교해요.'],
          ['결과지 인쇄', '학습 효과 리포트에서 검사 이력, 오류 프로파일, 학습량을 흑백 한 장으로 인쇄해 교사나 언어재활사와 나눠요.'],
        ],
      },
      {
        key: 'profile', title: '프로필', kind: 'screens',
        shots: [{ mock: 'profile', w: 446, h: 560 }],
        annots: [
          ['자가진단 다시 하기', '시작 단계를 새로 추천받아요. 지금까지의 기록은 그대로 남아요.', 'placement'],
          ['계정 설정', '이름 · 이메일 · 비밀번호를 바꾸고, 로그아웃과 계정 삭제도 여기서 해요.', 'account'],
          ['학습 초기화', '기록을 모두 지워요. 되돌릴 수 없어서 "초기화"를 직접 입력해야 진행돼요.', 'reset'],
          ['접근성 설정', '왼쪽 아래 Aa 버튼에서 글자 크게, 고대비, 모션 줄이기를 켜요. 내 학습 데이터 내려받기도 여기 있어요.', 'a11y'],
        ],
      },
    ],
  },
  {
    label: '더 알아보기',
    tabs: [{ key: 'about', title: '개발자 소개', kind: 'team' }],
  },
]

const TABS = GROUPS.flatMap((g) => g.tabs)

function CloseButton({ onClose }) {
  return <ModalClose onClose={onClose} />
}

// 주석 2열(overview 아래 주석과 같은 간격 28). 사진 없는 탭과 more가 같이 쓴다. link가 있으면 목업 영역과 잇는다.
function AnnotGrid({ items, link }) {
  if (!items?.length) return null
  return (
    <div className="grid gap-x-7 gap-y-[13px] sm:grid-cols-2">
      {items.map(([h, d, areaKey], i) => <Annotation key={h} h={h} d={d} n={i + 1} areaKey={areaKey} link={link} />)}
    </div>
  )
}

// 사진에 없는 기능(more). 본문 아래 구분선 뒤에 주석 2열로 붙인다(독화 요령의 행 구분선과 같은 fill 선).
function MoreNotes({ items }) {
  if (!items?.length) return null
  return (
    <div className="mt-[22px] flex flex-col gap-[13px] border-t border-fill pt-[22px]">
      <p className="text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">더 알아두기</p>
      <AnnotGrid items={items} />
    </div>
  )
}

// 01 화면 둘러보기(338:273) — 축소본 아래 주석 2열(간격 28)
function OverviewBody({ tab }) {
  const link = useAnnotLink()
  return (
    <div className="flex flex-col gap-5">
      {tab.shots?.length > 0 && <ShotSet tab={tab} link={link} />}
      <AnnotGrid items={tab.annots} link={link} />
      <MoreNotes items={tab.more} />
    </div>
  )
}

// 02·03·04·06~10(Screen guide) — 축소본(1~2장) + 오른쪽 주석. 축소본 사이 14, 주석까지 24(2장이면 14, 주석 안쪽 8)
// 사진이 없으면 주석만 한 열로 그린다(사진을 다시 찍는 동안 칸이 비어도 깨지지 않게).
function ScreensBody({ tab }) {
  const link = useAnnotLink()
  const shots = tab.shots || []
  const two = shots.length > 1
  return (
    <div className="flex flex-col">
      <div className={`flex flex-col md:flex-row md:items-start ${two ? 'gap-[14px]' : 'gap-6'}`}>
        {shots.length > 0 && <ShotSet tab={tab} link={link} two={two} className="md:shrink-0" />}
        <div className={`flex min-w-0 flex-1 flex-col ${tab.small ? 'gap-[11px] md:pl-2' : 'gap-[13px]'}`}>
          {(tab.annots || []).map(([h, d, areaKey], i) => (
            <Annotation key={h} h={h} d={d} small={tab.small} n={i + 1} areaKey={areaKey} link={link} />
          ))}
        </div>
      </div>
      <MoreNotes items={tab.more} />
    </div>
  )
}

// 단계 목록(처음 시작하기·말하기 6단계). 번호는 독화 요령의 번호색(primary-faint)을 작게, 오른쪽 칩은 숙달 기준.
function StepList({ steps }) {
  return (
    <div className="flex flex-col">
      <p className="pb-2 text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">{steps.label}</p>
      {steps.items.map(([h, d, rule], i) => (
        <div key={h} className={`flex items-start gap-4 py-[14px] ${i > 0 ? 'border-t border-fill' : ''}`}>
          <p className="w-7 shrink-0 text-[22px] font-bold leading-figma tracking-[-0.66px] text-primary-faint">{String(i + 1).padStart(2, '0')}</p>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[15px] font-bold leading-figma text-ink">{h}</p>
              {rule && <span className={`${CHIP} shrink-0 whitespace-nowrap bg-primary-100 text-primary-700`}>{rule}</span>}
            </div>
            <p className="break-keep text-[12.5px] leading-[1.58] text-ink-muted">{d}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// 사진 없는 탭(notes): 안내 한 줄 + 주석 2열 + 단계 목록 + 더 알아두기
function NotesBody({ tab }) {
  return (
    <div className="flex flex-col gap-5">
      {tab.intro && <p className="break-keep text-[14px] leading-[1.6] text-ink-muted">{tab.intro}</p>}
      <AnnotGrid items={tab.annots} />
      {tab.steps && <StepList steps={tab.steps} />}
      <MoreNotes items={tab.more} />
    </div>
  )
}

// '지금 내 상태' 숙달 기준 문장. 숫자는 학습 경로가 받은 단계 목록(서버 _STAGE_RULES·SPEAK_STAGES)에서 온다.
function ruleText(c) {
  if (!c.minAttempts || c.mastery == null) return null
  const verb = c.track === 'speak' ? '말하고' : c.pass != null ? '답하고' : '풀고'
  const rate = c.pass != null ? `${c.pass}점 이상을 통과로 세어 최근 통과율이` : c.track === 'speak' ? '최근 통과율이' : '최근 정답률이'
  return `${c.minAttempts}번 이상 ${verb} ${rate} ${c.mastery}% 이상이면 숙달이에요.`
}

function nextText(n) {
  if (!n) return '마지막 단계예요.'
  const note = n.open ? '열려 있어요.' : n.skip ? '이 단계를 숙달하면 열려요. 경로에서 건너뛸 수도 있어요.' : '앞 단계를 숙달하면 열려요.'
  return `${n.no}단계 ${n.title}. ${note}`
}

// '지금 내 상태' 카드(9/28, Figma 프레임 없음). 학습 경로의 가이드 버튼으로 열면 보고 있는 단계를 레슨 탭 맨 위에 보여 준다.
// 색은 트랙 토큰이라 발화 트랙에서는 분홍이 된다(AppShell data-track 안에서 열린다).
function StatusCard({ c }) {
  const rule = ruleText(c)
  const line = 'break-keep text-[12.5px] leading-[1.58] text-ink-muted'
  return (
    <section aria-label="지금 내 상태" className="mb-[22px] flex flex-col gap-3 rounded-18 border-2 border-line bg-surface-muted p-5">
      <div className="flex items-center justify-between gap-3 font-bold leading-figma">
        <span className="text-[11.5px] tracking-[0.345px] text-ink-hint">지금 내 상태</span>
        <span className="shrink-0 rounded-full bg-track-tint px-2.5 py-1 text-[12px] text-track">{c.statusLabel}</span>
      </div>
      <div className="flex flex-col gap-1 leading-figma">
        <p className="text-[12.5px] font-bold text-track">{c.trackLabel} · {c.no}단계</p>
        <p className="text-[19px] font-bold tracking-[-0.38px] text-ink">{c.title}</p>
        {c.desc && <p className={line}>{c.desc}</p>}
      </div>
      {c.open && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-[13px] font-bold leading-figma">
            <span className="text-ink-muted">진행률</span>
            <span className="text-track">{c.progLabel}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-fill">
            <div className="h-full rounded-full bg-track" style={{ width: `${c.progPct}%` }} />
          </div>
        </div>
      )}
      {rule && <p className={line}><b className="text-ink">숙달 기준</b> {rule}</p>}
      {c.guide && <p className={line}><b className="text-ink">이렇게 해 보세요</b> {c.guide}</p>}
      <p className={`${line} border-t border-fill pt-3`}><b className="text-ink">다음 단계</b> {nextText(c.next)}</p>
    </section>
  )
}

// 05 독화 요령(340:249) — 번호(30px, primary-faint) + 제목 16 + 설명 13 + 예시. 2열 3행, 행 사이 구분선.
const CHIP = 'rounded-[8px] px-[10px] py-1 text-[13px] font-bold leading-figma'
const BUBBLE = 'rounded-[12px] rounded-bl-[3px] bg-inactive-bg px-3 py-1.5 text-[12.5px] leading-figma text-ink'
const TIPS = [
  ['01', '똑같이 보이는 소리가 있어요', 'ㅂ · ㅁ · ㅍ는 입술이 닫혀 똑같이 보여요. 정확히 읽기보다 가능성을 좁힌다고 생각해요.', (
    <div className="flex items-center gap-[10px]">
      {['ㅂ', 'ㅁ', 'ㅍ'].map((j) => (
        <div key={j} className="flex flex-col items-center gap-[3px]">
          <img src="/ui/lp-370-90-guide-lips.svg" alt="" aria-hidden className="h-[18px] w-[34px]" />
          <span className="text-[11.5px] font-bold leading-figma text-ink-muted">{j}</span>
        </div>
      ))}
      <span className="text-[12px] leading-figma text-ink-faint">모두 같은 입모양</span>
    </div>
  )],
  ['02', '문맥으로 메꿔요', '입모양이 애매하면 앞뒤 말과 상황으로 판단해요.', (
    <div className="flex items-center gap-2">
      <span className="text-[14px] font-bold leading-figma text-ink">___ 마셔요</span>
      <span className={`${CHIP} bg-primary-100 text-primary-700`}>물</span>
      <span className={`${CHIP} bg-inactive-bg text-ink-hint line-through`}>불</span>
    </div>
  )],
  ['03', '모음을 닻으로 삼아요', '자음보다 모음이 훨씬 잘 보여요. 모음 뼈대를 먼저 잡고 자음을 채워요.', (
    <div className="flex items-center gap-1.5">
      {['ㅏ', 'ㅣ', 'ㅗ', 'ㅜ'].map((v) => <span key={v} className={`${CHIP} bg-primary-100 text-primary-700`}>{v}</span>)}
    </div>
  )],
  ['04', '첫 소리에 집중해요', '단어의 첫 입모양에 정보가 가장 많아요. 시작을 놓치면 뒤가 다 흔들려요.', (
    <p className="flex items-baseline gap-px font-bold leading-figma">
      <span className="text-[22px] text-primary-500">사</span><span className="text-[16px] text-ink-pale">과</span>
    </p>
  )],
  ['05', '보기 좋은 환경을 골라요', '밝은 곳에서 얼굴이 정면으로 보이고 천천히 말할 때 잘 보여요.', <span className={BUBBLE}>천천히, 마주 보고 말해 주세요</span>],
  ['06', '모르면 되물어요', '전부 읽을 필요는 없어요. 핵심 단어만 확인해도 충분해요.', <span className={BUBBLE}>○○ 말씀이세요?</span>],
]

function TipsBody() {
  const rows = [TIPS.slice(0, 2), TIPS.slice(2, 4), TIPS.slice(4, 6)]
  return (
    <div className="flex flex-col">
      {rows.map((row, i) => (
        <div key={row[0][0]} className={`flex flex-col gap-6 md:flex-row md:gap-11 ${i === 0 ? 'pb-[22px] pt-1' : 'border-t border-fill py-[22px]'}`}>
          {row.map(([n, h, d, ex]) => (
            <div key={n} className="flex gap-4 md:w-[361px] md:shrink-0">
              <p className="w-[42px] shrink-0 text-[30px] font-bold leading-figma tracking-[-0.9px] text-primary-faint">{n}</p>
              <div className="flex min-w-0 flex-1 flex-col items-start gap-1.5">
                <p className="text-[16px] font-bold leading-figma text-ink">{h}</p>
                <p className="break-keep text-[13px] leading-[1.6] text-ink-muted">{d}</p>
                <div className="pt-0.5">{ex}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// 11 개발자 소개(342:530) — 사진(또는 DOKA) 60 + 이름 17 · 역할 13.5 · 핸들 12.5. 팀 정보는 config/team.js(랜딩과 같이 씀).
// 누르면 그 줄 아래에 상세가 펼쳐진다(9/28, 가이드 자체가 모달이라 모달을 겹치지 않는다).
function Member({ m, open, onToggle, index }) {
  return (
    <button type="button" onClick={onToggle} aria-expanded={open}
      className={`flex items-center gap-4 rounded-14 p-1 text-left transition hover:bg-primary-50 md:w-[361px] md:shrink-0 ${open ? 'bg-primary-50' : ''}`}>
      <TeamAvatar m={m} index={index} />
      <div className="flex min-w-0 flex-col gap-1 whitespace-nowrap leading-figma">
        <p className="text-[17px] font-bold text-ink">{m.name}</p>
        <p className="text-[13.5px] text-ink-muted">{m.role}</p>
        {m.handle
          ? <p className="text-[12.5px] font-bold text-primary-500">{m.handle}</p>
          : null}
      </div>
    </button>
  )
}

function TeamBody() {
  const [open, setOpen] = useState(null)
  const rows = [TEAM.slice(0, 2), TEAM.slice(2, 4), TEAM.slice(4)]
  return (
    <div className="flex flex-col">
      <p className="pb-2 text-[15px] leading-[1.6] text-ink-muted">LIPLAB을 함께 만든 사람들이에요. 이름을 누르면 자세히 볼 수 있어요.</p>
      <ContactLine className="pb-[22px]" />
      {rows.map((row, i) => {
        const shown = row.find((m) => m.name === open)
        return (
          <div key={row[0].name} className={`flex flex-col gap-4 ${i === 0 ? 'pb-5 pt-1' : 'border-t border-fill py-5'}`}>
            <div className="flex flex-col gap-5 md:flex-row md:gap-11">
              {row.map((m) => <Member key={m.name} m={m} index={TEAM.indexOf(m)} open={open === m.name} onToggle={() => setOpen(open === m.name ? null : m.name)} />)}
            </div>
            {shown && <div className="rounded-14 bg-primary-50 px-4 py-4"><TeamMemberDetail m={shown} /></div>}
          </div>
        )
      })}
      <p className="flex items-center gap-[10px] whitespace-nowrap border-t border-fill pt-5 font-bold leading-figma">
        <span className="text-[13px] text-ink-faint">소스 코드</span>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-[14px] text-primary-500 hover:underline">
          {REPO_URL.replace('https://', '')}
        </a>
      </p>
    </div>
  )
}

const BODY = { overview: OverviewBody, screens: ScreensBody, tips: TipsBody, notes: NotesBody, team: TeamBody }

// initialKey: 처음 열 탭(없거나 모르는 키면 첫 탭). context: '지금 내 상태' 카드 내용({ tab, … }, CurriculumPath가 만든다).
export default function GuideModal({ open, onClose, initialKey, context }) {
  const startKey = TABS.some((t) => t.key === initialKey) ? initialKey : TABS[0].key
  const [activeKey, setActiveKey] = useState(startKey)
  // 포커스 가두기·ESC 닫기·닫으면 연 버튼으로 포커스 복원(hooks/useFocusTrap)
  const dialogRef = useFocusTrap(open, onClose)
  const stripRef = useRef(null)   // 모바일 가로 탭 줄. 처음 연 탭이 화면 밖이면 보이게 민다
  const contentRef = useRef(null)  // 오른쪽 내용. 탭을 바꾸면 맨 위부터 보이게 한다(긴 탭을 내려 본 뒤 다른 탭이 중간부터 보이던 것)

  // 열릴 때 처음 열 탭(initialKey, 없으면 첫 탭)으로 리셋 + 배경 스크롤 잠금. onClose에 기대지 않아, 부모가 다시 그려져도
  // 보던 탭이 처음 탭으로 돌아가지 않는다(startKey는 문자열이라 렌더마다 바뀌지 않는다).
  useEffect(() => {
    if (!open) return undefined
    setActiveKey(startKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open, startKey])

  // 모바일 가로 탭 줄에서 고른 탭이 화면 밖에 있으면 가운데로 민다(처음 연 탭이 오른쪽 끝일 때). 데스크톱에서는 줄이 숨어 있다.
  useEffect(() => {
    if (!open) return
    stripRef.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest', inline: 'center' })
    if (contentRef.current) contentRef.current.scrollTop = 0
  }, [open, activeKey])

  if (!open) return null
  const active = TABS.find((t) => t.key === activeKey) || TABS[0]
  const Body = BODY[active.kind]

  const tabClass = (on) =>
    `w-full rounded-10 px-3 py-[9px] text-left text-[14.5px] font-bold transition-colors ${
      on ? 'bg-primary-100 text-primary-500' : 'text-ink-muted hover:bg-black/[0.03]'
    }`

  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/50 p-4"
      onClick={onClose} role="dialog" aria-modal="true" aria-label="사용법 가이드">
      <div
        className="flex h-[680px] max-h-[90vh] w-full max-w-[1080px] flex-col overflow-hidden rounded-24 bg-white shadow-modal md:flex-row"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 좌측 세로 탭 (데스크톱) */}
        <nav className="hidden w-[248px] shrink-0 flex-col gap-[2px] overflow-y-auto border-r-1.5 border-line bg-surface-nav px-4 pb-6 pt-7 leading-figma md:flex" aria-label="가이드 목차">
          <p className="pb-[10px] pl-3 text-[20px] font-bold tracking-[-0.4px] text-ink">사용법 가이드</p>
          {GROUPS.map((g) => (
            <div key={g.label} className="flex flex-col gap-[2px]">
              {/* 그룹 라벨 — Figma 회색 그룹 헤더(ink-hint) */}
              <p className="pb-[6px] pl-3 pt-[14px] text-[11.5px] font-bold tracking-[0.345px] text-ink-hint">{g.label}</p>
              {g.tabs.map((t) => (
                <button key={t.key} type="button" onClick={() => setActiveKey(t.key)}
                  aria-current={t.key === activeKey ? 'true' : undefined}
                  className={tabClass(t.key === activeKey)}>
                  {t.title}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* 상단 가로 스크롤 탭 (모바일 폴백) */}
        <div className="shrink-0 border-b border-line bg-surface-nav md:hidden">
          <div className="flex items-center justify-between px-4 pt-4">
            <p className="text-[18px] font-bold text-ink">사용법 가이드</p>
            <CloseButton onClose={onClose} />
          </div>
          <div ref={stripRef} className="flex gap-2 overflow-x-auto px-4 pb-3 pt-3">
            {TABS.map((t) => {
              const on = t.key === activeKey
              return (
                <button key={t.key} type="button" onClick={() => setActiveKey(t.key)}
                  aria-current={on ? 'true' : undefined}
                  className={`shrink-0 whitespace-nowrap rounded-full px-3.5 py-2 text-[13.5px] font-bold transition-colors ${
                    on ? 'bg-primary-100 text-primary-500' : 'bg-surface-sunken text-ink-muted'
                  }`}>
                  {t.title}
                </button>
              )
            })}
          </div>
        </div>

        {/* 우측 컨텐츠 */}
        <div ref={contentRef} className="flex min-w-0 flex-1 flex-col overflow-y-auto px-6 py-6 md:py-[30px] md:pl-9 md:pr-[30px]">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-[22px] font-bold leading-figma tracking-[-0.65px] text-ink md:text-[26px]">{active.title}</h2>
            {/* 데스크톱 닫기(모바일은 상단 탭 헤더에 있음) */}
            <span className="hidden md:flex"><CloseButton onClose={onClose} /></span>
          </div>

          <div className="mt-[22px]">
            {context && context.tab === active.key && <StatusCard c={context} />}
            {/* 탭마다 새로 마운트해 강조·시연 상태를 탭 사이에 넘기지 않는다 */}
            <Body key={active.key} tab={active} />
          </div>
        </div>
      </div>
    </div>
  )
}
