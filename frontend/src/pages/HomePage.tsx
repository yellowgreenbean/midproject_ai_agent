// 홈 (docs/design/main-home.webp 시안 · 계좌 통합 대시보드 ACCT-F08)
// 로그인 전에도 보인다 — 그때는 공개 정보(추천 상품)만 부르고, 계좌·카드는 로그인한 본인 것만 부른다
import { useEffect, useState } from 'react'
import Icon, { type IconName } from '../components/Icon'
import SessionBadge from '../components/SessionBadge'
import {
  getAccountDashboard,
  getMe,
  getMyCards,
  getRecommendedProducts,
  logout,
  NOT_IMPLEMENTED,
  type ApiResult,
  type Account,
  type Card,
  type Product,
  type SessionUser,
} from '../api'
import logoMark from '../assets/logo-mark.png'
import cardArt from '../assets/card-durin.png'
import { cardArtOf } from './cardArt'
import { md } from '../cardRules'
import acctChecking from '../assets/acct-checking.png'
import acctSavings from '../assets/acct-savings.png'
import acctDeposit from '../assets/acct-deposit.png'
import acctInstallment from '../assets/acct-installment.png'
import greetHand from '../assets/greet-hand.png'
import ChatWidget from './ChatWidget'
import './HomePage.css'
import './CardPages.css'

// 계좌 유형 · 상품 아이콘 → 3D 그림
const ACCOUNT_ART: Record<string, string> = { CHECKING: acctChecking, SAVINGS: acctSavings }
const PRODUCT_ART: Record<Product['icon'], string> = { safe: acctDeposit, coins: acctInstallment }
const PRODUCT_KIND: Record<Product['icon'], string> = { safe: '정기예금', coins: '적금' }

type NavItem = { href: string; label: string; icon: IconName; mobile?: boolean }
const NAV: NavItem[] = [
  { href: '#/home', label: '홈', icon: 'home', mobile: true },
  { href: '#/accounts', label: '내 계좌', icon: 'wallet', mobile: true },
  { href: '#/cards', label: '카드', icon: 'card', mobile: true },
  { href: '#/products', label: '금융상품', icon: 'layers', mobile: true },
  { href: '#/notifications', label: '알림', icon: 'bell' }, // 모바일: 위쪽 종 아이콘
  { href: '#/settings', label: '마이페이지', icon: 'user' }, // 모바일: 위쪽 사람 아이콘
]
const won = (n: number) => `${n.toLocaleString('ko-KR')}원`

type Home = { me: SessionUser | null; total: number; accounts: Account[]; cards: Card[]; products: Product[] }

/** 서버에 아직 없는 기능(NOT_IMPLEMENTED)이면 빈 목록으로 */
const orEmpty = <T,>(r: ApiResult<T[]>): ApiResult<T[]> => (!r.success && r.error.code === NOT_IMPLEMENTED ? { success: true, data: [] } : r)

