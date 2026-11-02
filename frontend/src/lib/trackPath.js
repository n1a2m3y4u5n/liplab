const READ_ROUTE = { viseme: '/learn/viseme', word: '/learn/word', sentence: '/learn/scenario', conversation: '/learn/scenario?mode=conversation' }
// 단계별 숙달 최소 시도수 — 진행률 표시의 분모(backend/main.py _STAGE1~4_MIN_ATTEMPTS = 8·6·5·4와 같게).
// 9/28부터 서버가 단계마다 min_attempts·mastery(·pass)를 실어 보내므로 이 표는 응답에 없을 때만 쓴다.
const READ_TOTAL = { viseme: 8, word: 6, sentence: 5, conversation: 4 }
export function normalizeRead(stages) {
  return (stages || []).filter((s) => s.stage >= 1 && READ_ROUTE[s.key]).map((s) => ({
    key: s.key, stage: s.stage, no: s.stage, title: s.title, route: READ_ROUTE[s.key],
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || READ_TOTAL[s.key] || 8,
    desc: s.desc || '', mastery: s.mastery ?? null, pass: s.pass ?? null,
  }))
}
// 발화는 0단계(발성)부터 싣는다 — 백엔드가 0단계를 항상 열고 N단계는 N-1 숙달 시 해금하므로
// 빼면 새 사용자의 첫 노드가 잠긴 1단계가 된다. 표시 번호(no)는 1부터.
export function normalizeSpeak(stages) {
  return (stages || []).map((s, i) => ({
    key: `speak-${s.stage}`, stage: s.stage, no: i + 1, title: s.title, route: `/learn/speaking?stage=${s.stage}`,
    status: s.status, attempts: s.attempts ?? 0, total: s.min_attempts || 8,
    desc: s.desc || '', guide: s.guide || '', mastery: s.mastery ?? null, pass: s.pass ?? null,
    probe: s.probe || null, gain: s.gain || null,   // 모음·자음 낱말 속 확인, 4·5단계 개인 향상 경로(speak_curriculum)
  }))
}

