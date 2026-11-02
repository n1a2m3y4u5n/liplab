const valid = (t) => ['read', 'speak', 'listen'].includes(t)
export const lastTrackKey = (uid) => `liplab_last_track:${uid ?? 'guest'}`
export function saveLastTrack(uid, track, storage = globalThis.localStorage) {
  try { if (valid(track)) storage?.setItem(lastTrackKey(uid), track) } catch {}
}
export function loadLastTrack(uid, data = {}, storage = globalThis.localStorage) {
  try { const saved = storage?.getItem(lastTrackKey(uid)); if (valid(saved)) return saved } catch {}
  return ['read', 'speak', 'listen'].reduce((best, track) => {
    const sum = (t) => (data[t]?.stages || []).reduce((n, s) => n + (s.attempts || 0), 0)
    return sum(track) > sum(best) ? track : best
  }, 'read')
}
export function learnHref(track = 'read', section = 'path') {
  const params = new URLSearchParams()
  if (valid(track) && track !== 'read') params.set('track', track)
  if (section !== 'path') params.set('section', section)
  return '/learn/path' + (params.size ? '?' + params : '')
}
