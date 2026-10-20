import { isMinVersionSupported, TossAds } from '@apps-in-toss/web-framework'
import { useEffect, useRef, useState } from 'react'

const MIN_VERSION = '5.241.0' as const

type InitState = 'ready' | 'failed'

let initPromise: Promise<InitState> | null = null
// 초기화가 끝난 뒤 다시 마운트되면(홈 복원) 첫 렌더부터 배너 자리를 잡아 스크롤 위치가 밀리지 않게 한다
let initResult: InitState | null = null

function isBannerSupported(): boolean {
  try {
    return (
      TossAds.initialize.isSupported() &&
      TossAds.attachBanner.isSupported() &&
      isMinVersionSupported({ android: MIN_VERSION, ios: MIN_VERSION })
    )
  } catch {
    return false
  }
}

// SDK 초기화는 앱 전체에서 한 번만 한다.
function initTossAds(): Promise<InitState> {
  initPromise ??= new Promise<InitState>((resolve) => {
    try {
      TossAds.initialize({
        callbacks: {
          onInitialized: () => resolve('ready'),
          onInitializationFailed: (error) => {
            console.error('Toss Ads 초기화 실패:', error)
            resolve('failed')
          },
        },
      })
    } catch (e) {
      console.error('Toss Ads 초기화 실패:', e)
      resolve('failed')
    }
  }).then((s) => (initResult = s))
  return initPromise
}

/**
 * 배너를 컨테이너에 붙이고 화면을 떠날 때 destroy한다.
 * `ref`를 단 컨테이너는 `available`일 때만 렌더링한다 (지원하지 않으면 빈 공간을 남기지 않는다).
 */
export function useTossBanner(adGroupId: string | null) {
  const ref = useRef<HTMLDivElement>(null)
  const [supported] = useState(isBannerSupported)
  const [state, setState] = useState<InitState | 'pending'>(() => initResult ?? 'pending')
  const enabled = supported && adGroupId !== null

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    void initTossAds().then((s) => {
      if (!cancelled) setState(s)
    })
    return () => {
      cancelled = true
    }
  }, [enabled])

  const available = enabled && state === 'ready'

  useEffect(() => {
    if (!available || !ref.current || !adGroupId) return
    let attached: { destroy: () => void } | undefined
    try {
      attached = TossAds.attachBanner(adGroupId, ref.current, {
        theme: 'light',
        callbacks: {
          onNoFill: (p) => console.warn('표시할 광고가 없어요', p.slotId),
          onAdFailedToRender: (p) => console.error('광고 렌더링 실패', p.error.message),
        },
      })
    } catch (e) {
      console.error('배너 부착 실패', e)
    }
    return () => attached?.destroy()
  }, [available, adGroupId])

  return { ref, available }
}
