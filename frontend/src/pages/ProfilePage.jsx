import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import Modal from '../components/Modal'
import GuideModal from '../components/GuideModal'
import useStore from '../store/useStore'
import { accountAPI, learningAPI, reviewAPI } from '../api'
import { levelProgress } from '../lib/level'
import { mergeBadges, clearSignExplored } from '../lib/badges'

/**
 * 프로필 탭 (Figma 107:16 · 모바일 241:34) — 내 프로필(그라데이션 3D 카드) + 통계 3열 + 설정 리스트.
 * 계정 설정(220:27)·학습 초기화(222:28)는 모달로 연다. 로그아웃은 계정 설정 모달 안에 있다.
 * 레벨 진행은 오른쪽 패널 '레벨 진행'(137:163)과 같은 계산(lib/level.js — 백엔드 레벨 공식)이다.
 * 크기는 lg 미만이 모바일 프레임 값, lg 이상이 데스크톱 프레임 값이다.
 */
function StatCol({ icon, label, value, color }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1 font-bold leading-figma lg:gap-[7px] lg:py-1.5">
      <div className="flex items-center gap-1.5">
        {/* 라벨 아이콘은 데스크톱(135:46)에만 — 모바일(241:135)은 글자만 */}
        <img src={icon} alt="" className="hidden size-[18px] lg:block" />
        <span className="text-[11.5px] text-ink-faint lg:text-[13px] lg:text-ink-soft">{label}</span>
      </div>
      <span className={`text-[19px] tracking-[-0.38px] lg:text-[27px] lg:tracking-[-0.675px] ${color}`}>{value}</span>
    </div>
  )
}

/** 오른쪽 화살표 — 모바일 6×12 칸(241:150) · 데스크톱 7×14 칸(107:180 = menu-arrow). */
function Chevron() {
  return (
    <span aria-hidden className="relative h-3 w-1.5 shrink-0 lg:h-3.5 lg:w-[7px]">
      <img src="/ui/lp-240-34-arrow.svg" alt="" className="absolute left-1/2 top-1/2 max-w-none -translate-x-1/2 -translate-y-1/2 lg:hidden" />
      <img src="/ui/menu-arrow.svg" alt="" className="absolute left-1/2 top-1/2 hidden max-w-none -translate-x-1/2 -translate-y-1/2 lg:block" />
    </span>
  )
}

function MenuRow({ title, sub, onClick, first, danger }) {
  return (
    <button type="button" onClick={onClick}
      className={`flex w-full items-center justify-between py-[15px] pl-[18px] pr-4 text-left leading-figma hover:bg-surface-muted lg:px-[22px] lg:py-[18px] ${first ? '' : 'border-t-1.5 border-line'}`}>
      <span className="flex flex-col gap-[3px]">
        <span className={`text-[15px] font-bold lg:text-[16px] ${danger ? 'text-bad-text' : 'text-ink'}`}>{title}</span>
        <span className="text-[12px] text-ink-muted lg:text-[13px]">{sub}</span>
      </span>
      <Chevron />
    </button>
  )
}

