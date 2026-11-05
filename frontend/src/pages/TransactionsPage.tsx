// 거래내역 (docs/기획서.md Part 5 TRX-F03 · 10장) — 메뉴 「거래내역」. 계좌를 골라 입출금 내역을 보고, 「이체 결과」 탭은 이체 결과 화면으로
// shortcut: 기간(1·3·6개월) 거르기와 20건씩 더 불러오기는 아직 없다 — 더미가 10월 한 달치뿐이라 지금은 전부 보여 준다. 거래가 쌓이면 서버에 기간·페이지를 붙인다.
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import AccountTransactions from './AccountTransactions'
import { getAccounts, type Account } from '../api'
import { won } from '../productRules'
import './ProductPages.css'
import './AccountPages.css'

export default function TransactionsPage() {
  const [accounts, setAccounts] = useState<Account[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [id, setId] = useState('')
  useEffect(() => {
    void getAccounts().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setAccounts('guest') : setError(r.error.message)
      setAccounts(r.data)
      // 홈의 대표 계좌와 같은 순서: 즐겨찾기 → 정상 → 첫 계좌
      const main = r.data.find((a) => a.isFavorite) ?? r.data.find((a) => a.status === 'ACTIVE') ?? r.data[0]
      if (main) setId(main.id)
    })
  }, [])

  return (
    <AppShell title="거래내역" current="#/transactions" busy={!accounts && !error}>
      <section className="prod-head">
        <h2 className="prod-title">거래내역</h2>
        <div className="prod-tabs" role="group" aria-label="내역 종류">
          <button type="button" className="prod-chip" aria-pressed="true">
            입출금 내역
          </button>
          <a className="prod-chip" href="#/transfers">
            이체 결과
          </a>
        </div>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!accounts && !error && <p className="home-loading">불러오는 중…</p>}
      {accounts === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 거래내역이 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(accounts) &&
        (accounts.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">아직 계좌가 없어요</p>
            <a className="btn-pill" href="#/accounts/new">
              계좌 만들기
            </a>
          </div>
        ) : (
          <>
            <div className="panel prod-pad">
              <div className="field">
                <label className="field-label" htmlFor="tx-account">
                  계좌
                </label>
                <select id="tx-account" className="input" value={id} onChange={(e) => setId(e.target.value)}>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} {a.number} · {won(a.balance)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {id && <AccountTransactions key={id} id={id} />}
          </>
        ))}
    </AppShell>
  )
}
