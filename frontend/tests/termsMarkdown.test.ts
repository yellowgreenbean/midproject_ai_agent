// 실행: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseTermsMarkdown, termsToc } from '../src/termsMarkdown.ts'

test('장·조 제목과 문단, 문단 안 줄바꿈', () => {
  const blocks = parseTermsMarkdown('## 제1장 총칙\n\n### 제1조 (목적)\n\n첫 줄  \n둘째 줄\n\n1. 항목\n')
  assert.deepEqual(blocks, [
    { kind: 'heading', level: 2, text: '제1장 총칙', id: 'terms-h1' },
    { kind: 'heading', level: 3, text: '제1조 (목적)', id: 'terms-h2' },
    { kind: 'para', lines: ['첫 줄', '둘째 줄'] },
    { kind: 'para', lines: ['1. 항목'] },
  ])
  assert.deepEqual(termsToc(blocks), [
    { id: 'terms-h1', text: '제1장 총칙', level: 2 },
    { id: 'terms-h2', text: '제1조 (목적)', level: 3 },
  ])
})

test('표 — 빈 칸도 칸으로 남긴다', () => {
  const blocks = parseTermsMarkdown('별표 1)\n\n| 서비스종류 |  | 수수료 |\n| --- | --- | --- |\n| 조회 |  | 없음 |\n| 이체 | 타행이체 | 건당 500원 |\n\n끝')
  assert.deepEqual(blocks[1], {
    kind: 'table',
    head: ['서비스종류', '', '수수료'],
    rows: [
      ['조회', '', '없음'],
      ['이체', '타행이체', '건당 500원'],
    ],
  })
  assert.deepEqual(blocks[2], { kind: 'para', lines: ['끝'] })
})

test('구분선 없는 | 줄은 표가 아니라 문단, # 은 2단계로, CRLF 도 읽는다', () => {
  const blocks = parseTermsMarkdown('# 큰 제목\r\n\r\n| 그냥 글\r\n')
  assert.deepEqual(blocks, [
    { kind: 'heading', level: 2, text: '큰 제목', id: 'terms-h1' },
    { kind: 'para', lines: ['| 그냥 글'] },
  ])
})

test('태그는 글자 그대로 (HTML 로 해석하지 않음)', () => {
  assert.deepEqual(parseTermsMarkdown('<script>x</script>'), [{ kind: 'para', lines: ['<script>x</script>'] }])
})
