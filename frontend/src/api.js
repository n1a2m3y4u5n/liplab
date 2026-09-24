import axios from 'axios'
import useStore from './store/useStore'

/**
 * Axios instance with JWT token management and interceptors
 */
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: attach JWT token
api.interceptors.request.use(
  (config) => {
    const token = useStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: handle authentication errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || ''
    // 토큰 만료/무효 시: 로그아웃 후 재부팅 → AuthGate가 데모 계정으로 자동 재로그인.
    // (데모 로그인 요청 자체의 실패는 무한루프 방지를 위해 재부팅하지 않는다.)
    // 토큰 없이 보낸 요청의 401(로그인 실패, 미인증으로 연 공개 페이지 /terms·/privacy)은 만료가 아니라서
    // 재부팅하지 않는다. 재부팅하면 공개 페이지가 무한 새로고침된다(A11ySettings가 마운트마다 /auth/me 호출).
    if (error.response?.status === 401 && !url.includes('/auth/demo') && useStore.getState().token) {
      useStore.getState().logout()
      window.location.reload()
    }
    return Promise.reject(error)
  }
)

// ============================================
// Authentication API
// ============================================

export const authAPI = {
  // consent: { agree_terms, age_confirmed } — 서버가 확인하고 동의 기록(ConsentRecord)으로 남긴다.
  register: async (email, username, password, consent = {}) => {
    const response = await api.post('/auth/register', {
      email,
      username,
      password,
      agree_terms: !!consent.agree_terms,
      age_confirmed: !!consent.age_confirmed,
    })
    return response.data
  },

  login: async (email, password) => {
    const response = await api.post('/auth/login', {
      email,
      password,
    })
    return response.data
  },

  // 로그인 없이 데모 계정으로 즉시 입장(멱등)
  demoLogin: async () => {
    const response = await api.post('/auth/demo')
    return response.data
  },

  getMe: async () => {
    const response = await api.get('/auth/me')
    return response.data
  },
}

// ============================================
// Core Learning API
// ============================================

export const learningAPI = {
  getVisemes: async (text) => {
    const response = await api.get('/viseme', {
      params: { text },
    })
    return response.data
  },

  getScenario: async (situation, level) => {
    const response = await api.get('/scenario', {
      params: { situation, level },
    })
    return response.data
  },

  submitProgress: async (progressData) => {
    const response = await api.post('/progress', progressData)
    return response.data
  },

  getStatistics: async () => {
    const response = await api.get('/statistics')
    return response.data
  },

  getConversationTurn: async (situation, level, history) => {
    const response = await api.post('/conversation', { situation, level, history })
    return response.data
  },

  // Bookmarks
  getBookmarks: async (domain) => {
    const response = await api.get('/bookmarks', { params: domain ? { domain } : {} })
    return response.data
  },
  addBookmark: async (sentence, situation, level, domain = 'read') => {
    const response = await api.post('/bookmarks', { sentence, situation, level, domain })
    return response.data
  },
  removeBookmark: async (id) => {
    const response = await api.delete(`/bookmarks/${id}`)
    return response.data
  },

  // Analysis
  resetAnalysis: async () => {
    const response = await api.delete('/analysis/reset')
    return response.data
  },

  // Calendar (activity heatmap)
  getCalendar: async () => {
    const response = await api.get('/calendar')
    return response.data  // { 'YYYY-MM-DD': count }
  },
  // 회차 히스토리·활동 캘린더 — 날짜(브라우저 현지)별 '무엇을 학습했는지' { 'YYYY-MM-DD': [{kind,label,n,accuracy}] }
  getCalendarActivities: async (daysBack = 150) => (await api.get('/calendar/activities', {
    params: { days_back: daysBack, tz_offset_min: new Date().getTimezoneOffset() },
  })).data,
  // 회차 상세(Figma 212:24) — 히스토리 한 행(현지 날짜×종류×주제)의 문제별 기록·요약·코칭
  getActivityDetail: async (day, kind, topic = '') => (await api.get('/analysis/activity-detail', {
    params: { day, kind, topic, tz_offset_min: new Date().getTimezoneOffset() },
  })).data,
  // 분석 탭 요약·배지(backend/analytics.py). 날짜·연속 학습은 브라우저 시간대 기준.
  getAnalysisOverview: async () => (await api.get('/analysis/overview', {
    params: { tz_offset_min: new Date().getTimezoneOffset() },
  })).data,

  // Review sentences (wrong answers)
  getReviewSentences: async () => {
    const response = await api.get('/review-sentences')
    return response.data
  },

  // 한국어 → 한국수어(KSL) 학습 보조 번역
  translateSign: async (text) => {
    const response = await api.post('/sign/translate', { text }, { timeout: 60000 })
    return response.data
  },
}

