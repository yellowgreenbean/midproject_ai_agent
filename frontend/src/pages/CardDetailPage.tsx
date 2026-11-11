// 카드 상세 (docs/기획서.md Part 4 CARD-F02 상세 · F03 이용 내역 · F04 청구서 · F08 결제 계좌 바꾸기 · F09 해지)
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import CardTransactions from './CardTransactions'
import {
  changeCardAccount,
  getAccounts,
  getCard,
  getTerminationCheck,
  payCard,
  terminateCard,
  type Account,
  type CardDetail,
  type TerminationCheck,
  type TerminationReason,
} from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { won } from '../productRules'
import { BILL_STATUS_LABEL, CARD_STATUS_LABEL, CARD_TYPE_LABEL, dots, expiry, md, performanceText } from '../cardRules'
import { cardArtOf } from './cardArt'
import './ProductPages.css'
import './AccountPages.css'
import './CardPages.css'

const REASONS: { value: TerminationReason; label: string }[] = [
  { value: 'NOT_USING', label: '잘 안 써요' },
  { value: 'LOW_BENEFIT', label: '혜택이 적어요' },
  { value: 'HIGH_FEE', label: '연회비가 부담돼요' },
  { value: 'OTHER', label: '기타' },
]

type Op = 'account' | 'terminate' | 'pay'

