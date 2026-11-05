// 내 계좌 (docs/기획서.md Part 2 ACCT-F02) — 은행 앱의 「전체 계좌」처럼 입출금 계좌와 예금·적금을 한 화면에 묶어 보여 준다.
// 해지한 계좌는 맨 아래에 접어 둔다.
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { getAccountTransactions, getAccounts, getMySubscriptions, type Account, type AccountTransaction, type Subscription } from '../api'
import { won, ymd } from '../productRules'
import { ACCOUNT_ART, ACCOUNT_STATUS_LABEL } from './accountArt'
import { PRODUCT_ART, TYPE_LABEL } from './productArt'
import depositArt from '../assets/acct-deposit.png'
import './ProductPages.css'
import './AccountPages.css'

// 계좌 하나 = 카드 한 장. 누르면 상세(입출금 내역), 오른쪽 「송금」은 정상 계좌에만. 카드 아래에 가장 최근 거래 한 줄
function Cards({ list, recent = {} }: { list: Account[]; recent?: Record<string, AccountTransaction | undefined> }) {
  return (
    <ul className="acct-cards">
      {list.map((a) => (
        <li key={a.id} className={`panel acct-card is-${a.status.toLowerCase()}`}>
          <a className="acct-card-link" href={`#/accounts/${a.id}`}>
            <img src={ACCOUNT_ART[a.type]} alt="" className="acct-card-art" />
            <span className="acct-card-main">
              <span className="acct-card-name">
                <span className="acct-card-title">{a.name}</span>
                {a.isFavorite && (
                  <span className="acct-star" role="img" aria-label="즐겨찾기">
                    <Icon name="star" size={14} />
                  </span>
                )}
                {a.status !== 'ACTIVE' && <span className="acct-badge">{ACCOUNT_STATUS_LABEL[a.status] ?? a.status}</span>}
              </span>
              <small>두린은행 {a.number}</small>
            </span>
            <strong className="acct-card-bal">{a.status === 'CLOSED' ? '해지' : won(a.balance)}</strong>
            {recent[a.id] && (
              <span className={`acct-card-recent is-${recent[a.id]!.direction.toLowerCase()}`}>
                <span>최근</span>
                <span className="acct-card-recent-name">{recent[a.id]!.displayName}</span>
                <strong>
                  {recent[a.id]!.direction === 'IN' ? '+' : '-'}
                  {won(recent[a.id]!.amount)}
                </strong>
                <span>{`${Number(recent[a.id]!.createdAt.slice(5, 7))}/${Number(recent[a.id]!.createdAt.slice(8, 10))}`}</span>
              </span>
            )}
          </a>
          {a.status === 'ACTIVE' ? (
            <a className="btn-pill acct-card-send" href={`#/transfer?from=${a.id}`} aria-label={`${a.name}에서 송금`}>
              송금
            </a>
          ) : (
            <span className="acct-card-send" /> // 송금 버튼 자리 — 잔액 줄을 다른 카드와 맞춘다
          )}
        </li>
      ))}
    </ul>
  )
}

/** 'YYYYMMDD…' → 날짜 */
const day = (s: string) => new Date(Number(s.slice(0, 4)), Number(s.slice(4, 6)) - 1, Number(s.slice(6, 8)))
/** 가입일 → 만기일 사이에서 오늘이 어디쯤인지 (0~100) — 화면 막대 표시용 */
function progress(s: Subscription) {
  const start = day(s.startDate).getTime()
  const end = day(s.maturityDate).getTime()
  return end > start ? Math.min(100, Math.max(0, Math.round(((Date.now() - start) / (end - start)) * 100))) : 100
}

function Savings({ list }: { list: Subscription[] }) {
  return (
    <ul className="acct-cards">
      {list.map((s) => (
        <li key={s.id} className="panel acct-card">
          <a className="acct-card-link" href={`#/my/savings/${s.id}`}>
            <img src={PRODUCT_ART[s.productType]} alt="" className="acct-card-art" />
            <span className="acct-card-main">
              <span className="acct-card-name">
                <span className="acct-card-title">{s.productName}</span>
              </span>
              <small>
                {TYPE_LABEL[s.productType]} · 연 {s.appliedRate}% · 만기 {ymd(s.maturityDate)}
              </small>
              <progress className="acct-progress" value={progress(s)} max={100} aria-label="만기까지 지난 기간" />
            </span>
            <strong className="acct-card-bal">{won(s.principal)}</strong>
          </a>
          <span className="acct-card-send" />
        </li>
      ))}
    </ul>
  )
}

