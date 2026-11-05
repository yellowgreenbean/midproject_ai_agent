// 상품 상세 + 예상 이자 (docs/기획서.md Part 3 PROD-F02·F04·F05·F06) — 로그인 없이 볼 수 있다
import { useEffect, useState, type FormEvent } from 'react'
import AppShell from '../components/AppShell'
import Field from '../components/Field'
import Icon from '../components/Icon'
import { estimateInterest, getProduct, type Estimate, type ProductDetail } from '../api'
import { defaultMonths, digitsOnly, isDayUnit, monthOptions, won, ymd } from '../productRules'
import { PRODUCT_ART, TYPE_CLASS, TYPE_LABEL } from './productArt'
import './ProductPages.css'

export default function ProductDetailPage({ id }: { id: string }) {
  const [p, setP] = useState<ProductDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [amount, setAmount] = useState('')
  const [months, setMonths] = useState(0)
  const [days, setDays] = useState('')
  const [est, setEst] = useState<Estimate | null>(null)
  const [estError, setEstError] = useState<string | null>(null)

  useEffect(() => {
    void getProduct(id).then((r) => {
      if (!r.success) return setError(r.error.message)
      setP(r.data)
      setMonths(defaultMonths(monthOptions(r.data)))
    })
  }, [id])

  if (!p)
    return (
      <AppShell title="상품 상세" current="#/products" busy={!error}>
        {error ? (
          <p className="home-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="home-loading">불러오는 중…</p>
        )}
      </AppShell>
    )

  const deposit = p.type === 'TIME_DEPOSIT'
  const what = deposit ? '예치금' : '월 납입액'
  const options = monthOptions(p)
  const byDay = isDayUnit(p)
  const unit = byDay ? '일' : '개월'
  const bestRate = Math.max(...p.rates.map((r) => Number(r.baseRate))) // 금리표가 비면 -Infinity → 아무 줄도 표시 안 함

  async function onEstimate(e: FormEvent) {
    e.preventDefault()
    setEst(null)
    if (!amount) return setEstError(`${what}을 입력해 주세요.`)
    const r = await estimateInterest(id, Number(amount), byDay ? { months: 0, days: Number(days) } : { months })
    if (!r.success) return setEstError(r.error.message)
    setEstError(null)
    setEst(r.data)
  }

  const range =
    p.minAmount || p.maxAmount
      ? `${p.minAmount ? won(p.minAmount) + ' 이상' : ''}${p.minAmount && p.maxAmount ? ' ~ ' : ''}${p.maxAmount ? won(p.maxAmount) + ' 이하' : ''}`
      : '확인 필요'

  return (
    <AppShell title="상품 상세" current="#/products">
      <a className="more prod-back" href="#/products">
        <span className="prod-back-icon">
          <Icon name="chevron" size={14} />
        </span>
        상품 목록
      </a>

      <section className={`panel prod-hero ${TYPE_CLASS[p.type]}`} aria-labelledby="prod-name">
        <img src={PRODUCT_ART[p.type]} alt="" className="prod-hero-art" />
        <div className="prod-hero-text">
          <span className="pc-tag prod-hero-tag">두린은행 · {TYPE_LABEL[p.type]}</span>
          <h2 id="prod-name">{p.name}</h2>
          {p.description && <p className="prod-sub">{p.description}</p>}
        </div>
        <div className="prod-hero-rate">
          <p className="pc-rate">
            {p.maxRate ? (
              <>
                <small>최고</small> 연 {p.maxRate}%
              </>
            ) : (
              <span className="prod-muted">금리 확인 중</span>
            )}
          </p>
          {p.baseRate && p.baseRate !== p.maxRate && <p className="prod-hero-base">기본 연 {p.baseRate}%</p>}
        </div>
        <p className="prod-fine">세전 · 금리 기준일 {p.verifiedAt ? ymd(p.verifiedAt) : '확인 필요'} · 우대금리는 조건을 채우면 더해져요</p>
      </section>

      {!p.earlyTerminationAllowed && (
        <p className="prod-warn" role="note">
          중도 해지할 수 없는 상품이에요. 만기까지 돈을 찾을 수 없어요.
        </p>
      )}

      <div className="two-col">
        <section aria-labelledby="rate-table">
          <h2 id="rate-table" className="section-title">
            <span className="section-icon">
              <Icon name="list" size={18} />
            </span>
            기간별 금리
          </h2>
          <div className="panel prod-table-wrap">
            {p.rates.length === 0 ? (
              <p className="prod-pad prod-muted">금리표를 아직 확인하지 못했어요. 영업점이나 고객센터에 문의해 주세요.</p>
            ) : (
              <table className="prod-table">
                <thead>
                  <tr>
                    <th scope="col">기간</th>
                    <th scope="col">기본</th>
                    <th scope="col">최대 우대</th>
                  </tr>
                </thead>
                <tbody>
                  {p.rates.map((r) => (
                    <tr key={`${r.termMin}-${r.termMax}`} className={Number(r.baseRate) === bestRate ? 'is-best' : undefined}>
                      <td>
                        {r.termMin === r.termMax ? `${r.termMin}${unit}` : `${r.termMin}~${r.termMax}${unit}`}
                        {Number(r.baseRate) === bestRate && <span className="prod-best">최고</span>}
                      </td>
                      <td>연 {r.baseRate}%</td>
                      <td>{r.bonusRate && Number(r.bonusRate) > 0 ? `+${r.bonusRate}%p` : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section aria-labelledby="conditions">
          <h2 id="conditions" className="section-title">
            <span className="section-icon">
              <Icon name="user" size={18} />
            </span>
            가입 조건
          </h2>
          <dl className="panel prod-info">
            <div>
              <dt>가입 대상</dt>
              <dd>{p.eligibility ?? '확인 필요'}</dd>
            </div>
            <div>
              <dt>{what}</dt>
              <dd>
                {range}
                {p.amountUnit && p.amountUnit > 1 ? ` (${won(p.amountUnit)} 단위)` : ''}
              </dd>
            </div>
            <div>
              <dt>가입 기간</dt>
              <dd>
                {p.selectableMonths
                  ? p.selectableMonths.map((m) => `${m}개월`).join(' · ')
                  : byDay && p.minDays && p.maxDays
                    ? `${p.minDays}~${p.maxDays}일`
                    : p.termLabel || '확인 필요'}
              </dd>
            </div>
            <div>
              <dt>1인당</dt>
              <dd>{p.maxPerUser ? `${p.maxPerUser}개까지` : '확인 필요'}</dd>
            </div>
            <div>
              <dt>출금 계좌</dt>
              <dd>본인 명의 두린은행 입출금 계좌(정상)</dd>
            </div>
          </dl>
        </section>
      </div>

      {p.notes.length > 0 && (
        <section aria-labelledby="notes">
          <h2 id="notes" className="section-title">
            <span className="section-icon">
              <Icon name="bell" size={18} />
            </span>
            알아두세요
          </h2>
          <ul className="panel prod-notes">
            {p.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
            {!deposit && <li>가입하는 날 첫 달 돈만 빠져요. 다음 달부터는 자동으로 빠지지 않으니 「내 가입 상품 → 돈 넣기」로 직접 넣어 주세요.</li>}
          </ul>
        </section>
      )}

      <section aria-labelledby="estimate">
        <h2 id="estimate" className="section-title">
          <span className="section-icon">
            <Icon name="coins" size={18} />
          </span>
          예상 이자 계산
        </h2>
        {!p.subscribable ? (
          <p className="panel prod-pad prod-muted">
            {p.rates.length === 0 ? '금리표가 없어 계산과 가입을 할 수 없어요.' : 'N일 적금은 매일 자동 납입이 필요해 아직 앱에서 가입할 수 없어요.'}
          </p>
        ) : (
          <form className="panel prod-pad prod-form" onSubmit={onEstimate} noValidate>
            <div className="grid-2 prod-grid">
              <Field id="est-amount" label={deposit ? '맡길 돈' : '매달 넣을 돈'} message={estError ? { tone: 'error', text: estError } : null}>
                <div className="input-wrap">
                  <input
                    id="est-amount"
                    className="input"
                    inputMode="numeric"
                    value={amount ? Number(amount).toLocaleString('ko-KR') : ''}
                    onChange={(e) => setAmount(digitsOnly(e.target.value).slice(0, 13))}
                    placeholder={p.minAmount ? `${won(p.minAmount)} 이상` : '금액 입력'}
                    aria-invalid={!!estError}
                    aria-describedby="est-amount-msg"
                  />
                  <span className="timer prod-suffix">원</span>
                </div>
              </Field>
              {byDay ? (
                <Field id="est-days" label={`기간 (${p.minDays ?? 1}~${p.maxDays ?? ''}일)`}>
                  <div className="input-wrap">
                    <input
                      id="est-days"
                      className="input"
                      inputMode="numeric"
                      value={days}
                      onChange={(e) => setDays(digitsOnly(e.target.value).slice(0, 4))}
                      placeholder={`${p.minDays ?? 1}일 이상`}
                    />
                    <span className="timer prod-suffix">일</span>
                  </div>
                </Field>
              ) : (
                <Field id="est-months" label="기간">
                  <select id="est-months" className="input" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
                    {options.map((m) => (
                      <option key={m} value={m}>
                        {m}개월
                      </option>
                    ))}
                  </select>
                </Field>
              )}
            </div>
            <button className="btn-secondary prod-calc" type="submit">
              이자 계산하기
            </button>
            {est && (
              <div className="prod-result" aria-live="polite">
                <dl className="prod-dl">
                  <div>
                    <dt>적용 금리</dt>
                    <dd>연 {est.rate}% (기본금리)</dd>
                  </div>
                  <div>
                    <dt>넣는 돈 합계</dt>
                    <dd>{won(est.principalTotal)}</dd>
                  </div>
                  <div>
                    <dt>세전 이자</dt>
                    <dd>{won(est.interest)}</dd>
                  </div>
                  <div>
                    <dt>만기일</dt>
                    <dd>{ymd(est.maturityDate)}</dd>
                  </div>
                </dl>
                <p className="prod-total">
                  만기에 받는 돈 <strong>{won(est.maturityAmount)}</strong>
                </p>
                <p className="prod-fine">단리·세전으로 계산한 예상값이에요. 우대금리와 세금은 빠져 있어요.</p>
                <a className="btn-primary prod-cta" href={`#/products/${p.id}/subscribe?amount=${amount}&${byDay ? `days=${days}` : `months=${months}`}`}>
                  이 조건으로 가입하기
                </a>
              </div>
            )}
          </form>
        )}
      </section>
    </AppShell>
  )
}
