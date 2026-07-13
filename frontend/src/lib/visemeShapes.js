/**
 * 한국어 Viseme → 3D 모프타깃(blendshape) 정밀 매핑
 *
 * 기존 매핑은 Oculus OVR 비심(viseme_aa, viseme_PP 등) 15종만 사용해
 * 입모양이 거칠었다. 모델(realistic_face.glb)에는 ARKit 표준 52 블렌드셰이프
 * (jawOpen, mouthPucker, mouthFunnel, mouthClose, mouthStretch 등)가 함께
 * 들어 있으므로, 이를 조합해 한국어 조음(調音) 위치를 훨씬 정확히 표현한다.
 *
 * 가중치는 0~1. 모델에 없는 키는 렌더러가 자동으로 건너뛴다.
 * 이 매핑은 한국어 조음음성학(입술 원순/개방/폐쇄, 혀 위치)에 근거한다.
 */
// 설계 원칙: 이 모델의 Oculus viseme_* 모프는 메시를 왜곡시켜 사용하지 않는다.
// 대신 표준 ARKit 블렌드셰이프(jawOpen, mouthPucker, mouthFunnel, mouthSmile,
// mouthStretch, mouthPress 등)만 조합해 한국어 조음 위치를 표현한다.
// 기본(rest) 자세가 이미 '입술을 편하게 다문' 상태이므로, 각 viseme은
// 여기서 필요한 만큼만 벌리거나(jawOpen) 오므리거나(pucker) 당긴다(smile).
export const VISEME_BLENDSHAPES = {
  // 1) 양순음 ㅂ/ㅃ/ㅍ/ㅁ — 두 입술을 확실히 붙여 막고 살짝 압착
  //    mouthClose를 넣어 앞이 열린 모음(아→마) 뒤에도 입술이 반드시 닫히게 한다.
  1: { mouthClose: 0.18, mouthPressLeft: 0.22, mouthPressRight: 0.22, mouthRollLower: 0.1, mouthRollUpper: 0.1 },

  // 2) 개방모음 ㅏ/ㅐ — 턱을 크게 내려 입을 벌림 (한국어에서 가장 개방적인 모음)
  2: { jawOpen: 0.5, mouthLowerDownLeft: 0.1, mouthLowerDownRight: 0.1 },

  // 3) 전설모음 ㅣ/ㅔ/ㅖ — 입술을 좌우로 당겨 옆으로 벌림(미소형)
  3: { mouthSmileLeft: 0.5, mouthSmileRight: 0.5, jawOpen: 0.08, mouthStretchLeft: 0.15, mouthStretchRight: 0.15 },

  // 4) 원순모음 ㅗ/ㅛ/ㅜ/ㅠ — 입술을 둥글게 오므려 앞으로 내밈
  //    순수 pucker 0.95는 과장된 뽀뽀 모양 → funnel을 섞어 자연스러운 원순을 만든다.
  4: { mouthPucker: 0.55, mouthFunnel: 0.4, jawOpen: 0.06 },

  // 5) 중설모음 ㅓ/ㅕ/ㅡ — 중립에서 살짝 벌림
  5: { jawOpen: 0.2 },

  // 6) 치경음 ㄷ/ㄸ/ㅌ/ㄴ/ㄹ/ㅅ/ㅆ — 혀끝이 보이도록 입을 조금 더 벌림
  //    혀끝은 윗잇몸으로 올라가므로 tongueOut(밖으로 내밀기)은 쓰지 않는다.
  6: { jawOpen: 0.22 },

  // 7) 연구개음 ㄱ/ㄲ/ㅋ/ㅇ — 혀 뒤가 보이도록 입을 조금 더 벌림
  7: { jawOpen: 0.22 },

  // 8) 성문음 ㅎ — 숨을 내쉬며 입을 열고 이완
  8: { jawOpen: 0.24 },

  // 9) 이중모음 ㅘ/ㅙ/ㅚ/ㅝ/ㅞ/ㅟ/ㅢ — 원순+개방이 섞인 중간 형태
  9: { jawOpen: 0.16, mouthPucker: 0.28 },

  // 10) 경구개음 ㅈ/ㅉ/ㅊ — 혓날이 보이도록 살짝 더 벌리고 옆으로 조금 당김
  10: { jawOpen: 0.18, mouthSmileLeft: 0.18, mouthSmileRight: 0.18 },

  // 11~13) 동시조음 전환 프레임 — 다음 조음으로 가는 약한 중간 상태
  11: { mouthPressLeft: 0.12, mouthPressRight: 0.12 },  // → 양순
  12: { jawOpen: 0.07 },                                 // → 치경
  13: { jawOpen: 0.09 },                                 // → 연구개

  // 14) 휴지기 · 15) 중립 — 편하게 다문 기본 자세
  14: {},
  15: {},
}

