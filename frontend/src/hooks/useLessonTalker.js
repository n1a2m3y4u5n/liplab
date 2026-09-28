import { useCallback, useState } from 'react'
import useStore from '../store/useStore'
import { lessonTalker, lessonSeed } from '../lib/talkers'

// 레슨별 가상 화자(커리큘럼 계획 2-2, docs/talker-variation.md 3절). 단계마다 몇 번째 레슨인지를 사용자별로 기기에 세어 두고,
// 그 번호로 화자와 흔들림 씨앗을 정한다(lib/talkers.lessonTalker). 저장소가 막혀 있으면 이 창에서만 센다.
const KEY = 'liplab_talker_lessons'
const memory = {}
function readCounts() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {} } catch { return memory }
}
function writeCounts(m) {
  try { localStorage.setItem(KEY, JSON.stringify(m)) } catch { Object.assign(memory, m) }
}

// 개발 모드(StrictMode)는 초기화 함수를 두 번 부른다. 같은 단계의 레슨 시작이 1초 안에 다시 오면 앞 결과를 그대로 돌려줘
// 레슨 번호를 두 번 올리지 않는다(실제 레슨은 몇 분씩 걸린다).
let last = { key: null, at: 0, lesson: null }
export function startLesson(userKey, stage) {
  const key = `${userKey}:${stage}`
  const now = Date.now()
  if (last.key === key && now - last.at < 1000) return last.lesson
  const counts = readCounts()
  const n = Number.isInteger(counts[key]) ? counts[key] : 0
  writeCounts({ ...counts, [key]: n + 1 })
  const lesson = { index: n, talker: lessonTalker(userKey, stage, n), seed: lessonSeed(userKey, stage, n) }
  last = { key, at: now, lesson }
  return lesson
}

/** [{index, talker, seed}, 다음 레슨 시작 함수]. stage: 'viseme' | 'word' | 'closure' | 'sentence' | 'endless' */
export default function useLessonTalker(stage) {
  const uid = useStore((s) => s.user?.id ?? 'guest')
  const [lesson, setLesson] = useState(() => startLesson(uid, stage))
  const next = useCallback(() => setLesson(startLesson(uid, stage)), [uid, stage])
  return [lesson, next]
}
