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
