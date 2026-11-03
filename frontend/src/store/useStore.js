import { clearCheckpoints } from '../lib/lessonCheckpoint'
import { flushTrack, usageHeaders } from '../lib/track'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { clearSignExplored } from '../lib/badges'
import { clearUserKeys } from '../lib/localDataKeys'
import { clearCalibration } from '../lib/mouthScore'
import { clearAllAnswers } from '../lib/learnerProfile'

/**
 * 계정마다 다른 브라우저 저장값을 지운다(로그아웃·학습 초기화). 공용 기기에서 다음 사람에게 넘어가지 않게 한다.
 * 수어 탐험 배지는 서버 기록이 없어 브라우저가 판정하고(lib/badges.js), liplab_onboarded는 예전 온보딩 완료 표시다
 * (지금은 서버 배치 여부로 판단해 읽지 않는다). 접근성 설정·수어 안내를 본 여부는 기기 설정이라 남긴다.
 */
export function clearUserLocalData() {
  clearSignExplored()
  clearCheckpoints()
  clearCalibration()   // 얼굴 보정값(호출하는 곳이 없어 로그아웃 뒤에도 남던 값)
  clearAllAnswers()    // 학습자 답(보청기·인공와우·청력 손실 시기)의 메모리 사본
  clearUserKeys()      // 위 값과 듣기 설정·화자·소리 조건 등 사용자 값 키 전부
  try { localStorage.removeItem(`liplab_last_track:${useStore.getState().user?.id ?? 'guest'}`) } catch {}
  try { localStorage.removeItem('liplab_onboarded') } catch { /* 저장소 차단 시 무시 */ }
}

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

      // Clear auth state on logout. 이 계정의 연습 세션(메모리)·통계 캐시·계정별 브라우저 저장값도 함께 지운다
      // (토큰 만료로 풀린 경우도 같다. 다음에 로그인하는 사람이 앞사람의 시나리오·배지를 이어받지 않게).
      logout: () => {
        try {
          const token = get().token
          void flushTrack(true)
          if (token) void fetch('/api/auth/logout', { method: 'POST', headers: { ...usageHeaders(), Authorization: `Bearer ${token}` }, keepalive: true }).catch(() => {})
        } catch { /* Ignore telemetry errors. */ }
        clearUserLocalData()
        get().resetPractice()
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          statistics: null,
        })
      },

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
        currentScenario: state.currentScenario,
        currentSentence: state.currentSentence,
        currentSentenceIndex: state.currentSentenceIndex,
        practiceMode: state.practiceMode,
      }),
    }
  )
)

export default useStore
