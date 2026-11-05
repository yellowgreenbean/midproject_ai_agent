// 자동 로그아웃 시계 — 연장 창(SessionTimer)과 오른쪽 위 남은 시간(SessionBadge)이 같이 쓴다
import { useEffect, useState } from 'react'
import { logout, onSessionExpires } from './api'

/** 서버가 알려 준 만료 시각과 1초마다 바뀌는 지금 시각. 로그인 안 했으면 expiresAt 은 null */
export function useSessionClock() {
  const [expiresAt, setExpiresAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => onSessionExpires(setExpiresAt), [])
  useEffect(() => {
    if (expiresAt === null) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [expiresAt])
  return { expiresAt, now }
}

/** 로그아웃하고 로그인 화면으로. 이유가 있으면 로그인 화면이 안내한다(idle = 10분 무활동, max = 12시간 경과) */
export async function endSession(reason: false | 'idle' | 'max') {
  await logout() // 서버 세션이 이미 끝났어도 쿠키를 지운다
  location.hash = reason ? `#/login?expired=${reason}` : '#/login'
}
