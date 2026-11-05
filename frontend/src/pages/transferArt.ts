// 이체 화면 공통 글자 — 상태 이름과 시각 표시
import type { Transfer } from '../api'

export const STATUS_LABEL: Record<Transfer['status'], string> = { SUCCESS: '완료', FAILED: '실패', PENDING: '처리중' }

/** 2026-11-05T09:30:00+09:00 → 2026.11.05 09:30 */
export const when = (iso: string) => `${iso.slice(0, 4)}.${iso.slice(5, 7)}.${iso.slice(8, 10)} ${iso.slice(11, 16)}`
