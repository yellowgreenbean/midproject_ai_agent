// 숨은 카드 포인트 조회·현금화 (docs/기획서.md Part 4 CARD-F12, 1-1-7)
// 카드사 포인트 전액을 내 정상 입출금 계좌로 입금한다(1포인트 = 1원, 본인 확인 POINT_CASHOUT) — 사용자 결정 2026-11-11
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { cashOutPoints, getAccounts, getCardPoints, type Account, type CardPoints } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { won } from '../productRules'
import { dots, md } from '../cardRules'
import './ProductPages.css'
import './AccountPages.css'
import './CardPages.css'

const point = (n: number) => `${n.toLocaleString('ko-KR')}P`
/** 2026-11-05T09:30:00+09:00 → 11.05 09:30 */
const when = (iso: string) => `${iso.slice(5, 7)}.${iso.slice(8, 10)} ${iso.slice(11, 16)}`

export default function CardPointsPage() {
  const [data, setData] = useState<CardPoints | 'guest' | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAccountId] = useState('')
  const [open, setOpen] = useState<string | null>(null) // 현금화 창을 연 포인트 id
  const auth = useStepUp()
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  function load() {
    void getCardPoints().then((r) => {
      if (r.success) return setData(r.data)
      if (r.error.code === 'UNAUTHENTICATED') return setData('guest')
      setError(r.error.message)
    })
  }
  useEffect(() => {
    load()
    // 입금 계좌: 내 정상 입출금 계좌만, 즐겨찾기 계좌를 위에 (기획서 1-1-7)
    void getAccounts().then((r) => {
      if (!r.success) return
      const usable = r.data.filter((a) => a.type === 'CHECKING' && a.status === 'ACTIVE').sort((a, b) => Number(b.isFavorite) - Number(a.isFavorite))
      setAccounts(usable)
      setAccountId(usable[0]?.id ?? '')
    })
  }, [])

  function toggle(id: string) {
    setOpen(open === id ? null : id)
    auth.setValue('')
    setFormError(null)
    setNotice(null)
  }

  async function onCashOut(e: FormEvent, pointId: string) {
    e.preventDefault()
    if (!accountId) return setFormError('입금할 계좌를 골라 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('POINT_CASHOUT')
    const r = ch.success ? await cashOutPoints(pointId, accountId, ch.data) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    setOpen(null)
    setNotice(`${r.data.pointName} ${point(r.data.amount)}를 ${won(r.data.amount)}으로 바꿔 ${r.data.accountNumber}에 넣었어요.`)
    load()
  }

  const loaded = data !== null && data !== 'guest' ? data : null
  const total = loaded?.points.reduce((n, p) => n + p.balance, 0) ?? 0

  return (
    <AppShell title="카드 포인트" current="#/cards" busy={!data && !error}>
      <section className="prod-head">
        <a className="more" href="#/cards">
          내 카드로
        </a>
        <h2 className="prod-title is-dup">숨은 카드 포인트</h2>
        <p className="prod-sub">카드사에 쌓인 포인트를 모아 보고, 1포인트를 1원으로 바꿔 내 계좌로 받을 수 있어요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="home-loading">불러오는 중…</p>}
      {data === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 내 카드 포인트가 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}

      {loaded && (
        <section className="panel acct-summary" aria-labelledby="point-total">
          <div>
            <p id="point-total" className="acct-summary-label">
              현금으로 바꿀 수 있는 포인트
            </p>
            <p className="acct-summary-amount">{point(total)}</p>
            <p className="acct-summary-split">
              <span>카드사 {loaded.points.length}곳</span>
              <span>바꾸면 {won(total)}</span>
            </p>
          </div>
        </section>
      )}

      {loaded &&
        (loaded.points.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">쌓인 카드 포인트가 없어요</p>
            <p className="empty-sub">카드를 쓰면 카드사 포인트가 여기에 모여요.</p>
          </div>
        ) : (
          <section aria-labelledby="point-list">
            <div className="section-head">
              <h2 id="point-list" className="section-title">
                <span className="section-icon">
                  <Icon name="coins" size={18} />
                </span>
                카드사별 포인트
              </h2>
            </div>
            <ul className="panel acct-menu">
              {loaded.points.map((p) => (
                <li key={p.id}>
                  <button type="button" aria-expanded={open === p.id} onClick={() => toggle(p.id)} disabled={p.balance === 0}>
                    <span className="acct-menu-label">
                      {p.pointName} <small className="prod-muted">{p.companyName}</small>
                    </span>
                    <span className="acct-menu-value">{point(p.balance)}</span>
                    <Icon name="chevron" size={18} />
                  </button>
                  {p.expiringAmount > 0 && p.expiringDate && (
                    <p className="acct-menu-form card-warn">
                      {point(Math.min(p.expiringAmount, p.balance))}가 {md(p.expiringDate)}에 사라져요. 그 전에 현금으로 바꿔 보세요.
                    </p>
                  )}
                  {open === p.id &&
                    (accounts.length === 0 ? (
                      <div className="acct-menu-form">
                        <p className="prod-sub">포인트를 받을 정상 입출금 계좌가 없어요.</p>
                        <a className="btn-pill" href="#/accounts/new">
                          <Icon name="plus" size={16} />새 입출금 계좌 만들기
                        </a>
                      </div>
                    ) : (
                      <form className="acct-menu-form prod-form" onSubmit={(e) => void onCashOut(e, p.id)} noValidate>
                        <p className="prod-sub">
                          {p.pointName} {point(p.balance)} 전부를 {won(p.balance)}으로 바꿔요. 일부만 바꿀 수는 없어요.
                        </p>
                        <Field id={`point-account-${p.id}`} label="입금 계좌 (내 정상 입출금 계좌만)">
                          <select id={`point-account-${p.id}`} className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                            {accounts.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.isFavorite ? '★ ' : ''}
                                {a.name} · {a.number}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <StepUpField auth={auth} id={`point-password-${p.id}`} message={formError ? { tone: 'error', text: formError } : null} />
                        <button className="btn-primary" type="submit" disabled={busy}>
                          {busy ? '바꾸는 중…' : `${won(p.balance)} 받기`}
                        </button>
                      </form>
                    ))}
                </li>
              ))}
            </ul>
          </section>
        ))}

      {loaded && loaded.cashouts.length > 0 && (
        <section aria-labelledby="point-history">
          <div className="section-head">
            <h2 id="point-history" className="section-title">
              <span className="section-icon">
                <Icon name="list" size={18} />
              </span>
              현금화 내역
            </h2>
          </div>
          <ul className="panel rows">
            {loaded.cashouts.map((c) => (
              <li key={c.id}>
                <a href={`#/accounts/${c.accountId}`}>
                  <span className="row-main">
                    <strong>{c.pointName} 현금화</strong>
                    <small>
                      {when(c.requestedAt)} · {c.accountNumber} 입금
                    </small>
                  </span>
                  <span className="card-bill-amount">
                    <strong>{won(c.amount)}</strong>
                    <small>{c.status === 'COMPLETED' ? '입금 완료' : c.status === 'FAILED' ? '실패' : '처리 중'}</small>
                  </span>
                  <Icon name="chevron" size={18} />
                </a>
              </li>
            ))}
          </ul>
          <p className="prod-muted">포인트는 {dots(loaded.points[0]?.syncedAt.slice(0, 10) ?? '')} 기준이에요.</p>
        </section>
      )}
    </AppShell>
  )
}
