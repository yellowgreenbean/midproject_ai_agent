// 이체 결과 (docs/기획서.md Part 5 TRX-F02 · 5장 완료 화면 · 9장 상태) — 성공이면 받은 분·금액·거래 후 잔액, 실패면 사유 + 다시 보내기
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { addFavorite, getTransfer, type Transfer } from '../api'
import { won } from '../productRules'
import { STATUS_LABEL, when } from './transferArt'
import './ProductPages.css'
import './TransferPages.css'

export default function TransferResultPage({ id }: { id: string }) {
  const [t, setT] = useState<Transfer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fav, setFav] = useState<'idle' | 'busy' | 'done'>('idle')
  const [favError, setFavError] = useState<string | null>(null)
  useEffect(() => {
    void getTransfer(id).then((r) => (r.success ? setT(r.data) : setError(r.error.message)))
  }, [id])

  const resend = t && `#/transfer?${new URLSearchParams({ from: t.fromAccountId, to: t.toAccountNo, amount: String(t.amount) })}`
  return (
    <AppShell title="이체 결과" current="#/transfer" busy={!t && !error}>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!t && !error && <p className="home-loading">불러오는 중…</p>}
      {t && (
        <div className="panel prod-pad prod-form prod-narrow">
          <p className={`trf-status is-${t.status.toLowerCase()}`}>{STATUS_LABEL[t.status]}</p>
          <h2 className="prod-title">
            {t.status === 'SUCCESS'
              ? `${t.toHolderName}님께 ${won(t.amount)}을 보냈어요`
              : t.status === 'FAILED'
                ? '보내지 못했어요'
                : '결과를 확인하고 있어요'}
          </h2>
          {t.status === 'FAILED' && (
            <p className="prod-warn" role="alert">
              {t.message ?? '이체가 완료되지 않았어요. 잠시 후 다시 시도해 주세요.'} 돈은 빠져나가지 않았어요.
            </p>
          )}
          <dl className="prod-dl">
            <div>
              <dt>받는 분</dt>
              <dd>
                {t.toHolderName} · {t.toBank} {t.toAccountDisplay}
              </dd>
            </div>
            <div>
              <dt>금액</dt>
              <dd>{won(t.amount)}</dd>
            </div>
            <div>
              <dt>수수료</dt>
              <dd>{won(t.fee)}</dd>
            </div>
            <div>
              <dt>출금 계좌</dt>
              <dd>{t.fromAccountDisplay}</dd>
            </div>
            {t.balanceAfter !== null && (
              <div>
                <dt>거래 후 잔액</dt>
                <dd>{won(t.balanceAfter)}</dd>
              </div>
            )}
            <div>
              <dt>통장 표시</dt>
              <dd>
                내 통장 「{t.myDisplayName}」 · 받는 분 통장 「{t.theirDisplayName}」
              </dd>
            </div>
            <div>
              <dt>요청 시각</dt>
              <dd>{when(t.requestedAt)}</dd>
            </div>
          </dl>
          {favError && (
            <p className="home-error" role="alert">
              {favError}
            </p>
          )}
          <div className="prod-done-actions">
            {t.status === 'SUCCESS' && (
              <button
                type="button"
                className="btn-pill"
                disabled={fav !== 'idle'}
                onClick={() => {
                  setFav('busy')
                  void addFavorite(t.toAccountNo).then((r) => {
                    setFav(r.success ? 'done' : 'idle')
                    setFavError(r.success ? null : r.error.message)
                  })
                }}
              >
                {fav === 'done' ? '자주 쓰는 계좌에 담았어요' : '자주 쓰는 계좌에 추가'}
              </button>
            )}
            {t.status === 'FAILED' && resend && (
              <a className="btn-pill" href={resend}>
                다시 보내기
              </a>
            )}
            <a className="btn-pill" href="#/transfers">
              이체 결과 목록
            </a>
            <a className="btn-pill" href={`#/accounts/${t.fromAccountId}`}>
              내 계좌 보기
            </a>
          </div>
        </div>
      )}
    </AppShell>
  )
}
