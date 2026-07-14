import { motion, AnimatePresence } from 'framer-motion'

/**
 * 촉각 얼굴 모형 '시뮬레이터' — 아두이노가 재현하는 동작을 웹에서 동시에 시각화.
 * sim: { jaw(0~20), lip(0/1), voicing(0/1), airflow('none'|'plosive'|'fricative'), label, idx } | null
 *  - 턱: 입 벌림 높이   - 입술: 원순/평순 형태   - 진동: 목 하부 파동+얼굴 미세 흔들림
 *  - 기류: 파열=강한 버스트 퍼프 / 마찰=지속 스트림
 * 하드웨어 미연결 상태에서도 동작을 미리 보여줄 수 있다(심사·데모용).
 */
export default function TactileFaceSim({ sim, showLabel = true }) {
  const active = !!sim
  const jaw = sim?.jaw ?? 0
  const lip = sim?.lip ?? 0
  const voicing = sim?.voicing ?? 0
  const airflow = sim?.airflow ?? 'none'

  const open = 6 + (Math.min(jaw, 20) / 20) * 54   // 입 벌림(px)
  const lipRx = lip ? 22 : 40                       // 원순=좁게, 평순=넓게

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 220 270" className="w-full" style={{ maxWidth: 280 }}>
        <motion.g
          animate={voicing ? { x: [-1.6, 1.6, -1.6] } : { x: 0 }}
          transition={voicing ? { duration: 0.08, repeat: Infinity } : { duration: 0.2 }}>
          {/* 얼굴 */}
          <ellipse cx="110" cy="118" rx="82" ry="104" fill="#fde3c8" stroke="#e6c3a3" strokeWidth="2" />
          {/* 눈 */}
          <ellipse cx="80" cy="100" rx="7" ry="9" fill="#4b5563" />
          <ellipse cx="140" cy="100" rx="7" ry="9" fill="#4b5563" />
          {/* 코 */}
          <path d="M110 116 l-8 26 h16 z" fill="#eab892" />
          {/* 입술(바깥) */}
          <motion.ellipse cx="110" cy="182" fill="#d98a86" stroke="#c96f6a" strokeWidth="2"
            animate={{ rx: lipRx, ry: open / 2 + 9 }} transition={{ duration: 0.12 }} />
          {/* 입 안(열림) */}
          <motion.ellipse cx="110" cy="182" fill="#7a2e2b"
            animate={{ rx: Math.max(6, lipRx - 12), ry: open / 2 }} transition={{ duration: 0.12 }} />
        </motion.g>

        {/* 기류 퍼프 — 음소마다 재생(key=idx) */}
        <AnimatePresence>
          {active && airflow === 'plosive' && (
            <motion.circle key={`p${sim.idx}`} cx="110" r="7" fill="#93c5fd"
              initial={{ opacity: 0.85, scale: 0.4, cy: 200 }}
              animate={{ opacity: 0, scale: 2.8, cy: 245 }}
              transition={{ duration: 0.35 }} />
          )}
          {active && airflow === 'fricative' && [0, 1, 2, 3].map((i) => (
            <motion.circle key={`f${sim.idx}-${i}`} cx={104 + i * 4} r="3.5" fill="#bfdbfe"
              initial={{ opacity: 0.7, cy: 200 }}
              animate={{ opacity: 0, cy: 248 }}
              transition={{ duration: 0.5, delay: i * 0.09, repeat: 1 }} />
          ))}
        </AnimatePresence>

        {/* 진동(성대) — 목 부근 파동 */}
        {voicing === 1 && (
          <>
            <motion.path d="M84 240 q26 13 52 0" stroke="#a855f7" strokeWidth="2.5" fill="none"
              animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 0.22, repeat: Infinity }} />
            <motion.path d="M76 250 q34 15 68 0" stroke="#c084fc" strokeWidth="2" fill="none"
              animate={{ opacity: [0.2, 0.8, 0.2] }} transition={{ duration: 0.22, repeat: Infinity, delay: 0.08 }} />
          </>
        )}
      </svg>

      {showLabel && <div className="text-3xl font-bold text-primary-600 h-9">{active ? sim.label : ''}</div>}

      {/* 액추에이터 상태 칩 — 하드웨어가 받는 값 그대로 */}
      <div className="grid grid-cols-4 gap-2 w-full mt-2">
        <Chip title="턱" value={`${jaw}°`} on={active} accent="primary" />
        <Chip title="입술" value={lip ? '원순' : '평순'} on={active} accent="primary" />
        <Chip title="진동" value={voicing ? 'ON' : 'off'} on={voicing === 1} accent="purple" />
        <Chip title="기류" value={airflow === 'plosive' ? '파열' : airflow === 'fricative' ? '마찰' : '없음'}
          on={active && airflow !== 'none'} accent="blue" />
      </div>
    </div>
  )
}

function Chip({ title, value, on, accent }) {
  const color = !on ? 'bg-gray-50 text-gray-400'
    : accent === 'purple' ? 'bg-purple-100 text-purple-700'
      : accent === 'blue' ? 'bg-blue-100 text-blue-700' : 'bg-primary-50 text-primary-700'
  return (
    <div className={`rounded-lg py-1.5 text-center transition-colors ${color}`}>
      <p className="text-[10px] opacity-70">{title}</p>
      <p className="font-bold text-sm">{value}</p>
    </div>
  )
}