export default function HomePage() {
  const [home, setHome] = useState<Home | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      const [me, prodsRes] = await Promise.all([getMe(), getRecommendedProducts()])
      // 서버(backend/)에 아직 없는 기능(추천 상품·카드)은 빈 목록으로 두고 나머지를 보여 준다 — 다른 오류는 그대로 알린다
      const prods = orEmpty(prodsRes)
      if (!prods.success) return setError(prods.error.message)
      if (!me.success) return setHome({ me: null, total: 0, accounts: [], cards: [], products: prods.data })
      const [dash, cardsRes] = await Promise.all([getAccountDashboard(), getMyCards()])
      const cards = orEmpty(cardsRes)
      if (!dash.success) return setError(dash.error.message)
      if (!cards.success) return setError(cards.error.message)
      setHome({ me: me.data, total: dash.data.totalBalance, accounts: dash.data.accounts, cards: cards.data, products: prods.data })
    })()
  }, [])
  const guest = home !== null && home.me === null

  async function onLogout() {
    const r = await logout()
    if (!r.success) return setError(r.error.message)
    location.hash = '#/login' // 로그아웃 → 로그인 화면 (AUTH-F05)
  }

  return (
    <div className="home">
      <aside className="sidebar">
        <a className="sidebar-brand" href="#/home">
          <img src={logoMark} alt="" width={34} height={34} />
          Durin Bank
        </a>
        <nav aria-label="주 메뉴">
          <ul className="nav">
            {NAV.map((n) => (
              <li key={n.href}>
                <a href={n.href} aria-current={n.href === '#/home' ? 'page' : undefined}>
                  <Icon name={n.icon} />
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="home-body">
        <header className="topbar">
          <a className="topbar-brand" href="#/home">
            <img src={logoMark} alt="" width={28} height={28} />
            Durin Bank
          </a>
          <h1 className="topbar-title">홈</h1>
          <a className="search" href="#/search">
            <Icon name="search" size={20} />
            <span>계좌, 거래내역, 상품 등을 검색해보세요</span>
          </a>
          <SessionBadge />
          <a className="icon-btn" href="#/notifications" aria-label="알림">
            <Icon name="bell" />
          </a>
          <a className="icon-btn" href={guest ? '#/login' : '#/settings'} aria-label={guest ? '로그인' : '마이페이지'}>
            <Icon name="user" />
          </a>
          {home?.me && (
            <button type="button" className="text-btn" onClick={onLogout}>
              로그아웃
            </button>
          )}
        </header>

        <main className="home-main" aria-busy={!home && !error}>
          {error && (
            <p className="home-error" role="alert">
              {error}
            </p>
          )}
          {!home && !error && <p className="home-loading">불러오는 중…</p>}
          {home && (
            <>
              <section className="hero" aria-labelledby="hello">
                <div className="hero-text">
                  {home.me ? (
                    <>
                      <h2 id="hello">
                        {home.me.name}님, 좋은 하루예요 <img src={greetHand} alt="" className="hello-icon" />
                      </h2>
                      <p className="hero-sub">오늘도 두린뱅크와 함께, 더 나은 금융 생활을 시작해요.</p>
                      <p className="hero-label">총 자산</p>
                      <p className="hero-amount">{won(home.total)}</p>
                    </>
                  ) : (
                    <>
                      <h2 id="hello">
                        두린뱅크에 오신 걸 환영해요 <img src={greetHand} alt="" className="hello-icon" />
                      </h2>
                      <p className="hero-sub">로그인하면 계좌·카드·송금을 한곳에서 관리할 수 있어요.</p>
                    </>
                  )}
                </div>
                <div className="hero-actions">
                  {home.me ? (
                    <a className="btn-hero is-primary" href="#/transfer">
                      <Icon name="send" />
                      송금
                    </a>
                  ) : (
                    <a className="btn-hero is-primary" href="#/login">
                      <Icon name="user" />
                      로그인
                    </a>
                  )}
                  {home.me ? (
                    <a className="btn-hero" href="#/products">
                      <Icon name="layers" />
                      상품 둘러보기
                    </a>
                  ) : (
                    <a className="btn-hero" href="#/signup">
                      <Icon name="plus" />
                      회원가입
                    </a>
                  )}
                </div>
              </section>


              <div className="two-col">
                <section aria-labelledby="my-accounts">
                  <div className="section-head">
                    <h2 id="my-accounts" className="section-title">
                      <span className="section-icon">
                        <Icon name="wallet" size={18} />
                      </span>
                      내 계좌
                    </h2>
                    <a className="more" href="#/accounts">
                      전체 계좌 보기 <Icon name="chevron" size={14} />
                    </a>
                  </div>
                  <div className="panel">
                    {home.accounts.length === 0 ? (
                      <div className="empty">
                        <span className="empty-icon">
                          <Icon name="wallet" size={28} />
                        </span>
                        <p className="empty-title">{guest ? '로그인하면 내 계좌가 여기에 보여요' : '아직 계좌가 없어요'}</p>
                        <p className="empty-sub">입출금 통장을 만들면 여기에서 잔액을 바로 볼 수 있어요.</p>
                        <a className="btn-pill" href={guest ? '#/login' : '#/accounts/new'}>
                          <Icon name="plus" size={16} />
                          {guest ? '로그인하기' : '첫 계좌 만들기'}
                        </a>
                      </div>
                    ) : (
                      (() => {
                        // 대표 계좌 하나만 — 즐겨찾기한 계좌, 없으면 정상 계좌 중 첫 번째
                        const main = home.accounts.find((a) => a.isFavorite) ?? home.accounts.find((a) => a.status === 'ACTIVE') ?? home.accounts[0]
                        const others = home.accounts.length - 1
                        return (
                          <div className="main-acct">
                            <a className="main-acct-link" href={`#/accounts/${main.id}`}>
                              <img src={ACCOUNT_ART[main.type] ?? acctChecking} alt="" className="main-acct-art" />
                              <span className="main-acct-text">
                                <span className="main-acct-tag">대표 계좌{main.status === 'SUSPENDED' && ' · 일시정지'}</span>
                                <strong>{main.name}</strong>
                                <small>두린은행 {main.number}</small>
                              </span>
                            </a>
                            <p className="main-acct-bal">{won(main.balance)}</p>
                            <div className="main-acct-actions">
                              {main.status === 'ACTIVE' && (
                                <a className="btn-pill" href="#/transfer">
                                  <Icon name="send" size={16} />
                                  송금
                                </a>
                              )}
                              <a className="btn-pill is-plain" href={`#/accounts/${main.id}`}>
                                <Icon name="list" size={16} />
                                입출금 내역
                              </a>
                            </div>
                            {others > 0 && (
                              <a className="main-acct-more" href="#/accounts">
                                다른 계좌 {others}개 보기 <Icon name="chevron" size={14} />
                              </a>
                            )}
                          </div>
                        )
                      })()
                    )}
                  </div>
                </section>

                <section aria-labelledby="my-cards">
                  <div className="section-head">
                    <h2 id="my-cards" className="section-title">
                      <span className="section-icon">
                        <Icon name="card" size={18} />
                      </span>
                      카드 · 이용금액
                    </h2>
                  </div>
                  <div className="panel">
                    {home.cards.length === 0 ? (
                      <div className="empty empty-card">
                        <img src={cardArt} alt="" className="card-art" />
                        <div>
                          <p className="empty-title">{guest ? '로그인하면 내 카드가 여기에 보여요' : '아직 카드가 없어요'}</p>
                          <p className="empty-sub">체크카드를 만들면 이번 달 사용금액을 여기서 볼 수 있어요.</p>
                          <a className="btn-pill" href={guest ? '#/login' : '#/cards/apply'}>
                            {guest ? '로그인하기' : '카드 신청하기'} <Icon name="chevron" size={16} />
                          </a>
                        </div>
                      </div>
                    ) : (
                      <ul className="rows">
                        {home.cards.map((c) => (
                          <li key={c.id}>
                            <a href={`#/cards/${c.id}`}>
                              <img src={cardArtOf(c.productName, c.cardType)} alt="" className="card-thumb" />
                              <span className="row-main">
                                <strong>{c.name}</strong>
                                <small>
                                  {c.cardType === 'CREDIT' ? '신용' : '체크'} · {c.number}
                                </small>
                              </span>
                              {/* 신용카드는 낼 돈(확정 청구서), 없으면 이번 이용 기간에 쓴 돈 */}
                              <span className="card-bill-amount">
                                <strong>{won(c.unpaidAmount > 0 ? c.unpaidAmount : c.periodSpent)}</strong>
                                <small className="row-sub">{c.unpaidAmount > 0 && c.nextPaymentDate ? `${md(c.nextPaymentDate)} 결제` : '이번 달'}</small>
                              </span>
                              <Icon name="chevron" size={18} />
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </section>
              </div>

              <section aria-labelledby="reco">
                <div className="section-head">
                  <h2 id="reco" className="section-title">
                    <span className="section-icon">
                      <Icon name="layers" size={18} />
                    </span>
                    추천 예금·적금
                  </h2>
                  <a className="more" href="#/products">
                    전체 상품 보기 <Icon name="chevron" size={14} />
                  </a>
                </div>
                <ul className="products">
                  {home.products.map((p) => (
                    <li key={p.id}>
                      <a href={`#/products/${p.id}`} className={`panel product-card ${p.icon === 'safe' ? 'is-deposit' : 'is-installment'}`}>
                        <span className="pc-top">
                          <img src={PRODUCT_ART[p.icon]} alt="" className="pc-art" />
                          <span className="pc-tag">{PRODUCT_KIND[p.icon]}</span>
                        </span>
                        <strong className="pc-name">{p.name}</strong>
                        <span className="pc-desc">{p.description}</span>
                        <span className="pc-rate">
                          <small>최고</small> 연 {p.maxRate}%
                        </span>
                        <span className="pc-foot">
                          <span>{p.termLabel}</span>
                          <span className="pc-cta">
                            자세히 보기 <Icon name="chevron" size={14} />
                          </span>
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
        </main>
      </div>

      <ChatWidget />

      <nav className="tabbar" aria-label="아래 메뉴">
        {NAV.filter((n) => n.mobile).map((n) => (
          <a key={n.href} href={n.href} aria-current={n.href === '#/home' ? 'page' : undefined}>
            <Icon name={n.icon} />
            {n.label}
          </a>
        ))}
      </nav>
    </div>
  )
}
