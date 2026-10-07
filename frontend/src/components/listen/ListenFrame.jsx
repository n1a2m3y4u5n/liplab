import { useCallback, useEffect, useMemo, useState } from 'react'
import { loadVoices, setSimMode, stopAll } from '../../lib/listenAudio'
import { voiceRoles } from '../../lib/listenMix'
import ListenSetup from './ListenSetup'
import { useListenSettings } from './useClip'
import { IC, NOTICE, releaseClickFocus } from './ui'

/**
 * 소리 듣기 화면의 틀(레슨 집중 모드, 핸드오프 §3.4). 단계 레슨·연습 모드·오늘의 듣기·복습·소리 교실이 모두 이 틀을 쓴다.
 * 루트에 data-track="listen"을 달아 트랙색(버튼·진행바)이 청록이 된다. 위에 X · 진행바 · n / 전체, 그 아래 작은 제목 줄과 '소리 크기'.
 * 처음에는 소리 크기 맞추기(ListenSetup)를 거친다. 크기를 바꾸는 동안에도 내용은 숨겨 둘 뿐 그대로 둔다(묶음이 처음부터 다시 시작되지 않게).
 *
 * children(ctx): ctx = {settings, voices, voiceList, onProgress(cur, total, label?), active, ready}
 *  - ready: 설정과 목소리 목록이 모두 준비됨. active: 설정 화면이 닫혀 있음(키보드·하단 바를 이때만 쓴다).
 * showProgress=false면 진행바 자리에 제목만 둔다(소리 교실·고르는 화면).
 */
export default function ListenFrame({ kicker, onExit, exitAria = '나가기', showProgress = true, children }) {
  const [settings, saveSettings] = useListenSettings()
  const [editing, setEditing] = useState(false)
  const [voiceList, setVoiceList] = useState(null)
  const [prog, setProg] = useState({ cur: 0, total: 0, label: null })
  const voices = useMemo(() => voiceRoles(voiceList || []), [voiceList])
  useEffect(() => { loadVoices().then(setVoiceList) }, [])
  useEffect(() => { setSimMode(settings?.sim) }, [settings?.sim])
  useEffect(() => () => stopAll(), [])
  const onProgress = useCallback((cur, total, label = null) => setProg({ cur, total, label }), [])
  const setup = !settings || editing
  const barPct = prog.total ? (prog.cur / prog.total) * 100 : 0
  const counter = prog.label || (prog.total > 0 ? `${Math.min(prog.cur + 1, prog.total)} / ${prog.total}` : null)
  const exit = () => { stopAll(); onExit() }
  const ctx = { settings, voices, voiceList, onProgress, active: !setup, ready: !!settings && !!voiceList }
  return (
    <div data-track="listen" className="flex min-h-[100dvh] flex-col bg-page" style={{ paddingBottom: 'var(--listen-bar-h, 0px)' }}
      onClick={releaseClickFocus}>
      <div className="mx-auto flex w-full max-w-[676px] flex-1 flex-col px-[18px] pt-[18px] lg:pt-7 lg:[@media(max-height:860px)]:pt-5">
        {/* 진행 헤더(독화 레슨 91:13): 나가기 X + 진행바 + n / 전체 */}
        <div className="flex items-center gap-3 lg:gap-[18px]">
          <button type="button" onClick={exit} aria-label={exitAria} className="-m-1.5 shrink-0 rounded-full p-1.5">
            <img src={IC.close} alt="" className="size-8 lg:size-9" />
          </button>
          {showProgress ? (
            <>
              <div className="h-3 flex-1 overflow-hidden rounded-full bg-fill-strong lg:h-[14px]" role="progressbar" aria-label="진행"
                aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(barPct)} aria-valuetext={counter || '진행 전'}>
                <div className="h-full rounded-full bg-track transition-[width] duration-500" style={{ width: `${barPct}%` }} />
              </div>
              <span className="min-w-[3.5em] shrink-0 text-right text-[13px] font-bold leading-figma text-ink-muted lg:text-[15px]">{!setup && counter}</span>
            </>
          ) : <span className="flex-1" />}
        </div>

        <main className="mt-6 flex flex-1 flex-col gap-4 pb-6 lg:mt-5 lg:gap-5 lg:[@media(max-height:860px)]:mt-3.5">
          <div className="flex min-h-[44px] items-center justify-between gap-3">
            <p className="min-w-0 truncate text-[12px] font-bold text-track-dark lg:text-[13px]">{kicker}</p>
            {settings && !editing && (
              <button type="button" onClick={() => { stopAll(); setEditing(true) }} className="btn-secondary min-h-[44px] shrink-0 px-3.5 py-2 text-[13px]">소리 크기</button>
            )}
          </div>
          {setup && (
            <ListenSetup initial={settings} onSave={(v) => { saveSettings(v); setEditing(false) }} onCancel={settings ? () => setEditing(false) : null} />
          )}
          <div hidden={setup} className="flex flex-col gap-4 lg:gap-5">
            {settings ? children(ctx) : null}
          </div>
          <p className="mt-auto pt-2 text-center text-[12px] leading-[1.6] text-ink-faint">{NOTICE}</p>
        </main>
      </div>
    </div>
  )
}