/**
 * 위 매핑에서 실제 사용하는 모프타깃 키의 합집합.
 * 매 프레임 이 키들만 목표값으로 보간(lerp)하고 나머지는 건드리지 않는다.
 */
export const ACTIVE_MORPH_KEYS = Array.from(
  new Set(Object.values(VISEME_BLENDSHAPES).flatMap((shape) => Object.keys(shape)))
)

/**
 * 혀 전용 모프타깃 매핑 (mesh-scoped) — 혀(tongue01) 메시에만 적용된다.
 *
 * viseme_DD(혀끝을 윗잇몸으로), viseme_kk(혀 뒤를 연구개로)는 이 모델의
 * 얼굴 메시에도 존재해 얼굴을 왜곡시키므로, 렌더러가 이 키들은 '혀 메시에만'
 * 적용한다. 덕분에 얼굴은 ARKit 블렌드셰이프로 자연스럽게 유지하면서
 * 혀의 조음(調音) 위치만 정확히 표현할 수 있다.
 *
 * 참고: 독화에서 혀는 대부분 가려져 살짝만 보이므로 값은 과하지 않게 잡는다.
 * (예전 tongueOut=혀를 입 밖으로 내미는 잘못된 표현은 사용하지 않는다.)
 */
// tongueOut(혀끝 전방)은 '혀 메시에만' 적용되므로 얼굴을 왜곡하지 않고,
// 소량(≤0.2)이라 입 밖으로 나오지 않고 앞니 뒤에서 혀끝이 톡 보이는 정도다.
// viseme_DD(혀끝 위로) + tongueOut(앞으로)를 함께 써서 움직임을 뚜렷하게 만든다.
export const VISEME_TONGUE = {
  // 6) 치경음 ㄷ/ㄸ/ㅌ/ㄴ/ㄹ/ㅅ/ㅆ — 혀끝을 윗잇몸에 대고 앞으로 살짝 내밈
  6: { viseme_DD: 1.0, tongueOut: 0.18 },

  // 7) 연구개음 ㄱ/ㄲ/ㅋ/ㅇ — 혀 뒤가 연구개로 올라감 (뒤쪽이라 다소 덜 보임)
  7: { viseme_kk: 0.75 },

  // 10) 경구개음 ㅈ/ㅉ/ㅊ — 혓날이 경구개 부근 (viseme_DD로 근사)
  10: { viseme_DD: 0.6, tongueOut: 0.1 },

  // 12) 치경 전환 프레임 — 혀끝을 미리 올려 다음 조음으로 이어지게
  12: { viseme_DD: 0.55, tongueOut: 0.12 },
}

/**
 * 혀 전용 매핑에서 사용하는 모프타깃 키의 합집합. (혀 메시에만 lerp 적용)
 */
export const ACTIVE_TONGUE_KEYS = Array.from(
  new Set(Object.values(VISEME_TONGUE).flatMap((shape) => Object.keys(shape)))
)
