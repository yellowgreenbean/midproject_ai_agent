// 두린 챗봇 팝업 (자연어 입력, docs/기획서.md Part 3 5장) — 오른쪽 아래 버튼을 누르면 채팅창이 떠오른다.
// 화면마다 AppShell 이 새로 그려지므로, 대화 내용은 이 파일 안(모듈)에 들고 있어 화면을 옮겨도 이어진다.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import Icon from '../components/Icon'
import { sendChat, type ChatContext, type ChatReply } from '../api'
import logoMark from '../assets/logo-mark.png'
import './ChatPage.css'

type Message = ({ from: 'me' } & Pick<ChatReply, 'reply'>) | ({ from: 'bot' } & Omit<ChatReply, 'context'>)

// 다른 곳(예: #/chat 주소)에서 창을 열 때 보내는 신호
export const CHAT_OPEN_EVENT = 'durin:chat-open'

const saved: { messages: Message[]; context: ChatContext | null; open: boolean; greeting: boolean } = { messages: [], context: null, open: false, greeting: false }

export default function ChatWidget() {
  const [open, setOpenState] = useState(saved.open)
  const [messages, setMessagesState] = useState<Message[]>(saved.messages)
  const [context, setContext] = useState<ChatContext | null>(saved.context)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  const setOpen = (v: boolean) => {
    saved.open = v
    setOpenState(v)
  }
  const setMessages = (f: (m: Message[]) => Message[]) =>
    setMessagesState((m) => {
      saved.messages = f(m)
      return saved.messages
    })

  function show(r: Awaited<ReturnType<typeof sendChat>>) {
    setBusy(false)
    if (!r.success) return setMessages((m) => [...m, { from: 'bot', reply: r.error.message, links: [], suggestions: [] }])
    saved.context = r.data.context
    setContext(r.data.context)
    setMessages((m) => [...m, { from: 'bot', reply: r.data.reply, links: r.data.links, suggestions: r.data.suggestions }])
  }

  // 열기 — 처음 열 때만 인사를 받는다 (두 번 눌러도 인사는 한 번)
  function openChat() {
    setOpen(true)
    if (saved.messages.length > 0 || saved.greeting) return
    saved.greeting = true
    setBusy(true)
    void sendChat('', null).then(show)
  }

  useEffect(() => {
    window.addEventListener(CHAT_OPEN_EVENT, openChat)
    return () => window.removeEventListener(CHAT_OPEN_EVENT, openChat)
  })

  useEffect(() => {
    if (!open) return
    end.current?.scrollIntoView({ block: 'end' })
    input.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, messages])

  function say(message: string) {
    const m = message.trim()
    if (!m || busy) return
    setMessages((list) => [...list, { from: 'me', reply: m }])
    setText('')
    setBusy(true)
    void sendChat(m, context).then(show)
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    say(text)
  }

  const lastBot = messages.findLastIndex((m) => m.from === 'bot')
  const suggestions = lastBot >= 0 && messages[lastBot].from === 'bot' ? messages[lastBot].suggestions : []

  return (
    <>
      {open && (
        <section className="chat-pop" role="dialog" aria-label="두린 AI 상담">
          <header className="chat-head">
            <img src={logoMark} alt="" className="chat-head-logo" />
            <span className="chat-head-text">
              <strong>두린 AI</strong>
              <small>
                <span className="chat-dot" aria-hidden="true" />
                무엇이든 편하게 물어보세요
              </small>
            </span>
            <button type="button" className="chat-x" aria-label="채팅창 닫기" onClick={() => setOpen(false)}>
              ×
            </button>
          </header>

          <div className="chat-log" role="log" aria-live="polite" aria-busy={busy}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg is-${m.from}`}>
                {m.from === 'bot' && <img src={logoMark} alt="" className="chat-avatar" />}
                <div className="chat-msg-body">
                  <p className="chat-bubble">{m.reply}</p>
                  {m.from === 'bot' && m.links.length > 0 && (
                    <div className="chat-links">
                      {m.links.map((l) => (
                        <a key={l.href} className="chat-link" href={l.href} onClick={() => setOpen(false)}>
                          {l.label}
                          <Icon name="chevron" size={16} />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="chat-msg is-bot">
                <img src={logoMark} alt="" className="chat-avatar" />
                <p className="chat-bubble chat-typing" aria-label="답변을 준비하고 있어요">
                  <span />
                  <span />
                  <span />
                </p>
              </div>
            )}
            <div ref={end} />
          </div>

          {suggestions.length > 0 && (
            <div className="chat-suggest" aria-label="이렇게 물어보세요">
              {suggestions.map((s) => (
                <button key={s} type="button" onClick={() => say(s)} disabled={busy}>
                  {s}
                </button>
              ))}
            </div>
          )}

          <form className="chat-form" onSubmit={onSubmit}>
            <input
              ref={input}
              aria-label="챗봇에게 보낼 말"
              placeholder="메시지를 입력해 주세요"
              value={text}
              maxLength={500}
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit" className="chat-send" aria-label="보내기" disabled={busy || !text.trim()}>
              <Icon name="send" size={18} />
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        className={`chat-fab${open ? ' is-open' : ''}`}
        aria-label={open ? '채팅창 닫기' : '두린 AI 상담 열기'}
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openChat())}
      >
        {open ? <span className="chat-fab-x">×</span> : <Icon name="chat" size={28} />}
      </button>
    </>
  )
}
