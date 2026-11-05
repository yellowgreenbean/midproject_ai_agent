// 6자리 숫자 입력 — 은행 앱의 보안 키패드처럼 숫자 자리를 섞어 보여 준다. 실제 키보드로도 칠 수 있다(가린 칸이 동그라미 위에 겹쳐 있다).
import { useState } from 'react'
import { shuffledDigits } from '../pinRules'
import './PinPad.css'

type Props = { id: string; label: string; value: string; onChange: (v: string) => void; invalid?: boolean; length?: number }

export default function PinPad({ id, label, value, onChange, invalid, length = 6 }: Props) {
  const [keys] = useState(() => shuffledDigits())
  const press = (d: string) => value.length < length && onChange(value + d)

  return (
    <div className="pin">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <div className="pin-dots">
        {Array.from({ length }, (_, i) => (
          <span key={i} className={i < value.length ? 'is-on' : undefined} />
        ))}
        <input
          id={id}
          className="pin-input"
          type="password"
          inputMode="numeric"
          autoComplete="off"
          maxLength={length}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, length))}
          aria-invalid={invalid}
          aria-describedby={`${id}-msg`}
        />
      </div>
      <div className="pin-keys" role="group" aria-label="숫자 키패드">
        {keys.slice(0, 9).map((d) => (
          <button key={d} type="button" onClick={() => press(d)}>
            {d}
          </button>
        ))}
        <button type="button" className="pin-key-sub" onClick={() => onChange('')}>
          전체 지우기
        </button>
        <button type="button" onClick={() => press(keys[9])}>
          {keys[9]}
        </button>
        <button type="button" className="pin-key-sub" aria-label="한 자리 지우기" onClick={() => onChange(value.slice(0, -1))}>
          ←
        </button>
      </div>
    </div>
  )
}
