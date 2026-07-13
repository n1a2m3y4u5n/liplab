import { useEffect, useMemo, useState } from 'react'
import AvatarVRM from '../components/AvatarVRM'
import MouthFallback2D from '../components/MouthFallback2D'
import { VISEME_BLENDSHAPES } from '../lib/visemeShapes'

/**
 * Viseme 검사 페이지 (개발용, 비인증)
 * ------------------------------------------------------------------
 * 15종 viseme의 3D 입모양과 2D SVG 폴백을 나란히 렌더링해
 * 조음(폐쇄/개방/원순/전설/치경)이 정확한지 육안으로 검증한다.
 *
 * URL 쿼리 `?v=N` (1~15)로 특정 viseme을 지정할 수 있어
 * 스크린샷 자동 수집·회귀 검증에 사용한다. `?v=all`이면 15개를 격자로.
 */
const VISEME_LABELS = {
  1: '양순음 ㅂㅃㅍㅁ',
  2: '개방모음 ㅏㅐㅑㅒ',
  3: '전설모음 ㅣㅔㅖ',
  4: '원순모음 ㅗㅛㅜㅠ',
  5: '중설모음 ㅓㅕㅡ',
  6: '치경음 ㄷㄸㅌㄴㄹㅅㅆ',
  7: '연구개음 ㄱㄲㅋㅇ',
  8: '성문음 ㅎ',
  9: '이중모음 ㅘㅙㅚㅝㅞㅟㅢ',
  10: '경구개음 ㅈㅉㅊ',
  11: '전환→양순',
  12: '전환→치경',
  13: '전환→연구개',
  14: '휴지기',
  15: '중립(rest)',
}

const IDS = Array.from({ length: 15 }, (_, i) => i + 1)

function useQueryViseme() {
  const [v, setV] = useState(() => {
    const p = new URLSearchParams(window.location.search).get('v')
    if (p === 'all') return 'all'
    const n = parseInt(p, 10)
    return n >= 1 && n <= 15 ? n : 1
  })
  return [v, setV]
}

function WeightTable({ id }) {
  const shape = VISEME_BLENDSHAPES[id] || {}
  const entries = Object.entries(shape)
  return (
    <div style={{ fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6 }}>
      {entries.length === 0 ? (
        <span style={{ color: '#94a3b8' }}>(rest — 모프 없음)</span>
      ) : (
        entries.map(([k, val]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 150, color: '#334155' }}>{k}</span>
            <div style={{ flex: 1, background: '#e2e8f0', borderRadius: 4, height: 8, maxWidth: 160 }}>
              <div style={{ width: `${val * 100}%`, background: '#6366f1', height: 8, borderRadius: 4 }} />
            </div>
            <span style={{ width: 36, textAlign: 'right', color: '#475569' }}>{val.toFixed(2)}</span>
          </div>
        ))
      )}
    </div>
  )
}

function Cell({ id, big }) {
  const size = big ? 420 : 200
  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden', background: '#fff' }}>
      <div style={{ padding: '8px 12px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        <div style={{ fontWeight: 700, fontSize: big ? 18 : 13 }}>#{id} — {VISEME_LABELS[id]}</div>
      </div>
      <div style={{ display: 'flex', gap: 0 }}>
        {/* 3D */}
        <div style={{ width: size, height: size, background: 'linear-gradient(#1e293b,#0f172a)' }}>
          <AvatarVRM visemeId={id} />
        </div>
        {/* 2D fallback */}
        <div style={{ width: size, height: size, borderLeft: '1px solid #e2e8f0' }}>
          <MouthFallback2D visemeId={id} />
        </div>
      </div>
      {big && (
        <div style={{ padding: 12, borderTop: '1px solid #e2e8f0' }}>
          <WeightTable id={id} />
        </div>
      )}
    </div>
  )
}

export default function DevViseme() {
  const [v, setV] = useQueryViseme()

  // keep URL in sync so screenshots are addressable
  useEffect(() => {
    const url = new URL(window.location.href)
    url.searchParams.set('v', String(v))
    window.history.replaceState(null, '', url)
  }, [v])

  const isAll = v === 'all'

  return (
    <div style={{ minHeight: '100vh', background: '#f1f5f9', padding: 24 }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>LIPLAB · Viseme 검사기</h1>
        <p style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>
          왼쪽 = 3D(realistic_face.glb), 오른쪽 = 2D SVG 폴백. 두 표현이 같은 조음을 나타내야 한다.
        </p>

        {/* selector */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
          {IDS.map((id) => (
            <button
              key={id}
              onClick={() => setV(id)}
              style={{
                padding: '6px 10px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
                border: '1px solid ' + (v === id ? '#4f46e5' : '#cbd5e1'),
                background: v === id ? '#4f46e5' : '#fff',
                color: v === id ? '#fff' : '#334155', fontWeight: v === id ? 700 : 400,
              }}
            >
              {id}
            </button>
          ))}
          <button
            onClick={() => setV('all')}
            style={{
              padding: '6px 12px', borderRadius: 8, fontSize: 13, cursor: 'pointer',
              border: '1px solid ' + (isAll ? '#4f46e5' : '#cbd5e1'),
              background: isAll ? '#4f46e5' : '#fff', color: isAll ? '#fff' : '#334155',
              fontWeight: isAll ? 700 : 400,
            }}
          >
            전체 격자
          </button>
        </div>

        {isAll ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(420px,1fr))', gap: 16 }}>
            {IDS.map((id) => <Cell key={id} id={id} />)}
          </div>
        ) : (
          <Cell id={v} big />
        )}
      </div>
    </div>
  )
}
