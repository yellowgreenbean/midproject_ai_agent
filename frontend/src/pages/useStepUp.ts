// 본인 확인 값·안내·요청 (docs/기획서.md Part 1 AUTH-F12) — 칸은 StepUp.tsx 의 StepUpField
import { useEffect, useState } from 'react'
import { getPinStatus, stepUp, type StepUpAction } from '../api'

export function useStepUp() {
  const [pin, setPin] = useState<boolean | null>(null) // PIN 을 등록했나 — 모르면(불러오는 중·실패) 비밀번호 칸
  const [value, setValue] = useState('')
  useEffect(() => {
    void getPinStatus().then((r) => setPin(r.success && r.data.enabled))
  }, [])
  return {
    pin,
    value,
    setValue,
    /** 아직 다 넣지 않았으면 그 안내 문장, 다 넣었으면 null */
    missing: pin ? (value.length === 6 ? null : '간편 비밀번호 6자리를 눌러 주세요.') : value ? null : '비밀번호를 입력해 주세요.',
    /** 본인 확인 번호를 받는다 — 성공·실패 모두 입력을 비운다(같은 값을 다시 보내지 않게) */
    async verify(action: StepUpAction) {
      const r = await stepUp(action, pin ? { pin: value } : { password: value })
      setValue('')
      return r
    },
  }
}
export type StepUp = ReturnType<typeof useStepUp>
