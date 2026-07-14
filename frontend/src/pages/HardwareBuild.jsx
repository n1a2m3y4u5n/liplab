import { useNavigate } from 'react-router-dom'
import LearnHeader from '../components/LearnHeader'

/**
 * 타도마 촉각 학습기 — 하드웨어 조립 설명서 (레고 설명서 스타일)
 * 원본: Tadoma_학습기_사용설명서.docx + 실제 제작 사진 13장.
 * "이대로만 따라 하면 작동한다"를 목표로, 준비물 → 용어 → 조립 → 배선 → 점검 순서로 정리.
 */

const PHOTO = (name) => `/hardware/photos/${name}.jpg`

// 내려받을 3D 프린팅 파일 (public/hardware/)
const STL_FILES = [
  { f: 'liplab_face_shell.stl', label: '얼굴 본체', desc: '코~입~턱 셸' },
  { f: 'liplab_support.stl', label: '연결대', desc: '좌우 연결부 한 쌍' },
  { f: 'liplab_hinge.stl', label: '지지대(다리)', desc: '회전축 다리 한 쌍' },
]

// 3개 촉각 채널
const CHANNELS = [
  { ch: '턱 개폐', how: '서보모터 + 힌지 회전 구조', info: '모음의 입 벌림 정도 (개방도)' },
  { ch: '후두 진동', how: '코인형 진동모터', info: '유성음 / 무성음 구분' },
  { ch: '기류', how: '소형 DC 팬', info: '파열음 / 마찰음 구분' },
]

// 2.1 3D 프린팅 파츠
const PARTS_3D = [
  { name: 'liplab_face_shell.stl', src: '자체 설계', size: '9.6 × 9.6 × 5.8 cm', qty: '1', note: '얼굴 앞면 셸 (코~입~턱)' },
  { name: 'liplab_support.stl', src: '자체 설계', size: '11.1 × 12.9 × 0.8 cm', qty: '1 (좌우 한 쌍 포함)', note: '얼굴-힌지 연결대' },
  { name: 'liplab_hinge.stl', src: '자체 설계', size: '9.0 × 4.3 × 1.7 cm', qty: '1 (좌우 한 쌍 포함)', note: '회전축, 핀 지름 0.78cm' },
  { name: '받침대 통합파일', src: '자체 설계', size: '9.5 × 6.0 × 7.0 cm', qty: '1', note: '받침대 + 목탭 포함' },
]

// 2.2 전자부품 (BOM)
const BOM = [
  { part: '서보모터', spec: 'SG90 또는 MG996 계열, 4.8~6V', qty: '1', use: '턱 개폐 구동' },
  { part: '코인형 진동모터', spec: '1027 규격, DC 3V', qty: '1', use: '후두 진동' },
  { part: '소형 DC 팬', spec: 'DC 5V, 40×40mm급', qty: '1', use: '기류' },
  { part: '트랜지스터', spec: 'KTC8050D (NPN)', qty: '2', use: '진동모터·팬 스위칭' },
  { part: '저항', spec: '220Ω (200Ω도 무방)', qty: '2', use: '트랜지스터 베이스 전류 제한' },
  { part: '다이오드', spec: '1N4007', qty: '2 (권장)', use: '모터 역기전력 보호' },
  { part: '아두이노 보드', spec: 'Uno 또는 호환보드', qty: '1', use: '제어부' },
  { part: '외부전원', spec: 'DC 5V', qty: '1', use: '서보·모터·팬 전원 공급' },
]

const TOOLS = [
  '글루건 (일반 접착용)',
  '양면테이프 — 폼테이프 권장 (진동모터·팬 부착)',
  '브레드보드 · 점퍼선',
  '니퍼 · 와이어스트리퍼',
]

