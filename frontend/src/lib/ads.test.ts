import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AD_FREE_PASS_MS, FREE_FIRST_N, INTERSTITIAL_COOLDOWN_MS, TEST_AD_GROUP_ID } from './adConfig'

type Handlers = { options: { adGroupId: string }; onEvent: (e: { type: string }) => void; onError: (e: Error) => void }

const sdk = vi.hoisted(() => ({
  store: new Map<string, string>(),
  supported: true,
  loads: [] as Handlers[],
  shows: [] as Handlers[],
}))

vi.mock('@apps-in-toss/web-framework', () => ({
  loadFullScreenAd: Object.assign(
    (p: Handlers) => {
      sdk.loads.push(p)
      return () => {}
    },
    { isSupported: () => sdk.supported },
  ),
  showFullScreenAd: Object.assign(
    (p: Handlers) => {
      sdk.shows.push(p)
      return () => {}
    },
    { isSupported: () => sdk.supported },
  ),
  Storage: {
    getItem: async (k: string) => sdk.store.get(k) ?? null,
    setItem: async (k: string, v: string) => void sdk.store.set(k, v),
  },
}))

const flush = () => vi.advanceTimersByTimeAsync(0)

// 모듈 상태(쿨다운·로드 상태)는 앱 실행 단위라 테스트마다 새로 불러온다
async function freshAds() {
  vi.resetModules()
  return import('./ads')
}

/** 대기 중인 로드 요청에 차례로 loaded 이벤트를 보낸다(한 번에 하나씩 로드되는지도 함께 확인된다) */
async function finishLoads() {
  for (let i = 0; i < 4; i++) {
    await flush()
    const pending = sdk.loads.splice(0)
    for (const p of pending) p.onEvent({ type: 'loaded' })
  }
  await flush()
}

const lastShow = () => sdk.shows[sdk.shows.length - 1]

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-27T09:00:00+09:00'))
  sdk.store.clear()
  sdk.supported = true
  sdk.loads.length = 0
  sdk.shows.length = 0
  // 무료 스캔 횟수는 이미 다 쓴 상태로 시작한다
  sdk.store.set('ads.scanCount', String(FREE_FIRST_N))
})
afterEach(() => {
  vi.useRealTimers()
})

describe('광고 그룹 ID', () => {
  it('test 모드는 테스트 ID, live는 상수 ID이고 비어 있으면 null', async () => {
    const { resolveFullScreenAdGroupId } = await freshAds()
    expect(resolveFullScreenAdGroupId('interstitial', {}, 'production')).toBe(TEST_AD_GROUP_ID.interstitial)
    expect(resolveFullScreenAdGroupId('reward', {}, 'production')).toBe(TEST_AD_GROUP_ID.reward)
    const live = { interstitial: 'i-id', reward: ' ' }
    expect(resolveFullScreenAdGroupId('interstitial', {}, 'live', live)).toBe('i-id')
    expect(resolveFullScreenAdGroupId('reward', { VITE_ADS_MODE: 'live' }, 'production', live)).toBeNull()
  })
})

describe('전면광고 노출 판정', () => {
  it('무료 횟수 안이거나 이용권 중이거나 쿨다운 중이면 띄우지 않는다', async () => {
    const { shouldShowInterstitial } = await freshAds()
    const base = { scanCount: FREE_FIRST_N + 1, now: 1_000_000, lastShownAt: Number.NEGATIVE_INFINITY, adFreeUntil: 0 }
    expect(shouldShowInterstitial(base)).toBe(true)
    expect(shouldShowInterstitial({ ...base, scanCount: FREE_FIRST_N })).toBe(false)
    expect(shouldShowInterstitial({ ...base, adFreeUntil: base.now + 1 })).toBe(false)
    expect(shouldShowInterstitial({ ...base, lastShownAt: base.now - INTERSTITIAL_COOLDOWN_MS + 1 })).toBe(false)
    expect(shouldShowInterstitial({ ...base, lastShownAt: base.now - INTERSTITIAL_COOLDOWN_MS })).toBe(true)
  })
})

