// 화면을 그리다 오류가 나면 하얀 빈 화면 대신 안내 — 오류 내용은 React 가 개발자 도구 콘솔에 남긴다
import { Component, type ReactNode } from 'react'

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="signup-done">
        <div className="done-card" role="alert">
          <h1>화면에 문제가 생겼어요</h1>
          <p>홈으로 돌아가 다시 해 주세요. 계속되면 새로고침해 주세요.</p>
          {/* 주소만 바꾸면 이 안내가 그대로 남는다 — 새로 불러 처음부터 */}
          <button type="button" className="done-action" onClick={() => { location.hash = '#/home'; location.reload() }}>
            홈으로 가기
          </button>
        </div>
      </main>
    )
  }
}
