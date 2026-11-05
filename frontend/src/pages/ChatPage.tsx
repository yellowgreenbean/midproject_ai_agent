// #/chat 주소 — 챗봇은 이제 오른쪽 아래 팝업(ChatWidget)이다. 이 주소로 오면 홈으로 돌려보내고 팝업을 연다
import { useEffect } from 'react'
import { CHAT_OPEN_EVENT } from './ChatWidget'

export default function ChatPage() {
  useEffect(() => {
    location.replace('#/home')
    setTimeout(() => window.dispatchEvent(new Event(CHAT_OPEN_EVENT))) // 홈 화면이 그려진 다음에 연다
  }, [])
  return null
}
