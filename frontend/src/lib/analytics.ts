import { Analytics } from '@apps-in-toss/web-framework'

type Params = Record<string, string | number | boolean>

// 로깅 실패가 화면 동작에 영향을 주면 안 된다. 개인정보·검색어 원문·바코드 번호는 넘기지 않는다.
function send(kind: 'screen' | 'click', logName: string, params: Params) {
  try {
    Promise.resolve(Analytics[kind]({ log_name: logName, ...params })).catch(() => {})
  } catch {
    // 토스 앱 밖(일반 브라우저 등)에서는 무시한다
  }
}

export const logScreen = (logName: string, params: Params = {}) => send('screen', logName, params)
export const logClick = (logName: string, params: Params = {}) => send('click', logName, params)
