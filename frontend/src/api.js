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
    if (error.response?.status === 401 && !url.includes('/auth/demo')) {
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
  register: async (email, username, password) => {
    const response = await api.post('/auth/register', {
      email,
      username,
      password,
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
  getBookmarks: async () => {
    const response = await api.get('/bookmarks')
    return response.data
  },
  addBookmark: async (sentence, situation, level) => {
    const response = await api.post('/bookmarks', { sentence, situation, level })
    return response.data
  },
  removeBookmark: async (id) => {
    const response = await api.delete(`/bookmarks/${id}`)
    return response.data
  },

  // Analysis
  getAnalysis: async () => {
    const response = await api.get('/analysis', { timeout: 60000 })
    return response.data
  },
  resetAnalysis: async () => {
    const response = await api.delete('/analysis/reset')
    return response.data
  },

  // Calendar (activity heatmap)
  getCalendar: async () => {
    const response = await api.get('/calendar')
    return response.data  // { 'YYYY-MM-DD': count }
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
  setTrack: async (track) => (await api.post('/curriculum/track', { track })).data,
  getVisemeLessons: async () => (await api.get('/curriculum/viseme-lessons')).data,
  submitRecognition: async (viseme_id, chosen_id) =>
    (await api.post('/curriculum/recognition', { viseme_id, chosen_id })).data,
  getWords: async () => (await api.get('/curriculum/words')).data,
  submitWord: async (word, correct) => (await api.post('/curriculum/word-answer', { word, correct })).data,
  getClosure: async () => (await api.get('/curriculum/closure')).data,
  getRecommendedLevel: async () => (await api.get('/curriculum/recommended-level')).data,
}

export const scoreAPI = {
  score: async (correct, user_answer) => (await api.post('/score', { correct, user_answer })).data,
}

export const reviewAPI = {
  getDue: async () => (await api.get('/review/due')).data,
  answer: async (kind, ref, correct) => (await api.post('/review/answer', { kind, ref, correct })).data,
}

export default api
