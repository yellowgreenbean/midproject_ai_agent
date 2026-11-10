// UI01 회원가입 (docs/기획서.md Part 1 3.1 흐름 · AUTH-F01 회원가입 · F02 아이디 중복 확인 · F03 이메일 인증 · F10 약관)
import { useEffect, useState, type FormEvent } from 'react'
import Field, { type FieldMessage } from '../components/Field'
import { checkUsername, confirmEmailCode, getTerms, register, sendEmailCode, type Term } from '../api'
import {
  birthDateError,
  emailError,
  localToday,
  nameError,
  passwordConfirmError,
  passwordError,
  usernameError,
} from '../signupRules'
import logoMark from '../assets/logo-mark.png'
import hero from '../assets/signup-hero.png'
import './SignupPage.css'

type IdCheck = 'idle' | 'checking' | 'available' | 'taken'
type Mail = { expiresAt: number; resendAt: number }

const STEPS = ['아이디·비밀번호', '이메일 인증', '기본 정보', '약관 동의']
const mmss = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function SignupPage() {
  const today = localToday()
  const [username, setUsername] = useState('')
  const [idCheck, setIdCheck] = useState<IdCheck>('idle')
  const [idServerMsg, setIdServerMsg] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [email, setEmail] = useState('')
  const [mail, setMail] = useState<Mail | null>(null)
  const [code, setCode] = useState('')
  const [mailMsg, setMailMsg] = useState<FieldMessage>(null)
  const [mailBusy, setMailBusy] = useState(false)
  const [emailToken, setEmailToken] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [gender, setGender] = useState<'M' | 'F' | ''>('')
  const [payday, setPayday] = useState('')
  const [terms, setTerms] = useState<Term[]>([])
  const [agreed, setAgreed] = useState<Record<string, boolean>>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    getTerms().then((r) => (r.success ? setTerms(r.data) : setFormError(r.error.message)))
  }, [])

  // 인증번호 남은 시간 표시용 시계 (실제 제한은 서버 기준)
  useEffect(() => {
    if (!mail || emailToken) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [mail, emailToken])

  const errors = {
    username: usernameError(username),
    password: passwordError(password, username),
    password2: passwordConfirmError(password, password2),
    email: emailError(email),
    name: nameError(name),
    birthDate: birthDateError(birthDate, today),
    gender: gender ? null : '성별을 선택해 주세요.',
  }
  const show = (k: keyof typeof errors): FieldMessage =>
    touched[k] && errors[k] ? { tone: 'error', text: errors[k] } : null
  const touch = (k: string) => setTouched((t) => ({ ...t, [k]: true }))

  const requiredAgreed = terms.length > 0 && terms.every((t) => !t.required || agreed[t.id])
  const allAgreed = terms.length > 0 && terms.every((t) => agreed[t.id])
  const missing =
    (errors.username || idCheck !== 'available' ? '아이디 중복 확인이 필요해요' : null) ??
    (errors.password || errors.password2 ? '비밀번호를 확인해 주세요' : null) ??
    (!emailToken ? '이메일 인증이 필요해요' : null) ??
    (errors.name || errors.birthDate || errors.gender ? '기본 정보를 입력해 주세요' : null) ??
    (!requiredAgreed ? '필수 약관에 동의해 주세요' : null)
  const stepDone = [
    !errors.username && idCheck === 'available' && !errors.password && !errors.password2,
    !!emailToken,
    !errors.name && !errors.birthDate && !errors.gender,
    requiredAgreed,
  ]

  const idMsg: FieldMessage =
    idCheck === 'available'
      ? { tone: 'ok', text: '사용할 수 있는 아이디예요.' }
      : idCheck === 'taken'
        ? { tone: 'error', text: '이미 사용 중인 아이디예요.' }
        : idServerMsg
          ? { tone: 'error', text: idServerMsg }
          : (show('username') ?? (username ? { tone: 'info', text: '중복 확인을 눌러 주세요.' } : null))

  async function onCheckId() {
    touch('username')
    if (errors.username) return
    setIdCheck('checking')
    setIdServerMsg(null)
    const r = await checkUsername(username)
    if (!r.success) {
      setIdCheck('idle')
      setIdServerMsg(r.error.message || '확인에 실패했어요. 다시 시도해 주세요.')
      return
    }
    setIdCheck(r.data.available ? 'available' : 'taken')
  }

  async function onSendCode() {
    touch('email')
    if (errors.email) return
    setMailBusy(true)
    const r = await sendEmailCode(email)
    setMailBusy(false)
    if (!r.success) return setMailMsg({ tone: 'error', text: r.error.message })
    setMail(r.data)
    setNow(Date.now())
    setCode('')
    setMailMsg({ tone: 'info', text: `${email}로 인증번호를 보냈어요. 메일함(스팸함 포함)을 확인해 주세요.` })
  }

  async function onConfirmCode() {
    setMailBusy(true)
    const r = await confirmEmailCode(email, code)
    setMailBusy(false)
    if (!r.success) return setMailMsg({ tone: 'error', text: r.error.message })
    setEmailToken(r.data.token)
    setMailMsg({ tone: 'ok', text: '이메일 인증이 완료됐어요.' })
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setTouched(Object.fromEntries(Object.keys(errors).map((k) => [k, true])))
    if (missing || submitting || !emailToken || !gender) return
    setSubmitting(true)
    setFormError(null)
    const r = await register({
      username,
      password,
      passwordConfirm: password2,
      email,
      emailVerificationToken: emailToken,
      name: name.trim(),
      birthDate,
      gender,
      payday: payday ? Number(payday) : null,
      agreedTermIds: terms.filter((t) => agreed[t.id]).map((t) => t.id), // '모두 동의'여도 항목별로 보낸다
    })
    setSubmitting(false)
    if (!r.success) {
      if (r.error.code === 'USERNAME_TAKEN') setIdCheck('taken')
      if (r.error.code === 'EMAIL_NOT_VERIFIED') setEmailToken(null)
      return setFormError(r.error.message)
    }
    setDone(r.data.user_id)
  }

  const codeExpired = !!mail && now > mail.expiresAt
  const resendLeft = mail ? mail.resendAt - now : 0

  if (done) {
    return (
      <main className="signup-done">
        <div className="done-card">
          <div className="done-icon" aria-hidden="true">✓</div>
          <h1>{name.trim()}님, 가입을 환영해요</h1>
          <p>두린뱅크 계정이 만들어졌고 바로 로그인됐어요. 홈에서 첫 계좌를 열어 보세요.</p>
          <dl className="done-info">
            <dt>아이디</dt>
            <dd>{username}</dd>
            <dt>이메일</dt>
            <dd>{email}</dd>
          </dl>
          <a className="done-action" href="#/home">
            홈으로 가기
          </a>
        </div>
      </main>
    )
  }

  return (
    <div className="signup">
      <aside className="brand-panel">
        <a className="brand" href="#/home">
          <img src={logoMark} alt="" width={36} height={36} />
          <span>Durin Bank</span>
        </a>
        <img className="brand-hero" src={hero} alt="" />
        <h2 className="brand-title">
          몇 가지만 입력하면
          <br />
          바로 시작할 수 있어요
        </h2>
        <ol className="brand-steps">
          {STEPS.map((s, i) => (
            <li key={s} className={stepDone[i] ? 'is-done' : ''}>
              <span className="step-no">{stepDone[i] ? '✓' : i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </aside>

      <main className="signup-main">
        <a className="mobile-brand" href="#/home">
          <img src={logoMark} alt="" width={28} height={28} />
          <span>Durin Bank</span>
        </a>
        <h1 className="signup-title">회원가입</h1>
        <p className="signup-sub">두린뱅크 계정을 만들어 주세요.</p>

        <form className="signup-form" onSubmit={onSubmit} noValidate>
          <section className="card" aria-labelledby="sec-account">
            <h2 id="sec-account" className="card-title">
              <span className="card-no">1</span>아이디·비밀번호
            </h2>
            <Field id="username" label="아이디" message={idMsg}>
              <div className="row">
                <input
                  id="username"
                  className="input"
                  value={username}
                  autoComplete="username"
                  autoCapitalize="none"
                  placeholder="영문 소문자·숫자 4~20자"
                  aria-invalid={idCheck === 'taken' || !!show('username')}
                  aria-describedby="username-msg"
                  onChange={(e) => {
                    setUsername(e.target.value.trim().toLowerCase())
                    setIdCheck('idle') // 아이디를 바꾸면 다시 확인
                    setIdServerMsg(null)
                  }}
                  onBlur={() => touch('username')}
                />
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={onCheckId}
                  disabled={!username || idCheck === 'checking' || idCheck === 'available'}
                >
                  {idCheck === 'checking' ? '확인 중' : '중복 확인'}
                </button>
              </div>
            </Field>

            <Field
              id="password"
              label="비밀번호"
              message={show('password') ?? { tone: 'info', text: '영문·숫자를 섞어 8자 이상' }}
            >
              <div className="input-wrap">
                <input
                  id="password"
                  className="input"
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  autoComplete="new-password"
                  aria-invalid={!!show('password')}
                  aria-describedby="password-msg"
                  onChange={(e) => setPassword(e.target.value)}
                  onBlur={() => touch('password')}
                />
                <button
                  type="button"
                  className="toggle-pw"
                  aria-pressed={showPw}
                  onClick={() => setShowPw((v) => !v)}
                >
                  {showPw ? '숨기기' : '보기'}
                </button>
              </div>
            </Field>

            <Field
              id="password2"
              label="비밀번호 확인"
              message={
                show('password2') ??
                (password2 && !errors.password2 ? { tone: 'ok', text: '비밀번호가 일치해요.' } : null)
              }
            >
              <input
                id="password2"
                className="input"
                type={showPw ? 'text' : 'password'}
                value={password2}
                autoComplete="new-password"
                aria-invalid={!!show('password2')}
                aria-describedby="password2-msg"
                onChange={(e) => setPassword2(e.target.value)}
                onBlur={() => touch('password2')}
              />
            </Field>
          </section>

          <section className="card" aria-labelledby="sec-email">
            <h2 id="sec-email" className="card-title">
              <span className="card-no">2</span>이메일 인증
            </h2>
            <Field id="email" label="이메일" message={show('email') ?? (mail ? null : mailMsg)}>
              <div className="row">
                <input
                  id="email"
                  className="input"
                  type="email"
                  inputMode="email"
                  value={email}
                  autoComplete="email"
                  placeholder="example@email.com"
                  readOnly={!!emailToken}
                  aria-invalid={!!show('email')}
                  aria-describedby="email-msg"
                  onChange={(e) => {
                    setEmail(e.target.value.trim())
                    setMail(null) // 이메일을 바꾸면 인증을 다시
                    setEmailToken(null)
                    setMailMsg(null)
                  }}
                  onBlur={() => touch('email')}
                />
                {emailToken ? (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setEmailToken(null)
                      setMail(null)
                      setMailMsg(null)
                    }}
                  >
                    변경
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={onSendCode}
                    disabled={!email || mailBusy || resendLeft > 0}
                  >
                    {resendLeft > 0 ? `재발송 ${Math.ceil(resendLeft / 1000)}초` : mail ? '다시 받기' : '인증번호 받기'}
                  </button>
                )}
              </div>
            </Field>

            {mail && (
              <Field
                id="code"
                label="인증번호"
                message={codeExpired && !emailToken ? { tone: 'error', text: '인증 시간이 지났어요. 다시 받아 주세요.' } : mailMsg}
              >
                <div className="row">
                  <div className="input-wrap">
                    <input
                      id="code"
                      className="input"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      placeholder="6자리 숫자"
                      value={code}
                      readOnly={!!emailToken}
                      aria-describedby="code-msg"
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    />
                    {!emailToken && (
                      <span className={`timer ${codeExpired ? 'is-expired' : ''}`}>{mmss(mail.expiresAt - now)}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={onConfirmCode}
                    disabled={code.length !== 6 || mailBusy || codeExpired || !!emailToken}
                  >
                    {emailToken ? '인증 완료' : '확인'}
                  </button>
                </div>
              </Field>
            )}
          </section>

          <section className="card" aria-labelledby="sec-profile">
            <h2 id="sec-profile" className="card-title">
              <span className="card-no">3</span>기본 정보
            </h2>
            <Field id="name" label="이름(실명)" message={show('name') ?? { tone: 'info', text: '계좌 예금주 이름으로 쓰여요.' }}>
              <input
                id="name"
                className="input"
                value={name}
                autoComplete="name"
                aria-invalid={!!show('name')}
                aria-describedby="name-msg"
                onChange={(e) => setName(e.target.value)}
                onBlur={() => touch('name')}
              />
            </Field>

            <div className="grid-2">
              <Field id="birthDate" label="생년월일" message={show('birthDate')}>
                <input
                  id="birthDate"
                  className="input"
                  type="date"
                  min="1900-01-01"
                  max={today}
                  value={birthDate}
                  autoComplete="bday"
                  aria-invalid={!!show('birthDate')}
                  aria-describedby="birthDate-msg"
                  onChange={(e) => setBirthDate(e.target.value)}
                  onBlur={() => touch('birthDate')}
                />
              </Field>

              <Field id="payday" label="월급일" optional message={null}>
                <select
                  id="payday"
                  className="input"
                  value={payday}
                  aria-describedby="payday-msg"
                  onChange={(e) => setPayday(e.target.value)}
                >
                  <option value="">선택 안 함</option>
                  {Array.from({ length: 31 }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      매월 {i + 1}일
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <fieldset className="field gender" aria-describedby="gender-msg">
              <legend className="field-label">성별</legend>
              <div className="segmented">
                {(
                  [
                    ['M', '남성'],
                    ['F', '여성'],
                  ] as const
                ).map(([v, label]) => (
                  <label key={v} className={gender === v ? 'is-on' : ''}>
                    <input
                      type="radio"
                      name="gender"
                      value={v}
                      checked={gender === v}
                      onChange={() => setGender(v)}
                      onBlur={() => touch('gender')}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <p id="gender-msg" className={`field-msg ${show('gender') ? 'is-error' : ''}`} aria-live="polite">
                {show('gender')?.text}
              </p>
            </fieldset>

            <p className="purpose">
              생년월일·성별은 카드 발급 나이 확인과 발급 통계에만, 월급일은 카드 사용 금액 예측에만 써요. 월급일은 나중에 내
              정보에서 넣어도 돼요.
            </p>
          </section>

          <section className="card" aria-labelledby="sec-terms">
            <h2 id="sec-terms" className="card-title">
              <span className="card-no">4</span>약관 동의
            </h2>
            <label className="check check-all">
              <input
                type="checkbox"
                checked={allAgreed}
                disabled={terms.length === 0}
                onChange={(e) => setAgreed(Object.fromEntries(terms.map((t) => [t.id, e.target.checked])))}
              />
              <span>모두 동의해요</span>
            </label>
            <ul className="terms">
              {terms.map((t) => (
                <li key={t.id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={!!agreed[t.id]}
                      onChange={(e) => setAgreed((a) => ({ ...a, [t.id]: e.target.checked }))}
                    />
                    <span>
                      <em className={t.required ? 'tag-required' : 'tag-optional'}>{t.required ? '필수' : '선택'}</em>
                      {t.title}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>

          <div className="submit-bar">
            {formError && (
              <p className="form-error" role="alert">
                {formError}
              </p>
            )}
            <button type="submit" className="btn-primary" disabled={!!missing || submitting} aria-describedby="submit-hint">
              {submitting ? '가입하는 중…' : '가입하기'}
            </button>
            <p id="submit-hint" className="submit-hint" aria-live="polite">
              {missing ?? '모든 준비가 끝났어요.'}
            </p>
          </div>
        </form>
      </main>
    </div>
  )
}
