import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { evalAPI, curriculumAPI } from '../api'
import AppShell from '../components/AppShell'
import LoadingScreen from '../components/LoadingScreen'
import { TRANSFER_NOISE_NOTE } from '../lib/talkers'
import { changeTone, ciText, CHANGE_NOISE_NOTE } from '../lib/changeTone'

// 학습 효과 리포트 — 개인별 시행 기록으로 학습곡선·단계 도달 시행수·초기 대비 최근 향상도를
// 시각화한다. 공모전 평가/효과성 근거용. 데이터가 적으면 각 카드가 '쌓이면 표시' 상태를 그린다.

// 동형 폼 비교 문구 — 먼저 본 폼이 사전이다(파일럿에서 B를 먼저 보면 B(사전)·A(사후)).
const formPairLabel = (prog) => `동형 폼 ${prog.pre?.form || 'A'}(사전)·${prog.post?.form || 'B'}(사후) 비교`
// 동형이 아닐 때의 비교 설명. 폼은 A·B인데 판본이 다르면(9/27 v2에서 오답을 바꿈) 그 사실을 적는다.
const nonHomogeneousLabel = (prog) => {
  const [v1, v2] = prog.form_versions || []
  return v1 && v2 && v1 !== v2 ? `판본이 다른 검사 비교(${v1}→${v2}, 동형 아님)` : '가장 이른·최근 검사 비교'
}

// 새 가상 화자 조건(커리큘럼 계획 2-3): 사후 검사 문항 절반을 훈련에 없던 가상 화자로 봤을 때의 정답률. 한 얼굴 안에서 말 속도·입 벌림·
// 입술을 바꾼 앱 안의 근거리 전이 지표이고, 실제 사람 입모양으로의 전이(계획 3-3)는 아니다. 사후 검사 한 번 안의 차이라 향상도가 아니다.
// 문항 12개씩이라 한 사람의 차이는 잡음이 커서 색으로 좋고 나쁨을 매기지 않는다(9/29, 예전에는 −5%p 경계로 색을 바꿨다).
const TRANSFER_NOTE = '같은 얼굴이 말하는 방식만 바꾼 앱 안의 가상 화자예요. 실제 사람 입모양으로 옮겨 가는지는 아직 재지 않았어요.'
const signedPp = (x) => `${x >= 0 ? '+' : ''}${Math.round(x * 100)}%p`
// 사전 검사를 연습을 꽤 한 뒤에 봤으면(서버 기준 PRETEST_TRIALS_FLAG, 9/29) 향상도가 작게 나올 수 있다고 알린다
const afterTrainingNote = (pre) => (pre?.after_training
  ? `사전 검사를 독화 연습 ${pre.trials_before}회 뒤에 봤어요. 연습 효과가 사전 점수에 들어가 향상도가 작게 나올 수 있어요.` : '')

