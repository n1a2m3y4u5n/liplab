import { useEffect, useState } from 'react'
import api from '../api'

const empty = { video_id: '', source: '', license_label: '', evidence: '', decision: 'pending' }
export default function KmsavReview() {
  const [form, setForm] = useState(empty)
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api.get('/admin/kmsav').then(r => setRows(r.data.records))
  useEffect(() => { load().catch(() => setError('조회하지 못했어요.')) }, [])
  async function save(e) {
    e.preventDefault(); setBusy(true); setError('')
    try { await api.put('/admin/kmsav', form); await load(); setForm(empty) }
    catch { setError('저장하지 못했어요. 권한과 입력을 확인해 주세요.') }
    finally { setBusy(false) }
  }
  return <main className="p-6 space-y-4 text-ink">
    <h1 className="text-xl font-bold">영상 라이선스 검수</h1>
    <form onSubmit={save} className="space-y-3">
      {[['video_id', '영상 ID'], ['source', '출처 링크'], ['license_label', 'CC 표기'], ['evidence', '확인 근거']].map(([key, label]) =>
        <label key={key} className="block">{label}<input required maxLength={key === 'video_id' ? 11 : key === 'evidence' ? 1000 : key === 'source' ? 500 : 100}
          className="block w-full rounded border p-2" value={form[key]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></label>)}
      <label className="block">사용 여부<select className="ml-3 rounded border p-2" value={form.decision} onChange={e => setForm({ ...form, decision: e.target.value })}>
        <option value="pending">확인 대기</option><option value="usable">사용 가능</option><option value="rejected">사용 불가</option>
      </select></label>
      <button disabled={busy} className="btn-primary" type="submit">저장</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <ul>{rows.map(row => <li key={row.video_id} className="border-b py-3">
      <a href={row.source} target="_blank" rel="noreferrer">{row.video_id}</a> · {row.license_label} · {row.decision}
      <button className="ml-3" onClick={() => setForm(row)}>수정</button>
      <p>{row.evidence}</p>
    </li>)}</ul>
  </main>
}
