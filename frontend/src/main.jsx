import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// 본문 글꼴 — Pretendard 가변 글꼴(유니코드 범위별로 필요한 조각만 받는다)
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import './index.css'

// Load optional web fonts after the first render without inline CSP handlers.
const webFonts = document.getElementById('web-fonts')
if (webFonts) {
  const applyFonts = () => { webFonts.media = 'all' }
  webFonts.addEventListener('load', applyFonts, { once: true })
  if (webFonts.sheet) applyFonts()
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// PWA 서비스워커 등록 — 프로덕션 빌드에서만(개발 중 캐시 혼선 방지).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}

// 새로 불러온 화면이 10초 동안 멀쩡하면 재로드 표시를 지운다. 안 지우면 같은 탭에서 두 번째 배포를 만났을 때
// 표시가 남아 새로고침하지 않고 오류 화면이 뜬다(F30). 바로 지우지 않는 것은 조각이 계속 없을 때 무한 새로고침을 막으려는 것이다.
window.addEventListener('load', () => {
  setTimeout(() => { try { sessionStorage.removeItem('liplab_chunk_reload') } catch { /* 무시 */ } }, 10000)
})

// 배포 뒤 열려 있던 옛 화면이 사라진 조각 파일을 못 받으면 한 번만 새로 불러온다(무한 새로고침 방지).
window.addEventListener('vite:preloadError', (e) => {
  // 연결이 끊기면 새로고침도 실패하므로 앱의 오류 화면을 그대로 남긴다.
  if (navigator.onLine === false) return
  try {
    if (sessionStorage.getItem('liplab_chunk_reload')) return
    sessionStorage.setItem('liplab_chunk_reload', '1')
    e.preventDefault()
    window.location.reload()
  } catch { /* 저장소 사용 불가면 기존 오류 화면에 맡긴다 */ }
})
