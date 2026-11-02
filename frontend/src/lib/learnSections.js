export const CARDS = {
  scenario: { key: 'scenario', title: '상황별 연습', desc: '카페·병원 등 상황을 골라 연습해요', icon: '/ui/card-scenario.svg', chip: 'bg-pastel-amber', to: '/learn/scenario' },
  endless: { key: 'endless', title: '틀린 유형 계속 풀기', desc: '틀렸던 유형이 계속 나와요', icon: '/ui/tab-card-endless.svg', chip: 'bg-pastel-indigo', to: '/learn/endless' },
  nonsense: { key: 'nonsense', title: '뜻 없는 말 짝 맞추기', icon: '/ui/nav-practice.svg', chip: 'bg-pastel-indigo', to: '/learn/nonsense' },
  mouth: { key: 'mouth', title: '입모양 교실', desc: '입모양과 혀 위치를 확인해요', icon: '/ui/nav-learn.svg', chip: 'bg-pastel-violet', to: '/learn/viseme?tab=learn' },
  sign: { key: 'sign', title: '수어 보기', icon: '/ui/card-sign.svg', chip: 'bg-pastel-mint', to: '/learn/sign' },
  free: { key: 'free', title: '내 문장 입모양 보기', desc: '내가 쓴 문장의 입모양을 확인해요', icon: '/ui/card-free.svg', chip: 'bg-pastel-pink', to: '/pronounce' },
  review: { key: 'review', title: '말하기 복습', icon: '/ui/nav-review.svg', chip: 'bg-pastel-pink', to: '/review/speaking' },
}
export function sectionCards(track, section, wordOpen = false) {
  const keys = section === 'res' ? (track === 'speak' ? ['mouth'] : ['mouth', 'sign']) : track === 'speak' ? ['free', 'review'] : ['scenario', 'endless', ...(wordOpen ? ['nonsense'] : [])]
  return keys.map((key) => CARDS[key])
}
