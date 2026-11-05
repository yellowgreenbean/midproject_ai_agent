// 이체 화면이 쓰는 작은 규칙 — 잔액·한도·경고는 서버(backend/app/crud.py create_transfer)가 최종 판정한다

const DIGITS = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
const SMALL = ['', '십', '백', '천']
const BIG = ['', '만', '억', '조']

/** 350000 → "삼십오만 원" (금액 오입력 방지, 기획서 Part 5 4장). 십·백·천 앞의 "일"은 뺀다: 100000 → "십만 원" */
export function koreanWon(n: number): string {
  if (!Number.isSafeInteger(n) || n <= 0) return ''
  const groups: string[] = []
  for (let g = 0; n > 0; g++, n = Math.floor(n / 10000)) {
    const part = n % 10000
    if (!part) continue
    let text = ''
    for (let i = 3; i >= 0; i--) {
      const d = Math.floor(part / 10 ** i) % 10
      if (d) text += (d === 1 && i > 0 ? '' : DIGITS[d]) + SMALL[i]
    }
    groups.unshift(text + BIG[g])
  }
  return `${groups.join(' ')} 원`
}

/** 계좌번호를 치는 동안 최근·자주 목록에서 맞는 계좌 찾기 (Part 5 6장) — 14자리 원래 번호나 화면의 11자리 번호 어디에든 들어 있으면 */
export function matchTargets<T extends { accountNo: string; accountDisplay: string }>(lists: T[][], typed: string): T[] {
  if (typed.length < 2) return []
  const seen = new Set<string>()
  return lists.flat().filter((t) => {
    const hit = t.accountNo.includes(typed) || t.accountDisplay.replace(/-/g, '').includes(typed)
    if (!hit || seen.has(t.accountNo)) return false
    seen.add(t.accountNo)
    return true
  })
}
