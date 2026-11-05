// 카드 이용 내역 (docs/기획서.md Part 4 CARD-F03) — 카드 상세 한가운데. 달로 고르고(서버), 분류로 거르고(화면), 날짜별로 묶는다
import { useEffect, useState } from 'react'
import Icon from '../components/Icon'
import { getCardTransactions, type CardTransaction } from '../api'
import { won } from '../productRules'
import { byCategory, md, net, recentMonths } from '../cardRules'

const MONTHS = recentMonths(new Date(), 3) // 이번 달·지난달·지지난달 — 더미 이용 내역은 9·10월

export default function CardTransactions({ id }: { id: string }) {
  const [month, setMonth] = useState<string | undefined>()
  const [category, setCategory] = useState<string | null>(null)
  const [list, setList] = useState<CardTransaction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false // 달을 빨리 바꿀 때 늦게 온 옛 응답이 덮지 않게
    void getCardTransactions(id, month).then((r) => {
      if (stale) return
      if (!r.success) return setError(r.error.message)
      setError(null)
      setList(r.data)
      setCategory(null)
    })
    return () => {
      stale = true
    }
  }, [id, month])

  const sums = byCategory(list ?? [])
  const shown = (list ?? []).filter((t) => !category || t.category === category)
  const days: { day: string; rows: CardTransaction[] }[] = []
  for (const t of shown) {
    const day = t.transactedAt.slice(0, 10)
    if (days.at(-1)?.day === day) days.at(-1)!.rows.push(t)
    else days.push({ day, rows: [t] })
  }

  return (
    <section aria-labelledby="card-history" className="acct-history">
      <div className="section-head">
        <h2 id="card-history" className="section-title">
          <span className="section-icon">
            <Icon name="list" size={18} />
          </span>
          이용 내역
        </h2>
        <div className="prod-tabs" role="group" aria-label="달 고르기">
          {[undefined, ...MONTHS].map((m) => (
            <button key={m ?? 'all'} type="button" className="prod-chip" aria-pressed={month === m} onClick={() => setMonth(m)}>
              {m ? `${Number(m.slice(4))}월` : '전체'}
            </button>
          ))}
        </div>
      </div>
      {sums.length > 0 && (
        <div className="card-cats" role="group" aria-label="분류로 거르기">
          <p className="card-cats-total">
            {category ?? (month ? `${Number(month.slice(4))}월` : '전체')} 쓴 돈 <strong>{won((category ? sums.filter((x) => x.category === category) : sums).reduce((n, x) => n + x.amount, 0))}</strong>
          </p>
          {sums.map((x) => (
            <button key={x.category} type="button" className="prod-chip" aria-pressed={category === x.category} onClick={() => setCategory(category === x.category ? null : x.category)}>
              {x.category} {won(x.amount)}
            </button>
          ))}
        </div>
      )}
      <div className="panel acct-tx">
        {error && (
          <p className="prod-pad home-error" role="alert">
            {error}
          </p>
        )}
        {!list && !error && <p className="prod-pad prod-muted">불러오는 중…</p>}
        {list && shown.length === 0 && <p className="prod-pad prod-muted">{month ? '이 달에 쓴 내역이 없어요.' : '아직 쓴 내역이 없어요.'}</p>}
        {days.map((g) => (
          <div key={g.day} className="acct-tx-day">
            <h3 className="acct-tx-date">{md(g.day)}</h3>
            <ul>
              {g.rows.map((t) => (
                <li key={t.id} className={`acct-tx-row${t.status === 'CANCELED' ? ' is-canceled' : ''}`}>
                  <span className="acct-tx-icon">
                    <Icon name="card" size={18} />
                  </span>
                  <span className="acct-card-main">
                    <strong>{t.merchant}</strong>
                    <small>
                      {t.category} · {t.transactedAt.slice(11, 16)} · {t.installmentMonths > 1 ? `${t.installmentMonths}개월 할부` : '일시불'}
                      {t.isOverseas && ' · 해외'}
                    </small>
                  </span>
                  <span className="acct-tx-amount">
                    <strong>-{won(t.status === 'CANCELED' ? t.amount : net(t))}</strong>
                    {t.status !== 'APPROVED' && <small className="card-canceled">{t.status === 'CANCELED' ? '결제 취소' : `${won(t.canceledAmount)} 취소`}</small>}
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
