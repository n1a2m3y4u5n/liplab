import { useEffect, useState, useCallback } from 'react'
import { accountAPI, authAPI } from '../api'

const DEMO_EMAIL = 'demo@liplab.app'

/**
 * 접근성 설정(계획서 접근성/트랙2) — 청각장애·저시력 학습자를 위한 표시 옵션.
 * 글자 크게 / 고대비 / 모션 줄이기를 켜면 <html>에 클래스를 붙이고 localStorage에 저장한다.
 * opt-in이라 기본 디자인은 그대로 두고, 필요한 사용자만 강화된 표시를 받는다.
 */
const OPTS = [
  { key: 'large', cls: 'a11y-large', label: '글자 크게', desc: '본문·버튼 글자를 키웁니다' },
  { key: 'contrast', cls: 'a11y-contrast', label: '고대비', desc: '흐린 글자·경계를 진하게' },
  { key: 'reduce', cls: 'a11y-reduce-motion', label: '모션 줄이기', desc: '애니메이션·전환 최소화' },
]
const LS_KEY = 'liplab.a11y'

function load() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') } catch { return {} }
}
function apply(state) {
  const root = document.documentElement
  for (const o of OPTS) root.classList.toggle(o.cls, !!state[o.key])
}

export default function A11ySettings() {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState(load)
  const [isDemo, setIsDemo] = useState(true)  // 확인 전엔 안전하게 데모로 간주(내데이터 숨김)

  // 공용 데모 계정이면 개인정보 열람·삭제를 숨긴다(내려받기=방문자간 데이터 노출, 삭제=항상 403).
  useEffect(() => {
    let alive = true
    authAPI.getMe().then((u) => { if (alive) setIsDemo((u?.email || '') === DEMO_EMAIL) }).catch(() => {})
    return () => { alive = false }
  }, [])

  useEffect(() => { apply(state) }, [state])
  // 최초 마운트 시 저장값 적용(다른 탭·새로고침 대비)
  useEffect(() => { apply(load()) }, [])

  const toggle = useCallback((key) => {
    setState((s) => {
      const next = { ...s, [key]: !s[key] }
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)) } catch { /* 사생활 모드 등 무시 */ }
      return next
    })
  }, [])

  // 개인정보 열람권 — 내 데이터를 JSON 파일로 내려받기
  const exportData = useCallback(async () => {
    try {
      const d = await accountAPI.exportData()
      const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'liplab-내데이터.json'; a.click()
      URL.revokeObjectURL(url)
    } catch { alert('내려받기에 실패했어요.') }
  }, [])

  // 개인정보 삭제권 — 삭제는 현재 비밀번호 재확인이 필요해(§4.9) 프로필 → 계정 설정 한 곳에서 한다.
  const deleteAccount = useCallback(() => { window.location.href = '/profile' }, [])

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="접근성 설정 열기"
        className="fixed bottom-4 left-4 z-40 grid h-11 w-11 place-items-center rounded-full bg-slate-900 text-white shadow-lg hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-400"
        title="접근성 설정"
      >
        <span aria-hidden className="text-lg">♿</span>
      </button>
      {open && (
        <div role="dialog" aria-label="접근성 설정"
          className="fixed bottom-16 left-4 z-40 w-64 rounded-2xl border border-gray-200 bg-white p-3 shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-bold text-gray-900">접근성 설정</span>
            <button onClick={() => setOpen(false)} aria-label="닫기" className="text-gray-400 hover:text-gray-700">✕</button>
          </div>
          <div className="space-y-1.5">
            {OPTS.map((o) => (
              <button key={o.key} type="button" onClick={() => toggle(o.key)}
                role="switch" aria-checked={!!state[o.key]}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition ${state[o.key] ? 'border-sky-300 bg-sky-50' : 'border-gray-200 bg-white hover:bg-gray-50'}`}>
                <span>
                  <span className="block text-sm font-semibold text-gray-800">{o.label}</span>
                  <span className="block text-[11px] text-gray-500">{o.desc}</span>
                </span>
                <span aria-hidden className={`ml-2 grid h-5 w-9 shrink-0 items-center rounded-full px-0.5 transition ${state[o.key] ? 'bg-sky-500' : 'bg-gray-300'}`}>
                  <span className={`h-4 w-4 rounded-full bg-white shadow transition ${state[o.key] ? 'translate-x-4' : ''}`} />
                </span>
              </button>
            ))}
          </div>

          {/* 개인정보 열람·삭제권(§4.9) — 공용 데모 계정에는 노출하지 않음(방문자 간 데이터 격리) */}
          {!isDemo && (
          <div className="mt-3 border-t border-gray-100 pt-2.5">
            <p className="mb-1.5 text-xs font-semibold text-gray-500">내 데이터</p>
            <button type="button" onClick={exportData}
              className="mb-1.5 flex w-full items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-left text-sm font-medium text-gray-700 hover:bg-gray-50">
              ⬇ 내 학습 데이터 내려받기 <span className="text-[11px] text-gray-400">(JSON)</span>
            </button>
            <button type="button" onClick={deleteAccount}
              className="flex w-full items-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-left text-sm font-medium text-rose-600 hover:bg-rose-50">
              🗑 계정·데이터 삭제 <span className="text-[11px] text-rose-400">(프로필 → 계정 설정)</span>
            </button>
            <p className="mt-1.5 text-[11px] leading-snug text-gray-400">웹캠 영상은 기기 안에서만 처리돼요. 음성은 채점할 때만 서버로 보내 메모리에서 처리하고 저장하지 않으며, 전사문·음성 지표는 학습 기록으로 저장돼요.</p>
          </div>
          )}
        </div>
      )}
    </>
  )
}
