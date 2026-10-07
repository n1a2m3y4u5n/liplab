import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listenAPI } from '../api'
import AppShell from '../components/AppShell'
import { MDC_DB, splitTests, srtChange, testRows, axKindRows, confusionRows, dayBars } from '../lib/listenReport'
import { fmtDb } from '../lib/listenView'

/**
 * 소리 듣기 결과: /analysis/listening (GET /api/listen/summary, backend listen_curriculum). 계산은 lib/listenReport.js.
 * 위에서부터: 소음 속 듣기 검사(주 결과, 첫 검사와 비교) · 훈련 중 역치(소리만·소리+입모양) · 자주 헷갈린 소리와 다음 연습 ·
 * 소리 확인(Ling) · 최근 7일 연습량(권장: 하루 15~20분, 주 5일). 칸마다 기록이 없을 때 할 일을 적는다.
 * 역치는 낮을수록 시끄러운 곳에서 잘 알아듣는다는 뜻이다. 검사 사이 차이가 MDC(3 dB)보다 작으면 측정 오차일 수 있다고 함께 적는다.
 * 색은 트랙 청록 + 정오 초록·빨강 + 회색만 쓴다.
 */

const LING = { m: '음', u: '우', a: '아', i: '이', sh: '쉬', s: '스' }
const NOTICE = '소리 듣기는 청력을 진단하거나 치료하지 않아요. 보청기·인공와우 조절은 청능사나 병원에서 해요.'
const day = (iso) => (iso || '').slice(0, 10).replaceAll('-', '.')

function Section({ title, children, note, action }) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-18 border-2 border-line bg-white p-5 lg:rounded-22 lg:p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[17px] font-bold text-ink lg:text-[18px]">{title}</h2>
        {action}
      </div>
      {children}
      {note && <p className="break-keep text-[12px] leading-[1.6] text-ink-faint">{note}</p>}
    </section>
  )
}

function Empty({ text, to, label, navigate }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-14 bg-surface-sunken px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="break-keep text-[14px] leading-[1.6] text-ink-muted">{text}</p>
      {to && <button type="button" onClick={() => navigate(to)} className="btn-secondary min-h-[44px] shrink-0 px-4 py-2 text-[13px] text-track-dark">{label}</button>}
    </div>
  )
}

function Stat({ label, value, sub, main }) {
  return (
    <div className={`flex min-w-0 flex-col gap-1 rounded-14 px-3 py-3 ${main ? 'bg-track-tint' : 'bg-surface-sunken'}`}>
      <p className="break-keep text-[12px] font-bold text-ink-muted">{label}</p>
      <p className={`text-[18px] font-bold leading-figma lg:text-[20px] ${main ? 'text-track-dark' : 'text-ink'}`}>{value}</p>
      {sub && <p className="text-[12px] text-ink-faint">{sub}</p>}
    </div>
  )
}

function ReportSkeleton() {
  return (
    <div role="status" aria-label="불러오는 중" className="flex animate-pulse-slow flex-col gap-4">
      {[148, 120, 160].map((h, i) => <div key={i} className="rounded-18 border-2 border-line bg-white lg:rounded-22" style={{ height: h }} />)}
      <span className="sr-only">불러오는 중이에요</span>
    </div>
  )
}

