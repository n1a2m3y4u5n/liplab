const PHONEME_KEYS = ['initial', 'medial', 'final']
const FEATURE_LABELS = {
  bilabial: '양순음',
  open_vowel: '개구 모음',
  front_vowel: '전설 모음',
  rounded_vowel: '원순 모음',
  central_vowel: '중설 모음',
  alveolar: '치경음',
  velar: '연구개음',
  glottal: '후음',
  diphthong: '이중 모음',
  palatal: '구개음',
  transition_bilabial: '양순 전이',
  transition_alveolar: '치경 전이',
  transition_velar: '연구개 전이',
  silence: '쉼',
  neutral: '중립',
  unknown: '미분류',
}

function round(value, digits = 1) {
  const factor = 10 ** digits
  return Math.round((value || 0) * factor) / factor
}

export function formatFeatureLabel(feature) {
  if (!feature) return '아직 포커스 영역이 없습니다'

  if (FEATURE_LABELS[feature]) return FEATURE_LABELS[feature]

  return feature
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function getXpToNextLevel(totalXp = 0) {
  const currentLevel = Math.max(1, Math.floor(Math.sqrt(totalXp / 100)) + 1)
  const nextLevel = currentLevel + 1
  const nextThreshold = (nextLevel - 1) ** 2 * 100

  return {
    currentLevel,
    nextLevel,
    xpRemaining: Math.max(0, nextThreshold - totalXp),
  }
}

export function getWeeklySnapshot(calendarData = {}) {
  const today = new Date()
  const keys = []

  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date(today)
    date.setDate(today.getDate() - offset)
    keys.push(date.toISOString().slice(0, 10))
  }

  const counts = keys.map((key) => calendarData[key] || 0)

  return {
    daysActive: counts.filter((count) => count > 0).length,
    sessions: counts.reduce((sum, count) => sum + count, 0),
    bestDay: counts.length > 0 ? Math.max(...counts) : 0,
  }
}

export function buildDashboardRecommendation({ statistics, calendarData, user }) {
  const totalSessions = statistics?.total_sessions || 0
  const averageScore = statistics?.average_score || 0
  const weakViseme = statistics?.weak_visemes?.[0] || null
  const weekly = getWeeklySnapshot(calendarData)
  const xp = getXpToNextLevel(user?.total_xp || 0)

  if (totalSessions === 0) {
    return {
      title: '가벼운 워밍업부터 시작하세요',
      description: '먼저 학습 모드로 입모양에 익숙해진 뒤, 점수가 반영되는 테스트 모드로 넘어가는 편이 좋습니다.',
      mode: 'study',
      actionLabel: '학습 모드 준비',
      stats: [
        `레벨 ${xp.nextLevel}까지 ${xp.xpRemaining} XP`,
        `이번 주 활동 ${weekly.daysActive}/7일`,
        '아직 약점 입모 데이터가 없습니다',
      ],
    }
  }

  if (averageScore < 60) {
    return {
      title: '난이도를 올리기 전에 정확도를 회복하세요',
      description: '평균 점수가 아직 불안정합니다. 먼저 오답 복습으로 감각을 되찾은 뒤 주관식 테스트로 돌아가는 편이 좋습니다.',
      mode: 'review',
      actionLabel: '복습 모드 준비',
      stats: [
        `평균 점수 ${round(averageScore)}%`,
        `최근 7일 세션 ${weekly.sessions}회`,
        weakViseme ? `집중 영역: ${formatFeatureLabel(weakViseme.feature)}` : '약점 데이터가 더 필요합니다',
      ],
    }
  }

  if (weakViseme && weakViseme.error_rate >= 35) {
    return {
      title: '가장 약한 입모를 먼저 고정하세요',
      description: '선택지가 있는 빠른 반복 훈련으로 패턴을 안정시킨 뒤, 다시 직접 입력 테스트로 돌아가는 편이 효율적입니다.',
      mode: 'test-multiple',
      actionLabel: '4지선다 준비',
      stats: [
        `약한 영역: ${formatFeatureLabel(weakViseme.feature)}`,
        `오답률 ${round(weakViseme.error_rate)}%`,
        `레벨 ${xp.nextLevel}까지 ${xp.xpRemaining} XP`,
      ],
    }
  }

  if (weekly.daysActive < 3) {
    return {
      title: '가벼운 세션으로 학습 흐름을 다시 만드세요',
      description: '부담이 큰 채점 없이 스트릭을 이어가려면 짧은 대화 연습이 가장 빠릅니다.',
      mode: 'conversation',
      actionLabel: '대화 연습 준비',
      stats: [
        `이번 주 활동 ${weekly.daysActive}/7일`,
        `최근 7일 세션 ${weekly.sessions}회`,
        `레벨 ${xp.nextLevel}까지 ${xp.xpRemaining} XP`,
      ],
    }
  }

  return {
    title: '이제 더 어려운 인식 훈련으로 밀어붙일 수 있습니다',
    description: '기본 정확도가 안정적이므로 주관식 테스트를 유지하면서 음운 정확도를 더 끌어올릴 수 있습니다.',
    mode: 'test',
    actionLabel: '테스트 모드 준비',
    stats: [
      `평균 점수 ${round(averageScore)}%`,
      `이번 주 최고 ${weekly.bestDay}세션`,
      `레벨 ${xp.nextLevel}까지 ${xp.xpRemaining} XP`,
    ],
  }
}

export function buildSessionSummary(results = []) {
  const safeResults = Array.isArray(results) ? results : []
  const totalItems = safeResults.length

  if (totalItems === 0) {
    return {
      totalItems: 0,
      completedItems: 0,
      averageScore: null,
      totalXp: 0,
      averageTimeSeconds: 0,
      strongPhoneme: null,
      weakPhoneme: null,
      incorrectItems: [],
      bestResult: null,
      weakestResult: null,
    }
  }

  const phonemeTotals = {
    initial: 0,
    medial: 0,
    final: 0,
  }

  for (const result of safeResults) {
    for (const key of PHONEME_KEYS) {
      phonemeTotals[key] += result.phonemeAccuracy?.[key] || 0
    }
  }

  const phonemeAverages = Object.fromEntries(
    PHONEME_KEYS.map((key) => [key, round(phonemeTotals[key] / totalItems)])
  )

  const sortedPhonemes = [...PHONEME_KEYS].sort(
    (left, right) => phonemeAverages[right] - phonemeAverages[left]
  )
  const sortedResults = [...safeResults].sort((left, right) => right.score - left.score)

  return {
    totalItems,
    completedItems: safeResults.filter((item) => typeof item.score === 'number').length,
    averageScore: round(
      safeResults.reduce((sum, item) => sum + (item.score || 0), 0) / totalItems
    ),
    totalXp: safeResults.reduce((sum, item) => sum + (item.xpGained || 0), 0),
    averageTimeSeconds: round(
      safeResults.reduce((sum, item) => sum + (item.timeSpentSeconds || 0), 0) / totalItems
    ),
    phonemeAverages,
    strongPhoneme: sortedPhonemes[0],
    weakPhoneme: sortedPhonemes[sortedPhonemes.length - 1],
    incorrectItems: safeResults.filter((item) => (item.score || 0) < 80),
    bestResult: sortedResults[0] || null,
    weakestResult: sortedResults[sortedResults.length - 1] || null,
  }
}
