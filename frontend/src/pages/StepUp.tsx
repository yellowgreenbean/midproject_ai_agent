// 중요 작업 전 본인 확인 칸 (docs/기획서.md Part 1 AUTH-F12) — 간편 비밀번호(PIN)를 등록했으면 6자리 키패드, 아직이면 로그인 비밀번호.
// 값·빠진 입력 안내·확인 요청은 useStepUp()(useStepUp.ts) 이 갖고, 이 칸은 보여 주기만 한다.
import Field, { type FieldMessage } from '../components/Field'
import PinPad from '../components/PinPad'
import type { StepUp } from './useStepUp'

export function StepUpField({ auth, id, message }: { auth: StepUp; id: string; message: FieldMessage }) {
  if (auth.pin)
    return (
      <div className="field">
        <PinPad id={id} label="본인 확인 — 간편 비밀번호 6자리" value={auth.value} onChange={auth.setValue} invalid={message?.tone === 'error'} />
        <p id={`${id}-msg`} className={`field-msg ${message ? `is-${message.tone}` : ''}`} aria-live="polite">
          {message?.text}
        </p>
        <a className="prod-fine" href="#/settings/pin">
          간편 비밀번호를 잊으셨나요?
        </a>
      </div>
    )
  return (
    <>
      <Field id={id} label="본인 확인 — 로그인 비밀번호" message={message}>
        <input
          id={id}
          className="input"
          type="password"
          autoComplete="current-password"
          value={auth.value}
          onChange={(e) => auth.setValue(e.target.value)}
          aria-invalid={message?.tone === 'error'}
          aria-describedby={`${id}-msg`}
        />
      </Field>
      {auth.pin === false && (
        <p className="prod-fine">
          간편 비밀번호를 만들면 비밀번호 대신 6자리로 확인해요. <a href="#/settings/pin">만들기</a>
        </p>
      )}
    </>
  )
}
