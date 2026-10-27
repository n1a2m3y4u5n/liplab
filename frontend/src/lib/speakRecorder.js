import { track, errorKind } from './track.js'
// 녹음 시작까지 성공한 녹음기만 호출한 곳에 돌려준다.
export function startRecorder(stream, onData, onStop, Recorder = globalThis.MediaRecorder) {
  let rec
  try {
    rec = new Recorder(stream)
    rec.ondataavailable = onData
    rec.onstop = onStop
    rec.start()
    track('recording_start')
    return rec
  } catch (cause) {
    track('recording_failure', { error_kind: errorKind(cause) })
    if (rec) {
      rec.ondataavailable = null
      rec.onstop = null
      try { if (rec.state !== 'inactive') rec.stop() } catch { /* noop */ }
    }
    throw Object.assign(new Error('녹음을 시작하지 못했어요.', { cause }), { name: 'RecordingError' })
  }
}