function TalkerTransfer({ t }) {
  const d = t.default
  const n = t.new_talker
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="mb-2 text-[11px] font-bold text-ink-faint">새 가상 화자 조건 (사후 검사)</p>
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <p className="text-[11px] font-bold text-ink-faint">기본 얼굴 {d.n}문항</p>
          <p className="text-xl font-bold text-ink-muted">{Math.round((d.accuracy ?? 0) * 100)}%</p>
        </div>
        <div>
          <p className="text-[11px] font-bold text-ink-faint">새 가상 화자 {n.n}문항</p>
          <p className="text-xl font-bold text-primary-700">{Math.round((n.accuracy ?? 0) * 100)}%</p>
        </div>
        {t.gap != null && (
          <div className="pb-1">
            <span className="text-xs font-bold text-ink-muted">차이 {signedPp(t.gap)}</span>
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-ink-muted">{TRANSFER_NOISE_NOTE} {TRANSFER_NOTE}</p>
    </div>
  )
}

function Card({ title, hint, children }) {
  return (
    <section className="card-flat">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-[15px] font-bold leading-figma text-ink">{title}</h2>
        {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Metric({ label, value, unit, tone = 'text-primary-700' }) {
  return (
    <article className="card-flat">
      <p className="text-xs font-bold text-ink-soft">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${tone}`}>
        {value ?? '—'}{value != null && unit ? <span className="ml-0.5 text-base font-bold text-ink-faint">{unit}</span> : null}
      </p>
    </article>
  )
}

function EmptyLine({ children }) {
  return <p className="py-6 text-center text-xs text-ink-faint">{children}</p>
}

// 시행 순서(bin)별 값(0~1 또는 0~100)을 꺾은선으로. vals: [{bin,n,value}]
// 선 색은 분석 탭과 맞춘다: 정확도 = 초록(chart-accuracy, 96:66), 점수 = 보라(primary). 격자·눈금은 line·ink-faint 토큰.
const LINE_TONE = {
  accuracy: { line: 'stroke-chart-accuracy', dot: 'fill-chart-accuracy' },
  score: { line: 'stroke-primary-500', dot: 'fill-primary-500' },
}
function LineChart({ series, max = 1, fmt = (v) => `${Math.round(v * 100)}%`, tone = 'accuracy' }) {
  const t = LINE_TONE[tone] || LINE_TONE.accuracy
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
          <line x1={PL} x2={W - PR} y1={y(g * max)} y2={y(g * max)} className="stroke-line" strokeWidth="1" />
          <text x={PL - 6} y={y(g * max) + 3} textAnchor="end" fontSize="9" className="fill-ink-faint">{fmt(g * max)}</text>
        </g>
      ))}
      <polyline points={pts} fill="none" className={t.line} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {series.map((s, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(s.value)} r="3.5" className={t.dot} />
          <text x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" className="fill-ink-faint">{i + 1}</text>
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
        <span className="font-semibold text-ink">{label}</span>
        <span className="tabular-nums text-ink-muted">{value}{unit}{sub ? <span className="ml-1 text-ink-faint">{sub}</span> : null}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-fill">
        <div className="h-2 rounded-full bg-primary-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// 교사·언어재활사용 결과지(I-9) — 인쇄할 때만 보이는 흑백 A4 판. 화면용 카드와 달리 표와 숫자만 담는다.
const pct = (x) => (x == null ? '–' : `${Math.round(x * 100)}%`)
function PrintReport({ r }) {
  const prog = r.progression?.available ? r.progression : null
  const act = r.activity || {}
  const art = r.articulation && r.articulation.sessions ? r.articulation : null
  const th = 'border border-black px-2 py-1 text-left font-bold'
  const td = 'border border-black px-2 py-1'
  return (
    <div className="hidden bg-white text-[11pt] leading-relaxed text-black print:block">
      <h1 className="text-[16pt] font-bold">LIPLAB 독화 학습 결과지</h1>
      <p className="mt-1">학습자 {r.learner?.name || '–'} · 발행 {r.issued_on || (r.generated_at || '').slice(0, 10)} · 교사·언어재활사 참고용</p>

      <h2 className="mt-5 text-[12.5pt] font-bold">1. 표준검사 이력</h2>
      {r.tests?.length ? (
        <table className="mt-1 w-full border-collapse">
          <thead><tr><th className={th}>날짜</th><th className={th}>폼</th><th className={th}>판본</th><th className={th}>정답/문항</th><th className={th}>정확도</th><th className={th}>수준</th></tr></thead>
          <tbody>
            {r.tests.map((t, i) => (
              <tr key={i}><td className={td}>{t.date || '–'}</td><td className={td}>{t.form || '배치'}</td><td className={td}>{t.form_version || '–'}</td>
                <td className={td}>{t.correct ?? '–'}/{t.total ?? '–'}</td><td className={td}>{pct(t.accuracy)}</td><td className={td}>Lv.{t.level ?? '–'}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="mt-1">검사 기록이 없습니다.</p>}

      <h2 className="mt-5 text-[12.5pt] font-bold">2. 사전·사후 비교</h2>
      {prog ? (
        <div className="mt-1">
          <p>정확도 {pct(prog.pre.accuracy)} → {pct(prog.post.accuracy)} ({prog.accuracy_delta >= 0 ? '+' : ''}{Math.round(prog.accuracy_delta * 100)}%p
            {prog.accuracy_delta_ci95 ? `, ${ciText(prog.accuracy_delta_ci95)}` : ''}),
            수준 Lv.{prog.pre.level} → Lv.{prog.post.level}{prog.homogeneous ? ` · ${formPairLabel(prog)}` : ` · ${nonHomogeneousLabel(prog)}`}
            {prog.talker_transfer ? ` · 사후는 기본 얼굴 ${prog.talker_transfer.default.n}문항` : ''}</p>
          {prog.talker_transfer && (
            <p className="mt-1">새 가상 화자 조건(사후): 기본 얼굴 {pct(prog.talker_transfer.default.accuracy)}, 새 가상 화자 {pct(prog.talker_transfer.new_talker.accuracy)}
              {prog.talker_transfer.gap != null ? ` (${signedPp(prog.talker_transfer.gap)})` : ''}. {TRANSFER_NOISE_NOTE} {TRANSFER_NOTE}</p>
          )}
          {prog.error_phoneme_change?.some((e) => e.before || e.after) && (
            <p className="mt-1">자모별 오류 수 변화: {prog.error_phoneme_change.filter((e) => e.before || e.after).slice(0, 10)
              .map((e) => `${e.phoneme} ${e.before}→${e.after}`).join(', ')}</p>
          )}
        </div>
      ) : <p className="mt-1">사전·사후 검사가 두 번 이상 있어야 비교할 수 있습니다.</p>}

      <h2 className="mt-5 text-[12.5pt] font-bold">3. 오류 프로파일{r.error_profile?.from_test ? ` (${r.error_profile.from_test} 검사)` : ''}</h2>
      <p className="mt-1">약한 입모양 그룹: {r.error_profile?.visemes?.length ? r.error_profile.visemes.map((v) => v.name).join(', ') : '없음'}</p>
      <p>자주 틀린 자모: {r.error_profile?.phonemes?.length ? r.error_profile.phonemes.map((e) => `${e.phoneme}(${e.count})`).join(', ') : '없음'}</p>

      <h2 className="mt-5 text-[12.5pt] font-bold">4. 학습량</h2>
      <p className="mt-1">학습한 날 {act.active_days ?? 0}일{act.first_day ? ` (${act.first_day} ~ ${act.last_day})` : ''}</p>
      {act.trials_by_stage?.length > 0 && (
        <p>단계별 시행: {act.trials_by_stage.map((s) => `${s.name} ${s.n}회(정답 ${s.correct})`).join(', ')}</p>
      )}
      <p>말하기 연습 {act.speak?.n ?? 0}회{act.speak?.mean_score != null ? `, 평균 ${act.speak.mean_score}점` : ''}</p>

      <h2 className="mt-5 text-[12.5pt] font-bold">5. 웹캠 조음 교정</h2>
      {art ? (
        <p className="mt-1">교정 세션 {art.sessions}회, 목표 대비 평균 오차 {art.gap_start} → {art.gap_end} (세션 처음 → 끝, 0에 가까울수록 목표와 가까움)</p>
      ) : <p className="mt-1">교정 세션 기록이 없습니다.</p>}

      <h2 className="mt-5 text-[12.5pt] font-bold">해석 주의</h2>
      <ul className="mt-1 list-disc pl-5">{(r.notes || []).map((n, i) => <li key={i}>{n}</li>)}</ul>
    </div>
  )
}

export default function EvalReport() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [prog, setProg] = useState(null)   // 통제 향상도(축 I, 사전 A vs 사후 B)
  const [dl, setDl] = useState(false)      // 공개 자원 내려받기 상태(축 C)
  const [art, setArt] = useState(null)     // 웹캠 조음 교정 전후 오차(축 E-9)
  const [report, setReport] = useState(null)  // 교사·언어재활사용 결과지(I-9) — 인쇄 버튼을 누를 때 받는다
  const [printing, setPrinting] = useState(false)
  const [hist, setHist] = useState(null)   // 검사 이력 — 사전 검사(A)를 아직 안 봤는지(권유 문구)

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

  // 누를 때마다 결과지를 새로 받는다. 이전 결과지를 먼저 비워, 두 번째 인쇄가 새 결과지를 받기 전에 지난 것을 인쇄하지 않게 한다.
  const printReport = async () => {
    setReport(null)
    setPrinting(true)
    try { setReport(await evalAPI.report()) } catch { setPrinting(false) }
  }
  useEffect(() => {
    if (!printing || !report) return undefined
    const t = setTimeout(() => { window.print(); setPrinting(false) }, 60)   // 결과지가 그려진 뒤 인쇄 창
    return () => clearTimeout(t)
  }, [printing, report])

  useEffect(() => {
    evalAPI.summary().then(setData).catch(() => setData(null)).finally(() => setLoading(false))
    evalAPI.progression().then(setProg).catch(() => setProg(null))
    curriculumAPI.getArticulationTrend().then(setArt).catch(() => setArt(null))
    curriculumAPI.getAssessmentHistory().then(setHist).catch(() => setHist(null))
  }, [])

  const ov = data?.overview
  const bvr = data?.baseline_vs_recent
  const noData = ov && ov.total_trials === 0 && ov.total_sentences === 0
  // 사전 검사를 아직 안 봤는데 연습이 쌓였으면 부드럽게 알린다(막지 않는다). 기준은 서버의 연습 뒤 사전 표시와 같은 20회
  const practiced = (ov?.total_trials || 0) + (ov?.total_sentences || 0)
  const latePretest = hist && !hist.pretest_taken && practiced >= 20

  return (
    <>
      {report && <PrintReport r={report} />}
      <div className="print:hidden">
      <AppShell active="analysis" title="학습 효과 리포트"
        description="시행 기록으로 학습곡선과 단계별 도달 시행수, 초기 대비 최근 향상도를 확인합니다.">
      <div className="flex w-full flex-col gap-5">
        {/* 표준검사 진입(축 I) — 난이도를 맞춘 동형 폼 A(사전)·B(사후). 훈련 전 A, 훈련 뒤 B를 보면
            아래 '통제 향상도'에 변화가 나온다. 배치검사 화면에는 모드 전환기가 없으므로 여기서 연다. */}
        <div className="flex flex-col gap-3 rounded-18 border-2 border-line bg-white p-5 sm:flex-row sm:items-center">
          <div className="flex-1">
            <p className="text-sm font-bold text-ink">표준검사 사전·사후</p>
            <p className="mt-0.5 text-xs text-ink-muted">훈련 전에 사전(A), 훈련 뒤에 사후(B)를 한 번씩 보면 향상도를 비교해요. 각 24문항, 5분 안팎.</p>
            {latePretest && (
              <p className="mt-1 text-xs text-ink-muted">
                이미 독화 연습을 {practiced}회 했어요. 지금 사전 검사를 봐도 되지만, 결과에 '연습 뒤 사전'으로 표시돼요.
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => navigate('/learn/placement?form=A')} className="btn-secondary whitespace-nowrap !py-2.5 px-4 text-[14px]">사전 검사(A)</button>
            <button type="button" onClick={() => navigate('/learn/placement?form=B')} className="btn-primary whitespace-nowrap !py-2.5 px-4 text-[14px]">사후 검사(B)</button>
            <button type="button" onClick={printReport} disabled={printing} className="btn-secondary whitespace-nowrap !py-2.5 px-4 text-[14px]"
              title="검사 이력·오류 프로파일·학습량을 한 장으로 인쇄해 교사·언어재활사와 나눠요">
              {printing ? '준비 중…' : '결과지 인쇄'}
            </button>
          </div>
        </div>
        {loading ? (
          <LoadingScreen variant="inline" />
        ) : !data ? (
          <div className="rounded-18 border-2 border-line bg-white py-16 text-center text-sm text-ink-muted">리포트를 불러오지 못했습니다.</div>
        ) : noData ? (
          <div className="rounded-18 border-2 border-line bg-white px-5 py-16 text-center text-sm text-ink-muted">
            아직 학습 기록이 없습니다. 입모양 인지·단어·문장 연습을 진행하면 학습곡선과 향상도가 여기에 표시됩니다.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="총 시행" value={ov.total_trials} unit="회" tone="text-ink" />
              <Metric label="시행 정확도" value={ov.trial_accuracy} unit="%" tone="text-stat-accuracy" />
              <Metric label="문장 연습" value={ov.total_sentences} unit="회" tone="text-ink" />
              <Metric label="문장 평균점수" value={ov.sentence_avg_score} unit="점" />
            </div>

            {/* 유형(입모양·단어·문맥) 고정효과를 뺀 정확도(docs/eval-metrics.md). 단계가 바뀌어 문항 유형이 달라지는 것만으로 꺾이지 않는다 */}
            <Card title="학습곡선 (선다형 정확도)" hint="시간순 구간별 · 문항 유형 차이 보정">
              <LineChart series={data.learning_curve} max={1} />
            </Card>

            {/* 통제 향상도(축 I) — 동형 폼 사전(A)·사후(B) 비교. 배치검사에서 A/B를 모두 마치면 표시 */}
            {prog?.available && (
              <Card title="통제 향상도 (표준검사 사전·사후)"
                hint={prog.homogeneous ? formPairLabel(prog) : nonHomogeneousLabel(prog)}>
                <div className="flex flex-wrap items-end gap-6">
                  <div>
                    <p className="text-[11px] font-bold text-ink-faint">사전 정확도</p>
                    <p className="text-2xl font-bold text-ink-muted">{Math.round(prog.pre.accuracy * 100)}%</p>
                  </div>
                  <div className="pb-1 text-ink-ghost">→</div>
                  <div>
                    <p className="text-[11px] font-bold text-ink-faint">사후 정확도</p>
                    <p className="text-2xl font-bold text-primary-700">{Math.round(prog.post.accuracy * 100)}%</p>
                  </div>
                  {/* 색은 Newcombe 95% 구간이 0을 벗어날 때만(docs/eval-metrics.md 6절) */}
                  <div className="pb-1">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${changeTone(prog.accuracy_delta_clear, prog.accuracy_delta)}`}>
                      {prog.accuracy_delta >= 0 ? '+' : ''}{Math.round(prog.accuracy_delta * 100)}%p
                    </span>
                  </div>
                  <div className="pb-1 text-xs text-ink-muted">
                    수준 Lv.{prog.pre.level} → Lv.{prog.post.level}
                  </div>
                </div>
                {!prog.accuracy_delta_clear && (
                  <p className="mt-2 text-[11px] text-ink-faint">
                    {prog.accuracy_delta_ci95 ? `${ciText(prog.accuracy_delta_ci95)}. ` : ''}{CHANGE_NOISE_NOTE}
                  </p>
                )}
                {prog.pre?.after_training && <p className="mt-1 text-[11px] text-ink-faint">{afterTrainingNote(prog.pre)}</p>}
                {/* 사후 검사에 새 가상 화자 조건이 있으면 위 비교는 기본 얼굴 문항끼리다(계획 2-3). 옛 검사는 전 문항 그대로 */}
                {prog.talker_transfer && (
                  <p className="mt-2 text-[11px] text-ink-faint">
                    기본 얼굴 문항끼리 비교: 사후는 {prog.talker_transfer.default.n}문항(전체 {prog.talker_transfer.default.n + prog.talker_transfer.new_talker.n}문항 정확도 {Math.round((prog.post.accuracy_all ?? 0) * 100)}%)
                  </p>
                )}
                {prog.error_phoneme_change?.some((e) => e.before || e.after) && (
                  <div className="mt-3">
                    <p className="mb-1 text-[11px] font-bold text-ink-faint">음소별 오류 변화 (사전→사후)</p>
                    <div className="flex flex-wrap gap-1.5">
                      {prog.error_phoneme_change.filter((e) => e.before || e.after).slice(0, 8).map((e) => (
                        // 자모마다 오류가 몇 개뿐이라 개인 증감은 잡음이 커서 색을 매기지 않는다(9/29)
                        <span key={e.phoneme}
                          className="rounded-full bg-fill px-2 py-0.5 text-xs font-semibold text-ink-muted">
                          {e.phoneme} {e.before}→{e.after}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {prog.talker_transfer && <TalkerTransfer t={prog.talker_transfer} />}
              </Card>
            )}

            <div className="grid gap-5 md:grid-cols-2">
              <Card title="초기 대비 최근 향상도" hint={bvr ? `각 ${bvr.n_each}시행` : '최소 9시행 필요'}>
                {bvr ? (
                  <div>
                    <div className="flex items-end gap-6">
                      <div>
                        <p className="text-[11px] font-bold text-ink-faint">초기 1/3</p>
                        <p className="text-2xl font-bold text-ink-muted">{bvr.baseline_acc}%</p>
                      </div>
                      <div className="pb-1 text-ink-ghost">→</div>
                      <div>
                        <p className="text-[11px] font-bold text-ink-faint">최근 1/3</p>
                        <p className="text-2xl font-bold text-primary-700">{bvr.recent_acc}%</p>
                      </div>
                      <div className="pb-1">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${changeTone(bvr.clear, bvr.delta_pp)}`}>
                          {bvr.delta_pp >= 0 ? '+' : ''}{bvr.delta_pp}%p
                        </span>
                      </div>
                    </div>
                    {bvr.by_type?.length > 1 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {bvr.by_type.map((t) => (
                          <span key={t.item_type} className="rounded-full bg-fill px-2 py-0.5 text-[11px] font-semibold tabular-nums text-ink-muted">
                            {t.label} {t.baseline_acc}→{t.recent_acc}% ({t.delta_pp >= 0 ? '+' : ''}{t.delta_pp}%p)
                          </span>
                        ))}
                      </div>
                    )}
                    {!bvr.clear && (
                      <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
                        {bvr.ci95_pp ? `${ciText(bvr.ci95_pp, 1)}. ` : ''}{CHANGE_NOISE_NOTE}
                      </p>
                    )}
                    <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">{bvr.note}</p>
                  </div>
                ) : <EmptyLine>한 유형(입모양·단어·문맥)을 9회 이상 풀면 향상도가 표시됩니다.</EmptyLine>}
              </Card>

              <Card title="유형별 정확도">
                {data.by_item_type?.length ? (
                  data.by_item_type.map((it) => (
                    <BarRow key={it.item_type} label={it.label} value={it.accuracy} sub={`(${it.n}회)`} />
                  ))
                ) : <EmptyLine>선다형 시행이 쌓이면 표시됩니다.</EmptyLine>}
              </Card>
            </div>

            {/* 조음 교정 전후 오차(축 E-9) — 웹캠 교정 세션의 처음·끝에서 잰 관찰 차원(개구·원순·폐쇄) 평균 |목표−관찰| */}
            {art?.sessions > 0 && (
              <Card title="조음 교정 전후 오차 (웹캠)" hint={`교정 세션 ${art.sessions}회 · 0에 가까울수록 목표 입모양`}>
                <div className="flex flex-wrap items-end gap-6">
                  <div>
                    <p className="text-[11px] font-bold text-ink-faint">세션 처음</p>
                    <p className="text-2xl font-bold text-ink-muted">{Math.round(art.gap_start * 100)}</p>
                  </div>
                  <div className="pb-1 text-ink-ghost">→</div>
                  <div>
                    <p className="text-[11px] font-bold text-ink-faint">세션 끝</p>
                    <p className="text-2xl font-bold text-primary-700">{Math.round(art.gap_end * 100)}</p>
                  </div>
                  <div className="pb-1">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${art.change <= 0 ? 'bg-good-tint text-good-text' : 'bg-bad-tint text-bad-text'}`}>
                      {art.change <= 0 ? '' : '+'}{Math.round(art.change * 100)}
                    </span>
                  </div>
                  {art.early != null && art.recent != null && (
                    <div className="pb-1 text-xs text-ink-muted">
                      처음 세션들 {Math.round(art.early * 100)} → 최근 세션들 {Math.round(art.recent * 100)}
                    </div>
                  )}
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
                  입을 벌린 정도·입술 오므림·입술 닫힘을 목표와 비교한 평균 차이(0~100)입니다. 혀처럼 밖에서 안 보이는
                  조음은 포함되지 않아요. 영상은 기기 밖으로 나가지 않고 요약 수치만 저장됩니다.
                </p>
              </Card>
            )}

            {/* 숙달한 단계는 처음 숙달한 시도(9/27 이전 숙달은 기록 없음), 진행 중이면 두 기준(최소 시도·숙달 점수) 중 모자란 쪽의 진행 */}
            <Card title="단계별 숙달 도달 시행수" hint="숙달까지 걸린 시도 · 진행 중이면 기준까지">
              {data.trials_to_criterion?.length ? (
                <div className="space-y-1">
                  {data.trials_to_criterion.map((s) => (
                    <div key={s.stage} className="flex items-center gap-3 py-1.5">
                      <span className="w-24 shrink-0 text-xs font-semibold text-ink">{s.stage}. {s.name}</span>
                      <div className="flex-1">
                        <div className="h-2 rounded-full bg-fill">
                          <div className={`h-2 rounded-full ${s.mastered ? 'bg-good' : 'bg-primary-500'}`}
                               style={{ width: `${Math.round((s.progress ?? 0) * 100)}%` }} />
                        </div>
                      </div>
                      <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-ink-muted">
                        {s.mastered
                          ? (s.trials_to_mastery ? `${s.trials_to_mastery}회째 숙달` : `${s.attempts}회 · 정답 ${s.correct}`)
                          : `점수 ${Math.round(s.mastery_score)}/${s.mastery_threshold ?? '—'} · ${s.attempts}회`}
                      </span>
                      <span className={`w-14 shrink-0 text-right text-[11px] font-bold ${s.mastered ? 'text-good-text' : 'text-ink-faint'}`}>
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
                    <p className="text-3xl font-bold text-bad">{Math.round(data.same_viseme_ratio * 100)}%</p>
                    <p className="text-[11px] leading-relaxed text-ink-muted">
                      틀린 답 중 이만큼이 <b>입모양이 같아</b> 헷갈린 경우입니다. 독화에서 본질적으로
                      구분이 어려운 지점을 가리키며, 이 비율이 높을수록 청각·문맥 단서 보완이 필요합니다.
                    </p>
                  </div>
                ) : <EmptyLine>혼동 데이터가 쌓이면 표시됩니다.</EmptyLine>}
              </Card>

              <Card title="문장 점수 추이" hint="시간순 구간별 · 문장 난이도 차이 보정">
                <LineChart series={data.sentence_trend} max={100} fmt={(v) => `${Math.round(v)}`} tone="score" />
                {/* 답 방식별: 4지선다는 찍어도 25%가 맞고 100 또는 0점이라, 직접 입력(부분 점수)과 섞으면 어느 쪽 실력인지 알 수 없다 */}
                {data.sentence_by_mode?.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-line pt-3">
                    {data.sentence_by_mode.map((m) => (
                      <div key={m.mode} className="flex items-center justify-between gap-3 text-[11px]">
                        <span className="font-semibold text-ink">{m.label}</span>
                        <span className="tabular-nums text-ink-muted">{m.n}회 · 평균 {Math.round(m.avg_score)}점 · 합격 {Math.round(m.pass_rate)}%</span>
                      </div>
                    ))}
                    <p className="pt-1 text-[11px] leading-relaxed text-ink-faint">
                      보기 고름은 몰라도 네 번에 한 번은 맞아요. 직접 입력한 문장의 합격률이 실제 읽기 실력에 더 가깝습니다.
                    </p>
                  </div>
                )}
              </Card>
            </div>
          </>
        )}

        {/* 축 C — 공개 표준 독화 자원 내려받기(연구·교육 활용). 개인 학습 기록과 무관하게 항상 제공 */}
        {!loading && (
          <Card title="공개 표준 독화 자원 (축 C)" hint="연구·교육 활용 · CC BY 4.0">
            <p className="mb-3 text-[11px] leading-relaxed text-ink-muted">
              한국어 독화에는 표준 자원이 거의 없습니다. LIPLAB은 동구형이음 사전·독화 난이도 지수·자음
              시각 지각공간·표준 평가셋을 판본과 함께 공개합니다. 앱 밖 연구·교육에서도 활용할 수 있어요.
            </p>
            <button type="button" onClick={downloadResources} disabled={dl}
              className="btn-secondary !py-2.5 px-4 text-[14px] disabled:opacity-50">
              {dl ? '내려받는 중…' : '자원 JSON 내려받기'}
            </button>
          </Card>
        )}
      </div>
      </AppShell>
      </div>
    </>
  )
}
