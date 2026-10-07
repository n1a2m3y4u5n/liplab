/**
 * 한국어 Viseme → 3D 모프타깃(blendshape) 정밀 매핑
 * ------------------------------------------------------------------
 * 이 매핑은 실제 모델(realistic_face.glb)의 모프타깃을 **직접 감사(audit)** 하여
 * 존재가 확인된 ARKit 블렌드셰이프만 사용해 작성했다.
 *
 * 2026-09-21 모델 교체: Character Creator(CC) 두상. 얼굴(CC_Base_Body) 메시에
 * ARKit 52종이 전부 있고(jawOpen, mouthClose, mouthFunnel, mouthPucker,
 * mouthPress/Roll/Smile/Stretch/UpperUp/LowerDown L/R, mouthShrugUpper, tongueOut …),
 * 그 밖에 CC 고유 비심(V_*)·표정(Mouth_*, Brow_* …)·혀(T01~T11) 모프가 더 있다.
 *
 * 설계 원칙
 * 1) CC 고유 모프(V_Open, Mouth_Open 등)는 실측상 입술을 거의 움직이지 않아 쓰지 않고,
 *    표준 ARKit 셰이프만 조합한다(음성구동·웹캠 미러 프레임도 같은 52종을 쓴다).
 * 2) 기본(rest) 자세가 이미 '입술을 편하게 다문' 상태이므로, 각 viseme은
 *    거기서 필요한 만큼만 벌리고(jawOpen) / 오므리고(pucker·funnel) /
 *    당기고(smile·stretch) / 닫는다(mouthClose).
 * 3) 이 모델은 jawOpen '모프'가 피부를 움직이지 않는다(실측 −0.5mm). 벌림은 턱 뼈
 *    (CC_Base_JawRoot)가 담당하며 아래 이·혀·턱 피부가 함께 돈다 — 렌더러(AvatarVRM)가
 *    jawOpen 가중치를 뼈 회전각으로 옮긴다. 입술 셰이프는 그대로 모프로 적용한다.
 *    → '벌림'은 jawOpen(=턱 뼈), '입술 모양'은 ARKit 립 셰이프로 역할을 분담한다.
 *
 * ⚠️ 병합 이력 — 중복 키 정리(2026-09-07)
 *   이 객체에 viseme 1·2·4·6·7·10이 **각각 두 번 정의**되어 있었다. JS 객체 리터럴은
 *   뒤엣것이 앞엣것을 덮으므로, 앞의 정의(= 개발일지 2·6절의 ARKit 감사 + 브라우저 육안
 *   검증으로 확정한 값)가 코드에 남은 채 **실행되지 않고** 있었다. 예: 원순모음(4)의
 *   검증본 `funnel .62/pucker .48/jaw .05`가 이전 값 `pucker .55/funnel .4/jaw .06`으로
 *   덮여, 문서화된 튜닝이 화면에 반영되지 않았다.
 *
 *   두 정의는 서로 다른 축을 손대고 있어 실제로 병합 가능했다:
 *     · 앞 정의 = **입술 형태** (ARKit 감사·육안 검증 — mouthClose·mouthUpperUp·funnel 등)
 *     · 뒤 정의 = **턱 열림** (혀 렌더링[YMJ] 작업이 혀를 보이게 하려 jawOpen을 올림.
 *       올린 대상 6·7·10이 VISEME_TONGUE 보유 viseme과 정확히 일치하는 것이 근거)
 *   → 입술은 앞, 턱은 뒤를 취해 단일 정의로 합쳤다. 중복 재발은
 *     `visemeShapes.test.mjs`의 중복 키 검사가 막는다.
 *
 * 이전 매핑 대비 개선점
 *   · 양순음(1): mouthClose 를 추가해 두 입술을 확실히 붙임(ㅂ/ㅍ/ㅁ 폐쇄 강화).
 *   · 원순모음(4)·이중모음(9): mouthFunnel + mouthPucker 를 결합해 앞으로
 *     내민 둥근 'O' 형태를 정확히 표현(기존 pucker 단독 → 납작한 오므림 문제 해소).
 *   · 치경음(6): 조음상 혀끝이 잇몸 뒤에 있어 밖으로 나오지 않는데도 쓰였던
 *     tongueOut 을 제거하고, 윗니가 살짝 보이도록 mouthUpperUp 으로 교정.
 *   · 전설모음(3)·개방모음(2): mouthUpperUp/stretch 를 더해 벌림·좌우 확장을 명확화.
 *
 * 가중치는 0~1. 모델에 없는 키는 렌더러가 자동으로 건너뛴다.
 */
