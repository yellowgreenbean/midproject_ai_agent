// 마이페이지 — 토스의 「전체」처럼 한 화면: 맨 위 내 프로필, 아래로 보안 · 알림 · 약관 · 계정 묶음 (docs/기획서.md Part 1 UI05~UI08)
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon, { type IconName } from '../components/Icon'
import { getConsents, getProfile, logout, setConsent, type Profile } from '../api'
import './ProductPages.css'
import './AccountPages.css'
import './SettingsPages.css'

type Row = { icon: IconName; label: string; href?: string; value?: string; soon?: boolean }
const GROUPS: { title: string; rows: Row[] }[] = [
  {
    title: '보안',
    rows: [
      { icon: 'safe', label: '비밀번호 변경', href: '#/settings/password' },
      { icon: 'send', label: '이체 한도', value: '계좌마다 설정', href: '#/settings/limits' },
      { icon: 'bolt', label: '간편 비밀번호(PIN)', href: '#/settings/pin' },
    ],
  },
  { title: '알림', rows: [{ icon: 'bell', label: '입출금 알림', value: '계좌마다 설정', href: '#/accounts' }] },
  { title: '약관', rows: [{ icon: 'list', label: '약관 및 동의 내역', href: '#/settings/terms' }] },
]

export default function SettingsPage() {
  const [me, setMe] = useState<Profile | 'guest' | null>(null)
  const [marketing, setMarketing] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getProfile().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setMe('guest') : setError(r.error.message)
      setMe(r.data)
      void getConsents().then((c) => c.success && setMarketing(c.data.find((x) => x.termsId === 'marketing')?.agreed ?? false))
    })
  }, [])

  async function toggleMarketing() {
    if (marketing === null) return
    const r = await setConsent('marketing', !marketing)
    if (!r.success) return setError(r.error.message)
    setMarketing(r.data.find((x) => x.termsId === 'marketing')?.agreed ?? false)
  }

  async function onLogout() {
    const r = await logout()
    if (r.success) location.hash = '#/login'
    else setError(r.error.message)
  }

  return (
    <AppShell title="마이페이지" current="#/settings" busy={!me && !error}>
      <h2 className="prod-title is-dup">마이페이지</h2>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!me && !error && <p className="home-loading">불러오는 중…</p>}
      {me === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 내 정보와 설정을 볼 수 있어요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {me && me !== 'guest' && (
        <div className="set-wrap">
          <a className="panel set-profile" href="#/settings/profile">
            <span className="set-avatar" aria-hidden="true">
              {me.name.slice(0, 1)}
            </span>
            <span className="set-profile-text">
              <strong>{me.name}</strong>
              <small>
                {me.username} · {me.email}
              </small>
            </span>
            <span className="set-profile-go">
              내 정보
              <Icon name="chevron" size={16} />
            </span>
          </a>

          {GROUPS.map((g) => (
            <section key={g.title} className="set-group" aria-label={g.title}>
              <h3 className="set-group-title">{g.title}</h3>
              <ul className="panel set-menu">
                {g.rows.map((r) => (
                  <li key={r.label}>
                    {r.href ? (
                      <a href={r.href}>
                        <RowBody row={r} />
                        <Icon name="chevron" size={18} />
                      </a>
                    ) : (
                      <span className="is-off">
                        <RowBody row={r} />
                        {r.soon && <span className="set-soon">준비 중</span>}
                      </span>
                    )}
                  </li>
                ))}
                {g.title === '알림' && (
                  <li>
                    <button type="button" role="switch" aria-checked={!!marketing} disabled={marketing === null} onClick={() => void toggleMarketing()}>
                      <RowBody row={{ icon: 'send', label: '혜택 소식 받기', value: '선택 동의' }} />
                      <span className="acct-switch" aria-hidden="true" />
                    </button>
                  </li>
                )}
              </ul>
            </section>
          ))}

          <section className="set-group" aria-label="계정">
            <h3 className="set-group-title">계정</h3>
            <ul className="panel set-menu">
              <li>
                <button type="button" onClick={() => void onLogout()}>
                  <RowBody row={{ icon: 'user', label: '로그아웃' }} />
                </button>
              </li>
            </ul>
            <a className="set-leave" href="#/settings/withdraw">
              회원 탈퇴
            </a>
          </section>
        </div>
      )}
    </AppShell>
  )
}

function RowBody({ row }: { row: Row }) {
  return (
    <>
      <span className="set-icon">
        <Icon name={row.icon} size={18} />
      </span>
      <span className="set-label">{row.label}</span>
      {row.value && <span className="set-value">{row.value}</span>}
    </>
  )
}
