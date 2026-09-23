import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { evalAPI } from '../api'
import LearnHeader from '../components/LearnHeader'

// 학습 효과 리포트 — 개인별 시행 기록으로 학습곡선·단계 도달 시행수·초기 대비 최근 향상도를
// 시각화한다. 공모전 평가/효과성 근거용. 데이터가 적으면 각 카드가 '쌓이면 표시' 상태를 그린다.

function Card({ title, hint, children }) {
  return (
    <section className="rounded-[22px] border border-slate-200 bg-white p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-bold text-slate-800">{title}</h2>
        {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Metric({ label, value, unit, tone = 'text-violet-700' }) {
  return (
    <article className="rounded-[22px] border border-slate-200 bg-white p-5">
      <p className="text-xs font-bold text-slate-400">{label}</p>
      <p className={`mt-2 text-3xl font-black ${tone}`}>
        {value ?? '—'}{value != null && unit ? <span className="ml-0.5 text-base font-bold text-slate-400">{unit}</span> : null}
      </p>
    </article>
  )
}

function EmptyLine({ children }) {
  return <p className="py-6 text-center text-xs text-slate-400">{children}</p>
}

// 시행 순서(bin)별 값(0~1 또는 0~100)을 꺾은선으로. vals: [{bin,n,value}]
function LineChart({ series, max = 1, fmt = (v) => `${Math.round(v * 100)}%`, color = '#7c3aed' }) {
  if (!series || series.length === 0) return <EmptyLine>데이터가 쌓이면 학습곡선이 표시됩니다.</EmptyLine>
  const W = 520, H = 140, PL = 34, PR = 12, PT = 12, PB = 22
  const n = series.length
  const x = (i) => PL + (n === 1 ? (W - PL - PR) / 2 : (i * (W - PL - PR)) / (n - 1))
  const y = (v) => PT + (1 - Math.min(v, max) / max) * (H - PT - PB)
  const pts = series.map((s, i) => `${x(i)},${y(s.value)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="학습곡선">
      {[0, 0.5, 1].map((g) => (
        <g key={g}>
          <line x1={PL} x2={W - PR} y1={y(g * max)} y2={y(g * max)} stroke="#e2e8f0" strokeWidth="1" />
          <text x={PL - 6} y={y(g * max) + 3} textAnchor="end" fontSize="9" fill="#94a3b8">{fmt(g * max)}</text>
        </g>
      ))}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {series.map((s, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(s.value)} r="3.5" fill={color} />
          <text x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" fill="#94a3b8">{i + 1}</text>
        </g>
      ))}
    </svg>
  )
}

function BarRow({ label, value, max = 100, unit = '%', sub }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-700">{label}</span>
        <span className="tabular-nums text-slate-500">{value}{unit}{sub ? <span className="ml-1 text-slate-400">{sub}</span> : null}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-violet-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function EvalReport() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [prog, setProg] = useState(null)   // 통제 향상도(축 I, 사전 A vs 사후 B)
  const [dl, setDl] = useState(false)      // 공개 자원 내려받기 상태(축 C)

  // 축 C 공개 표준 자원(동구형이음 사전·난이도지수·지각공간·평가셋)을 판본과 함께 JSON으로 내려받는다.
  const downloadResources = async () => {
    setDl(true)
    try {
      const res = await evalAPI.resources()
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `liplab-perceptual-resources-${res?.meta?.semver || 'latest'}.json`
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch { /* 내려받기 실패는 조용히 무시 */ } finally { setDl(false) }
  }

  useEffect(() => {
    evalAPI.summary().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    evalAPI.progression().then(setProg).catch(() => setProg(null))
  }, [])

  const ov = data?.overview
  const bvr = data?.baseline_vs_recent
  const noData = ov && ov.total_trials === 0 && ov.total_sentences === 0

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="etc"
        title="학습 효과 리포트"
        description="시행 기록으로 학습곡선과 단계별 도달 시행수, 초기 대비 최근 향상도를 확인합니다."
        maxWidth="max-w-5xl"
        onExit={() => navigate('/analysis')}
      />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-5">
        {/* 표준검사 진입(축 I) — 난이도를 맞춘 동형 폼 A(사전)·B(사후). 훈련 전 A, 훈련 뒤 B를 보면
            아래 '통제 향상도'에 변화가 나온다. 배치검사 화면에는 모드 전환기가 없으므로 여기서 연다. */}
        <div className="flex flex-col gap-3 rounded-[24px] border border-slate-200 bg-white p-5 sm:flex-row sm:items-center">
          <div className="flex-1">
            <p className="text-sm font-bold text-slate-800">표준검사 사전·사후</p>
            <p className="mt-0.5 text-xs text-slate-500">훈련 전에 사전(A), 훈련 뒤에 사후(B)를 한 번씩 보면 향상도를 비교해요. 각 8문항.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => navigate('/learn/placement?form=A')} className="btn-secondary !py-2.5 px-4 text-[14px]">사전 검사(A)</button>
            <button type="button" onClick={() => navigate('/learn/placement?form=B')} className="btn-primary !py-2.5 px-4 text-[14px]">사후 검사(B)</button>
          </div>
        </div>
        {loading ? (
          <div className="rounded-[24px] border border-slate-200 bg-white py-20 text-center text-sm text-slate-400">리포트를 불러오는 중…</div>
        ) : !data ? (
          <div className="rounded-[24px] border border-slate-200 bg-white py-16 text-center text-sm text-slate-500">리포트를 불러오지 못했습니다.</div>
        ) : noData ? (
          <div className="rounded-[24px] border border-slate-200 bg-white px-5 py-16 text-center text-sm text-slate-500">
            아직 학습 기록이 없습니다. 입모양 인지·단어·문장 연습을 진행하면 학습곡선과 향상도가 여기에 표시됩니다.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="총 시행" value={ov.total_trials} unit="회" tone="text-slate-800" />
              <Metric label="시행 정확도" value={ov.trial_accuracy} unit="%" />
              <Metric label="문장 연습" value={ov.total_sentences} unit="회" tone="text-slate-800" />
              <Metric label="문장 평균점수" value={ov.sentence_avg_score} unit="점" tone="text-rose-600" />
            </div>

            <Card title="학습곡선 (선다형 정확도)" hint="시행을 시간순 구간으로 나눈 정확도">
              <LineChart series={data.learning_curve} max={1} />
            </Card>

            {/* 통제 향상도(축 I) — 동형 폼 사전(A)·사후(B) 비교. 배치검사에서 A/B를 모두 마치면 표시 */}
            {prog?.available && (
              <Card title="통제 향상도 (표준검사 사전·사후)"
                hint={prog.homogeneous ? '동형 폼 A(사전)·B(사후) 비교' : '가장 이른·최근 검사 비교'}>
                <div className="flex flex-wrap items-end gap-6">
                  <div>
                    <p className="text-[11px] font-bold text-slate-400">사전 정확도</p>
                    <p className="text-2xl font-black text-slate-500">{Math.round(prog.pre.accuracy * 100)}%</p>
                  </div>
                  <div className="pb-1 text-slate-300">→</div>
                  <div>
                    <p className="text-[11px] font-bold text-slate-400">사후 정확도</p>
                    <p className="text-2xl font-black text-violet-700">{Math.round(prog.post.accuracy * 100)}%</p>
                  </div>
                  <div className="pb-1">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${prog.accuracy_delta >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                      {prog.accuracy_delta >= 0 ? '+' : ''}{Math.round(prog.accuracy_delta * 100)}%p
                    </span>
                  </div>
                  <div className="pb-1 text-xs text-slate-500">
                    수준 Lv.{prog.pre.level} → Lv.{prog.post.level}
                  </div>
                </div>
                {prog.error_phoneme_change?.some((e) => e.before || e.after) && (
                  <div className="mt-3">
                    <p className="mb-1 text-[11px] font-bold text-slate-400">음소별 오류 변화 (사전→사후)</p>
                    <div className="flex flex-wrap gap-1.5">
                      {prog.error_phoneme_change.filter((e) => e.before || e.after).slice(0, 8).map((e) => (
                        <span key={e.phoneme}
                          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${e.delta < 0 ? 'bg-emerald-50 text-emerald-700' : e.delta > 0 ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-500'}`}>
                          {e.phoneme} {e.before}→{e.after}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            <div className="grid gap-5 md:grid-cols-2">
              <Card title="초기 대비 최근 향상도" hint={bvr ? `각 ${bvr.n_each}시행` : '최소 9시행 필요'}>
                {bvr ? (
                  <div>
                    <div className="flex items-end gap-6">
                      <div>
                        <p className="text-[11px] font-bold text-slate-400">초기 1/3</p>
                        <p className="text-2xl font-black text-slate-500">{bvr.baseline_acc}%</p>
                      </div>
                      <div className="pb-1 text-slate-300">→</div>
                      <div>
                        <p className="text-[11px] font-bold text-slate-400">최근 1/3</p>
                        <p className="text-2xl font-black text-violet-700">{bvr.recent_acc}%</p>
                      </div>
                      <div className="pb-1">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${bvr.delta_pp >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                          {bvr.delta_pp >= 0 ? '+' : ''}{bvr.delta_pp}%p
                        </span>
                      </div>
                    </div>
                    <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{bvr.note}</p>
                  </div>
                ) : <EmptyLine>선다형 시행이 9회 이상 쌓이면 향상도가 표시됩니다.</EmptyLine>}
              </Card>

              <Card title="유형별 정확도">
                {data.by_item_type?.length ? (
                  data.by_item_type.map((it) => (
                    <BarRow key={it.item_type} label={it.label} value={it.accuracy} sub={`(${it.n}회)`} />
                  ))
                ) : <EmptyLine>선다형 시행이 쌓이면 표시됩니다.</EmptyLine>}
              </Card>
            </div>

            <Card title="단계별 숙달 도달 시행수" hint="숙달 기준 시도수 대비 현재 시도">
              {data.trials_to_criterion?.length ? (
                <div className="space-y-1">
                  {data.trials_to_criterion.map((s) => (
                    <div key={s.stage} className="flex items-center gap-3 py-1.5">
                      <span className="w-24 shrink-0 text-xs font-semibold text-slate-700">{s.stage}. {s.name}</span>
                      <div className="flex-1">
                        <div className="h-2 rounded-full bg-slate-100">
                          <div className={`h-2 rounded-full ${s.mastered ? 'bg-emerald-500' : 'bg-violet-500'}`}
                               style={{ width: `${s.criterion_attempts ? Math.min(100, (s.attempts / s.criterion_attempts) * 100) : 0}%` }} />
                        </div>
                      </div>
                      <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-slate-500">
                        {s.attempts}/{s.criterion_attempts ?? '—'}회 · 정답 {s.correct}
                      </span>
                      <span className={`w-14 shrink-0 text-right text-[11px] font-bold ${s.mastered ? 'text-emerald-600' : 'text-slate-400'}`}>
                        {s.mastered ? '숙달' : s.status === 'in_progress' ? '진행중' : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : <EmptyLine>단계 연습을 시작하면 표시됩니다.</EmptyLine>}
            </Card>

            <div className="grid gap-5 md:grid-cols-2">
              <Card title="같은 입모양 혼동 비율" hint="오답 중 시각적으로 같은 입모양">
                {data.same_viseme_ratio != null ? (
                  <div className="flex items-center gap-4">
                    <p className="text-3xl font-black text-rose-600">{Math.round(data.same_viseme_ratio * 100)}%</p>
                    <p className="text-[11px] leading-relaxed text-slate-500">
                      틀린 답 중 이만큼이 <b>입모양이 같아</b> 헷갈린 경우입니다. 독화에서 본질적으로
                      구분이 어려운 지점을 가리키며, 이 비율이 높을수록 청각·문맥 단서 보완이 필요합니다.
                    </p>
                  </div>
                ) : <EmptyLine>혼동 데이터가 쌓이면 표시됩니다.</EmptyLine>}
              </Card>

              <Card title="문장 점수 추이" hint="문장 채점 점수(시간순 구간)">
                <LineChart series={data.sentence_trend} max={100} fmt={(v) => `${Math.round(v)}`} color="#e11d48" />
              </Card>
            </div>
          </>
        )}

        {/* 축 C — 공개 표준 독화 자원 내려받기(연구·교육 활용). 개인 학습 기록과 무관하게 항상 제공 */}
        {!loading && (
          <Card title="공개 표준 독화 자원 (축 C)" hint="연구·교육 활용 · CC BY 4.0">
            <p className="mb-3 text-[11px] leading-relaxed text-slate-500">
              한국어 독화에는 표준 자원이 거의 없습니다. LIPLAB은 동구형이음 사전·독화 난이도 지수·자음
              시각 지각공간·표준 평가셋을 판본과 함께 공개합니다. 앱 밖 연구·교육에서도 활용할 수 있어요.
            </p>
            <button type="button" onClick={downloadResources} disabled={dl}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white transition hover:bg-slate-700 disabled:opacity-50">
              {dl ? '내려받는 중…' : '자원 JSON 내려받기'}
            </button>
          </Card>
        )}
      </main>
    </div>
  )
}
