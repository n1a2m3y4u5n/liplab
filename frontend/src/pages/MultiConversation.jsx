import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { curriculumAPI, learningAPI } from '../api'
import MouthAvatar from '../components/MouthAvatar'
import AppShell from '../components/AppShell'
import CueBadges, { CueLegend } from '../components/CueBadges'

/**
 * 다자 대화 독화(축 H) — 여러 화자가 번갈아 말하는 대화에서 '지금 누가 말하는지' + 그 사람
 * 입모양을 함께 읽는 실전 훈련.
 *  - H-2: 화자마다 아바타를 하나씩 나란히 둔다. 말하는 사람만 문장 입모양을 재생하고, 듣는 사람은
 *    가끔 '음' 하고 입을 다무는 맞장구만 한다(움직임만으로 화자를 고르지 못하게 하는 방해 자극).
 *  - H-4: '무슨 말이었나요' 보기는 한 단어를 입모양이 같은 다른 단어로 바꾼 닮은꼴 문장들이라, 입만
 *    보면 구별이 안 되고 앞 대화 문맥으로 골라야 한다. 한 턴은 빈칸 문맥 추론 턴이다.
 *  - H-9: 서버가 준 서명 정답(answer_key)과 턴별 선택을 보내 서버가 다시 채점한다.
 * 9/26 변경 내역 §2·§5: 연습 탭의 '다자 대화' 기능은 없어지고, 상황별 시나리오 'AI 대화 → 여러 명 대화'가 이 화면으로 온다
 * (?speakers=2~4&situation=). 그래서 제목을 그 선택지 이름('여러 명 대화')으로 바꾸고 부제를 뺐다. 라우트·파일 삭제는 따로 정한다.
 */
const SPK_COLOR = ['bg-sky-500', 'bg-rose-500', 'bg-amber-500', 'bg-teal-500']
const SPK_RING = ['ring-sky-400', 'ring-rose-400', 'ring-amber-400', 'ring-teal-400']
const SPK_TEXT = ['text-sky-600', 'text-rose-600', 'text-amber-600', 'text-teal-600']  // 선택 전 화자별 글자색(Figma: 화자마다 색)
const SPK_NAME = ['A', 'B', 'C', 'D']
// 듣는 사람의 맞장구 — 중립으로 있다가 잠깐 입술을 다문다('음'). 화자마다 길이를 달리해 박자가 겹치지 않게 한다.
const BACKCHANNEL = [
  [{ viseme: 15, duration_ms: 1400 }, { viseme: 1, duration_ms: 380 }, { viseme: 15, duration_ms: 2300 }],
  [{ viseme: 15, duration_ms: 2100 }, { viseme: 1, duration_ms: 320 }, { viseme: 15, duration_ms: 1700 }],
  [{ viseme: 15, duration_ms: 2700 }, { viseme: 1, duration_ms: 420 }, { viseme: 15, duration_ms: 1300 }],
  [{ viseme: 15, duration_ms: 1800 }, { viseme: 1, duration_ms: 360 }, { viseme: 15, duration_ms: 2000 }],
]

