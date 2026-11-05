// 내 카드 (docs/기획서.md Part 4 CARD-F01 모아보기 · CARD-F04 결제 예정 금액·결제 캘린더 · CARD-F05 신청·배송 조회)
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import CardApplications from './CardApplications'
import { getCardApplications, getCardBills, getMyCards, type Card, type CardApplication, type CardBill } from '../api'
import { won } from '../productRules'
import { BILL_STATUS_LABEL, CARD_STATUS_LABEL, CARD_TYPE_LABEL, groupByPaymentDate, md } from '../cardRules'
import { cardArtOf } from './cardArt'
import './ProductPages.css'
import './AccountPages.css'
import './CardPages.css'

/** 결제일까지 남은 날 — 'D-9', 오늘이면 'D-day' */
function dday(date: string) {
  const [y, m, d] = date.split('-').map(Number)
  const now = new Date()
  const days = Math.round((new Date(y, m - 1, d).getTime() - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) / 86400000)
  return days === 0 ? 'D-day' : days > 0 ? `D-${days}` : `${-days}일 지남`
}

function BillRows({ bills }: { bills: CardBill[] }) {
  return (
    <ul className="rows">
      {bills.map((b) => {
        const body = (
          <>
            <span className="row-main">
              <strong>{b.cardName}</strong>
              <small>
                {md(b.usageStart)}~{md(b.usageEnd)} 이용분 · {b.accountNumber ?? '결제 계좌 없음'}
              </small>
              {b.lowBalance && <small className="card-warn">결제 계좌 잔액이 모자라요</small>}
            </span>
            <span className="card-bill-amount">
              <strong>{won(b.totalAmount)}</strong>
              <small className={`card-bill-status is-${b.status.toLowerCase()}`}>{BILL_STATUS_LABEL[b.status]}</small>
            </span>
          </>
        )
        // 진행 중(SCHEDULED) 청구서는 아직 저장 전이라 상세가 없다 — 카드의 이용 내역으로 보낸다
        return (
          <li key={`${b.cardId}-${b.billingYm}`}>
            <a href={b.id ? `#/card-bills/${b.id}` : `#/cards/${b.cardId}`}>
              {body}
              <Icon name="chevron" size={18} />
            </a>
          </li>
        )
      })}
    </ul>
  )
}

