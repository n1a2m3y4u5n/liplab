import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { learningAPI } from '../api'
import useStore from '../store/useStore'
import AppShell from '../components/AppShell'

export default function Bookmarks() {
  const navigate = useNavigate()
  const setScenario = useStore((s) => s.setScenario)
  const [bookmarks, setBookmarks] = useState([])
  const [loading, setLoading] = useState(true)
  const [removing, setRemoving] = useState(null)

  useEffect(() => {
    learningAPI.getBookmarks().then(setBookmarks).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const remove = async (id) => {
    setRemoving(id)
    try {
      await learningAPI.removeBookmark(id)
      setBookmarks((prev) => prev.filter((b) => b.id !== id))
    } catch (e) {
      console.error(e)
    } finally {
      setRemoving(null)
    }
  }

  const practice = async (bm) => {
    // Create a mini-scenario with just this bookmarked sentence
    const scenario = {
      situation: bm.situation || '북마크',
      level: bm.level || 1,
      sentences: [bm.sentence],
      scenario_id: `bookmark_${bm.id}`,
    }
    setScenario(scenario, 'test')
    navigate('/practice')
  }

  return (
    <AppShell active="review" title="북마크한 문장" description="어려웠던 문장들을 다시 연습해보세요">
      <div className="w-full">
        {loading ? (
          <div className="flex justify-center py-24">
            <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
          </div>
        ) : bookmarks.length === 0 ? (
          <div className="card text-center py-16">
            <p className="text-4xl mb-3">☆</p>
            <p className="text-gray-500 font-medium">북마크한 문장이 없습니다.</p>
            <p className="text-sm text-gray-400 mt-1">연습 중 어려운 문장에 ☆ 버튼을 눌러 저장하세요.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-primary mt-6">
              연습 시작하기
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">{bookmarks.length}개의 북마크된 문장</p>
            <AnimatePresence>
              {bookmarks.map((bm) => (
                <motion.div
                  key={bm.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className="card flex items-center gap-4"
                >
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gray-900 text-lg">{bm.sentence}</p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {bm.situation || '상황 미지정'} · 레벨 {bm.level}
                    </p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => practice(bm)}
                      className="px-3 py-1.5 text-sm rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors"
                    >
                      다시 연습
                    </button>
                    <button
                      onClick={() => remove(bm.id)}
                      disabled={removing === bm.id}
                      className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-500 hover:border-red-300 hover:text-red-500 transition-colors"
                    >
                      {removing === bm.id ? '...' : '삭제'}
                    </button>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </AppShell>
  )
}
