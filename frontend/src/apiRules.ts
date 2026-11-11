// 서버 호출이 실패했을 때 화면에 띄울 말 — api.ts 의 call 이 쓴다(테스트: tests/apiRules.test.ts)
import type { ApiError } from './api'

export const TIMEOUT_MS = 30_000
export const CHAT_TIMEOUT_MS = 100_000 // 챗봇은 제미나이를 세 번까지 기다린다(길 고르기 · 뜻 검색 · 답 쓰기, 각각 한 번 더 시도)

/** gotResponse: 서버가 답은 했는데 평소 모양(JSON)이 아니었다 */
export function callFailure(e: unknown, method: string, gotResponse: boolean): ApiError {
  if (gotResponse) return { code: 'SERVER_ERROR', message: '서버에서 문제가 생겼어요. 잠시 후 다시 해 주세요.' }
  if (e instanceof DOMException && e.name === 'TimeoutError')
    return {
      code: 'TIMEOUT',
      // 보내기·바꾸기는 서버에서 이미 처리됐을 수 있다 — 같은 걸 또 하기 전에 결과부터
      message: method === 'GET' ? '응답이 너무 늦어요. 잠시 후 다시 해 주세요.' : '응답이 너무 늦어요. 처리됐을 수 있으니 결과를 먼저 확인한 뒤 다시 해 주세요.',
    }
  return { code: 'NETWORK', message: '서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.' }
}
