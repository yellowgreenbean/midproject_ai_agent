// 계좌 상세 (docs/기획서.md Part 2 ACCT-F02~F06) — 잔액 새로고침 · 별명·즐겨찾기 · 입출금 알림 · 일시정지·해제·해지
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import AccountTransactions from './AccountTransactions'
import AccountTransfers from './AccountTransfers'
import { changeAccountStatus, getAccount, getBalance, setAccountNotifications, updateAccountPreferences, type AccountDetail } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { won, ymd } from '../productRules'
import { ACCOUNT_ART, ACCOUNT_STATUS_LABEL, ACCOUNT_TYPE_LABEL, BLOCKER, stamp } from './accountArt'
import './ProductPages.css'
import './AccountPages.css'

type Op = 'suspend' | 'resume' | 'close'
const OP: Record<Op, { label: string; note: string; done: string }> = {
  suspend: {
    label: '일시정지',
    note: '정지하면 이 계좌로 돈이 들어오지도 나가지도 않아요(이체·카드 결제·적금 납입 포함). 잔액 확인과 정지 해제는 할 수 있어요.',
    done: '계좌를 일시정지했어요.',
  },
  resume: { label: '정지 해제', note: '정지를 풀면 다시 입금·출금을 할 수 있어요.', done: '정지를 해제했어요.' },
  close: { label: '계좌 해지', note: '해지하면 다시 쓸 수 없어요. 거래 기록은 남고, 목록의 「해지한 계좌」에서 볼 수 있어요.', done: '계좌를 해지했어요.' },
}