// ============================================
// Curriculum (단계형 커리큘럼) API
// ============================================

export const curriculumAPI = {
  getStages: async () => (await api.get('/curriculum/stages')).data,
  setTrack: async (track, start_stage) => (await api.post('/curriculum/track', { track, start_stage })).data,
  resetTrack: async () => (await api.post('/curriculum/track/reset')).data,
  getVisemeLessons: async () => (await api.get('/curriculum/viseme-lessons')).data,
  submitRecognition: async (viseme_id, chosen_id) =>
    (await api.post('/curriculum/recognition', { viseme_id, chosen_id })).data,
  getWords: async () => (await api.get('/curriculum/words')).data,
  submitWord: async (word, correct, chosen) => (await api.post('/curriculum/word-answer', { word, correct, chosen })).data,
  getClosure: async () => (await api.get('/curriculum/closure')).data,
  submitClosure: async (item_id, chosen) => (await api.post('/curriculum/closure-answer', { item_id, chosen })).data,
  confusionMatrix: async () => (await api.get('/curriculum/confusion-matrix')).data,
  getRecommendedLevel: async () => (await api.get('/curriculum/recommended-level')).data,
  getNext: async () => (await api.get('/curriculum/next')).data,
  getCues: async (text, { focus = false, maxCues = null } = {}) => (await api.get('/cues', {
    params: { text, ...(focus ? { focus: true } : {}), ...(maxCues && maxCues > 0 ? { max_cues: maxCues } : {}) },
  })).data,
  // session(선택): 웹캠 조음 교정 세션 요약 { gap_start, gap_end, n_samples } (축 E-9)
  recordMouth: async (viseme_id, score, session = {}) => (await api.post('/curriculum/mouth-attempt', { viseme_id, score, ...session })).data,
  getArticulationTrend: async () => (await api.get('/analysis/articulation')).data,
  getMultiConversation: async (speakers = 2, turns = 6, scene) => (await api.get('/conversation/multi', { params: { speakers, turns, ...(scene ? { scene } : {}) } })).data,
  recordMultiConversation: async (payload) => (await api.post('/conversation/multi/result', payload)).data,
  getPlacement: async (n = 8, form = null) => (await api.get('/assessment/placement', { params: form ? { n, form } : { n } })).data,
  scorePlacement: async (items, responses, form = 'placement') => (await api.post('/assessment/score', { items, responses, form })).data,
  nextPlacementItem: async (asked, responses, n = 8) => (await api.post('/assessment/placement/next', { asked, responses, n })).data,
  getAssessmentHistory: async () => (await api.get('/assessment/history')).data,
}

export const scoreAPI = {
  score: async (correct, user_answer) => (await api.post('/score', { correct, user_answer })).data,
}

export const evalAPI = {
  summary: async () => (await api.get('/eval/summary')).data,
  progression: async () => (await api.get('/assessment/progression')).data,
  report: async () => (await api.get('/assessment/report', {   // 교사·언어재활사용 결과지(I-9)
    params: { tz_offset_min: new Date().getTimezoneOffset() },
  })).data,
  // 축 C 공개 표준 자원(동구형이음 사전·난이도지수·지각공간·평가셋) — 연구·교육 활용용 내려받기
  resources: async () => (await api.get('/assessment/resources')).data,
  benchmark: async () => (await api.get('/assessment/benchmark')).data,
}

export const reviewAPI = {
  getDue: async () => (await api.get('/review/due')).data,
  removeDue: async (kind, ref) => (await api.delete('/review/item', { params: { kind, ref } })).data,
  answer: async (kind, ref, correct) => (await api.post('/review/answer', { kind, ref, correct })).data,
}

