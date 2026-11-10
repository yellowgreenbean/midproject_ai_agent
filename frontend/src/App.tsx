// 화면 고르기 — 주소 뒤 #/경로 로 고른다.
// shortcut: 화면이 몇 개 안 돼 라우터 패키지 없이 해시만 본다. 화면이 늘거나 뒤로 가기 처리가 복잡해지면 react-router 를 들인다(새 의존성이라 먼저 물어볼 것).
import { useEffect, useState } from 'react'
import SignupPage from './pages/SignupPage'
import LoginPage from './pages/LoginPage'
import FindIdPage from './pages/FindIdPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import HomePage from './pages/HomePage'
import ComingSoonPage from './pages/ComingSoonPage'
import ProductsPage from './pages/ProductsPage'
import ProductDetailPage from './pages/ProductDetailPage'
import SubscribePage from './pages/SubscribePage'
import MySavingsPage from './pages/MySavingsPage'
import SavingDetailPage from './pages/SavingDetailPage'
import AccountsPage from './pages/AccountsPage'
import AccountOpenPage from './pages/AccountOpenPage'
import AccountDetailPage from './pages/AccountDetailPage'
import NotificationsPage from './pages/NotificationsPage'
import CardsPage from './pages/CardsPage'
import CardDetailPage from './pages/CardDetailPage'
import CardBillPage from './pages/CardBillPage'
import CardApplyPage from './pages/CardApplyPage'
import TransferPage from './pages/TransferPage'
import TransfersPage from './pages/TransfersPage'
import ScheduledTransfersPage from './pages/ScheduledTransfersPage'
import TransferResultPage from './pages/TransferResultPage'
import TransactionsPage from './pages/TransactionsPage'
import ChatPage from './pages/ChatPage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'
import PasswordChangePage from './pages/PasswordChangePage'
import PinPage from './pages/PinPage'
import ConsentsPage from './pages/ConsentsPage'
import WithdrawPage from './pages/WithdrawPage'
import TransferLimitsPage from './pages/TransferLimitsPage'

const TITLES = { signup: '회원가입', login: '로그인', findId: '아이디 찾기', resetPassword: '비밀번호 재설정', home: '홈', products: '금융상품', product: '상품 상세', subscribe: '상품 가입', savings: '내 가입 상품', saving: '내 가입 상품', accounts: '내 계좌', accountOpen: '계좌 개설', account: '계좌 상세', notifications: '알림', transfer: '송금', transfers: '이체 결과', scheduled: '예약·자동이체', transferResult: '이체 결과', transactions: '거래내역', chat: '두린 챗봇', settings: '마이페이지', profile: '내 정보', password: '비밀번호 변경', pin: '간편 비밀번호', consents: '약관 및 동의 내역', withdraw: '회원 탈퇴', limits: '이체 한도', cards: '내 카드', card: '카드 상세', cardBill: '카드 청구서', cardApply: '카드 신청', soon: '준비 중' }
type Page = keyof typeof TITLES
const PAGES: Record<string, Page> = { '/signup': 'signup', '/login': 'login', '/find-id': 'findId', '/reset-password': 'resetPassword', '/home': 'home', '/products': 'products', '/my/savings': 'savings', '/accounts': 'accounts', '/accounts/new': 'accountOpen', '/notifications': 'notifications', '/transfer': 'transfer', '/transfers': 'transfers', '/scheduled-transfers': 'scheduled', '/transactions': 'transactions', '/chat': 'chat', '/settings': 'settings', '/settings/profile': 'profile', '/settings/password': 'password', '/settings/pin': 'pin', '/settings/terms': 'consents', '/settings/withdraw': 'withdraw', '/settings/limits': 'limits', '/cards': 'cards', '/cards/apply': 'cardApply' }

export default function App() {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const onChange = () => {
      setHash(location.hash)
      scrollTo(0, 0)
    }
    addEventListener('hashchange', onChange)
    return () => removeEventListener('hashchange', onChange)
  }, [])

  const [path, qs = ''] = (hash.replace(/^#/, '') || '/home').split('?')
  const product = path.match(/^\/products\/([\w-]+)(\/subscribe)?$/)
  const saving = path.match(/^\/my\/savings\/([\w-]+)$/)
  const account = path.match(/^\/accounts\/([\w-]+)$/)
  const transfer = path.match(/^\/transfers\/([\w-]+)$/)
  const card = path.match(/^\/cards\/([\w-]+)$/)
  const bill = path.match(/^\/card-bills\/([\w-]+)$/)
  const page: Page = PAGES[path] ?? (product ? (product[2] ? 'subscribe' : 'product') : saving ? 'saving' : account ? 'account' : transfer ? 'transferResult' : card ? 'card' : bill ? 'cardBill' : 'soon')
  useEffect(() => {
    document.title = `두린뱅크 · ${TITLES[page]}`
  }, [page])
  if (page === 'signup') return <SignupPage />
  if (page === 'login') return <LoginPage expired={new URLSearchParams(qs).get('expired')} />
  if (page === 'findId') return <FindIdPage />
  if (page === 'resetPassword') return <ResetPasswordPage />
  if (page === 'home') return <HomePage />
  if (page === 'products') return <ProductsPage />
  if (page === 'savings') return <MySavingsPage />
  if (page === 'accounts') return <AccountsPage />
  if (page === 'accountOpen') return <AccountOpenPage />
  if (page === 'account' && account) return <AccountDetailPage key={account[1]} id={account[1]} />
  if (page === 'notifications') return <NotificationsPage />
  if (page === 'transfer') return <TransferPage query={new URLSearchParams(qs)} />
  if (page === 'transfers') return <TransfersPage />
  if (page === 'scheduled') return <ScheduledTransfersPage />
  if (page === 'transactions') return <TransactionsPage />
  if (page === 'chat') return <ChatPage />
  if (page === 'settings') return <SettingsPage />
  if (page === 'profile') return <ProfilePage />
  if (page === 'password') return <PasswordChangePage />
  if (page === 'pin') return <PinPage />
  if (page === 'consents') return <ConsentsPage />
  if (page === 'withdraw') return <WithdrawPage />
  if (page === 'limits') return <TransferLimitsPage />
  if (page === 'transferResult' && transfer) return <TransferResultPage key={transfer[1]} id={transfer[1]} />
  if (page === 'cards') return <CardsPage />
  if (page === 'cardApply') return <CardApplyPage />
  if (page === 'card' && card) return <CardDetailPage key={card[1]} id={card[1]} />
  if (page === 'cardBill' && bill) return <CardBillPage key={bill[1]} id={bill[1]} />
  if (page === 'saving' && saving) return <SavingDetailPage key={saving[1]} id={saving[1]} />
  if (page === 'product' && product) return <ProductDetailPage key={product[1]} id={product[1]} />
  if (page === 'subscribe' && product) return <SubscribePage key={product[1]} id={product[1]} query={new URLSearchParams(qs)} />
  return <ComingSoonPage />
}