export const VISEME_BLENDSHAPES_V1 = {
  // 1) 양순음 ㅂ/ㅃ/ㅍ/ㅁ — 두 입술을 붙여 확실히 막고 살짝 압착.
  //    mouthClose로 앞이 열린 모음(아→마) 뒤에도 입술이 반드시 닫히게 한다.
  1: { mouthClose: 0.35, mouthPressLeft: 0.22, mouthPressRight: 0.22, mouthRollLower: 0.12, mouthRollUpper: 0.12 },

  // 2) 개방모음 ㅏ/ㅐ/ㅑ/ㅒ — 턱을 크게 내리고 윗입술도 살짝 올려 크게 벌림
  //    (한국어에서 가장 개방적인 모음)
  2: { jawOpen: 0.5, mouthLowerDownLeft: 0.12, mouthLowerDownRight: 0.12, mouthUpperUpLeft: 0.06, mouthUpperUpRight: 0.06 },

  // 3) 전설모음 ㅣ/ㅔ/ㅖ — 입술을 좌우로 당겨 옆으로 벌리고 윗니가 살짝 보임
  3: { mouthSmileLeft: 0.45, mouthSmileRight: 0.45, mouthStretchLeft: 0.2, mouthStretchRight: 0.2, jawOpen: 0.1, mouthUpperUpLeft: 0.08, mouthUpperUpRight: 0.08 },

  // 4) 원순모음 ㅗ/ㅛ/ㅜ/ㅠ — 입술을 둥글게 오므려 앞으로 내민 'O'
  //  이 모델은 jawOpen이 조금만 커져도 윗니가 드러나 원순 특성을 해친다.
  //  → jaw는 최소(치아 감춤), funnel로 앞으로 내민 protrusion을 강조하고
  //    pucker는 살짝 낮춰 중앙에 작은 둥근 개구부가 보이게 한다.
  //  (순수 pucker 0.95는 과장된 뽀뽀 모양이라 funnel을 섞어 자연스러운 원순으로.)
  4: { mouthFunnel: 0.62, mouthPucker: 0.48, jawOpen: 0.05 },

  // 5) 중설모음 ㅓ/ㅕ/ㅡ — 중립에서 살짝 벌림
  5: { jawOpen: 0.22, mouthFunnel: 0.06 },

  // 6) 치경음 ㄷ/ㄸ/ㅌ/ㄴ/ㄹ/ㅅ/ㅆ — 윗니가 보이게 하고, 혀끝(VISEME_TONGUE)이
  //    드러나도록 턱을 조금 더 연다. 혀끝은 윗잇몸으로 올라가므로 tongueOut은 쓰지 않는다.
  6: { jawOpen: 0.22, mouthUpperUpLeft: 0.1, mouthUpperUpRight: 0.1, mouthShrugUpper: 0.05 },

  // 7) 연구개음 ㄱ/ㄲ/ㅋ/ㅇ — 조음이 입 안쪽이라 외형은 중립에 가깝지만,
  //    혀 뒤(VISEME_TONGUE)가 보이도록 조금 더 벌린다.
  7: { jawOpen: 0.22 },

  // 8) 성문음 ㅎ — 숨을 내쉬며 입을 열고 이완
  8: { jawOpen: 0.26 },

  // 9) 이중모음 ㅘ/ㅙ/ㅚ/ㅝ/ㅞ/ㅟ/ㅢ — 원순+개방이 섞인 중간 형태
  //  v4(꽉 둥근)와 v2(활짝 개방)의 중간: funnel/pucker로 둥근 내밈을 유지하되
  //  jaw는 절제해(치아 과다 노출 방지) '둥글게 살짝 벌린' 형태로.
  9: { jawOpen: 0.16, mouthFunnel: 0.38, mouthPucker: 0.32 },

  // 10) 경구개음 ㅈ/ㅉ/ㅊ — 입술을 살짝 내밀고 옆으로 조금 당기며,
  //     혓날(VISEME_TONGUE)이 보이도록 조금 더 벌린다.
  10: { jawOpen: 0.18, mouthFunnel: 0.14, mouthSmileLeft: 0.12, mouthSmileRight: 0.12 },

  // 11~13) 동시조음 전환 프레임 — 다음 조음으로 가는 약한 중간 상태
  11: { mouthClose: 0.18, mouthPressLeft: 0.1, mouthPressRight: 0.1 }, // → 양순
  12: { jawOpen: 0.08 },                                              // → 치경
  13: { jawOpen: 0.1 },                                               // → 연구개

  // 14) 휴지기 · 15) 중립 — 편하게 다문 기본 자세
  14: {},
  15: {},
}

