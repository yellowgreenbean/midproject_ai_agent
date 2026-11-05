// 자동 로그아웃 시간 계산 (docs/기획서.md Part 1 AUTH-F05) — 우리은행처럼 10분 무활동이면 끝, 1분 전에 「로그인 연장」 창
export const WARN_BEFORE_MS = 60_000

export type SessionStage = 'active' | 'warning' | 'expired'

export function sessionStage(expiresAt: number, now: number): SessionStage {
  if (now >= expiresAt) return 'expired'
  return expiresAt - now <= WARN_BEFORE_MS ? 'warning' : 'active'
}

/** 남은 초 → "09:41" */
export const mmss = (sec: number) => `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`

export const secondsLeft = (expiresAt: number, now: number) => Math.max(0, Math.ceil((expiresAt - now) / 1000))
