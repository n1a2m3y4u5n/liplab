import axios from 'axios'
import useStore from './store/useStore'
import { createInflight } from './lib/sharedRequest'

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

// 데스크톱(1280px 이상)에서는 오른쪽 패널(AppShell Rail)과 페이지가 같은 순간 같은 요약을 따로 불러, /analysis·/profile은
// overview를, /tasks·/review는 due를 두 번 받았다(overview 한 번에 서버 약 0.2초, 이벤트 2.4만 건 합성 DB). 진행 중인 약속만
// 나눠 2회 → 1회로 줄인다. TTL은 두지 않는다(복습·초기화 직후 오래된 값을 보이지 않게). 키에 토큰을 넣어 계정끼리 섞지 않는다.
const inflight = createInflight()
const sharedGet = (name, fetcher) => inflight(`${name}:${useStore.getState().token || ''}`, fetcher)

// Request interceptor: attach JWT token
api.interceptors.request.use(
  (config) => {
    const token = useStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 기록을 바꾸는 요청이 나가면 진행 중인 약속을 잊는다. 그 뒤에 부른 쪽이 바뀌기 전 응답을 나눠 받지 않게 한다.
    if ((config.method || 'get').toLowerCase() !== 'get') inflight.clear()
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

  // progressData.practice_only(선택): 정답을 본 뒤의 다시 풀기·자막 힌트 뒤 제출이면 true를 넣는다.
  // 서버가 점수만 주고 3단계 숙달·XP에는 넣지 않는다. 다른 호출은 이 필드 없이 그대로 보낸다.
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
  // 대화 되묻기 '다른 말로'(docs/curriculum-roadmap.md 1-4). 바꾼 문장이 없으면 { text: null }
  rephraseTurn: async (text, situation, level) => (await api.post('/conversation/rephrase', { text, situation, level })).data,

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
  // 분석 탭 요약·배지(backend/analytics.py). 날짜·연속 학습은 브라우저 시간대 기준. 패널과 페이지가 진행 중인 요청을 나눠 쓴다.
  getAnalysisOverview: () => {
    const tz = new Date().getTimezoneOffset()
    return sharedGet(`overview:${tz}`, async () => (await api.get('/analysis/overview', {
      params: { tz_offset_min: tz },
    })).data)
  },

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
  // options(선택): 화면에 보여 준 보기를 보인 순서대로. 서버가 시행 기록(TrialAttempt.options)에 남겨 '그 보기가 있었을 때 고른 비율'로
  // 혼동을 잰다(docs/confusion-pair-serving.md 5.4). 보내지 않아도 채점은 같다.
  // meta(선택, 파일럿 로그 P0): { rt_from_onset_ms, talker, hint_used } — lib/trialMeta. 기록만 하고 채점에는 쓰지 않는다
  submitRecognition: async (viseme_id, chosen_id, options, meta) =>
    (await api.post('/curriculum/recognition', { viseme_id, chosen_id, ...(options ? { options } : {}), ...(meta || {}) })).data,
  // 1단계 '같은지 다른지'(AX) 문항: 먼저·나중 음절과 고른 답('same' | 'different'). 정답은 서버가 입모양 무리로 정하고,
  // 이 답은 시행 기록·XP에만 남고 1단계 숙달에는 들어가지 않는다(docs/mastery-ewma.md 11.9절)
  submitRecognitionAx: async (a, b, chosen, options, meta) =>
    (await api.post('/curriculum/recognition-ax', { a, b, chosen, ...(options ? { options } : {}), ...(meta || {}) })).data,
  // 뜻 없는 말 짝 맞추기(C10, docs/nonsense-pairing.md): 지금 목록·블록, 답 제출. 시행 기록에만 남고 단계 숙달·복습·XP에는 들어가지 않는다.
  // options = 보인 도형 자리(낱말로, 보인 순서). 오늘 분량을 넘거나 블록이 맞지 않으면 409
  getNonsenseSession: async () => (await api.get('/nonsense/session')).data,
  submitNonsense: async (set_id, block, word, chosen, options, meta) =>
    (await api.post('/nonsense/answer', { set_id, block, word, chosen, ...(options ? { options } : {}), ...(meta || {}) })).data,
  getWords: async () => (await api.get('/curriculum/words')).data,
  // 3단계 문장 4지선다 오답 보기(레슨 밖·음절 수가 가까운 문장). exclude = 이번 레슨 문장들
  getSentenceOptions: async (sentence, exclude) => (await api.post('/curriculum/sentence-options', { sentence, exclude })).data,
  // speed: 답하기 전에 본 실제 재생 속도(학습자 선택 × 적응 감속). 1.0 미만 정답은 숙달에 0.5로 들어간다(docs/mastery-ewma.md 7절)
  // mode 'typed': 주관식(chosen = 입력한 글). 서버가 정답·'입모양은 맞음'·오답으로 채점해 verdict로 돌려준다(계획 1-2)
  // probe(선택): 짝 탐색 문항이면 /curriculum/words probes[].probe(자리·target·read·대비 단어). 숙달에는 보통 문항과 똑같이 들어간다
  submitWord: async (word, correct, chosen, speed, mode, options, probe, meta) =>
    (await api.post('/curriculum/word-answer', {
      word, correct, chosen, speed, ...(mode ? { mode } : {}), ...(options ? { options } : {}), ...(probe ? { probe } : {}),
      ...(meta || {}),
    })).data,
  getClosure: async () => (await api.get('/curriculum/closure')).data,
  submitClosure: async (item_id, chosen, options, meta) =>
    (await api.post('/curriculum/closure-answer', { item_id, chosen, ...(options ? { options } : {}), ...(meta || {}) })).data,
  // 2단계 레슨 속 문맥 문항(계획 1-3). 숙달에는 넣지 않고 시행 기록·취약 입모양에만 남는다
  submitContext: async (item_id, chosen, options, meta) =>
    (await api.post('/curriculum/context-answer', { item_id, chosen, ...(options ? { options } : {}), ...(meta || {}) })).data,
  confusionMatrix: async () => (await api.get('/curriculum/confusion-matrix')).data,
  getRecommendedLevel: async () => (await api.get('/curriculum/recommended-level')).data,
  getNext: async () => (await api.get('/curriculum/next')).data,
  getCues: async (text, { focus = false, maxCues = null } = {}) => (await api.get('/cues', {
    params: { text, ...(focus ? { focus: true } : {}), ...(maxCues && maxCues > 0 ? { max_cues: maxCues } : {}) },
  })).data,
  // session(선택): 웹캠 조음 교정 세션 요약 { gap_start, gap_end, n_samples } (축 E-9)
  recordMouth: async (viseme_id, score, session = {}) => (await api.post('/curriculum/mouth-attempt', { viseme_id, score, ...session })).data,
  getArticulationTrend: async () => (await api.get('/analysis/articulation')).data,
  getMultiConversation: async (speakers = 2, turns = 6, scene, level) => (await api.get('/conversation/multi', { params: { speakers, turns, ...(scene ? { scene } : {}), ...(level ? { level } : {}) } })).data,
  recordMultiConversation: async (payload) => (await api.post('/conversation/multi/result', payload)).data,
  getPlacement: async (n = 8, form = null) => (await api.get('/assessment/placement', { params: form ? { n, form } : { n } })).data,
  scorePlacement: async (items, responses, form = 'placement') => (await api.post('/assessment/score', { items, responses, form })).data,
  nextPlacementItem: async (asked, responses, n = 12) => (await api.post('/assessment/placement/next', { asked, responses, n })).data,
  getAssessmentHistory: async () => (await api.get('/assessment/history')).data,
  // 지연 유지 검사(C7): 상태(state none|waiting|due|done)·문항(볼 때만)·채점. 사전·사후 비교에는 섞이지 않는다
  getRetention: async () => (await api.get('/assessment/retention')).data,
  getRetentionItems: async () => (await api.get('/assessment/retention/items')).data,
  scoreRetention: async (responses) => (await api.post('/assessment/retention/score', { responses })).data,
  // 숙달 지연 탐침(C16): 이 레슨에 섞을 탐침(정답 없음, 서버가 비율 상한을 적용)과 답 기록. 숙달·복습·XP에는 들어가지 않는다
  getMasteryProbes: async (lessonLen, used = 0) => (await api.get('/curriculum/mastery-probes', { params: { lesson_len: lessonLen, used } })).data,
  answerMasteryProbe: async (id, chosen) => (await api.post('/curriculum/mastery-probe-answer', { id, chosen })).data,
  // 레슨별 정신적 노력(C14): { session_id, lesson_kind, stage, rating?, response?, n_items, accuracy }
  lessonEffort: async (payload) => (await api.post('/lesson/effort', payload)).data,
}

export const scoreAPI = {
  // practiceOnly(선택): 문장을 미리 본 뒤의 답('무슨 말인지 보기')이면 true. 서버가 점수만 주고 4단계 숙달·XP에는 넣지 않는다.
  score: async (correct, user_answer, { practiceOnly = false } = {}) => (await api.post('/score', {
    correct, user_answer, ...(practiceOnly ? { practice_only: true } : {}),
  })).data,
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
  // 패널과 페이지(과제·복습)가 진행 중인 요청을 나눠 쓴다(위 sharedGet)
  getDue: () => sharedGet('due', async () => (await api.get('/review/due')).data),
  removeDue: async (kind, ref) => (await api.delete('/review/item', { params: { kind, ref } })).data,
  // extra: { answer_mode: 'choice'|'typed', speed }. 보기를 고른 정답·1.0배 미만 정답은 서버가 품질 3으로 센다(backend/srs.py 머리말)
  answer: async (kind, ref, correct, extra = {}) => (await api.post('/review/answer', { kind, ref, correct, ...extra })).data,
}

// 과제 탭(오늘의 과제·특별 과제): 목록·목표·보상은 서버(daily_tasks.py)가 정하고 판정한다.
// claim은 달성했지만 받지 않은 보상을 모두 받는다(무엇을 달성했는지 보내지 않는다). 응답에 과제 목록이 함께 온다.
export const tasksAPI = {
  get: () => sharedGet('tasks', async () => (await api.get('/tasks')).data),
  claim: async () => (await api.post('/tasks/claim')).data,
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

// 청인 예비 파일럿(P3) 검사 묶음 — 파일럿 참여자만(서버가 403으로 막는다). docs/pilot/battery.md
export const batteryAPI = {
  status: async () => (await api.get('/pilot/battery/status')).data,
  start: async (label, layer) => (await api.post('/pilot/battery/start', { label, layer })).data,
  answer: async (payload) => (await api.post('/pilot/battery/answer', payload)).data,
  finish: async (payload) => (await api.post('/pilot/battery/finish', payload)).data,
  // 영상·음성은 로그인 머리글이 필요해 blob으로 받아 주소를 만든다(path는 서버가 준 '/pilot/battery/...')
  blob: async (path) => (await api.get(path, { responseType: 'blob', timeout: 60000 })).data,
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
    for (const k of ['loudness', 'pitch_range', 'duration', 'pitch_start', 'pitch_end', 'pitch_ref', 'pitch_final', 'pitch_frames', 'voiced_duration']) {
      if (metrics[k] != null) fd.append(k, String(metrics[k]))
    }
    if (opts.stage != null) fd.append('stage', String(opts.stage))
    if (opts.drill) fd.append('drill', opts.drill)
    if (opts.review) fd.append('review', '1')
    if (opts.probe) fd.append('probe', '1')   // 낱말 속 소리 확인(모음·자음 단계, 계획 2-5)
    if (opts.mouth_confidence != null) fd.append('mouth_confidence', String(opts.mouth_confidence))  // 웹캠 입모양 신뢰도(축 B AV융합)
    if (opts.mouth_track) fd.append('mouth_track', opts.mouth_track)  // 입모양 타임라인(축 B 구간별 보완, B-6)
    // FormData는 브라우저가 multipart 경계를 붙이도록 Content-Type을 비운다(인스턴스 기본 json 무효화).
    const res = await api.post('/speak/assess', fd, { headers: { 'Content-Type': undefined }, timeout: 60000 })
    return res.data
  },
}

// 소리 듣기(청능훈련) 트랙 — backend listen_curriculum, docs/auditory-training-design.md
// 모의 청취 모드(인공와우 모의, 청인 파일럿)면 기록에 sim: 'ci'를 붙인다(lib/listenAudio의 setSimMode)
const withSim = (body) => {
  const sim = globalThis.__liplabListenSim
  return sim ? { ...body, sim } : body
}
export const listenAPI = {
  getCurriculum: async () => (await api.get('/listen/curriculum')).data,
  skip: async (stage) => (await api.post('/listen/skip', { stage })).data,
  getStage: async (n) => (await api.get(`/listen/stage/${n}`)).data,
  answer: async (body) => (await api.post('/listen/answer', withSim(body))).data,
  ling: async (body) => (await api.post('/listen/ling', withSim(body))).data,
  testStart: async (body = {}) => (await api.post('/listen/test/start', body)).data,
  testAnswer: async (body) => (await api.post('/listen/test/answer', withSim(body))).data,
  summary: async () => (await api.get('/listen/summary')).data,
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

// 소리 조건(C17)·듣기 트랙 소리. lookup은 미리 합성한 서버 음성의 주소·길이·음절 시각을 준다. 없는 글·목소리면 서버가 404
// {available:false}로 답하고, 여기서는 null을 돌려준다(화면은 '소리 준비 중'을 보이고 레슨을 잇는다).
// voice를 생략하면 기본 목소리(소리 조건용). 목소리 목록은 voices().
export const soundAPI = {
  lookup: async (text, voice) => {
    try {
      return (await api.get('/sound', { params: { text, ...(voice ? { voice } : {}) }, timeout: 20000 })).data
    } catch (e) {
      if (e?.response?.status === 404) return null
      throw e
    }
  },
  voices: async () => (await api.get('/sound/voices')).data,
  // 답한 뒤 '소리와 함께 다시 보기'를 틀었다는 기록. kind 'trial'(1·2단계·문맥 추론, target = 서버에 기록된 목표) | 'sentence'(3단계)
  logReplay: async (kind, target, itemType) =>
    (await api.post('/sound/replay', { kind, target, ...(itemType ? { item_type: itemType } : {}) })).data,
  noiseUrl: (ext = 'ogg') => `/api/sound/noise/babble.${ext}`,
}

// 데모용 더미 학습 기록 시드(계정이 비어 있을 때만)
export const seedAPI = {
  seedDemo: async () => (await api.post('/seed-demo')).data,
}


export default api