export default function CardsPage() {
  const [cards, setCards] = useState<Card[] | 'guest' | null>(null)
  const [bills, setBills] = useState<CardBill[]>([])
  const [apps, setApps] = useState<CardApplication[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  function load() {
    void getMyCards().then((r) => {
      if (r.success) return setCards(r.data)
      if (r.error.code === 'UNAUTHENTICATED') return setCards('guest')
      setError(r.error.message)
    })
    // 청구서·신청은 곁들이는 정보 — 못 불러오면 그 구역만 빈다
    void getCardBills().then((r) => r.success && setBills(r.data))
    void getCardApplications().then((r) => r.success && setApps(r.data))
  }
  useEffect(load, [])

  function onAppChange(next: CardApplication) {
    setApps((list) => list.map((a) => (a.id === next.id ? next : a)))
    if (next.status !== 'ACTIVATED') return
    setNotice(`${next.productName}를 등록했어요. 아래 「내 카드」에서 바로 볼 수 있어요.`)
    load() // 새 카드가 목록에 들어온다
  }

  const { upcoming, past } = groupByPaymentDate(bills)
  const nextDue = upcoming.find((g) => g.due > 0)
  const working = apps.filter((a) => a.status !== 'ACTIVATED' && a.status !== 'CANCELED' && a.status !== 'REJECTED')

  return (
    <AppShell title="카드" current="#/cards" busy={!cards && !error}>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!cards && !error && <p className="home-loading">불러오는 중…</p>}
      {cards === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 내 카드가 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}

      {Array.isArray(cards) && (
        <section className="panel acct-summary" aria-labelledby="card-due">
          <div>
            <p id="card-due" className="acct-summary-label">
              {nextDue ? `${md(nextDue.date)} 결제 예정 · ${dday(nextDue.date)}` : '곧 낼 카드값'}
            </p>
            <p className="acct-summary-amount">{won(nextDue?.due ?? 0)}</p>
            <p className="acct-summary-split">
              <span>카드 {cards.length}장</span>
              {nextDue && <span>{nextDue.bills.filter((b) => b.totalAmount > 0).map((b) => b.cardName).join(' · ')}</span>}
            </p>
          </div>
          <div className="acct-summary-actions">
            <a className="btn-hero is-primary" href="#/cards/apply">
              <Icon name="plus" size={18} />
              카드 신청
            </a>
            {/* 캘린더는 이 화면 아래에 있다 — 주소(#)를 바꾸면 화면 이동이 되므로 스크롤만 한다 */}
            <button type="button" className="btn-hero acct-hero-btn" onClick={() => document.getElementById('card-calendar')?.scrollIntoView({ behavior: 'smooth' })}>
              <Icon name="list" size={18} />
              결제 캘린더
            </button>
          </div>
        </section>
      )}

      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}

      {working.length > 0 && (
        <section aria-labelledby="card-apps">
          <div className="section-head">
            <h2 id="card-apps" className="section-title">
              <span className="section-icon">
                <Icon name="send" size={18} />
              </span>
              신청한 카드 <span className="acct-count">{working.length}</span>
            </h2>
          </div>
          <CardApplications list={working} onChange={onAppChange} />
        </section>
      )}

      {Array.isArray(cards) && (
        <section aria-labelledby="card-mine">
          <div className="section-head">
            <h2 id="card-mine" className="section-title">
              <span className="section-icon">
                <Icon name="card" size={18} />
              </span>
              내 카드 <span className="acct-count">{cards.length}</span>
            </h2>
          </div>
          {cards.length === 0 ? (
            <div className="panel empty">
              <p className="empty-title">아직 카드가 없어요</p>
              <p className="empty-sub">체크카드를 만들면 쓴 돈이 바로 입출금 통장에서 빠져나가요.</p>
              <a className="btn-pill" href="#/cards/apply">
                <Icon name="plus" size={16} />
                체크카드 신청하기
              </a>
            </div>
          ) : (
            <ul className="acct-cards">
              {cards.map((c) => (
                <li key={c.id} className={`panel acct-card is-${c.status.toLowerCase()}`}>
                  <a className="acct-card-link card-row" href={`#/cards/${c.id}`}>
                    <img src={cardArtOf(c.productName, c.cardType)} alt="" className="card-row-art" />
                    <span className="acct-card-main">
                      <span className="acct-card-name">
                        <span className="acct-card-title">{c.name}</span>
                        {c.status !== 'ACTIVE' && <span className="acct-badge">{CARD_STATUS_LABEL[c.status] ?? c.status}</span>}
                      </span>
                      <small>
                        {CARD_TYPE_LABEL[c.cardType]} · 끝자리 {c.last4} · {c.linkedAccountName ?? '연결 계좌 없음'}
                      </small>
                    </span>
                    <span className="card-row-amount">
                      {c.unpaidAmount > 0 && c.nextPaymentDate ? (
                        <>
                          <strong>{won(c.unpaidAmount)}</strong>
                          <small>{md(c.nextPaymentDate)} 결제 예정</small>
                        </>
                      ) : (
                        <>
                          <strong>{won(c.periodSpent)}</strong>
                          <small>이번 달 쓴 돈</small>
                        </>
                      )}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {Array.isArray(cards) && (
        <section aria-labelledby="card-calendar-title" id="card-calendar">
          <div className="section-head">
            <h2 id="card-calendar-title" className="section-title">
              <span className="section-icon">
                <Icon name="coins" size={18} />
              </span>
              결제 캘린더
            </h2>
          </div>
          {upcoming.length === 0 ? (
            <p className="panel prod-pad prod-muted">결제할 카드값이 없어요. 체크카드는 쓸 때 바로 통장에서 빠져나가요.</p>
          ) : (
            <div className="card-calendar">
              {upcoming.map((g) => (
                <div key={g.date} className="panel card-day">
                  <h3 className="card-day-head">
                    <span>
                      {md(g.date)} <small>{dday(g.date)}</small>
                    </span>
                    <strong>{won(g.due)}</strong>
                  </h3>
                  <BillRows bills={g.bills} />
                </div>
              ))}
            </div>
          )}
          {past.length > 0 && (
            <details className="acct-closed">
              <summary>
                지난 결제 {past.length}건 <Icon name="chevron" size={16} />
              </summary>
              <div className="card-calendar">
                {past.map((g) => (
                  <div key={g.date} className="panel card-day">
                    <h3 className="card-day-head">
                      <span>{md(g.date)}</span>
                      <strong>{won(g.bills.reduce((n, b) => n + b.paidAmount, 0))}</strong>
                    </h3>
                    <BillRows bills={g.bills} />
                  </div>
                ))}
              </div>
            </details>
          )}
        </section>
      )}
    </AppShell>
  )
}
