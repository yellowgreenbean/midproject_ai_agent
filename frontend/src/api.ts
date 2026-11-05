// 서버 호출은 이 파일 한 곳에서만 한다. 함수 이름은 docs/기획서.md Part 1 7절 API 와 1:1.
// 서버: backend/ (FastAPI, 이 컴퓨터의 8010번 문). 서버는 snake_case·금액 문자열로 주고받고(C-5),
// 화면이 쓰기 편한 모양(camelCase·숫자)으로 바꾸는 일도 여기서만 한다.

export type ApiError = { code: string; message: string }
export type ApiResult<T> = { success: true; data: T } | { success: false; error: ApiError }

export type Term = { id: string; title: string; required: boolean; version: string }
export type RegisterBody = {
  username: string
  password: string
  passwordConfirm: string
  email: string
  emailVerificationToken: string
  name: string
  birthDate: string
  gender: 'M' | 'F'
  payday: number | null
  agreedTermIds: string[]
}
export type SessionUser = { user_id: string; username: string; name: string; status: string }
export type Account = { id: string; name: string; number: string; type: string; status: string; isFavorite: boolean; balance: number }
export type Product = { id: string; name: string; description: string; maxRate: string; termLabel: string; icon: 'safe' | 'coins' }

// shortcut: 서버 주소를 화면 주소의 8010번 문으로 고정 (8000 은 다른 프로젝트가 씀). 서버를 다른 곳에 두게 되면 환경 변수로 뺀다.
const API = `${location.protocol}//${location.hostname}:8010`

// 로그인한 요청마다 서버가 새 만료 시각을 X-Session-Expires-At 헤더로 준다 → 「로그인 연장」 창(SessionTimer)이 듣는다
let sessionExpiresAt: number | null = null
const sessionListeners = new Set<(expiresAt: number | null) => void>()
function setSessionExpires(at: number | null) {
  sessionExpiresAt = at
  sessionListeners.forEach((fn) => fn(at))
}
/** 듣기 시작하면 마지막으로 받은 시각을 바로 한 번 알려 준다. 돌려준 함수를 부르면 그만 듣는다. */
export function onSessionExpires(fn: (expiresAt: number | null) => void) {
  sessionListeners.add(fn)
  fn(sessionExpiresAt)
  return () => {
    sessionListeners.delete(fn)
  }
}
export const currentSessionExpires = () => sessionExpiresAt

