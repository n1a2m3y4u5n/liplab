/**
 * 웹캠 blendshape 시퀀스를 화면 주사율과 무관한 고정 속도로 맞춘다(축 D 립리딩 입력, 9/25).
 *
 * 예전 수집은 requestAnimationFrame마다 한 번씩 검출해, 30 fps 카메라라도 60 Hz 화면에서는 같은 프레임이 두 번,
 * 120 Hz 화면(맥북 ProMotion 등)에서는 네 번 들어갔다. 립리딩 모델 입력 길이와 반복 패턴이 기기마다 달라지므로,
 * 새 영상 프레임일 때만 검출해 시각과 함께 모으고, 이 함수로 60 Hz 시각 격자에 다시 놓는다. 30 fps 카메라면 프레임마다
 * 두 번 반복돼 벤치에서 검증한 제품 조건(dup2)과 같아진다.
 */

/**
 * frames: [{t, bs}] (t = ms, 오름차순). t0부터 durMs 동안 hz 간격의 시각마다, 그 시각 이전의 가장 늦은 프레임을 고른다.
 * 첫 프레임이 들어오기 전의 칸은 버린다. 반환: [bs, …]
 */
export function resampleFrames(frames, t0, durMs, hz = 60) {
  if (!frames || !frames.length || !(hz > 0) || !(durMs > 0)) return []
  const step = 1000 / hz
  const n = Math.round((durMs * hz) / 1000)
  const out = []
  let j = -1
  for (let k = 0; k < n; k++) {
    const tk = t0 + k * step
    while (j + 1 < frames.length && frames[j + 1].t <= tk) j++
    if (j >= 0) out.push(frames[j].bs)
  }
  return out
}
