import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mmss, secondsLeft, sessionStage } from '../src/sessionRules.ts'

const exp = 10 * 60_000 // 로그인 10분 뒤 만료

test('만료 1분 전부터 연장 창, 만료 시각이 되면 끝', () => {
  assert.equal(sessionStage(exp, 0), 'active')
  assert.equal(sessionStage(exp, exp - 60_001), 'active')
  assert.equal(sessionStage(exp, exp - 60_000), 'warning')
  assert.equal(sessionStage(exp, exp - 1), 'warning')
  assert.equal(sessionStage(exp, exp), 'expired')
})

test('남은 초는 올림, 음수 없음', () => {
  assert.equal(secondsLeft(exp, exp - 60_000), 60)
  assert.equal(secondsLeft(exp, exp - 58_500), 59)
  assert.equal(secondsLeft(exp, exp + 5_000), 0)
})

test('오른쪽 위 남은 시간은 분:초 두 자리', () => {
  assert.equal(mmss(600), '10:00')
  assert.equal(mmss(581), '09:41')
  assert.equal(mmss(5), '00:05')
})
