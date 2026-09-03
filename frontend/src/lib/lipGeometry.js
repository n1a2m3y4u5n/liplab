/**
 * 입술 기하 지표 (고도화 계획서 §2.5 그림8 재현).
 *
 * MediaPipe FaceLandmarker가 이미 돌려주는 얼굴 랜드마크(478점) 좌표에서 입술의
 * 가로너비·세로높이·안쪽개구도·종횡비·둘레를 계산한다. 양안(외안각) 거리로 정규화해
 * 카메라 거리·얼굴 크기에 무관하게 만든다.
 *
 * blendshape 코사인 채점(mouthScore.js)은 조명·모델에 흔들리지만, 좌표 기하는
 * 결정론적이고 해석 가능해 채점의 보조 근거가 된다. 순수 함수 — 부수효과 없음.
 */

// MediaPipe FaceLandmarker 표준 인덱스
const IDX = {
  mouthL: 61, mouthR: 291,     // 입꼬리(가로너비)
  lipTop: 0, lipBottom: 17,    // 바깥 입술 위/아래(세로높이)
  innerTop: 13, innerBottom: 14, // 안쪽 입술 위/아래(개구도)
  eyeL: 33, eyeR: 263,         // 좌우 외안각(정규화 기준 거리)
}

// 바깥 입술 둘레 링(시계방향 근사)
const OUTER_LIP_RING = [
  61, 146, 91, 181, 84, 17, 314, 405, 321, 375,
  291, 409, 270, 269, 267, 0, 37, 39, 40, 185,
]

function dist(a, b) {
  if (!a || !b) return 0
  const dx = a.x - b.x
  const dy = a.y - b.y
  const dz = (a.z || 0) - (b.z || 0)
  return Math.hypot(dx, dy, dz)
}

const r3 = (v) => Math.round(v * 1000) / 1000

/**
 * @param {Array<{x:number,y:number,z?:number}>} landmarks - res.faceLandmarks[0]
 * @returns {{width:number,height:number,inner:number,aspect:number,perimeter:number}|null}
 *   길이 지표는 모두 양안 거리로 나눈 무차원 값. 얼굴/입이 안 잡히면 null.
 */
export function lipGeometry(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length < 468) return null
  const L = landmarks
  const iod = dist(L[IDX.eyeL], L[IDX.eyeR])
  if (!iod) return null

  const width = dist(L[IDX.mouthL], L[IDX.mouthR]) / iod
  const height = dist(L[IDX.lipTop], L[IDX.lipBottom]) / iod
  const inner = dist(L[IDX.innerTop], L[IDX.innerBottom]) / iod

  let perimeter = 0
  for (let i = 0; i < OUTER_LIP_RING.length; i++) {
    const a = L[OUTER_LIP_RING[i]]
    const b = L[OUTER_LIP_RING[(i + 1) % OUTER_LIP_RING.length]]
    perimeter += dist(a, b)
  }
  perimeter /= iod

  return {
    width: r3(width),
    height: r3(height),
    inner: r3(inner),
    aspect: width > 0 ? r3(height / width) : 0, // 종횡비(세로/가로): 개방모음↑, 원순/폐구↓
    perimeter: r3(perimeter),
  }
}

export const LIP_GEOMETRY_LABELS = {
  width: '가로너비',
  height: '세로높이',
  inner: '안쪽 개구도',
  aspect: '종횡비',
  perimeter: '입술둘레',
}
