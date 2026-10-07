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
          ['나중에 할게요', '자가진단을 건너뛰면 1단계부터 시작해요. 프로필의 \'자가진단 다시 하기\'로 언제든 다시 할 수 있어요.'],
        ],
        steps: {
          label: '독화 4단계',
          items: [
            ['입모양 인지', '10개 입모양 그룹을 구별해요.', '8번 · 85%'],
            ['음절·단어', '입모양이 비슷한 단어 가운데 맞는 것을 골라요. 숙달하면 직접 적는 문항도 나와요.', '6번 · 85%'],
            ['문장 (상황별)', '상황별 문장을 입모양으로 읽고 답해요. 잘할수록 직접 적는 문항이 늘어요.', '5번 · 80%'],
            ['대화 실전', 'AI가 하는 말을 입모양으로 읽고 답해요. 못 알아들으면 되물어도 돼요.', '4번 · 75%'],
          ],
        },
        more: [
          ['단계가 열리는 기준', '단계마다 정한 횟수 이상 풀고 최근 정답률이 기준을 넘으면 숙달이에요. 문장은 60점, 대화는 55점 이상이면 맞힌 것으로 세요. 숙달하면 다음 단계가 열려요. 한 번 숙달한 단계는 다시 잠기지 않아요.'],
          ['발화 트랙', '말하기 연습은 따로 6단계예요. 학습 탭 위에서 발화를 고르면 돼요. 체험용 앱에서는 모든 단계가 처음부터 열려 있을 수 있어요.'],
        ],
      },
      {
        key: 'tour', title: '화면 둘러보기', kind: 'overview',
        shots: [{ mock: 'overview', w: 766, h: 404 }],
        annots: [
          ['내 기록', '불꽃은 연속 학습 일수, 별은 모은 XP, 육각형은 레벨이에요. 며칠 이어서 공부할수록 같은 문제에서 받는 XP가 늘어요(최대 3배). 휴대폰에서는 오른쪽 위 이름 첫 글자를 누르면 프로필로 가요.', 'stats'],
          ['오른쪽 패널', '넓은 화면(가로 1280px 이상)에서 오른쪽에 보여요. 오늘의 과제, 다시 풀 오답 수(틀린 문장·말하기 포함), 북마크 수를 보여 줘요. 과제 탭에서는 레벨 진행으로 바뀌어요. 복습 탭에서는 이번 주에 학습한 날로 바뀌어요.', 'rail'],
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
          ['트랙 전환', '독화 · 발화 · 소리 듣기를 골라요. 트랙마다 경로와 진도가 따로 저장돼요.', 'switch'],
          ['가이드', '보고 있는 단계의 설명, 진행률, 숙달 기준과 사용법을 바로 봐요.', 'guideBtn'],
          ['단계 노드', 'DOKA 하나가 한 단계예요. 체크가 붙은 DOKA는 숙달한 단계예요. 링을 두른 큰 DOKA는 지금 단계예요. 눈을 뜬 연한 DOKA는 건너뛸 수 있는 다음 단계, 잠든 DOKA는 잠긴 단계예요. 열린 DOKA를 누르면 그 단계를 바로 시작해요.', 'nodes'],
          ['단계 이동', "좌우 화살표로 이전 · 다음 단계를 둘러봐요. 바로 다음 잠긴 단계는 '여기로 건너뛸까요?'를 누르고 한 번 더 확인하면 열려요.", 'arrows'],
          ['레슨 카드', "보고 있는 단계의 진행률이 떠요. 숫자는 숙달 판정에 필요한 최소 시도 수 가운데 푼 수예요. 다 채웠는데 정답률이 모자라면 '숙달 중'으로 보여요. 처음이면 학습 시작하기를, 이어서 할 때는 이어서 학습하기를 눌러요.", 'sheet'],
        ],
      },
      {
        key: 'reading', title: '독화 레슨', kind: 'screens', small: true,
        shots: [{ mock: 'readQuestion', w: 238, h: 358 }, { mock: 'readWrong', w: 238, h: 358 }], demo: 'reading',
        annots: [
          ['북마크', '다시 보고 싶은 문제를 저장해요.', 'bookmark'],
          ['입모양 영상', '입모양이 계속 반복돼요. 사람마다 입 움직임이 달라서 왼쪽 위 화자 1~4가 레슨마다 바뀌어요. 다섯 레슨에 한 번은 기본 화자예요. 대화·복습도 같아요.', 'stage'],
          ['보기 고르기', '보기를 누르거나 숫자 키 1~4로 고르고 확인을 눌러요. 1단계는 입모양 그룹을, 2단계는 단어를 골라요. 단어의 틀린 보기는 화면에서 구별되는 것만 나와요. 2단계 레슨의 2문항과 문맥 추론은 문장 속 빈칸을 보기 3개 중에서 채워요.', 'options'],
          ['결과 바', '맞히면 초록, 틀리면 빨강이에요. 틀린 입모양·단어는 다음 날 복습에 다시 나와요. 12문항을 마치면 정답률·XP·걸린 시간이 나와요.', 'resultBar'],
        ],
        more: [
          ['2단계 결과 아래', '틀리면 어느 소리를 무엇으로 읽었는지, 원래 같은 입모양 짝인지 알려 줘요. 뜻은 수어로도 봐요. 입 옆 기호는 바람이 거센소리, 채운 마름모가 된소리, 물결이 콧소리예요. 숙달할수록 기호가 흐려져요.'],
          ['2단계 숙달 뒤', "12문항 중 4문항은 읽은 단어를 직접 적어요. 입모양이 똑같은 다른 말을 쓰면 '입모양은 맞음'으로 반만 쳐요."],
          ['약한 입모양은 천천히', '자주 틀리는 입모양은 약 1.35배 천천히 보여줘요. 2단계에서 느리게 보고 맞힌 답은 숙달에 반만 치고, 숙달에 가까워지면 원래 속도로 보여요. 검사는 늘 같은 속도예요.'],
          ['3단계 문장', '힌트는 글자 수, 첫 글자, 발음 자막 순서로 열려요. 발음 자막까지 보고 낸 답은 숙달에 들어가지 않아요. 잘할수록 보기 고르기가 줄고, 60점 아래 문장은 오늘의 복습에 하루 5개까지 다시 나와요.'],
          ['4단계 대화', '6턴을 이어가요. 처음에 요령 카드가 뜨고, 다시·천천히·다른 말로 되묻기는 한 턴에 두 번까지 감점이 없어요. 두 턴 연속 40점 아래면 쉬운 말로, 85점 이상이면 긴 말로 바뀌어요.'],
          ['문장 플레이어', '3·4단계 아바타 아래에서 재생 속도를 바꿔요. 투명 두상, 측면 보기, 성도 단면(옆에서 자른 입 안 그림)도 켜요. 측면 보기에서는 입술을 내밀고 모으는 움직임이 잘 보여요.'],
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
          ['자세히 보기', '이렇게 들렸어요, 소리별 정확도, DOKA의 한마디를 봐요. 웹캠 미러를 켰다면 입모양 점수가 따로 나와요. 모음 단계는 내 혀 위치를 목표와 겹쳐 보여 줘요.', 'detail'],
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
            ['자음', '입술소리부터 13개 소리를 한 소리만 다른 단어 짝으로 연습해요. 불/풀, 달/탈처럼 입모양이 같은 짝은 숨의 세기가 달라요. 거센소리는 손바닥을 입 앞에 대고, 바람이 세게 닿게 내 보세요. 사·자·차·하처럼 입 안이나 목에서 나는 소리도 연습해요.', '8번 · 85%'],
            ['음절·단어', '짧은 단어부터 여러 음절까지 또박또박 말하고, 받침까지 살려요. 20번 이상 말하고 최근 10번 점수가 처음 10번보다 15점 이상 오르고 50점 이상이면 68%에 못 닿아도 숙달이에요.', '8번 · 68%'],
            ['문장·억양', '평서문은 끝을 내리고, 예/아니오로 답하는 의문문은 마지막 음절을 올려요. 음절·단어처럼 처음보다 15점 이상 오르면 숙달로 봐요.', '6번 · 68%'],
          ],
        },
        more: [
          ['그래프와 웹캠 미러', '말하는 동안 파형, 목소리 크기, 높낮이가 바로 보여요. 웹캠 미러를 켜면 내 얼굴을 아바타 입모양과 나란히 비교해요.'],
          ['이 단계 숙달', '최근 통과율과 시도 수가 문항 아래에 보여요. 모음·자음은 그 소리가 든 낱말도 최근 3번 중 2번 합격해야 숙달이에요.'],
          ['출제 순서', '모음·자음·음절·단어는 최근 녹음에서 약하게 나온 소리가 든 문항을 앞쪽에 섞어 내요. 모음·자음은 한 바퀴 돈 뒤부터 순서를 섞어요.'],
          ['아쉬울 때', '통과하지 못하면 넘어가기와 다시 말하기 중에서 골라요.'],
        ],
      },
      {
        key: 'listening', title: '소리 듣기 6단계', kind: 'notes',
        intro: '보청기·인공와우로 말소리를 알아듣는 연습이에요. 앞 단계를 숙달하면 다음 단계가 열려요. 하루 15~20분, 일주일에 5일쯤이 알맞아요. 레슨 카드 아래 \'오늘의 듣기\'를 누르면 오늘 할 연습을 15분 안팎으로 묶어 차례로 이어 줘요.',
        steps: {
          label: '소리 듣기 6단계',
          items: [
            ['소리 확인', '음·우·아·이·쉬·스 여섯 소리가 들리는지 확인해요. 낮은 소리부터 아주 높은 소리까지 고르게 들어 있어요. 어제 들리던 소리가 안 들리면 기기를 점검해 보세요.', '한 번'],
            ['소리 구별', '두 소리가 같은지 달라요. 길이·억양 → 모음 → 자음의 세기 → 소리 자리·받침 순서로 수준이 저절로 올라가요. 수준 3부터는 두 소리를 다른 목소리로 들려줘요.', '수준 4 · 10번 중 9번'],
            ['낱말 고르기', '소리만 듣고 낱말을 골라요. 보기는 2개에서 4개로, 나중에는 한 소리만 다른 말로 바뀌어요.', '수준 3 · 10번 중 8번'],
            ['문장 알아듣기', '조용한 곳에서 문장을 듣고 들은 대로 써요. 틀린 낱말은 첫소리 자음만 보여 주니 다시 듣고 고쳐 써요.', '10번 · 80%'],
            ['소음 속 듣기', '여러 사람이 떠드는 소리 속에서 문장을 들어요. 낱말을 절반 이상 맞히면 소음이 커지고 놓치면 작아져서, 내가 낱말을 열에 넷쯤 알아듣는 소음 크기(역치)를 찾아요. 네 번에 한 번은 입모양이 함께 나와요.', '역치 0 dB 또는 3 dB 낮아짐'],
            ['대화 듣기', '병원·가게·안내 방송 같은 말을 듣고 내용을 골라요. 다시·천천히·다른 말로 되묻기는 감점이 없어요. 조용함·소음·전화 소리 중에서 골라요.', '12번 · 70%'],
          ],
        },
        more: [
          ['오늘의 듣기', '소리 확인 → 약한 소리 짝 → 문장 → 대화 순서로, 열린 단계에 맞춰 오늘 할 것을 정해 줘요. 블록 사이에 쉬어 가도 되고, 끝나면 오늘 연습한 분을 15분 목표와 비교해 보여 줘요. 과제 탭의 소리 듣기 과제를 눌러도 들어가요.'],
          ['연습 탭의 소리 듣기', '단계와 따로 원하는 것만 골라 연습해요. 소리 짝 집중 연습, 받아쓰기, 소음 속 듣기, 상황별 대화 듣기, 전화·울리는 방·잡음 같은 듣기 조건 연습이 있어요. 연습한 답은 단계 숙달에 들어가지 않아요.'],
          ['소리 교실', '헷갈리기 쉬운 소리 짝을 종류별로 골라 채점 없이 들어 봐요. 하나씩, 번갈아, 여러 목소리로 들을 수 있고, 짝마다 입모양이 같은지 다른지도 알려 줘요. 입모양이 같은 짝은 소리로만 가를 수 있어요.'],
          ['소리 크기', '처음에 편안한 크기를 맞춰요. 소음이 커져도 전체 소리 크기는 그대로이고 말과 소음의 비율만 바뀌어요. 귀가 아프거나 울리면 바로 멈추세요.'],
          ['소음 속 듣기 검사', '처음과 나중에 20문장 검사로 역치를 측정해요. 검사 문장과 목소리는 훈련에 나오지 않아서 실력이 는 정도를 비교할 수 있어요.'],
          ['안내', '청력을 진단하거나 치료하지 않아요. 보청기·인공와우 조절은 청능사나 병원에서 해요.'],
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
          ['수어 보기', '문장을 입력하면 한국수어의 낱말 순서로 바꾸고, 단어마다 국립국어원 수어 영상을 보여 줘요. 사전에 없는 말은 지문자(손가락 글자)로 보여요. 공식 통역은 아니에요.', 'sign'],
          ['엔드리스 학습', '두 레슨이 12문항씩 번갈아 나와요. 단어 레슨은 약한 입모양이 든 문제가 더 자주 나와요. 문맥 추론 레슨은 입모양이 같은 단어 중 문장에 맞는 것을 골라요. 지금 나오는 유형을 숙달도가 낮은 순서로 보여 줘요. 원할 때 멈추면 돼요.', 'endless'],
          ['입모양 교실', '입모양 그룹 10개마다 잘 보이는 정도, 소리 내는 법, 예시 단어를 봐요. 투명 두상을 켜면 혀와 치아가 비쳐 보이고, 성도 단면으로 옆에서 본 혀 위치도 봐요.', 'mouth'],
        ],
        more: [
          ['웹캠으로 내 입모양 확인', '입모양 교실에서 내 입모양을 목표와 비교해 점수와 맞추는 방법을 바로 보여 줘요. 아바타도 내 입을 따라 해요. 영상은 기기 밖으로 나가지 않아요.'],
          ['여러 명 대화', 'AI 대화에서 여러 명을 고르면 2~4명이 번갈아 말하고, 사람마다 입 움직임이 달라요. 누가 말하는지 먼저 찾고, 입모양이 같은 문장 중 흐름에 맞는 것을 골라요.'],
          ['빠른 말', '단어 단계를 숙달하면 엔드리스 단어를 1.25배, 1.6배, 2배 속도로 봐요. 2배는 문장을 소리 내 읽는 빠르기에 가까워요. 가장 빠른 속도에서 최근 12문항 중 10개를 맞히면 다음 속도예요. 복습은 숙달한 단계만 1.25배예요.'],
          ['음성으로 움직이는 아바타', '자유 발화 아래에서 녹음한 목소리로 아바타 입을 움직여 봐요. 서버에 모델이 없으면 이 칸은 보이지 않아요.'],
          ['소리 듣기 묶음', '아래 청록 카드들은 보청기·인공와우로 듣는 연습이에요. 소리 짝 집중 연습, 받아쓰기, 소음 속 듣기는 원하는 만큼 이어지고, 상황별 대화 듣기는 장소를, 듣기 조건 연습은 전화·울리는 방·잡음을 골라요. 소리 교실에서는 채점 없이 소리 짝을 들어 봐요. 준비 중인 카드는 흐리게 보여요.'],
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
        more: [
          ['소리 듣기 15분', '오늘의 과제에 청록색 소리 듣기 과제가 있으면 오늘 들은 분이 채워져요. 누르면 오늘의 듣기로 바로 가요.'],
        ],
      },
      {
        key: 'review', title: '복습', kind: 'screens',
        shots: [{ mock: 'review', w: 446, h: 560 }],
        annots: [
          ['오답 복습', '입모양·단어 레슨과 말하기에서 틀린 문제는 다음 날 다시 나와요. 맞힐수록 간격이 1일, 6일처럼 벌어지다 목록에서 빠져요. 60점 아래로 끝난 문장은 최근 10개까지 모이고, 오늘의 복습에서 하루 5개까지 다시 읽어요.', 'ctaWrong'],
          ['북마크 복습', '레슨 중 북마크 버튼으로 저장한 문제예요.', 'ctaMark'],
          ['항목', '언제 몇 번 틀렸는지 보여 주고, 누르면 그 종류의 복습을 시작해요.', 'items'],
          ['지우기', '누르면 항목마다 체크박스가 생겨요. 골라서 한 번에 지워요. 전체 선택도 돼요. 틀린 문장은 이 화면에서만 숨겨져요.', 'erase'],
        ],
        more: [
          ['듣기 복습', '소리 듣기에서 놓친 낱말과 문장은 며칠 뒤 청록 \'듣기 복습\' 카드에 모여요. 목록에는 \'듣기\' 배지로 보여요. 낱말을 먼저 고르고 문장을 받아써요. 복습한 답은 단계 숙달에 들어가지 않아요.'],
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
          ['약점 입모양·혼동 지도', '전체 통계 아래 링크로 들어가요. 입모양 종류별 점수와 자주 헷갈린 짝을 보여 줘요. 원래 같은 입모양인 짝은 따로 표시해요.'],
          ['소리 듣기 칸', '소리 듣기를 한 적이 있으면 차트 아래에 최근 역치, 이번 주 듣기 분, 소리 구별 정답률이 보여요. 결과 보기를 누르면 검사 추이와 자주 헷갈린 소리를 자세히 봐요.'],
          ['학습 효과 리포트', '학습곡선, 숙달까지 걸린 시도 수, 처음보다 얼마나 늘었는지를 봐요. 사전·사후 검사(각 24문항)는 난이도가 같아서 훈련 전과 후를 비교할 수 있어요. 사후 문항 절반은 검사에만 나오는 화자가 말하고, 그 점수를 \'새 가상 화자\'로 따로 보여 줘요. 검사 기록, 자주 틀린 것(오류 프로파일), 학습량은 흑백 한 장으로 인쇄해 교사나 언어재활사와 나눠요.'],
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
  const head = `${c.minAttempts}번 이상 ${verb} ${rate} ${c.mastery}%`
  // 말하기 모음·자음은 낱말 속 소리 확인(probe), 4·5단계는 개인 향상 경로(gain)가 더 있다(speak_curriculum)
  if (c.probe) return `${head}에 닿은 뒤, 그 소리가 든 낱말을 최근 ${c.probe.n}번 중 ${c.probe.need}번 합격하면 숙달이에요.`
  const base = `${head} 이상이면 숙달이에요.`
  if (c.gain) return `${base} ${c.gain.min_attempts}번 이상 말하고 최근 ${c.gain.recent}번 점수가 처음 ${c.gain.first}번보다 ${c.gain.delta}점 이상 올라도 숙달이에요.`
  return base
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
  ['06', '모르면 되물어요', '전부 읽을 필요는 없어요. 핵심만 되물어 확인해요. 대화 실전의 되묻기 버튼으로 연습해 봐요.', (
    <div className="flex items-center gap-1.5">
      {['다시', '천천히', '다른 말로'].map((t) => (
        <span key={t} className="rounded-[10px] border-2 border-line bg-white px-2.5 py-1 text-[12.5px] font-bold leading-figma text-ink">{t}</span>
      ))}
    </div>
  )],
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