// 3. 용어 (부품 사진으로 익히기)
const GLOSSARY = [
  { term: '받침대', desc: '밑판 + 기둥 + 윗판으로 된 흰색 거치대. 장치 전체를 책상 위에 세운다.', photo: 'base' },
  { term: '지지대(다리)', desc: '받침대 윗판 옆에 좌우로 세우는 흰색 다리 2개(liplab_hinge). 여기에 연결대를 연결한다.', photo: 'support' },
  { term: '연결대', desc: '지지대와 얼굴조립체를 잇는 연결부(liplab_support). 한쪽은 서보와 함께 움직이고, 반대쪽은 지지대에 걸쳐 회전축이 된다.', photo: null },
  { term: '얼굴조립체', desc: '반구형 돔 흰색 셸(liplab_face_shell). 한쪽엔 톱니 모양 이빨 테두리, 반대쪽엔 마름모 구멍(원래 눈 자리, 미사용)이 있다.', photo: 'done-side' },
  { term: '서보모터', desc: '파란색 소형 모터. 회전하며 얼굴조립체를 움직여 턱을 여닫는다.', photo: 'servofan' },
  { term: '팬', desc: '검정색 사각형 송풍팬. 코 부위로 바람을 보내 기류를 표현한다.', photo: 'servofan-top' },
  { term: '진동모터', desc: '은색 원판 모양의 작은 부품. 전기가 통하면 떨려서 후두 진동을 표현한다.', photo: 'vibmotor' },
  { term: '목탭', desc: '진동모터를 붙이기 위해 얼굴조립체 안쪽에 먼저 부착하는 작은 평판 조각.', photo: null },
]

// 4. 조립 순서
const STEPS = [
  {
    n: 1, code: '4.1', title: '전체 구조 한눈에 보기', photos: ['overview'],
    body: [
      '받침대 윗판 옆에 지지대(다리) 2개를 세우고, 각 지지대에 연결대를 연결한다.',
      '좌우로 연결된 연결대에 얼굴조립체를 얹는다.',
      '서보모터는 연결대에 붙어, 회전하며 얼굴조립체를 함께 움직인다. 반대쪽 연결대는 지지대에 걸쳐만 두어 회전축이 된다.',
      '팬은 서보 위 윗면 가운데쯤에, 진동모터는 얼굴조립체 아랫면에 붙인다.',
    ],
    tip: '문 경첩과 같은 원리다. 경첩 두 개 중 서보가 있는 한쪽만 힘을 줘도, 얼굴조립체 전체가 반대쪽 지지대를 축으로 함께 회전한다.',
  },
  {
    n: 2, code: '4.2', title: '받침대 준비', photos: ['base'],
    body: [
      '밑판 + 기둥 + 윗판 형태로 조립된 받침대를 평평한 곳에 놓는다.',
      '윗판 크기는 가로 9.5cm × 세로 6.0cm이다.',
    ],
  },
  {
    n: 3, code: '4.3', title: '지지대(다리) 세우기', photos: ['support'],
    body: [
      '지지대(다리) 2개를 받침대 윗판 옆에 좌우로 나란히 세운다.',
      '두 지지대 사이 간격은 얼굴조립체 테두리 폭(약 9.6cm)에 맞춘다.',
      '각 지지대의 핀이 바깥쪽으로 나가도록 방향을 잡는다.',
      '글루건으로 지지대 옆면을 윗판 끝쪽에 고정한다.',
    ],
  },
  {
    n: 4, code: '4.4', title: '연결대 연결', photos: ['support'],
    body: [
      '좌우 지지대 각각에 연결대를 연결한다.',
      '이 연결부가 이후 얼굴조립체의 회전축이 되므로, 양쪽 연결대가 수평으로 나란히 정렬되는지 확인한다.',
    ],
  },
  {
    n: 5, code: '4.5', title: '서보모터와 팬 장착', photos: ['servofan-top', 'servofan'],
    body: [
      '서보모터를 두 지지대 사이, 한쪽 연결대에 가깝게 놓고 글루건으로 붙인다. 이 부위는 서보와 함께 움직이는 쪽이다.',
      '팬은 서보모터 위에 걸쳐 윗면 가운데쯤에 놓고 글루건으로 고정한다.',
      '팬의 바람 나오는 면이 얼굴조립체 안쪽(코가 올 방향)을 향하도록 각도를 맞춘다.',
    ],
  },
  {
    n: 6, code: '4.6', title: '얼굴조립체 연결', photos: ['done-front'],
    body: [
      '얼굴조립체를 좌우 연결대에 얹어 연결한다.',
      '이빨 테두리가 있는 쪽이 정면(사용자 쪽), 마름모 구멍이 있는 쪽이 뒤를 향하게 방향을 맞춘다.',
      '접착 전에 손으로 살짝 움직여, 앞뒤로 부드럽게 기울어지는지·어딘가에 걸리지 않는지 확인한다.',
    ],
    warn: '서보와 맞닿는 부위는 계속 힘을 받아 접착이 약하면 나중에 떨어질 수 있다. 실제 제작에서는 이 연결부에 글루건을 넉넉히 발라 보강했다 — 필요하면 덧발라 준다.',
  },
  {
    n: 7, code: '4.7', title: '진동모터 부착', photos: ['vibmotor'],
    body: [
      '목탭을 얼굴조립체 아랫면에 양면테이프로 붙인다.',
      '목탭 위에 진동모터(은색 원판)를 부착한다.',
      '진동모터 전선은 얼굴조립체가 회전할 때 팽팽히 당겨지거나 걸리지 않도록 여유를 둔다.',
    ],
  },
  {
    n: 8, code: '4.8', title: '배선 정리', photos: ['wiring1'],
    body: [
      '서보·팬·진동모터에서 나온 전선을 받침대 뒤쪽으로 모은다.',
      '브레드보드를 받침대 옆이나 뒤에 두고, 점퍼선으로 각 부품과 아두이노를 연결한다.',
      '자세한 연결은 아래 "5. 배선도"를 그대로 따른다.',
    ],
  },
]