export default function ListeningReport() {
  const navigate = useNavigate()
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const load = useCallback(() => {
    setErr(false)
    setD(null)
    listenAPI.summary().then(setD).catch(() => setErr(true))
  }, [])
  useEffect(() => { load() }, [load])

  const { main, other } = splitTests(d?.tests)
  const change = srtChange(main)
  const latest = main[main.length - 1]
  const { rows, hidden } = testRows(main, 5, showAll)
  const wordTests = (d?.word_tests || []).filter((w) => w.complete)
  const ax = axKindRows(d?.ax_kinds)
  const conf = confusionRows(d?.confusions)
  const week = dayBars(d?.days)
  const tr = d?.training || {}
  return (
    <AppShell active="analysis">
      <div data-track="listen" className="mx-auto flex w-full max-w-[752px] flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="min-w-0 text-[22px] font-bold text-ink lg:text-[26px]">소리 듣기 결과</h1>
          <button type="button" onClick={() => navigate('/learn/path?track=listen')} className="btn-primary min-h-[44px] shrink-0 px-4 py-2 text-[14px]">연습하러 가기</button>
        </div>
        {err ? (
          <Section title="결과를 불러오지 못했어요">
            <p className="text-[14px] text-ink-muted">인터넷 연결을 확인하고 다시 불러와 주세요.</p>
            <button type="button" onClick={load} className="btn-primary self-start px-5 py-2.5 text-[14px]">다시 불러오기</button>
          </Section>
        ) : !d ? <ReportSkeleton /> : (
          <>
            <Section title="소음 속 듣기 검사"
              note={`역치는 낱말을 열에 넷쯤 알아듣는 '말과 소음의 크기 차이'예요. 낮을수록 시끄러운 곳에서 잘 알아들어요. 두 검사 사이 ${MDC_DB} dB 안쪽의 차이는 측정 오차일 수 있어요. 처음 한두 번은 검사에 익숙해지는 것만으로 1~2 dB 낮아지기도 해요.`}>
              {main.length === 0 && other.length === 0 && wordTests.length === 0 ? (
                <Empty navigate={navigate} text="아직 검사 기록이 없어요. 5단계 소음 속 듣기에서 처음 검사를 할 수 있어요." to="/learn/listening?stage=4" label="검사하러 가기" />
              ) : (
                <>
                  {latest && (
                    <div className="grid grid-cols-2 gap-2">
                      <Stat label="최근 역치" value={fmtDb(latest.srt_db)} sub={day(latest.started_at)} main />
                      <Stat label="처음과 비교" value={change ? (change.change > 0 ? `${change.change} dB 낮아짐` : change.change < 0 ? `${-change.change} dB 높아짐` : '같음') : '–'}
                        sub={change ? (change.withinError ? '측정 오차 범위 안' : `검사 ${main.length}번`) : '두 번째 검사부터 보여요'} />
                    </div>
                  )}
                  {rows.length > 0 && (
                    <div className="overflow-hidden rounded-14 border-2 border-line">
                      <table className="w-full text-left text-[14px]">
                        <caption className="sr-only">검사 기록, 최근 것부터</caption>
                        <thead className="bg-surface-sunken text-[12px] text-ink-muted">
                          <tr><th scope="col" className="px-3 py-2 font-bold">회차</th><th scope="col" className="px-3 py-2 font-bold">날짜</th>
                            <th scope="col" className="px-3 py-2 font-bold">폼</th><th scope="col" className="px-3 py-2 text-right font-bold">역치</th></tr>
                        </thead>
                        <tbody>
                          {rows.map((t) => (
                            <tr key={t.session} className="border-t-2 border-line">
                              <td className="px-3 py-2.5 text-ink">{t.first ? '처음' : `${t.order}번째`}{t.sim === 'ci' ? <span className="text-ink-faint"> · 모의</span> : null}</td>
                              <td className="px-3 py-2.5 text-ink-muted">{day(t.started_at)}</td>
                              <td className="px-3 py-2.5 text-ink-muted">{t.form}</td>
                              <td className="px-3 py-2.5 text-right font-bold text-ink">{fmtDb(t.srt_db)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {(hidden > 0 || showAll) && main.length > 5 && (
                        <button type="button" onClick={() => setShowAll((v) => !v)} className="min-h-[44px] w-full border-t-2 border-line text-[13px] font-bold text-track-dark">
                          {showAll ? '최근 것만 보기' : `가운데 ${hidden}번 더 보기`}
                        </button>
                      )}
                    </div>
                  )}
                  {(other.length > 0 || wordTests.length > 0) && (
                    <div className="flex flex-col gap-1.5">
                      <p className="text-[13px] font-bold text-ink-muted">훈련에 안 쓴 자료로 한 검사</p>
                      {other.map((t) => (
                        <div key={t.session} className="flex items-center justify-between gap-3 rounded-13 bg-surface-sunken px-3.5 py-2.5 text-[13px]">
                          <span className="min-w-0 break-keep text-ink-muted">두 사람 말소리 잡음 · 폼 {t.form} · {day(t.started_at)}</span>
                          <span className="shrink-0 font-bold text-ink">{fmtDb(t.srt_db)}</span>
                        </div>
                      ))}
                      {wordTests.map((w) => (
                        <div key={w.session} className="flex items-center justify-between gap-3 rounded-13 bg-surface-sunken px-3.5 py-2.5 text-[13px]">
                          <span className="min-w-0 break-keep text-ink-muted">낱말 검사(새 낱말 20개) · {day(w.started_at)}</span>
                          <span className="shrink-0 font-bold text-ink">{Math.round(w.accuracy * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </Section>

            <Section title="훈련 중 역치" note="훈련은 소리만이 기본이고 네 번에 한 번 입모양을 함께 보여 줘요. 입모양 이득은 두 역치의 차이예요. 입모양은 3D 아바타라 실제 얼굴과 다를 수 있어요.">
              {!tr.n_ao && !tr.n_av ? (
                <Empty navigate={navigate} text="5단계 소음 속 듣기를 하면 여기에 역치가 보여요." to="/learn/listening?stage=4" label="소음 속 듣기" />
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  <Stat label="소리만" value={fmtDb(tr.srt_ao_db)} sub={`${tr.n_ao}문장`} />
                  <Stat label="소리 + 입모양" value={fmtDb(tr.srt_av_db)} sub={tr.srt_av_db == null ? '8문장부터' : `${tr.n_av}문장`} />
                  <Stat label="입모양 이득" value={tr.av_gain_db == null ? '–' : `${tr.av_gain_db} dB`} main />
                </div>
              )}
            </Section>

            <Section title="자주 헷갈린 소리">
              {(d.recommendations || []).length === 0 && conf.length === 0 ? (
                <Empty navigate={navigate} text="낱말 고르기를 더 하면 자주 헷갈리는 소리를 찾아 드려요." to="/learn/listening?stage=2" label="낱말 고르기" />
              ) : (
                <>
                  {conf.length > 0 && (
                    <div className="overflow-hidden rounded-14 border-2 border-line">
                      <table className="w-full text-left text-[14px]">
                        <caption className="sr-only">낱말 고르기에서 헷갈린 소리 짝, 많은 순</caption>
                        <thead className="bg-surface-sunken text-[12px] text-ink-muted">
                          <tr><th scope="col" className="px-3 py-2 font-bold">자리</th><th scope="col" className="px-3 py-2 font-bold">들려준 소리 → 고른 소리</th>
                            <th scope="col" className="px-3 py-2 text-right font-bold">횟수</th></tr>
                        </thead>
                        <tbody>
                          {conf.map((c) => (
                            <tr key={`${c.where}${c.target}${c.heard}`} className="border-t-2 border-line">
                              <td className="px-3 py-2.5 text-ink-muted">{c.where}</td>
                              <td className="px-3 py-2.5 font-bold text-ink">{c.target} → <span className="text-bad-text">{c.heard}</span></td>
                              <td className="px-3 py-2.5 text-right text-ink">{c.n}번</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {(d.recommendations || []).map((r, i) => (
                    <div key={i} className="flex flex-col gap-2.5 rounded-14 bg-surface-sunken p-4">
                      <p className="break-keep text-[14px] leading-[1.6] text-ink">{r.text}</p>
                      <div className="flex flex-wrap gap-2">
                        {r.routes.map((x) => (
                          <button key={x.to} type="button" onClick={() => navigate(x.to)} className="btn-secondary min-h-[44px] px-3.5 py-2 text-[13px] text-track-dark">{x.label}</button>
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}
              {ax.length > 0 && (
                <div className="flex flex-col gap-2 pt-1">
                  <p className="text-[13px] font-bold text-ink-muted">소리 구별 종류별 정답률</p>
                  {ax.map((k) => (
                    <div key={k.kind} className="grid grid-cols-[minmax(0,7.5em)_1fr_auto] items-center gap-3 text-[13px]">
                      <span className="truncate text-ink">{k.label}</span>
                      <div className="h-2.5 overflow-hidden rounded-full bg-fill" aria-hidden>
                        <div className={`h-full rounded-full bg-track ${k.few ? 'opacity-40' : ''}`} style={{ width: `${Math.max(2, k.pct)}%` }} />
                      </div>
                      <span className="w-[6.5em] text-right font-bold text-ink">{k.pct}%<span className="font-normal text-ink-faint"> · {k.n}번</span></span>
                    </div>
                  ))}
                  {ax.some((k) => k.few) && <p className="text-[12px] text-ink-faint">흐린 막대는 5번 미만이라 아직 믿기 어려워요.</p>}
                </div>
              )}
            </Section>

            <Section title="소리 확인" note="지난번에 들리던 소리가 안 들리면 배터리와 기기 상태를 먼저 확인해요. 계속되면 청능사나 병원에 알려요.">
              {!d.last_check ? (
                <Empty navigate={navigate} text="아직 소리 확인을 하지 않았어요. 연습 전에 여섯 소리를 확인해 보세요." to="/learn/listening?stage=0" label="소리 확인" />
              ) : (
                <>
                  <div className="grid grid-cols-3 gap-1.5 text-center sm:grid-cols-6">
                    {Object.keys(LING).map((k) => {
                      const ok = d.last_check.results[k]
                      return (
                        <div key={k} className={`rounded-13 py-2.5 ${ok ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                          <p className="text-[17px] font-bold">{LING[k]}</p>
                          <p className="text-[12px] font-bold">{ok ? '들림' : '안 들림'}</p>
                        </div>
                      )
                    })}
                  </div>
                  {d.last_check.summary?.dropped?.length > 0 && (
                    <p className="break-keep rounded-13 bg-surface-sunken px-4 py-3 text-[14px] font-bold leading-[1.6] text-ink">
                      지난번에 들리던 {d.last_check.summary.dropped.map((x) => LING[x]).join('·')} 소리가 이번에는 안 들렸어요.
                    </p>
                  )}
                  <p className="text-[12px] text-ink-faint">{day(d.last_check.at)} · 지금까지 {d.n_checks}번 확인</p>
                </>
              )}
            </Section>

            <Section title="최근 7일 연습" note="막대는 날마다 푼 문항 수예요. 하루 15~20분, 일주일에 5일쯤이 알맞아요.">
              {week.total === 0 ? (
                <Empty navigate={navigate} text="지난 7일 동안 연습한 기록이 없어요." to="/learn/path?track=listen" label="연습하러 가기" />
              ) : (
                <>
                  <p className="text-[14px] text-ink"><b className="text-track-dark">7일 중 {week.activeDays}일</b> 연습했어요 · 모두 {week.total}문항</p>
                  <div className="flex h-[112px] items-end gap-1.5 sm:gap-2" role="img"
                    aria-label={week.bars.map((b) => `${b.label} ${b.n}문항`).join(', ')}>
                    {week.bars.map((b) => (
                      <div key={b.date} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
                        <span className="text-[12px] font-bold text-ink-muted">{b.n || ''}</span>
                        <div className={`w-full max-w-[44px] rounded-t-md ${b.n ? 'bg-track' : 'bg-fill'}`} style={{ height: b.n ? `${Math.max(6, b.pct * 0.64)}px` : '3px' }} />
                        <span className={`text-[12px] ${b.today ? 'font-bold text-track-dark' : 'text-ink-faint'}`}>{b.label}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Section>

            <p className="break-keep px-1 pb-2 text-center text-[12px] leading-[1.6] text-ink-faint">{NOTICE}</p>
          </>
        )}
      </div>
    </AppShell>
  )
}
