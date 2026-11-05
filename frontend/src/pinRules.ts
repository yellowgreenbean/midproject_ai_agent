// 간편 비밀번호(PIN) 규칙 — backend/app/rules.py pin_error 와 같은 규칙. 서버가 최종 판정하고, 화면은 먼저 알려 주기만 한다.

/** 오류가 없으면 null. birthDate 는 'YYYY-MM-DD' */
export function pinError(pin: string, birthDate: string): string | null {
  if (!/^[0-9]{6}$/.test(pin)) return '숫자 6자리로 정해 주세요.'
  if (new Set(pin).size === 1) return '같은 숫자만 쓸 수는 없어요.'
  const steps = new Set([...pin.slice(1)].map((d, i) => Number(d) - Number(pin[i])))
  if (steps.size === 1 && (steps.has(1) || steps.has(-1))) return '이어지는 숫자(123456 같은)는 쓸 수 없어요.'
  if (birthDate && pin === birthDate.slice(2, 4) + birthDate.slice(5, 7) + birthDate.slice(8, 10)) return '생년월일은 쓸 수 없어요.'
  return null
}

/** 0~9 를 섞은 키패드 배열 — 어깨 너머로 누르는 자리를 보고 숫자를 알아채기 어렵게 */
export function shuffledDigits(random: () => number = Math.random): string[] {
  const d = [...'0123456789']
  for (let i = d.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[d[i], d[j]] = [d[j], d[i]]
  }
  return d
}
