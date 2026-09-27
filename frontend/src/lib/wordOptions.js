// 2단계 단어 문항의 오답 보기. 서버(/curriculum/words)가 입모양 규칙으로 고른 distractors를 쓴다
// (동구형이음 제외, 숙달 전에는 보이는 최소대립 1개 + 입모양이 다른 단어 2개, 숙달 뒤에는 최소대립 3개). 서버 목록에 없는 단어
// (은행 밖 복습 항목·구버전 서버)는 은행에서 무작위로 고른다. 예전처럼 최소대립 짝을 우선하지 않는다:
// 짝의 약 2/3가 입모양이 완전히 같은 단어라 입만 보고는 풀 수 없는 문항이 됐다.
const shuffle = (a) => [...a].sort(() => Math.random() - 0.5)

export function pickDistractors(target, byWord, words) {
  const served = byWord.get(target)?.distractors
  if (served?.length >= 3) return served.slice(0, 3)
  return shuffle(words.filter((w) => w !== target)).slice(0, 3)
}
