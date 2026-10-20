// @vitest-environment jsdom
import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useTossBanner } from './useTossBanner'

vi.mock('@apps-in-toss/web-framework', () => {
  const supported = Object.assign(() => {}, { isSupported: () => true })
  return {
    isMinVersionSupported: () => true,
    TossAds: {
      initialize: Object.assign(
        ({ callbacks }: { callbacks: { onInitialized: () => void } }) => setTimeout(callbacks.onInitialized, 0),
        { isSupported: () => true },
      ),
      attachBanner: Object.assign(() => ({ destroy: () => {} }), supported),
    },
  }
})

describe('useTossBanner', () => {
  it('초기화가 끝난 뒤 다시 마운트되면 첫 렌더부터 배너 자리를 잡는다', async () => {
    const first = renderHook(() => useTossBanner('ad-id'))
    expect(first.result.current.available).toBe(false)
    await waitFor(() => expect(first.result.current.available).toBe(true))
    first.unmount()

    // 홈 복원: 첫 렌더에서 이미 available이어야 스크롤 위치가 밀리지 않는다
    const second = renderHook(() => useTossBanner('ad-id'))
    expect(second.result.current.available).toBe(true)
  })
})
