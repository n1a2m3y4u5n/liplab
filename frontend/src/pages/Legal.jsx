import { useNavigate } from 'react-router-dom'

/**
 * 이용약관 · 개인정보 처리방침 · 미성년자 보호 안내 (§4.9 보안·개인정보 대응).
 * /terms · /privacy 두 라우트가 이 페이지를 공유하며, 회원가입 동의 문구에서 링크로 연결된다.
 */
function Section({ title, children }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[20px] font-bold tracking-[-0.4px] text-ink">{title}</h2>
      <div className="flex flex-col gap-2 text-[14.5px] leading-[1.75] text-ink-muted">{children}</div>
    </section>
  )
}

export default function Legal() {
  const navigate = useNavigate()
  return (
    <div className="min-h-[100dvh] bg-[#f3f3f3] px-4 py-10">
      <div className="mx-auto flex w-full max-w-[720px] flex-col gap-8 rounded-[24px] border-2 border-line bg-white p-8 sm:p-10">
        <div className="flex items-center justify-between">
          <span className="font-display text-[24px] leading-none tracking-[-1px] text-primary-500">LIPLAB</span>
          <button type="button" onClick={() => navigate(-1)} className="text-[14px] font-bold text-primary-500">닫기</button>
        </div>

        <Section title="이용약관">
          <p>LIPLAB(이하 서비스)은 청각장애 학습자를 위한 한국어 독화·발화 훈련 학습 도구입니다. 이용자는 학습 목적에 한하여 서비스를 이용하며, 타인의 계정을 도용하거나 서비스 운영을 방해하는 행위를 하지 않습니다.</p>
          <p>서비스는 연구·교육용 프로토타입으로 제공되며, 학습 콘텐츠와 채점 결과의 정확성을 보증하지 않습니다. 서비스는 사전 고지 후 기능을 변경하거나 종료할 수 있습니다.</p>
        </Section>

        <Section title="개인정보 처리방침">
          <p><b className="text-ink">수집 항목</b> — 이메일, 표시 이름, 비밀번호(단방향 암호화 저장), 학습 진행·채점 기록.</p>
          <p><b className="text-ink">이용 목적</b> — 계정 식별, 학습 진행 관리, 개인화 추천, 학습 효과 분석.</p>
          <p><b className="text-ink">웹캠·음성</b> — 입모양·발음 채점에 쓰이는 웹캠 영상과 얼굴 계수는 <b className="text-ink">기기 안에서만 처리</b>되며 서버로 전송·저장하지 않습니다. 음성은 채점 목적으로 서버에 일시 전송되어 처리 후 저장하지 않습니다.</p>
          <p><b className="text-ink">보관·파기</b> — 학습 기록은 계정 유지 동안 보관하며, 회원 탈퇴 시 계정과 관련 기록을 지체 없이 파기합니다. 이용자는 언제든 프로필 → 계정 설정에서 <b className="text-ink">열람(내려받기)·정정·삭제</b>를 요청할 수 있습니다.</p>
          <p><b className="text-ink">제3자 제공</b> — 개인정보를 제3자에게 제공하지 않습니다. 대화·시나리오 생성에 외부 LLM API를 사용할 때에도 학습 문장 외 개인 식별 정보를 전달하지 않습니다.</p>
        </Section>

        <Section title="미성년자 보호">
          <p>만 14세 미만 아동은 개인정보 수집·이용에 <b className="text-ink">법정대리인(보호자)의 동의</b>가 필요합니다. 회원가입 시 보호자 동의 여부를 확인하며, 동의가 없으면 가입이 제한됩니다.</p>
          <p>미성년 이용자의 정보는 학습 목적에 한해 최소한으로 수집하며, 보호자는 자녀의 정보에 대한 열람·정정·삭제를 요청할 수 있습니다.</p>
        </Section>
      </div>
    </div>
  )
}
