/**
 * 카메라·마이크(getUserMedia, MediaRecorder) 오류를 짧은 한국어 안내로 바꾼다.
 *
 * 예전에는 어떤 오류든 '권한을 허용해 주세요'라고만 보여, 장치가 없거나(NotFoundError) 다른 앱이 쓰는 중이거나
 * (NotReadableError) https가 아닌 주소(안전하지 않은 컨텍스트)일 때도 권한 탓으로 안내했다.
 *
 * kind: 'camera' | 'mic'
 */
export function mediaErrorMessage(err, kind = 'camera') {
  const dev = kind === 'mic' ? '마이크' : '카메라'
  // 안전하지 않은 컨텍스트(http 주소)에는 navigator.mediaDevices 자체가 없어 TypeError로 온다
  if (typeof window !== 'undefined' && window.isSecureContext === false) {
    return `https 주소에서만 ${dev}를 쓸 수 있어요.`
  }
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return `이 브라우저에서는 ${dev}를 쓸 수 없어요.`
  }
  switch (err?.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'SecurityError':
      return `${dev} 권한이 막혀 있어요. 브라우저에서 ${dev} 권한을 허용해 주세요.`
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return `연결된 ${dev}를 찾지 못했어요. ${dev}가 연결돼 있는지 확인해 주세요.`
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return `${dev}를 켤 수 없어요. 다른 앱이나 탭이 ${dev}를 쓰고 있는지 확인해 주세요.`
    case 'NotSupportedError':
      return kind === 'mic' ? '이 브라우저에서는 녹음을 할 수 없어요.' : '이 브라우저에서는 카메라를 쓸 수 없어요.'
    default:
      return `${dev}를 쓸 수 없어요. ${dev} 연결과 권한을 확인해 주세요.`
  }
}
