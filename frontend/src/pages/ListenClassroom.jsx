import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { learningAPI, listenAPI } from '../api'
import { loadClip, stopAll } from '../lib/listenAudio'
import { alternate, lipDiffers, pairMissing } from '../lib/listenFlow'
import { soundStatusText } from '../lib/listenView'
import BottomBar from '../components/listen/BottomBar'
import ListenFrame from '../components/listen/ListenFrame'
import StateCard from '../components/listen/StateCard'
import { useClip } from '../components/listen/useClip'
import { useListenKeys, usePlayer } from '../components/listen/usePlayer'
import { Card, Heading, ProgressLine, Skeleton, SpeakerIcon } from '../components/listen/ui'

/**
 * 소리 교실: /listen/classroom (입모양 교실 /learn/viseme?tab=learn의 듣기판). 채점하지 않는다.
 * 종류별 소리 짝(GET /api/listen/contrasts → [{kind, label, desc, pairs:[{a,b}], words:[{target, partner}]}])을 고르고
 * A·B를 따로, 번갈아(A-B-A-B), 같은 말을 여러 목소리로 들어 본다. 짝마다 입모양이 같은지 다른지 보인다(서버 표시가 없으면 입모양 프레임 비교,
 * lib/listenFlow.lipDiffers). 입모양이 같은 짝은 소리로만 가를 수 있고, 다른 짝은 입을 함께 보면 도움이 된다.
 * 목소리는 훈련 목소리만 쓴다(검사 목소리는 훈련에서 들은 적이 없어야 역치 검사가 공정하다). 아래 버튼으로 그 종류의 소리 짝 집중 연습에 간다.
 * 키보드: 스페이스 = 번갈아 듣기, 1 = A, 2 = B.
 */

const LIP_TEXT = {
  true: { label: '입모양 다름', body: '입모양이 달라서 입을 함께 보면 구별하기 쉬워요.' },
  false: { label: '입모양 같음', body: '입모양이 같아서 소리로만 가를 수 있어요. 귀로 차이를 익혀 두면 좋아요.' },
}

