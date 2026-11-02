import { normalizeRead, normalizeSpeak } from './trackPath.js'
import { pathNodeState } from './pathNodes.js'
import { recommendedStage, quotaView } from './listenQuota.js'
import { todayReviewStart, todayReviewCount } from './reviewDue.js'
import { TRACK_LABEL } from './iaLabels.js'
export function todayNext({ stages, speak, listen, due, tasks, lastTrack = 'read' }) {
  if (!stages) return { label: '학습으로 가기', line: '정보를 가져오지 못했어요', to: '/learn/path', retry: true }
  if (stages.placed === false) return { label: '시작하기', to: '/onboarding' }
  const track = ['read', 'speak', 'listen'].includes(lastTrack) ? lastTrack : 'read'
  const rec = recommendedStage(listen)
  if (track === 'listen' && rec === 0 && !listen?.ling_today) return { label: '소리 확인하기', line: '소리 듣기 · 1분', to: '/learn/listening?stage=0' }
  const n = todayReviewCount(due)
  const review = { label: '복습 시작하기', line: `오늘 복습 ${n}개`, to: todayReviewStart(due), review: true }
  const studied = (tasks?.daily || []).some((t) => ['two_sessions', 'listen_15'].includes(t.key) && t.cur >= 1)
  if (studied && n > 0) return review
  const list = track === 'listen' ? (listen?.stages || []).map((s, i) => ({ ...s, no: i + 1, route: `/learn/listening?stage=${s.stage}` })) : track === 'speak' ? normalizeSpeak(speak?.stages) : normalizeRead(stages.stages)
  const idx = track === 'listen' ? list.findIndex((s) => s.stage === rec) : pathNodeState(list, track).currentIdx
  const node = list[idx]
  if (track === 'listen' && quotaView(node?.quota).met) return n > 0 ? review : { label: '한 묶음 더 하기', line: '소리 듣기 · 오늘 몫을 마쳤어요', to: `/learn/listening?stage=${rec}` }
  if (idx < 0) return n > 0 ? review : { label: '자유 연습 하기', line: TRACK_LABEL[track], to: `/learn/path?track=${track}&section=free` }
  return { label: node.attempts > 0 ? '이어서 학습하기' : '학습 시작하기', line: `${TRACK_LABEL[track]} · ${node.no}단계 ${node.title}`, to: node.route, state: track === 'read' && node.stage >= 3 ? { from: 'path' } : undefined }
}
