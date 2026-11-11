// 약관 및 동의 내역 (docs/기획서.md Part 1 AUTH-F10 · UI08) — 약관마다 버전·동의한 날. 선택 약관만 켜고 끌 수 있다
import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import Icon from '../components/Icon'
import { getConsents, setConsent, type Consent } from '../api'
import './ProductPages.css'
import './AccountPages.css'
import './SettingsPages.css'

const dot = (d: string) => d.slice(0, 10).replaceAll('-', '.')

export default function ConsentsPage() {
  const [list, setList] = useState<Consent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getConsents().then((r) => (r.success ? setList(r.data) : r.error.code === 'UNAUTHENTICATED' ? (location.hash = '#/login') : setError(r.error.message)))
  }, [])

  async function toggle(c: Consent) {
    const r = await setConsent(c.termsId, !c.agreed)
    if (r.success) setList(r.data)
    else setError(r.error.message)
  }

  return (
    <AppShell title="약관 및 동의 내역" current="#/settings" busy={!list && !error}>
      <a className="set-back" href="#/settings">
        <Icon name="chevron" size={16} />
        마이페이지
      </a>
      <section className="prod-head">
        <h2 className="prod-title is-dup">약관 및 동의 내역</h2>
        <p className="prod-sub">필수 약관은 서비스를 쓰는 동안 유지돼요. 선택 약관은 언제든 바꿀 수 있어요.</p>
      </section>
      {error && (
        <p className="home-error" role="alert">
          {error}
        </p>
      )}
      {!list && !error && <p className="home-loading">불러오는 중…</p>}
      {list && (
        <ul className="panel set-terms">
          {list.map((c) => (
            <li key={c.termsId}>
              <span className="set-terms-main">
                <strong>
                  <span className={`set-chip ${c.required ? 'is-req' : ''}`}>{c.required ? '필수' : '선택'}</span>
                  {c.title}
                </strong>
                <small>
                  {c.version.replaceAll('-', '.')} 판 · {c.recordedAt ? `${dot(c.recordedAt)} ${c.agreed ? '동의' : '철회'}` : '기록 없음'}
                </small>
                <a className="set-terms-more" href={`#/settings/terms/${c.termsId}`} aria-label={`${c.title} 자세히 보기`}>
                  자세히 보기
                  <Icon name="chevron" size={12} />
                </a>
              </span>
              {c.required ? (
                <span className={`set-state ${c.agreed ? 'is-ok' : ''}`}>{c.agreed ? '동의함' : '동의 안 함'}</span>
              ) : (
                <button type="button" role="switch" aria-checked={c.agreed} aria-label={`${c.title} ${c.agreed ? '끄기' : '켜기'}`} className="set-switch-btn" onClick={() => void toggle(c)}>
                  <span className="acct-switch" aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  )
}