/** 분 → '18시간'(Figma 222:210) — 1시간 미만은 분. */
function fmtHours(m) {
  const v = Math.max(0, Math.round(m || 0))
  return v < 60 ? `${v}분` : `${Math.round(v / 60)}시간`
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
  const [form, setForm] = useState({ username: '', email: '', current: '', next: '', emailPw: '', delPw: '' })
  const [edit, setEdit] = useState(null)        // 'username' | 'email' | null
  const [pwOpen, setPwOpen] = useState(false)
  const [delOpen, setDelOpen] = useState(false) // 계정 삭제 재인증 칸
  const [msg, setMsg] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [lost, setLost] = useState(null)        // 학습 초기화 '사라지는 기록' 실제 수치
  const [resetErr, setResetErr] = useState('')
  const [pilot, setPilot] = useState(null)      // 파일럿 진행 여부·내 참여 상태(§4.7) — 진행 중일 때만 줄을 보인다
  const [pilotCode, setPilotCode] = useState('')
  const [pilotMsg, setPilotMsg] = useState('')
  useEffect(() => { accountAPI.pilotStatus().then(setPilot).catch(() => setPilot(null)) }, [])
  const joinPilot = async () => {
    if (!pilotCode.trim()) return
    setBusy(true); setPilotMsg('')
    try {
      const r = await accountAPI.pilotJoin(pilotCode.trim())
      setPilot((p) => ({ ...(p || {}), joined: true, cohort: r.cohort }))
      setPilotMsg('파일럿에 참여했어요. 학습 기록은 이름 없이 가명으로만 연구에 쓰여요.')
    } catch (e) { setPilotMsg(e?.response?.data?.detail || '참여하지 못했어요.') } finally { setBusy(false) }
  }

  const openAccount = () => {
    setForm({ username: user?.username || '', email: user?.email || '', current: '', next: '', emailPw: '', delPw: '' })
    setEdit(null); setPwOpen(false); setDelOpen(false); setMsg(''); setModal('account')
  }
  // 학습 초기화 — 목록 수치는 이 계정의 실제 기록(분석 요약·복습·북마크)을 연 때마다 읽는다. 실패한 칸은 '–'.
  const openReset = () => {
    setConfirmText(''); setResetErr(''); setLost(null); setModal('reset')
    Promise.all([
      learningAPI.getAnalysisOverview().catch(() => null),
      reviewAPI.getDue().catch(() => null),
      learningAPI.getReviewSentences().catch(() => null),
      learningAPI.getBookmarks().catch(() => null),
    ]).then(([ov, dueRes, wrongRes, bmRes]) => {
      const len = (r) => (r == null ? null : (Array.isArray(r) ? r : r.items || []).length)
      const due = len(dueRes)
      const wrongN = len(wrongRes)
      setLost({
        ov,
        wrong: due == null && wrongN == null ? null : (due || 0) + (wrongN || 0),
        marks: len(bmRes),
      })
    })
  }

  const saveField = async (field) => {
    setBusy(true); setMsg('')
    try {
      // 이메일을 바꿀 때만 현재 비밀번호를 함께 보낸다(서버 재인증, §4.9).
      const payload = { username: form.username, email: form.email }
      if (field === 'email') payload.current_password = form.emailPw
      const u = await accountAPI.updateProfile(payload)
      if (u && updateUser) updateUser(u)
      setEdit(null); setForm((f) => ({ ...f, emailPw: '' }))
      setMsg(field === 'email' ? '이메일을 저장했어요.' : '이름을 저장했어요.')
    } catch (e) { setMsg(e?.response?.data?.detail || '저장하지 못했어요.') } finally { setBusy(false) }
  }
  const savePassword = async () => {
    if (!form.current || !form.next) { setMsg('현재·새 비밀번호를 입력해 주세요.'); return }
    setBusy(true); setMsg('')
    try {
      const r = await accountAPI.changePassword({ current_password: form.current, new_password: form.next })
      // 비밀번호를 바꾸면 기존 토큰이 모두 무효가 되므로, 응답의 새 토큰으로 이 기기 세션을 이어 간다.
      if (r?.access_token) useStore.getState().setAuth(user, r.access_token)
      setMsg('비밀번호를 변경했어요. 다른 기기에서는 다시 로그인해야 해요.')
      setForm((f) => ({ ...f, current: '', next: '' })); setPwOpen(false)
    } catch (e) { setMsg(e?.response?.data?.detail || '변경하지 못했어요(현재 비밀번호 확인).') } finally { setBusy(false) }
  }
  // 초기화 실패를 삼키지 않는다 — 실패하면 모달을 연 채 안내하고, 성공했을 때만 학습 경로로 간다.
  const resetLearning = async () => {
    if (confirmText.trim() !== '초기화') return
    setBusy(true); setResetErr('')
    try {
      // 목록에 적힌 범위(학습 기록·단계 진도·복습 목록·배지·XP)를 서버가 한 번에 지운다.
      await accountAPI.resetLearning()
      clearSignExplored()
      setModal(null)
      window.location.assign('/learn/path')   // 헤더의 XP·연속 학습까지 새로 읽도록 다시 불러온다
    } catch (e) {
      setResetErr(e?.response?.data?.detail || '초기화하지 못했어요. 잠시 후 다시 시도해 주세요.')
    } finally { setBusy(false) }
  }
  // 계정 삭제(삭제권) — 현재 비밀번호로 재인증한 뒤 서버에서 계정·데이터를 일괄 삭제하고 로그아웃한다.
  const delAccount = async () => {
    if (!form.delPw) { setMsg('계정을 삭제하려면 현재 비밀번호를 입력해 주세요.'); return }
    setBusy(true); setMsg('')
    try {
      await accountAPI.deleteAccount(form.delPw)
      logout(); navigate('/learn/path')
    } catch (e) { setMsg(e?.response?.data?.detail || '삭제하지 못했어요.') } finally { setBusy(false) }
  }

  const level = Math.max(1, statistics?.current_level || user?.current_level || 1)
  const xp = Math.max(0, statistics?.total_xp ?? user?.total_xp ?? 0)
  const lp = levelProgress(level, xp)
  const name = user?.username || '게스트'
  const email = user?.email || ''
  const days = Math.max(0, user?.streak_count || statistics?.days_learned || 0)
  const lessons = statistics?.lessons_completed ?? statistics?.completed_lessons ?? '—'

  // 사라지는 기록(222:207) — 불러오기 전 '…', 못 읽은 값은 '–'
  const n = (v) => (typeof v === 'number' ? v.toLocaleString() : lost ? '–' : '…')
  const ov = lost?.ov
  const badgeCount = ov ? mergeBadges(ov.badges).filter((b) => b.earned).length : null
  const lostRows = [
    ['학습 기록', `${n(ov?.sessions)}회 · ${ov ? fmtHours(ov.total_minutes) : n(null)}`],
    ['단계 진도', `독화 ${n(ov?.tracks?.read?.done)}단계 · 발화 ${n(ov?.tracks?.speak?.done)}단계`],
    ['복습 목록', `오답 ${n(lost?.wrong)}개 · 북마크 ${n(lost?.marks)}개`],
    ['배지 · XP', `배지 ${n(badgeCount)}개 · ${xp.toLocaleString()} XP`],
  ]

  return (
    <AppShell active="profile" title="프로필">
      {/* 내 프로필 — 그라데이션 3D 카드(107:145 / 241:121) */}
      <section className="flex h-[150px] w-full items-start gap-3.5 overflow-hidden rounded-18 border-2 border-b-5 border-primary-600 bg-[linear-gradient(156.15deg,#a78bfa_0%,#7d53de_70.92%)] pl-[18px] pr-4 pt-[22px] lg:h-[176px] lg:items-center lg:gap-6 lg:rounded-22 lg:bg-[linear-gradient(166.28deg,#a78bfa_0%,#7d53de_70.92%)] lg:px-[30px] lg:pt-[3px]">
        <div className="flex size-16 shrink-0 items-center justify-center rounded-full border-[3px] border-white/90 bg-white/20 text-2xl font-black text-white lg:size-[100px] lg:border-4 lg:text-4xl lg:shadow-[0px_4px_12px_0px_rgba(38,13,89,0.25)]">
          {name[0]}
        </div>
        <div className="mt-[19px] flex min-w-0 flex-1 flex-col gap-2 font-bold leading-figma text-white lg:mt-0 lg:max-w-[500px] lg:gap-2.5">
          <div className="flex items-center gap-2 lg:gap-2.5">
            <span className="truncate text-[20px] tracking-[-0.4px] lg:text-[26px] lg:tracking-[-0.52px]">{name}</span>
            <span className="shrink-0 rounded-full bg-white/[0.24] px-2.5 py-1 text-[11.5px] lg:px-3 lg:py-[5px] lg:text-[13px]">Lv.{lp.level}</span>
          </div>
          <div className="flex justify-between text-[11.5px] lg:text-[13px]">
            <span className="opacity-85">다음 레벨까지</span>
            {/* 이 레벨 구간에서 쌓은 XP / 구간 크기 — 막대와 같은 비율, 남은 양은 오른쪽 패널 '레벨 진행'과 같다 */}
            <span>{lp.inLevel.toLocaleString()} / {lp.span.toLocaleString()} XP</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-white/[0.28] lg:h-3">
            <div className="h-full rounded-full bg-white" style={{ width: `${lp.pct}%` }} />
          </div>
        </div>
      </section>

      {/* 통계(107:165 / 241:133) — 모바일은 흰 카드, 데스크톱은 카드 없이 */}
      <section className="flex w-full items-center rounded-16 border-2 border-line bg-white py-4 lg:rounded-none lg:border-0 lg:bg-transparent lg:py-2">
        <StatCol icon="/ui/stat-calendar.svg" label="학습한 날" value={`${days}일`} color="text-stat-xp" />
        <span className="h-[34px] w-[1.5px] shrink-0 bg-line lg:h-[46px]" />
        <StatCol icon="/ui/stat-check.svg" label="완료한 레슨" value={typeof lessons === 'number' ? `${lessons}개` : lessons} color="text-stat-accuracy" />
        <span className="h-[34px] w-[1.5px] shrink-0 bg-line lg:h-[46px]" />
        <StatCol icon="/ui/stat-starplus.svg" label="누적 XP" value={xp.toLocaleString()} color="text-stat-streak" />
      </section>

      {/* 설정(107:175 / 241:145) */}
      <section className="w-full overflow-hidden rounded-16 border-2 border-line bg-white lg:rounded-18">
        <MenuRow first title="사용법 가이드" sub="처음이라면 여기부터" onClick={() => setGuideOpen(true)} />
        <MenuRow title="자가진단 다시 하기" sub="지금 수준으로 단계 재추천" onClick={() => navigate('/learn/placement')} />
        <MenuRow title="계정 설정" sub="이름 · 이메일 · 비밀번호 · 로그아웃" onClick={openAccount} />
        {pilot?.enabled && (
          <MenuRow title="파일럿 참여" sub={pilot.joined ? '참여 중이에요' : '받은 참여 코드를 입력해요'} onClick={() => { setPilotMsg(''); setModal('pilot') }} />
        )}
        <MenuRow danger title="학습 초기화" sub="기록을 모두 지우고 처음부터" onClick={openReset} />
      </section>

      {/* 파일럿 참여(§4.7) — 운영자가 나눠 준 코드로 집단을 정한다. 내보내기는 가명으로만 한다. */}
      <Modal open={modal === 'pilot'} onClose={() => setModal(null)} title="파일럿 참여" gap="gap-[14px]" maxW="max-w-[480px]">
        {pilot?.joined ? (
          <p className="text-[14px] leading-[1.6] text-ink">파일럿에 참여 중이에요. 학습 기록은 이름·이메일 없이 가명으로만 연구에 쓰여요.</p>
        ) : (
          <>
            <p className="text-[14px] leading-[1.6] text-ink-muted">안내받은 참여 코드를 입력해 주세요. 학습 기록은 이름·이메일 없이 가명으로만 연구에 쓰여요.</p>
            <input value={pilotCode} onChange={(e) => setPilotCode(e.target.value)} maxLength={32} placeholder="참여 코드"
              className="w-full rounded-13 border-2 border-line px-4 py-3 text-[15px] outline-none focus:border-primary-400" />
            <button type="button" disabled={busy || !pilotCode.trim()} onClick={joinPilot} className="btn-primary w-full py-3 text-[15px]">참여하기</button>
          </>
        )}
        {pilotMsg && <p role="status" className="text-center text-[13px] font-bold text-ink-muted">{pilotMsg}</p>}
      </Modal>

      {/* 계정 설정 모달(220:164) */}
      <Modal open={modal === 'account'} onClose={() => setModal(null)} title="계정 설정" subtitle="내 정보를 관리해요" gap="gap-[18px]" maxW="max-w-[620px]">
        {/* Identity(220:197) */}
        <div className="flex items-center gap-4 rounded-14 border-1.5 border-line bg-surface-muted p-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-full border-4 border-white/90 bg-primary-100 text-xl font-black text-primary-700 shadow-[0px_4px_12px_0px_rgba(38,13,89,0.25)]">{name[0]}</div>
          <div className="flex min-w-0 flex-1 flex-col gap-1 leading-figma">
            <p className="truncate text-[18px] font-bold text-ink">{name}</p>
            <p className="truncate text-[13px] text-ink-muted">{email || '이메일 미설정'}</p>
          </div>
          <button type="button" onClick={() => setMsg('사진 변경은 준비 중이에요.')}
            className="shrink-0 rounded-[11px] border-2 border-line bg-white px-4 py-2.5 text-[13.5px] font-bold leading-figma text-ink-muted">
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
          onCancel={() => { setForm((f) => ({ ...f, email, emailPw: '' })); setEdit(null) }}
        />
        {edit === 'email' && form.email.trim().toLowerCase() !== email.toLowerCase() && (
          <input type="password" className="input-field -mt-1" value={form.emailPw} autoComplete="current-password"
            onChange={(e) => setForm({ ...form, emailPw: e.target.value })} placeholder="이메일 변경 확인용 현재 비밀번호" />
        )}
        {/* 비밀번호 */}
        <div className="flex w-full flex-col gap-[7px]">
          <p className="text-[13px] font-bold leading-figma text-ink-muted">비밀번호</p>
          {!pwOpen ? (
            <div className="flex items-center justify-between rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px] leading-figma">
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
        {/* Danger zone(220:220) — 로그아웃 · 계정 삭제 */}
        <div className="flex w-full gap-2.5">
          <button type="button" onClick={() => { logout(); navigate('/learn/path') }}
            className="btn-secondary flex-1 py-[15px] text-[15px]">
            로그아웃
          </button>
          <button type="button" disabled={busy} onClick={() => { setDelOpen((v) => !v); setMsg('') }}
            className="btn-secondary flex-1 border-bad-line py-[15px] text-[15px] text-bad-text disabled:opacity-50">
            계정 삭제
          </button>
        </div>
        {delOpen && (
          <div className="flex w-full flex-col gap-2 rounded-[12px] border-2 border-bad-line bg-white p-3">
            <p className="text-[13px] text-bad-text">계정과 모든 학습 기록이 영구 삭제되고 되돌릴 수 없어요. 현재 비밀번호를 입력해 주세요.</p>
            <input type="password" className="input-field" value={form.delPw} autoComplete="current-password"
              onChange={(e) => setForm({ ...form, delPw: e.target.value })} placeholder="현재 비밀번호" />
            <div className="flex gap-2">
              <button type="button" onClick={() => { setDelOpen(false); setForm((f) => ({ ...f, delPw: '' })) }} className="btn-secondary flex-1 !py-2.5">취소</button>
              <button type="button" disabled={busy || !form.delPw} onClick={delAccount}
                className="btn-bad flex-1 !py-2.5 text-[15px] disabled:opacity-50">영구 삭제</button>
            </div>
          </div>
        )}
      </Modal>

      {/* 학습 초기화 모달(222:165) */}
      <Modal open={modal === 'reset'} onClose={() => setModal(null)} title="학습 초기화" tone="danger" gap="gap-[18px]" maxW="max-w-[600px]">
        <div className="flex w-full items-center gap-[11px] rounded-13 bg-bad-tint px-4 py-[15px]">
          <img src="/ui/stat2-warning.svg" alt="" className="size-5 shrink-0" />
          <p className="flex-1 text-[14px] font-bold leading-[1.6] text-bad-text">초기화하면 지금까지의 모든 학습 기록이 사라져요.</p>
        </div>
        <p className="text-[13px] font-bold leading-figma text-ink-muted">사라지는 기록</p>
        <div className="flex w-full flex-col leading-figma">
          {lostRows.map(([k, v], i) => (
            <div key={k} className={`flex items-center justify-between gap-3 py-3 ${i ? 'border-t-1.5 border-line' : ''}`}>
              <span className="shrink-0 text-[14.5px] font-bold text-ink">{k}</span>
              <span className="text-right text-[13px] text-ink-muted">{v}</span>
            </div>
          ))}
        </div>
        {pilot?.joined && (
          <p className="w-full text-[13px] leading-[1.6] text-ink-muted">
            파일럿에 참여 중이라 사전·사후 검사 기록은 남아요. 참여를 그만두거나 자료 삭제를 원하면 연구진에게 알려 주세요.
          </p>
        )}
        <div className="flex w-full flex-col gap-2">
          <p className="text-[13px] font-bold leading-figma text-ink-muted">계속하려면 «초기화»를 입력해주세요</p>
          <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="초기화"
            className="h-[50px] w-full rounded-[12px] border-2 border-bad-line bg-white px-[14px] text-[15px] text-ink placeholder:text-placeholder focus:outline-none" />
        </div>
        {resetErr && <p role="alert" className="text-center text-[13px] font-bold text-bad-text">{resetErr}</p>}
        <div className="flex w-full gap-2.5">
          <button type="button" onClick={() => setModal(null)} className="btn-secondary flex-1 py-[15px] text-[16px]">
            취소
          </button>
          <button type="button" disabled={busy || confirmText.trim() !== '초기화'} onClick={resetLearning}
            className="btn-bad flex-1 py-[15px] text-[16px] disabled:cursor-not-allowed disabled:border-inactive-line disabled:bg-inactive disabled:text-inactive-text">
            {busy ? '초기화 중…' : '초기화하기'}
          </button>
        </div>
      </Modal>

      {/* 사용법 가이드 모달 (Figma 338:57) — /guide 페이지 대신 모달로 연다 */}
      <GuideModal open={guideOpen} onClose={() => setGuideOpen(false)} />
    </AppShell>
  )
}

/** 계정 설정 필드 행 — 평소엔 값+수정 링크, 편집 중엔 입력+저장/취소(Figma 220:204 패턴). readOnly는 값만 표시. */
function FieldRow({ label, value, display, editing, type = 'text', placeholder, busy, readOnly, onEdit, onChange, onSave, onCancel }) {
  return (
    <div className="flex w-full flex-col gap-[7px]">
      <p className="text-[13px] font-bold leading-figma text-ink-muted">{label}</p>
      {readOnly ? (
        <div className="flex items-center rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px] leading-figma">
          <span className="truncate text-[15px] text-ink">{display}</span>
        </div>
      ) : !editing ? (
        <div className="flex items-center justify-between rounded-[12px] border-2 border-line bg-white py-[14px] pl-4 pr-[14px] leading-figma">
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
