// 아이디 찾기 (docs/기획서.md Part 1 AUTH-F06 · UI03) — 가입한 이메일로 인증번호를 받아 맞히면 가린 아이디를 보여 준다
import { useState } from 'react'
import EmailVerify from './EmailVerify'
import { recoverUsernames } from '../api'
import logoMark from '../assets/logo-mark.png'
import './SignupPage.css'
import './LoginPage.css'

export default function FindIdPage() {
  const [found, setFound] = useState<{ username: string; created_at: string }[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function onVerified(email: string, token: string) {
    const r = await recoverUsernames(email, token)
    if (!r.success) return setError(r.error.message)
    setFound(r.data)
  }

  return (
    <main className="signup-done">
      <div className="done-card login-card">
        <a className="mobile-brand login-brand" href="#/home">
          <img src={logoMark} alt="" width={28} height={28} />
          <span>Durin Bank</span>
        </a>
        <h1>아이디 찾기</h1>
        {found === null ? (
          <>
            <p>가입할 때 적은 이메일로 인증번호를 보내 드려요.</p>
            <div className="login-fields">
              <EmailVerify purpose="USERNAME_RECOVERY" label="가입한 이메일" onVerified={(e, t) => void onVerified(e, t)} />
              {error && (
                <p className="field-msg is-error" role="alert">
                  {error}
                </p>
              )}
            </div>
          </>
        ) : found.length === 0 ? (
          <p role="status">이 이메일로 가입한 아이디가 없어요. 다른 이메일로 가입했는지 확인해 주세요.</p>
        ) : (
          <div role="status">
            <p>이 이메일로 가입한 아이디예요. 가린 글자는 직접 떠올려 주세요.</p>
            <ul className="login-fields login-found">
              {found.map((f) => (
                <li key={f.username}>
                  <strong>{f.username}</strong>
                  <small>{f.created_at.slice(0, 10).replaceAll('-', '.')} 가입</small>
                </li>
              ))}
            </ul>
          </div>
        )}
        <nav className="login-links" aria-label="계정 도움">
          <a href="#/reset-password">비밀번호 재설정</a>
          <a href="#/login">로그인</a>
        </nav>
      </div>
    </main>
  )
}
