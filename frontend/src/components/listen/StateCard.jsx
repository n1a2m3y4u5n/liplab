import { Card } from './ui'

/** 상태 안내 카드(준비 전·오류·잠김·빈 목록). 다음 행동은 actions(첫 번째가 주 버튼). */
export default function StateCard({ title, body, actions = [] }) {
  return (
    <Card className="flex flex-col items-center gap-3 py-8 text-center">
      <p role="status" className="text-[17px] font-bold leading-snug text-ink">{title}</p>
      {body && <p className="max-w-[420px] break-keep text-[14px] leading-[1.6] text-ink-muted">{body}</p>}
      {actions.length > 0 && (
        <div className="mt-2 flex w-full max-w-[360px] flex-col gap-2">
          {actions.map((a, i) => (
            <button key={a.label} type="button" onClick={a.onClick} className={`${i === 0 ? 'btn-primary' : 'btn-secondary'} py-3 text-[15px]`}>{a.label}</button>
          ))}
        </div>
      )}
    </Card>
  )
}

// 못 받은 이유마다 문구(useClip의 reason). 모르면 예전 문구
const MISSING_BODY = {
  not_prepared: '이 소리는 아직 만들지 않았어요. 이 문제는 세지 않고 넘어가요.',
  network: '인터넷 연결이 끊겨 소리를 받지 못했어요. 연결을 확인하고 다시 받아 보세요.',
  decode: '이 브라우저에서 소리 파일을 열지 못했어요. 다른 브라우저로 열거나 이 문제는 세지 않고 넘어가요.',
}

/** 문항 소리를 받지 못했을 때: 다시 받기 / 이 문항 넘기기(세지 않음). */
export const missingCard = (clip, onSkip) => (
  <StateCard title="이 소리를 아직 들을 수 없어요"
    body={MISSING_BODY[clip.reason] || '소리가 아직 준비되지 않았거나 인터넷 연결이 끊겼어요. 다시 받아 보거나, 이 문제는 세지 않고 넘어가요.'}
    actions={[{ label: '다시 받기', onClick: clip.retry }, { label: '이 문제 넘기기', onClick: onSkip }]} />
)

/** 잡음 파일을 받지 못했을 때(소음이 있어야 하는 과제). exitLabel은 들어온 곳으로 돌아가는 버튼 이름. */
export const noiseMissingCard = (nz, onExit, exitLabel = '학습 화면으로') => (
  <StateCard title="잡음 소리를 받지 못했어요" body="이 연습은 잡음이 있어야 할 수 있어요. 인터넷 연결을 확인하고 다시 받아 주세요."
    actions={[{ label: '다시 받기', onClick: nz.retry }, { label: exitLabel, onClick: onExit }]} />
)
