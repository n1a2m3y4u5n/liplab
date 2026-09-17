import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Global state management using Zustand
 * Persists auth token and user data to localStorage
 */
const useStore = create(
  persist(
    (set, get) => ({
      // Authentication state
      user: null,
      token: null,
      isAuthenticated: false,

      // Set user and token after login/register
      setAuth: (user, token) => set({
        user,
        token,
        isAuthenticated: true
      }),

      // Update user data (e.g., after level up)
      updateUser: (updates) => set((state) => ({
        user: state.user ? { ...state.user, ...updates } : null
      })),

      // Clear auth state on logout
      logout: () => set({
        user: null,
        token: null,
        isAuthenticated: false
      }),

      // Practice session state
      currentScenario: null,
      currentSentence: null,
      currentSentenceIndex: 0,
      practiceMode: 'test', // 'study' | 'test'

      setScenario: (scenario, mode = 'test') => set({
        currentScenario: scenario,
        currentSentenceIndex: 0,
        currentSentence: scenario?.sentences?.[0] || null,
        practiceMode: mode,
      }),

      nextSentence: () => set((state) => {
        if (!state.currentScenario) return state

        const nextIndex = state.currentSentenceIndex + 1
        const sentences = state.currentScenario.sentences

        if (nextIndex >= sentences.length) {
          // End of scenario
          return {
            currentSentenceIndex: nextIndex,
            currentSentence: null
          }
        }

        return {
          currentSentenceIndex: nextIndex,
          currentSentence: sentences[nextIndex]
        }
      }),

      resetPractice: () => set({
        currentScenario: null,
        currentSentence: null,
        currentSentenceIndex: 0
      }),

      // UI state
      isLoading: false,
      setLoading: (loading) => set({ isLoading: loading }),

      // 대시보드 히어로 CTA 등 외부에서 상단 학습 메뉴 드롭다운을 열어달라는 요청
      navMenuRequest: null,
      requestNavMenu: (id) => set({ navMenuRequest: id }),
      clearNavMenuRequest: () => set({ navMenuRequest: null }),

      // Statistics cache
      statistics: null,
      setStatistics: (stats) => set({ statistics: stats }),
    }),
    {
      name: 'liplab-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

export default useStore
