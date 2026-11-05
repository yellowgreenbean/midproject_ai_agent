import { test } from 'node:test'
import assert from 'node:assert/strict'
import { koreanWon, matchTargets } from '../src/transferRules.ts'

test('한글 금액', () => {
  assert.equal(koreanWon(350000), '삼십오만 원')
  assert.equal(koreanWon(3500000), '삼백오십만 원') // 0을 하나 더 친 경우(기획서 18장 사례)
  assert.equal(koreanWon(100000000), '일억 원')
  assert.equal(koreanWon(10000), '일만 원')
  assert.equal(koreanWon(1), '일 원')
  assert.equal(koreanWon(120010), '십이만 십 원')
  assert.equal(koreanWon(0), '')
})

test('계좌번호 치는 동안 찾기', () => {
  const a = { accountNo: '11000000000021', accountDisplay: '110-00-000021' }
  const b = { accountNo: '11000000000001', accountDisplay: '110-00-000001' }
  assert.deepEqual(matchTargets([[a, b], [a]], '021'), [a]) // 최근·자주에 같은 계좌가 있어도 한 번
  assert.deepEqual(matchTargets([[a, b]], '11000000001'), [b]) // 화면의 11자리 번호로도
  assert.deepEqual(matchTargets([[a, b]], '1'), []) // 한 글자로는 찾지 않는다
  assert.deepEqual(matchTargets([[a, b]], '999'), [])
})
