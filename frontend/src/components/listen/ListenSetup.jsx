import { useState } from 'react'
import { lingClip } from '../../lib/listenAudio'
import { clampGainDb, DEVICES, ROUTES, GAIN_MIN_DB, GAIN_MAX_DB } from '../../lib/listenMix'
import BottomBar from './BottomBar'
import SoundCard from './SoundCard'
import { useClip } from './useClip'
import { useListenKeys, usePlayer } from './usePlayer'
import { Card, ChoiceGroup, Heading, NOTICE, SYNTH } from './ui'

/**
 * 소리 크기 맞추기: 편안한 크기·쓰는 기기·듣는 방법. 소리 듣기의 어느 화면이든 처음에 거친다(ListenFrame).
 * 설정은 이 기기에만 저장한다(학습자 정보 원칙, C6). 연습하는 동안 이 크기를 넘지 않는다.
 */
const CALIBRATION_TEXT = '안녕하세요. 이 정도 크기가 편안한가요?'

// 인공와우 모의(청인 예비 파일럿): 연구진이 주소에 ?sim=ci를 붙여 열었거나 이미 켠 기기에서만 고를 수 있다. 학습자 화면에는 보이지 않는다
function simAllowed(initial) {
  try { return initial?.sim === 'ci' || new URLSearchParams(window.location.search).get('sim') === 'ci' } catch { return false }
}

export default function ListenSetup({ initial, onSave, onCancel }) {
  const [gainDb, setGainDb] = useState(initial?.gainDb ?? -15)
  const [sim, setSim] = useState(initial?.sim === 'ci' || (simAllowed(initial) && !initial))
  const showSim = simAllowed(initial)
  const [device, setDevice] = useState(initial?.device || 'unknown')
  const [route, setRoute] = useState(initial?.route || 'speaker')
  const player = usePlayer()
  const sample = useClip(CALIBRATION_TEXT, '')
  const test = async () => {
    const c = sample.clip || await lingClip('a')
    await player.play([{ clip: c, opts: { gainDb, sim: sim ? 'ci' : null } }])
  }
  const step = (d) => setGainDb((g) => clampGainDb(g + d))
  const save = () => { player.stop(); onSave({ gainDb, device, route, ...(sim && showSim ? { sim: 'ci' } : {}) }) }
  useListenKeys({ onPlay: test, canPlay: sample.state !== 'loading' && !player.busy, onEnter: save })
  const level = Math.round(((gainDb - GAIN_MIN_DB) / (GAIN_MAX_DB - GAIN_MIN_DB)) * 100)
  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Heading title="소리 크기 맞추기" sub="평소처럼 보청기나 인공와우를 켜고 예시 소리를 들으며 편안한 크기를 골라요. 연습하는 동안 이 크기를 넘지 않아요." />
      <SoundCard player={player} onPlay={test} clipState={sample.state === 'loading' ? 'loading' : 'ready'}
        label={sample.state === 'ready' ? '예시 문장 듣기' : '예시 소리 듣기(합성 모음)'} />
      <Card className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <p id="listen-gain-label" className="text-[15px] font-bold text-ink">크기</p>
          <p className="text-[15px] font-bold text-track-dark">{level}<span className="text-[12px] font-normal text-ink-faint"> / 100 · {gainDb} dB</span></p>
        </div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => step(-1)} disabled={gainDb <= GAIN_MIN_DB} aria-label="한 칸 작게"
            className="btn-secondary flex size-11 shrink-0 items-center justify-center p-0 text-[20px]">−</button>
          <input type="range" min={GAIN_MIN_DB} max={GAIN_MAX_DB} step={1} value={gainDb} onChange={(e) => setGainDb(Number(e.target.value))}
            aria-labelledby="listen-gain-label" aria-valuetext={`100 중 ${level}`} className="h-11 min-w-0 flex-1 accent-[var(--track)]" />
          <button type="button" onClick={() => step(1)} disabled={gainDb >= GAIN_MAX_DB} aria-label="한 칸 크게"
            className="btn-secondary flex size-11 shrink-0 items-center justify-center p-0 text-[20px]">+</button>
        </div>
        <div aria-hidden className="flex justify-between px-14 text-[12px] text-ink-faint"><span>작게</span><span>크게</span></div>
      </Card>
      <Card className="flex flex-col gap-5">
        <ChoiceGroup legend="쓰는 기기" options={DEVICES} value={device} onChange={setDevice} cols="grid-cols-1 sm:grid-cols-2" />
        <ChoiceGroup legend="듣는 방법" options={ROUTES} value={route} onChange={setRoute} cols="grid-cols-1" />
        {showSim && (
          <label className="flex min-h-[48px] items-start gap-3 rounded-13 border-2 border-line bg-surface-sunken px-4 py-3">
            <input type="checkbox" checked={sim} onChange={(e) => setSim(e.target.checked)} className="mt-1 size-4 accent-[var(--track)]" />
            <span className="text-[13px] leading-[1.6] text-ink">
              <b>인공와우 모의(연구용)</b> · 청인 참여자가 인공와우를 흉내 낸 소리(8채널 보코더)로 들어요. 예비 파일럿에서만 켜요.
            </span>
          </label>
        )}
      </Card>
      <p className="break-keep text-[12px] leading-[1.6] text-ink-faint">{SYNTH} 기기 정보는 이 기기에만 저장돼요. {NOTICE}</p>
      <BottomBar hint="편안한 크기를 고른 뒤 시작해요"
        primary={{ label: initial ? '이 크기로 저장' : '이 크기로 시작', onClick: save }}
        secondary={onCancel ? { label: '취소', onClick: () => { player.stop(); onCancel() } } : null} />
    </div>
  )
}
