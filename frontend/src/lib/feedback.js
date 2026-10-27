export const SUS_QUESTIONS = [
  "나는 이 앱을 자주 쓰고 싶다.",
  "이 앱은 단순했다.",
  "이 앱은 쓰기 쉬웠다.",
  "나는 기계를 잘 아는 사람의 도움 없이 이 앱을 쓸 수 있을 것 같다.",
  "이 앱의 여러 기능이 서로 잘 이어져 있었다.",
  "이 앱은 화면마다 쓰는 방법이 한결같았다.",
  "대부분의 사람은 이 앱 쓰는 법을 아주 빨리 익힐 것 같다.",
  "이 앱은 보자마자 어떻게 쓰는지 알 수 있었다.",
  "나는 이 앱을 쓸 때 자신 있었다.",
  "나는 새로 배울 것 없이 이 앱을 쓸 수 있었다."
]
export const SUS_LABELS = ['전혀 그렇지 않다', '그렇지 않다', '보통이다', '그렇다', '매우 그렇다']
export function susScore(answers) {
  if (answers.length !== 10 || answers.some(v => !Number.isInteger(v) || v < 1 || v > 5)) return null
  return answers.reduce((sum, v) => sum + v - 1, 0) * 2.5
}

export function screenName(path) {
  const names = { '/learn/path': '학습', '/practice/hub': '연습', '/learn/viseme': '입모양 학습', '/learn/word': '단어 학습', '/practice': '문장 연습', '/conversation': '대화 연습', '/tasks': '과제', '/profile': '프로필', '/learn/speaking': '말하기 연습', '/learn/listening': '듣기 연습' }
  return names[path] || (path.startsWith('/analysis') ? '분석' : path.startsWith('/review') ? '복습' : path.startsWith('/listen') ? '듣기' : path.startsWith('/learn') ? '학습' : '현재 화면')
}
