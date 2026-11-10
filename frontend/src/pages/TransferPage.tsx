// 송금 (docs/기획서.md Part 5 TRX-F01 · 5장 흐름) — 출금 계좌 → 받는 계좌 확인 → 금액·표시 이름 → 재확인 + 본인 확인 → 결과 화면
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import {
  BANK,
  BANKS,
  addFavorite,
  getAccounts,
  getFavorites,
  getRecentTargets,
  removeFavorite,
  updateFavorite,
  sendTransfer,
  verifyTransferTarget,
  type Account,
  type SavedTarget,
  type TransferTarget,
  type TransferWarning,
} from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import Icon from '../components/Icon'
import { digitsOnly, won } from '../productRules'
import { koreanWon, matchTargets } from '../transferRules'
import { ACCOUNT_ART } from './accountArt'
import logoMark from '../assets/logo-mark.png'
import './AccountPages.css'
import './ProductPages.css'
import './TransferPages.css'

const WARNING_TEXT: Record<TransferWarning, string> = {
  FIRST_LARGE: '처음 보내는 분에게 큰돈을 보내요. 금액을 한 번 더 확인해 주세요.',
  LARGE_VS_USUAL: '이 분께 평소 보내던 금액보다 훨씬 커요. 금액을 한 번 더 확인해 주세요.',
  RECENT_SAME: '방금 같은 분께 같은 금액을 보냈어요. 한 번 더 보낼까요?',
}
const NAME_MAX = 10 // 통장 표시 이름 (7장) — 서버도 다시 확인한다
const PICK_TABS = [
  { value: 'recent', label: '추천' },
  { value: 'fav', label: '자주' },
  { value: 'mine', label: '내 계좌' },
] as const
type PickTab = (typeof PICK_TABS)[number]['value']
type Pick = SavedTarget & { mine?: boolean }

