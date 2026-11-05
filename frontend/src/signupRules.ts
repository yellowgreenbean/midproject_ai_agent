// 회원가입 입력 규칙 (docs/기획서.md Part 1 AUTH-F01~F03). 서버 backend/app/rules.py 와 같은 규칙 — 바꿀 때 둘 다 고친다.
// 오류가 없으면 null, 있으면 화면에 보여 줄 한국어 문장을 돌려준다.

export const USERNAME_RE = /^[a-z][a-z0-9_]{3,19}$/

export function usernameError(v: string): string | null {
  if (!v) return '아이디를 입력해 주세요.'
  if (!USERNAME_RE.test(v)) return '영문 소문자로 시작하는 4~20자(소문자·숫자·밑줄)로 입력해 주세요.'
  return null
}

export function passwordError(pw: string, username: string): string | null {
  if (!pw) return '비밀번호를 입력해 주세요.'
  if (pw.length < 8 || pw.length > 64) return '8~64자로 입력해 주세요.'
  if (!/[A-Za-z]/.test(pw) || !/[0-9]/.test(pw)) return '영문과 숫자를 모두 넣어 주세요.'
  if (username && pw.toLowerCase().includes(username)) return '아이디가 들어간 비밀번호는 쓸 수 없어요.'
  return null
}

export function passwordConfirmError(pw: string, pw2: string): string | null {
  if (!pw2) return '비밀번호를 한 번 더 입력해 주세요.'
  return pw === pw2 ? null : '비밀번호가 일치하지 않아요.'
}

export function emailError(v: string): string | null {
  if (!v) return '이메일을 입력해 주세요.'
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : '이메일 형식을 확인해 주세요.'
}

export function nameError(v: string): string | null {
  if (!v.trim()) return '이름을 입력해 주세요.'
  return /^[가-힣a-zA-Z ]{2,20}$/.test(v.trim()) ? null : '한글 또는 영문 2~20자로 입력해 주세요.'
}

/** today 는 'YYYY-MM-DD' (사용자 기기 날짜) */
export function birthDateError(v: string, today: string): string | null {
  if (!v) return '생년월일을 선택해 주세요.'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || v < '1900-01-01') return '생년월일을 다시 확인해 주세요.'
  return v > today ? '미래 날짜는 선택할 수 없어요.' : null
}

export function localToday(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
