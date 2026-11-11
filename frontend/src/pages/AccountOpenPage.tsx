// 새 계좌 개설 (docs/기획서.md Part 2 ACCT-F01) — 입출금·저축예금 2종. 예금·적금은 상품 화면에서 가입한다
// 유형·약관 동의(form) → 본인 확인(verify: PIN 6자리, PIN 이 없으면 로그인 비밀번호, action ACCOUNT_OPEN) → 결과
import { useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { openAccount, type AccountDetail } from '../api'
import { ymd } from '../productRules'
import { ACCOUNT_ART, ACCOUNT_STATUS_LABEL, ACCOUNT_TYPE_LABEL } from './accountArt'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import depositArt from '../assets/acct-deposit.png'
import './ProductPages.css'
import './AccountPages.css'

const TYPES = [
  {
    value: 'CHECKING',
    desc: '월급·생활비처럼 자유롭게 넣고 빼는 통장이에요.',
    points: ['자유로운 입출금', '이체·카드 연결', '적금 출금 계좌'],
  },
  {
    value: 'SAVINGS',
    desc: '쓰지 않을 돈을 생활비와 따로 모아 두는 통장이에요.',
    points: ['언제든 넣고 빼기', '생활비와 따로 모으기', '적금 출금 계좌로는 못 써요'],
  },
] as const

export default function AccountOpenPage() {
  const [type, setType] = useState<'CHECKING' | 'SAVINGS'>('CHECKING')
  const [agreed, setAgreed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<AccountDetail | null>(null)
  const [step, setStep] = useState<'form' | 'verify'>('form')
  const auth = useStepUp()
  const [key] = useState(() => crypto.randomUUID()) // 다시 눌러도 계좌가 하나만 생기게 — 이 화면에서 한 번 만든 번호를 계속 쓴다

  function onNext(e: FormEvent) {
    e.preventDefault()
    if (!agreed) return setError('필수 약관에 동의해 주세요.')
    setError(null)
    setStep('verify')
  }

  async function onOpen(e: FormEvent) {
    e.preventDefault()
    if (auth.missing) return setError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('ACCOUNT_OPEN')
    const r = ch.success ? await openAccount(type, key, ch.data) : ch
    setBusy(false)
    if (!r.success) return setError(r.error.message)
    setDone(r.data)
  }

  if (done)
    return (
      <AppShell title="계좌 개설" current="#/accounts">
        <section className={`panel acct-done is-${done.type.toLowerCase()}`} aria-live="polite">
          <img src={ACCOUNT_ART[done.type]} alt="" className="acct-done-art" />
          <h2 className="acct-done-title">{ACCOUNT_TYPE_LABEL[done.type]}이 생겼어요</h2>
          <p className="acct-done-number">두린은행 {done.number}</p>
          <dl className="prod-info acct-done-info">
            <div>
              <dt>개설일</dt>
              <dd>{ymd(done.startDate)}</dd>
            </div>
            <div>
              <dt>상태</dt>
              <dd>{ACCOUNT_STATUS_LABEL[done.status]}</dd>
            </div>
            <div>
              <dt>잔액</dt>
              <dd>0원</dd>
            </div>
          </dl>
          <div className="acct-done-actions">
            <a className="btn-hero is-primary" href={`#/accounts/${done.id}`}>
              이 계좌 보기
            </a>
            <a className="btn-hero" href="#/accounts">
              내 계좌 목록
            </a>
          </div>
        </section>
      </AppShell>
    )

  return (
    <AppShell title="계좌 개설" current="#/accounts">
      <a className="more prod-back" href="#/accounts">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        내 계좌
      </a>

      {step === 'form' && (
        <form className="acct-open" onSubmit={onNext} noValidate>
          <fieldset className="acct-types">
            <legend className="acct-open-title">어떤 통장을 만들까요?</legend>
            {TYPES.map((t) => (
              <label key={t.value} className={`panel acct-type is-${t.value.toLowerCase()}${type === t.value ? ' is-on' : ''}`}>
                <input type="radio" name="type" value={t.value} checked={type === t.value} onChange={() => setType(t.value)} />
                <span className="acct-type-check" aria-hidden="true" />
                <img src={ACCOUNT_ART[t.value]} alt="" className="acct-type-art" />
                <strong className="acct-type-name">{ACCOUNT_TYPE_LABEL[t.value]}</strong>
                <span className="acct-type-desc">{t.desc}</span>
                <ul className="acct-type-points">
                  {t.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </label>
            ))}
          </fieldset>

          <section className="panel acct-open-sum" aria-label="이렇게 만들어져요">
            <h3>이렇게 만들어져요</h3>
            <dl className="prod-info">
              <div>
                <dt>계좌 이름</dt>
                <dd>{ACCOUNT_TYPE_LABEL[type]} (만든 뒤 별명으로 바꿀 수 있어요)</dd>
              </div>
              <div>
                <dt>처음 잔액</dt>
                <dd>0원</dd>
              </div>
            </dl>
            <label className="check acct-consent">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => {
                  setAgreed(e.target.checked)
                  setError(null)
                }}
              />
              <span>
                <em className="tag-required">필수</em>
                두린은행 예금거래 기본약관·{ACCOUNT_TYPE_LABEL[type]} 약관에 동의해요 (모의 서비스)
              </span>
            </label>
            {error && (
              <p className="field-msg is-error" role="alert">
                {error}
              </p>
            )}
            <button className="btn-primary" type="submit">
              다음
            </button>
          </section>

          <a className="panel acct-promo" href="#/products">
            <img src={depositArt} alt="" className="acct-promo-art" />
            <span className="acct-card-main">
              <strong>금리가 붙는 예금·적금을 찾으세요?</strong>
              <small>예금·적금은 계좌가 아니라 상품으로 가입해요</small>
            </span>
            <Icon name="chevron" size={18} />
          </a>
        </form>
      )}

      {step === 'verify' && (
        <form className="panel prod-pad prod-form prod-narrow" onSubmit={onOpen} noValidate>
          <h3 className="card-title">본인 확인 후 만들어요</h3>
          <dl className="prod-dl">
            <div>
              <dt>만들 통장</dt>
              <dd>{ACCOUNT_TYPE_LABEL[type]}</dd>
            </div>
            <div>
              <dt>약관 동의</dt>
              <dd>두린은행 예금거래 기본약관·{ACCOUNT_TYPE_LABEL[type]} 약관</dd>
            </div>
          </dl>
          <StepUpField auth={auth} id="acct-open-auth" message={error ? { tone: 'error', text: error } : null} />
          <div className="prod-actions">
            <button className="btn-primary" type="submit" disabled={busy}>
              {busy ? '만드는 중…' : `${ACCOUNT_TYPE_LABEL[type]} 만들기`}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setStep('form')
                setError(null)
                auth.setValue('')
              }}
              disabled={busy}
            >
              이전으로
            </button>
          </div>
        </form>
      )}
    </AppShell>
  )
}
