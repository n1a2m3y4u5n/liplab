import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listenAPI } from '../api'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'

/**
 * 소리 듣기 결과 — /analysis/listening (GET /api/listen/summary, backend listen_curriculum).
 * 최근 소리 확인(Ling), 소음 속 문장 인식 역치 검사 추이, 훈련 역치(소리만·소리+입모양)와 시청각 이득, 소리 구별 종류별 정답률,
 * 자주 헷갈린 소리와 다음 연습(독화·말하기로 잇기), 최근 7일 연습량(권장: 하루 15~20분, 주 5일).
 * 역치는 낮을수록 시끄러운 곳에서 잘 알아듣는다는 뜻이다. 검사 사이 차이가 작으면 측정 오차일 수 있다고 함께 적는다.
 */

const LING = { m: '음', u: '우', a: '아', i: '이', sh: '쉬', s: '스' }
const dB = (v) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v} dB`)
// 두 검사 차이의 최소 감지 변화(MDC95). 문장 단위(낱말 절반 이상) 1-up-1-down 20문장의 개인 내 SD 약 1.1 dB(Jansen 2012) × 2.77 ≈ 3 dB.
// 검사 절차를 낱말 점수 규칙으로 바꾸면 이 값도 바꾼다(docs/listen-advance-evidence-2026-10.md Q9)
const MDC_DB = 3.0

function Section({ title, children, note }) {
  return (
    <section className="flex flex-col gap-3 rounded-18 border-2 border-line bg-white p-5 lg:rounded-22 lg:p-6">
      <h2 className="text-[17px] font-bold text-ink">{title}</h2>
      {children}
      {note && <p className="text-[12px] leading-[1.6] text-ink-faint">{note}</p>}
    </section>
  )
}

export default function ListeningReport() {
  const navigate = useNavigate()
  const [d, setD] = useState(null)
  const [err, setErr] = useState(false)
  useEffect(() => { listenAPI.summary().then(setD).catch(() => setErr(true)) }, [])
  if (!d && !err) return <LoadingScreen />
  const allTests = d?.tests || []
  const tests = allTests.filter((t) => (t.noise || 'babble') === 'babble')   // 변화 비교는 주 검사(잡담 잡음)끼리
  const otherTests = allTests.filter((t) => t.noise && t.noise !== 'babble')
  const firstT = tests[0]
  const lastT = tests[tests.length - 1]
  const change = tests.length >= 2 ? Math.round((firstT.srt_db - lastT.srt_db) * 10) / 10 : null
  const maxDay = Math.max(1, ...(d?.days || []).map((x) => x.n))
  return (
    <AppShell active="analysis">
      <div data-track="listen" className="mx-auto flex w-full max-w-[752px] flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-[22px] font-bold text-ink lg:text-[26px]">소리 듣기 결과</h1>
          <button type="button" onClick={() => navigate('/learn/path?track=listen')} className="btn-primary px-4 py-2 text-[14px]">연습하러 가기</button>
        </div>
        {err ? (
          <Section title="결과를 불러오지 못했어요"><p className="text-[14px] text-ink-muted">네트워크를 확인하고 다시 열어 주세요.</p></Section>
        ) : (
          <>
            <Section title="소음 속 듣기 검사"
              note="역치는 낱말을 열에 넷쯤 알아듣는 '말과 소음의 크기 차이'예요. 낮을수록 시끄러운 곳에서 잘 알아들어요. 지금 검사 방식에서는 두 검사 사이 3 dB 안쪽의 차이는 측정 오차일 수 있어요. 처음 한두 번은 검사에 익숙해지는 것만으로 1~2 dB 낮아지기도 해요.">
              {allTests.length === 0 && !(d.word_tests || []).length ? (
                <p className="text-[14px] text-ink-muted">아직 검사 기록이 없어요. 소리 듣기 5단계(소음 속 듣기)에서 처음 검사를 할 수 있어요.</p>
              ) : (
                <>
                  <div className="flex flex-col gap-2">
                    {tests.map((t, i) => (
                      <div key={t.session} className="flex items-center justify-between rounded-13 bg-surface-muted px-4 py-2.5 text-[14px]">
                        <span className="text-ink-muted">{i === 0 ? '처음' : `${i + 1}번째`} · 폼 {t.form}{t.noise === 'talker2' ? ' · 두 사람 말소리' : ''}{t.sim === 'ci' ? ' · 인공와우 모의' : ''} · {(t.started_at || '').slice(0, 10)}</span>
                        <span className="font-bold text-ink">{dB(t.srt_db)}</span>
                      </div>
                    ))}
                  </div>
                  {otherTests.map((t) => (
                    <div key={t.session} className="flex items-center justify-between rounded-13 border-2 border-line px-4 py-2 text-[13px]">
                      <span className="text-ink-muted">훈련에 안 쓴 잡음(두 사람 말소리) · 폼 {t.form} · {(t.started_at || '').slice(0, 10)}</span>
                      <span className="font-bold text-ink">{dB(t.srt_db)}</span>
                    </div>
                  ))}
                  {(d.word_tests || []).filter((w) => w.complete).map((w) => (
                    <div key={w.session} className="flex items-center justify-between rounded-13 border-2 border-line px-4 py-2 text-[13px]">
                      <span className="text-ink-muted">낱말 검사(훈련에 안 나온 낱말 20개) · {(w.started_at || '').slice(0, 10)}</span>
                      <span className="font-bold text-ink">{Math.round(w.accuracy * 100)}%</span>
                    </div>
                  ))}
                  {change != null && (
                    <p className="text-[15px] font-bold text-track-dark">
                      {change > 0 ? `처음보다 ${change} dB 낮아졌어요` : change < 0 ? `처음보다 ${-change} dB 높아졌어요` : '처음과 같아요'}
                      {change !== 0 && Math.abs(change) < MDC_DB && <span className="font-normal text-ink-muted"> · 측정 오차 범위 안</span>}
                    </p>
                  )}
                </>
              )}
            </Section>

            <Section title="훈련 중 역치" note="훈련은 소리만이 기본이고 네 번에 한 번 입모양을 함께 보여 줘요. 입모양 이득은 두 조건의 역치 차이예요. 지금 입모양은 3D 아바타라 실제 사람 얼굴의 이득과 다를 수 있어요.">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-14 bg-surface-muted py-3"><p className="text-[12px] text-ink-muted">소리만</p><p className="text-[18px] font-bold text-ink">{dB(d.training.srt_ao_db)}</p><p className="text-[11px] text-ink-faint">{d.training.n_ao}문장</p></div>
                <div className="rounded-14 bg-surface-muted py-3"><p className="text-[12px] text-ink-muted">소리 + 입모양</p><p className="text-[18px] font-bold text-ink">{dB(d.training.srt_av_db)}</p><p className="text-[11px] text-ink-faint">{d.training.n_av}문장</p></div>
                <div className="rounded-14 bg-track-tint py-3"><p className="text-[12px] text-ink-muted">입모양 이득</p><p className="text-[18px] font-bold text-track-dark">{d.training.av_gain_db == null ? '–' : `${d.training.av_gain_db} dB`}</p></div>
              </div>
            </Section>

            <Section title="자주 헷갈린 소리">
              {(d.recommendations || []).length === 0 ? (
                <p className="text-[14px] text-ink-muted">낱말 고르기를 더 하면 자주 헷갈리는 소리를 찾아 드려요.</p>
              ) : d.recommendations.map((r, i) => (
                <div key={i} className="flex flex-col gap-2 rounded-14 border-2 border-line p-4">
                  <p className="text-[14px] text-ink">{r.text}</p>
                  <div className="flex flex-wrap gap-2">
                    {r.routes.map((x) => (
                      <button key={x.to} type="button" onClick={() => navigate(x.to)} className="btn-secondary px-3 py-1.5 text-[13px]">{x.label}</button>
                    ))}
                  </div>
                </div>
              ))}
              {(d.ax_kinds || []).length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {d.ax_kinds.map((k) => (
                    <span key={k.kind} className="rounded-full bg-surface-muted px-3 py-1 text-[12px] text-ink-muted">
                      {k.label} {Math.round((k.correct / k.n) * 100)}% <span className="text-ink-faint">({k.n})</span>
                    </span>
                  ))}
                </div>
              )}
            </Section>

            <Section title="소리 확인" note="지난번에 들리던 소리가 안 들리면 배터리와 기기 상태를 먼저 확인해요. 계속되면 청능사나 병원에 알려요.">
              {!d.last_check ? (
                <p className="text-[14px] text-ink-muted">아직 소리 확인을 하지 않았어요.</p>
              ) : (
                <>
                  <div className="grid grid-cols-6 gap-1.5 text-center">
                    {Object.keys(LING).map((k) => {
                      const ok = d.last_check.results[k]
                      return (
                        <div key={k} className={`rounded-13 py-2 ${ok ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                          <p className="text-[16px] font-bold">{LING[k]}</p>
                          <p className="text-[11px]">{ok ? '들림' : '안 들림'}</p>
                        </div>
                      )
                    })}
                  </div>
                  <p className="text-[12px] text-ink-faint">{(d.last_check.at || '').slice(0, 10)} · 지금까지 {d.n_checks}번 확인</p>
                </>
              )}
            </Section>

            <Section title="최근 7일 연습" note="하루 15~20분, 일주일에 5일쯤이 알맞아요.">
              <div className="flex h-24 items-end gap-2">
                {(d.days || []).map((x) => (
                  <div key={x.date} className="flex flex-1 flex-col items-center gap-1">
                    <div className="w-full rounded-t-md bg-track" style={{ height: `${(x.n / maxDay) * 72}px`, minHeight: x.n ? 4 : 0 }} />
                    <span className="text-[11px] text-ink-faint">{x.date.slice(5).replace('-', '/')}</span>
                  </div>
                ))}
              </div>
            </Section>
          </>
        )}
      </div>
    </AppShell>
  )
}
