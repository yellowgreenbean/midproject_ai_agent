// 이 계좌에서 보낸 이체 결과 — 계좌 상세 (docs/기획서.md Part 5 TRX-F02 · 10장 「이체 결과」 탭을 계좌 확인에서도, 사용자 결정 2026-11-10)
// 성공·실패·처리중을 모두 보여 준다(원장에는 성공한 것만 있어 입출금 내역과 다르다). 누르면 이체 결과 화면
import { useEffect, useState } from 'react'
import Icon from '../components/Icon'
import { getTransfers, type Transfer } from '../api'
import { won } from '../productRules'
import { STATUS_LABEL, when } from './transferArt'

export default function AccountTransfers({ id }: { id: string }) {
  const [list, setList] = useState<Transfer[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    void getTransfers({ accountId: id }).then((r) => (r.success ? setList(r.data) : setError(r.error.message)))
  }, [id])

  return (
    <section aria-labelledby="acct-transfers" className="acct-history">
      <h2 id="acct-transfers" className="section-title">
        <span className="section-icon">
          <Icon name="send" size={18} />
        </span>
        이 계좌의 이체 결과
      </h2>
      <div className="panel">
        {error && (
          <p className="prod-pad home-error" role="alert">
            {error}
          </p>
        )}
        {!list && !error && <p className="prod-pad prod-muted">불러오는 중…</p>}
        {list && list.length === 0 && <p className="prod-pad prod-muted">이 계좌에서 보낸 이체가 없어요.</p>}
        {list && list.length > 0 && (
          <ul className="rows">
            {list.slice(0, 10).map((t) => (
              <li key={t.id}>
                <a className="row-main" href={`#/transfers/${t.id}`}>
                  <strong>
                    {t.toHolderName} · {won(t.amount)}
                  </strong>
                  <small>
                    {when(t.requestedAt)} · {t.toBank} · <span className={`trf-status is-${t.status.toLowerCase()}`}>{STATUS_LABEL[t.status]}</span>
                  </small>
                </a>
              </li>
            ))}
          </ul>
        )}
        {list && list.length > 10 && (
          <a className="more prod-pad" href="#/transfers">
            이체 결과 전체 보기 <Icon name="chevron" size={14} />
          </a>
        )}
      </div>
    </section>
  )
}
