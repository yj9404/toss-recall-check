export const TEST_BANNER_ID = 'ait-ad-test-banner-id'

interface AdEnv {
  VITE_ADS_MODE?: string
  VITE_AD_GROUP_HOME?: string
  VITE_AD_GROUP_DETAIL?: string
}

// 위치마다 광고 그룹을 나눠 콘솔에서 위치별 성과를 따로 본다
type AdSlot = 'VITE_AD_GROUP_HOME' | 'VITE_AD_GROUP_DETAIL'

/** 배너의 광고 그룹 ID를 정한다. live인데 ID가 비어 있으면 null → 배너를 그리지 않는다. */
export function resolveAdGroupId(env: AdEnv, mode: string, slot: AdSlot): string | null {
  const adsMode = env.VITE_ADS_MODE ?? (mode === 'live' ? 'live' : 'test')
  if (adsMode !== 'live') return TEST_BANNER_ID
  const id = env[slot]?.trim()
  return id ? id : null
}

export const homeAdGroupId = () => resolveAdGroupId(import.meta.env, import.meta.env.MODE, 'VITE_AD_GROUP_HOME')
export const detailAdGroupId = () =>
  resolveAdGroupId(import.meta.env, import.meta.env.MODE, 'VITE_AD_GROUP_DETAIL')