// 5. 배선 표
const WIRE_SERVO = [
  ['빨강 (+)', '외부전원 (+)'],
  ['검정 (GND)', '외부전원 (−)'],
  ['노랑 (신호)', '아두이노 D9'],
]
const WIRE_VIB = [
  ['아두이노 D5', '저항1 (220Ω) 한쪽'],
  ['저항1 반대쪽', '트랜지스터1 베이스 (B, 가운데 핀)'],
  ['트랜지스터1 컬렉터 (C, 오른쪽 핀)', '진동모터 (+)'],
  ['트랜지스터1 이미터 (E, 왼쪽 핀)', '외부전원 (−)'],
  ['진동모터 (−)', '외부전원 (−)'],
  ['다이오드1 (권장)', '진동모터 양단에 역방향 병렬 — 띠 있는 쪽이 (+) 방향'],
]
const WIRE_FAN = [
  ['아두이노 D6', '저항2 (220Ω) 한쪽'],
  ['저항2 반대쪽', '트랜지스터2 베이스 (B, 가운데 핀)'],
  ['트랜지스터2 컬렉터 (C, 오른쪽 핀)', '팬 (+)'],
  ['트랜지스터2 이미터 (E, 왼쪽 핀)', '외부전원 (−)'],
  ['팬 (−)', '외부전원 (−)'],
  ['다이오드2 (권장)', '팬 양단에 역방향 병렬 — 띠 있는 쪽이 (+) 방향'],
]
const PIN_SUMMARY = [
  ['D9', '턱 서보 신호선'],
  ['D5', '진동모터 회로 (저항 경유)'],
  ['D6', '팬 회로 (저항 경유)'],
  ['GND', '외부전원 (−) 공통 연결'],
]

// 6. 최종 점검
const CHECKS = [
  '서보를 0~20도 범위로 천천히 돌려, 얼굴조립체가 받침대·힌지 어디에도 걸리지 않고 부드럽게 회전하는지 확인한다.',
  '진동모터 통전 시 얼굴 표면 전체에 진동이 고르게 전달되는지 손으로 확인한다.',
  '팬 통전 시 코 위치에서 바람이 느껴지는지 확인한다.',
  '트랜지스터 회로는 처음 작동 시 손으로 만져 발열을 확인한다. 뜨거우면 즉시 전원을 끄고 배선을 다시 점검한다.',
  '다이오드 없이 쓸 경우, 모터·팬을 급히 켜고 끄지 말고 세기를 점진적으로 조절하는 소프트웨어 로직을 사용해 역기전력 위험을 낮춘다.',
]