async function call<T>(method: 'GET' | 'POST' | 'PATCH' | 'DELETE', path: string, body?: unknown, headers?: Record<string, string>): Promise<ApiResult<T>> {
  try {
    const res = await fetch(API + path, {
      method,
      credentials: 'include', // 로그인 쿠키를 함께 보낸다
      headers: body === undefined ? headers : { 'Content-Type': 'application/json', ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const exp = res.headers.get('X-Session-Expires-At')
    if (exp) setSessionExpires(Date.parse(exp))
    return (await res.json()) as ApiResult<T>
  } catch {
    // 서버가 꺼져 있거나 응답이 JSON 이 아닐 때 — 화면에 그대로 알린다
    return { success: false, error: { code: 'NETWORK', message: '서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.' } }
  }
}

const map = <A, B>(r: ApiResult<A>, f: (a: A) => B): ApiResult<B> => (r.success ? { success: true, data: f(r.data) } : r)

// ---- 회원가입 (AUTH-F01~F03, F10) ----

/** GET /terms */
export const getTerms = () => call<Term[]>('GET', '/terms')

/** GET /auth/usernames/availability */
export const checkUsername = (username: string) =>
  call<{ available: boolean }>('GET', `/auth/usernames/availability?username=${encodeURIComponent(username)}`)

/** POST /auth/email-verifications — 메일 대신 서버가 dev_code 로 번호를 돌려준다(모의 메일) */
/** 인증번호를 어디에 쓰나 — 쓰임마다 따로 센다(가입 번호로 비밀번호를 바꿀 수 없게) */
export type MailPurpose = 'SIGNUP' | 'EMAIL_CHANGE' | 'USERNAME_RECOVERY' | 'PASSWORD_RESET'

export async function sendEmailCode(email: string, purpose: MailPurpose = 'SIGNUP'): Promise<ApiResult<{ expiresAt: number; resendAt: number; devCode: string }>> {
  const r = await call<{ expires_at: string; resend_at: string; dev_code: string }>('POST', '/auth/email-verifications', { email, purpose })
  return map(r, (d) => ({ expiresAt: Date.parse(d.expires_at), resendAt: Date.parse(d.resend_at), devCode: d.dev_code }))
}

/** POST /auth/email-verifications/confirm */
export const confirmEmailCode = (email: string, code: string, purpose: MailPurpose = 'SIGNUP') =>
  call<{ token: string }>('POST', '/auth/email-verifications/confirm', { email, code, purpose })

/** POST /auth/username-recovery — 아이디 찾기 (AUTH-F06). 가린 아이디만 돌려준다 */
export const recoverUsernames = (email: string, emailVerificationToken: string) =>
  call<{ username: string; created_at: string }[]>('POST', '/auth/username-recovery', { email, email_verification_token: emailVerificationToken })

/** POST /auth/password-resets — 비밀번호 재설정 (AUTH-F06). 성공하면 모든 기기에서 로그아웃 */
export const resetPassword = (b: { username: string; email: string; emailVerificationToken: string; newPassword: string; newPasswordConfirm: string }) =>
  call<object>('POST', '/auth/password-resets', {
    username: b.username,
    email: b.email,
    email_verification_token: b.emailVerificationToken,
    new_password: b.newPassword,
    new_password_confirm: b.newPasswordConfirm,
  })

/** POST /auth/register — 성공하면 서버가 로그인 쿠키도 준다(가입 직후 로그인, docs/decisions.md) */
export const register = (b: RegisterBody) =>
  call<SessionUser>('POST', '/auth/register', {
    username: b.username,
    password: b.password,
    password_confirm: b.passwordConfirm,
    email: b.email,
    email_verification_token: b.emailVerificationToken,
    name: b.name,
    birth_date: b.birthDate,
    gender: b.gender,
    payday: b.payday,
    agreed_term_ids: b.agreedTermIds,
  })

// ---- 로그인 · 로그아웃 (AUTH-F05) ----

/** POST /auth/login */
export const login = (username: string, password: string) => call<SessionUser>('POST', '/auth/login', { username, password })

/** POST /auth/logout */
export async function logout() {
  const r = await call<object>('POST', '/auth/logout')
  if (r.success) setSessionExpires(null)
  return r
}

/** POST /auth/session/extend — 「로그인 연장」. 새 만료 시각은 헤더로 온다(위 onSessionExpires) */
export const extendSession = () => call<object>('POST', '/auth/session/extend')

/** GET /users/me — 로그인 안 했으면 UNAUTHENTICATED */
export const getMe = () => call<SessionUser>('GET', '/users/me')

// ---- 설정: 내 정보 · 비밀번호 · 약관 · 회원 탈퇴 (AUTH-F07~F10) ----

export type Profile = {
  userId: string
  username: string
  name: string
  email: string
  emailVerified: boolean
  birthDate: string
  gender: 'M' | 'F'
  payday: number | null
  createdAt: string
}
type ProfileRaw = SessionUser & { email: string; email_verified: boolean; birth_date: string; gender: 'M' | 'F'; payday: number | null; created_at: string }
const toProfile = (p: ProfileRaw): Profile => ({
  userId: p.user_id,
  username: p.username,
  name: p.name,
  email: p.email,
  emailVerified: p.email_verified,
  birthDate: p.birth_date,
  gender: p.gender,
  payday: p.payday,
  createdAt: p.created_at,
})

/** GET /users/me — 내 정보 화면용 (getMe 와 같은 주소, 칸을 더 쓴다) */
export const getProfile = async () => map(await call<ProfileRaw>('GET', '/users/me'), toProfile)

/** PATCH /users/me — 1차는 월급일만 (null = 비움) */
export const updatePayday = async (payday: number | null) => map(await call<ProfileRaw>('PATCH', '/users/me', { payday }), toProfile)

/** PATCH /users/me — 이메일·생년월일·성별 (본인 확인 PROFILE_CHANGE, 이메일은 새 메일 인증 토큰도) — 보낸 칸만 바뀐다 */
export const updateProfile = async (b: { email?: string; emailVerificationToken?: string; birthDate?: string; gender?: 'M' | 'F'; stepUpChallengeId: string }) =>
  map(
    await call<ProfileRaw>('PATCH', '/users/me', {
      ...(b.email !== undefined && { email: b.email, email_verification_token: b.emailVerificationToken }),
      ...(b.birthDate !== undefined && { birth_date: b.birthDate }),
      ...(b.gender !== undefined && { gender: b.gender }),
      step_up_challenge_id: b.stepUpChallengeId,
    }),
    toProfile,
  )

/** POST /users/me/password/change — 성공하면 다른 기기의 로그인이 끊긴다 */
export const changePassword = (current: string, next: string, confirm: string) =>
  call<object>('POST', '/users/me/password/change', { current_password: current, new_password: next, new_password_confirm: confirm })

export type Consent = { termsId: string; title: string; required: boolean; version: string; agreed: boolean; recordedAt: string | null }
type ConsentRaw = { terms_id: string; title: string; required: boolean; version: string; agreed: boolean; recorded_at: string | null }
const toConsents = (l: ConsentRaw[]): Consent[] =>
  l.map((c) => ({ termsId: c.terms_id, title: c.title, required: c.required, version: c.version, agreed: c.agreed, recordedAt: c.recorded_at }))

/** GET /users/me/consents — 약관마다 마지막 동의 상태 */
export const getConsents = async () => map(await call<ConsentRaw[]>('GET', '/users/me/consents'), toConsents)

/** PATCH /users/me/consents — 선택 약관만 바꿀 수 있다 */
export const setConsent = async (termsId: string, agreed: boolean) =>
  map(await call<ConsentRaw[]>('PATCH', '/users/me/consents', { terms_id: termsId, agreed }), toConsents)

// ---- 이체 한도 (TRX-F07·F13) — 계좌마다. 올릴 때만 본인 확인(PROFILE_CHANGE) ----
type TransferLimitRaw = { account_id: string; account_name: string; account_number: string; per_transfer_limit: string; daily_limit: string; used_today: string; is_default: boolean }
export type TransferLimit = { accountId: string; accountName: string; accountNumber: string; perTransfer: number; daily: number; usedToday: number; isDefault: boolean }
const toLimit = (l: TransferLimitRaw): TransferLimit => ({
  accountId: l.account_id,
  accountName: l.account_name,
  accountNumber: l.account_number,
  perTransfer: Number(l.per_transfer_limit),
  daily: Number(l.daily_limit),
  usedToday: Number(l.used_today),
  isDefault: l.is_default,
})

/** GET /users/me/transfer-limits — 해지 안 한 내 계좌마다 지금 한도와 오늘 보낸 금액 */
export const getTransferLimits = async () => map(await call<TransferLimitRaw[]>('GET', '/users/me/transfer-limits'), (d) => d.map(toLimit))

/** PATCH /users/me/transfer-limits/{id} — 하나라도 올리면 stepUpChallengeId 가 있어야 한다 */
export const setTransferLimit = async (accountId: string, perTransfer: number, daily: number, stepUpChallengeId?: string) =>
  map(
    await call<TransferLimitRaw>('PATCH', `/users/me/transfer-limits/${encodeURIComponent(accountId)}`, {
      per_transfer_limit: perTransfer,
      daily_limit: daily,
      step_up_challenge_id: stepUpChallengeId ?? null,
    }),
    toLimit,
  )

export type CheckItem = { label: string; detail: string; href: string }
export type WithdrawalStatus = {
  moneyOk: boolean
  moneyItems: CheckItem[]
  dataReviewVersion: string
  dataReviewed: boolean
  linkedOk: boolean
  linkedItems: CheckItem[]
  linkedConfirmed: boolean
  canWithdraw: boolean
}
type WithdrawalRaw = {
  money_ok: boolean
  money_items: CheckItem[]
  data_review_version: string
  data_reviewed: boolean
  linked_ok: boolean
  linked_items: CheckItem[]
  linked_confirmed: boolean
  can_withdraw: boolean
}
const toWithdrawal = (w: WithdrawalRaw): WithdrawalStatus => ({
  moneyOk: w.money_ok,
  moneyItems: w.money_items,
  dataReviewVersion: w.data_review_version,
  dataReviewed: w.data_reviewed,
  linkedOk: w.linked_ok,
  linkedItems: w.linked_items,
  linkedConfirmed: w.linked_confirmed,
  canWithdraw: w.can_withdraw,
})

/** GET /users/me/withdrawal-checks — 탈퇴 전 3단계(남은 돈 · 삭제될 데이터 · 연결된 서비스). 서버가 매번 다시 본다 */
export const getWithdrawalStatus = async () => map(await call<WithdrawalRaw>('GET', '/users/me/withdrawal-checks'), toWithdrawal)

/** POST /users/me/withdrawal-checks/data-review — 보여 준 안내문 버전을 함께 보낸다 */
export const confirmDataReview = async (version: string) =>
  map(await call<WithdrawalRaw>('POST', '/users/me/withdrawal-checks/data-review', { version }), toWithdrawal)

/** POST /users/me/withdrawal-checks/linked-services */
export const confirmLinkedServices = async () => map(await call<WithdrawalRaw>('POST', '/users/me/withdrawal-checks/linked-services'), toWithdrawal)

/** POST /users/me/withdraw — 본인 확인(WITHDRAWAL) 필요. 성공하면 로그인이 끊긴다 */
export async function withdraw(stepUpChallengeId: string) {
  const r = await call<object>('POST', '/users/me/withdraw', { step_up_challenge_id: stepUpChallengeId })
  if (r.success) setSessionExpires(null)
  return r
}

// ---- 홈 ----

type AccountRaw = { id: string; name: string; number: string; account_type: string; status: string; is_favorite: boolean; balance: string }
const toAccount = (a: AccountRaw): Account => ({
  id: a.id,
  name: a.name,
  number: a.number,
  type: a.account_type,
  status: a.status,
  isFavorite: a.is_favorite,
  balance: Number(a.balance),
})

/** GET /account-dashboard/summary (ACCT-F08) — 해지 계좌는 빠진다 */
export async function getAccountDashboard(): Promise<ApiResult<{ totalBalance: number; accounts: Account[] }>> {
  const r = await call<{ total_balance: string; accounts: AccountRaw[] }>('GET', '/account-dashboard/summary')
  return map(r, (d) => ({
    totalBalance: Number(d.total_balance),
    accounts: d.accounts.map(toAccount),
  }))
}

type ProductRaw = { id: string; name: string; description: string; max_rate: string; term_label: string; icon: 'safe' | 'coins' }

/** GET /products/recommended — 로그인 없이 볼 수 있다 */
export async function getRecommendedProducts(): Promise<ApiResult<Product[]>> {
  const r = await call<ProductRaw[]>('GET', '/products/recommended')
  return map(r, (ps) =>
    ps.map((p) => ({ id: p.id, name: p.name, description: p.description, maxRate: p.max_rate, termLabel: p.term_label, icon: p.icon })),
  )
}

// ---- 예금·적금 상품 (Part 3 7절) ----

export type ProductType = 'TIME_DEPOSIT' | 'INSTALLMENT_SAVINGS'
export type ProductSummary = {
  id: string
  name: string
  type: ProductType
  description: string | null
  baseRate: string | null
  maxRate: string | null
  termLabel: string
  earlyTerminationAllowed: boolean
}
export type ProductDetail = ProductSummary & {
  verifiedAt: string | null
  rates: { termMin: number; termMax: number; termUnit: 'MONTH' | 'DAY'; baseRate: string; bonusRate: string | null }[]
  minAmount: number | null
  maxAmount: number | null
  amountUnit: number | null
  minMonths: number | null
  maxMonths: number | null
  selectableMonths: number[] | null
  maxPerUser: number | null
  minDays: number | null
  maxDays: number | null
  eligibility: string | null
  notes: string[]
  subscribable: boolean
}
/** 가입 기간 — 월 단위 상품은 months, 일 단위 상품(표지어음·CD)은 days */
export type Period = { months: number; days?: number }
export type Estimate = {
  rate: string
  interest: number
  principalTotal: number
  maturityAmount: number
  maturityDate: string
  firstPayment: number
}
export type Subscription = {
  id: string
  productId: string
  productName: string
  productType: ProductType
  accountNumber: string
  principal: number
  monthlyAmount: number | null
  appliedRate: string
  startDate: string
  maturityDate: string
  status: string
}

type SummaryRaw = {
  id: string
  name: string
  type: ProductType
  description: string | null
  base_rate: string | null
  max_rate: string | null
  term_label: string
  early_termination_allowed: boolean
}
type DetailRaw = SummaryRaw & {
  verified_at: string | null
  rates: { term_min: number; term_max: number; term_unit: 'MONTH' | 'DAY'; base_rate: string; bonus_rate: string | null }[]
  min_amount: string | null
  max_amount: string | null
  amount_unit: string | null
  min_months: number | null
  max_months: number | null
  selectable_months: number[] | null
  max_per_user: number | null
  min_days: number | null
  max_days: number | null
  eligibility: string | null
  notes: string[]
  subscribable: boolean
}
type EstimateRaw = {
  rate: string
  interest: string
  principal_total: string
  maturity_amount: string
  maturity_date: string
  first_payment: string
}
type SubscriptionRaw = {
  id: string
  product_id: string
  product_name: string
  product_type: ProductType
  account_number: string
  principal: string
  monthly_amount: string | null
  applied_rate: string
  start_date: string
  maturity_date: string
  status: string
}

const num = (s: string | null) => (s === null ? null : Number(s))
const toSummary = (p: SummaryRaw): ProductSummary => ({
  id: p.id,
  name: p.name,
  type: p.type,
  description: p.description,
  baseRate: p.base_rate,
  maxRate: p.max_rate,
  termLabel: p.term_label,
  earlyTerminationAllowed: p.early_termination_allowed,
})
const toEstimate = (e: EstimateRaw): Estimate => ({
  rate: e.rate,
  interest: Number(e.interest),
  principalTotal: Number(e.principal_total),
  maturityAmount: Number(e.maturity_amount),
  maturityDate: e.maturity_date,
  firstPayment: Number(e.first_payment),
})
const toSubscription = (s: SubscriptionRaw): Subscription => ({
  id: s.id,
  productId: s.product_id,
  productName: s.product_name,
  productType: s.product_type,
  accountNumber: s.account_number,
  principal: Number(s.principal),
  monthlyAmount: num(s.monthly_amount),
  appliedRate: s.applied_rate,
  startDate: s.start_date,
  maturityDate: s.maturity_date,
  status: s.status,
})

/** GET /products — 판매 중인 상품만. sort=rate 는 최고금리 높은 순 */
export async function getProducts(f: { q?: string; type?: ProductType; sort?: 'rate' }): Promise<ApiResult<ProductSummary[]>> {
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][])
  return map(await call<SummaryRaw[]>('GET', `/products?${qs}`), (ps) => ps.map(toSummary))
}

/** GET /products/{productId} */
export async function getProduct(id: string): Promise<ApiResult<ProductDetail>> {
  const r = await call<DetailRaw>('GET', `/products/${encodeURIComponent(id)}`)
  return map(r, (p) => ({
    ...toSummary(p),
    verifiedAt: p.verified_at,
    rates: p.rates.map((x) => ({ termMin: x.term_min, termMax: x.term_max, termUnit: x.term_unit, baseRate: x.base_rate, bonusRate: x.bonus_rate })),
    minAmount: num(p.min_amount),
    maxAmount: num(p.max_amount),
    amountUnit: num(p.amount_unit),
    minMonths: p.min_months,
    maxMonths: p.max_months,
    selectableMonths: p.selectable_months,
    maxPerUser: p.max_per_user,
    minDays: p.min_days,
    maxDays: p.max_days,
    eligibility: p.eligibility,
    notes: p.notes,
    subscribable: p.subscribable,
  }))
}

/** POST /products/{productId}/estimate — amount: 예금은 예치금, 적금은 월 납입액 */
export async function estimateInterest(id: string, amount: number, term: Period): Promise<ApiResult<Estimate>> {
  return map(await call<EstimateRaw>('POST', `/products/${encodeURIComponent(id)}/estimate`, { amount: String(amount), ...term }), toEstimate)
}

/** POST /products/{productId}/validate — 로그인 필요. 가입 직전과 같은 검사(계좌·잔액·한도) */
export async function validateSubscription(id: string, accountId: string, amount: number, term: Period): Promise<ApiResult<Estimate>> {
  const r = await call<EstimateRaw>('POST', `/products/${encodeURIComponent(id)}/validate`, { account_id: accountId, amount: String(amount), ...term })
  return map(r, toEstimate)
}

/** POST /auth/step-up — 중요 작업 전 본인 확인(1차는 로그인 비밀번호 재확인) */
export type StepUpAction =
  | 'SUBSCRIPTION'
  | 'ACCOUNT_STATUS_CHANGE'
  | 'TRANSFER'
  | 'WITHDRAWAL'
  | 'CARD_APPLICATION'
  | 'CARD_TERMINATION'
  | 'CARD_MANAGEMENT'
  | 'PROFILE_CHANGE'
  | 'PIN_ENROLL'
  | 'PIN_CHANGE'
  | 'PIN_RESET'
/** 간편 비밀번호(PIN)를 등록한 회원은 { pin }, 아직이면 { password } — PIN 등록·재설정은 언제나 { password } (AUTH-F12) */
export async function stepUp(action: StepUpAction, credential: { password: string } | { pin: string }): Promise<ApiResult<string>> {
  return map(await call<{ step_up_challenge_id: string }>('POST', '/auth/step-up', { action, ...credential }), (d) => d.step_up_challenge_id)
}

/** POST /subscriptions — 같은 idempotencyKey 로 다시 보내면 새 계약 없이 처음 결과를 돌려준다 */
export async function subscribe(
  b: { productId: string; accountId: string; amount: number; term: Period; stepUpChallengeId: string },
  idempotencyKey: string,
): Promise<ApiResult<Subscription>> {
  const body = { product_id: b.productId, account_id: b.accountId, amount: String(b.amount), ...b.term, step_up_challenge_id: b.stepUpChallengeId }
  return map(await call<SubscriptionRaw>('POST', '/subscriptions', body, { 'Idempotency-Key': idempotencyKey }), toSubscription)
}

/** GET /users/me/subscriptions */
export async function getMySubscriptions(): Promise<ApiResult<Subscription[]>> {
  return map(await call<SubscriptionRaw[]>('GET', '/users/me/subscriptions'), (ss) => ss.map(toSubscription))
}

export type SubscriptionDetail = Subscription & {
  earlyTerminationAllowed: boolean
  accountStatus: string
  payments: { amount: number; paidAt: string }[]
  payable: boolean
  monthlyMax: number | null
  paidThisMonth: number
}
type DetailSubRaw = SubscriptionRaw & {
  early_termination_allowed: boolean
  account_status: string
  payments: { amount: string; paid_at: string }[]
  payable: boolean
  monthly_max: string | null
  paid_this_month: string
}
const toSubDetail = (s: DetailSubRaw): SubscriptionDetail => ({
  ...toSubscription(s),
  earlyTerminationAllowed: s.early_termination_allowed,
  accountStatus: s.account_status,
  payments: s.payments.map((x) => ({ amount: Number(x.amount), paidAt: x.paid_at })),
  payable: s.payable,
  monthlyMax: num(s.monthly_max),
  paidThisMonth: Number(s.paid_this_month),
})

/** GET /users/me/subscriptions/{subscriptionId} */
export async function getMySubscription(id: string): Promise<ApiResult<SubscriptionDetail>> {
  return map(await call<DetailSubRaw>('GET', `/users/me/subscriptions/${encodeURIComponent(id)}`), toSubDetail)
}

/** POST /subscriptions/{subscriptionId}/payments — 적금 추가 납입(본인 확인 필요) */
export async function payInstallment(id: string, amount: number, stepUpChallengeId: string): Promise<ApiResult<SubscriptionDetail>> {
  const body = { amount: String(amount), step_up_challenge_id: stepUpChallengeId }
  return map(await call<DetailSubRaw>('POST', `/subscriptions/${encodeURIComponent(id)}/payments`, body), toSubDetail)
}

/** POST /subscriptions/{subscriptionId}/terminate — 중도 해지(본인 확인 필요, 원금만 돌려받음) */
export async function terminateSubscription(id: string, stepUpChallengeId: string): Promise<ApiResult<SubscriptionDetail>> {
  const body = { step_up_challenge_id: stepUpChallengeId }
  return map(await call<DetailSubRaw>('POST', `/subscriptions/${encodeURIComponent(id)}/terminate`, body), toSubDetail)
}

// ---- 계좌 (Part 2 9절 · ACCT-F01~F06) ----

export type CloseBlocker = 'BALANCE_REMAINING' | 'PENDING_TRANSFER' | 'LINKED_SUBSCRIPTION' | 'LINKED_CARD'
export type AccountDetail = Account & {
  defaultName: string
  nickname: string | null
  startDate: string
  closedAt: string | null
  balanceAsOf: string
  notificationsEnabled: boolean
  closeBlockers: CloseBlocker[]
}
type AccountDetailRaw = AccountRaw & {
  default_name: string
  nickname: string | null
  start_date: string
  closed_at: string | null
  balance_as_of: string
  notifications_enabled: boolean
  close_blockers: CloseBlocker[]
}
const toAccountDetail = (a: AccountDetailRaw): AccountDetail => ({
  ...toAccount(a),
  defaultName: a.default_name,
  nickname: a.nickname,
  startDate: a.start_date,
  closedAt: a.closed_at,
  balanceAsOf: a.balance_as_of,
  notificationsEnabled: a.notifications_enabled,
  closeBlockers: a.close_blockers,
})
const acct = (id: string) => `/accounts/${encodeURIComponent(id)}`

/** GET /accounts — 해지 계좌도 함께 온다 */
export async function getAccounts(): Promise<ApiResult<Account[]>> {
  return map(await call<AccountRaw[]>('GET', '/accounts'), (as) => as.map(toAccount))
}

/** POST /accounts — 같은 idempotencyKey 로 다시 보내면 새 계좌 없이 처음 결과를 돌려준다 */
export async function openAccount(type: 'CHECKING' | 'SAVINGS', idempotencyKey: string): Promise<ApiResult<AccountDetail>> {
  const body = { account_type: type, consents: ['required_terms'] }
  return map(await call<AccountDetailRaw>('POST', '/accounts', body, { 'Idempotency-Key': idempotencyKey }), toAccountDetail)
}

/** GET /accounts/{accountId} */
export async function getAccount(id: string): Promise<ApiResult<AccountDetail>> {
  return map(await call<AccountDetailRaw>('GET', acct(id)), toAccountDetail)
}

/** GET /accounts/{accountId}/balance — 잔액만 다시 읽기(새로고침) */
export async function getBalance(id: string): Promise<ApiResult<{ balance: number; balanceAsOf: string }>> {
  const r = await call<{ resAccountBalance: string; balance_as_of: string }>('GET', `${acct(id)}/balance`)
  return map(r, (d) => ({ balance: Number(d.resAccountBalance), balanceAsOf: d.balance_as_of }))
}

export type AccountTransaction = {
  id: string
  type: string
  direction: 'IN' | 'OUT'
  amount: number
  balanceAfter: number
  displayName: string
  createdAt: string // 2026-10-31T09:00:01+09:00
}
type AccountTransactionRaw = { id: string; type: string; direction: 'IN' | 'OUT'; amount: string; balance_after: string; display_name: string; created_at: string }

/** GET /accounts/{accountId}/transactions — 입출금 내역, 최신이 먼저. direction 을 주면 입금만·출금만 */
export async function getAccountTransactions(id: string, direction?: 'IN' | 'OUT'): Promise<ApiResult<AccountTransaction[]>> {
  const r = await call<AccountTransactionRaw[]>('GET', `${acct(id)}/transactions${direction ? `?direction=${direction}` : ''}`)
  return map(r, (ts) =>
    ts.map((t) => ({
      id: t.id,
      type: t.type,
      direction: t.direction,
      amount: Number(t.amount),
      balanceAfter: Number(t.balance_after),
      displayName: t.display_name,
      createdAt: t.created_at,
    })),
  )
}

/** PATCH /accounts/{accountId}/preferences — 별명 "" 은 기본 이름으로 */
export async function updateAccountPreferences(id: string, b: { nickname?: string; isFavorite?: boolean }): Promise<ApiResult<AccountDetail>> {
  const body = { nickname: b.nickname, is_favorite: b.isFavorite }
  return map(await call<AccountDetailRaw>('PATCH', `${acct(id)}/preferences`, body), toAccountDetail)
}

/** POST /accounts/{accountId}/suspend · resume · close — 본인 확인(ACCOUNT_STATUS_CHANGE) 필요 */
export async function changeAccountStatus(id: string, op: 'suspend' | 'resume' | 'close', stepUpChallengeId: string): Promise<ApiResult<AccountDetail>> {
  return map(await call<AccountDetailRaw>('POST', `${acct(id)}/${op}`, { step_up_challenge_id: stepUpChallengeId }), toAccountDetail)
}

/** PATCH /accounts/{accountId}/notification-settings — 입출금 알림 켜기·끄기 */
export async function setAccountNotifications(id: string, enabled: boolean): Promise<ApiResult<AccountDetail>> {
  return map(await call<AccountDetailRaw>('PATCH', `${acct(id)}/notification-settings`, { enabled }), toAccountDetail)
}

export type AppNotification = { id: string; type: string; title: string; body: string; createdAt: string; read: boolean }

/** GET /notifications — 최근 100개 */
export async function getNotifications(): Promise<ApiResult<AppNotification[]>> {
  const r = await call<{ id: string; type: string; title: string; body: string; created_at: string; read: boolean }[]>('GET', '/notifications')
  return map(r, (ns) => ns.map((n) => ({ id: n.id, type: n.type, title: n.title, body: n.body, createdAt: n.created_at, read: n.read })))
}

/** POST /notifications/read-all */
export const readAllNotifications = () => call<null>('POST', '/notifications/read-all')

// ---- 이체 (Part 5 TRX-F01·F02) ----
export const BANK = '두린은행' // 1차는 두린은행 계좌끼리만

export type TransferWarning = 'FIRST_LARGE' | 'LARGE_VS_USUAL' | 'RECENT_SAME'
export type TransferTarget = { accountNo: string; accountDisplay: string; holderName: string; isMine: boolean; warnings: TransferWarning[] }

/** GET /transfer-targets/verify — 받는 계좌 확인. amount 를 주면 재확인 화면 경고도 온다 */
export async function verifyTransferTarget(accountNo: string, fromAccountId: string, amount?: number): Promise<ApiResult<TransferTarget>> {
  const q = new URLSearchParams({ bank: BANK, account_no: accountNo, from_account_id: fromAccountId, ...(amount ? { amount: String(amount) } : {}) })
  const r = await call<{ account_no: string; account_display: string; holder_name: string; is_mine: boolean; warnings: TransferWarning[] }>(
    'GET',
    `/transfer-targets/verify?${q}`,
  )
  return map(r, (t) => ({ accountNo: t.account_no, accountDisplay: t.account_display, holderName: t.holder_name, isMine: t.is_mine, warnings: t.warnings }))
}

/** 간편 송금 목록 한 줄 (Part 5 6장) — 최근 보낸 계좌는 id 가 null */
export type SavedTarget = { id: string | null; accountNo: string; accountDisplay: string; holderName: string; nickname: string | null }
type SavedTargetRaw = { id: string | null; account_no: string; account_display: string; holder_name: string; nickname: string | null }
const toSaved = (t: SavedTargetRaw): SavedTarget => ({
  id: t.id,
  accountNo: t.account_no,
  accountDisplay: t.account_display,
  holderName: t.holder_name,
  nickname: t.nickname,
})

/** GET /transfer-targets/recent — 성공한 이체의 받는 계좌, 같은 계좌는 한 번, 최근 20개 */
export async function getRecentTargets(): Promise<ApiResult<SavedTarget[]>> {
  return map(await call<SavedTargetRaw[]>('GET', '/transfer-targets/recent'), (l) => l.map(toSaved))
}

/** GET /favorite-accounts — 자주 쓰는 계좌 */
export async function getFavorites(): Promise<ApiResult<SavedTarget[]>> {
  return map(await call<SavedTargetRaw[]>('GET', '/favorite-accounts'), (l) => l.map(toSaved))
}

/** POST /favorite-accounts — 이미 있으면 그 줄을 그대로 돌려준다 */
export async function addFavorite(accountNo: string): Promise<ApiResult<SavedTarget>> {
  return map(await call<SavedTargetRaw>('POST', '/favorite-accounts', { bank: BANK, account_no: accountNo }), toSaved)
}

/** PATCH /favorite-accounts/{id} — 별칭(null 이면 지움)·순서(0 = 맨 위). 바뀐 전체 목록이 온다 */
export async function updateFavorite(id: string, b: { nickname?: string | null; sortOrder?: number }): Promise<ApiResult<SavedTarget[]>> {
  const body = { ...('nickname' in b ? { nickname: b.nickname } : {}), ...(b.sortOrder === undefined ? {} : { sort_order: b.sortOrder }) }
  return map(await call<SavedTargetRaw[]>('PATCH', `/favorite-accounts/${encodeURIComponent(id)}`, body), (l) => l.map(toSaved))
}

/** DELETE /favorite-accounts/{id} */
export async function removeFavorite(id: string): Promise<ApiResult<unknown>> {
  return call('DELETE', `/favorite-accounts/${encodeURIComponent(id)}`)
}

export type Transfer = {
  id: string
  status: 'PENDING' | 'SUCCESS' | 'FAILED'
  failureReason: string | null
  message: string | null
  fromAccountId: string
  fromAccountDisplay: string
  toBank: string
  toAccountNo: string
  toAccountDisplay: string
  toHolderName: string
  amount: number
  fee: number
  myDisplayName: string
  theirDisplayName: string
  balanceAfter: number | null
  requestedAt: string
  completedAt: string | null
}
type TransferRaw = {
  id: string
  status: Transfer['status']
  failure_reason: string | null
  message: string | null
  from_account_id: string
  from_account_display: string
  to_bank: string
  to_account_no: string
  to_account_display: string
  to_holder_name: string
  amount: string
  fee: string
  my_display_name: string
  their_display_name: string
  balance_after: string | null
  requested_at: string
  completed_at: string | null
}
const toTransfer = (t: TransferRaw): Transfer => ({
  id: t.id,
  status: t.status,
  failureReason: t.failure_reason,
  message: t.message,
  fromAccountId: t.from_account_id,
  fromAccountDisplay: t.from_account_display,
  toBank: t.to_bank,
  toAccountNo: t.to_account_no,
  toAccountDisplay: t.to_account_display,
  toHolderName: t.to_holder_name,
  amount: Number(t.amount),
  fee: Number(t.fee),
  myDisplayName: t.my_display_name,
  theirDisplayName: t.their_display_name,
  balanceAfter: t.balance_after === null ? null : Number(t.balance_after),
  requestedAt: t.requested_at,
  completedAt: t.completed_at,
})

/** POST /transfers — 같은 idempotencyKey 로 다시 보내면 새로 보내지 않고 처음 결과를 돌려준다. 잔액 부족·한도 초과는 FAILED 결과로 온다 */
export async function sendTransfer(
  b: { fromAccountId: string; toAccountNo: string; amount: number; stepUpChallengeId: string; myDisplayName: string; theirDisplayName: string },
  idempotencyKey: string,
): Promise<ApiResult<Transfer>> {
  const body = {
    from_account_id: b.fromAccountId,
    to_bank: BANK,
    to_account_no: b.toAccountNo,
    amount: String(b.amount),
    step_up_challenge_id: b.stepUpChallengeId,
    my_display_name: b.myDisplayName,
    their_display_name: b.theirDisplayName,
  }
  return map(await call<TransferRaw>('POST', '/transfers', body, { 'Idempotency-Key': idempotencyKey }), toTransfer)
}

/** GET /transfers — 내가 보낸 이체 결과, 최신이 먼저 */
export async function getTransfers(): Promise<ApiResult<Transfer[]>> {
  return map(await call<TransferRaw[]>('GET', '/transfers'), (ts) => ts.map(toTransfer))
}

/** GET /transfers/{transferId} */
export async function getTransfer(id: string): Promise<ApiResult<Transfer>> {
  return map(await call<TransferRaw>('GET', `/transfers/${encodeURIComponent(id)}`), toTransfer)
}

// ---- 챗봇 (Part 3 7장 POST /agent/chat) — 대화 맥락(context)은 서버가 준 것을 다음 요청에 그대로 돌려보낸다 ----
export type ChatContext = { pending: 'TRANSFER_AMOUNT' | null }
export type ChatReply = { reply: string; links: { label: string; href: string }[]; suggestions: string[]; context: ChatContext }

/** POST /agent/chat — 빈 message 는 대화 시작 인사 */
export async function sendChat(message: string, context: ChatContext | null): Promise<ApiResult<ChatReply>> {
  return call<ChatReply>('POST', '/agent/chat', { message, ...(context ? { context } : {}) })
}

// ---- 카드 (Part 4 1차: CARD-F01~F05 · 결제 계좌 바꾸기 · 해지) ----

export type CardType = 'CHECK' | 'CREDIT'
export type Card = {
  id: string
  name: string
  productName: string
  companyName: string
  cardType: CardType
  number: string
  last4: string
  status: string
  creditLimit: number | null
  availableLimit: number | null
  linkedAccountId: string | null
  linkedAccountNumber: string | null
  linkedAccountName: string | null
  periodStart: string
  periodEnd: string
  periodSpent: number
  unpaidAmount: number
  nextPaymentDate: string | null
}
export type CardBill = {
  id: string | null // 진행 중(SCHEDULED) 청구서는 아직 저장 전이라 없다
  cardId: string
  cardName: string
  billingYm: string
  usageStart: string
  usageEnd: string
  paymentDate: string
  totalAmount: number
  paidAmount: number
  status: 'SCHEDULED' | 'CONFIRMED' | 'PAID' | 'OVERDUE'
  accountNumber: string | null
  lowBalance: boolean
}
export type Benefit = { category: string; rate: string; monthlyLimit: number | null }
export type CardDetail = Card & {
  issuedAt: string
  expiresAt: string
  paymentDay: number | null
  annualFee: number
  nextAnnualFeeDate: string | null
  usedAmount: number | null
  benefits: Benefit[]
  bills: CardBill[]
  paymentDayLocked: boolean
}
export type CardTransaction = {
  id: string
  approvalNo: string
  transactedAt: string
  merchant: string
  category: string
  amount: number
  canceledAmount: number
  status: 'APPROVED' | 'PARTIAL_CANCELED' | 'CANCELED'
  installmentMonths: number
  isOverseas: boolean
}
export type CardBillDetail = CardBill & { items: { transaction: CardTransaction; installmentSeq: number; principalAmount: number }[] }
export type TerminationCheck = {
  canTerminate: boolean
  blockers: string[]
  unpaidAmount: number
  periodSpent: number
  nextPaymentDate: string | null
  remainingInstallmentAmount: number
  recurringMerchants: string[]
  forfeitedPoints: number
  refundedAnnualFee: number
}
export type TerminationReason = 'NOT_USING' | 'LOW_BENEFIT' | 'HIGH_FEE' | 'OTHER'
export type CardProduct = {
  id: string
  name: string
  companyName: string
  cardType: CardType
  annualFee: number
  minAge: number
  benefits: Benefit[]
  terms: { id: string; title: string; required: boolean }[]
}
export type CardApplication = {
  id: string
  cardProductId: string
  productName: string
  cardType: CardType
  status: string
  appliedAt: string
  linkedAccountNumber: string | null
  deliveryAddress: string | null
  trackingNo: string | null
  userCardId: string | null
  history: { status: string; changedAt: string }[]
}

type CardRaw = {
  id: string
  name: string
  product_name: string
  company_name: string
  card_type: CardType
  number: string
  last4: string
  status: string
  credit_limit: string | null
  available_limit: string | null
  linked_account_id: string | null
  linked_account_number: string | null
  linked_account_name: string | null
  period_start: string
  period_end: string
  period_spent: string
  unpaid_amount: string
  next_payment_date: string | null
}
type CardBillRaw = {
  id: string | null
  card_id: string
  card_name: string
  billing_ym: string
  usage_start: string
  usage_end: string
  payment_date: string
  total_amount: string
  paid_amount: string
  status: CardBill['status']
  account_number: string | null
  low_balance: boolean
}
type BenefitRaw = { category: string; rate: string; monthly_limit: string | null }
type CardDetailRaw = CardRaw & {
  issued_at: string
  expires_at: string
  payment_day: number | null
  annual_fee: string
  next_annual_fee_date: string | null
  used_amount: string | null
  benefits: BenefitRaw[]
  bills: CardBillRaw[]
  payment_day_locked: boolean
}
type CardTransactionRaw = {
  id: string
  approval_no: string
  transacted_at: string
  merchant: string
  category: string
  amount: string
  canceled_amount: string
  status: CardTransaction['status']
  installment_months: number
  is_overseas: boolean
}
type CardApplicationRaw = {
  id: string
  card_product_id: string
  product_name: string
  card_type: CardType
  status: string
  applied_at: string
  linked_account_number: string | null
  delivery_address: string | null
  tracking_no: string | null
  user_card_id: string | null
  history: { status: string; changed_at: string }[]
}

const toCard = (c: CardRaw): Card => ({
  id: c.id,
  name: c.name,
  productName: c.product_name,
  companyName: c.company_name,
  cardType: c.card_type,
  number: c.number,
  last4: c.last4,
  status: c.status,
  creditLimit: num(c.credit_limit),
  availableLimit: num(c.available_limit),
  linkedAccountId: c.linked_account_id,
  linkedAccountNumber: c.linked_account_number,
  linkedAccountName: c.linked_account_name,
  periodStart: c.period_start,
  periodEnd: c.period_end,
  periodSpent: Number(c.period_spent),
  unpaidAmount: Number(c.unpaid_amount),
  nextPaymentDate: c.next_payment_date,
})
const toBill = (b: CardBillRaw): CardBill => ({
  id: b.id,
  cardId: b.card_id,
  cardName: b.card_name,
  billingYm: b.billing_ym,
  usageStart: b.usage_start,
  usageEnd: b.usage_end,
  paymentDate: b.payment_date,
  totalAmount: Number(b.total_amount),
  paidAmount: Number(b.paid_amount),
  status: b.status,
  accountNumber: b.account_number,
  lowBalance: b.low_balance,
})
const toBenefit = (b: BenefitRaw): Benefit => ({ category: b.category, rate: b.rate, monthlyLimit: num(b.monthly_limit) })
const toCardDetail = (c: CardDetailRaw): CardDetail => ({
  ...toCard(c),
  issuedAt: c.issued_at,
  expiresAt: c.expires_at,
  paymentDay: c.payment_day,
  annualFee: Number(c.annual_fee),
  nextAnnualFeeDate: c.next_annual_fee_date,
  usedAmount: num(c.used_amount),
  benefits: c.benefits.map(toBenefit),
  bills: c.bills.map(toBill),
  paymentDayLocked: c.payment_day_locked,
})
const toCardTx = (t: CardTransactionRaw): CardTransaction => ({
  id: t.id,
  approvalNo: t.approval_no,
  transactedAt: t.transacted_at,
  merchant: t.merchant,
  category: t.category,
  amount: Number(t.amount),
  canceledAmount: Number(t.canceled_amount),
  status: t.status,
  installmentMonths: t.installment_months,
  isOverseas: t.is_overseas,
})
const toApplication = (a: CardApplicationRaw): CardApplication => ({
  id: a.id,
  cardProductId: a.card_product_id,
  productName: a.product_name,
  cardType: a.card_type,
  status: a.status,
  appliedAt: a.applied_at,
  linkedAccountNumber: a.linked_account_number,
  deliveryAddress: a.delivery_address,
  trackingNo: a.tracking_no,
  userCardId: a.user_card_id,
  history: a.history.map((h) => ({ status: h.status, changedAt: h.changed_at })),
})
const card = (id: string) => `/cards/${encodeURIComponent(id)}`

/** GET /cards — 내 카드(해지한 카드 빼고). 홈도 같은 목록을 쓴다 */
export async function getMyCards(): Promise<ApiResult<Card[]>> {
  return map(await call<CardRaw[]>('GET', '/cards'), (cs) => cs.map(toCard))
}

/** GET /cards/{cardId} — 혜택·청구서 포함 */
export async function getCard(id: string): Promise<ApiResult<CardDetail>> {
  return map(await call<CardDetailRaw>('GET', card(id)), toCardDetail)
}

/** GET /cards/{cardId}/transactions — month: YYYYMM (가맹점 분류 거르기는 화면이 받은 목록에서 바로 한다) */
export async function getCardTransactions(id: string, month?: string): Promise<ApiResult<CardTransaction[]>> {
  const r = await call<CardTransactionRaw[]>('GET', `${card(id)}/transactions${month ? `?month=${month}` : ''}`)
  return map(r, (ts) => ts.map(toCardTx))
}

/** GET /card-bills — 결제 캘린더(내 모든 카드의 청구서) */
export async function getCardBills(): Promise<ApiResult<CardBill[]>> {
  return map(await call<CardBillRaw[]>('GET', '/card-bills'), (bs) => bs.map(toBill))
}

/** GET /card-bills/{billId} — 청구서에 든 거래 */
export async function getCardBill(id: string): Promise<ApiResult<CardBillDetail>> {
  const r = await call<CardBillRaw & { items: { transaction: CardTransactionRaw; installment_seq: number; principal_amount: string }[] }>(
    'GET',
    `/card-bills/${encodeURIComponent(id)}`,
  )
  return map(r, (b) => ({
    ...toBill(b),
    items: b.items.map((i) => ({ transaction: toCardTx(i.transaction), installmentSeq: i.installment_seq, principalAmount: Number(i.principal_amount) })),
  }))
}

/** PATCH /cards/{cardId}/linked-account — 결제·출금 계좌 바꾸기 (본인 확인 CARD_MANAGEMENT) */
export async function changeCardAccount(id: string, accountId: string, stepUpChallengeId: string): Promise<ApiResult<CardDetail>> {
  const r = await call<CardDetailRaw>('PATCH', `${card(id)}/linked-account`, { account_id: accountId, step_up_challenge_id: stepUpChallengeId })
  return map(r, toCardDetail)
}

type TerminationRaw = {
  can_terminate: boolean
  blockers: string[]
  unpaid_amount: string
  period_spent: string
  next_payment_date: string | null
  remaining_installment_amount: string
  recurring_merchants: string[]
  forfeited_points: string
  refunded_annual_fee: string
}
const toTermination = (t: TerminationRaw): TerminationCheck => ({
  canTerminate: t.can_terminate,
  blockers: t.blockers,
  unpaidAmount: Number(t.unpaid_amount),
  periodSpent: Number(t.period_spent),
  nextPaymentDate: t.next_payment_date,
  remainingInstallmentAmount: Number(t.remaining_installment_amount),
  recurringMerchants: t.recurring_merchants,
  forfeitedPoints: Number(t.forfeited_points),
  refundedAnnualFee: Number(t.refunded_annual_fee),
})

/** GET /cards/{cardId}/termination-check — 해지 전에 확인할 것 */
export async function getTerminationCheck(id: string): Promise<ApiResult<TerminationCheck>> {
  return map(await call<TerminationRaw>('GET', `${card(id)}/termination-check`), toTermination)
}

/** POST /cards/{cardId}/terminate (본인 확인 CARD_TERMINATION) */
export async function terminateCard(id: string, reason: TerminationReason, detail: string, stepUpChallengeId: string): Promise<ApiResult<TerminationCheck>> {
  const body = { reason_code: reason, reason_detail: detail || null, step_up_challenge_id: stepUpChallengeId }
  return map(await call<TerminationRaw>('POST', `${card(id)}/terminate`, body), toTermination)
}

/** GET /card-products — 신청할 수 있는 카드(판매 중) */
export async function getCardProducts(): Promise<ApiResult<CardProduct[]>> {
  type Raw = { id: string; name: string; company_name: string; card_type: CardType; annual_fee: string; min_age: number; benefits: BenefitRaw[]; terms: CardProduct['terms'] }
  return map(await call<Raw[]>('GET', '/card-products'), (ps) =>
    ps.map((p) => ({ id: p.id, name: p.name, companyName: p.company_name, cardType: p.card_type, annualFee: Number(p.annual_fee), minAge: p.min_age, benefits: p.benefits.map(toBenefit), terms: p.terms })),
  )
}

/** GET /card-applications — 신청·배송 조회 */
export async function getCardApplications(): Promise<ApiResult<CardApplication[]>> {
  return map(await call<CardApplicationRaw[]>('GET', '/card-applications'), (as) => as.map(toApplication))
}

/** POST /card-applications — 같은 idempotencyKey 로 다시 보내면 새 신청 없이 처음 결과 (본인 확인 CARD_APPLICATION) */
export async function applyCard(
  b: { productId: string; accountId: string; address: string; agreedTermIds: string[]; stepUpChallengeId: string },
  idempotencyKey: string,
): Promise<ApiResult<CardApplication>> {
  const body = { card_product_id: b.productId, linked_account_id: b.accountId, delivery_address: b.address, agreed_term_ids: b.agreedTermIds, step_up_challenge_id: b.stepUpChallengeId }
  return map(await call<CardApplicationRaw>('POST', '/card-applications', body, { 'Idempotency-Key': idempotencyKey }), toApplication)
}

/** POST /card-applications/{id}/deliver — 시연용 「배송 완료」 (1차는 실제 배송이 없다) */
export async function markDelivered(id: string): Promise<ApiResult<CardApplication>> {
  return map(await call<CardApplicationRaw>('POST', `/card-applications/${encodeURIComponent(id)}/deliver`), toApplication)
}

/** POST /card-applications/{id}/activate — 받은 카드 등록 */
export async function activateCard(id: string): Promise<ApiResult<CardApplication>> {
  return map(await call<CardApplicationRaw>('POST', `/card-applications/${encodeURIComponent(id)}/activate`), toApplication)
}

// ---- 간편 비밀번호 PIN (Part 1 AUTH-F11~F13) — 먼저 stepUp 으로 본인 확인 번호를 받고, 새 PIN 을 두 번 보낸다 ----
export type PinStatus = { enabled: boolean; lockedUntil: string | null; changedAt: string | null }
type PinStatusRaw = { enabled: boolean; locked_until: string | null; changed_at: string | null }
const toPinStatus = (p: PinStatusRaw): PinStatus => ({ enabled: p.enabled, lockedUntil: p.locked_until, changedAt: p.changed_at })

/** GET /auth/pin */
export async function getPinStatus(): Promise<ApiResult<PinStatus>> {
  return map(await call<PinStatusRaw>('GET', '/auth/pin'), toPinStatus)
}

/** POST /auth/pin/enroll · /change · /reset — 본인 확인은 순서대로 PIN_ENROLL(비밀번호) · PIN_CHANGE(지금 PIN) · PIN_RESET(비밀번호) */
export async function setPin(op: 'enroll' | 'change' | 'reset', stepUpChallengeId: string, pin: string, pinConfirm: string): Promise<ApiResult<PinStatus>> {
  const r = await call<PinStatusRaw>('POST', `/auth/pin/${op}`, { step_up_challenge_id: stepUpChallengeId, pin, pin_confirm: pinConfirm })
  return map(r, toPinStatus)
}
