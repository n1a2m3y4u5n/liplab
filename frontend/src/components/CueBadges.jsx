import { useState, useEffect } from 'react'
import { curriculumAPI } from '../api'

/**
 * 시각 증강 오버레이(고도화 축 J) — 입모양이 같은 동구형이음을, 입술 밖으로 드러나지
 * 않는 조음 자질에 대응하는 최소 기호로 구분해 준다. 기호는 임의가 아니라 자질에 대응한다.
 *   기식(격음) ≈ 바람 / 긴장(경음) ◆ 힘 / 울림(비음) ∿ 코울림. 평음은 기준이라 기호 없음.
 */
const CUE_STYLE = {
  aspirated: { sym: '≈', label: '기식(바람)', cls: 'bg-sky-100 text-sky-700 border-sky-200' },
  tense: { sym: '◆', label: '긴장(힘)', cls: 'bg-amber-100 text-amber-700 border-amber-200' },
  nasal: { sym: '∿', label: '울림(코)', cls: 'bg-violet-100 text-violet-700 border-violet-200' },
}

export function CueLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
      {Object.entries(CUE_STYLE).map(([k, s]) => (
        <span key={k} className="inline-flex items-center gap-1">
          <span className={`inline-flex h-4 w-4 items-center justify-center rounded border text-[10px] font-bold ${s.cls}`}>{s.sym}</span>
          {s.label}
        </span>
      ))}
      <span className="text-gray-400">평음은 기준(기호 없음)</span>
    </div>
  )
}

export default function CueBadges({ text }) {
  const [cues, setCues] = useState(null)
  useEffect(() => {
    let on = true
    if (!text) return undefined
    curriculumAPI.getCues(text)
      .then((d) => { if (on) setCues(d.cues || []) })
      .catch(() => { if (on) setCues([]) })
    return () => { on = false }
  }, [text])

  const bySyl = {}
  ;(cues || []).forEach((c) => {
    bySyl[c.syllable_index] = bySyl[c.syllable_index] || []
    bySyl[c.syllable_index].push(c)
  })

  return (
    <span className="inline-flex items-end gap-0.5 rounded-lg border border-gray-200 bg-white px-2 py-1">
      {[...text].map((ch, i) => (
        <span key={i} className="inline-flex flex-col items-center">
          <span className="flex h-4 items-center gap-0.5">
            {(bySyl[i] || []).map((c, j) => (
              <span
                key={j}
                title={CUE_STYLE[c.cue]?.label}
                className={`inline-flex h-4 w-4 items-center justify-center rounded border text-[10px] font-bold ${CUE_STYLE[c.cue]?.cls || ''}`}
              >
                {CUE_STYLE[c.cue]?.sym}
              </span>
            ))}
          </span>
          <span className="text-lg font-semibold text-gray-800">{ch}</span>
        </span>
      ))}
    </span>
  )
}
