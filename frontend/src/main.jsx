import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

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

// 배포 뒤 열려 있던 옛 화면이 사라진 조각 파일을 못 받으면 한 번만 새로 불러온다(무한 새로고침 방지).
window.addEventListener('vite:preloadError', (e) => {
  try {
    if (sessionStorage.getItem('liplab_chunk_reload')) return
    sessionStorage.setItem('liplab_chunk_reload', '1')
    e.preventDefault()
    window.location.reload()
  } catch { /* 저장소 사용 불가면 기존 오류 화면에 맡긴다 */ }
})
