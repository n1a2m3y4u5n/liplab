import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import WatermarkCard from '../components/WatermarkCard'
import { reviewAPI, learningAPI } from '../api'
import { relDay } from '../lib/relDay'

/**
 * 복습 탭 (Figma 100:15 · 선택 모드 318:33 · 모바일 239:34 / 318:233) — 오답·북마크 복습 진입 + 복습 항목 리스트.
 * 실데이터: reviewAPI.getDue(예정), learningAPI.getReviewSentences(오답), getBookmarks(북마크 — 독화·발화 모두).
 * 각 항목은 트랙 배지(독화=보라 / 발화=핑크) + 단어 + 사유. 클릭 시 해당 복습 흐름으로 이동.
 * 오른쪽 패널은 복습 탭 구성(스탯 + 오늘의 과제 + 이번 주 복습, 100:113).
 * 목록은 처음에 데스크톱 5개·모바일 3개만 보이고, 더 있으면 아래 원형 버튼(192:21 Scroll hint)으로 모두 펼친다.
 * 상대 날짜('3일 전 · ', lib/relDay)는 오답=가장 최근에 틀린 시각, 예정=마지막으로 다시 푼 시각(없으면 큐에 든 시각),
 * 북마크=북마크한 시각으로 붙인다. 오답 횟수('2회 틀렸어요')는 /api/review-sentences의 wrong_count.
 */
const HERO = {
  // 오답(199:22 / 239:122) — 보라, 워터마크 X(308:32)
  mistake: {
    card: 'border-primary-700 bg-[linear-gradient(137.7deg,var(--brand-light)_0%,var(--brand)_70.92%)] lg:bg-[linear-gradient(154.59deg,var(--brand-light)_0%,var(--brand)_70.92%)]',
    btn: 'text-primary-700 lg:border-primary-line',
    deco: { src: '/ui/lp-100-15-deco-mistake.svg', size: 170, top: -63.01, right: -63.01, hideBelowLg: true },
  },
  // 북마크(199:29 / 239:128) — 파랑, 워터마크 북마크(308:36, -30°)
  bookmark: {
    card: 'border-bookmark-dark bg-[linear-gradient(137.7deg,var(--bookmark-light)_0%,var(--bookmark)_70.92%)] lg:bg-[linear-gradient(154.59deg,var(--bookmark-light)_0%,var(--bookmark)_70.92%)]',
    btn: 'text-bookmark-dark lg:border-bookmark-line',
    deco: { src: '/ui/lp-100-15-deco-bookmark.svg', size: 170, top: -87, right: -87.22, rotate: -30, hideBelowLg: true },
  },
}

/** 복습 시작 카드 — 모바일(239:122)은 172×150 두 장 나란히·전폭 버튼, 데스크톱(199:22)은 168 높이·워터마크. */
function GradientCta({ tone, count, title, sub, subMobile, btn, onClick }) {
  const t = HERO[tone]
  return (
    <WatermarkCard as="button" type="button" onClick={onClick} deco={t.deco}
      className={`h-[150px] min-w-0 flex-1 rounded-18 border-2 border-b-5 px-3.5 pt-[27px] text-left lg:h-[168px] lg:rounded-20 lg:p-6 ${t.card}`}>
      <span className="flex flex-col gap-3 lg:gap-[18px]">
        <span className="flex flex-col gap-3 leading-figma text-white lg:gap-1.5">
          <span className="text-[17px] font-bold tracking-[-0.34px] lg:text-[22px] lg:tracking-[-0.44px]">{title} {count}개</span>
          <span className="text-[12px] opacity-85 lg:text-[13.5px]">
            <span className="lg:hidden">{subMobile}</span>
            <span className="hidden lg:inline">{sub}</span>
          </span>
        </span>
        <span className={`flex w-full items-center justify-center rounded-[11px] bg-white py-2.5 text-[12.5px] font-bold leading-figma lg:w-fit lg:rounded-13 lg:border-2 lg:border-b-4 lg:px-[26px] lg:py-[13px] lg:text-[15px] ${t.btn}`}>{btn}</span>
      </span>
    </WatermarkCard>
  )
}

