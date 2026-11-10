// 비밀번호 재설정 (docs/기획서.md Part 1 AUTH-F06 · UI04) — 2단계
//   ① 아이디 + 가입한 이메일 인증번호 → 서버가 같은 회원인지 확인하고 재설정 토큰(5분·한 번)을 준다
//   ② 새 비밀번호 두 번 → 바꾸면 모든 기기에서 로그아웃된다
// 본인 확인 비밀번호를 5번 틀려 잠긴 것은 풀리지 않는다(영업점 방문, 사용자 결정 2026-11-10).
import { useState, type FormEvent } from 'react'
import Field from '../components/Field'
import EmailVerify from './EmailVerify'
import { confirmPasswordReset, startPasswordReset } from '../api'
import { passwordConfirmError, passwordError } from '../signupRules'
import logoMark from '../assets/logo-mark.png'
import './SignupPage.css'
import './LoginPage.css'

export default function ResetPasswordPage() {
  const [username, setUsername] = useState('')
  const [mail, setMail] = useState<{ email: string; token: string } | null>(null)
  const [resetToken, setResetToken] = useState<string | null>(null)
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [tried, setTried] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const id = username.trim()
  const nextErr = tried || next ? passwordError(next, id.toLowerCase()) : null
  const confirmErr = tried || confirm ? passwordConfirmError(next, confirm) : null

  /** ① 아이디·이메일 확인 → 재설정 토큰 */
  async function onCheck(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!mail) return
    if (!id) return setError('아이디를 입력해 주세요.')
    setBusy(true)
    const r = await startPasswordReset(id, mail.email, mail.token)
    setBusy(false)
    if (!r.success) {
      if (r.error.code === 'EMAIL_NOT_VERIFIED') setMail(null) // 인증이 끝났으면(30분·한 번만) 번호부터 다시
      return setError(r.error.message) // IDENTITY_MISMATCH 면 메일 인증은 그대로 — 아이디만 고쳐 다시
    }
    setResetToken(r.data.resetToken)
  }

  /** ② 새 비밀번호 */
  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTried(true)
    setError(null)
    if (!resetToken || passwordError(next, id.toLowerCase()) || passwordConfirmError(next, confirm)) return
    setBusy(true)
    const r = await confirmPasswordReset(resetToken, next, confirm)
    setBusy(false)
    if (!r.success) {
      if (r.error.code === 'RESET_TOKEN_INVALID') {
        // 5분이 지났거나 이미 썼다 → 처음(메일 인증)부터
        setResetToken(null)
        setMail(null)
        setNext('')
        setConfirm('')
        setTried(false)
      }
      return setError(r.error.message)
    }
    setDone(true)
  }

  return (
    <main className="signup-done">
      <form className="done-card login-card" onSubmit={resetToken ? onSubmit : onCheck} noValidate>
        <a className="mobile-brand login-brand" href="#/home">
          <img src={logoMark} alt="" width={28} height={28} />
          <span>Durin Bank</span>
        </a>
        <h1>비밀번호 재설정</h1>
        {done ? (
          <p role="status">비밀번호를 다시 정했어요. 로그인돼 있던 기기는 모두 로그아웃했어요. 새 비밀번호로 로그인해 주세요.</p>
        ) : resetToken ? (
          <>
            <p>{id} 계정의 새 비밀번호를 정해 주세요. 5분 안에 마쳐야 해요.</p>
            <div className="login-fields">
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
              {error && (
                <p className="field-msg is-error" role="alert">
                  {error}
                </p>
              )}
            </div>
            <button className="btn-primary" type="submit" disabled={busy}>
              {busy ? '바꾸는 중…' : '새 비밀번호로 정하기'}
            </button>
          </>
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
              {error && (
                <p className="field-msg is-error" role="alert">
                  {error}
                </p>
              )}
            </div>
            {mail && (
              <button className="btn-primary" type="submit" disabled={busy}>
                {busy ? '확인 중…' : '다음'}
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
