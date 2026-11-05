// UI02 로그인 (docs/기획서.md Part 1 AUTH-F05). Google 로그인(F04)은 아직 없다. 아이디 찾기·비밀번호 재설정(F06)은 FindIdPage · ResetPasswordPage.
import { useState, type FormEvent } from 'react'
import Field from '../components/Field'
import { login } from '../api'
import logoMark from '../assets/logo-mark.png'
import './SignupPage.css'
import './LoginPage.css'

// 자동 로그아웃 뒤 안내 (SessionTimer 가 #/login?expired=idle|max 로 보낸다)
const EXPIRED: Record<string, string> = {
  idle: '10분 동안 이용이 없어 자동으로 로그아웃됐어요. 다시 로그인해 주세요.',
  max: '로그인한 지 12시간이 지나 자동으로 로그아웃됐어요. 다시 로그인해 주세요.',
}

export default function LoginPage({ expired = null }: { expired?: string | null }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username || !password) return setError('아이디와 비밀번호를 입력해 주세요.')
    setBusy(true)
    setError(null)
    const r = await login(username, password)
    setBusy(false)
    if (!r.success) return setError(r.error.message)
    location.hash = '#/home'
  }

  return (
    <main className="signup-done">
      <form className="done-card login-card" onSubmit={onSubmit} noValidate>
        <a className="mobile-brand login-brand" href="#/home">
          <img src={logoMark} alt="" width={28} height={28} />
          <span>Durin Bank</span>
        </a>
        <h1>로그인</h1>
        <p>두린뱅크 아이디로 로그인해 주세요.</p>
        {expired && EXPIRED[expired] && (
          <p className="login-notice" role="status">
            {EXPIRED[expired]}
          </p>
        )}

        <div className="login-fields">
          <Field id="login-username" label="아이디">
            <input
              id="login-username"
              className="input"
              autoComplete="username"
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-describedby="login-username-msg"
            />
          </Field>
          <Field id="login-password" label="비밀번호" message={error ? { tone: 'error', text: error } : null}>
            <div className="input-wrap">
              <input
                id="login-password"
                className="input"
                type={showPw ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!error}
                aria-describedby="login-password-msg"
              />
              <button type="button" className="toggle-pw" onClick={() => setShowPw((v) => !v)} aria-pressed={showPw}>
                {showPw ? '숨기기' : '보기'}
              </button>
            </div>
          </Field>
        </div>

        <button className="btn-primary" type="submit" disabled={busy}>
          {busy ? '확인 중…' : '로그인'}
        </button>

        <nav className="login-links" aria-label="계정 도움">
          <a href="#/find-id">아이디 찾기</a>
          <a href="#/reset-password">비밀번호 재설정</a>
          <a href="#/signup">회원가입</a>
        </nav>
      </form>
    </main>
  )
}