// ── V15(docs/viseme-calibration-2026-10.md): 538 탐색 절반 분포로 다시 맞춘 표 ──
// 오늘 아침 V2 감사(docs/avatar-validity-2026-10.md 10절)에서 위의 표(V1)는 실제 화자와의 거리 구조(RSA)와 진폭 범위 두 기준을 모두
// 넘지 못했다(ㅏ 턱 과다, ㅣ 입꼬리 당김 과다, ㅗㅜ 돌출 과다, 비원순 무리의 돌출 부족, 쉼·전환의 턱 부족). 아래 표는 같은 MediaPipe
// 측정기에서 538 탐색 절반 화자 37명의 무리별 중앙값을 목표로, 모프 → MediaPipe 순방향 사상(정지 자세 3,798개·렌더로 학습)과 앱
// 렌더 궤적 시뮬레이션으로 맞춘 뒤 탐색 문장을 실제로 렌더해 확인했다. 비원순 무리에도 사람처럼 약한 기본 돌출이 있고, 입꼬리 당김은
// 거의 없다(538 화자의 폭 진폭은 0에 가깝다). 확인 절반 판정과 쓰는 방식은 문서 6·10절.
export const VISEME_BLENDSHAPES_V15 = {
  // 1) 양순 ㅂ·ㅃ·ㅍ·ㅁ: 입술을 붙이고(mouthClose·압착) 사람처럼 살짝 내민다(538 양순 돌출 중앙값)
  1: { jawOpen: 0.02, mouthClose: 0.14, mouthPressLeft: 0.2, mouthPressRight: 0.2, mouthRollLower: 0.15, mouthRollUpper: 0.1, mouthFunnel: 0.19, mouthPucker: 0.27, mouthSmileLeft: 0.06, mouthSmileRight: 0.06, mouthUpperUpLeft: 0.01, mouthUpperUpRight: 0.01, mouthLowerDownLeft: 0.07, mouthLowerDownRight: 0.07, mouthShrugUpper: 0.07 },
  // 2) ㅏ·ㅐ: 턱 벌림을 538 범위로 줄이고(0.50 → 0.27) 아랫입술을 내린다. 돌출은 가장 작은 무리(돌출 바닥값을 정하는 무리)
  2: { jawOpen: 0.27, mouthFunnel: 0.04, mouthPucker: 0.08, mouthStretchLeft: 0.13, mouthStretchRight: 0.13, mouthLowerDownLeft: 0.15, mouthLowerDownRight: 0.15, mouthShrugLower: 0.1 },
  // 3) ㅣ·ㅔ: 입꼬리 당김을 크게 줄인다(smile 0.45 → 0.15, stretch 0.20 → 0.07, 538 화자의 폭 진폭은 0에 가깝다). 턱은 조금, 돌출은 비원순 기본값
  3: { jawOpen: 0.15, mouthFunnel: 0.12, mouthPucker: 0.35, mouthSmileLeft: 0.15, mouthSmileRight: 0.15, mouthStretchLeft: 0.07, mouthStretchRight: 0.07, mouthUpperUpLeft: 0.05, mouthUpperUpRight: 0.05, mouthLowerDownLeft: 0.07, mouthLowerDownRight: 0.07, mouthShrugUpper: 0.04, mouthShrugLower: 0.02 },
  // 4) ㅗ·ㅜ: 둥글림을 538 범위로 줄인다(funnel 0.62 → 0.50, pucker 0.48 → 0.32)
  4: { jawOpen: 0.1, mouthClose: 0.04, mouthPressLeft: 0.11, mouthPressRight: 0.11, mouthRollUpper: 0.1, mouthFunnel: 0.5, mouthPucker: 0.32, mouthUpperUpLeft: 0.04, mouthUpperUpRight: 0.04, mouthLowerDownLeft: 0.02, mouthLowerDownRight: 0.02, mouthShrugUpper: 0.02 },
  // 5) ㅓ·ㅡ: 조금 벌리고 기본 돌출
  5: { jawOpen: 0.12, mouthClose: 0.03, mouthPressLeft: 0.03, mouthPressRight: 0.03, mouthRollLower: 0.08, mouthFunnel: 0.14, mouthPucker: 0.21, mouthStretchLeft: 0.02, mouthStretchRight: 0.02, mouthUpperUpLeft: 0.07, mouthUpperUpRight: 0.07, mouthLowerDownLeft: 0.02, mouthLowerDownRight: 0.02, mouthShrugUpper: 0.06, mouthShrugLower: 0.04 },
  // 6) 치경 ㄷ·ㅌ·ㄴ·ㄹ·ㅅ: 조금 벌리고 윗입술을 살짝 올리며 기본 돌출
  6: { jawOpen: 0.13, mouthClose: 0.01, mouthPressLeft: 0.02, mouthPressRight: 0.02, mouthRollLower: 0.04, mouthRollUpper: 0.04, mouthFunnel: 0.17, mouthPucker: 0.19, mouthStretchLeft: 0.02, mouthStretchRight: 0.02, mouthUpperUpLeft: 0.12, mouthUpperUpRight: 0.12, mouthLowerDownLeft: 0.06, mouthLowerDownRight: 0.06, mouthShrugUpper: 0.04, mouthShrugLower: 0.02 },
  // 7) 연구개 ㄱ·ㅋ·ㅇ: 조금 벌리고 기본 돌출
  7: { jawOpen: 0.19, mouthClose: 0.02, mouthPressLeft: 0.01, mouthPressRight: 0.01, mouthRollLower: 0.05, mouthFunnel: 0.17, mouthPucker: 0.24, mouthStretchLeft: 0.06, mouthStretchRight: 0.06, mouthUpperUpLeft: 0.06, mouthUpperUpRight: 0.06, mouthLowerDownLeft: 0.05, mouthLowerDownRight: 0.05, mouthShrugUpper: 0.03, mouthShrugLower: 0.02 },
  // 8) 성문 ㅎ: 입 안쪽 무리 가운데 턱을 가장 많이 벌린다
  8: { jawOpen: 0.27, mouthClose: 0.11, mouthPressLeft: 0.01, mouthPressRight: 0.01, mouthRollLower: 0.01, mouthFunnel: 0.15, mouthPucker: 0.16, mouthSmileLeft: 0.02, mouthSmileRight: 0.02, mouthStretchLeft: 0.07, mouthStretchRight: 0.07, mouthUpperUpLeft: 0.07, mouthUpperUpRight: 0.07, mouthLowerDownLeft: 0.01, mouthLowerDownRight: 0.01, mouthShrugUpper: 0.08 },
  // 9) 이중모음 정지 모양(엔진은 내지 않음, 1단계 순환용): 0.6 × 4 + 0.4 × 2
  9: { jawOpen: 0.17, mouthClose: 0.02, mouthPressLeft: 0.07, mouthPressRight: 0.07, mouthRollUpper: 0.06, mouthFunnel: 0.32, mouthPucker: 0.22, mouthStretchLeft: 0.05, mouthStretchRight: 0.05, mouthUpperUpLeft: 0.02, mouthUpperUpRight: 0.02, mouthLowerDownLeft: 0.07, mouthLowerDownRight: 0.07, mouthShrugUpper: 0.01, mouthShrugLower: 0.04 },
  // 10) 경구개 ㅈ·ㅉ·ㅊ: 조금 벌리고 둥글림을 조금 더
  10: { jawOpen: 0.16, mouthClose: 0.03, mouthPressLeft: 0.01, mouthPressRight: 0.01, mouthRollLower: 0.05, mouthRollUpper: 0.04, mouthFunnel: 0.26, mouthPucker: 0.18, mouthSmileLeft: 0.06, mouthSmileRight: 0.06, mouthStretchLeft: 0.03, mouthStretchRight: 0.03, mouthLowerDownLeft: 0.07, mouthLowerDownRight: 0.07, mouthShrugLower: 0.04 },
  // 11) 양순 전환: 입술을 더 꽉 다물고 아랫입술을 말아 넣는다(538에서 양순 전환이 가장 두드러진 무리)
  11: { jawOpen: 0.08, mouthClose: 0.5, mouthPressLeft: 0.06, mouthPressRight: 0.06, mouthRollLower: 0.3, mouthFunnel: 0.1, mouthPucker: 0.2, mouthSmileLeft: 0.02, mouthSmileRight: 0.02, mouthStretchLeft: 0.03, mouthStretchRight: 0.03, mouthUpperUpLeft: 0.03, mouthUpperUpRight: 0.03, mouthShrugUpper: 0.05, mouthShrugLower: 0.15 },
  // 12) 치경 전환: 턱을 조금만 벌린 기본 돌출
  12: { jawOpen: 0.08, mouthClose: 0.02, mouthRollLower: 0.01, mouthFunnel: 0.18, mouthPucker: 0.18, mouthUpperUpLeft: 0.1, mouthUpperUpRight: 0.1, mouthLowerDownLeft: 0.03, mouthLowerDownRight: 0.03, mouthShrugUpper: 0.03 },
  // 13) 연구개 전환: 조금 벌린 기본 돌출
  13: { jawOpen: 0.17, mouthClose: 0.01, mouthPressLeft: 0.07, mouthPressRight: 0.07, mouthRollUpper: 0.08, mouthFunnel: 0.2, mouthPucker: 0.15, mouthSmileLeft: 0.02, mouthSmileRight: 0.02, mouthStretchLeft: 0.02, mouthStretchRight: 0.02, mouthLowerDownLeft: 0.09, mouthLowerDownRight: 0.09, mouthShrugLower: 0.03 },
  // 14) 휴지(어절 사이): 다물지 않고 살짝 벌린 이완 자세(538 쉼 구간)
  14: { jawOpen: 0.09, mouthClose: 0.04, mouthPressLeft: 0.04, mouthPressRight: 0.04, mouthRollLower: 0.01, mouthFunnel: 0.1, mouthPucker: 0.12, mouthStretchLeft: 0.01, mouthStretchRight: 0.01, mouthLowerDownLeft: 0.12, mouthLowerDownRight: 0.12 },
  // 15) 중립(재생 전후·한글 아닌 문자): 편하게 다문 기본 자세
  15: {},
}

