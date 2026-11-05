// 체크카드 신청 (docs/기획서.md Part 4 CARD-F05 1-2) — ① 카드 고르기 ② 출금 계좌·받을 주소 ③ 약관 ④ 본인 확인 → 배송 시작
// 신용카드 발급(모의 심사·한도)은 2차라 고를 수 없게 보여 준다.
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { Steps } from './CardApplications'
import { applyCard, getAccounts, getCardProducts, getMyCards, type Account, type CardApplication, type CardProduct } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import { won } from '../productRules'
import { cardArtOf } from './cardArt'
import './ProductPages.css'
import './AccountPages.css'
import './CardPages.css'

export default function CardApplyPage() {
  const [products, setProducts] = useState<CardProduct[] | null>(null)
  const [held, setHeld] = useState<string[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [productId, setProductId] = useState('')
  const [accountId, setAccountId] = useState('')
  const [address, setAddress] = useState('')
  const [agreed, setAgreed] = useState<string[]>([])
  const auth = useStepUp()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<CardApplication | null>(null)
  const [key] = useState(() => crypto.randomUUID()) // 다시 눌러도 신청이 하나만 생기게 — 이 화면에서 한 번 만든 번호를 계속 쓴다

  useEffect(() => {
    void getCardProducts().then((r) => {
      if (!r.success) return setError(r.error.message)
      setProducts(r.data)
    })
    void getMyCards().then((r) => r.success && setHeld(r.data.map((c) => c.productName)))
    void getAccounts().then((r) => {
      if (!r.success) return
      const ok = r.data.filter((a) => a.type === 'CHECKING' && a.status === 'ACTIVE') // 카드는 정상 입출금 계좌에만 연결된다
      setAccounts(ok)
      setAccountId((id) => id || (ok[0]?.id ?? ''))
    })
  }, [])

  const checks = (products ?? []).filter((p) => p.cardType === 'CHECK')
  const credits = (products ?? []).filter((p) => p.cardType === 'CREDIT')
  // 고르기 전에는 아직 없는 카드 중 첫 번째 — 이미 가진 카드는 고를 수 없다
  const selected = productId || checks.find((p) => !held.includes(p.name))?.id
  const chosen = checks.find((p) => p.id === selected && !held.includes(p.name))

  function pick(id: string) {
    setProductId(id)
    setAgreed([])
    setError(null)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!chosen) return setError('신청할 카드를 골라 주세요.')
    if (!accountId) return setError('출금 계좌를 골라 주세요.')
    if (address.trim().length < 5) return setError('카드를 받을 주소를 5자 이상 적어 주세요.')
    if (chosen.terms.some((t) => t.required && !agreed.includes(t.id))) return setError('필수 약관에 동의해 주세요.')
    if (auth.missing) return setError(auth.missing)
    setBusy(true)
    const ch = await auth.verify('CARD_APPLICATION')
    const r = ch.success ? await applyCard({ productId: chosen.id, accountId, address: address.trim(), agreedTermIds: agreed, stepUpChallengeId: ch.data }, key) : ch
    setBusy(false)
    auth.setValue('')
    if (!r.success) return setError(r.error.message)
    setDone(r.data)
  }

  if (done)
    return (
      <AppShell title="카드 신청" current="#/cards">
        <section className="panel acct-done card-done" aria-live="polite">
          <img src={cardArtOf(done.productName, done.cardType)} alt="" className="card-done-art" />
          <h2 className="acct-done-title">{done.productName}를 보내기 시작했어요</h2>
          <p className="acct-done-number">운송장 {done.trackingNo} · 출금 계좌 {done.linkedAccountNumber}</p>
          <Steps app={done} />
          <p className="prod-fine">카드를 받으면 「내 카드」에서 등록해 주세요. 등록하면 바로 쓸 수 있어요.</p>
          <div className="acct-done-actions">
            <a className="btn-hero is-primary" href="#/cards">
              배송 조회
            </a>
            <a className="btn-hero" href="#/home">
              홈으로
            </a>
          </div>
        </section>
      </AppShell>
    )

  return (
    <AppShell title="카드 신청" current="#/cards" busy={!products && !error}>
      <a className="more prod-back" href="#/cards">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        내 카드
      </a>

      <form className="acct-open" onSubmit={onSubmit} noValidate>
        <fieldset className="acct-types card-types">
          <legend className="acct-open-title">어떤 체크카드를 만들까요?</legend>
          {!products && !error && <p className="home-loading">불러오는 중…</p>}
          {checks.map((p) => {
            const mine = held.includes(p.name)
            return (
              <label key={p.id} className={`panel acct-type card-type${selected === p.id ? ' is-on' : ''}${mine ? ' is-held' : ''}`}>
                <input type="radio" name="product" value={p.id} checked={selected === p.id} disabled={mine} onChange={() => pick(p.id)} />
                <span className="acct-type-check" aria-hidden="true" />
                <img src={cardArtOf(p.name, p.cardType)} alt="" className="card-type-art" />
                <strong className="acct-type-name">{p.name}</strong>
                <span className="acct-type-desc">
                  {p.companyName} · 연회비 {p.annualFee > 0 ? won(p.annualFee) : '없음'} · 만 {p.minAge}세부터
                  {mine && ' · 이미 가지고 있어요'}
                </span>
                <ul className="acct-type-points">
                  {p.benefits.map((b) => (
                    <li key={b.category}>
                      {b.category} {b.rate}%
                    </li>
                  ))}
                </ul>
              </label>
            )
          })}
        </fieldset>
        {credits.length > 0 && (
          <p className="prod-fine">신용카드({credits.map((p) => p.name).join(', ')}) 발급은 심사 기능과 함께 다음 단계에서 열려요.</p>
        )}

        <section className="panel acct-open-sum" aria-label="신청 정보">
          <h3>신청 정보</h3>
          {accounts.length === 0 ? (
            <div className="prod-form">
              <p className="prod-sub">체크카드는 정상 입출금 계좌에 연결돼요. 먼저 계좌를 만들어 주세요.</p>
              <a className="btn-pill" href="#/accounts/new">
                <Icon name="plus" size={16} />
                입출금 계좌 만들기
              </a>
            </div>
          ) : (
            <Field id="apply-account" label="출금 계좌 — 카드로 쓴 돈이 바로 빠져나가요">
              <select id="apply-account" className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.number} · {won(a.balance)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field id="apply-address" label="카드 받을 주소">
            <input id="apply-address" className="input" maxLength={100} value={address} placeholder="예) 서울시 중구 세종대로 1" onChange={(e) => setAddress(e.target.value)} />
          </Field>
          {chosen?.terms.map((t) => (
            <label key={t.id} className="check acct-consent">
              <input
                type="checkbox"
                checked={agreed.includes(t.id)}
                onChange={(e) => setAgreed((list) => (e.target.checked ? [...list, t.id] : list.filter((x) => x !== t.id)))}
              />
              <span>
                <em className="tag-required">{t.required ? '필수' : '선택'}</em>
                {t.title}에 동의해요 (모의 서비스)
              </span>
            </label>
          ))}
          <StepUpField auth={auth} id="apply-password" message={error ? { tone: 'error', text: error } : null} />
          <button className="btn-primary" type="submit" disabled={busy || accounts.length === 0 || !chosen}>
            {busy ? '신청하는 중…' : chosen ? `${chosen.name} 신청하기` : '카드를 골라 주세요'}
          </button>
          <p className="prod-fine">체크카드는 심사 없이 바로 만들어 보내요. 배송이 시작되면 신청을 취소할 수 없고, 받은 뒤 해지할 수 있어요.</p>
        </section>
      </form>
    </AppShell>
  )
}