function shuffle(arr, seed) {
  // 대화마다 고정된 순서(다시 방문해도 보기 순서가 바뀌지 않게) — 간단한 LCG
  let s = seed >>> 0
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    s = (s * 1664525 + 1013904223) >>> 0
    const j = s % (i + 1);
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

export default function MultiConversation() {
  const [conv, setConv] = useState(null)
  const [idx, setIdx] = useState(0)
  const [frames, setFrames] = useState([])
  const [loading, setLoading] = useState(true)
  const [spkChoice, setSpkChoice] = useState([])     // 턴별로 고른 화자
  const [readChoice, setReadChoice] = useState([])   // 턴별로 고른 문장(빈칸 턴은 null)
  const [closureChoice, setClosureChoice] = useState(null)
  // 상황별 시나리오의 'AI 대화 · 여러 명'에서 들어오면 ?speakers=2~4 &level=1~5 &situation=적은 상황(225:183). 없으면 2명·임의 장면.
  const [params] = useSearchParams()
  const scene = (params.get('situation') || '').trim() || undefined
  const lv = parseInt(params.get('level'), 10)
  const level = lv >= 1 && lv <= 5 ? lv : undefined   // 그 화면에서 고른 난이도(1~5): 한 턴 길이. 없으면 서버 기본
  const [numSpeakers, setNumSpeakers] = useState(() => Math.min(4, Math.max(2, parseInt(params.get('speakers'), 10) || 2)))  // 화자 수(2~4) — 난이도 조절
  const [result, setResult] = useState(null)         // 서버 종합 채점(세션 종료 시)
  const [loadError, setLoadError] = useState(false)  // 대화를 못 불러오면 셸 안에서 다시 시도
  const submittedRef = useRef(false)
  // 화자별 얼굴(H-6) — public/models/faces/faces.json에 등록된 GLB를 화자 순서대로 배정한다. 목록이 비었거나 모자라면
  // 기본 얼굴을 쓴다(없는 파일을 불러 오류가 나지 않게 목록에 있는 것만 쓴다).
  const [faces, setFaces] = useState([])
  useEffect(() => {
    fetch('/models/faces/faces.json').then((r) => (r.ok ? r.json() : { faces: [] }))
      .then((d) => setFaces(Array.isArray(d?.faces) ? d.faces.filter((f) => typeof f?.url === 'string') : []))
      .catch(() => setFaces([]))
  }, [])
  const framesReqRef = useRef(0)   // 입모양 요청 번호 — 빨리 넘기면 늦게 온 이전 턴 응답을 버린다

  const load = useCallback(async () => {
    setLoading(true); setLoadError(false)
    try {
      const c = await curriculumAPI.getMultiConversation(numSpeakers, 6, scene, level)
      setConv({ ...c, seed: Math.floor(Math.random() * 1e9) })
      setIdx(0); setSpkChoice([]); setReadChoice([]); setClosureChoice(null)
      setResult(null); submittedRef.current = false
    } catch { setLoadError(true) } finally { setLoading(false) }
  }, [numSpeakers, scene, level])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!conv) return
    const t = conv.turns[idx]
    const req = ++framesReqRef.current
    setFrames([])
    if (t) learningAPI.getVisemes(t.text).then((f) => { if (framesReqRef.current === req) setFrames(f) }).catch(() => {})
  }, [conv, idx])

  const closureIdx = conv?.closure ? conv.closure.index : -1

  // 턴별 보기 — 정답 + 닮은꼴 문장(입모양이 같아 문맥이 필요한 오답). 닮은꼴이 없으면 다른 턴 문장으로 채운다.
  const readOptions = useMemo(() => {
    if (!conv) return []
    return conv.turns.map((t, i) => {
      const alike = (t.lookalikes || []).filter((x) => x && x !== t.text)
      const others = conv.turns.map((u) => u.text).filter((x) => x && x !== t.text && !alike.includes(x))
      const opts = [t.text, ...alike.slice(0, 3)]
      for (const o of shuffle(others, conv.seed + i)) {
        if (opts.length >= 4) break
        if (!opts.includes(o)) opts.push(o)
      }
      return shuffle(opts, conv.seed * 7 + i)
    })
  }, [conv])

  // 모든 턴을 다 풀면(화자 + 문장 또는 빈칸) 서버에 한 번 보낸다 — 서명 정답으로 서버가 다시 채점한다.
  const submit = useCallback(async (spk, read, clo) => {
    if (submittedRef.current || !conv) return
    submittedRef.current = true
    const hits = [], misses = []
    conv.turns.forEach((t, i) => {
      if (read[i] == null) return
      ;(read[i] === t.text ? hits : misses).push(t.text)
    })
    try {
      const r = await curriculumAPI.recordMultiConversation({
        answer_key: conv.answer_key || null,
        speaker_choices: conv.turns.map((_, i) => spk[i] ?? null),
        read_choices: conv.turns.map((_, i) => read[i] ?? null),
        closure_choice: clo,
        // answer_key가 없는 옛 서버용 집계값(있으면 서버가 무시한다)
        speaker_correct: conv.turns.filter((t, i) => spk[i] === t.speaker).length,
        speaker_total: conv.turns.filter((_, i) => spk[i] != null).length,
        read_correct: hits.length, read_total: hits.length + misses.length,
        read_hits: hits, read_misses: misses,
      })
      setResult(r)
    } catch { submittedRef.current = false }
  }, [conv])

  const turnDone = (i, spk = spkChoice, read = readChoice, clo = closureChoice) =>
    spk[i] != null && (i === closureIdx ? clo != null : read[i] != null)

  const maybeSubmit = (spk, read, clo) => {
    if (conv && conv.turns.every((_, i) => turnDone(i, spk, read, clo))) submit(spk, read, clo)
  }

  const chooseSpeaker = (s) => {
    if (spkChoice[idx] != null) return
    const next = [...spkChoice]; next[idx] = s
    setSpkChoice(next)
    maybeSubmit(next, readChoice, closureChoice)
  }
  const chooseRead = (text) => {
    if (readChoice[idx] != null) return
    const next = [...readChoice]; next[idx] = text
    setReadChoice(next)
    maybeSubmit(spkChoice, next, closureChoice)
  }
  const chooseClosure = (w) => {
    if (closureChoice != null) return
    setClosureChoice(w)
    maybeSubmit(spkChoice, readChoice, w)
  }

  // 불러오는 중·실패여도 셸(사이드바 '연습' 활성·레일·모바일 탭)은 그대로 두고 본문 자리만 바꾼다(§4-11).
  const speakerToggle = (
    <div className="flex items-center gap-1.5 text-[13px]">
      <span className="text-ink-muted">화자</span>
      {[2, 3, 4].map((n) => (
        <button key={n} type="button" onClick={() => setNumSpeakers(n)} aria-pressed={numSpeakers === n} disabled={loading}
          className={`rounded-full px-3.5 py-1 font-bold transition disabled:opacity-60 ${numSpeakers === n ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}>
          {n}명
        </button>
      ))}
    </div>
  )

  if (loading || !conv) {
    return (
      <AppShell active="practice" title="여러 명 대화" closeTo="/practice/hub">
        <div className="flex justify-end">{speakerToggle}</div>
        <div className="card flex flex-col items-center gap-3 py-16 text-center">
          {loading ? (
            <p role="status" className="text-[15px] font-bold text-ink-muted">대화를 불러오는 중…</p>
          ) : (
            <>
              <p role="alert" className="text-[15px] font-bold text-ink">대화를 불러오지 못했어요.</p>
              <button type="button" onClick={load} className="btn-primary">다시 불러오기</button>
            </>
          )}
        </div>
      </AppShell>
    )
  }
  const turn = conv.turns[idx]
  const last = idx >= conv.turns.length - 1
  const guess = spkChoice[idx]
  const answered = guess != null
  const isClosure = idx === closureIdx
  const readGuess = readChoice[idx]
  const done = turnDone(idx)
  const nDone = conv.turns.filter((_, i) => turnDone(i)).length

  return (
    <AppShell active="practice" title="여러 명 대화" closeTo="/practice/hub">
      {/* 안내 + 화자 수 토글(난이도) */}
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <p className="text-[15px] text-ink-muted">장면 <b className="text-ink">{conv.scene}</b> · <b className="text-ink">누가 말하는지</b> 찾은 뒤, 앞 대화 흐름으로 <b className="text-ink">무슨 말인지</b> 골라 보세요.</p>
        {speakerToggle}
      </div>
      {loadError && (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-14 border-2 border-bad-line bg-bad-tint px-4 py-2.5 text-[13.5px] font-bold text-bad-text">
          새 대화를 불러오지 못했어요.
          <button type="button" onClick={load} className="shrink-0 underline">다시 불러오기</button>
        </div>
      )}

      {/* 발화 순서 타임라인 — 푼 턴은 화자색, 현재는 링, 나머지는 회색(정답 미리보기 방지) */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        {conv.turns.map((t, i) => {
          const color = spkChoice[i] != null ? SPK_COLOR[t.speaker] : (i < idx ? 'bg-gray-300' : 'bg-gray-200')
          return (
            <button key={i} type="button" onClick={() => setIdx(i)} aria-label={`${i + 1}번째 발화`}
              className={`h-3 w-6 shrink-0 rounded-full ${color} ${i === idx ? 'ring-2 ring-primary-500' : ''}`} />
          )
        })}
        <span className="ml-2 shrink-0 text-xs text-ink-muted">{nDone} / {conv.turns.length}턴 완료</span>
      </div>

      {/* 세션 종합 채점(축 H) — 서버 재채점. 종합 = 닮은꼴 문장 고르기 + 빈칸 문맥 추론, 화자 식별은 따로. */}
      {result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-[14px] border-2 border-emerald-200 bg-emerald-50/70 px-4 py-2.5">
          <span className="text-sm font-bold text-emerald-800">이번 대화 종합 {result.combined}점</span>
          <span className="text-xs text-emerald-700">
            문장 {Math.round(result.read_accuracy * 100)}%
            {result.closure_correct != null && <> · 빈칸 {result.closure_correct ? '정답' : '오답'}</>}
            {' '}· 화자 찾기 {Math.round(result.speaker_accuracy * 100)}%
          </span>
          {result.missed_visemes?.length > 0 && (
            <span className="text-[11px] text-emerald-600">잘못 읽은 입모양 {result.missed_visemes.length}개를 약점 통계에 넣었어요(다음 추천에 반영)</span>
          )}
        </div>
      )}

      {/* 카드 1: 화자 아바타들 + 화자 찾기 */}
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[17px] font-bold text-ink">{conv.scene}</p>
          <p className="text-[13px] font-bold text-ink-muted">{idx + 1} / {conv.turns.length}턴</p>
        </div>

        <div className={`grid gap-2.5 ${conv.speakers >= 4 ? 'grid-cols-2 lg:grid-cols-4' : conv.speakers === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {Array.from({ length: conv.speakers }).map((_, s) => {
            const speaking = s === turn.speaker
            return (
              <div key={s} className={`relative rounded-xl ${answered && speaking ? `ring-2 ${SPK_RING[s]}` : ''}`}>
                {/* 화자별 아바타는 턴이 바뀌어도 다시 만들지 않는다(WebGL 캔버스 재생성 비용) — frames만 바뀐다 */}
                <MouthAvatar frames={speaking ? frames : BACKCHANNEL[s % BACKCHANNEL.length]}
                  height={null} className="h-[150px] lg:h-[230px]" modelUrl={faces[s]?.url} />
                <span className={`absolute left-2 top-2 rounded-md px-2 py-0.5 text-xs font-bold text-white ${SPK_COLOR[s]}`}>
                  {SPK_NAME[s]}
                </span>
              </div>
            )
          })}
        </div>
        <p className="mt-3 text-center text-[15px] font-bold text-ink-muted">
          {answered
            ? <>지금 <span className={`rounded px-1.5 py-0.5 text-white ${SPK_COLOR[turn.speaker]}`}>화자 {SPK_NAME[turn.speaker]}</span>가 말합니다</>
            : '지금 말하는 사람은 누구일까요?'}
        </p>

        <div className="mt-4 flex gap-3">
          {Array.from({ length: conv.speakers }).map((_, i) => {
            const isAns = answered && i === turn.speaker
            const isWrongPick = answered && i === guess && guess !== turn.speaker
            const base = 'flex flex-1 items-center justify-center gap-1.5 rounded-[14px] py-4 text-[17px] font-bold transition-all'
            const cls = isAns ? `${SPK_COLOR[i]} border-2 border-b-2 border-transparent text-white`
              : isWrongPick ? 'border-2 border-b-2 border-rose-300 bg-rose-50 text-rose-500 line-through'
              : answered ? 'border-2 border-b-[5px] border-line bg-white text-gray-300'
              : `border-2 border-b-[5px] border-line bg-white ${SPK_TEXT[i]} hover:border-primary-300 active:translate-y-[1px] active:border-b-2`
            return (
              <button key={i} disabled={answered} onClick={() => chooseSpeaker(i)} className={`${base} ${cls}`}>
                <span className="grid h-5 w-5 place-items-center rounded-full bg-black/10 text-xs">{SPK_NAME[i]}</span>
                화자 {SPK_NAME[i]}
              </button>
            )
          })}
        </div>
      </div>

      {/* 카드 2: 무슨 말이었나요(닮은꼴 문장) 또는 빈칸 문맥 추론 + 네비게이션 */}
      <div className="card flex flex-col">
        <div className="min-h-[120px] flex-1">
          {!answered ? (
            <p className="mt-2 rounded-[14px] border-2 border-dashed border-line py-10 text-center text-sm font-bold text-gray-400">
              먼저 말하는 사람을 찾아 주세요
            </p>
          ) : isClosure ? (
            closureChoice == null ? (
              <div>
                <p className="mb-1 text-[13px] font-bold text-ink-muted">빈칸에 들어갈 말은? 보기는 입모양이 같아요 — 앞 대화 흐름으로 고르세요.</p>
                <p className="mb-3 text-lg font-bold text-ink">“{conv.closure.display}”</p>
                <div className="flex flex-wrap gap-2">
                  {conv.closure.options.map((w) => (
                    <button key={w} onClick={() => chooseClosure(w)}
                      className="rounded-[12px] border-2 border-line bg-white px-5 py-3 text-[16px] font-bold text-ink transition hover:border-primary-300 hover:bg-primary-50">
                      {w}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mt-1 space-y-2">
                <p className={`text-sm font-bold ${closureChoice === conv.closure.answer ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {closureChoice === conv.closure.answer ? '정답! 문맥으로 골랐어요' : `아쉬워요 — 정답은 '${conv.closure.answer}'`}
                </p>
                <p className="text-lg font-bold text-ink">“{turn.text}”</p>
                <div className="overflow-x-auto rounded-[12px] border border-gray-100 bg-gray-50 p-2.5">
                  <CueBadges text={turn.text} />
                  <div className="mt-1.5"><CueLegend /></div>
                </div>
              </div>
            )
          ) : readGuess == null ? (
            <div>
              <p className="mb-2 text-[13px] font-bold text-ink-muted">무슨 말이었나요? 입모양이 같은 문장이 섞여 있어요 — 대화 흐름에 맞는 것을 고르세요.</p>
              <div className="space-y-2">
                {readOptions[idx].map((opt) => (
                  <button key={opt} onClick={() => chooseRead(opt)}
                    className="block w-full rounded-[12px] border-2 border-line bg-white px-4 py-3 text-left text-[15px] font-medium text-ink transition hover:border-primary-300 hover:bg-primary-50">
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-1 space-y-2">
              <p className={`text-sm font-bold ${readGuess === turn.text ? 'text-emerald-600' : 'text-rose-600'}`}>
                {readGuess === turn.text ? '정답! 잘 읽었어요' : '아쉬워요 — 실제로는'}
              </p>
              <p className="text-lg font-bold text-ink">“{turn.text}”</p>
              <div className="overflow-x-auto rounded-[12px] border border-gray-100 bg-gray-50 p-2.5">
                <CueBadges text={turn.text} />
                <div className="mt-1.5"><CueLegend /></div>
              </div>
            </div>
          )}
        </div>
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-gray-400">{idx + 1} / {conv.turns.length}</span>
          <div className="flex gap-2">
            {idx > 0 && <button onClick={() => setIdx(idx - 1)} className="rounded-[12px] border-2 border-line px-3 py-1.5 text-sm font-bold text-ink hover:bg-gray-50">이전</button>}
            {!last ? (
              <button onClick={() => setIdx(idx + 1)} disabled={!done}
                className="rounded-[12px] bg-primary-500 px-4 py-1.5 text-sm font-bold text-white hover:bg-primary-600 disabled:opacity-40">다음 발화 →</button>
            ) : (
              <button onClick={load} className="rounded-[12px] bg-emerald-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-emerald-700">새 대화 ↻</button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