// 빌드 시 Vite가 import.meta.env를 채운다. node 테스트에서는 비어 있어 기본값을 쓴다.
const ENV = (typeof import.meta !== 'undefined' && import.meta.env) || {}
/** V15 표를 쓰는가. 확인 절반 판정(문서 6절) 결과에 따라 기본값을 정한다. */
export const VISEME_V15_ENABLED = ENV.VITE_VISEME_V15 === '1'

/** 앱이 쓰는 표(V1 또는 V15). 아바타·퀴즈 보기·가상 화자가 모두 이 표를 읽는다. */
export const VISEME_BLENDSHAPES = VISEME_V15_ENABLED ? VISEME_BLENDSHAPES_V15 : VISEME_BLENDSHAPES_V1

/**
 * 두 표(V1·V15)에서 쓰는 모프타깃 키의 합집합.
 * 매 프레임 이 키들만 목표값으로 보간(lerp)하고 나머지는 건드리지 않는다. 어느 표를 쓰든 같은 키 집합이라, 표를 바꿔도 다른 표에서만
 * 쓰던 모프가 얼굴에 남지 않는다(목표에 없는 키는 0으로 돌아간다).
 */
export const ACTIVE_MORPH_KEYS = Array.from(
  new Set([...Object.values(VISEME_BLENDSHAPES_V1), ...Object.values(VISEME_BLENDSHAPES_V15)].flatMap((shape) => Object.keys(shape)))
)

