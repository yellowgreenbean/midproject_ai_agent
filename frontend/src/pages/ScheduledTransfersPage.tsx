// 예약 송금 · 자동이체 관리 (docs/기획서.md Part 5 8장) — 목록과 취소·해지. 등록·변경은 아직 없다.
// 취소·해지는 본인 확인(SCHEDULED_TRANSFER)을 받는다(사용자 결정 2026-11-09). 회원 탈퇴 ③ 「연결된 서비스」에서 이 화면으로 온다.
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import { cancelScheduledTransfer, getScheduledTransfers, type ScheduledTransfer } from '../api'
import { won } from '../productRules'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import './ProductPages.css'
import './TransferPages.css'

const STATUS: Record<string, string> = {
  SCHEDULED: '예약됨',
  PROCESSING: '보내는 중',
  SUCCESS: '보냄',
  FAILED: '실패',
  CANCELED: '취소됨',
  ACTIVE: '자동이체 중',
  PAUSED: '잠시 멈춤',
}
const CANCELABLE = ['SCHEDULED', 'ACTIVE', 'PAUSED']

const when = (s: ScheduledTransfer) =>
  s.type === 'MONTHLY'
    ? `매월 ${s.dayOfMonth === 99 ? '말일' : `${s.dayOfMonth}일`}`
    : s.executeAt
      ? new Date(s.executeAt).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : ''

export default function ScheduledTransfersPage() {
  const [list, setList] = useState<ScheduledTransfer[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const auth = useStepUp()

  useEffect(() => {
    void getScheduledTransfers().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setList('guest') : setError(r.error.message)
      setList(r.data)
    })
  }, [])

  async function onCancel(e: FormEvent, s: ScheduledTransfer) {
    e.preventDefault()
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('SCHEDULED_TRANSFER')
    const r = ch.success ? await cancelScheduledTransfer(s.id, ch.data) : ch
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setList((l) => (Array.isArray(l) ? l.map((x) => (x.id === s.id ? r.data : x)) : l))
    setOpenId(null)
    setNotice(`${s.toHolderName}님께 보내는 ${s.type === 'MONTHLY' ? '자동이체를 해지' : '예약 송금을 취소'}했어요.`)
  }

  return (
    <AppShell title="예약·자동이체" current="#/transfer" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title is-dup">예약·자동이체</h2>
        <p className="prod-sub">예약해 둔 송금과 매달 나가는 자동이체예요. 취소·해지하면 더 이상 돈이 나가지 않아요.</p>
      </section>
      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list === 'guest' && (
        <div className="panel empty">
          <p className="empty-title">로그인하면 예약·자동이체가 여기에 보여요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      )}
      {Array.isArray(list) &&
        (list.length === 0 ? (
          <div className="panel empty">
            <p className="empty-title">예약·자동이체가 없어요</p>
          </div>
        ) : (
          <ul className="panel rows">
            {list.map((s) => (
              <li key={s.id}>
                <div className="row-main">
                  <strong>
                    {s.type === 'MONTHLY' ? '자동이체' : '예약 송금'} · {s.toHolderName}
                  </strong>
                  <small>
                    {when(s)} · {s.toBank} {s.toAccountNo} · {STATUS[s.status] ?? s.status}
                  </small>
                </div>
                <span className="trf-item-side">
                  <strong className="row-amount">{won(s.amount)}</strong>
                  {CANCELABLE.includes(s.status) && (
                    <button
                      type="button"
                      className="btn-pill is-plain"
                      aria-expanded={openId === s.id}
                      onClick={() => {
                        setOpenId(openId === s.id ? null : s.id)
                        setFormError(null)
                        auth.setValue('')
                      }}
                    >
                      {s.type === 'MONTHLY' ? '해지' : '취소'}
                    </button>
                  )}
                </span>
                {openId === s.id && (
                  <form className="acct-menu-form prod-form" onSubmit={(e) => void onCancel(e, s)} noValidate>
                    <StepUpField auth={auth} id={`sch-${s.id}`} message={formError ? { tone: 'error', text: formError } : null} />
                    <button className="btn-primary is-danger" type="submit" disabled={busy}>
                      {busy ? '처리 중…' : s.type === 'MONTHLY' ? '자동이체 해지하기' : '예약 취소하기'}
                    </button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        ))}
    </AppShell>
  )
}
