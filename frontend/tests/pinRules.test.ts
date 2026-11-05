import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pinError, shuffledDigits } from '../src/pinRules.ts'

test('PIN — 서버(rules.py)와 같은 규칙', () => {
  assert.equal(pinError('135790', '1987-09-01'), null)
  assert.equal(pinError('123457', '1987-09-01'), null) // 끝 하나만 달라도 괜찮다
  for (const bad of ['000000', '012345', '543210', '870901', '1234567', '', '12 456']) assert.notEqual(pinError(bad, '1987-09-01'), null, bad)
})

test('키패드는 0~9 를 한 번씩, 섞어서', () => {
  const keys = shuffledDigits()
  assert.deepEqual([...keys].sort(), [...'0123456789'])
  assert.notDeepEqual(shuffledDigits(() => 0), [...'0123456789']) // 섞는다
})
