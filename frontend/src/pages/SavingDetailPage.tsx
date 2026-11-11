// 내 가입 상품 상세 — 납입 내역 · 추가 납입(적금, PROD-F12) · 중도 해지 (docs/기획서.md Part 3 PROD-F09·F10·F12)
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { getMySubscription, payInstallment, terminateSubscription, type SubscriptionDetail } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { digitsOnly, PAYMENT_TYPE_LABEL, won, ymd } from '../productRules'
import { PRODUCT_ART, STATUS_LABEL, TYPE_LABEL } from './productArt'
import './ProductPages.css'

type Action = 'pay' | 'terminate' | null

export default function SavingDetailPage({ id }: { id: string }) {
  const [s, setS] = useState<SubscriptionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState<Action>(null)
  const [amount, setAmount] = useState('')
  const auth = useStepUp()
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    void getMySubscription(id).then((r) => (r.success ? setS(r.data) : setError(r.error.message)))
  }, [id])

  if (!s)
    return (
      <AppShell title="내 가입 상품" current="#/products" busy={!error}>
        {error ? (
          <div className="panel empty">
            <p className="empty-title">{error}</p>
            <a className="btn-pill" href={error.includes('로그인') ? '#/login' : '#/my/savings'}>
              {error.includes('로그인') ? '로그인하기' : '내 가입 상품으로'}
            </a>
          </div>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )

  const left = s.monthlyMax === null ? null : Math.max(s.monthlyMax - s.paidThisMonth, 0)
  const fixed = s.paymentType === 'FIXED'
  const savingsActive = s.productType === 'INSTALLMENT_SAVINGS' && s.status === 'ACTIVE'
  // 다음 회차 시작일 — "12월 10일부터"
  const nextDay = s.nextPeriodStart ? `${Number(s.nextPeriodStart.slice(4, 6))}월 ${Number(s.nextPeriodStart.slice(6, 8))}일` : ''

  function open(a: Action) {
    setAction(a)
    setFormError(null)
    auth.setValue('')
    setNotice(null)
    setAmount(a === 'pay' && fixed && s?.monthlyAmount ? String(s.monthlyAmount) : '') // 정액은 정한 금액만 넣을 수 있다
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (action === 'pay' && !amount) return setFormError('넣을 돈을 입력해 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('SUBSCRIPTION')
    const r = !ch.success ? ch : action === 'pay' ? await payInstallment(id, Number(amount), ch.data) : await terminateSubscription(id, ch.data)
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    setNotice(action === 'pay' ? `${won(Number(amount))}을 넣었어요.` : `해지했어요. 원금 ${won(r.data.principal)}을 출금 계좌로 돌려드렸어요.`)
    setS(r.data)
    setAction(null)
    setAmount('')
  }

  return (
    <AppShell title="내 가입 상품" current="#/products">
      <a className="more prod-back" href="#/my/savings">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        내 가입 상품
      </a>

      <section className="panel prod-hero" aria-labelledby="sub-name">
        <img src={PRODUCT_ART[s.productType]} alt="" className="prod-hero-art" />
        <div className="prod-hero-text">
          <p className="prod-kind">
            {TYPE_LABEL[s.productType]} · {STATUS_LABEL[s.status] ?? s.status}
          </p>
          <h2 id="sub-name">{s.productName}</h2>
          <a className="more" href={`#/products/${s.productId}`}>
            상품 안내 보기 <Icon name="chevron" size={14} />
          </a>
        </div>
        <dl className="prod-rates-big">
          <div>
            <dt>{s.productType === 'TIME_DEPOSIT' ? '맡긴 돈' : '넣은 돈'}</dt>
            <dd className="is-strong">{won(s.principal)}</dd>
          </div>
        </dl>
      </section>

      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}

      <dl className="panel prod-dl">
        {s.paymentType && (
          <div>
            <dt>납입 방식</dt>
            <dd>
              {PAYMENT_TYPE_LABEL[s.paymentType]}
              {fixed && s.monthlyAmount !== null && ` · 매달 ${won(s.monthlyAmount)}`}
            </dd>
          </div>
        )}
        <div>
          <dt>적용 금리</dt>
          <dd>연 {s.appliedRate}% (세전)</dd>
        </div>
        <div>
          <dt>가입일</dt>
          <dd>{ymd(s.startDate)}</dd>
        </div>
        <div>
          <dt>만기일</dt>
          <dd>{ymd(s.maturityDate)}</dd>
        </div>
        <div>
          <dt>출금 계좌</dt>
          <dd>
            {s.accountNumber}
            {s.accountStatus === 'SUSPENDED' && ' · 일시정지'}
          </dd>
        </div>
        {savingsActive && (
          <div>
            <dt>이번 회차</dt>
            <dd>
              {fixed
                ? s.paidThisMonth > 0
                  ? `넣었어요 · 다음 회차는 ${nextDay}부터`
                  : `아직 안 넣었어요 · ${nextDay} 전까지 넣어 주세요`
                : left === null
                  ? `${won(s.paidThisMonth)} 넣음`
                  : `${won(s.paidThisMonth)} 넣음 · ${won(left)} 더 넣을 수 있어요 (${nextDay}부터 새 회차)`}
            </dd>
          </div>
        )}
      </dl>

      {s.status === 'ACTIVE' && (
        <section aria-label="가입 상품 관리" className="prod-manage">
          {!s.earlyTerminationAllowed && <p className="prod-fine">중도 해지할 수 없는 상품이에요. 만기일에 원금과 이자를 출금 계좌로 보내 드려요.</p>}
          {s.accountStatus === 'SUSPENDED' && <p className="prod-warn">출금 계좌가 정지되어 있어요. 정지를 해제해야 해지·만기 금액을 받을 수 있어요.</p>}
          <div className="prod-tabs">
            {s.payable && (
              <button type="button" className="prod-chip" aria-pressed={action === 'pay'} onClick={() => open(action === 'pay' ? null : 'pay')}>
                돈 넣기
              </button>
            )}
            {s.earlyTerminationAllowed && (
              <button type="button" className="prod-chip" aria-pressed={action === 'terminate'} onClick={() => open(action === 'terminate' ? null : 'terminate')}>
                중도 해지
              </button>
            )}
          </div>

          {action && (
            <form className="panel prod-pad prod-form prod-narrow" onSubmit={onSubmit} noValidate>
              {action === 'pay' ? (
                <Field id="pay-amount" label={fixed ? '이번 회차에 넣을 돈 (정액)' : '넣을 돈'}>
                  <div className="input-wrap">
                    <input
                      id="pay-amount"
                      className="input"
                      inputMode="numeric"
                      value={amount ? Number(amount).toLocaleString('ko-KR') : ''}
                      onChange={(e) => setAmount(digitsOnly(e.target.value).slice(0, 13))}
                      readOnly={fixed}
                    />
                    <span className="timer prod-suffix">원</span>
                  </div>
                </Field>
              ) : (
                <p className="prod-warn" role="note">
                  지금 해지하면 이자 없이 원금 {won(s.principal)}만 출금 계좌로 돌려받아요. 해지한 뒤에는 되돌릴 수 없어요.
                </p>
              )}
              <StepUpField auth={auth} id="act-password" message={formError ? { tone: 'error', text: formError } : null} />
              <button className="btn-primary" type="submit" disabled={busy}>
                {busy ? '처리 중…' : action === 'pay' ? '넣기' : '해지하기'}
              </button>
            </form>
          )}
        </section>
      )}

      {s.payments.length > 0 && (
        <section aria-labelledby="pays">
          <h2 id="pays" className="section-title">
            납입 내역
          </h2>
          <ul className="panel rows prod-pays">
            {s.payments.map((x) => (
              <li key={x.paidAt + x.amount}>
                <span>{ymd(x.paidAt)}</span>
                <strong>{won(x.amount)}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}
    </AppShell>
  )
}
