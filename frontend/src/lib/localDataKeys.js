// 로그아웃·학습 초기화 때 브라우저에서 지울 '사용자 값' 저장 키(F4, 11/03 검토).
// 보청기·인공와우 종류와 이득 dB, 청력 손실 시기(학습자 답), 얼굴 보정값, 화자·소리 조건, 무의미어 사용 시간 같은 건강·개인 값이라
// 공용 기기에서 다음 사람에게 남지 않게 한다. 접근성 설정(liplab.a11y)·소리 끔(liplab_mute)·안내를 본 여부·기기 ID는 기기 설정이라 남긴다
// (기기 ID는 계측 범위를 사람이 정하는 항목이라 건드리지 않는다).
export const USER_LOCAL_EXACT_KEYS = [
  'liplab_listen_settings',          // 듣기 설정: 보청기·인공와우, 이득 dB
  'liplab_mouth_calibration_v2',     // 얼굴 보정값
  'liplab_mouth_calibration_v1',
  'liplab_talker_lessons',           // 레슨 화자 기록
  'liplab_onboarded',
  'liplab.retentionPrompt.dismissedOn',
]
export const USER_LOCAL_KEY_PREFIXES = [
  'liplab_learner_info:',            // 학습자 답(청력 손실 시기 등)
  'liplab_sound_condition:',         // 소리 조건 선택
  'liplab.nonsense.ms.',             // 무의미어 하루 사용 시간
  'liplab_last_track:',
]

/** 저장소에 있는 모든 키 중 지울 것만 골라 준다. */
export function userLocalKeysToClear(allKeys) {
  return [...allKeys].filter((k) => USER_LOCAL_EXACT_KEYS.includes(k) || USER_LOCAL_KEY_PREFIXES.some((p) => k.startsWith(p)))
}

/** storage(기본 localStorage)에서 위 키를 지운다. 저장소를 못 쓰면 조용히 넘어간다. */
export function clearUserKeys(storage = globalThis.localStorage) {
  try {
    const keys = []
    for (let i = 0; i < storage.length; i++) keys.push(storage.key(i))
    for (const k of userLocalKeysToClear(keys)) storage.removeItem(k)
  } catch { /* 저장소 차단 시 무시 */ }
}
