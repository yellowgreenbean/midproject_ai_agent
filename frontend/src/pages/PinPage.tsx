// 간편 비밀번호(PIN) 만들기 · 바꾸기 · 잊었을 때 다시 정하기 (docs/기획서.md Part 1 AUTH-F11·F13 · UI09~UI11)
// 셋 다 ① 본인 확인(만들기·다시 정하기는 로그인 비밀번호, 바꾸기는 지금 PIN) ② 새 PIN ③ 한 번 더 — 순서가 같다.
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import PinPad from '../components/PinPad'
import { getPinStatus, getProfile, setPin, stepUp, type PinStatus } from '../api'
import { pinError } from '../pinRules'
import { stamp } from './accountArt'
import './ProductPages.css'
import './SettingsPages.css'

type Op = 'enroll' | 'change' | 'reset'
type Step = 'verify' | 'new' | 'confirm'
const OP: Record<Op, { title: string; action: 'PIN_ENROLL' | 'PIN_CHANGE' | 'PIN_RESET'; done: string }> = {
  enroll: { title: '간편 비밀번호 만들기', action: 'PIN_ENROLL', done: '간편 비밀번호를 만들었어요' },
  change: { title: '간편 비밀번호 바꾸기', action: 'PIN_CHANGE', done: '간편 비밀번호를 바꿨어요' },
  reset: { title: '간편 비밀번호 다시 정하기', action: 'PIN_RESET', done: '간편 비밀번호를 다시 정했어요' },
}

/** ISO 시각 → 2026.11.05 16:30 */
const when = (iso: string) => stamp(iso.slice(0, 19).replace(/\D/g, ''))