export default function AccountDetailPage({ id }: { id: string }) {
  const [a, setA] = useState<AccountDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [balanceError, setBalanceError] = useState<string | null>(null)
  const [op, setOp] = useState<Op | null>(null)
  const [editing, setEditing] = useState(false)
  const [nickname, setNickname] = useState('')
  const auth = useStepUp()
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    void getAccount(id).then((r) => (r.success ? setA(r.data) : setError(r.error.message)))
  }, [id])

  if (!a)
    return (
      <AppShell title="계좌 상세" current="#/accounts" busy={!error}>
        {error ? (
          <div className="panel empty">
            <p className="empty-title">{error}</p>
            <a className="btn-pill" href={error.includes('로그인') ? '#/login' : '#/accounts'}>
              {error.includes('로그인') ? '로그인하기' : '내 계좌로'}
            </a>
          </div>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )

  const closed = a.status === 'CLOSED'

  function show(next: AccountDetail, message: string) {
    setA(next)
    setNotice(message)
  }

  async function refresh() {
    setBalanceError(null)
    const r = await getBalance(id)
    if (!r.success) return setBalanceError('현재 잔액을 불러오지 못했어요. 다시 시도해 주세요.')
    setA((x) => x && { ...x, ...r.data })
  }

  async function toggle(kind: 'favorite' | 'alerts') {
    if (!a) return
    setNotice(null)
    const r = kind === 'favorite' ? await updateAccountPreferences(id, { isFavorite: !a.isFavorite }) : await setAccountNotifications(id, !a.notificationsEnabled)
    if (!r.success) return setNotice(r.error.message)
    const on = kind === 'favorite' ? r.data.isFavorite : r.data.notificationsEnabled
    show(r.data, kind === 'favorite' ? (on ? '즐겨찾기에 넣었어요.' : '즐겨찾기에서 뺐어요.') : on ? '입출금 알림을 켰어요.' : '입출금 알림을 껐어요.')
  }

  async function onRename(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const r = await updateAccountPreferences(id, { nickname })
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setEditing(false)
    show(r.data, r.data.nickname ? '별명을 바꿨어요.' : '기본 이름으로 되돌렸어요.')
  }

  function start(next: Op | null) {
    setOp(next)
    setEditing(false)
    auth.setValue('')
    setFormError(null)
    setNotice(null)
  }

  async function onStatus(e: FormEvent) {
    e.preventDefault()
    if (!op) return
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('ACCOUNT_STATUS_CHANGE')
    const r = ch.success ? await changeAccountStatus(id, op, ch.data) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    show(r.data, OP[op].done)
    setOp(null)
  }

  const blocked = op === 'close' && a.closeBlockers.length > 0

  return (
    <AppShell title="계좌 상세" current="#/accounts">
      <a className="more prod-back" href="#/accounts">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        내 계좌
      </a>

      <section className={`panel acct-hero is-${a.type.toLowerCase()}`} aria-labelledby="acct-name">
        <img src={ACCOUNT_ART[a.type]} alt="" className="acct-hero-art" />
        <div className="acct-hero-text">
          <span className="acct-hero-tags">
            <span className="pc-tag">{ACCOUNT_TYPE_LABEL[a.type]}</span>
            {a.status !== 'ACTIVE' && <span className="acct-badge">{ACCOUNT_STATUS_LABEL[a.status] ?? a.status}</span>}
          </span>
          <h2 id="acct-name">
            {a.name}
            {!closed && (
              <button
                type="button"
                className={`acct-fav${a.isFavorite ? ' is-on' : ''}`}
                aria-pressed={a.isFavorite}
                aria-label="즐겨찾기"
                onClick={() => void toggle('favorite')}
              >
                <Icon name="star" size={22} />
              </button>
            )}
          </h2>
          <p className="prod-sub">두린은행 {a.number}</p>
        </div>
        <div className="acct-hero-bal">
          <strong className="acct-balance">{won(a.balance)}</strong>
          <p className="prod-hero-base">
            {stamp(a.balanceAsOf)} 기준
            {!closed && (
              <button type="button" className="acct-link" onClick={() => void refresh()}>
                새로고침
              </button>
            )}
          </p>
          {balanceError && (
            <p className="field-msg is-error" role="alert">
              {balanceError}
            </p>
          )}
        </div>
        {!closed && (
          <div className="acct-hero-actions">
            {a.status === 'ACTIVE' && (
              <a className="btn-hero is-primary" href={`#/transfer?from=${a.id}`}>
                <Icon name="send" size={18} />
                송금
              </a>
            )}
            {/* 내역은 이 화면 아래에 있다 — 주소(#)를 바꾸면 화면 이동이 되므로 스크롤만 한다 */}
            <button type="button" className="btn-hero acct-hero-btn" onClick={() => document.getElementById('acct-history')?.scrollIntoView({ behavior: 'smooth' })}>
              <Icon name="list" size={18} />
              거래내역
            </button>
          </div>
        )}
      </section>

      {notice && (
        <p className="prod-ok" role="status">
          {notice}
        </p>
      )}
      {a.status === 'SUSPENDED' && <p className="prod-warn">일시정지된 계좌예요. 정지를 해제하기 전까지는 입금·출금이 모두 막혀요.</p>}
      {closed && <p className="prod-warn">해지한 계좌예요. 기록만 볼 수 있어요.</p>}

      <div className="acct-body">
        <div>
          <AccountTransactions id={id} />
          <AccountTransfers id={id} />
        </div>
        <div className="acct-side">
      <section aria-labelledby="acct-info">
        <h2 id="acct-info" className="section-title">
          <span className="section-icon">
            <Icon name="wallet" size={18} />
          </span>
          계좌 정보
        </h2>
        <dl className="panel prod-info">
          <div>
            <dt>계좌번호</dt>
            <dd>두린은행 {a.number}</dd>
          </div>
          <div>
            <dt>계좌 종류</dt>
            <dd>{ACCOUNT_TYPE_LABEL[a.type]}</dd>
          </div>
          {a.nickname && (
            <div>
              <dt>기본 이름</dt>
              <dd>{a.defaultName}</dd>
            </div>
          )}
          <div>
            <dt>개설일</dt>
            <dd>{ymd(a.startDate)}</dd>
          </div>
          {a.closedAt && (
            <div>
              <dt>해지일</dt>
              <dd>{ymd(a.closedAt)}</dd>
            </div>
          )}
        </dl>
      </section>

      {!closed && (
        <section aria-labelledby="acct-settings" className="prod-manage">
          <h2 id="acct-settings" className="section-title">
            <span className="section-icon">
              <Icon name="settings" size={18} />
            </span>
            설정
          </h2>
          <ul className="panel acct-menu">
            <li>
              <button
                type="button"
                aria-expanded={editing}
                onClick={() => {
                  start(null)
                  setEditing(!editing)
                  setNickname(a.nickname ?? '')
                }}
              >
                <span className="acct-menu-label">별명</span>
                <span className="acct-menu-value">{a.nickname ?? '없음'}</span>
                <Icon name="chevron" size={18} />
              </button>
              {editing && (
                <form className="acct-menu-form prod-form" onSubmit={onRename} noValidate>
                  <Field id="acct-nickname" label="별명 (30자까지 · 비우면 기본 이름)" message={formError ? { tone: 'error', text: formError } : null}>
                    <input
                      id="acct-nickname"
                      className="input"
                      maxLength={30}
                      value={nickname}
                      placeholder={a.defaultName}
                      onChange={(e) => {
                        setNickname(e.target.value)
                        setFormError(null)
                      }}
                      aria-invalid={!!formError}
                      aria-describedby="acct-nickname-msg"
                    />
                  </Field>
                  <div className="prod-actions">
                    <button className="btn-primary" type="submit" disabled={busy}>
                      저장
                    </button>
                    <button className="btn-secondary" type="button" onClick={() => setEditing(false)}>
                      취소
                    </button>
                  </div>
                </form>
              )}
            </li>
            <li>
              <button type="button" role="switch" aria-checked={a.notificationsEnabled} onClick={() => void toggle('alerts')}>
                <span className="acct-menu-label">입출금 알림</span>
                <span className="acct-switch" aria-hidden="true" />
              </button>
            </li>
          </ul>

          <h2 className="section-title">
            <span className="section-icon">
              <Icon name="safe" size={18} />
            </span>
            계좌 관리
          </h2>
          <ul className="panel acct-menu">
            {(a.status === 'ACTIVE' ? (['suspend', 'close'] as const) : (['resume'] as const)).map((o) => (
              <li key={o}>
                <button type="button" className={o === 'close' ? 'is-danger' : undefined} aria-expanded={op === o} onClick={() => start(op === o ? null : o)}>
                  <span className="acct-menu-label">{OP[o].label}</span>
                  <Icon name="chevron" size={18} />
                </button>
                {op === o && blocked && (
                  <div className="acct-menu-form" role="alert">
                    <p className="empty-title">지금은 해지할 수 없어요</p>
                    <ul className="acct-blockers">
                      {a.closeBlockers.map((b) => (
                        <li key={b}>
                          {BLOCKER[b].text}{' '}
                          {BLOCKER[b].href && (
                            <a className="more" href={BLOCKER[b].href}>
                              {BLOCKER[b].link} <Icon name="chevron" size={14} />
                            </a>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {op === o && !blocked && (
                  <form className="acct-menu-form prod-form" onSubmit={onStatus} noValidate>
                    <p className="prod-warn" role="note">
                      {OP[o].note}
                    </p>
                    <StepUpField auth={auth} id="acct-password" message={formError ? { tone: 'error', text: formError } : null} />
                    <button className="btn-primary" type="submit" disabled={busy}>
                      {busy ? '처리 중…' : OP[o].label}
                    </button>
                  </form>
                )}
              </li>
            ))}
          </ul>
          {a.status === 'SUSPENDED' && <p className="prod-fine">일시정지된 계좌는 정지를 해제한 뒤에 해지할 수 있어요.</p>}
        </section>
      )}
        </div>
      </div>
    </AppShell>
  )
}
