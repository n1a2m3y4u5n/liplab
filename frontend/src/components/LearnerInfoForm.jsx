import { useState } from 'react'
import { ONSET_OPTIONS, DEVICE_OPTIONS, SIGN_OPTIONS, normalizeAnswers, toggleDevice, learnerDefaults, describeDefaults } from '../lib/learnerProfile'

/**
 * 학습자 정보 선택 질문 세 개(계획 2-6). 온보딩과 프로필이 함께 쓴다. 모두 선택이고 답하지 않아도 된다.
 * 답은 이 기기에만 저장하고 서버로 보내지 않는다(저장은 부르는 쪽이 useLearnerInfo로).
 *   onSave(answers) · onSkip() · saveLabel · skipLabel
 */
function Chip({ on, onClick, children }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={`rounded-full border-2 px-4 py-2 text-[14px] font-bold leading-figma transition-colors ${
        on ? 'border-primary-500 bg-primary-100 text-primary-700' : 'border-line bg-white text-ink-muted hover:border-primary-300'}`}>
      {children}
    </button>
  )
}

function Question({ id, title, children }) {
  return (
    <fieldset className="flex flex-col gap-2" aria-labelledby={id}>
      <legend id={id} className="mb-2 text-[15px] font-bold leading-figma text-ink">{title}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  )
}

export default function LearnerInfoForm({ initial, onSave, onSkip, saveLabel = '저장하고 계속', skipLabel = '건너뛰기', busy = false }) {
  const [a, setA] = useState(() => normalizeAnswers(initial))
  const pick = (key, value) => setA((p) => ({ ...p, [key]: p[key] === value ? null : value }))
  const notes = describeDefaults(learnerDefaults(a))

  return (
    <div className="flex w-full flex-col gap-5">
      <Question id="li-onset" title="언제부터 잘 안 들렸나요?">
        {ONSET_OPTIONS.map((o) => <Chip key={o.value} on={a.onset === o.value} onClick={() => pick('onset', o.value)}>{o.label}</Chip>)}
      </Question>
      <Question id="li-device" title="쓰는 기기가 있나요? (여러 개 골라도 돼요)">
        {DEVICE_OPTIONS.map((o) => (
          <Chip key={o.value} on={a.devices.includes(o.value)} onClick={() => setA((p) => ({ ...p, devices: toggleDevice(p.devices, o.value) }))}>{o.label}</Chip>
        ))}
      </Question>
      <Question id="li-sign" title="수어를 쓰나요?">
        {SIGN_OPTIONS.map((o) => <Chip key={o.value} on={a.sign === o.value} onClick={() => pick('sign', o.value)}>{o.label}</Chip>)}
      </Question>

      {notes.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-14 bg-surface-muted px-4 py-3 text-[13px] leading-[1.6] text-ink-muted">
          {notes.map((n) => <li key={n}>· {n}</li>)}
        </ul>
      )}
      <p className="text-[12px] leading-[1.6] text-ink-faint">고른 내용은 이 휴대폰이나 컴퓨터에만 남고 인터넷으로 보내지 않아요. 프로필에서 언제든 바꾸거나 지울 수 있어요.</p>

      <div className="flex w-full flex-col gap-2.5">
        <button type="button" disabled={busy} onClick={() => onSave(normalizeAnswers(a))} className="btn-primary btn-lg w-full">{saveLabel}</button>
        {onSkip && <button type="button" disabled={busy} onClick={onSkip} className="btn-secondary btn-lg w-full text-track">{skipLabel}</button>}
      </div>
    </div>
  )
}
