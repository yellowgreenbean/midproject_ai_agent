// 비밀번호 변경 (docs/기획서.md Part 1 AUTH-F08 · UI06) — 지금 비밀번호 확인 → 새 비밀번호 두 번. 바꾸면 다른 기기의 로그인은 끊긴다
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { changePassword, getMe } from '../api'
import { passwordConfirmError, passwordError } from '../signupRules'
import './ProductPages.css'
import './SettingsPages.css'

export default function PasswordChangePage() {
  const [username, setUsername] = useState<string | null>(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [tried, setTried] = useState(false)
  const [serverError, setServerError] = useState<{ field: 'current' | 'next'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    void getMe().then((r) => (r.success ? setUsername(r.data.username) : (location.hash = '#/login')))
  }, [])

  const nextErr = tried || next ? passwordError(next, username ?? '') : null
  const confirmErr = tried || confirm ? passwordConfirmError(next, confirm) : null

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTried(true)
    setServerError(null)
    if (!current || passwordError(next, username ?? '') || passwordConfirmError(next, confirm)) return
    setBusy(true)
    const r = await changePassword(current, next, confirm)
    setBusy(false)
    if (r.success) return setDone(true)
    setServerError({ field: r.error.code === 'WRONG_PASSWORD' || r.error.code.endsWith('LOCKED') ? 'current' : 'next', text: r.error.message })
  }

  const currentMsg = serverError?.field === 'current' ? serverError.text : tried && !current ? '지금 비밀번호를 입력해 주세요.' : null
  const nextMsg = serverError?.field === 'next' ? serverError.text : nextErr

  return (
    <AppShell title="비밀번호 변경" current="#/settings" busy={!username}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      {done ? (
        <div className="panel empty">
          <span className="empty-icon">
            <Icon name="safe" size={26} />
          </span>
          <p className="empty-title">비밀번호를 바꿨어요</p>
          <p className="empty-sub">다른 기기에서 로그인돼 있던 곳은 모두 로그아웃했어요.</p>
          <a className="btn-pill" href="#/settings">
            마이페이지로
          </a>
        </div>
      ) : (
        <>
          <section className="prod-head">
            <h2 className="prod-title is-dup">비밀번호 변경</h2>
            <p className="prod-sub">영문과 숫자를 섞어 8자 이상으로 정해 주세요. 아이디가 들어가면 쓸 수 없어요.</p>
          </section>
          <form className="panel set-form prod-form" onSubmit={onSubmit} noValidate>
            <Field id="pw-current" label="지금 비밀번호" message={currentMsg ? { tone: 'error', text: currentMsg } : null}>
              <input
                id="pw-current"
                className="input"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                aria-invalid={!!currentMsg}
                aria-describedby="pw-current-msg"
              />
            </Field>
            <Field id="pw-next" label="새 비밀번호" message={nextMsg ? { tone: 'error', text: nextMsg } : next ? { tone: 'ok', text: '쓸 수 있는 비밀번호예요.' } : null}>
              <input
                id="pw-next"
                className="input"
                type="password"
                autoComplete="new-password"
                maxLength={64}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                aria-invalid={!!nextMsg}
                aria-describedby="pw-next-msg"
              />
            </Field>
            <Field id="pw-confirm" label="새 비밀번호 확인" message={confirmErr ? { tone: 'error', text: confirmErr } : null}>
              <input
                id="pw-confirm"
                className="input"
                type="password"
                autoComplete="new-password"
                maxLength={64}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                aria-invalid={!!confirmErr}
                aria-describedby="pw-confirm-msg"
              />
            </Field>
            <button className="btn-primary" type="submit" disabled={busy}>
              {busy ? '바꾸는 중…' : '비밀번호 바꾸기'}
            </button>
          </form>
        </>
      )}
    </AppShell>
  )
}
