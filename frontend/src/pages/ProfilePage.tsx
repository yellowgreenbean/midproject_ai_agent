// 내 정보 (docs/기획서.md Part 1 AUTH-F07 · UI05) — 보기 · 월급일(바로) · 이메일(새 메일 인증 + 본인 확인) · 생년월일·성별(본인 확인). 이름·아이디는 못 바꾼다
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import Field from '../components/Field'
import EmailVerify from './EmailVerify'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { getProfile, updatePayday, updateProfile, type Profile } from '../api'
import './ProductPages.css'
import './AccountPages.css'
import './SettingsPages.css'

const DAYS = Array.from({ length: 31 }, (_, i) => i + 1)
const dot = (d: string) => d.slice(0, 10).replaceAll('-', '.')

export default function ProfilePage() {
  const [me, setMe] = useState<Profile | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<'payday' | 'email' | 'birth' | null>(null)
  const [payday, setPayday] = useState('')
  const [mail, setMail] = useState<{ email: string; token: string } | null>(null)
  const [birth, setBirth] = useState('')
  const [gender, setGender] = useState<'M' | 'F'>('M')
  const [formError, setFormError] = useState<string | null>(null)
  const auth = useStepUp()
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)

  useEffect(() => {
    void getProfile().then((r) => (r.success ? setMe(r.data) : r.error.code === 'UNAUTHENTICATED' ? setMe('guest') : setError(r.error.message)))
  }, [])

  async function onSave(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const r = await updatePayday(payday ? Number(payday) : null)
    setBusy(false)
    if (!r.success) return setError(r.error.message)
    setMe(r.data)
    setEditing(null)
    setSaved('월급일을 저장했어요.')
  }

  function open(next: 'payday' | 'email' | 'birth') {
    if (!me || me === 'guest') return
    setEditing(editing === next ? null : next)
    setPayday(me.payday ? String(me.payday) : '')
    setMail(null)
    setBirth(me.birthDate)
    setGender(me.gender)
    setFormError(null)
    auth.setValue('')
    setSaved(null)
  }

  async function onSensitive(e: FormEvent) {
    e.preventDefault()
    if (editing === 'email' && !mail) return setFormError('새 이메일의 인증번호를 먼저 확인해 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('PROFILE_CHANGE')
    const r = !ch.success
      ? ch
      : editing === 'email' && mail
        ? await updateProfile({ email: mail.email, emailVerificationToken: mail.token, stepUpChallengeId: ch.data })
        : await updateProfile({ birthDate: birth, gender, stepUpChallengeId: ch.data })
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setMe(r.data)
    setSaved(editing === 'email' ? '이메일을 바꿨어요. 이제 아이디 찾기·비밀번호 재설정은 새 이메일로 해요.' : '생년월일·성별을 바꿨어요.')
    setEditing(null)
  }

  return (
    <AppShell title="내 정보" current="#/settings" busy={!me && !error}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      <section className="prod-head">
        <h2 className="prod-title is-dup">내 정보</h2>
        <p className="prod-sub">가입할 때 적은 정보예요. 월급일은 언제든, 이메일·생년월일·성별은 본인 확인 뒤에 바꿀 수 있어요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!me && !error && <p className="home-loading">불러오는 중…</p>}
      {me === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인이 필요해요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {me && me !== 'guest' && (
        <div className="set-wrap">
          <dl className="panel set-info">
            <div>
              <dt>이름</dt>
              <dd>{me.name}</dd>
            </div>
            <div>
              <dt>아이디</dt>
              <dd>{me.username}</dd>
            </div>
            <div>
              <dt>이메일</dt>
              <dd>
                {me.email}
                {me.emailVerified && <span className="set-chip is-ok">인증됨</span>}
              </dd>
            </div>
            <div>
              <dt>생년월일</dt>
              <dd>{dot(me.birthDate)}</dd>
            </div>
            <div>
              <dt>성별</dt>
              <dd>{me.gender === 'M' ? '남성' : '여성'}</dd>
            </div>
            <div>
              <dt>로그인 방식</dt>
              <dd>아이디·비밀번호</dd>
            </div>
            <div>
              <dt>가입일</dt>
              <dd>{dot(me.createdAt)}</dd>
            </div>
          </dl>

          <ul className="panel acct-menu">
            <li>
              <button
                type="button"
                aria-expanded={editing === 'payday'}
                onClick={() => open('payday')}
              >
                <span className="acct-menu-label">월급일</span>
                <span className="acct-menu-value">{me.payday ? `매달 ${me.payday}일` : '없음'}</span>
                <Icon name="chevron" size={18} />
              </button>
              {editing === 'payday' && (
                <form className="acct-menu-form prod-form" onSubmit={onSave}>
                  <label className="field-label" htmlFor="set-payday">
                    월급이 들어오는 날
                  </label>
                  <select id="set-payday" className="input" value={payday} onChange={(e) => setPayday(e.target.value)}>
                    <option value="">없음</option>
                    {DAYS.map((d) => (
                      <option key={d} value={d}>
                        매달 {d}일
                      </option>
                    ))}
                  </select>
                  <div className="prod-actions">
                    <button className="btn-primary" type="submit" disabled={busy}>
                      저장
                    </button>
                    <button className="btn-secondary" type="button" onClick={() => setEditing(null)}>
                      취소
                    </button>
                  </div>
                </form>
              )}
            </li>
            <li>
              <button type="button" aria-expanded={editing === 'email'} onClick={() => open('email')}>
                <span className="acct-menu-label">이메일</span>
                <span className="acct-menu-value">{me.email}</span>
                <Icon name="chevron" size={18} />
              </button>
              {editing === 'email' && (
                <form className="acct-menu-form prod-form" onSubmit={onSensitive} noValidate>
                  {mail ? (
                    <p className="field-msg is-ok">{mail.email} 인증을 마쳤어요.</p>
                  ) : (
                    <EmailVerify purpose="EMAIL_CHANGE" label="새 이메일 — 인증번호를 보내 드려요" onVerified={(email, token) => setMail({ email, token })} />
                  )}
                  <StepUpField auth={auth} id="set-email-auth" message={formError ? { tone: 'error', text: formError } : null} />
                  <div className="prod-actions">
                    <button className="btn-primary" type="submit" disabled={busy}>
                      {busy ? '바꾸는 중…' : '이메일 바꾸기'}
                    </button>
                    <button className="btn-secondary" type="button" onClick={() => setEditing(null)}>
                      취소
                    </button>
                  </div>
                </form>
              )}
            </li>
            <li>
              <button type="button" aria-expanded={editing === 'birth'} onClick={() => open('birth')}>
                <span className="acct-menu-label">생년월일·성별</span>
                <span className="acct-menu-value">
                  {dot(me.birthDate)} · {me.gender === 'M' ? '남성' : '여성'}
                </span>
                <Icon name="chevron" size={18} />
              </button>
              {editing === 'birth' && (
                <form className="acct-menu-form prod-form" onSubmit={onSensitive} noValidate>
                  <Field id="set-birth" label="생년월일">
                    <input id="set-birth" className="input" type="date" value={birth} onChange={(e) => setBirth(e.target.value)} aria-describedby="set-birth-msg" />
                  </Field>
                  <fieldset className="card-reasons">
                    <legend className="field-label">성별</legend>
                    {(['M', 'F'] as const).map((g) => (
                      <label key={g} className="check">
                        <input type="radio" name="gender" checked={gender === g} onChange={() => setGender(g)} />
                        <span>{g === 'M' ? '남성' : '여성'}</span>
                      </label>
                    ))}
                  </fieldset>
                  <StepUpField auth={auth} id="set-birth-auth" message={formError ? { tone: 'error', text: formError } : null} />
                  <div className="prod-actions">
                    <button className="btn-primary" type="submit" disabled={busy}>
                      {busy ? '바꾸는 중…' : '저장'}
                    </button>
                    <button className="btn-secondary" type="button" onClick={() => setEditing(null)}>
                      취소
                    </button>
                  </div>
                </form>
              )}
            </li>
          </ul>
          {saved && (
            <p className="set-done" role="status">
              {saved}
            </p>
          )}
          <p className="prod-fine">이름과 아이디는 바꿀 수 없어요. 이메일·생년월일·성별은 본인 확인을 한 번 더 해요.</p>
        </div>
      )}
    </AppShell>
  )
}
