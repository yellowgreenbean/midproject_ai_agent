// 오른쪽 위 「자동 로그아웃까지 남은 시간 + 연장」 (우리은행 방식). 로그인 안 했으면 아무것도 안 그린다.
// 휴대폰 폭에선 머리 줄에 자리가 없어 그 아래 한 줄로 내려간다(SessionTimer.css).
import { useState } from 'react'
import Icon from './Icon'
import { extendSession } from '../api'
import { mmss, secondsLeft, WARN_BEFORE_MS } from '../sessionRules'
import { endSession, useSessionClock } from '../useSessionClock'

export default function SessionBadge() {
  const { expiresAt, now } = useSessionClock()
  const [busy, setBusy] = useState(false)
  if (expiresAt === null) return null

  const s = secondsLeft(expiresAt, now)
  async function onExtend() {
    setBusy(true)
    const r = await extendSession()
    setBusy(false)
    if (!r.success) void endSession('idle') // 서버에선 이미 끝남
  }

  // 남은 시간과 연장을 버튼 하나로 — 따로 있으면 시계를 눌러야 하는지 연장을 눌러야 하는지 헷갈린다
  return (
    <button
      type="button"
      className={`session-badge${expiresAt - now <= WARN_BEFORE_MS ? ' is-urgent' : ''}`}
      onClick={() => void onExtend()}
      disabled={busy}
      aria-label={`자동 로그아웃까지 ${Math.floor(s / 60)}분 ${s % 60}초. 눌러서 로그인 연장`}
    >
      <Icon name="clock" size={16} />
      <span className="session-badge-time">{mmss(s)}</span>
      <span className="session-badge-act">연장</span>
    </button>
  )
}
