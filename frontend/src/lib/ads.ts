export const TEST_BANNER_ID = 'ait-ad-test-banner-id'

interface AdEnv {
  VITE_ADS_MODE?: string
  VITE_AD_GROUP_HOME?: string
}

/** 홈 배너의 광고 그룹 ID를 정한다. live인데 ID가 비어 있으면 null → 배너를 그리지 않는다. */
export function resolveHomeAdGroupId(env: AdEnv, mode: string): string | null {
  const adsMode = env.VITE_ADS_MODE ?? (mode === 'live' ? 'live' : 'test')
  if (adsMode !== 'live') return TEST_BANNER_ID
  const id = env.VITE_AD_GROUP_HOME?.trim()
  return id ? id : null
}

export const homeAdGroupId = () => resolveHomeAdGroupId(import.meta.env, import.meta.env.MODE)
