import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'

/**
 * 이용약관 · 개인정보 처리방침 · 미성년자 보호 안내 (§4.9 보안·개인정보 대응).
 * /terms · /privacy 두 라우트가 이 페이지를 공유하며, 회원가입 동의 문구에서 링크로 연결된다.
 * /privacy로 들어오면 개인정보 처리방침 절로 바로 내려간다.
 * Figma 프레임이 없는 법적 요건 페이지라 디자인 토큰(page 배경·흰 카드 r22·ink/line)과 공용 로고로만 꾸민다.
 * 시행일은 backend/main.py의 _TERMS_VERSION·_PRIVACY_VERSION과 같게 유지한다(가입 동의 기록에 남는 판본).
 * 내용은 실제 데이터 흐름 기준이다: 웹캠 영상은 기기 안, 입모양 수치·음성은 서버로 전송(음성은 저장 안 함),
 * 전사문·음성 지표는 저장, LLM(Anthropic)에는 학습 문장만(식별 정보 없음), 호스팅은 Fly.io 도쿄 리전.
 */
const EFFECTIVE_DATE = '2026-09-23'
// 개인정보 보호책임자 — 공개 배포 전에 팀 대표 연락처를 넣어야 한다(비어 있으면 '공개 전 기재'로 보인다).
const PRIVACY_OFFICER = { name: 'LIPLAB 팀장', contact: '' }
function Section({ id, title, children }) {
  return (
    <section id={id} className="flex scroll-mt-6 flex-col gap-3">
      <h2 className="text-[20px] font-bold leading-figma tracking-[-0.4px] text-ink">{title}</h2>
      <div className="flex flex-col gap-2 text-[14.5px] leading-relaxed text-ink-muted">{children}</div>
    </section>
  )
}

