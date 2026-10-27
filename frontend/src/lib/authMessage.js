// 서버 오류 → 한국어 안내. FastAPI 422는 detail이 배열({loc, msg})이라 그대로 렌더하면 React가 깨진다.
const AUTH_ERR = {
  'Incorrect email or password': '이메일·비밀번호를 확인해 주세요.',
  'Email already registered': '이미 가입된 이메일이에요.',
  'Username already taken': '이미 쓰고 있는 사용자명이에요.',
}
export function authErrorMessage(detail, mode, error) {
  // 응답이 없거나(끊김·시간 초과) 서버 쪽 오류면 입력 탓이 아니므로 비밀번호를 의심하게 하지 않는다.
  if (error && !error.response) return error.code === 'ECONNABORTED' ? '응답이 너무 늦어요. 잠시 후 다시 시도해 주세요.' : '인터넷 연결을 확인하고 다시 시도해 주세요.'
  const status = error?.response?.status
  if (status === 429) return '시도가 너무 많아요. 잠시 후 다시 시도해 주세요.'
  if (status >= 500) return '서버에 문제가 있어요. 잠시 후 다시 시도해 주세요.'
  if (typeof detail === 'string') return AUTH_ERR[detail] || detail
  if (Array.isArray(detail)) {
    const field = detail.map((d) => (Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null)).find(Boolean)
    if (field === 'password') {
      const long = detail.find((d) => /72바이트/.test(d?.msg || ''))
      if (long) return '비밀번호는 72바이트(한글 약 24자, 영문 72자)까지 쓸 수 있어요.'
    }
    if (field === 'password') return '비밀번호는 6자 이상 입력해주세요.'
    if (field === 'username') return '사용자명은 2~50자로 입력해주세요.'
    if (field === 'email') return '이메일 형식을 확인해 주세요.'
  }
  return mode === 'login' ? '이메일·비밀번호를 확인해 주세요.' : '가입에 실패했어요.'
}
