import { test } from 'node:test'
import assert from 'node:assert/strict'
import { callFailure } from '../src/apiRules.ts'

test('서버가 답은 했는데 JSON 이 아니면 「연결할 수 없어요」가 아니라 서버 문제', () => {
  assert.equal(callFailure(new SyntaxError('bad json'), 'GET', true).code, 'SERVER_ERROR')
})

test('너무 늦으면 TIMEOUT — 보내기는 처리됐을 수 있다고 알린다', () => {
  const late = new DOMException('late', 'TimeoutError')
  assert.equal(callFailure(late, 'GET', false).code, 'TIMEOUT')
  assert.doesNotMatch(callFailure(late, 'GET', false).message, /처리됐을 수/)
  assert.match(callFailure(late, 'POST', false).message, /처리됐을 수 있으니 결과를 먼저 확인/)
})

test('서버가 꺼져 연결 자체가 안 되면 NETWORK', () => {
  assert.equal(callFailure(new TypeError('Failed to fetch'), 'POST', false).code, 'NETWORK')
})