// 축 G 콘텐츠 사람검수(운영자용) — 생성 후보 승인/반려. 서버가 LIPLAB_REVIEW=1일 때만 열림.
export const contentReviewAPI = {
  candidates: async () => (await api.get('/admin/content/candidates')).data,
  review: async (kind, item, decision) => (await api.post('/admin/content/review', { kind, item, decision })).data,
}

// 축 E 조음 — 보이지 않는 조음(혀·조음위치) 가이드와 관찰 차원 교정
export const articulationAPI = {
  guide: async (text) => (await api.get('/articulation/guide', { params: { text } })).data,
  feedback: async (viseme, observed) => (await api.post('/articulation/feedback', { viseme, observed })).data,
}

// 개인정보 열람·삭제권(§4.9)
export const accountAPI = {
  exportData: async () => (await api.get('/account/data')).data,
  // 삭제·이메일 변경은 현재 비밀번호로 재인증한다(§4.9). 비밀번호 변경 응답의 access_token으로 이 기기 세션을 이어 간다.
  deleteAccount: async (password) => (await api.delete('/account', { params: { confirm: true }, data: { password } })).data,
  updateProfile: async (payload) => (await api.patch('/account/profile', payload)).data,
  changePassword: async (payload) => (await api.post('/account/password', payload)).data,
  // 학습 초기화 — 계정은 두고 학습 기록·XP·연속 학습·배치를 처음으로(공용 데모 계정은 403)
  resetLearning: async () => (await api.post('/account/learning-reset', null, { params: { confirm: true } })).data,
  // 파일럿(§4.7) — 진행 중일 때만 참여 코드 입력(운영자가 LIPLAB_PILOT=1로 켠다)
  pilotStatus: async () => (await api.get('/pilot/status')).data,
  pilotJoin: async (code) => (await api.post('/pilot/join', { code })).data,
}

// 발화(말하기) — 커리큘럼 6단계 + 녹음 채점·코칭.
export const speakAPI = {
  getCurriculum: async () => (await api.get('/speak/curriculum')).data,
  skip: async (stage) => (await api.post('/speak/skip', { stage })).data,   // 건너뛰기(80:6) — 잠긴 다음 단계 하나를 연다
  getStage: async (n) => (await api.get(`/speak/stage/${n}`)).data,
  getAnalysis: async () => (await api.get('/speak/analysis', { timeout: 30000 })).data,
  getReview: async () => (await api.get('/speak/review')).data,
  assess: async (target, blob, metrics = {}, opts = {}) => {
    const fd = new FormData()
    fd.append('target', target)
    fd.append('audio', blob, 'speech.webm')
    for (const k of ['loudness', 'pitch_range', 'duration', 'pitch_start', 'pitch_end']) {
      if (metrics[k] != null) fd.append(k, String(metrics[k]))
    }
    if (opts.stage != null) fd.append('stage', String(opts.stage))
    if (opts.drill) fd.append('drill', opts.drill)
    if (opts.review) fd.append('review', '1')
    if (opts.mouth_confidence != null) fd.append('mouth_confidence', String(opts.mouth_confidence))  // 웹캠 입모양 신뢰도(축 B AV융합)
    if (opts.mouth_track) fd.append('mouth_track', opts.mouth_track)  // 입모양 타임라인(축 B 구간별 보완, B-6)
    // FormData는 브라우저가 multipart 경계를 붙이도록 Content-Type을 비운다(인스턴스 기본 json 무효화).
    const res = await api.post('/speak/assess', fd, { headers: { 'Content-Type': undefined }, timeout: 60000 })
    return res.data
  },
}

// 음성구동 아바타(A4) — 실제 음성 → 52 블렌드셰이프 립싱크
export const avatarAPI = {
  audio2faceStatus: async () => (await api.get('/avatar/audio2face/status')).data,
  audio2face: async (blob) => {
    const fd = new FormData()
    fd.append('audio', blob, 'speech.webm')
    const res = await api.post('/avatar/audio2face', fd, {
      headers: { 'Content-Type': undefined }, timeout: 120000,
    })
    return res.data
  },
}

// 데모용 더미 학습 기록 시드(계정이 비어 있을 때만)
export const seedAPI = {
  seedDemo: async () => (await api.post('/seed-demo')).data,
}


export default api
