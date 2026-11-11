// 예약 송금 · 자동이체 관리 (docs/기획서.md Part 5 8장, TRX-F10·F11) — 목록, 바꾸기(금액·날짜·시각·지정일), 취소·해지.
// 등록은 송금 화면의 재확인 단계에서 한다. 바꾸기·취소·해지는 실행 10분 전까지, 본인 확인(SCHEDULED_TRANSFER)을 받는다(사용자 결정 2026-11-09). 회원 탈퇴 ③ 「연결된 서비스」에서 이 화면으로 온다.
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import { cancelScheduledTransfer, getScheduledTransfers, updateScheduledTransfer, type ScheduledTransfer } from '../api'
import { digitsOnly, won } from '../productRules'
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
const DAYS = [...Array.from({ length: 28 }, (_, i) => i + 1), 99] // 99 = 말일
/** ISO(+09:00) → datetime-local 입력값 (YYYY-MM-DDTHH:mm, 한국 시각) */
const localInput = (iso: string | null) => (iso ? new Date(Date.parse(iso) + 9 * 3600_000).toISOString().slice(0, 16) : '')

const when = (s: ScheduledTransfer) =>
  s.type === 'MONTHLY'
    ? `매월 ${s.dayOfMonth === 99 ? '말일' : `${s.dayOfMonth}일`}`
    : s.executeAt
      ? new Date(s.executeAt).toLocaleString('ko-KR', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : ''

export default function ScheduledTransfersPage() {
  const [list, setList] = useState<ScheduledTransfer[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<{ id: string; op: 'edit' | 'cancel' } | null>(null)
  const [edit, setEdit] = useState({ amount: '', at: '', day: 1 })
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
    setOpen(null)
    setNotice(`${s.toHolderName}님께 보내는 ${s.type === 'MONTHLY' ? '자동이체를 해지' : '예약 송금을 취소'}했어요.`)
  }

  async function onEdit(e: FormEvent, s: ScheduledTransfer) {
    e.preventDefault()
    if (!Number(edit.amount)) return setFormError('1원 이상 입력해 주세요.')
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('SCHEDULED_TRANSFER')
    const b = s.type === 'ONCE' ? { amount: Number(edit.amount), executeAt: `${edit.at}:00+09:00` } : { amount: Number(edit.amount), dayOfMonth: edit.day }
    const r = ch.success ? await updateScheduledTransfer(s.id, b, ch.data) : ch
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setList((l) => (Array.isArray(l) ? l.map((x) => (x.id === s.id ? r.data : x)) : l))
    setOpen(null)
    setNotice(`${s.toHolderName}님께 보내는 ${s.type === 'MONTHLY' ? '자동이체' : '예약 송금'}을 바꿨어요.`)
  }

  function toggle(s: ScheduledTransfer, op: 'edit' | 'cancel') {
    setOpen(open?.id === s.id && open.op === op ? null : { id: s.id, op })
    setEdit({ amount: String(s.amount), at: localInput(s.executeAt), day: s.dayOfMonth ?? 1 })
    setFormError(null)
    auth.setValue('')
  }

  return (
    <AppShell title="예약·자동이체" current="#/transfer" busy={!list && !error}>
      <section className="prod-head">
        <h2 className="prod-title is-dup">예약·자동이체</h2>
        <p className="prod-sub">예약해 둔 송금과 매달 나가는 자동이체예요. 실행 10분 전까지 바꾸거나 취소할 수 있어요. 새 예약은 송금 화면에서 「예약하기」를 골라요.</p>
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
                    <>
                      <button type="button" className="btn-pill is-plain" aria-expanded={open?.id === s.id && open.op === 'edit'} onClick={() => toggle(s, 'edit')}>
                        바꾸기
                      </button>
                      <button type="button" className="btn-pill is-plain" aria-expanded={open?.id === s.id && open.op === 'cancel'} onClick={() => toggle(s, 'cancel')}>
                        {s.type === 'MONTHLY' ? '해지' : '취소'}
                      </button>
                    </>
                  )}
                </span>
                {open?.id === s.id && open.op === 'edit' && (
                  <form className="acct-menu-form prod-form" onSubmit={(e) => void onEdit(e, s)} noValidate>
                    <Field id={`sch-amount-${s.id}`} label="금액 (원)">
                      <input
                        id={`sch-amount-${s.id}`}
                        className="input"
                        inputMode="numeric"
                        value={edit.amount}
                        onChange={(e) => setEdit({ ...edit, amount: digitsOnly(e.target.value).slice(0, 13) })}
                      />
                    </Field>
                    {s.type === 'ONCE' ? (
                      <Field id={`sch-at-${s.id}`} label="보낼 날짜·시각 (10분 단위)">
                        <input id={`sch-at-${s.id}`} className="input" type="datetime-local" step={600} value={edit.at} onChange={(e) => setEdit({ ...edit, at: e.target.value })} />
                      </Field>
                    ) : (
                      <Field id={`sch-day-${s.id}`} label="매달 (오전 6시)">
                        <select id={`sch-day-${s.id}`} className="input" value={edit.day} onChange={(e) => setEdit({ ...edit, day: Number(e.target.value) })}>
                          {DAYS.map((d) => (
                            <option key={d} value={d}>
                              {d === 99 ? '말일' : `${d}일`}
                            </option>
                          ))}
                        </select>
                      </Field>
                    )}
                    <StepUpField auth={auth} id={`sch-edit-${s.id}`} message={formError ? { tone: 'error', text: formError } : null} />
                    <button className="btn-primary" type="submit" disabled={busy}>
                      {busy ? '처리 중…' : '바꾸기'}
                    </button>
                  </form>
                )}
                {open?.id === s.id && open.op === 'cancel' && (
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
