import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react'
import { learningAPI } from '../api'
import { fingerspellImage } from '../lib/fingerspell'

// 입모양(three)은 필요할 때만 로드 → 수어 영상만 볼 땐 three 안 받음.
//  - 기본형: "입모양 함께" 토글을 켤 때 LipSyncPlayer3D
//  - 나란히 보기형(split): 번역 결과가 나온 뒤 MouthAvatar(컨트롤 없는 경량 아바타)
const LipSyncPlayer3D = lazy(() => import('./LipSyncPlayer3D'))
const MouthAvatar = lazy(() => import('./MouthAvatar'))

/**
 * 수어 결과 패널 — 문장(text)을 받아 번역하고, **실제 국립국어원 수어 영상을 메인으로**
 * 인라인 재생한다. 사전 미등재어는 지문자.
 * variant='default': 입모양(mouthing)은 옵션 토글(기본 off). WordStage·Practice·전역 수어 오버레이가 쓴다.
 * variant='split': Figma 226:156 "수어와 입모양"의 Players(226:160) — 같은 폭 두 칸
 *   ('수어 영상' 초록 | '입모양 아바타' 보라, 머리 글자 + 190px 무대). 입력 전에는 Figma 자리 그림(손·입)을 둔다.
 *   /learn/sign(Sign.jsx)만 쓴다. Figma에 없는 것 중 단어 이동(토큰 칩·전체 재생), 라이선스 출처 표기,
 *   근접 수어 대체 안내('사전에 없어 근접 수어로 표시')는 기능·정확성 때문에 남긴다. 수형 설명·사전 링크·
 *   번역 메모(수어 문법 주석)는 나란히 보기에서 뺐다(9/24, 기본형 패널에는 그대로 있다).
 */
const FS_MS = 1200  // 전체재생 시 지문자 토큰 표시 시간

/** 나란히 보기 한 칸(226:161 / 226:169) — 머리 글자 13.5px + 흰 70% 무대(190px, r14). */
function Player({ label, tone, children }) {
  const cls = tone === 'sign' ? 'bg-pastel-mint text-stat-accuracy' : 'bg-primary-100 text-primary-700'
  return (
    <div className={`flex min-w-0 flex-col items-center gap-2.5 rounded-16 py-4 ${cls}`}>
      <p className="text-[13.5px] font-bold leading-figma">{label}</p>
      <div className="relative flex h-[190px] w-full items-center justify-center overflow-hidden rounded-14 bg-white/70">
        {children}
      </div>
    </div>
  )
}

/** 입모양 자리 그림(226:172 입 120×64 + 226:173 속 82×32) — 문장을 넣기 전·아바타를 불러오는 동안. */
function MouthPlaceholder() {
  return (
    <span aria-hidden className="relative h-16 w-[120px]">
      <img src="/ui/lp-226-32-mouth.svg" alt="" className="absolute inset-0 size-full" />
      <img src="/ui/lp-226-32-mouth-inner.svg" alt="" className="absolute left-[19px] top-4 h-8 w-[82px]" />
    </span>
  )
}

function CoverageBadge({ method, coverage }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className={`px-2 py-0.5 rounded-full font-medium ${method === 'llm' ? 'bg-indigo-100 text-indigo-700' : 'bg-amber-100 text-amber-700'}`}>
        {method === 'llm' ? 'AI 번역(Claude)' : '규칙 근사'}
      </span>
      <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700">수어 {coverage.matched}</span>
      {coverage.fingerspelled > 0 && (
        <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">지문자 {coverage.fingerspelled}</span>
      )}
    </div>
  )
}

