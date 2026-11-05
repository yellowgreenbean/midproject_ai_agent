// 회원 탈퇴 (docs/기획서.md Part 1 AUTH-F09 · UI07) — 탈퇴 전 3단계: ① 남은 돈 옮기기 ② 삭제될 데이터 확인 ③ 연결된 서비스 확인.
// 「완료」는 서버가 매번 다시 판단한다. 셋 다 끝나면 비밀번호로 본인 확인 뒤 탈퇴.
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { confirmDataReview, confirmLinkedServices, getWithdrawalStatus, withdraw, type CheckItem, type WithdrawalStatus } from '../api'
import { StepUpField } from './StepUp'
import { useStepUp } from './useStepUp'
import './ProductPages.css'
import './SettingsPages.css'

// ② 안내문 — 바꾸면 서버의 DATA_REVIEW_VERSION(backend/app/crud.py)도 올린다
const DATA_GROUPS = [
  { title: '바로 삭제돼요', items: '로그인 기록, 계좌 별명·즐겨찾기, 알림 설정과 알림, 자주 쓰는 계좌, 카드 설정' },
  { title: '1개월 뒤 삭제돼요', items: '이름·아이디·이메일·생년월일 같은 회원 정보 (부정 가입을 막으려고 잠깐 둬요)' },
  { title: '5년 동안 따로 보관해요', items: '계좌·거래 기록, 이체 기록, 예금·적금 가입 기록, 카드 이용 기록 (전자금융거래법)' },
]
const INFO_SERVICES = ['입출금 알림 — 설정이 지워지고 알림이 멈춰요', '모든 약관 동의 — 탈퇴하면 자동으로 철회돼요']

export default function WithdrawPage() {
  const [st, setSt] = useState<WithdrawalStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const auth = useStepUp()
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    void getWithdrawalStatus().then((r) => (r.success ? setSt(r.data) : r.error.code === 'UNAUTHENTICATED' ? (location.hash = '#/login') : setError(r.error.message)))
  }, [])

  async function run(p: ReturnType<typeof getWithdrawalStatus>) {
    const r = await p
    if (r.success) setSt(r.data)
    else setError(r.error.message)
  }

  async function onWithdraw(e: FormEvent) {
    e.preventDefault()
    if (auth.missing) return setFormError(auth.missing)
    setBusy(true)
    setFormError(null)
    const ch = await auth.verify('WITHDRAWAL')
    const r = ch.success ? await withdraw(ch.data) : ch
    setBusy(false)
    if (r.success) return setDone(true)
    setFormError(r.error.message)
    void run(getWithdrawalStatus()) // 그 사이 바뀐 게 있으면 단계 표시도 다시
  }

  if (done)
    return (
      <AppShell title="회원 탈퇴" current="#/settings">
        <div className="panel empty">
          <span className="empty-icon">
            <Icon name="user" size={26} />
          </span>
          <p className="empty-title">탈퇴했어요</p>
          <p className="empty-sub">그동안 두린은행을 써 주셔서 고마워요. 언제든 다시 가입할 수 있어요.</p>
          <a className="btn-pill" href="#/login">
            처음으로
          </a>
        </div>
      </AppShell>
    )

  return (
    <AppShell title="회원 탈퇴" current="#/settings" busy={!st && !error}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      <section className="prod-head">
        <h2 className="prod-title">탈퇴하기 전에 확인해 주세요</h2>
        <p className="prod-sub">세 가지를 모두 마쳐야 탈퇴할 수 있어요. 탈퇴하면 되돌릴 수 없어요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!st && !error && <p className="home-loading">확인하는 중…</p>}
      {st && (
        <ol className="set-steps">
          <Step no={1} title="남은 돈 옮기기" ok={st.moneyOk}>
            {st.moneyOk ? (
              <p className="set-step-sub">계좌에 남은 돈과 진행 중인 예금·적금이 없어요.</p>
            ) : (
              <>
                <p className="set-step-sub">남은 돈을 모두 옮기고, 예금·적금을 정리해야 해요.</p>
                <Items items={st.moneyItems} />
                <button type="button" className="btn-pill is-plain" onClick={() => void run(getWithdrawalStatus())}>
                  다 옮겼어요, 다시 확인
                </button>
              </>
            )}
          </Step>

          <Step no={2} title="삭제될 데이터 확인하기" ok={st.dataReviewed}>
            <dl className="set-data">
              {DATA_GROUPS.map((g) => (
                <div key={g.title}>
                  <dt>{g.title}</dt>
                  <dd>{g.items}</dd>
                </div>
              ))}
            </dl>
            <p className="prod-fine">탈퇴하면 거래 기록은 다시 가입해도 볼 수 없어요.</p>
            {!st.dataReviewed && (
              <button type="button" className="btn-pill" onClick={() => void run(confirmDataReview(st.dataReviewVersion))}>
                내용을 확인했어요
              </button>
            )}
          </Step>

          <Step no={3} title="연결된 서비스 확인하기" ok={st.linkedOk}>
            {st.linkedItems.length > 0 ? (
              <>
                <p className="set-step-sub">아래 서비스를 먼저 정리해야 탈퇴할 수 있어요.</p>
                <Items items={st.linkedItems} />
              </>
            ) : (
              <ul className="set-info-list">
                {INFO_SERVICES.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            )}
            {!st.linkedConfirmed && (
              <button type="button" className="btn-pill" disabled={st.linkedItems.length > 0} onClick={() => void run(confirmLinkedServices())}>
                확인했어요
              </button>
            )}
          </Step>
        </ol>
      )}

      {st?.canWithdraw && (
        <form className="panel set-form prod-form" onSubmit={onWithdraw} noValidate>
          <p className="empty-title">마지막으로 본인 확인을 할게요</p>
          <StepUpField auth={auth} id="wd-password" message={formError ? { tone: 'error', text: formError } : null} />
          <button className="btn-primary is-danger" type="submit" disabled={busy}>
            {busy ? '처리 중…' : '탈퇴하기'}
          </button>
        </form>
      )}
    </AppShell>
  )
}

function Step({ no, title, ok, children }: { no: number; title: string; ok: boolean; children: ReactNode }) {
  return (
    <li className={`panel set-step${ok ? ' is-ok' : ''}`}>
      <div className="set-step-head">
        <span className="set-step-no" aria-hidden="true">
          {ok ? '✓' : no}
        </span>
        <strong>{title}</strong>
        <span className={`set-chip ${ok ? 'is-ok' : 'is-todo'}`}>{ok ? '완료' : '확인 필요'}</span>
      </div>
      {children}
    </li>
  )
}

function Items({ items }: { items: CheckItem[] }) {
  return (
    <ul className="set-items">
      {items.map((i, n) => (
        <li key={n}>
          <a href={i.href}>
            <span>
              <strong>{i.label}</strong>
              <small>{i.detail}</small>
            </span>
            <Icon name="chevron" size={16} />
          </a>
        </li>
      ))}
    </ul>
  )
}
