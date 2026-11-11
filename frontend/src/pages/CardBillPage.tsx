// 카드 청구서 (docs/기획서.md Part 4 CARD-F04 1-1-4) — 이 달에 낼 돈과 그 안에 든 거래
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { getCardBill, type CardBillDetail } from '../api'
import { won } from '../productRules'
import { BILL_STATUS_LABEL, dots, md } from '../cardRules'
import './ProductPages.css'
import './AccountPages.css'
import './CardPages.css'

export default function CardBillPage({ id }: { id: string }) {
  const [b, setB] = useState<CardBillDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getCardBill(id).then((r) => (r.success ? setB(r.data) : setError(r.error.message)))
  }, [id])

  if (!b)
    return (
      <AppShell title="청구서" current="#/cards" busy={!error}>
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

  return (
    <AppShell title="청구서" current="#/cards">
      <a className="more prod-back" href={`#/cards/${b.cardId}`}>
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        {b.cardName}
      </a>

      <section className="panel acct-summary" aria-labelledby="bill-title">
        <div>
          <p id="bill-title" className="acct-summary-label">
            {b.cardName} · {Number(b.billingYm.slice(4))}월 청구서
          </p>
          <p className="acct-summary-amount">{won(b.totalAmount)}</p>
          <p className="acct-summary-split">
            <span className={`card-bill-status is-${b.status.toLowerCase()}`}>{BILL_STATUS_LABEL[b.status]}</span>
            <span>
              {md(b.paymentDate)} {b.status === 'PAID' ? '결제함' : '결제'} · {b.accountNumber ?? '결제 계좌 없음'}
            </span>
          </p>
        </div>
      </section>
      {b.lowBalance && (
        <p className="prod-warn">
          결제 계좌 잔액이 {won(b.shortfall)} 모자라요. 결제일 전에 채워 두세요.{' '}
          {b.accountId && (
            <a
              className="more"
              href={`#/transfer?${new URLSearchParams({ toAccount: b.accountId, amount: String(b.shortfall), at: new Date(Date.parse(`${b.paymentDate}T18:00:00+09:00`) - 86_400_000).toISOString() })}`}
            >
              채우기 송금 <Icon name="chevron" size={14} />
            </a>
          )}
        </p>
      )}

      <dl className="panel prod-info">
        <div>
          <dt>이용 기간</dt>
          <dd>
            {dots(b.usageStart)} ~ {dots(b.usageEnd)}
          </dd>
        </div>
        <div>
          <dt>결제일</dt>
          <dd>{dots(b.paymentDate)}</dd>
        </div>
        <div>
          <dt>낸 돈</dt>
          <dd>{won(b.paidAmount)}</dd>
        </div>
        <div>
          <dt>거래</dt>
          <dd>{b.items.length}건 (취소한 거래는 빠져요)</dd>
        </div>
      </dl>

      <section aria-labelledby="bill-items">
        <h2 id="bill-items" className="section-title">
          <span className="section-icon">
            <Icon name="list" size={18} />
          </span>
          청구 내역
        </h2>
        <ul className="panel rows">
          {b.items.map((i) => (
            <li key={i.transaction.id} className="card-bill-item">
              <span className="row-main">
                <strong>{i.transaction.merchant}</strong>
                <small>
                  {md(i.transaction.transactedAt)} · {i.transaction.category} · {i.transaction.installmentMonths > 1 ? `할부 ${i.installmentSeq}/${i.transaction.installmentMonths}회차` : '일시불'}
                </small>
              </span>
              <strong>{won(i.principalAmount)}</strong>
            </li>
          ))}
        </ul>
      </section>
    </AppShell>
  )
}
