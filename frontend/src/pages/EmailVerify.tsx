// 메일 인증번호 받기·맞히기 — 아이디 찾기 · 비밀번호 재설정 · 이메일 바꾸기가 같이 쓴다 (가입 화면의 메일 인증과 같은 서버 주소)
// 모의 메일이라 보낸 번호를 화면에 함께 보여 준다(가입 화면과 같음).
import { useEffect, useState } from 'react'
import Field, { type FieldMessage } from '../components/Field'
import { confirmEmailCode, sendEmailCode, type MailPurpose } from '../api'

type Props = { purpose: MailPurpose; label: string; onVerified: (email: string, token: string) => void }

export default function EmailVerify({ purpose, label, onVerified }: Props) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [sent, setSent] = useState<{ resendAt: number } | null>(null)
  const [msg, setMsg] = useState<FieldMessage>(null)
  const [codeMsg, setCodeMsg] = useState<FieldMessage>(null)
  const [now, setNow] = useState(() => Date.now())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!sent) return
    const t = setInterval(() => setNow(Date.now()), 1000) // 다시 받기까지 남은 초
    return () => clearInterval(t)
  }, [sent])

  async function send() {
    if (!email.trim()) return setMsg({ tone: 'error', text: '이메일을 입력해 주세요.' })
    setBusy(true)
    const r = await sendEmailCode(email.trim(), purpose)
    setBusy(false)
    if (!r.success) return setMsg({ tone: 'error', text: r.error.message })
    setSent({ resendAt: r.data.resendAt })
    setNow(Date.now())
    setCode('')
    setCodeMsg(null)
    setMsg({ tone: 'info', text: `인증번호를 보냈어요. (모의 메일 — 인증번호 ${r.data.devCode})` })
  }

  async function confirm() {
    if (!/^\d{6}$/.test(code)) return setCodeMsg({ tone: 'error', text: '인증번호 6자리를 입력해 주세요.' })
    setBusy(true)
    const r = await confirmEmailCode(email.trim(), code, purpose)
    setBusy(false)
    if (!r.success) return setCodeMsg({ tone: 'error', text: r.error.message })
    onVerified(email.trim(), r.data.token)
  }

  const wait = sent ? Math.ceil((sent.resendAt - now) / 1000) : 0
  return (
    <div className="prod-form">
      <Field id={`${purpose}-email`} label={label} message={msg}>
        <div className="input-wrap">
          <input
            id={`${purpose}-email`}
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              setSent(null)
            }}
            aria-describedby={`${purpose}-email-msg`}
          />
          <button type="button" className="toggle-pw" disabled={busy || wait > 0} onClick={() => void send()}>
            {wait > 0 ? `${wait}초` : sent ? '다시 받기' : '번호 받기'}
          </button>
        </div>
      </Field>
      {sent && (
        <Field id={`${purpose}-code`} label="인증번호 6자리" message={codeMsg}>
          <div className="input-wrap">
            <input
              id={`${purpose}-code`}
              className="input"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              aria-invalid={codeMsg?.tone === 'error'}
              aria-describedby={`${purpose}-code-msg`}
            />
            <button type="button" className="toggle-pw" disabled={busy} onClick={() => void confirm()}>
              확인
            </button>
          </div>
        </Field>
      )}
    </div>
  )
}
