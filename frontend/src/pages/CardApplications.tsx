// 카드 신청·배송 조회 (docs/기획서.md Part 4 CARD-F05) — 단계 막대와, 단계마다 할 일 버튼
// 1차는 실제 배송이 없어 「배송 시작」·「배송 완료」를 시연용 버튼으로 넘긴다(기획서 1-2 ⑥).
// 신청 취소는 배송 시작 전(승인까지)만 — 본인 확인 없이 확인 창만 (사용자 결정 2026-11-10)
import { useState } from 'react'
import { activateCard, cancelCardApplication, markDelivered, shipCard, type CardApplication } from '../api'
import { APPLICATION_STEPS, CARD_TYPE_LABEL, dots } from '../cardRules'
import { cardArtOf } from './cardArt'

export function Steps({ app }: { app: CardApplication }) {
  const at = APPLICATION_STEPS.findIndex((s) => s.status === app.status)
  return (
    <ol className="card-steps" aria-label="진행 단계">
      {APPLICATION_STEPS.map((s, i) => (
        <li key={s.status} className={i < at ? 'is-done' : i === at ? 'is-now' : undefined} aria-current={i === at ? 'step' : undefined}>
          {s.label}
        </li>
      ))}
    </ol>
  )
}

type Props = { list: CardApplication[]; onChange: (next: CardApplication) => void }

export default function CardApplications({ list, onChange }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<{ id: string; text: string } | null>(null) // 실패는 그 신청 칸에만

  async function next(app: CardApplication, cancel = false) {
    if (cancel && !window.confirm(`${app.productName} 신청을 취소할까요? 필요하면 다시 신청할 수 있어요.`)) return
    setBusy(app.id)
    setError(null)
    const step = cancel ? cancelCardApplication : app.status === 'APPROVED' ? shipCard : app.status === 'SHIPPING' ? markDelivered : activateCard
    const r = await step(app.id)
    setBusy(null)
    if (!r.success) return setError({ id: app.id, text: r.error.message })
    onChange(r.data)
  }

  return (
    <ul className="acct-cards">
      {list.map((a) => (
        <li key={a.id} className="panel card-app">
          <div className="card-app-head">
            <img src={cardArtOf(a.productName, a.cardType)} alt="" className="card-thumb" />
            <span className="acct-card-main">
              <strong>{a.productName}</strong>
              <small>
                {CARD_TYPE_LABEL[a.cardType]} · {dots(a.appliedAt)} 신청{a.trackingNo && ` · 운송장 ${a.trackingNo}`}
              </small>
            </span>
          </div>
          <Steps app={a} />
          {a.deliveryAddress && <p className="prod-fine">받는 곳: {a.deliveryAddress}</p>}
          {a.status === 'APPROVED' && (
            <div className="card-app-actions">
              <p className="prod-fine">카드를 만들고 있어요. 배송이 시작되기 전까지 신청을 취소할 수 있어요.</p>
              <button type="button" className="btn-secondary" disabled={busy === a.id} onClick={() => void next(a)}>
                배송 시작으로 바꾸기 (시연용)
              </button>
              <button type="button" className="btn-secondary" disabled={busy === a.id} onClick={() => void next(a, true)}>
                신청 취소
              </button>
            </div>
          )}
          {a.status === 'SHIPPING' && (
            <div className="card-app-actions">
              <p className="prod-fine">배송 중에는 신청을 취소할 수 없어요. 받은 뒤 해지할 수 있어요.</p>
              <button type="button" className="btn-secondary" disabled={busy === a.id} onClick={() => void next(a)}>
                배송 완료로 바꾸기 (시연용)
              </button>
            </div>
          )}
          {a.status === 'DELIVERED' && (
            <div className="card-app-actions">
              <p className="prod-fine">카드를 받았다면 등록해 주세요. 등록하면 바로 쓸 수 있어요.</p>
              <button type="button" className="btn-primary" disabled={busy === a.id} onClick={() => void next(a)}>
                {busy === a.id ? '등록하는 중…' : '받은 카드 등록하기'}
              </button>
            </div>
          )}
          {error?.id === a.id && (
            <p className="field-msg is-error" role="alert">
              {error.text}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}
