import { loadFullScreenAd, showFullScreenAd, Storage } from '@apps-in-toss/web-framework'
import {
  AD_FREE_PASS_MS,
  FREE_FIRST_N,
  INTERSTITIAL_COOLDOWN_MS,
  LIVE_AD_GROUP_ID,
  TEST_AD_GROUP_ID,
} from './adConfig'

export const TEST_BANNER_ID = TEST_AD_GROUP_ID.banner

interface AdEnv {
  VITE_ADS_MODE?: string
  VITE_AD_GROUP_HOME?: string
}

const adsMode = (env: AdEnv, mode: string) => env.VITE_ADS_MODE ?? (mode === 'live' ? 'live' : 'test')

/**
 * 홈 배너의 광고 그룹 ID를 정한다. live인데 ID가 비어 있으면 null → 배너를 그리지 않는다.
 * 배너는 스크롤되는 홈 목록에만 둔다(비게임 출시 체크리스트: 배너는 스크롤 가능한 화면에만).
 */
export function resolveAdGroupId(env: AdEnv, mode: string): string | null {
  if (adsMode(env, mode) !== 'live') return TEST_BANNER_ID
  const id = env.VITE_AD_GROUP_HOME?.trim()
  return id ? id : null
}

export const homeAdGroupId = () => resolveAdGroupId(import.meta.env, import.meta.env.MODE)

// ─── 전면·리워드 광고 ───────────────────────────────────────────────

type FullScreenSlot = 'interstitial' | 'reward'

/** 전면·리워드 광고 그룹 ID. live인데 adConfig의 ID가 비어 있으면 null → 그 광고는 쓰지 않는다. */
export function resolveFullScreenAdGroupId(
  slot: FullScreenSlot,
  env: AdEnv,
  mode: string,
  live: Record<FullScreenSlot, string> = LIVE_AD_GROUP_ID,
): string | null {
  if (adsMode(env, mode) !== 'live') return TEST_AD_GROUP_ID[slot]
  return live[slot].trim() || null
}

const groupId = (slot: FullScreenSlot) => resolveFullScreenAdGroupId(slot, import.meta.env, import.meta.env.MODE)

/** 스캔 직전에 전면광고를 띄울지 정한다. 횟수는 이번 스캔을 포함한 누적 값이다. */
export function shouldShowInterstitial(s: {
  scanCount: number
  now: number
  lastShownAt: number
  adFreeUntil: number
}): boolean {
  if (s.scanCount <= FREE_FIRST_N) return false
  if (s.adFreeUntil > s.now) return false
  return s.now - s.lastShownAt >= INTERSTITIAL_COOLDOWN_MS
}

// 'failed'는 이번 실행에서 로드에 실패한 상태다. 다음 preloadAds() 때 다시 시도한다.
type LoadState = 'idle' | 'loading' | 'loaded' | 'failed'

const SCAN_COUNT_KEY = 'ads.scanCount'
const AD_FREE_UNTIL_KEY = 'ads.adFreeUntil'
// 저장소가 응답하지 않아도 스캔을 막지 않는다
const STORAGE_TIMEOUT_MS = 2_000
// 로드 이벤트가 오지 않아도(AdMob 최대 60초) 다음 광고 그룹 로드를 막지 않는다. 늦게 온 결과는 그대로 반영한다.
const LOAD_TIMEOUT_MS = 60_000
// 광고가 뜨지 않거나 dismissed가 오지 않아도(Android 5.255.0) 사용자를 붙잡아 두지 않는다
const SHOW_START_TIMEOUT_MS = 10_000
const SHOW_END_TIMEOUT_MS = 120_000

const loadState: Record<FullScreenSlot, LoadState> = { interstitial: 'idle', reward: 'idle' }
let showing: FullScreenSlot | null = null
// 전면광고 쿨다운은 메모리에만 둔다. 앱을 새로 시작하면 초기화된다.
let lastInterstitialAt = Number.NEGATIVE_INFINITY
let scanCount = 0
let adFreeUntil = 0
let initPromise: Promise<void> | null = null
// 여러 광고 그룹을 동시에 로드하면 이벤트가 유실되는 토스앱 버전이 있어 한 번에 하나씩 로드한다
let loadChain: Promise<void> = Promise.resolve()