export default function PinPage() {
  const [status, setStatus] = useState<PinStatus | null>(null)
  const [birth, setBirth] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [op, setOp] = useState<Op | null>(null)
  const [step, setStep] = useState<Step>('verify')
  const [secret, setSecret] = useState('') // ① 로그인 비밀번호 또는 지금 PIN
  const [challenge, setChallenge] = useState('')
  const [pin, setPinValue] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    void getPinStatus().then((r) => (r.success ? setStatus(r.data) : r.error.code === 'UNAUTHENTICATED' ? (location.hash = '#/login') : setError(r.error.message)))
    void getProfile().then((r) => r.success && setBirth(r.data.birthDate))
  }, [])

  function start(next: Op) {
    setOp(next)
    setStep('verify')
    setSecret('')
    setPinValue('')
    setAgain('')
    setError(null)
    setDone(null)
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault()
    if (!op) return
    if (op === 'change' ? secret.length !== 6 : !secret) return setError(op === 'change' ? '지금 간편 비밀번호 6자리를 눌러 주세요.' : '로그인 비밀번호를 입력해 주세요.')
    setBusy(true)
    const r = await stepUp(OP[op].action, op === 'change' ? { pin: secret } : { password: secret })
    setBusy(false)
    setSecret('')
    if (!r.success) return setError(r.error.message)
    setChallenge(r.data)
    setError(null)
    setStep('new')
  }

  function onNew(e: FormEvent) {
    e.preventDefault()
    const err = pinError(pin, birth)
    if (err) return setError(err)
    setError(null)
    setStep('confirm')
  }

  async function onConfirm(e: FormEvent) {
    e.preventDefault()
    if (!op) return
    if (again !== pin) {
      setAgain('')
      return setError('두 번 누른 숫자가 달라요. 다시 눌러 주세요.')
    }
    setBusy(true)
    const r = await setPin(op, challenge, pin, again)
    setBusy(false)
    if (!r.success) {
      // 본인 확인 번호가 끝났으면(5분·한 번만) 처음부터, 규칙에 걸리면 새 PIN 부터
      setStep(r.error.code === 'STEP_UP_REQUIRED' ? 'verify' : 'new')
      setPinValue('')
      setAgain('')
      return setError(r.error.message)
    }
    setStatus(r.data)
    setDone(OP[op].done)
    setOp(null)
  }

  const locked = status?.lockedUntil ? `여러 번 틀려서 ${when(status.lockedUntil)}까지 간편 비밀번호를 쓸 수 없어요. 「잊으셨나요?」로 다시 정하면 바로 풀려요.` : null
  const msg = error ? ({ tone: 'error', text: error } as const) : null

  return (
    <AppShell title="간편 비밀번호" current="#/settings" busy={!status && !error}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      <section className="prod-head">
        <h2 className="prod-title is-dup">간편 비밀번호</h2>
        <p className="prod-sub">송금·카드·계좌 관리처럼 중요한 일을 할 때 로그인 비밀번호 대신 숫자 6자리로 확인해요.</p>
      </section>

      {done && (
        <p className="prod-ok" role="status">
          {done}
        </p>
      )}
      {locked && <p className="prod-warn">{locked}</p>}

      {status && !op && (
        <div className="panel set-form prod-form">
          <p className="empty-title">{status.enabled ? '간편 비밀번호를 쓰고 있어요' : '아직 간편 비밀번호가 없어요'}</p>
          {status.enabled && status.changedAt && <p className="prod-fine">마지막으로 정한 때 {when(status.changedAt)}</p>}
          {status.enabled ? (
            <>
              <button className="btn-primary" type="button" onClick={() => start('change')}>
                간편 비밀번호 바꾸기
              </button>
              <button className="btn-secondary" type="button" onClick={() => start('reset')}>
                간편 비밀번호를 잊으셨나요?
              </button>
            </>
          ) : (
            <button className="btn-primary" type="button" onClick={() => start('enroll')}>
              간편 비밀번호 만들기
            </button>
          )}
          <p className="prod-fine">같은 숫자만(111111), 이어지는 숫자(123456), 생년월일 6자리는 쓸 수 없어요. 5번 틀리면 10분 동안 막혀요.</p>
        </div>
      )}

      {op && (
        <form className="panel set-form prod-form" onSubmit={step === 'verify' ? onVerify : step === 'new' ? onNew : onConfirm} noValidate>
          <p className="empty-title">{OP[op].title}</p>
          <ol className="card-steps pin-steps" aria-label="진행 단계">
            {(['verify', 'new', 'confirm'] as const).map((s, i) => (
              <li key={s} className={s === step ? 'is-now' : i < ['verify', 'new', 'confirm'].indexOf(step) ? 'is-done' : undefined}>
                {['본인 확인', '새 번호', '한 번 더'][i]}
              </li>
            ))}
          </ol>
          {step === 'verify' &&
            (op === 'change' ? (
              <>
                <PinPad key="verify" id="pin-current" label="지금 간편 비밀번호" value={secret} onChange={setSecret} invalid={!!error} />
                <p id="pin-current-msg" className={`field-msg ${msg ? 'is-error' : ''}`} aria-live="polite">
                  {error}
                </p>
              </>
            ) : (
              <Field id="pin-password" label="로그인 비밀번호" message={msg}>
                <input
                  id="pin-password"
                  className="input"
                  type="password"
                  autoComplete="current-password"
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  aria-invalid={!!error}
                  aria-describedby="pin-password-msg"
                />
              </Field>
            ))}
          {step !== 'verify' && (
            <>
              {/* key 가 바뀌면 키패드를 새로 섞는다 */}
              <PinPad
                key={step}
                id="pin-new"
                label={step === 'new' ? '새 간편 비밀번호 6자리' : '같은 번호를 한 번 더'}
                value={step === 'new' ? pin : again}
                onChange={step === 'new' ? setPinValue : setAgain}
                invalid={!!error}
              />
              <p id="pin-new-msg" className={`field-msg ${msg ? 'is-error' : ''}`} aria-live="polite">
                {error}
              </p>
            </>
          )}
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? '확인하는 중…' : step === 'confirm' ? '이 번호로 정하기' : '다음'}
          </button>
          <button className="btn-secondary" type="button" onClick={() => setOp(null)}>
            그만두기
          </button>
        </form>
      )}
    </AppShell>
  )
}
