export const SPEAKING_STAGE_MENU_ITEMS = [
  { stage: 0, label: '발성', description: '원할 때 목소리 내기 · 길게 유지', icon: '🗣️', to: '/learn/speaking?stage=0' },
  { stage: 1, label: '운율 조절', description: '크기 · 길이 · 높낮이 바꾸기', icon: '🎚️', to: '/learn/speaking?stage=1' },
  { stage: 2, label: '모음', description: '기본 모음 8개 — 가장 잘 보이는 소리', icon: '👄', to: '/learn/speaking?stage=2' },
  { stage: 3, label: '자음', description: '입술소리부터 · 최소대립쌍', icon: '🅿️', to: '/learn/speaking?stage=3' },
  { stage: 4, label: '음절·단어', description: '짧은 단어부터 여러 음절까지', icon: '🔤', to: '/learn/speaking?stage=4' },
  { stage: 5, label: '문장·억양', description: '평서문은 내림, 의문문은 올림', icon: '💬', to: '/learn/speaking?stage=5' },
]

export const SPEAKING_REVIEW_MENU_ITEM = {
  label: '말하기 복습',
  description: '부족했던 발음 다시 연습하기',
  icon: '🔁',
  to: '/review/speaking',
}

export const SPEAKING_MENU_ITEMS = [...SPEAKING_STAGE_MENU_ITEMS, SPEAKING_REVIEW_MENU_ITEM]

export const getSpeakingStageMenuItem = (stage) => (
  SPEAKING_STAGE_MENU_ITEMS.find((item) => item.stage === stage)
)
