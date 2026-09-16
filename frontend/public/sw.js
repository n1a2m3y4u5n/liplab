/* LIPLAB 서비스워커 — 설치·앱셸 오프라인(계획서 트랙2 PWA).
 * 보수적 전략: API는 절대 캐시하지 않고, 페이지 이동은 네트워크 우선(끊기면 캐시 셸),
 * 정적 자산(JS/CSS/이미지/폰트)은 stale-while-revalidate. 버전 올리면 옛 캐시 정리. */
const CACHE = 'liplab-v1'
const SHELL = ['/', '/index.html', '/icon.svg', '/manifest.webmanifest']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (e) => {
  const req = e.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return          // 외부(모델·CDN 등)는 건드리지 않음
  if (url.pathname.startsWith('/api/')) return             // API는 캐시 금지(항상 네트워크)

  if (req.mode === 'navigate') {                           // 페이지 이동: 네트워크 우선 → 실패 시 셸
    e.respondWith(
      fetch(req).catch(() => caches.match(req).then((r) => r || caches.match('/index.html')))
    )
    return
  }
  // 정적 자산: 캐시 우선 + 백그라운드 갱신(stale-while-revalidate)
  e.respondWith(
    caches.match(req).then((cached) => {
      const fetching = fetch(req).then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(req, copy))
        }
        return res
      }).catch(() => cached)
      return cached || fetching
    })
  )
})
