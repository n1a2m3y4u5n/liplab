import { useEffect, useState } from 'react'
import api from '../api'
import useStore from '../store/useStore'

export default function AdminFeedback() {
  const token = useStore(s => s.token)
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [includeTests, setIncludeTests] = useState(false)
  const [start, setStart] = useState(() => new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10))
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10))
  useEffect(() => {
    let active = true
    setRows([]); setError('')
    api.get('/admin/feedback', { params: { include_tests: includeTests, start, end } }).then(r => { if (active) setRows(r.data.records) })
      .catch(() => { if (active) setError('조회할 수 없어요. 관리자 권한과 조회 기간(최대 32일)을 확인해 주세요.') })
    return () => { active = false }
  }, [includeTests, start, end, token])
  const download = async () => {
    try {
      const r = await api.get('/admin/feedback', { params: { format: 'csv', include_tests: includeTests, start, end }, responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const a = document.createElement('a'); a.href = url; a.download = 'feedback.csv'; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch { setError('CSV를 받지 못했어요.') }
  }
  return <main className="p-6">
    <h1>신고·SUS</h1>
    <label className="mr-3">시작일 (UTC) <input type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
    <label className="mr-3">종료일 (UTC) <input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>
    <label><input type="checkbox" checked={includeTests} onChange={e => setIncludeTests(e.target.checked)} /> 점검 계정 포함</label>
    <button className="ml-4" onClick={download}>CSV 받기</button>
    <p role="status">{error}</p>
    <div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr>
      {['시각', '사용자', '기기 / 세션', '화면', '종류', '내용'].map(v => <th key={v}>{v}</th>)}
    </tr></thead><tbody>{rows.map(r => <tr key={r.id}>
      <td>{r.ts}</td><td>{r.user_id}{r.is_demo ? ' (데모)' : ''}{r.is_test ? ' (점검)' : ''}</td>
      <td>{r.device_id}<br />{r.session_id}</td><td>{r.route}</td><td>{r.event}</td>
      <td className="whitespace-pre-wrap">{r.props.text || (r.props.score != null ? `${r.props.score} / 100 · ${r.props.answers.join(', ')}` : '—')}<br />{JSON.stringify(r.ua)} · {r.props.width}×{r.props.height}</td>
    </tr>)}</tbody></table></div>
  </main>
}