/**
 * 혀 전용 모프타깃 매핑 (mesh-scoped) — 혀(tongue01) 메시에만 적용된다.
 *
 * CC 모델의 혀(CC_Base_Tongue) 메시가 가진 모프를 실측해 골랐다(각 모프 1.0에서
 * 혀끝/혀뒤가 움직인 거리, 단위 mm):
 *   T06_Tongue_Tip_Up  혀끝 +11.6 위·−4.7 뒤, 혀뒤 0     → 치경(혀끝을 윗잇몸에)
 *   T01_Tongue_Up      혀끝 +17.2 위,         혀뒤 +5.5 위 → 혀 전체 올림
 *   T10/T11_Bulge_L/R  혀뒤 +5.3 위, 혀끝 −12.6 뒤       → 설배 융기(연구개)
 *   V_Tongue_Curl_D    혀끝 −10.2 뒤·−2.4 아래            → 혀끝 물러남
 *   tongueOut          혀끝 +35.7 앞                      → 전방(소량만 쓴다)
 * 렌더러가 이 키들은 '혀 메시에만' 적용하므로 얼굴은 왜곡되지 않는다.
 *
 * 참고: 독화에서 혀는 대부분 가려져 살짝만 보이므로 값은 과하지 않게 잡는다.
 * tongueOut은 소량(≤0.2)이라 입 밖으로 나오지 않고 앞니 뒤에서 혀끝이 톡 보이는 정도다.
 */
