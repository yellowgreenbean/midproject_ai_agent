import type { ReactNode } from 'react'

export type FieldMessage = { tone: 'error' | 'ok' | 'info'; text: string } | null

type Props = {
  id: string
  label: string
  optional?: boolean
  message?: FieldMessage
  children: ReactNode
}

/** 라벨 + 입력칸 + 안내 문장. 입력칸에는 aria-describedby={`${id}-msg`} 를 붙인다 */
export default function Field({ id, label, optional, message, children }: Props) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
        {optional && <span className="field-optional">선택</span>}
      </label>
      {children}
      <p id={`${id}-msg`} className={`field-msg ${message ? `is-${message.tone}` : ''}`} aria-live="polite">
        {message?.text}
      </p>
    </div>
  )
}
