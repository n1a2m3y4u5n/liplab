import { useState, useEffect } from 'react'
import { curriculumAPI, accountAPI } from '../api'
import useStore from '../store/useStore'

// 파일럿 기호 켬·끔(J-12) — 기호 없이 학습하는 집단이면 서버가 기호 목록을 비워 주고(/api/cues), 화면은 범례와
// 웹캠 울림 기호도 숨긴다. 로그인한 계정마다 한 번만 묻는다. 값은 true(켬)·false(끔)·null(아직 모름·조회 실패).
// 범례는 null이면 보이고(기호 자체는 서버가 막는다), 웹캠 울림 기호는 true일 때만 보인다(연구 조건을 흐리지 않게).
const _cueFlag = { token: undefined, promise: null }
export function useCuesEnabled() {
  const token = useStore((s) => s.token)
  const [on, setOn] = useState(null)
  useEffect(() => {
    let alive = true
    if (!token) { setOn(true); return undefined }
    if (_cueFlag.token !== token || !_cueFlag.promise) {
      _cueFlag.token = token
      _cueFlag.promise = accountAPI.pilotStatus().then((s) => s?.cues !== false)
        .catch(() => { _cueFlag.promise = null; return null })   // 실패는 기억하지 않고 다음에 다시 묻는다
    }
    const p = _cueFlag.promise
    if (p) p.then((v) => { if (alive) setOn(v) })
    return () => { alive = false }
  }, [token])
  return on
}

/**
 * 시각 증강 오버레이(고도화 축 J) — 입모양이 같은 동구형이음을, 입술 밖으로 드러나지
 * 않는 조음 자질에 대응하는 최소 SVG 기호로 구분해 준다. 기호는 임의가 아니라 자질에 대응한다.
 *   기식(격음) 바람 / 긴장(경음) 채운마름모 / 울림(비음) 물결. 평음은 기준이라 기호 없음.
 * 숙달도가 오르면 백엔드가 strength를 낮춰 기호가 점진적으로 흐려진다(페이딩).
 */
const CUE_META = {
  aspirated: { label: '기식(바람)', color: '#0284c7', bg: 'bg-sky-50 border-sky-200' },
  tense: { label: '긴장(힘)', color: '#b45309', bg: 'bg-amber-50 border-amber-200' },
  nasal: { label: '울림(코)', color: '#7c3aed', bg: 'bg-violet-50 border-violet-200' },
}

/** 자질별 SVG 글리프(16x16). 색은 currentColor. */
export function CueGlyph({ cue, size = 14 }) {
  const color = CUE_META[cue]?.color || '#666'
  const common = { width: size, height: size, viewBox: '0 0 16 16', fill: 'none', stroke: color }
  if (cue === 'aspirated') {
    // 바람(기식) — 새어 나가는 공기 흐름
    return (
      <svg {...common} strokeWidth="1.6" strokeLinecap="round">
        <path d="M2 5 h7 a2 2 0 1 0 -2 -2" />
        <path d="M2 8.5 h9 a2 2 0 1 1 -2 2" />
        <path d="M2 12 h5" />
      </svg>
    )
  }
  if (cue === 'nasal') {
    // 울림(비음) — 코울림 물결
    return (
      <svg {...common} strokeWidth="1.7" strokeLinecap="round">
        <path d="M1.5 8 q 2 -4 3.5 0 t 3.5 0 t 3.5 0" />
        <path d="M1.5 11.5 q 2 -4 3.5 0 t 3.5 0 t 3.5 0" opacity="0.55" />
      </svg>
    )
  }
  // 긴장(경음) — 힘을 준 채운 마름모
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill={color} stroke="none">
      <polygon points="8,1.5 14.5,8 8,14.5 1.5,8" />
    </svg>
  )
}

export function CueLegend() {
  const cuesOn = useCuesEnabled()
  if (cuesOn === false) return null
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
      {Object.entries(CUE_META).map(([k, s]) => (
        <span key={k} className="inline-flex items-center gap-1">
          <span className={`inline-flex h-5 w-5 items-center justify-center rounded border ${s.bg}`}><CueGlyph cue={k} /></span>
          {s.label}
        </span>
      ))}
      <span className="text-gray-400">평음은 기준(기호 없음)</span>
    </div>
  )
}

export default function CueBadges({ text, showControls = false }) {
  const [cues, setCues] = useState(null)
  // 축 J 조절: focus=약한 표적 음소에만 기호(지식추적 연동, 서버가 판단) / maxCues=기호 과다 상한(0=무제한)
  const [focus, setFocus] = useState(false)
  const [maxCues, setMaxCues] = useState(0)
  useEffect(() => {
    let on = true
    if (!text) return undefined
    // 슬라이더 연속 조작 시 요청 폭주 방지 — 250ms 디바운스
    const timer = setTimeout(() => {
      curriculumAPI.getCues(text, { focus, maxCues })
        .then((d) => { if (on) setCues(d.cues || []) })
        .catch(() => { if (on) setCues([]) })
    }, 200)
    return () => { on = false; clearTimeout(timer) }
  }, [text, focus, maxCues])

  const bySyl = {}
  ;(cues || []).forEach((c) => {
    bySyl[c.syllable_index] = bySyl[c.syllable_index] || []
    bySyl[c.syllable_index].push(c)
  })

  const badges = (
    <span className="inline-flex items-end gap-0.5 rounded-lg border border-gray-200 bg-white px-2 py-1">
      {[...text].map((ch, i) => (
        <span key={i} className="inline-flex flex-col items-center">
          <span className="flex h-5 items-center gap-0.5">
            {(bySyl[i] || []).map((c, j) => (
              <span
                key={j}
                title={`${CUE_META[c.cue]?.label}${c.strength != null && c.strength < 1 ? ' · 익어가는 중' : ''}`}
                style={{ opacity: c.strength ?? 1 }}
                className={`inline-flex h-5 w-5 items-center justify-center rounded border ${CUE_META[c.cue]?.bg || ''}`}
              >
                <CueGlyph cue={c.cue} />
              </span>
            ))}
          </span>
          <span className="text-lg font-semibold text-gray-800">{ch}</span>
        </span>
      ))}
    </span>
  )

  if (!showControls) return badges

  return (
    <span className="inline-flex flex-col gap-1.5">
      {badges}
      <span className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-gray-500">
        <label className="inline-flex cursor-pointer items-center gap-1.5" title="아직 약한 음소에만 기호를 남깁니다(개인 학습기록 기반).">
          <input type="checkbox" checked={focus} onChange={(e) => setFocus(e.target.checked)} className="h-3 w-3 accent-violet-600" />
          표적 음소 집중
        </label>
        <label className="inline-flex items-center gap-1.5" title="화면에 동시에 뜨는 기호 수를 제한해 과다를 막습니다.">
          최대 기호
          <input type="range" min="0" max="8" value={maxCues} onChange={(e) => setMaxCues(Number(e.target.value))} className="h-1 w-20 accent-violet-600" />
          <span className="w-8 tabular-nums text-gray-600">{maxCues === 0 ? '무제한' : maxCues}</span>
        </label>
      </span>
    </span>
  )
}
