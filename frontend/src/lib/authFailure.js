// 현재 세션의 토큰으로 보낸 요청만 만료 처리한다. 계정을 바꾸기 전 요청이 늦게 실패해도 새 계정을 지키고,
// 로그인 입력 오류는 Login 화면이 안내하도록 남긴다.
export function handleUnauthorized(error, session, reload) {
  if (error.response?.status !== 401 || !session.token) return
  const config = error.config
  if (!config || /(?:^|\/)auth\/(?:login|register|demo)(?:[/?#]|$)/.test(config.url || '')) return
  const headers = config.headers
  const authorization = headers?.get?.('Authorization') ?? headers?.Authorization ?? headers?.authorization
  if (authorization !== `Bearer ${session.token}`) return
  session.logout()
  reload()
}
