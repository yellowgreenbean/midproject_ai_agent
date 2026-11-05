// 앱 틀 — 왼쪽 메뉴(1024px 이상) · 위 헤더 · 아래 탭바(모바일) · 챗봇 버튼. 모양은 HomePage.css 의 홈 틀을 그대로 쓴다.
// shortcut: 홈(HomePage.tsx)은 아직 같은 틀을 자기 안에 따로 갖고 있다. 홈을 고칠 차례가 오면 이 부품으로 바꾼다.
import { useEffect, useState, type ReactNode } from 'react'
import Icon, { type IconName } from './Icon'
import SessionBadge from './SessionBadge'
import ChatWidget from '../pages/ChatWidget'
import { getMe, logout } from '../api'
import logoMark from '../assets/logo-mark.png'
import '../pages/HomePage.css'

type NavItem = { href: string; label: string; icon: IconName; mobile?: boolean }
const NAV: NavItem[] = [
  { href: '#/home', label: '홈', icon: 'home', mobile: true },
  { href: '#/accounts', label: '내 계좌', icon: 'wallet', mobile: true },
  { href: '#/cards', label: '카드', icon: 'card', mobile: true },
  { href: '#/products', label: '금융상품', icon: 'layers', mobile: true },
  { href: '#/notifications', label: '알림', icon: 'bell' },
  { href: '#/settings', label: '마이페이지', icon: 'user' },
]

type Props = { title: string; current: string; busy?: boolean; children: ReactNode }

export default function AppShell({ title, current, busy, children }: Props) {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null)
  useEffect(() => {
    void getMe().then((r) => setLoggedIn(r.success))
  }, [])

  async function onLogout() {
    const r = await logout()
    if (r.success) location.hash = '#/login'
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
                <a href={n.href} aria-current={n.href === current ? 'page' : undefined}>
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
          <h1 className="topbar-title">{title}</h1>
          <a className="search" href="#/search">
            <Icon name="search" size={20} />
            <span>계좌, 거래내역, 상품 등을 검색해보세요</span>
          </a>
          <SessionBadge />
          <a className="icon-btn" href="#/notifications" aria-label="알림">
            <Icon name="bell" />
          </a>
          <a className="icon-btn" href={loggedIn ? '#/settings' : '#/login'} aria-label={loggedIn ? '마이페이지' : '로그인'}>
            <Icon name="user" />
          </a>
          {loggedIn && (
            <button type="button" className="text-btn" onClick={onLogout}>
              로그아웃
            </button>
          )}
        </header>

        <main className="home-main" aria-busy={busy}>
          {children}
        </main>
      </div>

      <ChatWidget />

      <nav className="tabbar" aria-label="아래 메뉴">
        {NAV.filter((n) => n.mobile).map((n) => (
          <a key={n.href} href={n.href} aria-current={n.href === current ? 'page' : undefined}>
            <Icon name={n.icon} />
            {n.label}
          </a>
        ))}
      </nav>
    </div>
  )
}
