/** 로그인 화면 전환에도 공유한 내부 주소를 유지한다. */
export function loginDestination(location) {
  const candidate = location.state?.loginReturnTo || location.pathname + location.search + location.hash
  if (typeof candidate !== 'string' || !candidate.startsWith('/') || candidate.startsWith('//') || /[\\\r\n]/.test(candidate)) return '/'
  const path = candidate.split(/[?#]/)[0]
  return ['/', '/login', '/signup'].includes(path) ? '/' : candidate
}
