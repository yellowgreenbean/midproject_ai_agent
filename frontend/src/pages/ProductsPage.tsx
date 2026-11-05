// 예금·적금 상품 목록 (docs/기획서.md Part 3 PROD-F01·F03) — 로그인 없이 볼 수 있다
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { getProducts, type ProductSummary, type ProductType } from '../api'
import { PRODUCT_ART, TYPE_CLASS, TYPE_LABEL } from './productArt'
import './ProductPages.css'

const TABS: { type: ProductType | undefined; label: string }[] = [
  { type: undefined, label: '전체' },
  { type: 'TIME_DEPOSIT', label: '예금' },
  { type: 'INSTALLMENT_SAVINGS', label: '적금' },
]

export default function ProductsPage() {
  const [type, setType] = useState<ProductType | undefined>()
  const [q, setQ] = useState('')
  const [byRate, setByRate] = useState(false)
  const [list, setList] = useState<ProductSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false // 빨리 입력할 때 늦게 온 옛 응답이 새 결과를 덮지 않게
    void getProducts({ q: q.trim() || undefined, type, sort: byRate ? 'rate' : undefined }).then((r) => {
      if (stale) return
      if (!r.success) return setError(r.error.message)
      setError(null)
      setList(r.data)
    })
    return () => {
      stale = true
    }
  }, [type, q, byRate])

  return (
    <AppShell title="금융상품" current="#/products" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title">예금 · 적금</h2>
        <p className="prod-sub">두린은행 상품을 비교하고 바로 가입해 보세요. 금리는 세전 연 이율이에요.</p>
        <a className="more" href="#/my/savings">
          내 가입 상품 보기 <Icon name="chevron" size={14} />
        </a>
      </section>

      <div className="prod-tools">
        <div className="prod-tabs" role="group" aria-label="상품 종류">
          {TABS.map((t) => (
            <button key={t.label} type="button" className="prod-chip" aria-pressed={type === t.type} onClick={() => setType(t.type)}>
              {t.label}
            </button>
          ))}
        </div>
        <label className="prod-search">
          <Icon name="search" size={18} />
          <span className="visually-hidden">상품 이름 검색</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="상품 이름으로 찾기" maxLength={40} />
        </label>
        <button type="button" className="prod-chip" aria-pressed={byRate} onClick={() => setByRate((v) => !v)}>
          금리 높은 순
        </button>
      </div>

      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list && (
        <>
          <p className="prod-count" aria-live="polite">
            {list.length}개 상품
          </p>
          {list.length === 0 ? (
            <div className="panel empty">
              <p className="empty-title">찾는 상품이 없어요</p>
              <p className="empty-sub">다른 이름으로 검색하거나 종류를 바꿔 보세요.</p>
            </div>
          ) : (
            <ul className="products">
              {list.map((p) => (
                <li key={p.id}>
                  <a href={`#/products/${p.id}`} className={`panel product-card ${TYPE_CLASS[p.type]}`}>
                    <span className="pc-top">
                      <img src={PRODUCT_ART[p.type]} alt="" className="pc-art" />
                      <span className="pc-tag">{TYPE_LABEL[p.type]}</span>
                    </span>
                    <strong className="pc-name">{p.name}</strong>
                    <span className="pc-desc">
                      {p.termLabel || '기간 확인 필요'}
                      {!p.earlyTerminationAllowed && <span className="prod-badge-warn">중도해지 불가</span>}
                    </span>
                    <span className="pc-rate">
                      {p.maxRate ? (
                        <>
                          <small>최고</small> 연 {p.maxRate}%
                        </>
                      ) : (
                        <span className="prod-muted">금리 확인 중</span>
                      )}
                    </span>
                    <span className="pc-foot">
                      <span>{p.baseRate && p.baseRate !== p.maxRate ? `기본 연 ${p.baseRate}%` : '세전 연 이율'}</span>
                      <span className="pc-cta">
                        자세히 보기 <Icon name="chevron" size={14} />
                      </span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </AppShell>
  )
}