export default function Legal() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  // /privacy는 개인정보 처리방침 절로 바로(ScrollToTop이 맨 위로 올린 뒤에 내려간다).
  useEffect(() => {
    if (pathname !== '/privacy') return undefined
    const t = window.setTimeout(() => document.getElementById('privacy')?.scrollIntoView({ block: 'start' }), 0)
    return () => window.clearTimeout(t)
  }, [pathname])

  // 닫기 — 가입 화면의 링크는 새 탭으로 열려 되돌아갈 기록이 없다. 그 탭은 닫고, 닫히지 않으면 처음 화면으로.
  const close = () => {
    if (window.history.length > 1) { navigate(-1); return }
    window.close()
    window.setTimeout(() => { if (!window.closed) navigate('/') }, 150)
  }

  return (
    <div className="min-h-[100dvh] bg-page px-4 py-10">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 rounded-22 border-2 border-line bg-white p-8 sm:p-10">
        <div className="flex items-center justify-between">
          <Logo size={24} />
          <button type="button" onClick={close} className="text-[14px] font-bold text-primary-500">닫기</button>
        </div>

        <h1 className="text-[25px] font-bold leading-figma tracking-[-0.625px] text-ink lg:text-[30px] lg:tracking-[-0.75px]">
          이용약관 · 개인정보 처리방침
        </h1>

        <Section id="terms" title="이용약관">
          <p>LIPLAB(이하 서비스)은 청각장애 학습자를 위한 한국어 독화·발화 훈련 학습 도구입니다. 이용자는 학습 목적에 한하여 서비스를 이용하며, 타인의 계정을 도용하거나 서비스 운영을 방해하는 행위를 하지 않습니다.</p>
          <p>서비스는 연구·교육용 프로토타입으로 제공되며, 학습 콘텐츠와 채점 결과의 정확성을 보증하지 않습니다. 서비스는 사전 고지 후 기능을 변경하거나 종료할 수 있습니다.</p>
        </Section>

        <Section id="privacy" title="개인정보 처리방침">
          <p className="text-[13px]">시행일 {EFFECTIVE_DATE}</p>
          <p><b className="text-ink">수집 항목</b> — 이메일, 표시 이름, 비밀번호(복호화할 수 없는 해시로 저장), 가입 동의 기록(동의한 약관·처리방침 판본, 동의 시각, 연령 확인 여부), 학습 기록(문항별 정오답, 문장 채점 점수, 말하기 연습의 전사문·점수·음성 지표[크기·음높이 범위·길이·억양 시작과 끝]·소리별 점수·코칭 문장, 소리·입모양·융합 점수, 입모양 연습의 점수와 교정 세션 처음·끝 오차), 파일럿 연구에 참여한 경우 참여 코드와 집단.</p>
          <p><b className="text-ink">이용 목적</b> — 계정 식별, 학습 진행 관리, 약점에 맞춘 문항 추천, 학습 효과 분석.</p>
          <p><b className="text-ink">웹캠</b> — 웹캠 영상은 <b className="text-ink">기기 안에서만 처리</b>하며 서버로 보내지 않습니다. 입모양 연습 중에는 기기에서 계산한 입모양 수치(턱 벌림·입술 둥글림·입술 다물기)와 점수를 교정 안내와 약점 분석을 위해 서버로 보냅니다. 입모양 수치의 원본(프레임마다의 값)은 저장하지 않고, 연습마다의 점수와 교정 세션의 처음·끝 오차(목표와의 평균 차이), 그리고 점수에서 나온 약점 정보만 학습 기록에 남습니다.</p>
          <p><b className="text-ink">음성</b> — 말하기 채점을 할 때 녹음한 음성을 서버로 보내 메모리에서만 처리하고 저장하지 않습니다. 채점 결과인 전사문과 음성 지표는 학습 기록으로 저장합니다.</p>
          <p><b className="text-ink">처리 위탁·국외 이전</b> — ① Fly.io, Inc.(미국): 서비스 호스팅과 데이터 저장. 서버는 일본 도쿄 리전에 있습니다. ② Anthropic, PBC(미국): 학습 문장·대화·코칭 문구 생성. 학습 문장과 채점에 필요한 전사문만 보내며 이메일·이름 등 이용자를 식별하는 정보는 보내지 않습니다. 두 경우 모두 서비스 이용 중 네트워크로 전송됩니다.</p>
          <p><b className="text-ink">제3자 제공</b> — 위 처리 위탁 외에 개인정보를 제3자에게 제공하지 않습니다.</p>
          <p><b className="text-ink">보관·파기</b> — 학습 기록과 가입 동의 기록은 계정 유지 동안 보관하며, 회원 탈퇴 시 지체 없이 파기합니다. 당사자 파일럿 연구에 참여한 경우 그 자료는 별도 연구 동의서에 적힌 기간 동안 보관한 뒤 파기합니다.</p>
          <p><b className="text-ink">이용자의 권리</b> — 프로필 → 계정 설정에서 정정·삭제를, 접근성 설정의 '내 데이터'에서 열람(내려받기)을 할 수 있습니다. 계정 삭제와 이메일 변경은 현재 비밀번호를 다시 확인합니다.</p>
          <p><b className="text-ink">개인정보 보호책임자</b> — {PRIVACY_OFFICER.name} · {PRIVACY_OFFICER.contact || '연락처는 공개 전 기재'}</p>
        </Section>

        <Section id="minors" title="미성년자 보호">
          <p>만 14세 미만 아동은 개인정보 수집·이용에 <b className="text-ink">법정대리인(보호자)의 동의</b>가 필요합니다. 회원가입 때 '만 14세 이상이거나 보호자 동의를 받았다'는 확인을 받고, 확인하지 않으면 가입할 수 없습니다. 확인 사실과 시각은 가입 동의 기록으로 서버에 남습니다.</p>
          <p>미성년 이용자의 정보는 학습 목적에 한해 최소한으로 수집하며, 보호자는 자녀의 정보에 대한 열람·정정·삭제를 요청할 수 있습니다.</p>
        </Section>
      </div>
    </div>
  )
}
