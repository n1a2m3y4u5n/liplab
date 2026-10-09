import { useEffect, useRef, useState } from 'react'
import { listenAPI } from '../../api'
import { lingClip } from '../../lib/listenAudio'
import { LING_LABEL, lingNotes } from '../../lib/listenFlow'
import BottomBar from './BottomBar'
import { TaskEnd } from './ListenComplete'
import SoundCard from './SoundCard'
import StateCard from './StateCard'
import { useListenKeys, usePlayer } from './usePlayer'
import { Heading, Option } from './ui'

/**
 * 0단계 소리 확인(Ling 6소리): 음·우·아·이·쉬·스와 소리 없는 차례를 섞어 들렸는지 누른다. 소리는 화면이 합성한다(lingClip).
 * 끝나면 /api/listen/ling에 결과를 보내고 요약(들림·안 들림, 어제와 달라진 소리)을 보인다. 끝 버튼은 finish가 정한다(ListenComplete.TaskEnd).
 */
export default function LingCheck({ data, settings, onProgress, onExit, finish, exitLabel = '학습 화면으로', active }) {
  const seq = data.sequence || []
  const [k, setK] = useState(0)
  const res = useRef({ results: {}, fa: 0 })
  const [summary, setSummary] = useState(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)
  const player = usePlayer()
  const t0 = useRef(Date.now())
  useEffect(() => { onProgress(Math.min(k, seq.length), seq.length) }, [k, seq.length, onProgress])
  useEffect(() => { player.reset() }, [k, player.reset])
  const cur = seq[k]
  const heardOnce = player.everDone
  // Ling 소리는 화면이 합성한다(lingClip). 받는 동안도 '나오는 중'과 구별되지 않게 미리 만들어 둔다
  const [clips, setClips] = useState({})
  useEffect(() => {
    let on = true
    Promise.all(Object.keys(LING_LABEL).map(async (key) => [key, await lingClip(key)]))
      .then((pairs) => { if (on) setClips(Object.fromEntries(pairs)) }).catch(() => {})
    return () => { on = false }
  }, [])
  const ready = cur === 'silent' || !!clips[cur]
  const playNow = () => {
    if (!cur || !ready) return
    player.play([cur === 'silent' ? { silenceMs: 1400 } : { clip: clips[cur], opts: { gainDb: settings.gainDb } }])
  }
  const submit = async () => {
    setSaving(true)
    setErr(null)
    try {
      const r = await listenAPI.ling({ results: res.current.results, false_alarms: res.current.fa, route: settings.route })
      setSummary(r.summary)
    } catch { setErr('결과를 저장하지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요.') }
    setSaving(false)
  }
  const answer = (heard) => {
    if (!heardOnce || player.busy || k >= seq.length) return
    if (cur === 'silent') { if (heard) res.current.fa += 1 } else res.current.results[cur] = heard
    if (k + 1 < seq.length) { setK(k + 1); return }
    setK(seq.length)
    submit()
  }
  const done = k >= seq.length
  useListenKeys({ active: active && !done, onPlay: playNow, canPlay: ready && !player.busy, optionCount: 2, canPick: heardOnce && !player.busy,
    onPick: (i) => answer(i === 0) })

  if (summary) {
    const { sub, notes } = lingNotes(summary)
    return (
      <TaskEnd finish={finish} result={{ stage: 0, n: 0, c: 0, skipped: 0, mastered: false, summary, elapsed: Math.floor((Date.now() - t0.current) / 1000) }}
        title="오늘의 소리 확인" sub={sub} notes={notes}>
        <div className="grid w-full grid-cols-3 gap-2 sm:grid-cols-6">
          {(data.sounds || []).map((s) => {
            const ok = summary.heard.includes(s.key)
            return (
              <div key={s.key} className={`flex flex-col items-center gap-0.5 rounded-14 border-2 py-3 ${ok ? 'border-good/40 bg-good-tint' : 'border-bad/30 bg-bad-tint'}`}>
                <span className="text-[20px] font-bold text-ink">{s.label}</span>
                <span className="text-[12px] text-ink-muted">{s.band}</span>
                <span className={`text-[12px] font-bold ${ok ? 'text-good-text' : 'text-bad-text'}`}>{ok ? '들림' : '안 들림'}</span>
              </div>
            )
          })}
        </div>
      </TaskEnd>
    )
  }
  if (done) {
    return (
      <>
        <StateCard title={saving ? '결과를 저장하고 있어요' : '결과를 저장하지 못했어요'} body={saving ? null : err} />
        <BottomBar active={active} alert={!saving ? err : null} primary={!saving ? { label: '다시 저장하기', onClick: submit } : null}
          secondary={!saving ? { label: exitLabel, onClick: onExit } : null} />
      </>
    )
  }
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title={heardOnce ? '소리가 들렸나요?' : '버튼을 눌러 소리를 들어요'}
        meta={`소리 ${k + 1} / ${seq.length}`} sub={k === 0 ? '아무 소리가 나지 않는 차례도 있어요. 들렸을 때만 \'들렸어요\'를 눌러요.' : null} />
      {/* 무음 시행이 드러나지 않게 상태 문구는 소리가 있든 없든 같다 */}
      <SoundCard player={player} onPlay={playNow} clipState={ready ? 'ready' : 'loading'} label="소리 내기"
        statusText={player.busy ? '잘 들어 보세요' : player.phase === 'done' ? '끝났어요. 들렸는지 골라요' : null} />
      <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
        {['들렸어요', '안 들렸어요'].map((l, i) => (
          <Option key={l} index={i} label={l} big disabled={!heardOnce || player.busy} waiting={!heardOnce} onClick={() => answer(i === 0)} />
        ))}
      </div>
      <p className="hidden text-center text-[13px] text-ink-faint lg:block">스페이스 키로 듣고, 1·2 키로 골라요</p>
    </div>
  )
}
