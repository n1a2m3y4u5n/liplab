import { useState, useRef, useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { tactileAPI, learningAPI } from '../api'
import TactileFaceSim from '../components/TactileFaceSim'
import LearnHeader from '../components/LearnHeader'

/**
 * 촉각(타도마) 학습 — 얼굴 모형(아두이노)을 손으로 느끼며 말을 이해하는 훈련.
 * 청각장애인이 상대의 턱·입술·진동·기류를 손으로 느껴 말을 알아듣는 '타도마(Tadoma)' 방식을,
 * 3D 프린팅 얼굴 모형 + 웹(Web Serial)으로 재현한다.
 *  - 체험 모드: 문장을 골라 재생 → 손으로 느끼며 익힘
 *  - 퀴즈 모드: 모형이 단어를 '말해주고' → 무엇이었는지 맞히기(채점)
 * ※ Web Serial API는 Chrome/Edge(데스크톱)에서만 동작한다.
 */

const AIRFLOW_CODE = { none: 0, plosive: 1, fricative: 2 }
const PRESET = ['바다', '파도', '엄마', '아빠', '학교', '사과', '나무', '우유', '안녕하세요']
// 촉각(타도마) 5단계 커리큘럼 — 감각 → 요소 → 변별 → 낱말 → 문장으로 위계적으로 확장.
// (독화·발화 커리큘럼처럼 '쉬운 단서 → 통합'의 체계적 진행)
const LEVELS = [
  { title: '감각 (유·무성)', goal: '진동의 유무를 손끝으로 감지', desc: '진동이 있고 없음을 느껴 구별해요', groups: [['바', '파'], ['다', '타'], ['가', '카'], ['자', '차']] },
  { title: '모음', goal: '턱 벌림·입술 모양으로 모음 변별', desc: '턱 벌림과 입술 모양의 차이를 느껴요', groups: [['아', '이', '우'], ['오', '으', '이'], ['애', '우', '으']] },
  { title: '최소대립쌍', goal: '눈으론 같은 소리를 촉각으로 구별', desc: '눈으론 같아도 촉각으론 다른 소리 (핵심)', groups: [['바', '파', '마'], ['달', '탈'], ['불', '풀'], ['발', '팔'], ['방', '팡']] },
  { title: '단어', goal: '촉각 단서를 종합해 낱말 인식', desc: '낱말을 알아맞혀요', pool: ['바다', '파도', '엄마', '아빠', '학교', '사과', '나무', '우유', '다리', '토끼', '기차', '구름', '하늘', '노래', '머리', '가방', '친구', '바나나', '강아지', '고양이', '자동차', '무지개', '선생님', '운동화', '바람', '구두', '포도', '단추'] },
  { title: '문장', goal: '연속된 말의 흐름을 촉각으로 따라가기', desc: '짧은 문장을 이해해요', pool: ['밥 먹어요', '안녕하세요', '고마워요', '사랑해요', '잘 자요', '어디 가요', '물 좀 주세요', '이름이 뭐예요', '지금 몇 시예요', '천천히 말해요', '다시 한 번요', '괜찮아요', '같이 가요', '내일 만나요'] },
]
const _rand = (n) => Math.floor(Math.random() * n)
const _shuffle = (a) => [...a].sort(() => Math.random() - 0.5)
function makeQuestion(lv) {
  // 변별 단계(감각·모음·최소대립쌍)는 성격상 '보기 중 고르기'가 맞다 → 객관식 고정.
  if (lv.groups) {
    const g = lv.groups[_rand(lv.groups.length)]
    return { type: 'choice', answer: g[_rand(g.length)], options: _shuffle(g) }
  }
  const answer = lv.pool[_rand(lv.pool.length)]
  // 낱말·문장 단계는 독화처럼 유형을 섞는다 — 객관식(4지선다) ↔ 주관식(직접 입력).
  if (Math.random() < 0.5) return { type: 'input', answer, options: [] }
  const opts = new Set([answer])
  while (opts.size < Math.min(4, lv.pool.length)) opts.add(lv.pool[_rand(lv.pool.length)])
  return { type: 'choice', answer, options: _shuffle([...opts]) }
}

// ── 커스텀 펌웨어 생성 — 사용자가 입력한 핀 배치를 .ino에 반영 ──────────────
// 팬은 analogWrite(PWM)로 세기를 조절한다. Uno의 PWM 핀은 3·5·6·9·10·11이지만,
// Servo 라이브러리가 Timer1을 점유해 D9·D10의 PWM을 끄므로 팬 유효 핀은 3·5·6·11.
const FAN_PWM_PINS = [3, 5, 6, 11]
const MIN_PIN = 2   // D0·D1은 USB 시리얼(RX/TX)이라 부품 연결 금지
const PIN_FIELDS = [
  { key: 'jaw', label: '턱 서보', token: 'pinJaw', def: 9, pwm: false },
  { key: 'lip', label: '입술 서보', token: 'pinLip', def: 10, pwm: false },
  { key: 'vib', label: '진동 모터', token: 'pinVib', def: 5, pwm: false },
  { key: 'fan', label: '팬(기류)', token: 'pinFan', def: 6, pwm: true },   // analogWrite → PWM 핀 필요
]

// 전송한 시리얼 라인을 사람이 읽는 상태로 디코드 (신호 모니터용)
function decodeSentLine(line) {
  if (!line) return '—'
  if (line.startsWith('SET')) {
    const p = line.split(',').slice(1)
    return `핀 설정 → 턱 D${p[0]} · 입술 D${p[1]} · 진동 D${p[2]} · 팬 D${p[3]}`
  }
  const [j, l, v, a, d] = line.split(',').map(Number)
  if ([j, l, v, a, d].every((x) => x === 0)) return '정지(휴지)'
  const air = a === 1 ? '파열(강)' : a === 2 ? '마찰(약)' : '없음'
  return `턱 ${j}° · 입술 ${l ? '원순' : '평순'} · 진동 ${v ? 'ON' : 'off'} · 기류 ${air} · ${d}ms`
}

// 템플릿 .ino의 기본 핀 변수를 사용자 값으로 치환하고, 상단에 사용자 핀표 주석을 붙인다.
function buildCustomIno(template, pins) {
  let out = template
  for (const f of PIN_FIELDS) {
    out = out.replace(new RegExp(`(int ${f.token}\\s*=\\s*)\\d+`), `$1${pins[f.key]}`)
  }
  const header = [
    '// ===== 사용자 지정 핀 배치 (LIPLAB 웹에서 생성) =====',
    ...PIN_FIELDS.map((f) => `//   ${f.label} → D${pins[f.key]}`),
    '// ※ 아래 배선 설명의 핀 번호는 기본값 예시이며, 실제 연결은 위 표를 따르세요.',
    '// ==================================================',
    '',
  ].join('\n')
  return header + out
}

export default function TactilePractice() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  // 대시보드 카드에서 특정 레벨/모드로 바로 진입(?level=N&mode=quiz)
  const _lvParam = parseInt(searchParams.get('level'), 10)
  const _initLevel = Number.isInteger(_lvParam) && _lvParam >= 0 && _lvParam < LEVELS.length ? _lvParam : 0
  // 학습(퀴즈)을 기본으로 — 체계적 커리큘럼이 중심. 체험은 보조(명시적 요청 시에만).
  const _initMode = searchParams.get('mode') === 'explore' ? 'explore' : 'quiz'
  const reviewMode = searchParams.get('review') != null || location.pathname === '/review/tactile'   // 복습 모드(예정·틀림·북마크 항목 다시)
  const hardwareView = location.pathname === '/learn/tactile/hardware'   // 하드웨어 전용 탭(조립 설명서·핀 설정·신호 모니터)
  const supported = typeof navigator !== 'undefined' && 'serial' in navigator

  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('')
  const [text, setText] = useState('바다')
  const [playing, setPlaying] = useState(false)
  const [sim, setSim] = useState(null)           // 시뮬레이터 현재 음소 상태
  const [simHidden, setSimHidden] = useState(false)  // 퀴즈에서 시뮬레이터 가리기(순수 촉각)
  const [mode, setMode] = useState(_initMode)   // 'explore' | 'quiz'

  const [level, setLevel] = useState(_initLevel)          // 촉각 커리큘럼 레벨(0~4)
  const [quiz, setQuiz] = useState(null)         // {type:'choice'|'input', answer, options}
  const [quizResult, setQuizResult] = useState(null)
  const [typed, setTyped] = useState('')          // 주관식 입력값
  const [score, setScore] = useState({ correct: 0, total: 0 })
  const [aiPool, setAiPool] = useState(null)      // {level, items} — AI 생성 문제 풀(단어·문장)
  const [reviewPool, setReviewPool] = useState(null)  // 복습 항목(target 배열)
  const [marks, setMarks] = useState({})          // 북마크 상태 {target: bookmarkId}
  const [pins, setPins] = useState({ jaw: 9, lip: 10, vib: 5, fan: 6 })  // 커스텀 펌웨어 핀
  const [pinMsg, setPinMsg] = useState('')
  // 신호 모니터 — 웹이 실제로 보내는지 / 보드가 받는지 확인용
  const [lastSent, setLastSent] = useState('')
  const [sentCount, setSentCount] = useState(0)
  const [boardReply, setBoardReply] = useState('')
  const [replyCount, setReplyCount] = useState(0)

  // 핀 입력 검증 — 문제 있으면 안내 문구, 없으면 null
  const validatePins = () => {
    const vals = PIN_FIELDS.map((f) => pins[f.key])
    if (vals.some((v) => !Number.isInteger(v) || v < MIN_PIN || v > 13)) return '핀은 2~13 사이 정수로 입력해 주세요. (D0·D1은 USB 통신용이라 쓸 수 없어요)'
    if (new Set(vals).size !== vals.length) return '부품마다 서로 다른 핀을 써야 해요(중복 불가).'
    if (!FAN_PWM_PINS.includes(pins.fan)) return `팬은 ${FAN_PWM_PINS.join('·')}번 중 하나여야 바람 세기가 조절돼요. (서보와 겹치지 않는 PWM 핀)`
    return null
  }

  // 사용자 핀 배치를 반영한 .ino 생성·다운로드(오프라인 플래시용)
  const downloadCustomIno = async () => {
    const err = validatePins()
    if (err) { setPinMsg(err); return }
    try {
      const tpl = await (await fetch('/hardware/liplab_face.ino')).text()
      const blob = new Blob([buildCustomIno(tpl, pins)], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'liplab_face_custom.ino'; a.click()
      URL.revokeObjectURL(url)
      setPinMsg('✓ 내 핀 배치가 반영된 liplab_face_custom.ino를 내려받았어요.')
    } catch { setPinMsg('펌웨어 템플릿을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.') }
  }

  // 연결된 아두이노에 런타임 핀 설정 전송(재업로드 불필요) — SET,jaw,lip,vib,fan
  const sendPins = async () => {
    const err = validatePins()
    if (err) { setPinMsg(err); return }
    if (!connected) { setPinMsg('먼저 아래 "얼굴 모형 연결"을 눌러 연결해 주세요.'); return }
    if (playing) { setPinMsg('재생이 끝난 뒤에 핀을 적용해 주세요.'); return }
    try {
      await sendLine(`SET,${pins.jaw},${pins.lip},${pins.vib},${pins.fan}`)
      setPinMsg('✓ 이 핀 배치를 아두이노에 적용했어요 (재업로드 없이 즉시 반영).')
    } catch { setPinMsg('전송에 실패했어요. 연결 상태를 확인해 주세요.') }
  }

  // 복습 모드: 예정·틀림·북마크 항목을 받아 문제 풀로 사용
  useEffect(() => {
    if (!reviewMode) return
    tactileAPI.getReview().then((d) => setReviewPool((d.items || []).map((i) => i.target))).catch(() => setReviewPool([]))
  }, [reviewMode])

  // 복습 풀이 준비되면 첫 문제 자동 출제
  useEffect(() => {
    if (reviewMode && reviewPool && reviewPool.length && !quiz) newQuiz()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewMode, reviewPool])

  // 단어(3)·문장(4) 단계에 진입하면 AI로 새 문제 풀을 받아 변주를 준다(실패 시 내장 풀 폴백).
  useEffect(() => {
    if (reviewMode || !LEVELS[level].pool) { setAiPool(null); return }
    let cancelled = false
    tactileAPI.getPool(level)
      .then((d) => { if (!cancelled && d.items?.length >= 4) setAiPool({ level, items: d.items }) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [level, reviewMode])

  // 현재 레벨의 실효 데이터 — 복습 모드면 복습 풀, 아니면 AI 풀이 있으면 pool 교체
  const effLevel = (lvIdx) => {
    if (reviewMode && reviewPool && reviewPool.length) {
      return { title: '복습', goal: '틀린·예정·북마크 항목 다시', desc: '복습 항목', pool: reviewPool }
    }
    const lv = LEVELS[lvIdx]
    if (lv.pool && aiPool && aiPool.level === lvIdx && aiPool.items.length) return { ...lv, pool: aiPool.items }
    return lv
  }

  // 북마크 토글 — 현재 문제(정답 텍스트)를 촉각 도메인 북마크
  const toggleMark = async (t) => {
    if (!t) return
    try {
      if (marks[t]) { await learningAPI.removeBookmark(marks[t]); setMarks((m) => { const n = { ...m }; delete n[t]; return n }) }
      else { const r = await learningAPI.addBookmark(t, '촉각', 1, 'tactile'); setMarks((m) => ({ ...m, [t]: r.id })) }
    } catch { /* 이미 북마크됨 등 — 무시 */ }
  }

  const portRef = useRef(null)
  const writerRef = useRef(null)
  const readerRef = useRef(null)
  const enc = useRef(new TextEncoder())

  const disconnect = async () => {
    try { await readerRef.current?.cancel() } catch { /* noop */ }
    readerRef.current = null
    try { writerRef.current?.releaseLock() } catch { /* noop */ }
    try { await portRef.current?.close() } catch { /* noop */ }
    writerRef.current = null; portRef.current = null; setConnected(false)
  }
  useEffect(() => () => { disconnect() }, [])

  // 보드가 돌려주는 응답(ok / pins set)을 읽어 신호가 실제로 도달·처리되는지 확인
  const startReader = async (port) => {
    try {
      const reader = port.readable.pipeThrough(new TextDecoderStream()).getReader()
      readerRef.current = reader
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += value
        let nl
        while ((nl = buf.indexOf('\n')) >= 0) {
          const ln = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1)
          if (ln) { setBoardReply(ln); setReplyCount((c) => c + 1) }
        }
      }
    } catch { /* 연결 해제 시 정상 종료 */ }
  }

  const connect = async () => {
    try {
      const port = await navigator.serial.requestPort()
      await port.open({ baudRate: 9600 })
      portRef.current = port
      writerRef.current = port.writable.getWriter()
      startReader(port)   // 보드 응답 수신 시작(신호 확인)
      setConnected(true); setStatus('얼굴 모형이 연결되었어요.')
      // 연결되면 현재 핀 배치를 즉시 반영(런타임) — 유효할 때만
      if (!validatePins()) { try { await sendLine(`SET,${pins.jaw},${pins.lip},${pins.vib},${pins.fan}`) } catch { /* noop */ } }
    } catch (e) {
      const msg = e?.message || ''
      let hint
      if (/No port selected|cancel/i.test(msg)) hint = '포트 선택이 취소됐어요.'
      else if (/open|access|busy|in use|failed to open/i.test(msg)) hint = '포트를 열 수 없어요 — 아두이노 IDE의 시리얼 모니터 등 다른 프로그램이 그 포트를 쓰고 있으면 닫고 다시 시도하세요.'
      else hint = '연결에 실패했어요.'
      setStatus(`${hint}${msg ? ` (${msg})` : ''}`)
    }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const sendLine = async (line) => {
    if (!writerRef.current) return
    await writerRef.current.write(enc.current.encode(line + '\n'))
    setLastSent(line); setSentCount((c) => c + 1)   // 신호 모니터
  }

  const playSequence = async (seq) => {
    setPlaying(true)
    let i = 0
    for (const p of seq) {
      setSim({ jaw: p.jaw, lip: p.lip, voicing: p.voicing, airflow: p.airflow, label: p.label, idx: i++ })
      const a = AIRFLOW_CODE[p.airflow] ?? 0
      await sendLine(`${p.jaw},${p.lip},${p.voicing},${a},${p.duration_ms}`)   // 하드웨어(연결 시)
      await sleep(p.duration_ms + 40)   // 시뮬레이터/하드웨어가 유지하는 동안 대기
    }
    await sendLine('0,0,0,0,0')          // 정지(휴지)
    setSim(null); setPlaying(false)
  }

  const playText = async (t) => {
    if (playing || !t.trim()) return
    try {
      const d = await tactileAPI.getSequence(t)
      await playSequence(d.sequence)   // 하드웨어 미연결이면 시뮬레이터만 동작
    } catch { setStatus('음소 시퀀스를 불러오지 못했어요.') }
  }

  const newQuiz = (lvIdx = level) => {
    setQuiz(makeQuestion(effLevel(lvIdx)))
    setQuizResult(null)
    setTyped('')
  }
  const pickLevel = (i) => { setLevel(i); setQuiz(null); setQuizResult(null); setTyped('') }
  const playQuiz = async () => {
    if (!quiz || playing) return
    const d = await tactileAPI.getSequence(quiz.answer)
    await playSequence(d.sequence)
  }
  // 정답 처리 공통 — 객관식/주관식 모두 여기로
  const grade = (picked, ok) => {
    setQuizResult({ ok, picked })
    setScore((s) => ({ correct: s.correct + (ok ? 1 : 0), total: s.total + 1 }))
    // 대시보드 촉각 진행도 + 복습(SRS/틀림)에 결과 반영 — target을 함께 보냄
    tactileAPI.submitResult(level, ok, quiz?.answer || '').catch(() => {})
  }
  const answerQuiz = (opt) => {
    if (!quiz || quizResult) return
    grade(opt, opt === quiz.answer)
  }
  const submitTyped = () => {
    if (!quiz || quizResult || !typed.trim()) return
    const norm = (s) => s.replace(/\s+/g, '')
    grade(typed.trim(), norm(typed) === norm(quiz.answer))
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-primary-50">
      <LearnHeader
        accent="tactile"
        title={hardwareView ? '얼굴 모형 · 하드웨어' : reviewMode ? '촉각 복습' : '촉각 학습'}
        description={hardwareView ? '실제 얼굴 모형을 만들고, 연결·핀 설정·신호 확인까지 여기서 해요' : '얼굴 모형의 턱·입술·진동·바람을 손으로 느끼며 말을 이해해요'}
        maxWidth="max-w-4xl"
        onExit={() => { disconnect(); navigate('/dashboard') }}
      />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* 브라우저 안내 */}
        {!supported ? (
          <div className="card border-l-4 border-amber-400 bg-amber-50">
            <p className="font-semibold text-amber-800">이 브라우저에서는 하드웨어 연결이 지원되지 않아요.</p>
            <p className="text-sm text-amber-700 mt-1">촉각 학습은 <b>데스크톱 Chrome 또는 Edge</b>에서만 얼굴 모형(USB)에 연결할 수 있어요(Web Serial API). Chrome/Edge로 접속해 주세요.</p>
          </div>
        ) : (
          <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700">
            ⓘ 하드웨어 연결(Web Serial)은 <b>데스크톱 Chrome·Edge</b>에서만 동작합니다. USB로 얼굴 모형을 연결한 뒤 아래 버튼을 눌러주세요.
          </div>
        )}

        {/* DIY — 오픈소스 하드웨어: 상세 설명서로 크게 유도 (하드웨어 탭 전용) */}
        {hardwareView && (
        <button
          onClick={() => navigate('/hardware/build')}
          className="group w-full overflow-hidden rounded-2xl bg-gradient-to-br from-purple-600 to-violet-500 p-5 text-left text-white shadow-lg shadow-purple-200 transition hover:shadow-xl hover:brightness-105 sm:p-6"
        >
          <div className="flex items-center gap-4">
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-white/20 text-3xl">🛠️</span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-black tracking-wider text-purple-100">오픈소스 하드웨어 · 직접 만들기</p>
              <h2 className="mt-0.5 text-lg font-black sm:text-xl">얼굴 모형 조립 설명서 보기</h2>
              <p className="mt-1 text-sm text-purple-50">
                3D 프린팅 파일 · 부품(BOM) · 조립 순서 · 배선도 · 펌웨어까지, 실제 제작 사진과 함께 이대로만 따라 하면 완성돼요.
              </p>
            </div>
            <span className="ml-1 shrink-0 text-2xl transition group-hover:translate-x-1">→</span>
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {['🧩 STL 파일', '📦 부품 목록', '🔧 조립·배선', '💾 펌웨어 다운로드'].map((t) => (
              <span key={t} className="rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold">{t}</span>
            ))}
          </div>
        </button>
        )}

        {/* 고급(선택): 내 핀 배치로 실시간 적용 / 맞춤 펌웨어 (하드웨어 탭 전용) */}
        {hardwareView && (
        <div className="card">
          <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-3">
            <p className="text-sm font-semibold text-gray-800">🔧 내 핀 배치 설정 <span className="text-xs font-normal text-gray-400">· 선택</span></p>
            <p className="mt-0.5 text-[11px] text-gray-500">
              각 부품을 연결한 아두이노 핀(D2~D13)을 입력하세요. 연결돼 있으면 <b>재업로드 없이 바로 적용</b>되고,
              오프라인 플래시용 <b>맞춤 펌웨어</b>도 받을 수 있어요.
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {PIN_FIELDS.map((f) => (
                <label key={f.key} className="text-xs font-medium text-gray-600">
                  {f.label}{f.pwm && <span className="text-purple-500"> · PWM</span>}
                  <div className="mt-0.5 flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-2 py-1">
                    <span className="text-gray-400">D</span>
                    <input type="number" min="2" max="13"
                      value={Number.isFinite(pins[f.key]) ? pins[f.key] : ''}
                      onChange={(e) => { const v = parseInt(e.target.value, 10); setPins((p) => ({ ...p, [f.key]: Number.isNaN(v) ? '' : v })) }}
                      className="w-full text-sm outline-none" />
                  </div>
                </label>
              ))}
            </div>
            <p className="mt-1 text-[10px] text-gray-400">D0·D1은 USB 통신용이라 제외돼요. 팬은 세기 조절이 필요해 서보와 겹치지 않는 PWM 핀(3·5·6·11)에 연결하세요.</p>
            <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              <button onClick={sendPins} disabled={!connected || playing}
                className="rounded-lg bg-purple-600 py-2 text-sm font-semibold text-white transition hover:bg-purple-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400">
                🔌 연결된 모형에 이 핀 적용
              </button>
              <button onClick={downloadCustomIno}
                className="rounded-lg border-2 border-purple-300 py-2 text-sm font-semibold text-purple-700 transition hover:bg-purple-100">
                ⬇ 맞춤 펌웨어(.ino) 받기
              </button>
            </div>
            {!connected && <p className="mt-1 text-[10px] text-gray-400">‘즉시 적용’은 아래 <b>얼굴 모형 연결</b> 후에 쓸 수 있어요. (한 번은 펌웨어를 업로드해 둬야 함)</p>}
            {pinMsg && <p className="mt-1 text-[11px] text-gray-600">{pinMsg}</p>}
          </div>
        </div>
        )}

        {/* 연결 (학습·복습·하드웨어 모두 — 실제 모형으로 느끼려면 필요) */}
        <div className="card">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-gray-900">얼굴 모형 연결 · {connected ? '🟢 연결됨' : '⚪ 연결 안 됨'}</p>
            {connected ? (
              <button onClick={disconnect} className="shrink-0 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50">연결 해제</button>
            ) : (
              <button onClick={connect} disabled={!supported}
                className="shrink-0 px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-semibold hover:bg-primary-700 disabled:opacity-40">🔌 얼굴 모형 연결</button>
            )}
          </div>
          {status && (
            <p className={`mt-1 text-xs leading-relaxed ${connected ? 'text-gray-500' : 'text-red-500'}`}>{status}</p>
          )}
          {!connected && (
            <p className="mt-1 text-[11px] text-gray-400">
              ※ <b>아두이노 IDE의 시리얼 모니터</b>가 열려 있으면 포트를 못 열어요(포트는 한 프로그램만 사용). 닫고 연결하세요. · 데스크톱 Chrome·Edge 전용.
            </p>
          )}
        </div>

        {/* 제어 신호 모니터 (하드웨어 탭 전용) */}
        {hardwareView && (
        <div className="card">
          <p className="mb-1 text-sm font-bold text-gray-900">📟 제어 신호 모니터</p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-gray-50 p-2">
              <div className="text-gray-400">웹 → 보드 (전송) · <b className="text-gray-700">{sentCount}건</b></div>
              <div className="mt-0.5 break-all font-mono text-[11px] text-purple-700">{lastSent || '—'}</div>
              <div className="text-[11px] text-gray-500">{decodeSentLine(lastSent)}</div>
            </div>
            <div className="rounded-lg bg-gray-50 p-2">
              <div className="text-gray-400">보드 → 웹 (응답) · <b className="text-gray-700">{replyCount}건</b></div>
              <div className="mt-0.5 break-all font-mono text-[11px] text-green-700">{boardReply || '—'}</div>
              <div className="text-[11px] text-gray-500">{replyCount > 0 ? '보드가 명령을 받고 있어요' : '아직 응답 없음'}</div>
            </div>
          </div>
          {connected && sentCount > 0 && replyCount === 0 && (
            <p className="mt-2 rounded-lg bg-amber-50 p-2 text-[11px] leading-relaxed text-amber-700">
              신호는 나가는데 <b>보드 응답이 없어요.</b> ① 펌웨어가 실제로 업로드됐는지 ② 올바른 포트를 골랐는지 ③ 9600 baud인지 확인하세요.
            </p>
          )}
          {connected && replyCount > 0 && (
            <p className="mt-2 rounded-lg bg-green-50 p-2 text-[11px] leading-relaxed text-green-700">
              보드가 응답 중이라 <b>신호는 정상 도달·처리</b>돼요. 그래도 안 움직이면 <b>서보·모터의 외부 5V 전원, 공통 GND, 핀 번호·배선</b>을 확인하세요. (서보 각도 범위가 작아 움직임이 미세할 수도)
            </p>
          )}
          {!connected && <p className="mt-1 text-[11px] text-gray-400">연결하면 전송/응답 신호가 실시간으로 표시돼요. 데스크톱 Chrome·Edge에서만 동작합니다.</p>}
        </div>
        )}

        {/* ── 학습·복습 콘텐츠 (하드웨어 탭에선 숨김) ── */}
        {!hardwareView && (<>

        {/* 복습 모드 배너 */}
        {reviewMode && (
          <div className="card border-l-4 border-purple-400 bg-purple-50">
            <p className="font-bold text-purple-800">🔁 촉각 복습</p>
          </div>
        )}

        {/* 모드 전환 — 학습(커리큘럼)이 기본, 체험은 보조 (복습 모드에선 숨김) */}
        {!reviewMode && (
        <div className="grid grid-cols-2 gap-2 p-1.5 bg-gray-100 rounded-2xl">
          {[['quiz', '🎯', '단계 학습', '커리큘럼 퀴즈'], ['explore', '🖐️', '자유 체험', '아무 말이나 느껴보기']].map(([id, icon, label, desc]) => (
            <button key={id} onClick={() => setMode(id)}
              className={`py-3 rounded-xl text-center transition-all ${mode === id ? 'bg-white shadow text-purple-700' : 'text-gray-500 hover:text-gray-700'}`}>
              <div className="text-xl leading-none mb-1">{icon}</div>
              <div className="font-bold text-sm">{label}</div>
              <div className="text-[11px] opacity-70">{desc}</div>
            </button>
          ))}
        </div>
        )}

        {mode === 'explore' && !reviewMode ? (
          <div className="card space-y-4">
            <div className="rounded-xl bg-gray-50 p-2">
              <p className="text-xs text-center text-gray-500 mb-1">
                얼굴 모형 시뮬레이터 {connected ? '· 하드웨어와 동시 동작' : '· 하드웨어 없이도 동작을 볼 수 있어요'}
              </p>
              <TactileFaceSim sim={sim} showLabel={true} />
            </div>
            <div>
              <p className="text-sm text-gray-500 mb-2">낱말·문장을 골라 재생하면 얼굴 모형이 그대로 재현해요. 손을 대고 느껴보세요.</p>
              <div className="flex flex-wrap gap-2 mb-3">
                {PRESET.map((w) => (
                  <button key={w} onClick={() => setText(w)}
                    className={`px-3 py-1.5 rounded-full text-sm border ${text === w ? 'border-primary-400 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}>{w}</button>
                ))}
              </div>
              <input value={text} onChange={(e) => setText(e.target.value)}
                className="input-field" placeholder="직접 입력 (한글 문장)" />
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => playText(text)} disabled={playing || !text.trim()}
                className="btn-primary px-6 py-3 disabled:opacity-50">{playing ? '재생 중…' : '▶ 재생 (느껴보기)'}</button>
              {!connected && <span className="text-xs text-gray-400">하드웨어 미연결 — 시뮬레이터로 재생</span>}
            </div>
          </div>
        ) : (
          <>
          {/* ── 촉각 커리큘럼 5단계 (체계적 학습 경로) — 복습 모드에선 숨김 ── */}
          {!reviewMode && (
          <div className="card">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="text-base font-bold text-gray-900">촉각 커리큘럼 · 5단계</h2>
              <span className="text-xs text-gray-400">감각 → 변별 → 문장</span>
            </div>
            <p className="mb-3 text-xs text-gray-500">
              쉬운 촉각 단서부터 시작해 단계적으로 실제 말 이해까지 확장하는 체계적 과정이에요. 단계를 골라 퀴즈로 익혀요.
            </p>
            <div className="space-y-1.5">
              {LEVELS.map((lv, i) => {
                const active = i === level
                return (
                  <button key={i} onClick={() => pickLevel(i)}
                    className={`flex w-full items-center gap-3 rounded-xl border-2 p-2.5 text-left transition-all ${active ? 'border-purple-400 bg-purple-50' : 'border-gray-100 bg-white hover:border-gray-300'}`}>
                    <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${active ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-500'}`}>{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm font-bold ${active ? 'text-purple-800' : 'text-gray-800'}`}>{lv.title}</div>
                      <div className="truncate text-xs text-gray-500">{lv.goal}</div>
                    </div>
                    {active && <span className="shrink-0 text-xs font-semibold text-purple-600">학습 중 →</span>}
                  </button>
                )
              })}
            </div>
          </div>
          )}

          {/* ── 선택한 단계 퀴즈 ── */}
          <div className="card space-y-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm text-gray-500">
                {reviewMode
                  ? <b className="text-purple-700">🔁 복습 문제</b>
                  : <><b className="text-gray-700">{level + 1}단계 · {LEVELS[level].title}</b> — {LEVELS[level].desc}</>}
              </p>
              <div className="flex shrink-0 items-center gap-3">
                {quiz && quizResult && (
                  <button onClick={() => toggleMark(quiz.answer)} title="북마크(복습에 추가)"
                    className={`whitespace-nowrap text-sm ${marks[quiz.answer] ? 'text-amber-500' : 'text-gray-300 hover:text-amber-400'}`}>
                    {marks[quiz.answer] ? '★ 북마크됨' : '☆ 북마크'}
                  </button>
                )}
                <button onClick={() => setSimHidden((v) => !v)} className="whitespace-nowrap text-xs text-gray-400 underline">
                  {simHidden ? '👁 시뮬레이터 보기' : '🙈 가리기(순수 촉각)'}
                </button>
                <span className="whitespace-nowrap text-sm text-gray-500">점수 {score.correct}/{score.total}</span>
              </div>
            </div>

            {/* 시뮬레이터 — 선택지 바로 위에 두어 '느끼고 → 바로 답하기' 동선을 짧게 */}
            {!simHidden && (
              <div className="rounded-xl bg-gray-50 p-2">
                <p className="mb-1 text-center text-xs text-gray-500">
                  얼굴 모형 시뮬레이터 {connected ? '· 하드웨어와 동시 동작' : '· 하드웨어 없이도 동작을 볼 수 있어요'}
                </p>
                <TactileFaceSim sim={sim} showLabel={false} />
              </div>
            )}

            {!quiz ? (
              reviewMode
                ? <p className="py-4 text-center text-sm text-gray-400">{reviewPool == null ? '복습 항목 불러오는 중…' : '복습할 항목이 없어요.'}</p>
                : <button onClick={() => newQuiz()} className="btn-primary w-full py-3">이 단계 퀴즈 풀기</button>
            ) : (
              <>
                <button onClick={playQuiz} disabled={playing}
                  className="w-full rounded-xl bg-purple-600 py-3 font-semibold text-white transition-all hover:bg-purple-700 disabled:opacity-50">
                  {playing ? '재생 중… 손으로 느껴보세요' : '🖐️ 느끼기 (재생)'}
                </button>
                <div className="flex justify-center">
                  <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-[11px] font-medium text-purple-700">
                    {quiz.type === 'input' ? '주관식 · 느낀 말을 직접 입력' : '객관식 · 보기에서 고르기'}
                  </span>
                </div>
                {quiz.type === 'input' ? (
                  <div className="space-y-2">
                    <input value={typed} onChange={(e) => setTyped(e.target.value)} disabled={!!quizResult}
                      onKeyDown={(e) => { if (e.key === 'Enter') submitTyped() }}
                      className={`input-field text-center text-lg ${quizResult ? (quizResult.ok ? 'border-green-400 bg-green-50' : 'border-red-300 bg-red-50') : ''}`}
                      placeholder="느낀 말을 입력하세요" />
                    {!quizResult && (
                      <button onClick={submitTyped} disabled={!typed.trim()}
                        className="btn-primary w-full py-2.5 disabled:opacity-50">제출</button>
                    )}
                  </div>
                ) : (
                  <div className={`grid gap-2 ${quiz.options.length > 2 ? 'grid-cols-3' : 'grid-cols-2'}`}>
                    {quiz.options.map((opt) => {
                      const picked = quizResult?.picked === opt
                      const isAnswer = quizResult && opt === quiz.answer
                      const cls = quizResult
                        ? (isAnswer ? 'border-green-400 bg-green-50 text-green-700'
                          : picked ? 'border-red-300 bg-red-50 text-red-600' : 'border-gray-200 text-gray-300')
                        : 'border-gray-200 hover:border-purple-400 hover:bg-purple-50 text-gray-800'
                      return (
                        <button key={opt} onClick={() => answerQuiz(opt)} disabled={!!quizResult}
                          className={`rounded-xl border-2 py-4 text-xl font-bold transition-all ${cls}`}>{opt}</button>
                      )
                    })}
                  </div>
                )}
                {quizResult && (
                  <div className={`rounded-lg p-3 text-center text-sm ${quizResult.ok ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
                    {quizResult.ok ? '정답! 🎉' : `정답은 "${quiz.answer}" 였어요.`}
                    <button onClick={() => newQuiz()} className="ml-3 font-semibold underline">다음 →</button>
                  </div>
                )}
              </>
            )}
          </div>
          </>
        )}

        <p className="text-xs text-gray-400 text-center">
          ‘바다’와 ‘파도’처럼 입모양이 비슷한 말도, 진동(성대)과 바람(기류)의 차이로 촉각으로는 구별됩니다.
        </p>
        </>)}
      </main>
    </div>
  )
}
