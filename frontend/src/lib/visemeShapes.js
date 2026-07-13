/**
 * 한국어 Viseme → 3D 모프타깃(blendshape) 정밀 매핑
 * ------------------------------------------------------------------
 * 이 매핑은 실제 모델(realistic_face.glb)의 모프타깃을 **직접 감사(audit)** 하여
 * 존재가 확인된 ARKit 블렌드셰이프만 사용해 작성했다.
 *
 * base 메시(66개 모프)에 확인된 ARKit 셰이프(발췌):
 *   jawOpen, mouthClose, mouthFunnel, mouthPucker,
 *   mouthPressLeft/Right, mouthRollUpper/Lower,
 *   mouthSmileLeft/Right, mouthStretchLeft/Right,
 *   mouthUpperUpLeft/Right, mouthLowerDownLeft/Right,
 *   mouthShrugUpper, tongueOut ...
 *
 * 설계 원칙
 * 1) Oculus viseme_*(viseme_aa 등) 모프는 이 모델에서 메시를 과하게 왜곡시켜
 *    쓰지 않고, 표준 ARKit 셰이프만 조합한다.
 * 2) 기본(rest) 자세가 이미 '입술을 편하게 다문' 상태이므로, 각 viseme은
 *    거기서 필요한 만큼만 벌리고(jawOpen) / 오므리고(pucker·funnel) /
 *    당기고(smile·stretch) / 닫는다(mouthClose).
 * 3) jawOpen 은 base·teeth·tongue 세 메시에 공통 존재하여 턱·치아·혀가 함께
 *    움직인다. 반면 입술 셰이프(pucker/funnel/smile 등)는 base 메시 전용이다.
 *    → '벌림'은 jawOpen, '입술 모양'은 ARKit 립 셰이프로 역할을 분담한다.
 *
 * 이전 매핑 대비 개선점
 *   · 양순음(1): mouthClose 를 추가해 두 입술을 확실히 붙임(ㅁ/ㅂ/ㅃ/ㅍ 폐쇄 강화).
 *   · 원순모음(4)·이중모음(9): mouthFunnel + mouthPucker 를 결합해 앞으로
 *     내민 둥근 'O' 형태를 정확히 표현(기존 pucker 단독 → 납작한 오므림 문제 해소).
 *   · 치경음(6): 조음상 혀끝이 잇몸 뒤에 있어 밖으로 나오지 않는데도 쓰였던
 *     tongueOut 을 제거하고, 윗니가 살짝 보이도록 mouthUpperUp 으로 교정.
 *   · 전설모음(3)·개방모음(2): mouthUpperUp/stretch 를 더해 벌림·좌우 확장을 명확화.
 *
 * 가중치는 0~1. 모델에 없는 키는 렌더러가 자동으로 건너뛴다.
 */
export const VISEME_BLENDSHAPES = {
  // 1) 양순음 ㅁ/ㅂ/ㅃ/ㅍ — 두 입술을 붙여 확실히 막고 살짝 압착
  1: { mouthClose: 0.35, mouthPressLeft: 0.22, mouthPressRight: 0.22, mouthRollLower: 0.12, mouthRollUpper: 0.12 },

  // 2) 개방모음 ㅏ/ㅐ/ㅑ/ㅒ — 턱을 크게 내리고 윗입술도 살짝 올려 크게 벌림
  2: { jawOpen: 0.5, mouthLowerDownLeft: 0.12, mouthLowerDownRight: 0.12, mouthUpperUpLeft: 0.06, mouthUpperUpRight: 0.06 },
  // 3) 전설모음 ㅣ/ㅔ/ㅖ — 입술을 좌우로 당겨 옆으로 벌리고 윗니가 살짝 보임
  3: { mouthSmileLeft: 0.45, mouthSmileRight: 0.45, mouthStretchLeft: 0.2, mouthStretchRight: 0.2, jawOpen: 0.1, mouthUpperUpLeft: 0.08, mouthUpperUpRight: 0.08 },

  // 4) 원순모음 ㅗ/ㅛ/ㅜ/ㅠ — 입술을 둥글게 오므려 앞으로 내민 'O'
  //  이 모델은 jawOpen이 조금만 커져도 윗니가 드러나 원순 특성을 해친다.
  //  → jaw는 최소(치아 감춤), funnel로 앞으로 내민 protrusion을 강조하고
  //    pucker는 살짝 낮춰 중앙에 작은 둥근 개구부가 보이게 한다.
  4: { mouthFunnel: 0.62, mouthPucker: 0.48, jawOpen: 0.05 },
  // 5) 중설모음 ㅓ/ㅕ/ㅡ — 중립에서 살짝 벌림
  5: { jawOpen: 0.22, mouthFunnel: 0.06 },

  // 6) 치경음 ㄷ/ㄸ/ㅌ/ㄴ/ㄹ/ㅅ/ㅆ — 이가 가깝게 살짝 벌리고 윗니가 보임
  6: { jawOpen: 0.12, mouthUpperUpLeft: 0.1, mouthUpperUpRight: 0.1, mouthShrugUpper: 0.05 },

  // 7) 연구개음 ㄱ/ㄲ/ㅋ/ㅇ — 입을 조금 벌림(조음은 안쪽이라 외형은 중립)
  7: { jawOpen: 0.18 },
  // 8) 성문음 ㅎ — 숨을 내쉬며 입을 열고 이완
  8: { jawOpen: 0.26 },

  // 9) 이중모음 ㅘ/ㅙ/ㅚ/ㅝ/ㅞ/ㅟ/ㅢ — 원순+개방이 섞인 중간 형태
  //  v4(꽉 둥근)와 v2(활짝 개방)의 중간: funnel/pucker로 둥근 내밈을 유지하되
  //  jaw는 절제해(치아 과다 노출 방지) '둥글게 살짝 벌린' 형태로.
  9: { jawOpen: 0.16, mouthFunnel: 0.38, mouthPucker: 0.32 },

  // 10) 경구개음 ㅈ/ㅉ/ㅊ — 입술을 살짝 내밀고 옆으로 조금 당김
  10: { jawOpen: 0.12, mouthFunnel: 0.14, mouthSmileLeft: 0.12, mouthSmileRight: 0.12 },
  // 11~13) 동시조음 전환 프레임 — 다음 조음으로 가는 약한 중간 상태
  11: { mouthClose: 0.18, mouthPressLeft: 0.1, mouthPressRight: 0.1 }, // → 양순
  12: { jawOpen: 0.08 },                                              // → 치경
  13: { jawOpen: 0.1 },                                               // → 연구개

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
