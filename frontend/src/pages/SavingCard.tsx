// 예금·적금 큰 카드 한 장 — 통장 그림 · 모은 돈 · 만기까지 진행 막대 (내 예금·적금 · 내 계좌 화면이 같이 씀)
import Icon from '../components/Icon'
import type { Subscription } from '../api'
import { daysLeft, savingsProgress, won, ymd } from '../productRules'
import { PRODUCT_ART, STATUS_LABEL, TYPE_CLASS, TYPE_LABEL } from './productArt'
import './ProductPages.css'
import './AccountPages.css'

const dDay = (maturity: string) => {
  const d = daysLeft(maturity)
  return d > 0 ? `D-${d}` : d === 0 ? '오늘 만기' : '만기 지남'
}

/** 큰 카드 한 장 — 통장 그림 · 모은 돈 · 만기까지 진행 막대 */
export default function SavingCard({ s }: { s: Subscription }) {
  const active = s.status === 'ACTIVE'
  const deposit = s.productType === 'TIME_DEPOSIT'
  return (
    <a href={`#/my/savings/${s.id}`} className={`panel sav-card ${TYPE_CLASS[s.productType]} ${active ? '' : 'is-done'}`}>
      <span className="sav-top">
        <span className="pc-tag">{TYPE_LABEL[s.productType]}</span>
        <span className="sav-status">{STATUS_LABEL[s.status] ?? s.status}</span>
      </span>
      <img src={PRODUCT_ART[s.productType]} alt="" className="sav-art" />
      <strong className="sav-name">{s.productName}</strong>
      <small className="sav-label">{deposit ? '맡긴 돈' : '지금까지 넣은 돈'}</small>
      <span className="sav-amount">{won(s.principal)}</span>
      <span className="sav-sub">
        연 {s.appliedRate}% · {deposit ? '만기에 한 번에 받아요' : s.monthlyAmount !== null ? `매달 ${won(s.monthlyAmount)}` : '자유롭게 넣는 적금'}
      </span>
      {active && (
        <span className="sav-due">
          <progress
            className="acct-progress sav-progress"
            value={savingsProgress(s.startDate, s.maturityDate)}
            max={100}
            aria-label="만기까지 지난 기간"
          />
          <span className="sav-due-text">
            <span>만기 {ymd(s.maturityDate)}</span>
            <strong>{dDay(s.maturityDate)}</strong>
          </span>
        </span>
      )}
      <span className="pc-foot">
        <span>출금 {s.accountNumber}</span>
        <span className="pc-cta">
          자세히 보기 <Icon name="chevron" size={14} />
        </span>
      </span>
    </a>
  )
}