export default function CardDetailPage({ id }: { id: string }) {
  const [c, setC] = useState<CardDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [op, setOp] = useState<Op | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState('')
  const [check, setCheck] = useState<TerminationCheck | null>(null)
  const [reason, setReason] = useState<TerminationReason>('NOT_USING')
  const [detail, setDetail] = useState('')
  const auth = useStepUp()
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    void getCard(id).then((r) => (r.success ? setC(r.data) : setError(r.error.message)))
  }, [id])

  if (!c)
    return (
      <AppShell title="카드 상세" current="#/cards" busy={!error}>
        {error ? (
          <div className="panel empty">
            <p className="empty-title">{error}</p>
            <a className="btn-pill" href={error.includes('로그인') ? '#/login' : '#/cards'}>
              {error.includes('로그인') ? '로그인하기' : '내 카드로'}
            </a>
          </div>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )

  const ended = c.status === 'TERMINATED'
  // 지금 낼 수 있는 대금 — 확정·연체 청구서, 해지한 카드면 이번 기간 사용액까지 (서버 POST /cards/{id}/payments 와 같은 계산)
  const payAmount = c.cardType === 'CREDIT' ? c.unpaidAmount + (ended ? c.periodSpent : 0) : 0
  // 옮길 수 있는 계좌 = 내 정상 입출금 계좌 중 지금 계좌가 아닌 것 (서버도 같은 검사를 한다)
  const choices = accounts.filter((a) => a.type === 'CHECKING' && a.status === 'ACTIVE' && a.id !== c.linkedAccountId)

  function start(next: Op | null) {
    setOp(next)
    auth.setValue('')
    setFormError(null)
    setNotice(null)
    if (next === 'account')
      void getAccounts().then((r) => {
        if (!r.success) return setFormError(r.error.message)
        setAccounts(r.data)
        setAccountId(r.data.find((a) => a.type === 'CHECKING' && a.status === 'ACTIVE' && a.id !== c?.linkedAccountId)?.id ?? '')
      })
    if (next === 'terminate') {
      setCheck(null)
      void getTerminationCheck(id).then((r) => (r.success ? setCheck(r.data) : setFormError(r.error.message)))
    }
  }

  async function onAccount(e: FormEvent) {
    e.preventDefault()
    if (!accountId) return setFormError('옮길 계좌를 골라 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('CARD_MANAGEMENT')
    const r = ch.success ? await changeCardAccount(id, accountId, ch.data) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    setC(r.data)
    setOp(null)
    setNotice(`결제 계좌를 ${r.data.linkedAccountName}(${r.data.linkedAccountNumber})로 바꿨어요.`)
  }

  async function onPay(e: FormEvent) {
    e.preventDefault()
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('CARD_MANAGEMENT')
    const r = ch.success ? await payCard(id, ch.data) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    setC(r.data)
    setOp(null)
    setNotice(`카드 대금 ${won(payAmount)}을 ${r.data.linkedAccountNumber ?? '결제 계좌'}에서 냈어요.`)
  }

  async function onTerminate(e: FormEvent) {
    e.preventDefault()
    if (reason === 'OTHER' && !detail.trim()) return setFormError('해지 이유를 적어 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('CARD_TERMINATION')
    const r = ch.success ? await terminateCard(id, reason, detail.trim(), ch.data) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    const next = await getCard(id)
    if (next.success) setC(next.data)
    setOp(null)
    setNotice(r.data.periodSpent > 0 ? `카드를 해지했어요. 이번 기간에 쓴 ${won(r.data.periodSpent)}은 결제일에 청구돼요.` : '카드를 해지했어요.')
  }

  return (
    <AppShell title="카드 상세" current="#/cards">
      <a className="more prod-back" href="#/cards">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        내 카드
      </a>

      <section className={`panel acct-hero card-hero is-${c.cardType.toLowerCase()}`} aria-labelledby="card-name">
        <img src={cardArtOf(c.productName, c.cardType)} alt="" className="card-hero-art" />
        <div className="acct-hero-text">
          <span className="acct-hero-tags">
            <span className="pc-tag">{CARD_TYPE_LABEL[c.cardType]}카드</span>
            {c.status !== 'ACTIVE' && <span className="acct-badge">{CARD_STATUS_LABEL[c.status] ?? c.status}</span>}
          </span>
          <h2 id="card-name">{c.name}</h2>
          <p className="prod-sub">
            {c.companyName} · {c.number}
            {c.expiresAt && ` · 유효기간 ${expiry(c.expiresAt)}`}
          </p>
        </div>
        <div className="acct-hero-bal">
          {c.creditLimit !== null && c.availableLimit !== null ? (
            <>
              <strong className="acct-balance">{won(c.availableLimit)}</strong>
              <p className="prod-hero-base">
                쓸 수 있는 한도 · 전체 {won(c.creditLimit)} 중 {won(c.usedAmount ?? 0)} 사용 중
              </p>
            </>
          ) : (
            <>
              <strong className="acct-balance">{won(c.periodSpent)}</strong>
              <p className="prod-hero-base">이번 달 쓴 돈 · 쓸 때 바로 통장에서 빠져나가요</p>
            </>
          )}
        </div>
      </section>

      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}
      {ended && <p className="prod-warn">해지한 카드예요. 기록만 볼 수 있어요.</p>}
      {c.unpaidAmount > 0 && c.nextPaymentDate && (
        <p className="prod-ok">
          {md(c.nextPaymentDate)}에 {won(c.unpaidAmount)}이 {c.linkedAccountNumber ?? '결제 계좌'}에서 빠져나가요.
        </p>
      )}

      <div className="acct-body">
        <CardTransactions id={id} />
        <div className="acct-side">
          {c.bills.length > 0 && (
            <section aria-labelledby="card-bills">
              <h2 id="card-bills" className="section-title">
                <span className="section-icon">
                  <Icon name="coins" size={18} />
                </span>
                청구서
              </h2>
              <ul className="panel rows">
                {c.bills.map((b) => (
                  <li key={b.billingYm}>
                    <a href={b.id ? `#/card-bills/${b.id}` : '#/cards/' + c.id}>
                      <span className="row-main">
                        <strong>{Number(b.billingYm.slice(4))}월 청구서</strong>
                        <small>
                          {md(b.paymentDate)} 결제 · {md(b.usageStart)}~{md(b.usageEnd)} 이용분
                        </small>
                      </span>
                      <span className="card-bill-amount">
                        <strong>{won(b.totalAmount)}</strong>
                        <small className={`card-bill-status is-${b.status.toLowerCase()}`}>{BILL_STATUS_LABEL[b.status]}</small>
                      </span>
                      {b.id && <Icon name="chevron" size={18} />}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-labelledby="card-info">
            <h2 id="card-info" className="section-title">
              <span className="section-icon">
                <Icon name="card" size={18} />
              </span>
              카드 정보
            </h2>
            <dl className="panel prod-info">
              <div>
                <dt>{c.cardType === 'CREDIT' ? '결제 계좌' : '출금 계좌'}</dt>
                <dd>{c.linkedAccountNumber ? `${c.linkedAccountName} · 두린은행 ${c.linkedAccountNumber}` : '없음'}</dd>
              </div>
              {c.paymentDay !== null && (
                <div>
                  <dt>결제일</dt>
                  <dd>
                    매월 {c.paymentDay}일 · 지금은 {md(c.periodStart)}~{md(c.periodEnd)} 이용분을 모으는 중
                  </dd>
                </div>
              )}
              <div>
                <dt>발급일</dt>
                <dd>{dots(c.issuedAt)}</dd>
              </div>
              <div>
                <dt>유효기간</dt>
                <dd>{c.expiresAt ? expiry(c.expiresAt) : '정보 없음'}</dd>
              </div>
              <div>
                <dt>연회비</dt>
                <dd>{c.annualFee > 0 ? `${won(c.annualFee)}${c.nextAnnualFeeDate ? ` · 다음 청구 ${dots(c.nextAnnualFeeDate)}` : ''}` : '없음'}</dd>
              </div>
            </dl>
          </section>

          {c.benefits.length > 0 && (
            <section aria-labelledby="card-benefits">
              <h2 id="card-benefits" className="section-title">
                <span className="section-icon">
                  <Icon name="star" size={18} />
                </span>
                혜택
              </h2>
              {c.performance.map((p) => (
                <p key={p.period} className={p.tierLevel === null ? 'prod-warn' : 'prod-ok'}>
                  {performanceText(p)}
                </p>
              ))}
              <ul className="panel rows card-benefits">
                {c.benefits.map((b) => (
                  <li key={b.id} className={b.achieved ? undefined : 'is-locked'}>
                    <span className="row-main">
                      <strong>
                        {b.title}
                        {!b.achieved && <span className="acct-badge">실적 미달</span>}
                      </strong>
                      {b.conditions.length > 0 && <small>{b.conditions.join(' · ')}</small>}
                      {(b.monthlyLimit !== null || b.limitGroup) && (
                        <small>
                          {[b.monthlyLimit !== null && `한 달 ${won(b.monthlyLimit)}까지`, b.limitGroup && `${b.limitGroup.name} 한 달 ${won(b.limitGroup.monthlyLimit)}까지`]
                            .filter(Boolean)
                            .join(' · ')}
                        </small>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {payAmount > 0 && (
            <section aria-labelledby="card-pay" className="prod-manage">
              <h2 id="card-pay" className="section-title">
                <span className="section-icon">
                  <Icon name="coins" size={18} />
                </span>
                카드 대금
              </h2>
              <ul className="panel acct-menu">
                <li>
                  <button type="button" aria-expanded={op === 'pay'} onClick={() => start(op === 'pay' ? null : 'pay')}>
                    <span className="acct-menu-label">지금 결제하기</span>
                    <span className="acct-menu-value">{won(payAmount)}</span>
                    <Icon name="chevron" size={18} />
                  </button>
                  {op === 'pay' && (
                    <form className="acct-menu-form prod-form" onSubmit={onPay} noValidate>
                      <p className="prod-sub">
                        {c.linkedAccountName} {c.linkedAccountNumber}에서 {won(payAmount)}이 빠져나가요. 잔액이 모자라면 한 푼도 빠지지 않아요.
                      </p>
                      <StepUpField auth={auth} id="card-pay-password" message={formError ? { tone: 'error', text: formError } : null} />
                      <button className="btn-primary" type="submit" disabled={busy}>
                        {busy ? '내는 중…' : `${won(payAmount)} 내기`}
                      </button>
                    </form>
                  )}
                </li>
              </ul>
            </section>
          )}

          {!ended && (
            <section aria-labelledby="card-manage" className="prod-manage">
              <h2 id="card-manage" className="section-title">
                <span className="section-icon">
                  <Icon name="settings" size={18} />
                </span>
                카드 관리
              </h2>
              <ul className="panel acct-menu">
                <li>
                  <button type="button" aria-expanded={op === 'account'} onClick={() => start(op === 'account' ? null : 'account')}>
                    <span className="acct-menu-label">{c.cardType === 'CREDIT' ? '결제 계좌 바꾸기' : '출금 계좌 바꾸기'}</span>
                    <span className="acct-menu-value">{c.linkedAccountName}</span>
                    <Icon name="chevron" size={18} />
                  </button>
                  {op === 'account' &&
                    (c.paymentDayLocked ? (
                      <p className="acct-menu-form prod-warn" role="alert">
                        오늘은 이 카드의 결제일이라 결제 계좌를 바꿀 수 없어요. 내일 다시 시도해 주세요.
                      </p>
                    ) : accounts.length > 0 && choices.length === 0 ? (
                      <div className="acct-menu-form">
                        <p className="prod-sub">옮길 수 있는 다른 입출금 계좌가 없어요.</p>
                        <a className="btn-pill" href="#/accounts/new">
                          <Icon name="plus" size={16} />새 입출금 계좌 만들기
                        </a>
                      </div>
                    ) : (
                      <form className="acct-menu-form prod-form" onSubmit={onAccount} noValidate>
                        <Field id="card-account" label="새 계좌 (내 정상 입출금 계좌만)">
                          <select id="card-account" className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                            {choices.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name} · {a.number}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <StepUpField auth={auth} id="card-password" message={formError ? { tone: 'error', text: formError } : null} />
                        <button className="btn-primary" type="submit" disabled={busy}>
                          {busy ? '바꾸는 중…' : '이 계좌로 바꾸기'}
                        </button>
                      </form>
                    ))}
                </li>
                <li>
                  <button type="button" className="is-danger" aria-expanded={op === 'terminate'} onClick={() => start(op === 'terminate' ? null : 'terminate')}>
                    <span className="acct-menu-label">카드 해지</span>
                    <Icon name="chevron" size={18} />
                  </button>
                  {op === 'terminate' && !check && !formError && <p className="acct-menu-form prod-muted">확인하는 중…</p>}
                  {op === 'terminate' && check && !check.canTerminate && (
                    <div className="acct-menu-form" role="alert">
                      <p className="empty-title">지금은 해지할 수 없어요</p>
                      <ul className="acct-blockers">
                        <li>
                          아직 내지 않은 카드 대금 {won(check.unpaidAmount)}이 있어요. 위의 「지금 결제하기」로 먼저 낸 뒤 해지할 수 있어요.
                        </li>
                      </ul>
                    </div>
                  )}
                  {op === 'terminate' && check?.canTerminate && (
                    <form className="acct-menu-form prod-form" onSubmit={onTerminate} noValidate>
                      <ul className="acct-blockers" aria-label="해지 전에 알아 두세요">
                        <li>해지하면 다시 쓸 수 없어요. 이용 내역과 청구서는 남아요.</li>
                        {check.periodSpent > 0 && (
                          <li>
                            이번 기간에 쓴 {won(check.periodSpent)}은 해지 뒤에도 {check.nextPaymentDate ? md(check.nextPaymentDate) : '결제일'}에 청구돼요.
                          </li>
                        )}
                        {check.remainingInstallmentAmount > 0 && <li>남은 할부 {won(check.remainingInstallmentAmount)}도 계속 청구돼요.</li>}
                        {check.recurringMerchants.length > 0 && <li>이 카드로 내던 자동결제({check.recurringMerchants.join(', ')})가 끊겨요.</li>}
                        {check.forfeitedPoints > 0 && <li>포인트 {check.forfeitedPoints.toLocaleString('ko-KR')}점이 사라져요.</li>}
                        {check.refundedAnnualFee > 0 && <li>연회비 중 남은 기간 몫 {won(check.refundedAnnualFee)}을 돌려받아요.</li>}
                      </ul>
                      <fieldset className="card-reasons">
                        <legend className="field-label">해지하는 이유</legend>
                        {REASONS.map((r) => (
                          <label key={r.value} className="check">
                            <input type="radio" name="reason" value={r.value} checked={reason === r.value} onChange={() => setReason(r.value)} />
                            <span>{r.label}</span>
                          </label>
                        ))}
                      </fieldset>
                      {reason === 'OTHER' && (
                        <Field id="card-reason" label="이유 (100자까지)">
                          <input id="card-reason" className="input" maxLength={100} value={detail} onChange={(e) => setDetail(e.target.value)} />
                        </Field>
                      )}
                      <StepUpField auth={auth} id="card-password" message={formError ? { tone: 'error', text: formError } : null} />
                      <button className="btn-primary is-danger" type="submit" disabled={busy}>
                        {busy ? '해지하는 중…' : '카드 해지하기'}
                      </button>
                    </form>
                  )}
                  {op === 'terminate' && !check && formError && (
                    <p className="acct-menu-form field-msg is-error" role="alert">
                      {formError}
                    </p>
                  )}
                </li>
              </ul>
              {c.cardType === 'CREDIT' && <p className="prod-fine">분실·정지 신고, 이용 한도 바꾸기는 다음 단계에서 열려요.</p>}
            </section>
          )}
        </div>
      </div>
    </AppShell>
  )
}
