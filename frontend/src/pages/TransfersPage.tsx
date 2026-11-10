// 이체 결과 목록 (docs/기획서.md Part 5 TRX-F02 · 10장 「이체 결과」 탭) — 내가 보낸 이체의 성공·실패, 최신이 먼저
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { getTransfers, type Transfer } from '../api'
import { won } from '../productRules'
import { STATUS_LABEL, when } from './transferArt'
import './ProductPages.css'
import './TransferPages.css'

export default function TransfersPage() {
  const [list, setList] = useState<Transfer[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    void getTransfers().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setList('guest') : setError(r.error.message)
      setList(r.data)
    })
  }, [])

  return (
    <AppShell title="이체 결과" current="#/transfer" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title is-dup">이체 결과</h2>
        <p className="prod-sub">내가 보낸 이체가 잘 갔는지 볼 수 있어요. 실패한 이체는 돈이 빠져나가지 않아요.</p>
        <a className="more" href="#/scheduled-transfers">
          예약·자동이체 보기
        </a>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 이체 결과가 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(list) &&
        (list.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">아직 보낸 이체가 없어요</p>
            <a className="btn-pill" href="#/transfer">
              송금하기
            </a>
          </div>
        ) : (
          <ul className="panel rows">
            {list.map((t) => (
              <li key={t.id}>
                <a href={`#/transfers/${t.id}`}>
                  <span className="row-main">
                    <strong>{t.toHolderName}</strong>
                    <small>{when(t.requestedAt)}</small>
                  </span>
                  <span className="trf-item-side">
                    <strong className="row-amount">{won(t.amount)}</strong>
                    <small className={`trf-status is-${t.status.toLowerCase()}`}>{STATUS_LABEL[t.status]}</small>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        ))}
    </AppShell>
  )
}