export default function SignPanel({ text, variant = 'default' }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [current, setCurrent] = useState(0)
  const [playingAll, setPlayingAll] = useState(false)
  const [showMouth, setShowMouth] = useState(false)
  const fsTimer = useRef(null)

  useEffect(() => {
    const q = (text || '').trim().slice(0, 200)
    if (!q) { setResult(null); return }
    let cancelled = false
    setLoading(true); setError(''); setResult(null); setCurrent(0); setPlayingAll(false)
    learningAPI.translateSign(q)
      .then((data) => { if (!cancelled) setResult(data) })
      .catch((e) => { if (!cancelled) setError(e?.response?.data?.detail || '번역 중 오류가 발생했습니다.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [text])

  const tokens = result?.tokens || []
  const token = tokens[current] || null

  const clearFs = () => { if (fsTimer.current) { clearTimeout(fsTimer.current); fsTimer.current = null } }
  const advance = useCallback(() => {
    setCurrent((i) => { if (i < tokens.length - 1) return i + 1; setPlayingAll(false); return i })
  }, [tokens.length])

  // 전체재생: 영상 토큰은 <video onEnded>로, 지문자/영상없음 토큰은 타이머로 진행
  useEffect(() => {
    clearFs()
    if (!playingAll || !token) return
    const hasVideo = token.type === 'sign' && token.video_url
    if (!hasVideo) fsTimer.current = setTimeout(advance, FS_MS)
    return clearFs
  }, [playingAll, current, token, advance])

  if (variant === 'split') {
    return (
      <SplitView text={text} loading={loading} error={error} result={result} tokens={tokens} token={token}
        current={current} playingAll={playingAll} advance={advance}
        onPick={(i) => { setPlayingAll(false); setCurrent(i) }}
        onPlayAll={() => { setCurrent(0); setPlayingAll(true) }} />
    )
  }

  if (!text) return null
  if (loading) return <div className="py-14 text-center text-gray-500 text-sm">수어로 변환 중…</div>
  if (error) return <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
  if (!result || tokens.length === 0) return <div className="py-10 text-gray-500 text-sm text-center">변환할 단어가 없습니다.</div>

  return (
    <div>
      {/* 헤더 */}
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <CoverageBadge method={result.method} coverage={result.coverage} />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer select-none">
            <input type="checkbox" checked={showMouth} onChange={(e) => setShowMouth(e.target.checked)} />
            입모양 함께
          </label>
          <button onClick={() => { setCurrent(0); setPlayingAll(true) }}
            className="text-xs px-3 py-1.5 rounded-lg bg-primary-500 text-white hover:bg-primary-600 font-medium">
            전체 재생
          </button>
        </div>
      </div>

      {result.notes && <p className="mb-2 text-xs text-gray-500">{result.notes}</p>}
      {result.annotations?.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {result.annotations.map((a, i) => (
            <span key={i} className="text-[11px] px-2 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-100">
              {a.marker}: {a.note}
            </span>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-5 gap-4">
        {/* 메인: 수어 영상 (또는 지문자/수형설명) */}
        <div className={showMouth ? 'md:col-span-3' : 'md:col-span-5'}>
          <div className="relative rounded-2xl overflow-hidden bg-slate-900 flex items-center justify-center" style={{ minHeight: 300 }}>
            {token.type === 'sign' && token.video_url ? (
              <video
                key={token.video_url}
                src={token.video_url}
                autoPlay muted playsInline
                loop={!playingAll}
                onEnded={playingAll ? advance : undefined}
                onError={() => { if (playingAll) advance() }}   // 로드 실패 시에도 전체재생이 멈추지 않게 다음으로
                className="w-full h-auto max-h-[440px] bg-white"
              />
            ) : token.type === 'sign' ? (
              // 영상 해석 실패 → 수형설명 텍스트로 폴백
              <div className="p-6 text-center text-slate-100">
                <p className="text-sm text-slate-300 mb-2">수형 설명</p>
                <p className="text-base leading-relaxed">{token.description || '설명 없음'}</p>
                {token.dict_url && (
                  <a href={token.dict_url} target="_blank" rel="noopener noreferrer"
                    className="inline-block mt-3 text-xs text-primary-300 underline">국립국어원에서 영상 보기 ↗</a>
                )}
              </div>
            ) : (
              // 지문자(지화) — 자모별 손모양 이미지(없으면 글자 폴백)
              <div className="p-4 text-center w-full">
                <p className="text-xs text-slate-400 mb-3">지문자 (지화) — 한 글자씩 손모양으로</p>
                <div className="flex flex-wrap gap-3 justify-center items-end">
                  {token.jamo.map((group, gi) => (
                    <div key={gi} className="flex gap-1 items-end p-1.5 rounded-lg bg-white/5">
                      {group.map((jamo, ji) => {
                        const img = fingerspellImage(jamo)
                        return (
                          <div key={ji} className="flex flex-col items-center">
                            {img ? (
                              <img src={img} alt={`지문자 ${jamo}`} loading="lazy"
                                className="h-24 w-auto rounded bg-white object-contain" />
                            ) : (
                              <div className="h-24 w-14 rounded bg-white/90 flex items-center justify-center text-slate-800 text-2xl font-bold">{jamo}</div>
                            )}
                            <span className="mt-1 text-xs text-slate-200">{jamo}</span>
                          </div>
                        )
                      })}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 현재 단어 라벨 (별칭 치환은 투명하게 "밥 → 식사"로) */}
            <div className="absolute top-3 left-3 bg-black/55 text-white px-3 py-1 rounded-lg text-sm font-semibold">
              {token.word}
              {token.signed_as && <span className="text-amber-300"> → {token.signed_as}</span>}
              {token.negate && <span className="ml-1 text-red-300 text-xs">(부정)</span>}
              <span className="ml-2 text-white/60 text-xs">{current + 1}/{tokens.length}</span>
            </div>
          </div>

          {/* 현재 토큰 부가정보(별칭 안내 · 수형설명 · 출처) */}
          {token.type === 'sign' && (
            <div className="mt-1.5">
              {token.signed_as && (
                /^\d+$/.test(String(token.word)) ? (
                  <p className="text-[11px] text-slate-500 mb-0.5">
                    숫자 ‘{token.word}’ → 수어 ‘{token.signed_as}’
                  </p>
                ) : (
                  <p className="text-[11px] text-amber-600 mb-0.5">
                    ‘{token.word}’은 사전에 없어 근접 수어 ‘{token.signed_as}’로 표시합니다.
                  </p>
                )
              )}
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs text-gray-500 line-clamp-2 flex-1">{token.description}</p>
                {token.dict_url && (
                  <a href={token.dict_url} target="_blank" rel="noopener noreferrer"
                    className="text-[11px] text-gray-400 hover:text-primary-600 whitespace-nowrap">국립국어원 ↗</a>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 옵션: 입모양(mouthing) */}
        {showMouth && (
          <div className="md:col-span-2">
            <p className="text-xs text-gray-500 mb-1">입모양</p>
            <Suspense fallback={<div className="py-10 text-center text-xs text-gray-400">입모양 불러오는 중…</div>}>
              <LipSyncPlayer3D visemes={token.visemes || []} isPlaying={false} />
            </Suspense>
          </div>
        )}
      </div>

      {/* 토큰 순서 (클릭해 이동) */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {tokens.map((t, i) => (
          <button
            key={i}
            onClick={() => { setPlayingAll(false); setCurrent(i) }}
            className={`px-2.5 py-1 rounded-lg text-sm border transition-colors ${
              i === current ? 'border-primary-500 bg-primary-50 text-primary-700 font-semibold'
              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
            }`}
            title={t.type === 'sign' ? '수어' : '지문자'}
          >
            {t.word}
            {t.type === 'fingerspell' && <span className="ml-1 text-[10px] text-gray-400">지문자</span>}
          </button>
        ))}
      </div>

      {/* 출처표시 */}
      <Attribution className="mt-4 border-t border-gray-100 pt-3 text-gray-400" />
    </div>
  )
}

/** 출처 표시 — 수어 영상(CC BY-NC-ND)·지문자 그림(CC BY-SA) 라이선스가 요구하는 표기라 두 형태 모두 남긴다. */
function Attribution({ className = '' }) {
  return (
    <p className={`text-[11px] leading-relaxed ${className}`}>
      수어 영상·데이터 출처: 국립국어원 「한국수어사전」(sldict.korean.go.kr) — CC BY-NC-ND 2.0 KR.
      지문자 손모양(한글): “Korean manual alphabet” © Kwamikagami / Wikimedia Commons — CC BY-SA 3.0.
      영문 지문자(A–Z)는 국제(미국식) 지문자 — “Sign language A–Z”, Wikimedia Commons, Public Domain.
      학습·이해 보조(베타)용이며 공식 통역이 아닙니다.
    </p>
  )
}

/**
 * 나란히 보기(split) — 수어 영상 칸 + 입모양 아바타 칸, 그 아래 단어 이동 줄과 출처.
 * 수어 칸: 영상(반복, 전체 재생 중엔 끝나면 다음 단어) · 영상이 없으면 수형 설명 · 사전 미등재어는 지문자 그림.
 * 입모양 칸: 현재 단어의 입모양 프레임을 MouthAvatar가 반복 재생(컨트롤·오버레이 없음).
 */
function SplitView({ text, loading, error, result, tokens, token, current, playingAll, advance, onPick, onPlayAll }) {
  const ready = !!(text && !loading && !error && result && tokens.length && token)
  let signStage
  if (!text) {
    signStage = <img src="/ui/lp-226-32-hand.svg" alt="" aria-hidden className="size-[72px]" />
  } else if (loading) {
    signStage = <p role="status" className="text-[13.5px] font-bold text-stat-accuracy">수어로 변환 중…</p>
  } else if (error) {
    signStage = <p role="alert" className="px-4 text-center text-[13.5px] text-bad">{error}</p>
  } else if (!ready) {
    signStage = <p className="text-[13.5px] text-ink-muted">변환할 단어가 없습니다.</p>
  } else if (token.type === 'sign' && token.video_url) {
    signStage = (
      <video
        key={token.video_url}
        src={token.video_url}
        autoPlay muted playsInline
        loop={!playingAll}
        onEnded={playingAll ? advance : undefined}
        onError={() => { if (playingAll) advance() }}   // 로드 실패 시에도 전체재생이 멈추지 않게 다음으로
        aria-label={`${token.word} 수어 영상`}
        className="h-full w-full bg-white object-contain"
      />
    )
  } else if (token.type === 'sign') {
    // 영상 해석 실패 → 수형설명 텍스트로 폴백
    signStage = (
      <div className="flex max-h-full flex-col items-center gap-2 overflow-y-auto px-4 text-center text-ink">
        <p className="text-[12px] font-bold text-stat-accuracy">수형 설명</p>
        <p className="text-[13.5px] leading-relaxed">{token.description || '설명 없음'}</p>
      </div>
    )
  } else {
    // 지문자(지화) — 자모별 손모양 이미지(없으면 글자 폴백)
    signStage = (
      <div className="flex max-h-full flex-wrap items-end justify-center gap-2 overflow-y-auto p-3">
        {token.jamo.map((group, gi) => (
          <div key={gi} className="flex items-end gap-1">
            {group.map((jamo, ji) => {
              const img = fingerspellImage(jamo)
              return (
                <div key={ji} className="flex flex-col items-center">
                  {img ? (
                    <img src={img} alt={`지문자 ${jamo}`} loading="lazy" className="h-20 w-auto rounded bg-white object-contain" />
                  ) : (
                    <div className="flex h-20 w-12 items-center justify-center rounded bg-white text-2xl font-bold text-ink">{jamo}</div>
                  )}
                  <span className="mt-1 text-[11px] font-bold text-ink-muted">{jamo}</span>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Players(226:160) — 같은 폭 두 칸, 간격 14 */}
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        <Player label="수어 영상" tone="sign">{signStage}</Player>
        <Player label="입모양 아바타" tone="mouth">
          {ready ? (
            <Suspense fallback={<MouthPlaceholder />}>
              <MouthAvatar frames={token.visemes || []} height={190} />
            </Suspense>
          ) : <MouthPlaceholder />}
        </Player>
      </div>

      {ready && (
        <>
          {/* 단어 이동 — 번역된 단어 순서(누르면 그 단어로) + 전체 재생 */}
          <div className="flex flex-wrap items-center gap-2">
            {tokens.map((t, i) => (
              <button key={i} type="button" onClick={() => onPick(i)} aria-pressed={i === current}
                title={t.type === 'sign' ? '수어' : '지문자'}
                className={`rounded-full px-3.5 py-2 text-[13px] font-bold leading-figma transition ${i === current ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted hover:bg-surface-hover'}`}>
                {t.word}
                {t.type === 'fingerspell' && <span className="ml-1 text-[11px] opacity-70">지문자</span>}
              </button>
            ))}
            <button type="button" onClick={onPlayAll}
              className="ml-auto rounded-full border-1.5 border-line px-3.5 py-2 text-[13px] font-bold leading-figma text-primary-500">
              전체 재생
            </button>
          </div>

          {/* 근접 수어 안내 — 사전에 없는 단어를 다른 수어로 보일 때만. Figma 226:156 밖이지만, 보이는 영상이
              입력한 단어가 아니라는 사실은 숨기지 않는다(맨 위 설명 참고). */}
          {token.type === 'sign' && token.signed_as && (
            /^\d+$/.test(String(token.word))
              ? <p className="text-[12px] leading-relaxed text-ink-muted">숫자 ‘{token.word}’ → 수어 ‘{token.signed_as}’</p>
              : <p className="text-[12px] leading-relaxed text-warn-text">‘{token.word}’은 사전에 없어 근접 수어 ‘{token.signed_as}’로 표시합니다.</p>
          )}
        </>
      )}

      <Attribution className="border-t-1.5 border-line pt-3 text-ink-faint" />
    </div>
  )
}
