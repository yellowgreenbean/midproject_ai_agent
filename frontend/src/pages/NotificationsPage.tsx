// 알림 센터 (docs/기획서.md Part 2 ACCT-F06) — 입출금·만기 알림. 이 화면을 열면 모두 읽음으로 바꾼다
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { getNotifications, readAllNotifications, type AppNotification } from '../api'
import './ProductPages.css'
import './AccountPages.css'

/** 알림을 누르면 갈 곳과 글자 — 잔액 부족(LOW_BALANCE)은 청구서(event_id = 청구서 id, 당일 알림은 끝에 :D-0)에서 「채우기 송금」,
 * 입출금은 그 계좌, 포인트 소멸 예정은 포인트 화면(현금화), 연회비는 그 카드 */
function link(n: AppNotification): { href: string; label: string } | null {
  if (n.type === 'LOW_BALANCE' && n.eventId) return { href: `#/card-bills/${n.eventId.split(':')[0]}`, label: '청구서 보고 채우기' }
  if (n.type === 'TRANSACTION' && n.accountId) return { href: `#/accounts/${n.accountId}`, label: '계좌 보기' }
  if (n.type === 'POINT_EXPIRING') return { href: '#/cards/points', label: '포인트 현금으로 바꾸기' }
  if (n.type === 'ANNUAL_FEE' && n.cardId) return { href: `#/cards/${n.cardId}`, label: '카드 보기' }
  return null
}

/** 2026-11-05T09:30:00+09:00 → 11.05 09:30 */
const when = (iso: string) => `${iso.slice(5, 7)}.${iso.slice(8, 10)} ${iso.slice(11, 16)}`

export default function NotificationsPage() {
  const [list, setList] = useState<AppNotification[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getNotifications().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setList('guest') : setError(r.error.message)
      setList(r.data) // 처음 받은 읽음 표시를 그대로 보여 주고, 서버에는 읽음으로 남긴다
      if (r.data.some((n) => !n.read)) void readAllNotifications()
    })
  }, [])

  return (
    <AppShell title="알림" current="#/notifications" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title is-dup">알림</h2>
        <p className="prod-sub">입금·출금, 예금·적금 만기, 카드 결제일·연회비·포인트 소멸을 알려 드려요. 입출금 알림은 계좌 상세에서 끌 수 있어요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 알림이 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(list) &&
        (list.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">아직 알림이 없어요</p>
          </div>
        ) : (
          <ul className="panel rows acct-notes">
            {list.map((n) => (
              <li key={n.id} className={n.read ? '' : 'is-unread'}>
                <span className="row-main">
                  <strong>
                    {!n.read && <span className="acct-dot" aria-label="안 읽음" />}
                    {n.title}
                  </strong>
                  <small>{n.body}</small>
                  {link(n) && (
                    <a className="more" href={link(n)!.href}>
                      {link(n)!.label}
                    </a>
                  )}
                </span>
                <small className="prod-muted">{when(n.createdAt)}</small>
              </li>
            ))}
          </ul>
        ))}
    </AppShell>
  )
}