export const VISEME_TONGUE = {
  // 6) 치경음 ㄷ/ㄸ/ㅌ/ㄴ/ㄹ/ㅅ/ㅆ — 혀끝을 윗잇몸에 대고 앞으로 살짝 내밈
  6: { T06_Tongue_Tip_Up: 1.0, tongueOut: 0.18 },

  // 7) 연구개음 ㄱ/ㄲ/ㅋ/ㅇ — 혀 뒤(설배)가 연구개로 올라가고 혀끝은 뒤로 물러남
  //    (뒤쪽 융기는 Bulge 좌우를 같이 써서 좌우 대칭으로 만든다)
  7: { T10_Tongue_Bulge_Left: 0.5, T11_Tongue_Bulge_Right: 0.5, V_Tongue_Curl_D: 0.4 },

  // 10) 경구개음 ㅈ/ㅉ/ㅊ — 혓날이 경구개 부근 (혀끝 위 + 혀 전체를 조금 올림)
  10: { T06_Tongue_Tip_Up: 0.6, T01_Tongue_Up: 0.3, tongueOut: 0.1 },

  // 12) 치경 전환 프레임 — 혀끝을 미리 올려 다음 조음으로 이어지게
  12: { T06_Tongue_Tip_Up: 0.55, tongueOut: 0.12 },
}

/**
 * 혀 전용 매핑에서 사용하는 모프타깃 키의 합집합. (혀 메시에만 lerp 적용)
 */
export const ACTIVE_TONGUE_KEYS = Array.from(
  new Set(Object.values(VISEME_TONGUE).flatMap((shape) => Object.keys(shape)))
)