function Chip({ on, onClick, children }) {
  // 휴대폰에서 종류 줄은 옆으로 넘기므로, 고른 칩이 화면 밖에 있으면 보이게 옮긴다
  const ref = useRef(null)
  useEffect(() => { if (on) ref.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' }) }, [on])
  return (
    <button ref={ref} type="button" onClick={onClick} aria-pressed={on}
      className={`min-h-[40px] shrink-0 rounded-full px-4 py-2 text-[14px] font-bold leading-figma transition-colors ${on ? 'bg-track text-white' : 'bg-surface-sunken text-ink-muted hover:text-ink'}`}>
      {children}
    </button>
  )
}

/** 짝 하나(목록 칸): 'A · B' + 입모양 표시. */
function PairButton({ item, on, lip, onClick }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={`flex min-h-[64px] flex-col items-start justify-center gap-1 rounded-14 border-2 px-3.5 py-2.5 text-left transition-colors lg:rounded-16 ${on ? 'border-track bg-track-tint' : 'border-line bg-white hover:border-track'}`}>
      <span className="break-keep text-[17px] font-bold leading-snug text-ink">{item.a} <span className="text-ink-faint">·</span> {item.b}</span>
      <span className="text-[12px] font-bold text-ink-muted">{lip == null ? ' ' : LIP_TEXT[lip].label}</span>
    </button>
  )
}

/** 고른 짝 듣기 판: A · B · 번갈아 듣기 + 목소리 + 같은 말 다른 목소리 + 재생 상태. */
function ListenPanel({ item, lip, settings, voices, voiceList, active }) {
  const [voiceIdx, setVoiceIdx] = useState(0)
  const voice = voices.train[voiceIdx % voices.train.length] || ''
  const a = useClip(item.a, voice)
  const b = useClip(item.b, voice)
  const player = usePlayer()
  const [what, setWhat] = useState(null)
  // 여러 목소리 소리를 받는 동안 짝·목소리를 바꾸거나 화면을 떠나면 받은 뒤에 틀지 않는다(예전에는 다른 짝을 고른 뒤나 연습 탭으로
  // 나간 뒤에 앞 짝의 소리가 나왔다). 짝이 바뀌면 이 판이 새로 그려지고(key), 목소리가 바뀌면 세대가 오른다
  const gen = useRef(0)
  useEffect(() => () => { gen.current += 1 }, [])
  useEffect(() => { gen.current += 1; player.reset(); setWhat(null) }, [item.a, item.b, voice, player.reset])
  const opts = { gainDb: settings.gainDb }
  const ready = a.state === 'ready' && b.state === 'ready'
  const play = (steps, label) => { if (!player.busy) { setWhat(label); player.play(steps) } }
  const playOne = (c, label) => c.clip && play([{ clip: c.clip, opts }], label)
  const playAlt = () => ready && play(alternate(a.clip, b.clip, 2).map((clip) => ({ clip, opts })), `${item.a} · ${item.b} 번갈아`)
  const playVoices = async () => {
    if (player.busy) return
    const id = gen.current
    const clips = (await Promise.all(voices.train.map((v) => loadClip(item.a, v)))).filter(Boolean)
    if (id !== gen.current) return
    if (clips.length) play(clips.map((clip) => ({ clip, opts })), `「${item.a}」 여러 목소리`)
  }
  useListenKeys({ active, onPlay: playAlt, canPlay: ready && !player.busy, optionCount: 2, canPick: !player.busy,
    onPick: (i) => playOne(i === 0 ? a : b, i === 0 ? item.a : item.b) })
  // 못 받은 이유마다 글을 달리하고, 서버에 아직 없는 소리가 아니면(연결 끊김·풀기 실패) 다시 받기를 둔다(lib/listenFlow.pairMissing)
  const miss = pairMissing(a, b)
  const missing = miss.missing
  const retry = () => { if (a.state === 'missing') a.retry(); if (b.state === 'missing') b.retry() }
  const label = (v, i) => voiceList?.find((x) => x.id === v)?.label || `목소리 ${i + 1}`
  const status = missing ? miss.text
    : !ready ? soundStatusText('loading')
      : player.busy ? `${what || ''} 나오는 중${player.parts > 1 ? ` · ${player.part} / ${player.parts}` : ''}`
        : player.phase === 'done' ? '소리가 끝났어요' : '버튼을 누르면 소리가 나와요'
  const big = 'flex min-h-[88px] flex-col items-center justify-center gap-1.5 rounded-16 border-2 border-b-5 px-2 py-3 transition-all disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-[104px] lg:rounded-18'
  return (
    <Card className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2.5 lg:gap-3">
        {[[a, item.a, 1], [b, item.b, 2]].map(([c, text, n]) => (
          <button key={n} type="button" onClick={() => playOne(c, text)} disabled={c.state !== 'ready' || player.busy}
            aria-label={`${text} 듣기, ${n}번 키`} className={`${big} border-line bg-white text-ink enabled:hover:border-track`}>
            <span className="text-track-dark"><SpeakerIcon playing={false} size={22} /></span>
            <span className="break-keep text-[22px] font-bold leading-snug lg:text-[24px]">{text}</span>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <button type="button" onClick={playAlt} disabled={!ready || player.busy} className="btn-primary py-3 text-[15px] disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text">
          번갈아 듣기 <span className="font-normal opacity-80">· A B A B</span>
        </button>
        <button type="button" onClick={playVoices} disabled={a.state !== 'ready' || player.busy || voices.train.length < 2} className="btn-secondary py-3 text-[15px] text-track-dark">
          같은 말, 다른 목소리
        </button>
      </div>
      <div className="flex flex-col gap-2">
        <ProgressLine phase={ready ? player.phase : 'idle'} run={player.run} totalMs={player.totalMs} />
        <div className="flex items-center justify-between gap-3">
          <p role="status" aria-live="polite" className={`min-w-0 break-keep text-[13px] font-bold ${player.busy ? 'text-track-dark' : 'text-ink-muted'}`}>{status}</p>
          {miss.canRetry && (
            <button type="button" onClick={retry} className="btn-secondary min-h-[44px] shrink-0 px-3.5 py-2 text-[13px] text-track-dark">다시 받기</button>
          )}
        </div>
      </div>
      {voices.train.length > 1 && (
        <div className="flex flex-col gap-2 border-t-1.5 border-line pt-4">
          <p className="text-[13px] font-bold text-ink-muted">목소리</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="목소리">
            {voices.train.map((v, i) => <Chip key={v || i} on={i === voiceIdx % voices.train.length} onClick={() => setVoiceIdx(i)}>{label(v, i)}</Chip>)}
          </div>
        </div>
      )}
      {lip != null && (
        <p className="break-keep rounded-14 bg-surface-sunken px-4 py-3 text-[14px] leading-[1.6] text-ink">
          <b>{LIP_TEXT[lip].label}</b> · {LIP_TEXT[lip].body}
        </p>
      )}
    </Card>
  )
}

export default function ListenClassroom() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [kinds, setKinds] = useState(null)
  const [err, setErr] = useState(null)
  const [nonce, setNonce] = useState(0)
  const [sel, setSel] = useState(null)   // 고른 짝 {a, b}
  const [lips, setLips] = useState({})   // 'a|b' → true | false | null
  const asked = useRef(new Set())
  useEffect(() => {
    setErr(null)
    listenAPI.contrasts().then((k) => setKinds(Array.isArray(k) ? k : k?.kinds || []))
      .catch((e) => setErr(e?.response?.status === 404 ? 'missing' : 'network'))
  }, [nonce])
  const kindKey = params.get('kind')
  const kind = kinds?.find((k) => k.kind === kindKey) || kinds?.[0] || null
  const items = kind ? [...(kind.pairs || []).map((p) => ({ ...p, group: 'pair' })),
    ...(kind.words || []).map((w) => ({ a: w.target, b: w.partner, group: 'word', lip_same: w.lip_same, contrast: w.contrast }))] : []
  const cur = sel && items.find((x) => x.a === sel.a && x.b === sel.b) ? sel : items[0] || null
  // 입모양 표시: 서버 표시가 없으면 고른 종류의 짝마다 입모양 프레임을 한 번씩 받아 비교한다(같은 짝은 다시 받지 않는다)
  useEffect(() => {
    if (!kind) return
    for (const it of items) {
      const key = `${it.a}|${it.b}`
      const known = lipDiffers(it, kind)
      if (known != null) { if (lips[key] !== known) setLips((m) => ({ ...m, [key]: known })); continue }
      if (asked.current.has(key)) continue
      asked.current.add(key)
      Promise.all([learningAPI.getVisemes(it.a), learningAPI.getVisemes(it.b)])
        .then(([fa, fb]) => setLips((m) => ({ ...m, [key]: lipDiffers(it, kind, { a: fa, b: fb }) })))
        .catch(() => setLips((m) => ({ ...m, [key]: null })))
    }
  }, [kind?.kind, items.length])   // eslint-disable-line react-hooks/exhaustive-deps
  const exit = () => { stopAll(); navigate('/practice/hub') }
  // 연습으로: 종류 전체(practice_key 'kind:…'), 낱말 짝을 골랐으면 그 대조만(words[].contrast 'onset:ㅂ:ㅍ' 꼴)도 고를 수 있다
  const practice = (contrast) => { stopAll(); navigate(`/listen/practice/contrast?contrast=${encodeURIComponent(contrast)}`) }
  const pickKind = (k) => { stopAll(); setSel(null); setParams({ kind: k }, { replace: true }) }
  const pairs = items.filter((x) => x.group === 'pair')
  // 종류 안의 짝이 모두 같거나 모두 다르면(서버 lip 'same'·'differs') 설명 글이 이미 말하므로 짝마다 다시 적지 않는다. 섞이면('mixed') 짝마다 적는다
  const uniform = kind?.lip === 'same' || kind?.lip === 'differs'
  const lipOf = (it) => (uniform ? null : lips[`${it.a}|${it.b}`] ?? null)
  const words = items.filter((x) => x.group === 'word')
  return (
    <ListenFrame kicker="소리 교실 · 채점하지 않아요" onExit={exit} exitAria="나가기, 연습 탭으로" showProgress={false}>
      {(ctx) => (
        err ? (
          <StateCard title={err === 'missing' ? '소리 교실은 준비 중이에요' : '소리 짝을 불러오지 못했어요'}
            body={err === 'missing' ? '곧 열려요. 지금은 학습 경로의 소리 구별 단계로 들어 볼 수 있어요.' : '인터넷 연결을 확인하고 다시 불러와 주세요.'}
            actions={err === 'missing' ? [{ label: '연습 탭으로', onClick: exit }] : [{ label: '다시 불러오기', onClick: () => setNonce((n) => n + 1) }, { label: '연습 탭으로', onClick: exit }]} />
        ) : !kinds || !ctx.voiceList ? <Skeleton /> : !kind ? (
          <StateCard title="들어 볼 소리 짝이 없어요" actions={[{ label: '연습 탭으로', onClick: exit }]} />
        ) : (
          <div className="flex animate-fade-in flex-col gap-4 lg:gap-5">
            <Heading title="소리 교실" sub="헷갈리기 쉬운 소리 짝을 골라 마음껏 들어 봐요. 같은 말을 여러 목소리로 들으면 목소리가 바뀌어도 알아듣기 쉬워져요." />
            <div className="-mx-[18px] flex gap-2 overflow-x-auto px-[18px] pb-1 [scrollbar-width:none] lg:mx-0 lg:flex-wrap lg:overflow-visible lg:px-0" role="group" aria-label="소리 짝 종류">
              {kinds.map((k) => <Chip key={k.kind} on={k.kind === kind.kind} onClick={() => pickKind(k.kind)}>{k.label}</Chip>)}
            </div>
            {kind.desc && <p className="break-keep text-[15px] leading-[1.6] text-ink">{kind.desc}</p>}
            {cur && (
              <ListenPanel key={`${cur.a}|${cur.b}`} item={cur} lip={lipOf(cur)}
                settings={ctx.settings} voices={ctx.voices} voiceList={ctx.voiceList} active={ctx.active} />
            )}
            {pairs.length > 0 && (
              <section className="flex flex-col gap-2.5">
                <h2 className="text-[15px] font-bold text-ink">소리 짝</h2>
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:gap-3">
                  {pairs.map((p) => <PairButton key={`${p.a}|${p.b}`} item={p} on={cur?.a === p.a && cur?.b === p.b} lip={lipOf(p)}
                    onClick={() => { stopAll(); setSel(p) }} />)}
                </div>
              </section>
            )}
            {words.length > 0 && (
              <section className="flex flex-col gap-2.5">
                <h2 className="text-[15px] font-bold text-ink">낱말로 들어 보기</h2>
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:gap-3">
                  {words.map((p) => <PairButton key={`${p.a}|${p.b}`} item={p} on={cur?.a === p.a && cur?.b === p.b} lip={lipOf(p)}
                    onClick={() => { stopAll(); setSel(p) }} />)}
                </div>
              </section>
            )}
            <BottomBar active={ctx.active} hint="스페이스 번갈아 듣기 · 1·2 하나씩"
              primary={{ label: `${kind.label} 연습하기`, onClick: () => practice(kind.practice_key || `kind:${kind.kind}`) }}
              secondary={cur?.contrast ? { label: `${cur.a}·${cur.b} 짝만 연습`, onClick: () => practice(cur.contrast) } : null} />
          </div>
        )
      )}
    </ListenFrame>
  )
}