// ── 재사용 컴포넌트 ──────────────────────────────────────
function Figure({ name, caption }) {
  return (
    <figure className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <img src={PHOTO(name)} alt={caption || name} loading="lazy" className="w-full object-cover" />
      {caption && <figcaption className="px-4 py-2.5 text-xs text-slate-500">{caption}</figcaption>}
    </figure>
  )
}

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="bg-slate-50 text-left">
            {head.map((h) => (
              <th key={h} className="border-b border-slate-200 px-3 py-2.5 font-black text-slate-700">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="odd:bg-white even:bg-slate-50/40">
              {r.map((c, j) => (
                <td key={j} className={`border-b border-slate-100 px-3 py-2.5 align-top ${j === 0 ? 'font-bold text-slate-800' : 'text-slate-600'}`}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DownloadCard({ href, download, icon, label, sub }) {
  return (
    <a href={href} download={download}
      className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-violet-400 hover:bg-violet-50">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-violet-100 text-xl">{icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-bold text-slate-900">{label}</span>
        <span className="block text-xs text-slate-500">{sub}</span>
      </span>
      <span className="ml-auto shrink-0 text-violet-500">⬇</span>
    </a>
  )
}

function SectionTitle({ eyebrow, children }) {
  return (
    <div className="mb-4">
      {eyebrow && <p className="text-xs font-black tracking-[0.14em] text-violet-600">{eyebrow}</p>}
      <h2 className="mt-1 text-xl font-black text-slate-900 sm:text-2xl">{children}</h2>
    </div>
  )
}

export default function HardwareBuild() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <LearnHeader
        title="타도마 학습기 조립 설명서"
        description="3D 프린팅 얼굴 모형을 직접 만드는 전 과정 — 이대로만 따라 하면 작동합니다."
        accent="tactile"
        onExit={() => navigate('/learn/tactile')}
      />

      <main className="mx-auto max-w-3xl space-y-14 px-4 py-8 sm:py-10">

        {/* 완성 목표 */}
        <section>
          <SectionTitle eyebrow="목표">완성된 모습</SectionTitle>
          <p className="mb-4 text-sm leading-relaxed text-slate-600">
            코~입~턱까지의 얼굴 모형이 받침대 위에 세워지고, 서보(턱)·진동모터(후두)·팬(기류) 세 채널이
            아두이노로 제어됩니다. 아래가 최종 완성 형태예요.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Figure name="done-side" caption="완성 측면 — 돔형 얼굴 셸이 받침대 위에서 앞뒤로 회전한다" />
            <Figure name="done-front" caption="완성 정면 — 서보·팬이 얼굴 안쪽에, 아두이노·브레드보드로 배선" />
          </div>
        </section>

        {/* 1. 개요 */}
        <section>
          <SectionTitle eyebrow="1. 개요">세 개의 촉각 채널</SectionTitle>
          <p className="mb-4 text-sm leading-relaxed text-slate-600">
            타도마는 손을 얼굴에 대고 발화를 촉각으로 읽는 방법이에요. 이 장치는 웹사이트(LIPLAB)에서
            문장을 음소 단위로 분석한 결과를 시리얼 통신으로 받아, 아래 세 채널로 재현합니다.
          </p>
          <Table head={['채널', '구현 방식', '표현 정보']} rows={CHANNELS.map((c) => [c.ch, c.how, c.info])} />
          <p className="mt-3 text-xs leading-relaxed text-slate-500">
            ※ 입술 돌출(원순/평순) 채널은 최종 구현에서 제외했습니다. 얼굴 형태는 촉각 전달과 무관한
            눈·귀·이마는 빼고, 촉각으로 말을 읽는 데 필요한 코~입~턱 범위만 구현했어요.
          </p>
        </section>

        {/* 2. 준비물 */}
        <section>
          <SectionTitle eyebrow="2. 준비물">무엇을 준비하나요</SectionTitle>

          <h3 className="mb-2 mt-1 font-black text-slate-800">2.1 · 3D 프린팅 파츠</h3>
          <Table head={['파일명', '출처', '규격(가로×세로×높이)', '수량', '비고']}
            rows={PARTS_3D.map((p) => [p.name, p.src, p.size, p.qty, p.note])} />
          <p className="mt-2 text-xs leading-relaxed text-slate-500">
            ※ liplab_support와 liplab_hinge는 좌우 두 조각이 한 STL 파일에 들어 있으니 각각 1회씩만 프린트하면 됩니다.
            받침대 통합파일은 팀 자체 설계 파일이에요.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {STL_FILES.map((s) => (
              <DownloadCard key={s.f} href={`/hardware/${s.f}`} download={s.f} icon="🧩" label={s.label} sub={s.desc} />
            ))}
          </div>

          <h3 className="mb-2 mt-6 font-black text-slate-800">2.2 · 전자부품</h3>
          <Table head={['부품', '규격', '수량', '용도']} rows={BOM.map((b) => [b.part, b.spec, b.qty, b.use])} />

          <h3 className="mb-2 mt-6 font-black text-slate-800">2.3 · 공구 및 소모품</h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {TOOLS.map((t) => (
              <li key={t} className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700">
                <span className="text-violet-500">▪</span>{t}
              </li>
            ))}
          </ul>
        </section>

        {/* 3. 용어 */}
        <section>
          <SectionTitle eyebrow="3. 용어">부품 이름부터 익히기</SectionTitle>
          <p className="mb-4 text-sm leading-relaxed text-slate-600">
            조립을 시작하기 전에, 아래 부품 이름을 사진과 함께 눈에 익혀 두세요. 이후 설명이 훨씬 쉬워집니다.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {GLOSSARY.map((g) => (
              <div key={g.term} className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                {g.photo && <img src={PHOTO(g.photo)} alt={g.term} loading="lazy" className="h-40 w-full object-cover" />}
                <div className="p-4">
                  <p className="font-black text-slate-900">{g.term}</p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-600">{g.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 4. 조립 순서 */}
        <section>
          <SectionTitle eyebrow="4. 조립 순서">순서대로 따라 만들기</SectionTitle>
          <div className="space-y-5">
            {STEPS.map((s) => (
              <div
                key={s.code}
                className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-6"
              >
                <div className="mb-3 flex items-center gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-violet-600 text-base font-black text-white">{s.n}</span>
                  <div>
                    <p className="text-xs font-black tracking-wide text-violet-500">STEP {s.code}</p>
                    <h3 className="text-lg font-black text-slate-900">{s.title}</h3>
                  </div>
                </div>

                <ol className="mb-4 space-y-2">
                  {s.body.map((line, i) => (
                    <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-slate-700">
                      <span className="shrink-0 font-black text-slate-300">{i + 1}</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ol>

                {s.photos && (
                  <div className={`grid gap-3 ${s.photos.length > 1 ? 'sm:grid-cols-2' : ''}`}>
                    {s.photos.map((p) => <Figure key={p} name={p} />)}
                  </div>
                )}

                {s.tip && (
                  <div className="mt-4 rounded-xl bg-violet-50 px-4 py-3 text-sm leading-relaxed text-violet-900">
                    <span className="font-black">💡 원리 · </span>{s.tip}
                  </div>
                )}
                {s.warn && (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-900">
                    <span className="font-black">⚠️ 주의 · </span>{s.warn}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* 5. 배선도 */}
        <section>
          <SectionTitle eyebrow="5. 배선도">전선 연결하기</SectionTitle>
          <div className="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700">
            <span className="font-black">트랜지스터(KTC8050D) 핀 순서 · </span>
            평평한 면을 정면으로 봤을 때 <b>왼쪽부터 이미터(E) — 베이스(B) — 컬렉터(C)</b> 순입니다.
          </div>

          <div className="space-y-6">
            <div>
              <h3 className="mb-2 font-black text-slate-800">5.1 · 턱 서보</h3>
              <Table head={['서보 선', '연결 위치']} rows={WIRE_SERVO} />
            </div>
            <div>
              <h3 className="mb-2 font-black text-slate-800">5.2 · 진동모터 (트랜지스터1 회로)</h3>
              <Table head={['핀 / 선', '연결 위치']} rows={WIRE_VIB} />
            </div>
            <div>
              <h3 className="mb-2 font-black text-slate-800">5.3 · 팬 (트랜지스터2 회로)</h3>
              <Table head={['핀 / 선', '연결 위치']} rows={WIRE_FAN} />
            </div>

            <div className="rounded-2xl border-2 border-rose-200 bg-rose-50 p-4">
              <p className="font-black text-rose-800">5.4 · 공통 접지 (필수)</p>
              <p className="mt-1 text-sm leading-relaxed text-rose-900">
                <b>외부전원 (−) 를 아두이노 GND와 반드시 연결</b>하세요. 이 연결이 빠지면 전체 회로가 아예 작동하지 않습니다.
              </p>
            </div>

            <div>
              <h3 className="mb-2 font-black text-slate-800">5.5 · 아두이노 핀 배정 요약</h3>
              <Table head={['핀', '용도']} rows={PIN_SUMMARY} />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Figure name="wiring1" caption="실제 브레드보드 배선 — 트랜지스터·저항·점퍼선" />
              <Figure name="wiring2" caption="배선 다른 각도 — 좌측 전원 레일 기준" />
            </div>
          </div>
        </section>

        {/* 6. 최종 점검 */}
        <section>
          <SectionTitle eyebrow="6. 최종 점검">작동 확인</SectionTitle>
          <ol className="space-y-2">
            {CHECKS.map((c, i) => (
              <li key={i} className="flex gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-slate-900 text-xs font-black text-white">{i + 1}</span>
                <span>{c}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* 펌웨어 업로드 + IDE 닫기 (강조) */}
        <section>
          <SectionTitle eyebrow="7. 펌웨어 & 연결">코드 올리고 웹에 연결</SectionTitle>

          <div className="mb-4">
            <DownloadCard href="/hardware/liplab_face.ino" download="liplab_face.ino" icon="💾"
              label="기본 펌웨어 내려받기 (liplab_face.ino)" sub="기본 핀 D9·D5·D6이 위 배선과 이미 일치해요" />
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              부품을 다른 핀에 연결했다면, 촉각 학습 페이지의 <b>"내 핀 배치 설정"</b>에서 맞춤 펌웨어(.ino)를 받거나
              연결된 모형에 재업로드 없이 바로 적용할 수 있어요.
            </p>
          </div>

          <ol className="space-y-2">
            {[
              '위 버튼으로 펌웨어(liplab_face.ino)를 내려받습니다. (기본 핀 D9·D5·D6이 위 배선과 이미 일치합니다.)',
              '아두이노 IDE에서 이 파일을 열고, USB로 아두이노를 연결한 뒤 업로드합니다.',
              '업로드가 끝나고 정상 작동을 확인했다면, 다음 안내에 따라 IDE 창을 닫습니다.',
            ].map((c, i) => (
              <li key={i} className="flex gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-violet-600 text-xs font-black text-white">{i + 1}</span>
                <span>{c}</span>
              </li>
            ))}
          </ol>

          <div className="mt-4 rounded-2xl border-2 border-rose-300 bg-rose-50 p-5">
            <p className="flex items-center gap-2 text-base font-black text-rose-800">
              <span className="text-xl">🚨</span> 반드시 아두이노 IDE 창을 닫으세요
            </p>
            <p className="mt-2 text-sm leading-relaxed text-rose-900">
              아두이노 IDE가 켜져 있으면 <b>시리얼 포트를 IDE가 점유</b>하고 있어, 웹사이트가 같은 포트로
              연결할 수 없습니다. 코드를 업로드해 작동을 확인한 뒤에는 <b>IDE 창을 완전히 닫고</b>(시리얼 모니터도 함께),
              그 다음 웹에서 "얼굴 모형 연결"을 눌러 학습을 시작하세요.
            </p>
            <p className="mt-2 text-xs text-rose-700">
              증상: 웹에서 연결을 눌러도 포트가 열리지 않거나 "포트를 열 수 없어요" 오류가 나면, 대부분 IDE가 아직 포트를 잡고 있는 경우입니다.
            </p>
          </div>

          <div className="mt-4 rounded-xl bg-slate-100 px-4 py-3 text-sm leading-relaxed text-slate-600">
            ⓘ 웹↔하드웨어 연결(Web Serial)은 <b>데스크톱 Chrome · Edge</b>에서만 동작합니다. USB로 얼굴 모형을 연결한 상태에서 사용하세요.
          </div>
        </section>

        <div className="pt-2 text-center">
          <button onClick={() => navigate('/learn/tactile')} className="rounded-xl bg-violet-600 px-8 py-3 text-sm font-bold text-white transition hover:bg-violet-500">
            촉각 학습으로 돌아가기 →
          </button>
        </div>
      </main>
    </div>
  )
}
