import { track, errorKind } from './track.js'
// Safari의 MP4/AAC와 Chromium의 WebM/Opus 지원 차이를 처리한다.
export function recorderOptions(Recorder = globalThis.MediaRecorder) {
  if (typeof Recorder?.isTypeSupported !== 'function') return undefined
  const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4', 'audio/aac', 'audio/ogg;codecs=opus']
    .find(type => Recorder.isTypeSupported(type))
  return mimeType ? { mimeType } : undefined
}

export function recordingFilename(blob) {
  const type = (blob?.type || '').split(';')[0].toLowerCase()
  const ext = { 'audio/mp4': 'm4a', 'video/mp4': 'mp4', 'audio/aac': 'aac', 'audio/ogg': 'ogg', 'audio/wav': 'wav', 'audio/mpeg': 'mp3' }[type] || 'webm'
  return `speech.${ext}`
}

export function createRecorder(stream, Recorder = globalThis.MediaRecorder) {
  if (typeof Recorder !== 'function') throw Object.assign(new Error('MediaRecorder unavailable'), { name: 'NotSupportedError' })
  return new Recorder(stream, recorderOptions(Recorder))
}

// 녹음 시작까지 성공한 녹음기만 호출한 곳에 돌려준다.
export function startRecorder(stream, onData, onStop, Recorder = globalThis.MediaRecorder) {
  let rec
  try {
    rec = createRecorder(stream, Recorder)
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
