import { useState } from 'react'
import BottomBar from './BottomBar'
import { QuotaBar } from './QuotaProgress'
import { quotaView } from '../../lib/listenQuota'

const METHODS = {
  ling: ['▶', '들림 / 안 들림'], ax: ['▶ 1 → ▶ 2', '= 같아요 / ≠ 달라요'],
  word_id: ['▶', '낱말 고르기'], sentence: ['▶', '들은 문장 쓰기'],
  noise: ['▶ + 소음', '들은 문장 쓰기'], convo: ['▶', '대답 고르기'],
}

export default function ListenStart({ data, onStart, active }) {
  const q = quotaView(data.quota)
  const [condition, setCondition] = useState('quiet')
  const method = METHODS[data.mode] || METHODS.ling
  return <div className="flex flex-col gap-5">
    <div><p className="text-[13px] font-bold text-track-dark">소리 듣기 · {data.stage + 1}단계</p><h1 className="mt-2 text-[28px] font-black lg:text-[34px]">{data.title}</h1></div>
    <div className="flex min-h-[190px] flex-col items-center justify-center gap-6 rounded-20 border-2 border-line bg-white p-6" role="img" aria-label={method.join(', ')}>
      <div className="text-[38px] font-bold text-track-dark">{method[0]}</div><div className="text-[19px] font-bold">{method[1]}</div>
    </div>
    {data.mode === 'convo' && <fieldset className="rounded-20 border-2 border-line bg-white p-4"><legend className="px-2 text-[14px] font-bold">듣기 조건</legend><div className="grid grid-cols-2 gap-2">{(data.conditions || ['quiet']).map((c) => <button type="button" key={c} aria-pressed={condition === c} onClick={() => setCondition(c)} className={`btn-secondary min-h-11 px-2 ${condition === c ? 'border-track bg-track-tint text-track-dark' : ''}`}>{({ quiet: '조용함', noise: '소음', phone: '전화', room: '울리는 방' })[c]}</button>)}</div></fieldset>}
    <div className="flex flex-col gap-4 rounded-20 border-2 border-line bg-white p-5"><div className="flex justify-between font-bold"><span>오늘 몫</span><span className="text-ink-muted">◷ {Math.max(0, q.total - q.filled) * 4}분</span></div><QuotaBar quota={data.quota} /><div className="flex justify-between text-[15px] font-bold text-track-dark"><span>{q.total}묶음</span><span>{q.batch}문제 / 묶음</span></div></div>
    <BottomBar active={active} primary={{ label: '시작하기', onClick: () => onStart(condition) }} />
  </div>
}
