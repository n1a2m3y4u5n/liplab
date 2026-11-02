import { useEffect, useState } from 'react'
import api from '../api'
import { LayerRunner } from './PilotBattery'
const transport = {
  answer: async body => (await api.post('/pilot/av-comparison/answer', body)).data,
  finish: async body => (await api.post('/pilot/av-comparison/finish', body)).data,
}
export default function AvComparison() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [run, setRun] = useState(null)
  const [checks, setChecks] = useState({ headphone: false, volume: false })
  const [snr, setSnr] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api.get('/pilot/av-comparison').then(r => setStatus(r.data)).catch(() => setError('조회하지 못했어요.'))
  useEffect(() => { load() }, [])
  async function start(e) {
    e.preventDefault(); setBusy(true); setError('')
    try { setRun((await api.post('/pilot/av-comparison/start', { snr_db: Number(snr), headphone_check: checks.headphone, volume_fixed: checks.volume })).data) }
    catch(e) { setError(e.response?.data?.detail || '시작하지 못했어요.') }
    finally { setBusy(false) }
  }
  if (run) return <LayerRunner run={run} checks={checks} transport={transport} onExit={() => { setRun(null); load() }} />
  return <main className="mx-auto max-w-[720px] space-y-4 p-6 text-ink">
    <h1 className="text-xl font-bold">소음 속 문장 비교</h1>
    {error && <p role="alert">{error}</p>}
    {status?.status === 'waiting_for_material' ? <p role="status">자료 대기</p> : status && <form onSubmit={start} className="space-y-4">
      <label className="block">연구진이 맞춘 SNR (dB)<input required type="number" min="-20" max="25" step="0.1" value={snr} onChange={e => setSnr(e.target.value)} className="ml-3 rounded border p-2" /></label>
      <label className="block"><input type="checkbox" checked={checks.headphone} onChange={e => setChecks({ ...checks, headphone: e.target.checked })} /> 헤드폰을 썼어요</label>
      <label className="block"><input type="checkbox" checked={checks.volume} onChange={e => setChecks({ ...checks, volume: e.target.checked })} /> 볼륨을 고정했어요</label>
      <button className="btn-primary" disabled={busy || !checks.headphone || !checks.volume || snr === '' || status.sessions.some(s => s.completed)}>시작·이어 하기</button>
    </form>}
    <ul>{status?.sessions.map(s => <li key={s.id} className="border-b py-3">{s.completed ? '마침' : '진행 중'} · {s.snr_db} dB
      {s.completed && <p>아바타 차이 {s.avatar_gain?.toFixed(3) ?? '—'} · 실제 얼굴 차이 {s.real_gain?.toFixed(3) ?? '—'} · 상대 지수 {s.relative_index?.toFixed(3) ?? '—'}</p>}
    </li>)}</ul>
  </main>
}
