/**
 * 입술 너머 확장 조음 단서 (축 K) — 순수 함수.
 *
 * 웹캠 채점(D)은 입술을 중심으로 본다. 그러나 말은 얼굴 전체에 조음 흔적을 남긴다 —
 * 턱 개폐, 볼 팽창, 콧방울 움직임 등. 이 모듈은 MediaPipe blendshape에서 입술 외 얼굴
 * 신호를 뽑아, 입 밖으로 잘 안 드러나는 자질(비음·압력)의 '상관 신호'를 보조적으로 추정한다.
 *
 * 계획서 §3.11: 이 미세 신호는 조명·개인차에 민감하므로 판정이 아니라 보조 단서로만 쓴다
 * (J의 시각 기호를 뒷받침하거나 B의 융합 입력으로). 근거: 얼굴 전체 조음 흔적 관찰,
 * 입술 주변 넓은 영역을 쓰는 립리딩 연구, Eulerian Video Magnification(미세움직임 확대).
 */
const _clamp01 = (x) => Math.max(0, Math.min(1, x))

// 입술 '너머'의 얼굴 blendshape 차원(MediaPipe FaceLandmarker 카테고리명)
export const FACE_KEYS = [
  'jawOpen', 'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight',
  'noseSneerLeft', 'noseSneerRight', 'mouthPressLeft', 'mouthPressRight',
]

export const FACE_SIGNAL_LABELS = {
  jaw_open: '턱 벌림',
  nasal: '코 울림(비음)',
  cheek_pressure: '볼 압력(파열·긴장)',
}

/**
 * 얼굴 전체 신호(0~1)를 추정한다. 판정이 아니라 보조 단서다.
 *   · jaw_open: 턱 개구도 — 개방/폐쇄의 큰 흐름
 *   · nasal: 콧방울 움직임에서 추정한 비음 상관(약함)
 *   · cheek_pressure: 볼 팽창·입술 압력에서 추정한 파열/긴장 상관
 */
export function faceSignals(bs) {
  bs = bs || {}
  const avg = (a, b) => ((bs[a] || 0) + (bs[b] || 0)) / 2
  return {
    jaw_open: _clamp01(bs.jawOpen || 0),
    nasal: _clamp01(avg('noseSneerLeft', 'noseSneerRight') * 1.5),
    cheek_pressure: _clamp01((bs.cheekPuff || 0) * 1.2 + avg('mouthPressLeft', 'mouthPressRight') * 0.5),
  }
}

/** 신호 전체 활성도(얼굴이 얼마나 움직였는지) — 보조 신뢰도 판단용. */
export function faceActivity(bs) {
  const s = faceSignals(bs)
  return _clamp01((s.jaw_open + s.nasal + s.cheek_pressure) / 3)
}
