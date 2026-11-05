// 가입 (docs/기획서.md Part 3 PROD-F07·F08) — 조건 입력 → 서버 검증 → 최종 확인 + 본인 확인(비밀번호) → 가입 완료
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import {
  getAccountDashboard,
  getMe,
  getProduct,
  subscribe,
  validateSubscription,
  type Account,
  type Estimate,
  type ProductDetail,
  type Subscription,
} from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { defaultMonths, digitsOnly, isDayUnit, monthOptions, won, ymd } from '../productRules'
import { TYPE_LABEL } from './productArt'
import './ProductPages.css'

type Step = 'form' | 'confirm' | 'done'
type Load = { p: ProductDetail; accounts: Account[] } | 'guest' | null

// 같은 가입 요청을 두 번 보내도 계약이 하나만 생기게 하는 번호 (최종 확인 화면에 들어올 때 한 번 만든다)
const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`)

export default function SubscribePage({ id, query }: { id: string; query: URLSearchParams }) {
  const [load, setLoad] = useState<Load>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('form')
  const [accountId, setAccountId] = useState('')
  const [amount, setAmount] = useState(digitsOnly(query.get('amount') ?? ''))
  const [months, setMonths] = useState(Number(query.get('months')) || 0)
  const [days, setDays] = useState(digitsOnly(query.get('days') ?? ''))
  const [est, setEst] = useState<Estimate | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const auth = useStepUp()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<Subscription | null>(null)

  useEffect(() => {
    void (async () => {
      const [me, prod] = await Promise.all([getMe(), getProduct(id)])
      if (!prod.success) return setError(prod.error.message)
      if (!me.success) return setLoad('guest')
      const dash = await getAccountDashboard()
      if (!dash.success) return setError(dash.error.message)
      const usable = dash.data.accounts.filter((a) => a.type === 'CHECKING' && a.status === 'ACTIVE') // 서버도 다시 확인한다
      setLoad({ p: prod.data, accounts: usable })
      setAccountId((cur) => cur || usable[0]?.id || '')
      setMonths((cur) => (monthOptions(prod.data).includes(cur) ? cur : defaultMonths(monthOptions(prod.data))))
    })()
  }, [id])

  const title = '상품 가입'
  if (error || load === null)
    return (
      <AppShell title={title} current="#/products" busy={!error}>
        {error ? (
          <p className="home-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )
  if (load === 'guest')
    return (
      <AppShell title={title} current="#/products">
        <div className="panel empty">
          <p className="empty-title">가입하려면 로그인이 필요해요</p>
          <p className="empty-sub">상품 둘러보기와 이자 계산은 로그인 없이도 할 수 있어요.</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      </AppShell>
    )

  const { p, accounts } = load
  const deposit = p.type === 'TIME_DEPOSIT'
  const account = accounts.find((a) => a.id === accountId)
  const byDay = isDayUnit(p)
  const period = byDay ? { months: 0, days: Number(days) } : { months }

  async function onCheck(e: FormEvent) {
    e.preventDefault()
    if (!accountId) return setFormError('출금할 입출금 계좌가 없어요. 먼저 계좌를 만들어 주세요.')
    if (!amount) return setFormError(`${deposit ? '예치금' : '월 납입액'}을 입력해 주세요.`)
    setBusy(true)
    const r = await validateSubscription(p.id, accountId, Number(amount), period)
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setFormError(null)
    setEst(r.data)
    setKey(newKey())
    setStep('confirm')
  }

  async function onSubscribe(e: FormEvent) {
    e.preventDefault()
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('SUBSCRIPTION')
    if (!ch.success) {
      setBusy(false)
      return setFormError(ch.error.message)
    }
    const r = await subscribe({ productId: p.id, accountId, amount: Number(amount), term: period, stepUpChallengeId: ch.data }, key)
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    setDone(r.data)
    setStep('done')
  }

  if (step === 'done' && done)
    return (
      <AppShell title={title} current="#/products">
        <div className="panel empty prod-done">
          <p className="empty-title">{done.productName} 가입을 마쳤어요</p>
          <p className="empty-sub">
            연 {done.appliedRate}% · 만기 {ymd(done.maturityDate)} · {done.accountNumber} 에서 {won(done.principal)} 출금
          </p>
          <div className="prod-done-actions">
            <a className="btn-pill" href="#/my/savings">
              내 가입 상품 보기
            </a>
            <a className="btn-pill" href="#/home">
              홈으로
            </a>
          </div>
        </div>
      </AppShell>
    )

  return (
    <AppShell title={title} current="#/products">
      <section className="prod-head">
        <p className="prod-kind">{TYPE_LABEL[p.type]}</p>
        <h2 className="prod-title">{p.name}</h2>
      </section>

      {step === 'form' && (
        <form className="panel prod-pad prod-form prod-narrow" onSubmit={onCheck} noValidate>
          <Field id="sub-account" label="출금 계좌">
            {accounts.length === 0 ? (
              <p className="prod-muted">쓸 수 있는 입출금 계좌가 없어요. 정상 상태의 본인 입출금 계좌가 필요해요.</p>
            ) : (
              <select id="sub-account" className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} {a.number} · {won(a.balance)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field id="sub-amount" label={deposit ? '맡길 돈' : '첫 달에 넣을 돈'} message={formError ? { tone: 'error', text: formError } : null}>
            <div className="input-wrap">
              <input
                id="sub-amount"
                className="input"
                inputMode="numeric"
                value={amount ? Number(amount).toLocaleString('ko-KR') : ''}
                onChange={(e) => setAmount(digitsOnly(e.target.value).slice(0, 13))}
                aria-invalid={!!formError}
                aria-describedby="sub-amount-msg"
              />
              <span className="timer prod-suffix">원</span>
            </div>
          </Field>
          {byDay ? (
            <Field id="sub-days" label={`기간 (${p.minDays ?? 1}~${p.maxDays ?? ''}일)`}>
              <div className="input-wrap">
                <input
                  id="sub-days"
                  className="input"
                  inputMode="numeric"
                  value={days}
                  onChange={(e) => setDays(digitsOnly(e.target.value).slice(0, 4))}
                />
                <span className="timer prod-suffix">일</span>
              </div>
            </Field>
          ) : (
            <Field id="sub-months" label="기간">
              <select id="sub-months" className="input" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
                {monthOptions(p).map((m) => (
                  <option key={m} value={m}>
                    {m}개월
                  </option>
                ))}
              </select>
            </Field>
          )}
          <button className="btn-primary" type="submit" disabled={busy || accounts.length === 0}>
            {busy ? '확인 중…' : '다음'}
          </button>
        </form>
      )}

      {step === 'confirm' && est && (
        <form className="panel prod-pad prod-form prod-narrow" onSubmit={onSubscribe} noValidate>
          <h3 className="card-title">가입 내용을 확인해 주세요</h3>
          <dl className="prod-dl">
            <div>
              <dt>출금 계좌</dt>
              <dd>
                {account?.name} {account?.number}
              </dd>
            </div>
            <div>
              <dt>오늘 출금</dt>
              <dd>{won(est.firstPayment)}</dd>
            </div>
            {!deposit && (
              <div>
                <dt>매달 직접 넣을 돈</dt>
                <dd>
                  {won(est.firstPayment)} × {months}개월 (다음 달부터는 자동으로 빠지지 않아요)
                </dd>
              </div>
            )}
            <div>
              <dt>적용 금리</dt>
              <dd>연 {est.rate}% (가입 후 바뀌지 않아요)</dd>
            </div>
            <div>
              <dt>만기일</dt>
              <dd>{ymd(est.maturityDate)}</dd>
            </div>
            <div>
              <dt>예상 만기 금액</dt>
              <dd>
                {won(est.maturityAmount)} (세전 이자 {won(est.interest)}{deposit ? '' : ', 매달 같은 돈을 넣었을 때'})
              </dd>
            </div>
          </dl>
          {!p.earlyTerminationAllowed && (
            <p className="prod-warn" role="note">
              중도 해지할 수 없는 상품이에요.
            </p>
          )}
          <StepUpField auth={auth} id="sub-password" message={formError ? { tone: 'error', text: formError } : null} />
          <div className="prod-actions">
            <button className="btn-primary" type="submit" disabled={busy}>
              {busy ? '가입하는 중…' : `${won(est.firstPayment)} 내고 가입하기`}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setStep('form')
                setFormError(null)
              }}
              disabled={busy}
            >
              조건 바꾸기
            </button>
          </div>
        </form>
      )}
    </AppShell>
  )
}
