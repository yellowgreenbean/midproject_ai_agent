// 약관 본문(Markdown) → 화면 블록. 약관 파일(data/rag/terms/*.md)에 쓰이는 것만 다룬다:
//   ## · ### 제목(장·조) / 빈 줄로 나뉜 문단(문단 안 줄바꿈 유지) / | 표 |
// shortcut: 굵게·링크 같은 인라인 문법은 약관 파일에 없어 글자 그대로 둔다. 새 약관에 쓰이면 여기에 더한다.
// HTML 로 바꾸지 않고 블록 목록만 만든다 — 화면(React)이 글자로 그리므로 본문에 태그가 섞여도 실행되지 않는다.

export type TermsBlock =
  | { kind: 'heading'; level: 2 | 3 | 4; text: string; id: string }
  | { kind: 'para'; lines: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] }

export type TocItem = { id: string; text: string; level: 2 | 3 | 4 }

const HEADING = /^(#{1,6})\s+(.+?)\s*#*\s*$/
const TABLE_SEP = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())

export function parseTermsMarkdown(md: string): TermsBlock[] {
  const lines = md.replace(/\r\n?/g, '\n').split('\n')
  const blocks: TermsBlock[] = []
  let para: string[] = []
  let headings = 0
  const flush = () => {
    if (para.length) blocks.push({ kind: 'para', lines: para })
    para = []
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd()
    if (!line.trim()) {
      flush()
      continue
    }
    const h = line.match(HEADING)
    if (h) {
      flush()
      // # 은 화면 제목과 겹치므로 ## 와 같게, #### 이하는 4로 묶는다
      const level = Math.min(Math.max(h[1].length, 2), 4) as 2 | 3 | 4
      blocks.push({ kind: 'heading', level, text: h[2], id: `terms-h${++headings}` })
      continue
    }
    if (line.trimStart().startsWith('|') && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1].trim())) {
      flush()
      const head = cells(line)
      const rows: string[][] = []
      for (i += 2; i < lines.length && lines[i].trimStart().startsWith('|'); i++) rows.push(cells(lines[i]))
      i-- // for 가 다시 1 더한다
      blocks.push({ kind: 'table', head, rows })
      continue
    }
    para.push(line.trim())
  }
  flush()
  return blocks
}

/** 목차 — 장(##)·조(###) 제목 */
export const termsToc = (blocks: TermsBlock[]): TocItem[] =>
  blocks.flatMap((b) => (b.kind === 'heading' && b.level <= 3 ? [{ id: b.id, text: b.text, level: b.level }] : []))