function isFullScreenSupported(): boolean {
  try {
    return loadFullScreenAd.isSupported() && showFullScreenAd.isSupported()
  } catch {
    return false
  }
}

// ─── 화면에서 구독하는 상태 ───

export interface AdsSnapshot {
  /** unsupported면 리워드 버튼을 그리지 않는다 */
  reward: LoadState | 'unsupported'
  rewardShowing: boolean
  adFreeUntil: number
}

const listeners = new Set<() => void>()
let snapshot: AdsSnapshot | null = null

function buildSnapshot(): AdsSnapshot {
  return {
    reward: groupId('reward') && isFullScreenSupported() ? loadState.reward : 'unsupported',
    rewardShowing: showing === 'reward',
    adFreeUntil,
  }
}

function emit() {
  snapshot = buildSnapshot()
  for (const listener of listeners) listener()
}

export function subscribeAds(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export const getAdsSnapshot = (): AdsSnapshot => (snapshot ??= buildSnapshot())

function setLoadState(slot: FullScreenSlot, state: LoadState) {
  loadState[slot] = state
  emit()
}

// ─── 영구 저장 (토스 앱 Storage. 앱 밖이거나 실패하면 메모리 값만 쓴다) ───

function readNumber(key: string): Promise<number> {
  const read = (async () => {
    const value = Number(await Storage.getItem(key))
    return Number.isFinite(value) ? value : 0
  })().catch(() => 0)
  const timeout = new Promise<number>((resolve) => setTimeout(() => resolve(0), STORAGE_TIMEOUT_MS))
  return Promise.race([read, timeout])
}

function writeNumber(key: string, value: number) {
  try {
    Promise.resolve(Storage.setItem(key, String(value))).catch(() => {})
  } catch {
    // 토스 앱 밖(일반 브라우저 등)에서는 저장하지 않는다
  }
}

/** 앱 시작 시 저장된 스캔 횟수와 이용권 만료 시각을 메모리로 불러온다. 여러 번 불러도 한 번만 읽는다. */
export function initAds(): Promise<void> {
  initPromise ??= Promise.all([readNumber(SCAN_COUNT_KEY), readNumber(AD_FREE_UNTIL_KEY)]).then(([count, until]) => {
    scanCount = count
    adFreeUntil = until
    emit()
  })
  return initPromise
}

export const isAdFreeActive = (now = Date.now()) => adFreeUntil > now

// ─── 로드 ───

function loadOne(slot: FullScreenSlot, adGroupId: string): Promise<void> {
  return new Promise((resolve) => {
    let settled = false
    let cleanup: (() => void) | undefined
    const timer = setTimeout(resolve, LOAD_TIMEOUT_MS)
    const settle = (state: LoadState) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      cleanup?.()
      setLoadState(slot, state)
      resolve()
    }
    try {
      cleanup = loadFullScreenAd({
        options: { adGroupId },
        onEvent: (event) => {
          if (event.type === 'loaded') settle('loaded')
        },
        onError: (error) => {
          console.warn('광고 로드 실패', slot, error)
          settle('failed')
        },
      })
      if (settled) cleanup()
    } catch (e) {
      console.warn('광고 로드 실패', slot, e)
      settle('failed')
    }
  })
}

function queueLoad(slot: FullScreenSlot) {
  const adGroupId = groupId(slot)
  if (!adGroupId || !isFullScreenSupported()) return
  if (loadState[slot] === 'loading' || loadState[slot] === 'loaded' || showing === slot) return
  setLoadState(slot, 'loading')
  loadChain = loadChain.then(() => loadOne(slot, adGroupId))
}

/** 다음 노출에 쓸 전면·리워드 광고를 미리 받아 둔다. 이용권이 있는 동안은 받지 않는다. */
export function preloadAds(): void {
  void initAds().then(() => {
    if (isAdFreeActive()) return
    queueLoad('interstitial')
    queueLoad('reward')
  })
}

