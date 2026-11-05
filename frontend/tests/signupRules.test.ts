// 실행: npm test  (Node 의 내장 테스트 — 새 패키지 없음)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { birthDateError, emailError, nameError, passwordConfirmError, passwordError, usernameError } from '../src/signupRules.ts'

test('아이디', () => {
  assert.equal(usernameError('minjun_kim'), null)
  assert.ok(usernameError('abc')) // 너무 짧음
  assert.ok(usernameError('1abcd')) // 숫자로 시작
  assert.ok(usernameError('Minjun')) // 대문자
  assert.ok(usernameError(''))
})

test('비밀번호', () => {
  assert.equal(passwordError('durin2026!', 'minjun_kim'), null)
  assert.ok(passwordError('short1', 'x'))
  assert.ok(passwordError('onlyletters', 'x'))
  assert.ok(passwordError('12345678', 'x'))
  assert.ok(passwordError('MINJUN_KIM99', 'minjun_kim')) // 아이디 포함(대소문자 무시)
  assert.equal(passwordConfirmError('a1b2c3d4', 'a1b2c3d4'), null)
  assert.ok(passwordConfirmError('a1b2c3d4', 'a1b2c3d5'))
})

test('이메일·이름', () => {
  assert.equal(emailError('a@example.com'), null)
  assert.ok(emailError('a@example'))
  assert.equal(nameError('김두린'), null)
  assert.ok(nameError('김'))
  assert.ok(nameError('김두린1'))
})

test('생년월일은 미래 날짜를 막는다', () => {
  assert.equal(birthDateError('1990-05-01', '2026-11-05'), null)
  assert.equal(birthDateError('2026-11-05', '2026-11-05'), null)
  assert.ok(birthDateError('2026-11-06', '2026-11-05'))
  assert.ok(birthDateError('1899-12-31', '2026-11-05'))
  assert.ok(birthDateError('', '2026-11-05'))
})
