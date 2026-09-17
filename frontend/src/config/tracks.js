// 학습 트랙 정의(리디자인 스펙 6.2) — 독화·말하기 2개.
// ❌ 촉각(tactile) 트랙은 제거됨 — 항목 추가하지 말 것.
//
// 공통 컴포넌트(features/learn/shared)는 이 객체만 보고 트랙 간 차이를 흡수한다.
// - 레슨 링크(to)는 트랙마다 URL 방식이 달라도 완성된 형태로 적는다.
//   독화는 레슨별 경로(/learn/lipreading/lesson/<id>), 말하기는 쿼리(/learn/speaking?stage=N).
// - 잠금·진행 상태는 백엔드 단계 API에서 온다. apiNamespace·stagesMethod는 api.js의 실제 이름이다.
//   (스펙 예시의 learningAPI는 문장 출제·채점용이고, 독화 단계·잠금은 curriculumAPI.getStages가 준다.)
// - lessons[].stage는 그 API 응답의 stage 번호와 매칭된다. practice는 단계 밖 활동이라 잠금이 없다.
// 항목 문구는 기존 PillarHub·GlobalLearningMenu·speakingNavigation에서 가져왔다.
// (node --test에서도 읽히도록 import에 확장자를 적는다)
import { SPEAKING_STAGE_MENU_ITEMS, SPEAKING_REVIEW_MENU_ITEM } from './speakingNavigation.js'

export const TRACKS = {
  lipreading: {
    id: 'lipreading',
    label: '독화',
    hubTitle: '입모양으로 읽어요',
    description: '상대의 입모양을 보고 말을 이해하는 훈련이에요. 입모양 학습부터 문장 학습까지 골라 진행하세요.',
    icon: '👄',
    accent: 'reading',   // LearnHeader 배경색 키
    basePath: '/learn/lipreading',
    apiNamespace: 'curriculumAPI',
    stagesMethod: 'getStages',
    lessons: [
      { id: 'placement', stage: 0, title: '배치검사', desc: '내 독화 수준 진단하기', icon: '📋', to: '/learn/placement' },
      { id: 'viseme', stage: 1, title: '입모양 학습', desc: '자음·모음의 입모양 학습', icon: '👄', to: '/learn/lipreading/lesson/viseme' },
      { id: 'word', stage: 2, title: '단어 학습', desc: '비슷한 입모양 구별 학습', icon: '🔤', to: '/learn/lipreading/lesson/word' },
      { id: 'sentence', stage: 3, title: '문장 학습', desc: '상황별 독화와 AI 대화 학습', icon: '💬', to: '/learn/lipreading/lesson/sentence' },
      // 대화 실전은 문장 학습 화면에서 상황을 고른 뒤 'AI 대화'로 시작한다
      // (시나리오 없이 대화 화면에 직접 들어가면 대시보드로 돌아간다).
      { id: 'conversation', stage: 4, title: '대화 실전', desc: 'AI와 실전 대화', icon: '🗨️', to: '/learn/lipreading/lesson/sentence' },
    ],
    practice: [
      { id: 'closure', title: '문맥 추론', desc: '앞뒤 맥락으로 뜻 찾기', icon: '🧩', to: '/learn/lipreading/lesson/closure' },
      { id: 'multi-conversation', title: '다자 대화', desc: '여러 사람 대화에서 화자와 입모양 읽기', icon: '👥', to: '/learn/lipreading/lesson/multi-conversation' },
      { id: 'pronounce', title: '내 문장 발음 보기', desc: '원하는 문장의 입모양 확인하기', icon: '✍️', to: '/pronounce' },
      { id: 'review', title: '독화 복습', desc: '틀렸던 문장 다시 풀기', icon: '🔁', to: '/review/mistakes' },
    ],
  },
  speaking: {
    id: 'speaking',
    label: '말하기',
    hubTitle: '소리 내어 말해요',
    description: '내 발음을 눈으로 보며 다듬는 훈련이에요. 마이크로 녹음하면 AI가 전사·채점하고 코칭해줘요.',
    icon: '🗣️',
    accent: 'speaking',
    basePath: '/learn/speaking',
    apiNamespace: 'speakAPI',
    stagesMethod: 'getCurriculum',
    lessons: SPEAKING_STAGE_MENU_ITEMS.map(({ stage, label, description, icon, to }) => (
      { id: `stage-${stage}`, stage, title: label, desc: description, icon, to }
    )),
    practice: [
      { id: 'review', title: SPEAKING_REVIEW_MENU_ITEM.label, desc: SPEAKING_REVIEW_MENU_ITEM.description, icon: SPEAKING_REVIEW_MENU_ITEM.icon, to: SPEAKING_REVIEW_MENU_ITEM.to },
    ],
  },
}

export const TRACK_IDS = Object.keys(TRACKS)

export const getTrack = (id) => TRACKS[id] || null
