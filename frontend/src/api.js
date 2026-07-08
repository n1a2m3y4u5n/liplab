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
    if (error.response?.status === 401) {
      // Token expired or invalid
      useStore.getState().logout()

      // Redirect to login if not already there
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
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
}

export default api