/** 목록 화살표 — 모바일 5×10(239:154) · 데스크톱 6×12(189:41). 에셋은 칸보다 커서 가운데 겹쳐 둔다(Figma 인셋). */
function RowArrow() {
  return (
    <span aria-hidden className="relative h-2.5 w-[5px] shrink-0 lg:h-3 lg:w-1.5">
      <img src="/ui/lp-239-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2 lg:hidden" />
      <img src="/ui/review-arrow.svg" alt="" className="absolute left-1/2 top-1/2 hidden max-w-none -translate-x-1/2 -translate-y-1/2 lg:block" />
    </span>
  )
}

function ReviewItem({ track, word, meta, rel, onClick, first, selectMode, checked, className = '' }) {
  const isSpeak = track === '발화'
  const badge = (
    <span className={`flex w-[46px] shrink-0 items-center justify-center rounded-[7px] py-1 text-[11px] font-bold leading-figma lg:w-[54px] lg:rounded-lg lg:py-[5px] lg:text-[11.5px] ${isSpeak ? 'bg-speak-tint text-speak-dark' : 'bg-primary-100 text-primary-700'}`}>{track}</span>
  )
  const text = (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5 leading-figma lg:gap-[3px]">
      <span className="truncate text-[15px] font-bold text-ink lg:text-[16px]">{word}</span>
      <span className="text-[11.5px] text-ink-muted lg:text-[12.5px]">{rel ? `${rel} · ${meta}` : meta}</span>
    </span>
  )
  const row = `flex w-full items-center gap-[11px] py-3 text-left lg:gap-3.5 lg:py-4 ${first ? '' : 'border-t-1.5 border-line'} ${className}`
  // 선택 모드(318:33): [체크박스][트랙배지][텍스트] · 화살표 제거 · 클릭=체크 토글.
  if (selectMode) {
    return (
      <button type="button" onClick={onClick} aria-pressed={checked} className={row}>
        {checked
          ? <img src="/ui/lp-318-33-checkbox-on.svg" alt="" className="size-[22px] shrink-0" />
          : <span className="size-[22px] shrink-0 rounded-[7px] border-2 border-line" />}
        {badge}
        {text}
      </button>
    )
  }
  // 기본 모드: 화살표 · 클릭=해당 복습 화면으로 이동.
  return (
    <button type="button" onClick={onClick} className={row}>
      {badge}
      {text}
      <RowArrow />
    </button>
  )
}

/** 지우기 버튼(317:34 / 모바일 317:42) — 휴지통 아이콘 + 글자, 1.5px 테두리 알약. */
function EraseButton({ onClick, className = '' }) {
  return (
    <button type="button" onClick={onClick}
      className={`items-center gap-1.5 rounded-full border-1.5 border-line py-[7px] pl-3 pr-3.5 text-[12.5px] font-bold leading-figma text-ink-muted lg:py-2 lg:text-[13.5px] ${className}`}>
      <img src="/ui/lp-100-15-trash.svg" alt="" className="size-3.5 lg:size-[15px]" />
      지우기
    </button>
  )
}

// 목록 첫 화면 개수(Figma 항목 수) — 모바일 3 · 데스크톱 5
const PEEK_MOBILE = 3
const PEEK_DESKTOP = 5

