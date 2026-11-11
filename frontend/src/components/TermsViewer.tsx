// 약관 본문 보기 (docs/기획서.md Part 1 AUTH-F10 정상 흐름 1 「가입 시 약관 내용 제공」 · 5 「마이페이지에서 열람」)
// TermsViewer: 제목·버전·시행일 + 목차(장·조) + 본문. 마이페이지 화면(TermsDetailPage)과 가입 화면의 TermsDialog 가 같이 쓴다.
// TermsDialog: 가입 화면용 전체 화면 창 — 화면을 옮기면 입력하던 가입 정보가 사라지므로 주소를 바꾸지 않고 위에 띄운다.
// productId 를 주면 그 예금·적금 상품의 약관(Part 3, GET /products/{id}/terms/{termsId})을 읽는다 — 상품 상세·가입 화면(ProductTerms).
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import Icon from './Icon'
import { getProductTerm, getTermDetail, type TermDetail } from '../api'
import { parseTermsMarkdown, termsToc, type TermsBlock } from '../termsMarkdown'
import './TermsViewer.css'

const dot = (d: string) => d.slice(0, 10).replaceAll('-', '.')

function Block({ b }: { b: TermsBlock }) {
  if (b.kind === 'heading') {
    const H = b.level === 2 ? 'h3' : b.level === 3 ? 'h4' : 'h5' // 화면 제목이 h2
    return (
      <H id={b.id} tabIndex={-1} className={`tv-h tv-h${b.level}`}>
        {b.text}
      </H>
    )
  }
  if (b.kind === 'table')
    return (
      <div className="tv-table-wrap">
        <table className="tv-table">
          <thead>
            <tr>{b.head.map((c, i) => <th key={i}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {b.rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  return (
    <p className="tv-p">
      {b.lines.map((l, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {l}
        </Fragment>
      ))}
    </p>
  )
}

function goTo(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  el.focus({ preventScroll: true }) // 화면 읽기 프로그램도 그 조로 옮겨 간다
}

export default function TermsViewer({ termsId, productId }: { termsId: string; productId?: string }) {
  const [term, setTerm] = useState<TermDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = productId ? getProductTerm(productId, termsId) : getTermDetail(termsId)
    void load.then((r) => alive && (r.success ? setTerm(r.data) : setError(r.error.message)))
    return () => {
      alive = false
    }
  }, [termsId, productId])

  const blocks = useMemo(() => (term?.content ? parseTermsMarkdown(term.content) : []), [term])
  const toc = useMemo(() => termsToc(blocks), [blocks])

  if (error)
    return (
      <p className="tv-status is-error" role="alert">
        {error}
      </p>
    )
  if (!term) return <p className="tv-status">약관을 불러오는 중…</p>

  return (
    <article className="tv" aria-labelledby="tv-title">
      <header className="tv-head">
        <h2 id="tv-title" className="tv-title">
          {term.required !== null && <span className={`tv-chip ${term.required ? 'is-req' : ''}`}>{term.required ? '필수' : '선택'}</span>}
          {term.title}
        </h2>
        {term.version && term.effectiveAt && (
          <p className="tv-meta">
            {term.version} 판 · {dot(term.effectiveAt)} 시행
          </p>
        )}
      </header>

      {toc.length >= 3 && (
        <details className="tv-toc">
          <summary>
            목차 <small>{toc.filter((t) => t.level === 3).length || toc.length}개 조항</small>
          </summary>
          <ol>
            {toc.map((t) => (
              <li key={t.id} className={t.level === 3 ? 'is-sub' : ''}>
                <button type="button" onClick={() => goTo(t.id)}>
                  {t.text}
                </button>
              </li>
            ))}
          </ol>
        </details>
      )}

      {term.content ? (
        <div className="tv-body">
          {blocks.map((b, i) => (
            <Block key={i} b={b} />
          ))}
        </div>
      ) : (
        <p className="tv-empty">약관 본문을 준비하고 있어요.</p>
      )}

      {term.source?.startsWith('http') && (
        <p className="tv-source">
          학습용으로 옮긴 약관이에요. 원문:{' '}
          <a href={term.source} target="_blank" rel="noreferrer">
            {new URL(term.source).host}
          </a>
        </p>
      )}
    </article>
  )
}

/** 가입 화면용 — 전체 화면 창. Esc · 닫기로 닫고, 닫으면 「보기」 버튼으로 초점을 돌려준다 */
export function TermsDialog({ termsId, productId, onClose }: { termsId: string; productId?: string; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose) // 부모가 다시 그려져도 아래 준비(초점·스크롤 잠금)를 다시 하지 않게
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden' // 뒤 화면이 같이 스크롤되지 않게
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCloseRef.current()
    addEventListener('keydown', onKey)
    return () => {
      removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      opener?.focus()
    }
  }, [])

  return (
    <div className="tv-dialog" role="dialog" aria-modal="true" aria-labelledby="tv-title">
      <div className="tv-dialog-bar">
        <button ref={closeRef} type="button" className="tv-dialog-close" onClick={onClose}>
          <Icon name="chevron" size={16} />
          닫기
        </button>
      </div>
      <div className="tv-dialog-body">
        <TermsViewer termsId={termsId} productId={productId} />
      </div>
    </div>
  )
}
