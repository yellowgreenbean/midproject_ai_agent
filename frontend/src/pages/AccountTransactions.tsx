// 계좌 입출금 내역 — 계좌 상세 한가운데. 날짜별로 묶고, 전체·입금·출금과 기간(1·3·6개월 · 직접)으로 거른다 (Part 5 10장)
import { useEffect, useState } from 'react'
import Icon, { type IconName } from '../components/Icon'
import { getAccountTransactions, type AccountTransaction } from '../api'
import { won } from '../productRules'

const FILTERS: { value: 'IN' | 'OUT' | undefined; label: string }[] = [
  { value: undefined, label: '전체' },
  { value: 'IN', label: '입금' },
  { value: 'OUT', label: '출금' },
]
// 원장 type → 줄 앞 아이콘
const TYPE_ICON: Record<string, IconName> = {
  TRANSFER_IN: 'arrowIn',
  POINT_CASHOUT: 'arrowIn',
  TRANSFER_OUT: 'send',
  CARD_PAYMENT: 'card',
  SUBSCRIPTION_PAYMENT: 'coins',
  SUBSCRIPTION_PAYOUT: 'coins',
}
const WEEK = ['일', '월', '화', '수', '목', '금', '토']
const PERIODS = [
  { months: 1, label: '1개월' },
  { months: 3, label: '3개월' },
  { months: 6, label: '6개월' },
  { months: 0, label: '직접' },
]
/** 오늘(한국)에서 n개월 전 → YYYY-MM-DD */
const monthsAgo = (n: number) => {
  const d = new Date(Date.now() + 9 * 3600_000)
  d.setUTCMonth(d.getUTCMonth() - n)
  return d.toISOString().slice(0, 10)
}

/** '2026-10-31T09:00:01+09:00' → '10월 31일 금요일' */
function dayLabel(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${m}월 ${d}일 ${WEEK[new Date(y, m - 1, d).getDay()]}요일`
}

export default function AccountTransactions({ id }: { id: string }) {
  const [filter, setFilter] = useState<'IN' | 'OUT' | undefined>()
  const [months, setMonths] = useState(1) // 기본 1개월 (10장)
  const [range, setRange] = useState({ startDate: monthsAgo(1), endDate: monthsAgo(0) }) // 「직접」일 때
  const [list, setList] = useState<AccountTransaction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false // 거르기를 빨리 바꿀 때 늦게 온 옛 응답이 덮지 않게
    void getAccountTransactions(id, filter, months ? { startDate: monthsAgo(months) } : range).then((r) => {
      if (stale) return
      if (!r.success) return setError(r.error.message)
      setError(null)
      setList(r.data)
    })
    return () => {
      stale = true
    }
  }, [id, filter, months, range])

  // 같은 날 거래끼리 묶기 (목록은 이미 최신이 먼저)
  const days: { day: string; rows: AccountTransaction[] }[] = []
  for (const t of list ?? []) {
    const day = t.createdAt.slice(0, 10)
    if (days.at(-1)?.day === day) days.at(-1)!.rows.push(t)
    else days.push({ day, rows: [t] })
  }

  return (
    <section aria-labelledby="acct-history" className="acct-history">
      <div className="section-head">
        <h2 id="acct-history" className="section-title">
          <span className="section-icon">
            <Icon name="list" size={18} />
          </span>
          입출금 내역
        </h2>
        <div className="prod-tabs" role="group" aria-label="내역 거르기">
          {FILTERS.map((f) => (
            <button key={f.label} type="button" className="prod-chip" aria-pressed={filter === f.value} onClick={() => setFilter(f.value)}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="prod-tabs acct-tx-period" role="group" aria-label="기간">
        {PERIODS.map((p) => (
          <button key={p.label} type="button" className="prod-chip" aria-pressed={months === p.months} onClick={() => setMonths(p.months)}>
            {p.label}
          </button>
        ))}
        {months === 0 && (
          <>
            <label className="visually-hidden" htmlFor={`tx-from-${id}`}>
              시작일
            </label>
            <input id={`tx-from-${id}`} className="input" type="date" value={range.startDate} onChange={(e) => setRange({ ...range, startDate: e.target.value })} />
            <label className="visually-hidden" htmlFor={`tx-to-${id}`}>
              종료일
            </label>
            <input id={`tx-to-${id}`} className="input" type="date" value={range.endDate} onChange={(e) => setRange({ ...range, endDate: e.target.value })} />
          </>
        )}
      </div>
      <div className="panel acct-tx">
        {error && (
          <p className="prod-pad home-error" role="alert">
            {error}
          </p>
        )}
        {!list && !error && <p className="prod-pad prod-muted">불러오는 중…</p>}
        {list && list.length === 0 && <p className="prod-pad prod-muted">{filter ? '해당하는 거래가 없어요.' : '이 기간에는 거래가 없어요.'}</p>}
        {days.map((g) => (
          <div key={g.day} className="acct-tx-day">
            <h3 className="acct-tx-date">{dayLabel(g.day)}</h3>
            <ul>
              {g.rows.map((t) => (
                <li key={t.id} className={`acct-tx-row is-${t.direction.toLowerCase()}`}>
                  <span className="acct-tx-icon">
                    <Icon name={TYPE_ICON[t.type] ?? 'list'} size={18} />
                  </span>
                  <span className="acct-card-main">
                    <strong>{t.displayName}</strong>
                    <small>{t.createdAt.slice(11, 16)}</small>
                  </span>
                  <span className="acct-tx-amount">
                    <strong>
                      {t.direction === 'IN' ? '+' : '-'}
                      {won(t.amount)}
                    </strong>
                    <small>잔액 {won(t.balanceAfter)}</small>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