describe('스캔 전면광고', () => {
  it('미리 로드는 전면 → 리워드 순서로 하나씩 한다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await flush()
    expect(sdk.loads.map((l) => l.options.adGroupId)).toEqual([TEST_AD_GROUP_ID.interstitial])
    sdk.loads.splice(0)[0].onEvent({ type: 'loaded' })
    await flush()
    expect(sdk.loads.map((l) => l.options.adGroupId)).toEqual([TEST_AD_GROUP_ID.reward])
  })

  it('광고가 닫힌 뒤에 resolve하고, 90초 안의 다음 스캔은 광고 없이 통과한다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()

    let proceeded = false
    void ads.showScanInterstitial().then(() => (proceeded = true))
    await flush()
    expect(sdk.shows).toHaveLength(1)
    lastShow().onEvent({ type: 'show' })
    await flush()
    expect(proceeded).toBe(false)
    lastShow().onEvent({ type: 'dismissed' })
    await flush()
    expect(proceeded).toBe(true)

    // 닫힌 뒤 다음 광고를 다시 받아 둔다
    await finishLoads()
    await expect(ads.showScanInterstitial()).resolves.toBe(true)
    expect(sdk.shows).toHaveLength(1)

    vi.advanceTimersByTime(INTERSTITIAL_COOLDOWN_MS)
    void ads.showScanInterstitial()
    await flush()
    expect(sdk.shows).toHaveLength(2)
  })

  it('처음 N번은 광고 없이 통과하고 스캔 횟수를 저장한다', async () => {
    sdk.store.delete('ads.scanCount')
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    for (let i = 0; i < FREE_FIRST_N; i++) await expect(ads.showScanInterstitial()).resolves.toBe(true)
    expect(sdk.shows).toHaveLength(0)
    expect(sdk.store.get('ads.scanCount')).toBe(String(FREE_FIRST_N))
    void ads.showScanInterstitial()
    await flush()
    expect(sdk.shows).toHaveLength(1)
  })

  it('광고가 떠 있는 동안의 중복 호출은 false로 무시한다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    void ads.showScanInterstitial()
    await flush()
    await expect(ads.showScanInterstitial()).resolves.toBe(false)
    expect(sdk.shows).toHaveLength(1)
  })

  it('미리 받은 광고가 없거나, 표시에 실패하거나, 응답이 없어도 스캔을 막지 않는다', async () => {
    const ads = await freshAds()
    // 로드 전
    await expect(ads.showScanInterstitial()).resolves.toBe(true)
    expect(sdk.shows).toHaveLength(0)

    await finishLoads()
    let proceeded = false
    void ads.showScanInterstitial().then(() => (proceeded = true))
    await flush()
    lastShow().onEvent({ type: 'failedToShow' })
    await flush()
    expect(proceeded).toBe(true)

    // 실패한 광고는 쿨다운에 들어가지 않는다. 다시 받아 두고 이번엔 아무 이벤트도 오지 않는 경우
    await finishLoads()
    proceeded = false
    void ads.showScanInterstitial().then(() => (proceeded = true))
    await flush()
    expect(sdk.shows).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(proceeded).toBe(true)
  })

  it('광고를 지원하지 않는 환경에서는 바로 통과한다', async () => {
    sdk.supported = false
    const ads = await freshAds()
    ads.preloadAds()
    await flush()
    expect(sdk.loads).toHaveLength(0)
    await expect(ads.showScanInterstitial()).resolves.toBe(true)
    expect(ads.getAdsSnapshot().reward).toBe('unsupported')
  })
})

describe('광고 제거 이용권', () => {
  it('보상 이벤트를 받아야만 24시간 이용권을 저장하고, 그동안 전면광고를 건너뛴다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    expect(ads.getAdsSnapshot().reward).toBe('loaded')

    const result = ads.showAdFreeReward()
    await flush()
    expect(lastShow().options.adGroupId).toBe(TEST_AD_GROUP_ID.reward)
    lastShow().onEvent({ type: 'show' })
    lastShow().onEvent({ type: 'userEarnedReward' })
    lastShow().onEvent({ type: 'dismissed' })
    await expect(result).resolves.toBe('earned')

    const until = Date.now() + AD_FREE_PASS_MS
    expect(ads.getAdsSnapshot().adFreeUntil).toBe(until)
    expect(sdk.store.get('ads.adFreeUntil')).toBe(String(until))
    expect(ads.isAdFreeActive()).toBe(true)

    // 이용권 중에는 전면광고를 받지도 띄우지도 않는다
    await flush()
    expect(sdk.loads).toHaveLength(0)
    await ads.showScanInterstitial()
    expect(sdk.shows).toHaveLength(1)
  })

  it('광고가 웹뷰를 덮는 동안 밀린 타이머가 이벤트보다 먼저 돌아도, 늦게 온 보상 이벤트로 이용권을 준다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    let result: string | undefined
    void ads.showAdFreeReward().then((r) => (result = r))
    await flush()
    const ad = lastShow()

    // 광고를 보는 동안 웹뷰 JS가 멈춰 이벤트가 하나도 오지 않다가, 닫힌 뒤 밀린 타이머가 먼저 돈다
    await vi.advanceTimersByTimeAsync(30_000)
    expect(result).toBe('closed')
    expect(ads.getAdsSnapshot().rewardShowing).toBe(false)

    // 그다음 밀린 이벤트가 몰려 온다
    ad.onEvent({ type: 'show' })
    ad.onEvent({ type: 'userEarnedReward' })
    ad.onEvent({ type: 'dismissed' })
    expect(ads.isAdFreeActive()).toBe(true)
    expect(ads.getAdsSnapshot().adFreeUntil).toBe(Date.now() + AD_FREE_PASS_MS)
  })

  it('SDK가 표시 실패를 알렸을 때만 failed다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    const result = ads.showAdFreeReward()
    await flush()
    lastShow().onEvent({ type: 'failedToShow' })
    await expect(result).resolves.toBe('failed')
  })

  it('보상 전에 닫으면 이용권을 주지 않는다', async () => {
    const ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    const result = ads.showAdFreeReward()
    await flush()
    lastShow().onEvent({ type: 'show' })
    lastShow().onEvent({ type: 'dismissed' })
    await expect(result).resolves.toBe('closed')
    expect(ads.isAdFreeActive()).toBe(false)
    expect(sdk.store.has('ads.adFreeUntil')).toBe(false)
  })

  it('저장된 이용권은 다음 실행에서도 유지되고, 만료되면 다시 광고를 띄운다', async () => {
    sdk.store.set('ads.adFreeUntil', String(Date.now() + 60_000))
    let ads = await freshAds()
    ads.preloadAds()
    await flush()
    expect(ads.isAdFreeActive()).toBe(true)
    expect(sdk.loads).toHaveLength(0)

    vi.advanceTimersByTime(60_000)
    ads = await freshAds()
    ads.preloadAds()
    await finishLoads()
    void ads.showScanInterstitial()
    await flush()
    expect(sdk.shows).toHaveLength(1)
  })
})