// 같은 송금을 두 번 보내도 한 번만 나가게 하는 번호 (재확인 화면에 들어올 때 한 번 만든다)
const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`)

export default function TransferPage({ query }: { query: URLSearchParams }) {
  const [accounts, setAccounts] = useState<Account[] | 'guest' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'to' | 'amount' | 'confirm'>('to') // 한 화면에 질문 하나 — 누구에게 → 얼마 → 보낼까요
  const [fromId, setFromId] = useState(query.get('from') ?? '')
  const [bank, setBank] = useState(query.get('bank') ?? BANK) // 받는 은행 — 다른 은행은 가상 타행(Part 5 11장)
  const [toNo, setToNo] = useState(digitsOnly(query.get('to') ?? ''))
  const [target, setTarget] = useState<TransferTarget | null>(null)
  const [toError, setToError] = useState<string | null>(null)
  const [amount, setAmount] = useState(digitsOnly(query.get('amount') ?? ''))
  const [myName, setMyName] = useState('')
  const [theirName, setTheirName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const auth = useStepUp()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  // 간편 송금 (6장) — 최근 보낸 계좌 · 자주 쓰는 계좌 · 내 다른 계좌에서 고르기
  const [tab, setTab] = useState<PickTab>('recent')
  const [recent, setRecent] = useState<SavedTarget[]>([])
  const [favs, setFavs] = useState<SavedTarget[]>([])
  const [pickError, setPickError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false) // 자주 탭 편집 — 별칭·순서·빼기

  useEffect(() => {
    void Promise.all([getRecentTargets(), getFavorites()]).then(([r, f]) => {
      if (r.success) setRecent(r.data)
      if (f.success) setFavs(f.data)
      // 보낸 적이 없으면 빈 「추천」 대신 고를 게 있는 탭을 먼저 보여 준다
      if (r.success && r.data.length === 0) setTab(f.success && f.data.length > 0 ? 'fav' : 'mine')
      const failed = [r, f].find((x) => !x.success && x.error.code !== 'UNAUTHENTICATED')
      if (failed && !failed.success) setPickError(failed.error.message)
    })
  }, [])

  useEffect(() => {
    void getAccounts().then((r) => {
      if (!r.success) return r.error.code === 'UNAUTHENTICATED' ? setAccounts('guest') : setError(r.error.message)
      const usable = r.data.filter((a) => a.status === 'ACTIVE') // 정상 계좌만 (서버도 다시 확인한다)
      setAccounts(usable)
      setFromId((cur) => (usable.some((a) => a.id === cur) ? cur : (usable[0]?.id ?? '')))
    })
  }, [])

  const title = '송금'
  if (error || accounts === null)
    return (
      <AppShell title={title} current="#/transfer" busy={!error}>
        {error ? (
          <p className="home-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )
  if (accounts === 'guest')
    return (
      <AppShell title={title} current="#/transfer">
        <div className="panel empty">
          <p className="empty-title">송금하려면 로그인이 필요해요</p>
          <a className="btn-pill" href="#/login">
            로그인하기
          </a>
        </div>
      </AppShell>
    )

  const from = accounts.find((a) => a.id === fromId)
  const n = Number(amount)

  async function onVerify(no = toNo, b = bank) {
    if (!no) return setToError('받는 계좌번호를 입력해 주세요.')
    setToNo(no)
    setBank(b)
    setBusy(true)
    const r = await verifyTransferTarget(no, fromId, undefined, b)
    setBusy(false)
    if (!r.success) {
      setTarget(null)
      return setToError(r.error.message)
    }
    setToError(null)
    setTarget(r.data)
    setMyName(r.data.holderName) // 받는 분 실명을 미리 채우고 뒤에 메모만 덧붙이게 (7장)
    setStep('amount')
  }

  async function toggleFavorite(t: SavedTarget) {
    const on = favs.find((f) => f.accountNo === t.accountNo)
    if (on?.id) {
      const r = await removeFavorite(on.id)
      if (!r.success) return setPickError(r.error.message)
      setFavs(favs.filter((f) => f !== on))
    } else {
      const r = await addFavorite(t.accountNo)
      if (!r.success) return setPickError(r.error.message)
      setFavs([...favs, r.data])
    }
    setPickError(null)
  }

  async function patchFavorite(id: string, b: { nickname?: string | null; sortOrder?: number }) {
    const r = await updateFavorite(id, b)
    if (!r.success) return setPickError(r.error.message)
    setPickError(null)
    setFavs(r.data)
  }

  async function onNext(e: FormEvent) {
    e.preventDefault()
    if (!target) return setToError('받는 계좌를 먼저 확인해 주세요.')
    if (!n) return setFormError('1원 이상 입력해 주세요.')
    if (from && n > from.balance) return setFormError('잔액이 부족해요.')
    if (myName.trim().length > NAME_MAX || theirName.trim().length > NAME_MAX) return setFormError(`통장 표시 이름은 ${NAME_MAX}자까지예요.`)
    setBusy(true)
    const r = await verifyTransferTarget(target.accountNo, fromId, n, bank) // 재확인 화면 경고를 받는다
    setBusy(false)
    if (!r.success) return setFormError(r.error.message)
    setFormError(null)
    setTarget(r.data)
    setKey(newKey())
    setStep('confirm')
  }

  async function onSend(e: FormEvent) {
    e.preventDefault()
    if (!target) return
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('TRANSFER')
    if (!ch.success) {
      setBusy(false)
      return setFormError(ch.error.message)
    }
    const r = await sendTransfer(
      { fromAccountId: fromId, toBank: bank, toAccountNo: target.accountNo, amount: n, stepUpChallengeId: ch.data, myDisplayName: myName, theirDisplayName: theirName },
      key,
    )
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setFormError(r.error.message)
    location.hash = `#/transfers/${r.data.id}` // 성공·실패 모두 결과 화면에서 보여 준다
  }

  const warned = (target?.warnings.length ?? 0) > 0
  const mine: Pick[] = accounts
    .filter((a) => a.id !== fromId) // 출금 계좌는 빼고 (6장)
    .map((a) => ({ id: null, accountNo: digitsOnly(a.number), accountDisplay: a.number, holderName: a.name, nickname: null, mine: true }))
  const found = matchTargets([recent, favs], toNo)
  const shown: Pick[] = found.length ? found : tab === 'recent' ? recent : tab === 'fav' ? favs : mine
  const EMPTY: Record<PickTab, string> = {
    recent: '아직 보낸 계좌가 없어요. 한 번 보내면 여기에 떠요.',
    fav: '별을 누르면 자주 쓰는 계좌로 모아 둘 수 있어요.',
    mine: '옮길 수 있는 내 다른 계좌가 없어요.',
  }
  const QUICK = [10000, 50000, 100000, 1000000]
  const addAmount = (v: number) => {
    setAmount((a) => String(Math.min(Number(a || 0) + v, 9999999999999))) // 빨리 여러 번 눌러도 누른 만큼 더해지게
    setFormError(null)
  }
  // 이름 첫 글자 동그라미 — 사람마다 색이 달라 목록에서 빨리 찾게 (이름 글자 코드로 5색 중 하나)
  const avatar = (name: string, isMine?: boolean) => (
    <span className={`trf-avatar tone-${isMine ? 'mine' : [...name].reduce((h, c) => h + c.charCodeAt(0), 0) % 5}`} aria-hidden="true">
      {name.slice(0, 1)}
    </span>
  )
  const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '00', '0', 'del'] as const
  const press = (k: (typeof KEYS)[number]) => {
    setAmount((a) => (k === 'del' ? a.slice(0, -1) : digitsOnly(a + k).slice(0, 13)))
    setFormError(null)
  }
  // 오른쪽(PC) · 아래(휴대폰) 「보내는 내용」 영수증 — 단계를 지날수록 채워진다
  const receipt = from && (
    <aside className="panel trf-receipt" aria-label="보내는 내용">
      <p className="trf-receipt-title">보내는 내용</p>
      <div className="trf-receipt-from">
        <img src={ACCOUNT_ART[from.type]} alt="" />
        <span className="acct-card-main">
          <strong>{from.name}</strong>
          <small>
            {BANK} {from.number}
          </small>
        </span>
      </div>
      <dl className="trf-receipt-dl">
        <div>
          <dt>출금 가능</dt>
          <dd>{won(from.balance)}</dd>
        </div>
        <div>
          <dt>받는 분</dt>
          <dd>{target ? `${target.holderName}${target.isMine ? ' (내 계좌)' : ''}` : '아직 안 골랐어요'}</dd>
        </div>
        <div>
          <dt>보낼 금액</dt>
          <dd>{n > 0 ? won(n) : '—'}</dd>
        </div>
        <div>
          <dt>수수료</dt>
          <dd>0원</dd>
        </div>
        <div className="is-total">
          <dt>보낸 뒤 잔액</dt>
          <dd className={n > from.balance ? 'is-over' : undefined}>{n > 0 ? won(from.balance - n) : won(from.balance)}</dd>
        </div>
      </dl>
      <p className="prod-fine">다른 은행으로 보내도 수수료는 0원이에요.</p>
    </aside>
  )
  const toWho = target && (
    <div className="trf-who">
      {avatar(target.holderName, target.isMine)}
      <span className="acct-card-main">
        <strong>
          {target.holderName}
          {target.isMine ? ' (내 계좌)' : ''}
        </strong>
        <small>
          {bank} {target.accountDisplay}
        </small>
      </span>
    </div>
  )

  return (
    <AppShell title={title} current="#/transfer">
      {accounts.length === 0 ? (
        <div className="panel empty">
          <p className="empty-title">보낼 수 있는 계좌가 없어요</p>
          <p className="empty-sub">정상 상태의 내 계좌가 있어야 송금할 수 있어요.</p>
          <a className="btn-pill" href="#/accounts/new">
            계좌 만들기
          </a>
        </div>
      ) : (
        <div className="trf-layout">
          {step === 'to' ? (
        <div className="trf-step">
          <p className="trf-steps" aria-label="3단계 중 1단계">
            <span className="is-on" />
            <span />
            <span />
          </p>
          <h2 className="trf-q">누구에게 보낼까요?</h2>

          <fieldset className="trf-from-list">
            <legend className="field-label">보내는 계좌</legend>
            {accounts.map((a) => (
              <label key={a.id} className={`panel trf-from-card${a.id === fromId ? ' is-on' : ''}`}>
                <input
                  type="radio"
                  name="trf-from"
                  value={a.id}
                  checked={a.id === fromId}
                  onChange={() => {
                    setFromId(a.id)
                    setTarget(null) // 내 계좌가 바뀌면 같은 계좌인지 다시 확인한다
                  }}
                />
                <img src={ACCOUNT_ART[a.type]} alt="" className="trf-from-art" />
                <span className="acct-card-main">
                  <strong>{a.name}</strong>
                  <small>
                    {BANK} {a.number}
                  </small>
                </span>
                <strong className="trf-from-bal">{won(a.balance)}</strong>
              </label>
            ))}
          </fieldset>

          <div className="panel trf-to">
            <p className="field-label">받는 분 계좌</p>
            <div className="trf-bank">
              <img src={logoMark} alt="" width={36} height={36} />
              <Field id="trf-bank" label="받는 은행">
                <select
                  id="trf-bank"
                  className="input"
                  value={bank}
                  onChange={(e) => {
                    setBank(e.target.value)
                    setTarget(null) // 은행이 바뀌면 계좌를 다시 확인한다
                    setToError(null)
                  }}
                >
                  {BANKS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field id="trf-to" label="계좌번호" message={toError ? { tone: 'error', text: toError } : null}>
              <div className="trf-to-box">
                <input
                  id="trf-to"
                  className="input trf-to-input"
                  inputMode="numeric"
                  placeholder="숫자만 입력"
                  autoComplete="off"
                  value={toNo}
                  onChange={(e) => {
                    setToNo(digitsOnly(e.target.value).slice(0, 14))
                    setTarget(null)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      void onVerify()
                    }
                  }}
                  aria-invalid={!!toError}
                  aria-describedby="trf-to-msg"
                />
                {toNo && (
                  <button type="button" className="trf-clear" aria-label="계좌번호 지우기" onClick={() => setToNo('')}>
                    ×
                  </button>
                )}
                <button type="button" className="trf-verify" onClick={() => void onVerify()} disabled={busy || !toNo}>
                  {busy ? '확인 중…' : '확인'}
                </button>
              </div>
            </Field>
          </div>

          <div className="panel trf-pick-panel">
            <div className="trf-picks">
              {found.length ? (
                <p className="prod-fine">보낸 적 있는 계좌에서 찾았어요</p>
              ) : (
                <div className="trf-tabs-row">
                  <div className="prod-tabs" role="group" aria-label="받는 계좌 고르기">
                    {PICK_TABS.map((t) => (
                      <button
                        key={t.value}
                        type="button"
                        className="prod-chip"
                        aria-pressed={tab === t.value}
                        onClick={() => {
                          setTab(t.value)
                          setEditing(false)
                        }}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                  {tab === 'fav' && favs.length > 0 && (
                    <button type="button" className="trf-edit" onClick={() => setEditing(!editing)}>
                      {editing ? '완료' : '편집'}
                    </button>
                  )}
                </div>
              )}
              {pickError && (
                <p className="home-error" role="alert">
                  {pickError}
                </p>
              )}
              {shown.length === 0 ? (
                <div className="trf-empty">
                  <span className="trf-empty-icon" aria-hidden="true">
                    <Icon name={tab === 'fav' ? 'star' : tab === 'mine' ? 'wallet' : 'send'} size={24} />
                  </span>
                  <p>{EMPTY[tab]}</p>
                </div>
              ) : editing && !found.length && tab === 'fav' ? (
                <ul className="trf-pick-list">
                  {favs.map((f, i) => (
                    <li key={f.accountNo}>
                      {avatar(f.holderName)}
                      <span className="trf-pick">
                        <input
                          className="input trf-nick"
                          aria-label={`${f.holderName} 별칭`}
                          defaultValue={f.nickname ?? ''}
                          placeholder={`별칭 (예: ${f.holderName})`}
                          maxLength={20}
                          onBlur={(e) => {
                            const v = e.target.value.trim()
                            if (f.id && v !== (f.nickname ?? '')) void patchFavorite(f.id, { nickname: v || null })
                          }}
                        />
                        <small>
                          {f.holderName} · {BANK} {f.accountDisplay}
                        </small>
                      </span>
                      <button
                        type="button"
                        className="trf-star trf-up"
                        aria-label={`${f.holderName} 위로`}
                        disabled={i === 0}
                        onClick={() => f.id && void patchFavorite(f.id, { sortOrder: i - 1 })}
                      >
                        <Icon name="chevron" size={18} />
                      </button>
                      <button
                        type="button"
                        className="trf-star trf-down"
                        aria-label={`${f.holderName} 아래로`}
                        disabled={i === favs.length - 1}
                        onClick={() => f.id && void patchFavorite(f.id, { sortOrder: i + 1 })}
                      >
                        <Icon name="chevron" size={18} />
                      </button>
                      <button
                        type="button"
                        className="trf-star is-on"
                        aria-pressed
                        aria-label={`${f.holderName} 자주 쓰는 계좌에서 빼기`}
                        onClick={() => void toggleFavorite(f)}
                      >
                        <Icon name="star" size={20} />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="trf-pick-list">
                  {shown.map((t) => {
                    const fav = favs.some((f) => f.accountNo === t.accountNo)
                    return (
                      <li key={t.accountNo}>
                        <button type="button" className="trf-pick" onClick={() => void onVerify(t.accountNo, BANK)} disabled={busy}>
                          {avatar(t.holderName, t.mine)}
                          <span className="acct-card-main">
                            <strong>{t.nickname ? `${t.nickname} (${t.holderName})` : t.holderName}</strong>
                            <small>
                              {BANK} {t.accountDisplay}
                              {t.mine ? ' · 내 계좌' : ''}
                            </small>
                          </span>
                        </button>
                        {!t.mine && (
                          <button
                            type="button"
                            className={`trf-star${fav ? ' is-on' : ''}`}
                            aria-pressed={fav}
                            aria-label={`${t.holderName} 자주 쓰는 계좌`}
                            onClick={() => void toggleFavorite(t)}
                          >
                            <Icon name="star" size={20} />
                          </button>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : step === 'amount' && target ? (
        <form className="trf-step" onSubmit={onNext} noValidate>
          <p className="trf-steps" aria-label="3단계 중 2단계">
            <span className="is-on" />
            <span className="is-on" />
            <span />
          </p>
          <div className="panel trf-who-bar">
            {toWho}
            <button
              type="button"
              className="trf-edit"
              onClick={() => {
                setStep('to')
                setTarget(null)
                setFormError(null)
              }}
            >
              바꾸기
            </button>
          </div>
          <h2 className="trf-q">얼마를 보낼까요?</h2>
          <div className="panel trf-amount">
            <label htmlFor="trf-amount" className="visually-hidden">
              보낼 금액
            </label>
            <div className={`trf-amount-box${formError ? ' is-error' : ''}`}>
              <input
                id="trf-amount"
                className="trf-amount-input"
                inputMode="numeric"
                placeholder="0"
                value={amount ? n.toLocaleString('ko-KR') : ''}
                onChange={(e) => {
                  setAmount(digitsOnly(e.target.value).slice(0, 13))
                  setFormError(null) // 고친 금액에 지난 안내가 남지 않게
                }}
                aria-invalid={!!formError}
                aria-describedby="trf-amount-msg"
              />
              <span className="trf-amount-unit">원</span>
            </div>
            <p id="trf-amount-msg" className={formError ? 'field-msg is-error' : 'trf-amount-ko'} role={formError ? 'alert' : undefined}>
              {formError ?? (n > 0 ? koreanWon(n) : from ? `출금 가능 ${won(from.balance)} · ${from.name}에서` : '')}
            </p>
            <div className="trf-quick">
              {QUICK.map((v) => (
                <button key={v} type="button" className="prod-chip" onClick={() => addAmount(v)}>
                  +{v >= 10000 ? `${v / 10000}만` : v}
                </button>
              ))}
              {from && (
                <button
                  type="button"
                  className="prod-chip"
                  onClick={() => {
                    setAmount(String(from.balance))
                    setFormError(null)
                  }}
                >
                  전액
                </button>
              )}
              {n > 0 && (
                <button type="button" className="prod-chip" onClick={() => setAmount('')}>
                  지우기
                </button>
              )}
            </div>
            <div className="trf-keypad" role="group" aria-label="숫자 누르기">
              {KEYS.map((k) => (
                <button key={k} type="button" onClick={() => press(k)} aria-label={k === 'del' ? '한 글자 지우기' : k}>
                  {k === 'del' ? <Icon name="chevron" size={22} /> : k}
                </button>
              ))}
            </div>
          </div>
          <details className="panel trf-more">
            <summary>
              통장에 남길 이름 바꾸기 <Icon name="chevron" size={16} />
            </summary>
            <div className="trf-more-body">
              <Field id="trf-my-name" label={`내 통장에 남길 이름 (${NAME_MAX}자까지)`}>
                <input id="trf-my-name" className="input" value={myName} placeholder="받는 분 이름" onChange={(e) => setMyName(e.target.value)} />
              </Field>
              <Field id="trf-their-name" label={`받는 분 통장에 남길 이름 (${NAME_MAX}자까지)`}>
                <input id="trf-their-name" className="input" value={theirName} placeholder="비우면 내 이름" onChange={(e) => setTheirName(e.target.value)} />
              </Field>
            </div>
          </details>
          <button className="btn-primary" type="submit" disabled={busy || !n}>
            {busy ? '확인 중…' : '다음'}
          </button>
        </form>
      ) : (
        target && (
          <form className="trf-step" onSubmit={onSend} noValidate>
            <p className="trf-steps" aria-label="3단계 중 3단계">
              <span className="is-on" />
              <span className="is-on" />
              <span className="is-on" />
            </p>
            <div className="panel trf-confirm">
              {avatar(target.holderName, target.isMine)}
              <h2 className="trf-q">
                {target.holderName}님께
                <br />
                <span className={warned ? 'trf-big is-warn' : 'trf-big'}>{won(n)}</span>
                <br />
                보낼까요?
              </h2>
              <p className="trf-amount-ko">{koreanWon(n)}</p>
              {target.warnings.map((w) => (
                <p key={w} className="prod-warn" role="alert">
                  {WARNING_TEXT[w]}
                </p>
              ))}
              <dl className="prod-info trf-confirm-info">
                <div>
                  <dt>받는 계좌</dt>
                  <dd>
                    {bank} {target.accountDisplay}
                  </dd>
                </div>
                <div>
                  <dt>보내는 계좌</dt>
                  <dd>
                    {from?.name} {from?.number}
                  </dd>
                </div>
                <div>
                  <dt>수수료</dt>
                  <dd>0원</dd>
                </div>
                <div>
                  <dt>통장 표시 (내 쪽 · 받는 분 쪽)</dt>
                  <dd>
                    {myName.trim() || target.holderName} · {theirName.trim() || '내 이름'}
                  </dd>
                </div>
              </dl>
            </div>
            <div className="panel trf-auth">
              <StepUpField auth={auth} id="trf-password" message={formError ? { tone: 'error', text: formError } : null} />
            </div>
            <div className="trf-actions">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setStep('amount')
                  setFormError(null)
                }}
                disabled={busy}
              >
                고치기
              </button>
              <button className="btn-primary" type="submit" disabled={busy}>
                {busy ? '보내는 중…' : `${won(n)} 보내기`}
              </button>
            </div>
          </form>
        )
          )}
          {receipt}
        </div>
      )}
    </AppShell>
  )
}
