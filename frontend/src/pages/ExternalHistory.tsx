// 다른 은행 내역 — 거래내역 화면의 탭 (docs/기획서.md Part 5 10장, 읽기 전용, 우리 원장·잔액과 섞지 않는다)
//   transfer: 다른 은행 이체내역 (TRX-F09, CODEF 이체결과 더미) · deposit: 다른 은행 예적금 내역 (TRX-F14, CODEF 샌드박스)
// 연결된 다른 은행 계좌는 지금 user_001 에게만 있다(사용자 결정 2026-11-10) — 다른 회원은 서버가 「연결된 계좌가 아니에요」로 답한다
import { useEffect, useState } from 'react'
import {
  EXTERNAL_DEPOSIT_ACCOUNT,
  EXTERNAL_TRANSFER_ACCOUNT,
  getExternalDeposit,
  getExternalTransfers,
  type ExternalDeposit,
  type ExternalTransfer,
} from '../api'
import { won } from '../productRules'
import { STATUS_LABEL, when } from './transferArt'

const CHANNEL_LABEL = { APP: '', SCHEDULED: '예약이체', AUTO: '자동이체' } as const
/** YYYY-MM-DD ↔ YYYYMMDD */
const compact = (d: string) => d.replaceAll('-', '')
const ymd = (s: string) => (s ? `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}` : '')
const today = () => new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10)
/** 만기일(YYYYMMDD)까지 남은 날 — 만기일이 없으면 null (10장 「만기까지 D-OO」) */
const daysUntil = (end: string) => (end ? Math.ceil((Date.parse(`${end.slice(0, 4)}-${end.slice(4, 6)}-${end.slice(6, 8)}T00:00:00+09:00`) - Date.now()) / 86_400_000) : null)

export default function ExternalHistory({ kind }: { kind: 'transfer' | 'deposit' }) {
  // 더미 이체내역은 2025-01-01~02, 샌드박스 견본 적금은 2019년이라 그 해부터 오늘까지를 기본으로
  const [range, setRange] = useState({ start: kind === 'transfer' ? '2025-01-01' : '2019-01-01', end: today() })
  const [transfers, setTransfers] = useState<ExternalTransfer[] | null>(null)
  const [deposit, setDeposit] = useState<{ data: ExternalDeposit; daysLeft: number | null } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let stale = false // 기간을 빨리 바꿀 때 늦게 온 옛 응답이 덮지 않게
    if (kind === 'transfer')
      void getExternalTransfers(compact(range.start), compact(range.end)).then((r) => {
        if (stale) return
        setError(r.success ? null : r.error.message)
        if (r.success) setTransfers(r.data.items)
      })
    else
      void getExternalDeposit(compact(range.start), compact(range.end)).then((r) => {
        if (stale) return
        setError(r.success ? null : r.error.message)
        if (r.success) setDeposit({ data: r.data, daysLeft: daysUntil(r.data.resAccountEndDate) })
      })
    return () => {
      stale = true
    }
  }, [kind, range])

  const account = kind === 'transfer' ? EXTERNAL_TRANSFER_ACCOUNT : EXTERNAL_DEPOSIT_ACCOUNT
  const left = deposit?.daysLeft ?? null
  const d = deposit?.data

  return (
    <section className="acct-history" aria-label={kind === 'transfer' ? '다른 은행 이체내역' : '다른 은행 예적금 내역'}>
      <div className="panel prod-pad">
        <p className="prod-muted">
          {account.bank} {account.accountNo} · 다른 은행에서 받아 온 내역이라 두린은행 잔액과 따로 봐요.
        </p>
        <div className="prod-tabs" role="group" aria-label="조회 기간">
          <label className="visually-hidden" htmlFor={`ext-from-${kind}`}>
            시작일
          </label>
          <input id={`ext-from-${kind}`} className="input" type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} />
          <label className="visually-hidden" htmlFor={`ext-to-${kind}`}>
            종료일
          </label>
          <input id={`ext-to-${kind}`} className="input" type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} />
        </div>
      </div>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!error && (kind === 'transfer' ? !transfers : !deposit) && <p className="prod-muted">불러오는 중…</p>}

      {kind === 'transfer' && transfers && !error && (
        <ul className="panel rows">
          {transfers.length === 0 && <li className="prod-muted">이 기간에는 이체가 없어요.</li>}
          {transfers.map((t, i) => (
            <li key={`${t.requestedAt}-${i}`}>
              <span className="row-main">
                <strong>
                  {t.transType === '오픈뱅킹' ? '내 계좌로 옮기기' : t.toHolderName} · {won(t.amount)}
                </strong>
                <small>
                  {when(t.requestedAt)} · {t.toBank} {t.toAccountNo}
                  {CHANNEL_LABEL[t.channel] && ` · ${CHANNEL_LABEL[t.channel]}`}
                  {t.fee > 0 && ` · 수수료 ${won(t.fee)}`}
                </small>
              </span>
              {/* CODEF 결과에는 실패 사유가 없어 상태만 보여 준다 (10장) */}
              <span className={`trf-status is-${t.status.toLowerCase()}`}>{STATUS_LABEL[t.status]}</span>
            </li>
          ))}
        </ul>
      )}

      {kind === 'deposit' && d && !error && (
        <>
          <dl className="panel prod-info">
            <div>
              <dt>계좌</dt>
              <dd>
                {d.resAccountNickName || d.resAccountName} {d.resAccountDisplay}
              </dd>
            </div>
            <div>
              <dt>이율</dt>
              <dd>연 {Number(d.resRate)}%</dd>
            </div>
            <div>
              <dt>기간</dt>
              <dd>
                {ymd(d.resAccountStartDate)} ~ {d.resAccountEndDate ? ymd(d.resAccountEndDate) : '만기 없음'}
                {left !== null && (left >= 0 ? ` · 만기까지 D-${left}` : ' · 만기 지남')}
              </dd>
            </div>
            <div>
              <dt>현재 잔액</dt>
              <dd>{won(Number(d.resAccountBalance))}</dd>
            </div>
            {d.resValidPeriod && (
              <div>
                <dt>납입</dt>
                <dd>
                  {d.resFinalRoundNo}회 / {d.resValidPeriod}개월{d.resMonthlyPayment && ` · 월 ${won(Number(d.resMonthlyPayment))}`}
                </dd>
              </div>
            )}
          </dl>
          <ul className="panel rows">
            {d.resTrHistoryList.length === 0 && <li className="prod-muted">이 기간에는 납입이 없어요.</li>}
            {d.resTrHistoryList.map((h) => (
              <li key={`${h.resRoundNo}-${h.resAccountTrDate}`}>
                <span className="row-main">
                  <strong>
                    {h.resRoundNo}회차 · +{won(Number(h.resAccountIn))}
                  </strong>
                  <small>
                    {ymd(h.resAccountTrDate)} · {h.resMonth.slice(0, 4)}년 {Number(h.resMonth.slice(4))}월분
                    {[h.resAccountDesc1, h.resAccountDesc3].filter(Boolean).length > 0 && ` · ${[h.resAccountDesc1, h.resAccountDesc3].filter(Boolean).join(' ')}`}
                  </small>
                </span>
                <small className="prod-muted">잔액 {won(Number(h.resAfterTranBalance))}</small>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