export default function ReviewTab() {
  const navigate = useNavigate()
  const [due, setDue] = useState(0)
  const [wrong, setWrong] = useState(0)
  const [marks, setMarks] = useState(0)
  const [items, setItems] = useState([])
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(false)       // 스크롤 힌트로 목록 전체 펼침
  const [selectMode, setSelectMode] = useState(false)  // 복습 선택(삭제) 모드 UI 상태
  const [selected, setSelected] = useState(new Set())  // 선택된 항목 id 집합

  useEffect(() => {
    let on = true
    Promise.all([
      reviewAPI.getDue().catch(() => ({ items: [] })),
      learningAPI.getReviewSentences().catch(() => []),
      learningAPI.getBookmarks().catch(() => []),
    ]).then(([dueRes, wrongRes, bmRes]) => {
      if (!on) return
      const dueItems = dueRes.items || []
      const wrongArr = Array.isArray(wrongRes) ? wrongRes : (wrongRes.items || [])
      const bmArr = Array.isArray(bmRes) ? bmRes : (bmRes.items || [])
      setDue(dueItems.length)
      setWrong(wrongArr.length)
      setMarks(bmArr.length)
      const meta = (x, kind) => {
        if (kind === 'bookmark') return '북마크를 했어요'
        if (kind === 'wrong') return x.wrong_count ? `${x.wrong_count}회 틀렸어요` : '틀렸어요'
        return '다시 볼 항목'
      }
      const norm = (arr, kind) => arr.map((x, i) => ({
        id: `${kind}-${x.id ?? i}`,
        track: (x.domain === 'speak' || x.track === 'speak') ? '발화' : '독화',
        // 예정 항목(/api/review/due)은 {kind, ref, name} — 입모양은 레슨 이름, 단어는 ref가 곧 단어
        word: x.word || x.sentence || x.text || x.target || x.name || x.ref || '복습 항목',
        meta: meta(x, kind),
        rel: relDay(x.updated_at || x.created_at),
        kind,
        raw: x,   // 삭제 요청에 쓰는 원래 식별자(북마크 id, 예정 항목 kind·ref)
      }))
      setItems([...norm(wrongArr, 'wrong'), ...norm(dueItems, 'due'), ...norm(bmArr, 'bookmark')])
    })
    return () => { on = false }
  }, [])

  const shown = items.filter((it) => filter === 'all' || (filter === 'wrong' ? it.kind !== 'bookmark' : it.kind === 'bookmark'))
  const chips = [
    { key: 'all', label: '전체', n: items.length },
    { key: 'wrong', label: '오답', n: wrong + due },
    { key: 'bookmark', label: '북마크', n: marks },
  ]
  // 펼치기 전에는 모바일 3개·데스크톱 5개만 — 나머지는 CSS로 숨기고, 넘치는 쪽 화면에만 스크롤 힌트를 둔다.
  const hintMobile = !expanded && shown.length > PEEK_MOBILE
  const hintDesktop = !expanded && shown.length > PEEK_DESKTOP
  const peekClass = (i) => {
    if (expanded || i < PEEK_MOBILE) return ''
    return i < PEEK_DESKTOP ? 'hidden lg:flex' : 'hidden'
  }
  const deleteShown = selectMode && selected.size > 0
  // 카드 아래 여백 — 스크롤 힌트가 마지막이면 힌트가 여백을 대신한다(239:134 pb 4 · 189:21 pb 0).
  const padBottom = `${hintMobile && !deleteShown ? 'pb-1' : selectMode ? 'pb-5' : 'pb-[18px]'} ${hintDesktop && !deleteShown ? 'lg:pb-0' : 'lg:pb-[22px]'}`

  const exitSelect = () => { setSelectMode(false); setSelected(new Set()) }
  const toggleItem = (id) => setSelected((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  // 현재 보이는 항목 전체 선택 ↔ 이미 전체면 해제.
  const toggleAll = () => setSelected((prev) => {
    const allOn = shown.length > 0 && shown.every((it) => prev.has(it.id))
    if (allOn) {
      const next = new Set(prev)
      shown.forEach((it) => next.delete(it.id))
      return next
    }
    const next = new Set(prev)
    shown.forEach((it) => next.add(it.id))
    return next
  })
  // 북마크는 서버에서 지우고, 복습 예정 항목은 예정 목록에서 뺀다. 최근 오답 문장은 시도 기록에서 계산되는
  // 목록이라 지울 서버 항목이 없어 이 화면에서만 숨긴다(다시 틀리지 않으면 다음부터는 나오지 않는다).
  const deleteSelected = () => {
    const picked = items.filter((it) => selected.has(it.id))
    for (const it of picked) {
      if (it.kind === 'bookmark' && it.raw?.id != null) learningAPI.removeBookmark(it.raw.id).catch(() => {})
      else if (it.kind === 'due' && it.raw?.kind && it.raw?.ref != null) reviewAPI.removeDue(it.raw.kind, it.raw.ref).catch(() => {})
    }
    setItems((prev) => prev.filter((it) => !selected.has(it.id)))
    setMarks((n) => Math.max(0, n - picked.filter((it) => it.kind === 'bookmark').length))
    setDue((n) => Math.max(0, n - picked.filter((it) => it.kind === 'due').length))
    setWrong((n) => Math.max(0, n - picked.filter((it) => it.kind === 'wrong').length))
    exitSelect()
  }
  const openItem = (it) => {
    if (it.kind !== 'bookmark') return navigate('/review/mistakes')
    // 발화 북마크는 말하기 복습(/api/speak/review가 발화 북마크를 함께 모은다)으로 간다.
    return navigate(it.track === '발화' ? '/review/speaking' : '/review/saved')
  }

  return (
    <AppShell active="review" title="복습" rail="review">
      <div className="flex w-full gap-2.5 lg:gap-3.5">
        <GradientCta tone="mistake" count={wrong + due} title="복습할 오답" sub="오답 다시보기" subMobile="약 3분이면 끝나요"
          btn="오답 복습하기" onClick={() => navigate('/review/mistakes')} />
        <GradientCta tone="bookmark" count={marks} title="복습할 북마크" sub="북마크 다시보기" subMobile="저장해둔 문장이에요"
          btn="북마크 복습하기" onClick={() => navigate('/review/saved')} />
      </div>

      {/* 복습할 항목 (189:21 / 239:134) */}
      <section className={`flex w-full flex-col rounded-16 border-2 border-line bg-white lg:rounded-18 ${selectMode ? 'gap-3 px-5 pt-5' : 'gap-3 px-[18px] pt-[18px] lg:gap-4'} lg:px-[22px] lg:pt-[22px] ${padBottom}`}>
        {/* 모바일 머리 행(239:135 / 318:266) — 제목 + 지우기 또는 취소 */}
        <div className="flex items-center justify-between lg:hidden">
          <p className="text-[16px] font-bold leading-figma text-ink">복습할 항목</p>
          {selectMode ? (
            <button type="button" onClick={exitSelect}
              className="rounded-full border-1.5 border-line px-3.5 py-[7px] text-[12.5px] font-bold leading-figma text-ink-muted">취소</button>
          ) : shown.length > 0 ? (
            <EraseButton onClick={() => setSelectMode(true)} className="flex" />
          ) : null}
        </div>

        {/* 필터 줄 — 칩 + (데스크톱) 지우기 · 선택 모드면 전체 선택(+ 데스크톱 취소) */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-[7px] lg:gap-2">
            {chips.map((c) => (
              <button key={c.key} type="button" onClick={() => setFilter(c.key)} aria-pressed={filter === c.key}
                className={`flex items-center gap-[5px] rounded-full px-[13px] py-2 font-bold leading-figma lg:gap-1.5 lg:px-4 lg:py-[9px] ${filter === c.key ? 'bg-primary-500 text-white' : 'bg-surface-sunken text-ink-muted'}`}>
                <span className="text-[12.5px] lg:text-[13.5px]">{c.label}</span>
                <span className={`text-[11px] lg:text-[12px] ${filter === c.key ? 'text-white/75' : 'text-ink-ghost'}`}>{c.n}</span>
              </button>
            ))}
          </div>
          {selectMode ? (
            <div className="flex shrink-0 items-center gap-3.5">
              <button type="button" onClick={toggleAll} className="text-[12.5px] font-bold leading-figma text-primary-500 lg:text-[13.5px]">전체 선택</button>
              <button type="button" onClick={exitSelect}
                className="hidden rounded-full border-1.5 border-line px-4 py-2 text-[13.5px] font-bold leading-figma text-ink-muted lg:block">취소</button>
            </div>
          ) : shown.length > 0 ? (
            <EraseButton onClick={() => setSelectMode(true)} className="hidden shrink-0 lg:flex" />
          ) : null}
        </div>

        <div className="flex flex-col">
          {shown.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-muted">복습할 항목이 없어요. 잘하고 있어요!</p>
          ) : shown.map((it, i) => (
            <ReviewItem key={it.id} {...it} first={i === 0} className={peekClass(i)}
              selectMode={selectMode} checked={selected.has(it.id)}
              onClick={() => (selectMode ? toggleItem(it.id) : openItem(it))} />
          ))}
        </div>

        {/* 스크롤 힌트(192:21 / 320:36) — 가운데 38px 원 버튼(에셋 52px: 그림자 포함), 누르면 목록을 모두 펼친다 */}
        {(hintMobile || hintDesktop) && (
          <div className={`relative h-[52px] w-full shrink-0 ${hintDesktop ? '' : 'lg:hidden'}`}>
            <button type="button" onClick={() => setExpanded(true)} aria-label="복습할 항목 더 보기"
              className="absolute left-1/2 top-2 size-[38px] -translate-x-1/2 rounded-full">
              <img src="/ui/lp-318-33-scroll-more.svg" alt="" className="absolute max-w-none"
                style={{ top: '-10.53%', left: '-18.42%', width: '136.84%', height: '136.85%' }} />
            </button>
          </div>
        )}

        {deleteShown && (
          <button type="button" onClick={deleteSelected} className="btn-bad w-full py-[15px] text-[16px]">
            선택한 {selected.size}개 지우기
          </button>
        )}
      </section>
    </AppShell>
  )
}
