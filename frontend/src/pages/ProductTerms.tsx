// 상품 약관 목록 + 「자세히 보기」 (docs/기획서.md Part 3) — 상품 상세와 가입 확인 화면이 같이 쓴다.
// 화면을 옮기지 않고 창(TermsDialog)으로 띄운다 — 입력하던 금액·기간이 사라지지 않게.
import { useState } from 'react'
import Icon from '../components/Icon'
import { TermsDialog } from '../components/TermsViewer'
import type { ProductTerm } from '../api'

export default function ProductTerms({ productId, terms }: { productId: string; terms: ProductTerm[] }) {
  const [viewing, setViewing] = useState<string | null>(null)
  return (
    <>
      <ul className="prod-terms">
        {terms.map((t) => (
          <li key={t.id}>
            <span>{t.title}</span>
            <button type="button" className="prod-terms-more" onClick={() => setViewing(t.id)} aria-label={`${t.title} 자세히 보기`}>
              자세히 보기 <Icon name="chevron" size={14} />
            </button>
          </li>
        ))}
      </ul>
      {viewing && <TermsDialog termsId={viewing} productId={productId} onClose={() => setViewing(null)} />}
    </>
  )
}
