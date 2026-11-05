// 비밀번호 재설정 (docs/기획서.md Part 1 AUTH-F06) — 아이디 + 가입한 이메일 인증번호 → 새 비밀번호 두 번.
// 바꾸면 모든 기기에서 로그아웃되고, 비밀번호를 여러 번 틀려 잠긴 것도 풀린다.
import { useState, type FormEvent } from 'react'
import Field from '../components/Field'
import EmailVerify from './EmailVerify'
import { resetPassword } from '../api'
import { passwordConfirmError, passwordError } from '../signupRules'
import logoMark from '../assets/logo-mark.png'
import './SignupPage.css'
import './LoginPage.css'

export default function ResetPasswordPage() {
  const [username, setUsername] = useState('')
  const [mail, setMail] = useState<{ email: string; token: string } | null>(null)
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [tried, setTried] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const nextErr = tried || next ? passwordError(next, username.trim().toLowerCase()) : null
  const confirmErr = tried || confirm ? passwordConfirmError(next, confirm) : null

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTried(true)
    if (!mail || !username.trim() || passwordError(next, username.trim().toLowerCase()) || passwordConfirmError(next, confirm)) return
    setBusy(true)
    const r = await resetPassword({ username: username.trim(), email: mail.email, emailVerificationToken: mail.token, newPassword: next, newPasswordConfirm: confirm })
    setBusy(false)
    if (!r.success) {
      if (r.error.code === 'EMAIL_NOT_VERIFIED') setMail(null) // 인증이 끝났으면(30분·한 번만) 번호부터 다시
      return setError(r.error.message)
    }
    setDone(true)
  }

  return (
    <main className="signup-done">
      <form className="done-card login-card" onSubmit={onSubmit} noValidate>
        <a className="mobile-brand login-brand" href="#/home">
          <img src={logoMark} alt="" width={28} height={28} />
          <span>Durin Bank</span>
        </a>
        <h1>비밀번호 재설정</h1>
        {done ? (
          <p role="status">비밀번호를 다시 정했어요. 다른 기기에서 로그인돼 있던 곳은 모두 로그아웃했어요. 새 비밀번호로 로그인해 주세요.</p>
        ) : (
          <>
            <p>아이디와 가입한 이메일을 확인한 뒤 새 비밀번호를 정해요.</p>
            <div className="login-fields">
              <Field id="rp-username" label="아이디">
                <input
                  id="rp-username"
                  className="input"
                  autoComplete="username"
                  autoCapitalize="none"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-describedby="rp-username-msg"
                />
              </Field>
              {mail ? (
                <p className="field-msg is-ok">{mail.email} 인증을 마쳤어요.</p>
              ) : (
                <EmailVerify purpose="PASSWORD_RESET" label="가입한 이메일" onVerified={(email, token) => setMail({ email, token })} />
              )}
              {mail && (
                <>
                  <Field id="rp-next" label="새 비밀번호" message={nextErr ? { tone: 'error', text: nextErr } : null}>
                    <input
                      id="rp-next"
                      className="input"
                      type="password"
                      autoComplete="new-password"
                      maxLength={64}
                      value={next}
                      onChange={(e) => setNext(e.target.value)}
                      aria-invalid={!!nextErr}
                      aria-describedby="rp-next-msg"
                    />
                  </Field>
                  <Field id="rp-confirm" label="새 비밀번호 확인" message={confirmErr ? { tone: 'error', text: confirmErr } : null}>
                    <input
                      id="rp-confirm"
                      className="input"
                      type="password"
                      autoComplete="new-password"
                      maxLength={64}
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      aria-invalid={!!confirmErr}
                      aria-describedby="rp-confirm-msg"
                    />
                  </Field>
                </>
              )}
              {error && (
                <p className="field-msg is-error" role="alert">
                  {error}
                </p>
              )}
            </div>
            {mail && (
              <button className="btn-primary" type="submit" disabled={busy}>
                {busy ? '바꾸는 중…' : '새 비밀번호로 정하기'}
              </button>
            )}
          </>
        )}
        <nav className="login-links" aria-label="계정 도움">
          <a href="#/find-id">아이디 찾기</a>
          <a href="#/login">로그인</a>
        </nav>
      </form>
    </main>
  )
}