export default function AccountsPage() {
  const [list, setList] = useState<Account[] | 'guest' | null>(null)
  const [subs, setSubs] = useState<Subscription[]>([])
  const [recent, setRecent] = useState<Record<string, AccountTransaction | undefined>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getAccounts().then((r) => {
      if (r.success) {
        setList(r.data)
        // 카드마다 가장 최근 거래 한 줄 — 계좌는 보통 두세 개라 하나씩 묻는다. 못 불러오면 그 줄만 안 보인다
        for (const a of r.data.filter((x) => x.status !== 'CLOSED'))
          void getAccountTransactions(a.id).then((t) => t.success && setRecent((m) => ({ ...m, [a.id]: t.data[0] })))
        return
      }
      if (r.error.code === 'UNAUTHENTICATED') return setList('guest')
      setError(r.error.message)
    })
    // 예금·적금은 곁들이는 정보 — 못 불러오면 그 구역만 「상품 보러 가기」 줄로 대신한다
    void getMySubscriptions().then((r) => r.success && setSubs(r.data.filter((s) => s.status === 'ACTIVE')))
  }, [])

  const open = Array.isArray(list) ? list.filter((a) => a.status !== 'CLOSED') : []
  const closed = Array.isArray(list) ? list.filter((a) => a.status === 'CLOSED') : []
  const cash = open.reduce((n, a) => n + a.balance, 0)
  const saved = subs.reduce((n, s) => n + s.principal, 0)

  return (
    <AppShell title="내 계좌" current="#/accounts" busy={!list && !error}>
      {Array.isArray(list) && open.length > 0 && (
        <section className="panel acct-summary" aria-labelledby="acct-total">
          <div>
            <p id="acct-total" className="acct-summary-label">
              총 자산
            </p>
            <p className="acct-summary-amount">{won(cash + saved)}</p>
            <p className="acct-summary-split">
              <span>입출금 {won(cash)}</span>
              <span>예금·적금 {won(saved)}</span>
            </p>
          </div>
          <div className="acct-summary-actions">
            <a className="btn-hero is-primary" href="#/transfer">
              <Icon name="send" size={18} />
              송금
            </a>
            <a className="btn-hero" href="#/accounts/new">
              <Icon name="plus" size={18} />
              계좌 개설
            </a>
          </div>
        </section>
      )}
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 내 계좌가 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(list) && (
        <section aria-labelledby="acct-cash">
          <div className="section-head">
            <h2 id="acct-cash" className="section-title">
              <span className="section-icon">
                <Icon name="wallet" size={18} />
              </span>
              입출금 <span className="acct-count">{open.length}</span>
            </h2>
          </div>
          {open.length === 0 ? (
            <div className="panel empty">
              <p className="empty-title">아직 계좌가 없어요</p>
              <p className="empty-sub">입출금 통장을 만들면 여기에서 잔액을 바로 볼 수 있어요.</p>
              <a className="btn-pill" href="#/accounts/new">
                <Icon name="plus" size={16} />첫 계좌 만들기
              </a>
            </div>
          ) : (
            <Cards list={open} recent={recent} />
          )}
        </section>
      )}
      {Array.isArray(list) && (
        <section aria-labelledby="acct-saved">
          <div className="section-head">
            <h2 id="acct-saved" className="section-title">
              <span className="section-icon">
                <Icon name="coins" size={18} />
              </span>
              예금·적금 <span className="acct-count">{subs.length}</span>
            </h2>
            {subs.length > 0 && (
              <a className="more" href="#/my/savings">
                전체 보기 <Icon name="chevron" size={14} />
              </a>
            )}
          </div>
          {subs.length > 0 && <Savings list={subs} />}
          <a className="panel acct-promo" href="#/products">
            <img src={depositArt} alt="" className="acct-promo-art" />
            <span className="acct-card-main">
              <strong>{subs.length > 0 ? '다른 예금·적금도 비교해 보세요' : '목돈은 예금·적금에 넣어 두세요'}</strong>
              <small>두린은행 예금·적금 금리 비교하기</small>
            </span>
            <Icon name="chevron" size={18} />
          </a>
        </section>
      )}
      {closed.length > 0 && (
        <details className="acct-closed">
          <summary>
            해지한 계좌 {closed.length}개 <Icon name="chevron" size={16} />
          </summary>
          <Cards list={closed} />
        </details>
      )}
    </AppShell>
  )
}