// ─── 노출 ───

/** 광고를 띄우고 닫히거나 실패하면 resolve한다. 실제로 화면에 떴으면 true. */
function present(slot: FullScreenSlot, adGroupId: string, onReward?: () => void): Promise<boolean> {
  showing = slot
  emit()
  return new Promise<boolean>((resolve) => {
    let done = false
    let shown = false
    let cleanup: (() => void) | undefined
    let timer: ReturnType<typeof setTimeout> | undefined
    const finish = () => {
      if (done) return
      done = true
      clearTimeout(timer)
      cleanup?.()
      showing = null
      // 한 번 보여준 광고는 다시 쓸 수 없어 새로 받아야 한다
      setLoadState(slot, 'idle')
      resolve(shown)
    }
    const arm = (ms: number) => {
      clearTimeout(timer)
      timer = setTimeout(finish, ms)
    }
    arm(SHOW_START_TIMEOUT_MS)
    try {
      cleanup = showFullScreenAd({
        options: { adGroupId },
        onEvent: (event) => {
          switch (event.type) {
            case 'show':
            case 'impression':
              shown = true
              if (slot === 'interstitial') lastInterstitialAt = Date.now()
              arm(SHOW_END_TIMEOUT_MS)
              break
            case 'userEarnedReward':
              onReward?.()
              break
            case 'dismissed':
              finish()
              break
            case 'failedToShow':
              console.warn('광고 표시 실패', slot)
              finish()
              break
          }
        },
        onError: (error) => {
          console.warn('광고 표시 실패', slot, error)
          finish()
        },
      })
      if (done) cleanup()
    } catch (e) {
      console.warn('광고 표시 실패', slot, e)
      finish()
    }
  }).then((shown) => {
    preloadAds()
    return shown
  })
}

/**
 * 바코드 사진 스캔 직전에 부른다. 띄울 차례면 전면광고를 보여주고 닫힌 뒤에 resolve한다.
 * 무료 횟수·이용권·쿨다운·미준비·실패로 광고를 건너뛰어도 바로 resolve하므로, 호출한 쪽은 결과와 무관하게 스캔을 이어간다.
 * false는 다른 광고가 떠 있는 중이라는 뜻이다. 이때는 이번 호출을 무시한다(중복 실행 방지).
 */
export async function showScanInterstitial(): Promise<boolean> {
  if (showing) return false
  await initAds()
  if (showing) return false
  scanCount += 1
  writeNumber(SCAN_COUNT_KEY, scanCount)
  const now = Date.now()
  if (!shouldShowInterstitial({ scanCount, now, lastShownAt: lastInterstitialAt, adFreeUntil })) return true
  const adGroupId = groupId('interstitial')
  // 누를 때 로드하면 사용자가 기다려야 하므로, 미리 받아 둔 광고가 없으면 이번엔 건너뛰고 다음 것을 받는다
  if (!adGroupId || loadState.interstitial !== 'loaded' || !isFullScreenSupported()) {
    preloadAds()
    return true
  }
  await present('interstitial', adGroupId)
  return true
}

export type RewardResult = 'earned' | 'closed' | 'failed'

/**
 * 리워드 광고를 보여준다. 끝까지 봐서 보상 이벤트를 받았을 때만 광고 제거 이용권(지금부터 24시간)을 저장한다.
 * closed는 광고는 떴지만 보상 전에 닫은 경우, failed는 광고를 띄우지 못한 경우다.
 */
export async function showAdFreeReward(): Promise<RewardResult> {
  if (showing) return 'failed'
  await initAds()
  const adGroupId = groupId('reward')
  if (showing || !adGroupId || loadState.reward !== 'loaded' || !isFullScreenSupported()) return 'failed'
  let earned = false
  const shown = await present('reward', adGroupId, () => {
    earned = true
    adFreeUntil = Date.now() + AD_FREE_PASS_MS
    writeNumber(AD_FREE_UNTIL_KEY, adFreeUntil)
    emit()
  })
  return earned ? 'earned' : shown ? 'closed' : 'failed'
}
