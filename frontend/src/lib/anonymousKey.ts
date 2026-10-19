import { User } from '@apps-in-toss/web-framework'

let started = false

/**
 * 앱 시작 시 한 번만 식별키를 발급받는다. 서버로 보내지 않는다.
 * 앱 버전이 낮아 지원하지 않거나 실패해도 앱은 키 없이 정상 동작한다.
 */
export async function initAnonymousKey(): Promise<void> {
  if (started) return
  started = true
  try {
    const result: unknown = await User.getAnonymousKey()
    if (result === 'ERROR' || result == null) console.warn('식별키를 받지 못했어요')
  } catch (e) {
    console.warn('식별키를 받지 못했어요', e)
  }
}
