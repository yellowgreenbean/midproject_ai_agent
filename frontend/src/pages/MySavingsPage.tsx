// 내 가입 상품 (docs/기획서.md Part 3 PROD-F09) — 로그인한 본인 것만
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { getMySubscriptions, type Subscription } from '../api'
import { won, ymd } from '../productRules'
import { PRODUCT_ART, STATUS_LABEL } from './productArt'
import './ProductPages.css'


export default function MySavingsPage() {
  const [list, setList] = useState<Subscription[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getMySubscriptions().then((r) => {
      if (r.success) return setList(r.data)
      if (r.error.code === 'UNAUTHENTICATED') return setList('guest')
      setError(r.error.message)
    })
  }, [])

  return (
    <AppShell title="내 가입 상품" current="#/products" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title">내 예금 · 적금</h2>
        <a className="more" href="#/products">
          상품 더 보기 <Icon name="chevron" size={14} />
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
          <p className="empty-title">로그인하면 가입한 상품이 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(list) &&
        (list.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">아직 가입한 상품이 없어요</p>
            <p className="empty-sub">예금·적금으로 돈을 모아 보세요.</p>
            <a className="btn-pill" href="#/products">
              상품 둘러보기
            </a>
          </div>
        ) : (
          <ul className="panel rows">
            {list.map((s) => (
              <li key={s.id}>
                <a href={`#/my/savings/${s.id}`}>
                  <img src={PRODUCT_ART[s.productType]} alt="" className="row-art" />
                  <span className="row-main">
                    <strong>{s.productName}</strong>
                    <small>
                      연 {s.appliedRate}% · 만기 {ymd(s.maturityDate)} · {s.accountNumber}
                      {s.monthlyAmount !== null && ` · 매달 ${won(s.monthlyAmount)}`}
                    </small>
                  </span>
                  <span className="rate">
                    <strong>{won(s.principal)}</strong>
                    <small>{STATUS_LABEL[s.status] ?? s.status}</small>
                  </span>
                  <Icon name="chevron" size={18} />
                </a>
              </li>
            ))}
          </ul>
        ))}
    </AppShell>
  )
}
