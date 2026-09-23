import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import Modal from '../components/Modal'
import GuideModal from '../components/GuideModal'
import useStore from '../store/useStore'
import { accountAPI, learningAPI, curriculumAPI } from '../api'

/**
 * 프로필 탭 (Figma 리디자인) — 내 프로필(그라데이션 3D 카드) + 통계 3열 + 설정 리스트.
 * 계정 설정·학습 초기화는 모달로 연다. 로그아웃은 계정 설정 모달 안에 있다.
 */
function StatCol({ icon, label, value, color }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-[7px] py-1.5">
      <div className="flex items-center gap-1.5">
        <img src={icon} alt="" className="h-[18px] w-[18px]" />
        <span className="text-[13px] font-bold text-[#7a7a8c]">{label}</span>
      </div>
      <span className="text-[27px] font-bold tracking-[-0.675px]" style={{ color }}>{value}</span>
    </div>
  )
}

function MenuRow({ title, sub, onClick, first, danger }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center justify-between px-[22px] py-[18px] text-left hover:bg-gray-50 ${first ? '' : 'border-t-[1.5px] border-line'}`}>
      <span className="flex flex-col gap-[3px]">
        <span className={`text-[16px] font-bold ${danger ? 'text-[#b91c1c]' : 'text-ink'}`}>{title}</span>
        <span className="text-[13px] text-ink-muted">{sub}</span>
      </span>
      <img src="/ui/menu-arrow.svg" alt="" className="h-3.5 w-[7px]" />
    </button>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const user = useStore((s) => s.user)
  const statistics = useStore((s) => s.statistics)
  const logout = useStore((s) => s.logout)
  const updateUser = useStore((s) => s.updateUser)
  const [modal, setModal] = useState(null)     // 'account' | 'reset'
  const [guideOpen, setGuideOpen] = useState(false)  // 사용법 가이드 모달
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ username: '', email: '', current: '', next: '' })
  const [edit, setEdit] = useState(null)        // 'username' | 'email' | null
  const [pwOpen, setPwOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [confirmText, setConfirmText] = useState('')

  const openAccount = () => {
    setForm({ username: user?.username || '', email: user?.email || '', current: '', next: '' })
    setEdit(null); setPwOpen(false); setMsg(''); setModal('account')
  }
  const openReset = () => { setConfirmText(''); setModal('reset') }

  const saveField = async (field) => {
    setBusy(true); setMsg('')
    try {
      const u = await accountAPI.updateProfile({ username: form.username, email: form.email })
      if (u && updateUser) updateUser(u)
      setEdit(null); setMsg(field === 'email' ? '이메일을 저장했어요.' : '이름을 저장했어요.')
    } catch (e) { setMsg(e?.response?.data?.detail || '저장하지 못했어요.') } finally { setBusy(false) }
  }
  const savePassword = async () => {
    if (!form.current || !form.next) { setMsg('현재·새 비밀번호를 입력해 주세요.'); return }
    setBusy(true); setMsg('')
    try {
      await accountAPI.changePassword({ current_password: form.current, new_password: form.next })
      setMsg('비밀번호를 변경했어요.'); setForm((f) => ({ ...f, current: '', next: '' })); setPwOpen(false)
    } catch (e) { setMsg(e?.response?.data?.detail || '변경하지 못했어요(현재 비밀번호 확인).') } finally { setBusy(false) }
  }
  const resetLearning = async () => {
    if (confirmText.trim() !== '초기화') return
    setBusy(true)
    try {
      await learningAPI.resetAnalysis().catch(() => {})
      await curriculumAPI.resetTrack().catch(() => {})
      setModal(null); navigate('/learn/path')
    } finally { setBusy(false) }
  }
  // 계정 삭제(삭제권) — 확인 후 서버에서 계정·데이터 일괄 삭제하고 로그아웃한다.
  const delAccount = async () => {
    if (!window.confirm('계정과 모든 학습 기록이 영구 삭제됩니다. 계속할까요?')) return
    setBusy(true); setMsg('')
    try {
      await accountAPI.deleteAccount()
      logout(); navigate('/learn/path')
    } catch (e) { setMsg(e?.response?.data?.detail || '삭제하지 못했어요.') } finally { setBusy(false) }
  }

  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const PER = 500
  const inLevel = xp % PER
  const name = user?.username || '게스트'
  const email = user?.email || ''
  const days = Math.max(0, user?.streak_count || statistics?.days_learned || 0)
  const lessons = statistics?.lessons_completed ?? statistics?.completed_lessons ?? '—'

  return (
    <AppShell active="profile" title="프로필">
      {/* 내 프로필 — 그라데이션 3D 카드 */}
      <section className="relative w-full overflow-hidden rounded-[22px] border-2 border-b-[5px] border-[#6d3fc4] p-6 sm:p-8"
        style={{ backgroundImage: 'linear-gradient(166.28deg, #a78bfa 0%, #7d53de 70.92%)' }}>
        <div className="flex items-center gap-6">
          <div className="flex h-[100px] w-[100px] shrink-0 items-center justify-center rounded-full border-4 border-white/90 bg-white/20 text-4xl font-black text-white shadow-[0px_4px_12px_0px_rgba(38,13,89,0.25)]">
            {name[0]}
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            <div className="flex items-center gap-2.5">
              <span className="truncate text-[26px] font-bold tracking-[-0.52px] text-white">{name}</span>
              <span className="shrink-0 rounded-full bg-white/25 px-3 py-[5px] text-[13px] font-bold text-white">Lv.{level}</span>
            </div>
            <div className="flex justify-between text-[13px] font-bold text-white">
              <span className="opacity-85">다음 레벨까지</span>
              <span>{inLevel.toLocaleString()} / {PER} XP</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-white/30">
              <div className="h-full rounded-full bg-white" style={{ width: `${(inLevel / PER) * 100}%` }} />
            </div>
          </div>
        </div>
      </section>

      {/* 통계 */}
      <section className="flex w-full items-center py-2">
        <StatCol icon="/ui/stat-calendar.svg" label="학습한 날" value={`${days}일`} color="#5f3ab8" />
        <span className="h-[46px] w-[1.5px] bg-line" />
        <StatCol icon="/ui/stat-check.svg" label="완료한 레슨" value={typeof lessons === 'number' ? `${lessons}개` : lessons} color="#047857" />
        <span className="h-[46px] w-[1.5px] bg-line" />
        <StatCol icon="/ui/stat-starplus.svg" label="누적 XP" value={xp.toLocaleString()} color="#b45309" />
      </section>

      {/* 설정 */}
      <section className="card-flat w-full !p-0">
        <MenuRow first title="사용법 가이드" sub="처음이라면 여기부터" onClick={() => setGuideOpen(true)} />
        <MenuRow title="자가진단 다시 하기" sub="지금 수준으로 단계 재추천" onClick={() => navigate('/learn/placement')} />
        <MenuRow title="계정 설정" sub="이름 · 이메일 · 비밀번호 · 로그아웃" onClick={openAccount} />
        <MenuRow danger title="학습 초기화" sub="기록을 모두 지우고 처음부터" onClick={openReset} />
      </section>

      {/* 계정 설정 모달 */}
      <Modal open={modal === 'account'} onClose={() => setModal(null)} title="계정 설정" subtitle="내 정보를 관리해요" gap="gap-[18px]" maxW="max-w-[620px]">
        {/* Identity */}
        <div className="flex items-center gap-4 rounded-[14px] border-[1.5px] border-line bg-[#fafafc] p-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-4 border-white/90 bg-primary-100 text-xl font-black text-primary-700 shadow-[0px_4px_12px_0px_rgba(38,13,89,0.25)]">{name[0]}</div>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="truncate text-[18px] font-bold text-ink">{name}</p>
            <p className="truncate text-[13px] text-ink-muted">{email || '이메일 미설정'}</p>
          </div>
          <button type="button" onClick={() => setMsg('사진 변경은 준비 중이에요.')}
            className="shrink-0 rounded-[11px] border-2 border-line bg-white px-4 py-2.5 text-[13.5px] font-bold text-ink-muted">
            사진 변경
          </button>
        </div>

        {/* 이름 */}
        <FieldRow label="이름" editing={edit === 'username'}
          onEdit={() => { setEdit('username'); setMsg('') }}
          value={form.username}
          display={name}
          busy={busy}
          onChange={(v) => setForm({ ...form, username: v })}
          onSave={() => saveField('username')}
          onCancel={() => { setForm((f) => ({ ...f, username: name })); setEdit(null) }}
        />
        {/* 이메일 — 정정권(§4.9)상 수정 가능 */}
        <FieldRow label="이메일" editing={edit === 'email'} type="email"
          onEdit={() => { setEdit('email'); setMsg('') }}
          value={form.email}
          display={email || '미설정'}
          busy={busy}
          onChange={(v) => setForm({ ...form, email: v })}
          onSave={() => saveField('email')}
          onCancel={() => { setForm((f) => ({ ...f, email })); setEdit(null) }}
        />
        {/* 비밀번호 */}
        <div className="flex w-full flex-col gap-[7px]">
          <p className="text-[13px] font-bold text-ink-muted">비밀번호</p>
          {!pwOpen ? (
            <div className="flex items-center justify-between rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px]">
              <span className="text-[15px] text-ink">••••••••</span>
              <button type="button" onClick={() => { setPwOpen(true); setMsg('') }} className="text-[13px] font-bold text-primary-500">변경</button>
            </div>
          ) : (
            <div className="flex flex-col gap-2 rounded-[12px] border-2 border-line bg-white p-3">
              <input type="password" className="input-field" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} placeholder="현재 비밀번호" />
              <input type="password" className="input-field" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} placeholder="새 비밀번호" />
              <div className="flex gap-2">
                <button type="button" onClick={() => { setPwOpen(false); setForm((f) => ({ ...f, current: '', next: '' })) }} className="btn-secondary flex-1 !py-2.5">취소</button>
                <button type="button" disabled={busy} onClick={savePassword} className="btn-primary flex-1 !py-2.5">변경</button>
              </div>
            </div>
          )}
        </div>

        {msg && <p className="text-center text-[13px] font-bold text-primary-600">{msg}</p>}

        <div className="h-[1.5px] w-full bg-line" />
        <div className="flex w-full gap-[10px]">
          <button type="button" onClick={() => { logout(); navigate('/learn/path') }}
            className="flex-1 rounded-[14px] border-2 border-b-[5px] border-line bg-white py-[15px] text-[15px] font-bold text-ink-muted transition-all active:translate-y-[1px] active:border-b-2">
            로그아웃
          </button>
          <button type="button" disabled={busy} onClick={delAccount}
            className="flex-1 rounded-[14px] border-2 border-b-[5px] border-[#f3c8c8] bg-white py-[15px] text-[15px] font-bold text-[#b91c1c] transition-all active:translate-y-[1px] active:border-b-2 disabled:opacity-50">
            계정 삭제
          </button>
        </div>
      </Modal>

      {/* 학습 초기화 모달 */}
      <Modal open={modal === 'reset'} onClose={() => setModal(null)} title="학습 초기화" tone="danger" gap="gap-[18px]" maxW="max-w-xl">
        <div className="flex w-full items-center gap-[11px] rounded-[13px] bg-[#feecec] px-4 py-[15px]">
          <img src="/ui/stat2-warning.svg" alt="" className="h-5 w-5 shrink-0" />
          <p className="flex-1 text-[14px] font-bold leading-[1.6] text-[#b91c1c]">초기화하면 지금까지의 모든 학습 기록이 사라져요.</p>
        </div>
        <p className="text-[13px] font-bold text-ink-muted">사라지는 기록</p>
        <div className="flex w-full flex-col">
          {[
            ['학습 기록', '142회 · 18시간'],
            ['단계 진도', '독화 4단계 · 발화 2단계'],
            ['복습 목록', '오답 8개 · 북마크 23개'],
            ['배지 · XP', `배지 7개 · ${xp.toLocaleString()} XP`],
          ].map(([k, v], i) => (
            <div key={k} className={`flex items-center justify-between py-3 ${i ? 'border-t-[1.5px] border-line' : ''}`}>
              <span className="text-[14.5px] font-bold text-ink">{k}</span>
              <span className="text-[13px] text-ink-muted">{v}</span>
            </div>
          ))}
        </div>
        <div className="flex w-full flex-col gap-2">
          <p className="text-[13px] font-bold text-ink-muted">계속하려면 «초기화»를 입력해주세요</p>
          <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="초기화"
            className="h-[50px] w-full rounded-[12px] border-2 border-[#f3c8c8] bg-white px-[14px] text-[15px] text-ink placeholder:text-[#c9c9d6] focus:outline-none" />
        </div>
        <div className="flex w-full gap-[10px]">
          <button type="button" onClick={() => setModal(null)}
            className="flex-1 rounded-[14px] border-2 border-b-[5px] border-line bg-white py-[15px] text-[16px] font-bold text-ink-muted transition-all active:translate-y-[1px] active:border-b-2">
            취소
          </button>
          <button type="button" disabled={busy || confirmText.trim() !== '초기화'} onClick={resetLearning}
            className="flex-1 rounded-[14px] border-2 border-b-[5px] py-[15px] text-[16px] font-bold transition-all active:translate-y-[1px] active:border-b-2 disabled:cursor-not-allowed enabled:border-rose-700 enabled:bg-rose-500 enabled:text-white disabled:border-[#d2d2de] disabled:bg-[#e4e4ec] disabled:text-[#a0a0b0]">
            {busy ? '초기화 중…' : '초기화하기'}
          </button>
        </div>
      </Modal>

      {/* 사용법 가이드 모달 (Figma 338:57) — /guide 페이지 대신 모달로 연다 */}
      <GuideModal open={guideOpen} onClose={() => setGuideOpen(false)} />
    </AppShell>
  )
}

/** 계정 설정 필드 행 — 평소엔 값+수정 링크, 편집 중엔 입력+저장/취소(Figma 패턴). readOnly는 값만 표시. */
function FieldRow({ label, value, display, editing, type = 'text', placeholder, busy, readOnly, onEdit, onChange, onSave, onCancel }) {
  return (
    <div className="flex w-full flex-col gap-[7px]">
      <p className="text-[13px] font-bold text-ink-muted">{label}</p>
      {readOnly ? (
        <div className="flex items-center rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px]">
          <span className="truncate text-[15px] text-ink">{display}</span>
        </div>
      ) : !editing ? (
        <div className="flex items-center justify-between rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px]">
          <span className="truncate text-[15px] text-ink">{display}</span>
          <button type="button" onClick={onEdit} className="shrink-0 text-[13px] font-bold text-primary-500">수정</button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <input type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className="input-field flex-1" />
          <button type="button" onClick={onCancel} className="btn-secondary shrink-0 !px-3 !py-2.5">취소</button>
          <button type="button" disabled={busy} onClick={onSave} className="btn-primary shrink-0 !px-3 !py-2.5">저장</button>
        </div>
      )}
    </div>
  )
}
