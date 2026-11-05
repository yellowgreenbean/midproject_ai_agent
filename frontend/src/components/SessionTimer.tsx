// 자동 로그아웃 — 10분 동안 아무것도 안 하면 로그아웃, 1분 전에 「로그인 연장」 창 (우리은행 방식, docs/domain-rules.md 7)
// 서버가 로그인한 응답마다 새 만료 시각을 주므로(api.ts onSessionExpires) 화면 이동·조회만 해도 시간이 다시 10분이 된다.
// shortcut: 탭을 여러 개 열면 탭마다 따로 센다. 다른 탭에서 연장해도 이 탭은 모른다 — 필요해지면 BroadcastChannel 로 맞춘다.
import { useEffect, useRef, useState } from 'react'
import { currentSessionExpires, extendSession } from '../api'
import { secondsLeft, sessionStage } from '../sessionRules'
import { endSession, useSessionClock } from '../useSessionClock'
import '../pages/SignupPage.css'
import './SessionTimer.css'

export default function SessionTimer() {
  const { expiresAt, now } = useSessionClock()
  const [busy, setBusy] = useState(false)
  const [cappedAt, setCappedAt] = useState<number | null>(null) // 연장해도 이 시각에서 안 늘어남 = 로그인 최대 12시간
  const dialog = useRef<HTMLDialogElement>(null)
  const leaving = useRef(false)

  const stage = expiresAt === null ? 'active' : sessionStage(expiresAt, now)
  const maxReached = cappedAt !== null && cappedAt === expiresAt

  async function leave(reason: false | 'idle' | 'max') {
    if (leaving.current) return
    leaving.current = true
    await endSession(reason)
    leaving.current = false
  }

  async function onExtend() {
    setBusy(true)
    const r = await extendSession()
    setBusy(false)
    if (!r.success) return void leave('idle') // 서버에선 이미 끝남
    const at = currentSessionExpires() // 연장 직후 새 시각 (state 는 다음 그리기에 바뀜)
    if (at !== null && sessionStage(at, Date.now()) === 'warning') setCappedAt(at)
  }

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (stage === 'warning' && !d.open) d.showModal()
    if (stage !== 'warning' && d.open) d.close()
    if (stage === 'expired') void leave(maxReached ? 'max' : 'idle')
  }, [stage, maxReached])

  const s = expiresAt === null ? 0 : secondsLeft(expiresAt, now)
  return (
    <dialog
      ref={dialog}
      className="session-dialog"
      aria-labelledby="session-title"
      aria-describedby="session-desc"
      onCancel={(e) => {
        e.preventDefault() // Esc = 연장 (우리은행의 Pause 키처럼 키보드로 바로 연장)
        if (!maxReached && !busy) void onExtend()
      }}
    >
      <h2 id="session-title">{maxReached ? '로그인 시간이 다 됐어요' : '곧 자동으로 로그아웃돼요'}</h2>
      <p id="session-desc">
        {maxReached ? '로그인한 지 12시간이 지나 더 연장할 수 없어요. ' : '10분 동안 이용이 없어 '}
        <strong className="session-count">{s}초</strong> 뒤 로그아웃돼요.
        {maxReached ? ' 다시 로그인해 주세요.' : ' 계속 이용하려면 로그인을 연장해 주세요.'}
      </p>
      <div className="session-actions">
        {maxReached ? (
          <button type="button" className="btn-primary" onClick={() => void leave(false)}>
            다시 로그인
          </button>
        ) : (
          <>
            <button type="button" className="btn-primary" onClick={() => void onExtend()} disabled={busy} autoFocus>
              {busy ? '연장 중…' : '로그인 연장'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => void leave(false)}>
              로그아웃
            </button>
          </>
        )}
      </div>
    </dialog>
  )
}
