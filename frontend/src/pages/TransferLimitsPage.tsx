// 이체 한도 (docs/기획서.md Part 5 TRX-F07 확인 · TRX-F13 변경) — 계좌마다 1회·1일 한도. 내리기는 바로, 올리기는 비밀번호 한 번 더.
// 범위·단위 검사는 서버가 한다(1만 원 단위 · 1회 1억 · 1일 5억 · 1회 ≤ 1일) — 화면은 서버 문장을 그대로 보여 준다
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { getTransferLimits, setTransferLimit, type TransferLimit } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { digitsOnly, won } from '../productRules'
import { koreanWon } from '../transferRules'
import './ProductPages.css'
import './SettingsPages.css'

export default function TransferLimitsPage() {
  const [list, setList] = useState<TransferLimit[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)

  useEffect(() => {
    void getTransferLimits().then((r) => (r.success ? setList(r.data) : r.error.code === 'UNAUTHENTICATED' ? (location.hash = '#/login') : setError(r.error.message)))
  }, [])

  const saved = (l: TransferLimit) => {
    setList((xs) => xs && xs.map((x) => (x.accountId === l.accountId ? l : x)))
    setEditing(null)
  }

  return (
    <AppShell title="이체 한도" current="#/settings" busy={!list && !error}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      <section className="prod-head">
        <h2 className="prod-title is-dup">이체 한도</h2>
        <p className="prod-sub">한 번에, 하루에 보낼 수 있는 금액이에요. 한도를 올릴 때는 비밀번호를 한 번 더 확인해요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list?.length === 0 && (
        <div className="panel empty">
          <p className="empty-title">한도를 정할 계좌가 없어요</p>
          <a className="btn-pill" href="#/accounts/new">
            계좌 만들기
          </a>
        </div>
      )}
      {list && list.length > 0 && (
        <ul className="set-limits">
          {list.map((l) => (
            <li key={l.accountId} className="panel set-limit">
              <div className="set-limit-head">
                <strong>{l.accountName}</strong>
                <small>{l.accountNumber}</small>
                {l.isDefault && <span className="set-chip">기본 한도</span>}
              </div>
              {editing === l.accountId ? (
                <LimitForm limit={l} onSaved={saved} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <dl className="set-info">
                    <div>
                      <dt>1회 한도</dt>
                      <dd>{won(l.perTransfer)}</dd>
                    </div>
                    <div>
                      <dt>1일 한도</dt>
                      <dd>{won(l.daily)}</dd>
                    </div>
                    <div>
                      <dt>오늘 남은 한도</dt>
                      <dd>{won(Math.max(0, l.daily - l.usedToday))}</dd>
                    </div>
                  </dl>
                  <button type="button" className="btn-pill is-plain" onClick={() => setEditing(l.accountId)}>
                    한도 바꾸기
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="prod-fine">한도는 1만 원 단위로 1회 최대 1억 원, 1일 최대 5억 원까지 정할 수 있어요. 정하지 않으면 1회 500만 원, 1일 1,000만 원이에요.</p>
    </AppShell>
  )
}

function LimitForm({ limit, onSaved, onCancel }: { limit: TransferLimit; onSaved: (l: TransferLimit) => void; onCancel: () => void }) {
  const [per, setPer] = useState(String(limit.perTransfer))
  const [daily, setDaily] = useState(String(limit.daily))
  const auth = useStepUp()
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const p = Number(per)
  const d = Number(daily)
  const raising = p > limit.perTransfer || d > limit.daily
  const id = limit.accountId

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (raising && auth.missing) return setFormError(auth.missing)
    setBusy(true)
    setFormError(null)
    const ch = raising ? await auth.verify('PROFILE_CHANGE') : null
    const r = ch && !ch.success ? ch : await setTransferLimit(id, p, d, ch?.data)
    setBusy(false)
    if (r.success) onSaved(r.data)
    else setFormError(r.error.message)
  }

  const amountInput = (key: string, label: string, value: string, set: (v: string) => void) => {
    const n = Number(value)
    return (
      <Field id={`${key}-${id}`} label={label} message={n > 0 ? { tone: 'ok', text: koreanWon(n) } : null}>
        <input
          id={`${key}-${id}`}
          className="input"
          inputMode="numeric"
          value={value ? n.toLocaleString('ko-KR') : ''}
          onChange={(e) => set(digitsOnly(e.target.value).slice(0, 9))} // 최대 5억 = 9자리
          aria-describedby={`${key}-${id}-msg`}
        />
      </Field>
    )
  }

  return (
    <form className="set-limit-form prod-form" onSubmit={onSubmit} noValidate>
      {amountInput('lim-per', '1회 한도 (원)', per, setPer)}
      {amountInput('lim-daily', '1일 한도 (원)', daily, setDaily)}
      {raising && (
        <StepUpField auth={auth} id={`lim-pw-${id}`} message={null} />
      )}
      {formError && (
        <p className="home-error" role="alert">
          {formError}
        </p>
      )}
      <div className="set-limit-actions">
        <button type="button" className="btn-pill is-plain" onClick={onCancel}>
          취소
        </button>
        <button className="btn-primary" type="submit" disabled={busy || !p || !d}>
          {busy ? '저장하는 중…' : '저장'}
        </button>
      </div>
    </form>
  )
}
