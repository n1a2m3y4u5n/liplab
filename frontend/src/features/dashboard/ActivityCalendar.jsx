import { useMemo } from 'react'

// ── GitHub 스타일 활동 캘린더 ─────────────────────────────────────────────────
export default function ActivityCalendar({ data }) {
  const today = new Date()
  // 오늘 포함 90일
  const days = useMemo(() => {
    const arr = []
    for (let i = 89; i >= 0; i--) {
      const d = new Date(today)
      d.setDate(today.getDate() - i)
      const key = d.toISOString().slice(0, 10)
      arr.push({ key, count: data[key] || 0 })
    }
    return arr
  }, [data])

  const getColor = (count) => {
    if (count === 0) return 'bg-gray-100'
    if (count <= 2)  return 'bg-green-200'
    if (count <= 5)  return 'bg-green-400'
    return 'bg-green-600'
  }

  // 7행 열 배열로 변환 (일요일 시작)
  const startPad = new Date(days[0].key).getDay() // 0=Sun
  const cells = [...Array(startPad).fill(null), ...days]

  return (
    <div>
      <div className="flex gap-0.5 flex-wrap">
        {cells.map((cell, i) =>
          cell === null ? (
            <div key={`pad-${i}`} className="w-3.5 h-3.5" />
          ) : (
            <div
              key={cell.key}
              title={`${cell.key}: ${cell.count}문장`}
              className={`w-3.5 h-3.5 rounded-sm ${getColor(cell.count)} transition-colors cursor-default`}
            />
          )
        )}
      </div>
      <div className="flex items-center gap-1 mt-2 text-xs text-gray-400">
        <span>적음</span>
        {['bg-gray-100','bg-green-200','bg-green-400','bg-green-600'].map(c => (
          <div key={c} className={`w-3 h-3 rounded-sm ${c}`} />
        ))}
        <span>많음</span>
      </div>
    </div>
  )
}
